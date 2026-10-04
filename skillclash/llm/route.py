from __future__ import annotations

import random
from collections import Counter
from typing import Any

from skillclash.i18n import t
from skillclash.llm.backend import LLMBackend
from skillclash.llm.prompts import PROMPTGEN_USER_TEMPLATE, ROUTER_SYSTEM_TEMPLATE
from skillclash.model import Finding, InstallUnit, Severity, Skill
from skillclash.paths import make_ref


def select_target_skills(
    skills: list[Skill],
    overlap_clusters: list[list[str]],
    max_skills: int = 40,
) -> list[Skill]:
    """Select skills to test based on overlap clusters and highest similarity."""
    skill_by_id = {s.id: s for s in skills}
    selected_ids: list[str] = []

    # 1. From clusters
    for comp in overlap_clusters:
        for sid in comp:
            if sid in skill_by_id and sid not in selected_ids:
                selected_ids.append(sid)
                if len(selected_ids) >= max_skills:
                    break
        if len(selected_ids) >= max_skills:
            break

    # 2. Top up if fewer than 10
    if len(selected_ids) < min(10, len(skills)):
        for s in skills:
            if s.id not in selected_ids:
                selected_ids.append(s.id)
                if len(selected_ids) >= min(10, max_skills):
                    break

    return [skill_by_id[sid] for sid in selected_ids[:max_skills]]


def build_routing_listing(
    all_skills: list[Skill],
    target_skills: list[Skill],
    max_listing: int = 60,
    seed: int = 42,
) -> tuple[str, list[str]]:
    """Build Claude Code-styled skill listing text capped at max_listing."""
    target_ids = {s.id for s in target_skills}
    other_skills = [s for s in all_skills if s.id not in target_ids]

    rng = random.Random(seed)
    rng.shuffle(other_skills)

    available_slots = max_listing - len(target_skills)
    chosen_others = other_skills[: max(0, available_slots)]

    combined = list(target_skills) + chosen_others
    combined.sort(key=lambda s: s.qualified_name)

    lines = [f"- {s.qualified_name}: {s.description}" for s in combined]
    names = [s.qualified_name for s in combined]
    return "\n".join(lines), names


def generate_skill_test_prompts(
    skill: Skill,
    backend: LLMBackend,
    k: int = 4,
) -> list[str]:
    """Generate k realistic test queries for a skill using PROMPTGEN prompt."""
    body_lines = skill.body.splitlines()[:60]
    body_truncated = "\n".join(body_lines)[:2500]

    prompt = PROMPTGEN_USER_TEMPLATE.format(
        k=k,
        name=skill.name,
        description=skill.description,
        body_first_60_lines=body_truncated,
    )

    try:
        res = backend.complete_json(
            "You generate realistic user test messages for skills. Return JSON only.",
            prompt,
            temperature=0.3,
        )
        prompts = res.get("prompts", [])
        if isinstance(prompts, list) and prompts:
            return [str(p).strip() for p in prompts[:k]]
    except Exception:
        pass

    # No usable prompts: skip this skill rather than measuring it with generic filler text.
    return []


def run_route_simulation(
    units: list[InstallUnit],
    promptgen_backend: LLMBackend,
    router_backend: LLMBackend,
    *,
    overlap_clusters: list[list[str]] | None = None,
    max_route_skills: int = 40,
    prompts_per_skill: int = 4,
    repeats: int = 3,
    max_calls: int = 300,
    lang: str = "zh-TW",
) -> tuple[list[Finding], dict[str, Any]]:
    """Execute L5 routing simulation, generating confusion matrix, ROUTE-STEAL and ROUTE-DEAD."""
    invocable = [s for u in units for s in u.skills if s.model_invocable]
    if len(invocable) < 2:
        return [], {"skills": [], "matrix": []}

    targets = select_target_skills(invocable, overlap_clusters or [], max_skills=max_route_skills)
    listing_text, available_names = build_routing_listing(invocable, targets)
    available_name_set = set(available_names)

    system_prompt = ROUTER_SYSTEM_TEMPLATE.format(listing=listing_text)

    # Matrix: target_skills x (target_skills + none)
    target_qnames = [s.qualified_name for s in targets]
    n_targets = len(targets)

    # stolen_records: (source_idx, dest_idx) -> list of stolen prompts
    stolen_records: dict[tuple[int, int], list[str]] = {}

    calls_budget = max_calls
    # matrix counts: [source][dest]
    matrix_counts = [[0] * n_targets for _ in range(n_targets)]
    none_counts = [0] * n_targets
    total_queries_per_target = [0] * n_targets

    for i, target_skill in enumerate(targets):
        if calls_budget <= 0:
            break

        test_queries = generate_skill_test_prompts(
            target_skill,
            promptgen_backend,
            k=prompts_per_skill,
        )
        calls_budget -= 1

        for q in test_queries:
            votes: list[str] = []
            for r_idx in range(repeats):
                if calls_budget <= 0:
                    break
                calls_budget -= 1

                try:
                    res = router_backend.complete_json(
                        system_prompt,
                        q,
                        temperature=0.7,
                        cache_key_extra=f"repeat_{r_idx}",
                    )
                    chosen = str(res.get("skill", "none")).strip()
                    if chosen not in available_name_set:
                        chosen = "none"
                    votes.append(chosen)
                except Exception:
                    votes.append("none")

            if not votes:
                continue

            # Majority vote
            winner = Counter(votes).most_common(1)[0][0]
            total_queries_per_target[i] += 1

            if winner == "none":
                none_counts[i] += 1
            elif winner in target_qnames:
                j = target_qnames.index(winner)
                matrix_counts[i][j] += 1
                if i != j:
                    stolen_records.setdefault((i, j), []).append(q)
            else:
                # Routed to another skill not in targets
                none_counts[i] += 1

    # Compute percentages M[i][j]
    matrix_pct = [[0.0] * n_targets for _ in range(n_targets)]
    hit_rates = [0.0] * n_targets

    for i in range(n_targets):
        tot = total_queries_per_target[i]
        if tot > 0:
            for j in range(n_targets):
                matrix_pct[i][j] = round(matrix_counts[i][j] / tot, 4)
            hit_rates[i] = matrix_pct[i][i]

    findings: list[Finding] = []

    # 1. ROUTE-STEAL (WARN): i != j and M[i][j] >= 0.25
    for (i, j), stolen_prompts in stolen_records.items():
        fraction = matrix_pct[i][j]
        if fraction >= 0.25:
            sa = targets[i]
            sb = targets[j]
            sample_prompts = stolen_prompts[:3]
            sample_text = " | ".join(f'"{p}"' for p in sample_prompts)

            findings.append(
                Finding(
                    rule="ROUTE-STEAL",
                    severity=Severity.WARN,
                    title=f"{t('rule.ROUTE-STEAL.title', lang)}: {sa.qualified_name} → {sb.qualified_name} ({fraction * 100:.0f}%)",
                    message=t(
                        "route.steal.msg",
                        lang,
                        a=sa.qualified_name,
                        b=sb.qualified_name,
                        pct=fraction * 100,
                        samples=sample_text,
                    ),
                    skills=[make_ref(sa, line=None), make_ref(sb, line=None)],
                    evidence={
                        "stolen_ratio": fraction,
                        "sample_prompts": sample_prompts,
                        "count": len(stolen_prompts),
                    },
                    confidence=fraction,
                    source="route",
                    fix=t("route.steal.fix", lang, a=sa.qualified_name, b=sb.qualified_name),
                )
            )

    # 2. ROUTE-DEAD (INFO): hit_rate < 0.25
    for i in range(n_targets):
        if total_queries_per_target[i] > 0 and hit_rates[i] < 0.25:
            sa = targets[i]
            rate = hit_rates[i]
            findings.append(
                Finding(
                    rule="ROUTE-DEAD",
                    severity=Severity.INFO,
                    title=(
                        f"{t('rule.ROUTE-DEAD.title', lang)}: {sa.qualified_name} "
                        f"({t('label.hit_rate', lang)} {rate * 100:.0f}%)"
                    ),
                    message=t("route.dead.msg", lang, pct=rate * 100),
                    skills=[make_ref(sa, line=None)],
                    evidence={"hit_rate": rate},
                    confidence=round(1.0 - rate, 3),
                    source="route",
                    fix=t("route.dead.fix", lang, name=sa.qualified_name),
                )
            )

    route_stats = {
        "skills": target_qnames,
        "matrix": matrix_pct,
    }

    return findings, route_stats
