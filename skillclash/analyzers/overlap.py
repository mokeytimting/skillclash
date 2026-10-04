from __future__ import annotations

from typing import Any

from skillclash.analyzers.similarity import (
    build_tfidf_model,
    compute_tfidf_vector,
    cosine_similarity,
)
from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Severity, Skill, UnitKind
from skillclash.parse.tokenize import tokenize
from skillclash.paths import make_ref, same_pack, units_by_skill


def get_trigger_text(skill: Skill) -> str:
    """Build the text the model routes on: name + description + when_to_use + triggers."""
    name_spaced = skill.name.replace("-", " ").replace("_", " ")
    parts = [name_spaced, skill.description]

    for key in ("when_to_use", "triggers"):
        value = skill.frontmatter.get(key)
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        elif value:
            parts.append(str(value))

    return " ".join(parts)


def find_connected_components(nodes: set[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Compute connected components of a graph."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for u, v in edges:
        adj.setdefault(u, []).append(v)
        adj.setdefault(v, []).append(u)

    visited: set[str] = set()
    components: list[list[str]] = []

    for node in sorted(nodes):
        if node not in visited:
            comp: list[str] = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for neighbor in adj.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(comp) > 1:
                components.append(sorted(comp))

    return components


def check_overlap(
    units: list[InstallUnit],
    name_clash_pairs: set[tuple[str, str]],
    *,
    warn_threshold: float = 0.25,
    info_threshold: float = 0.20,
    intra: bool = False,
    lang: str = "zh-TW",
) -> tuple[list[Finding], dict[str, Any]]:
    """Compute L2 trigger overlap using TF-IDF and inverted index."""
    findings: list[Finding] = []

    # Filter invocable skills
    invocable_skills: list[Skill] = []
    for u in units:
        if u.kind == UnitKind.MEMORY:
            continue
        for sk in u.skills:
            if sk.model_invocable:
                invocable_skills.append(sk)

    if len(invocable_skills) < 2:
        return findings, {"overlap_pairs_total": 0, "overlap_clusters": []}

    # 1. Tokenize trigger texts
    skill_tokens: dict[str, list[str]] = {}
    docs: list[list[str]] = []
    for sk in invocable_skills:
        toks = tokenize(get_trigger_text(sk))
        skill_tokens[sk.id] = toks
        docs.append(toks)

    # 2. Build IDF model
    idf_dict, median_idf = build_tfidf_model(docs)

    # 3. Compute normalized TF-IDF vectors
    vectors: dict[str, dict[str, float]] = {}
    for sk in invocable_skills:
        vectors[sk.id] = compute_tfidf_vector(skill_tokens[sk.id], idf_dict)

    # 4. Inverted index for terms with idf >= median_idf (for large sets)
    min_idf = 0.0 if len(invocable_skills) <= 20 else median_idf
    inv_index: dict[str, list[str]] = {}
    for sk in invocable_skills:
        vec = vectors[sk.id]
        for term in vec:
            if idf_dict.get(term, 0) >= min_idf:
                inv_index.setdefault(term, []).append(sk.id)

    # Candidate pairs
    candidate_pairs: set[tuple[str, str]] = set()
    for term, sids in inv_index.items():
        if len(sids) > 1:
            for i in range(len(sids)):
                for j in range(i + 1, len(sids)):
                    a, b = sids[i], sids[j]
                    if a > b:
                        a, b = b, a
                    candidate_pairs.add((a, b))

    skill_by_id = {s.id: s for s in invocable_skills}
    unit_of = units_by_skill(units)

    # Calculate cosine for candidates
    # Group by skill to enforce max 5 most similar targets per skill
    raw_pairs: list[tuple[Skill, Skill, float, list[tuple[str, float]]]] = []
    total_pairs_count = 0
    warn_edges: list[tuple[str, str]] = []
    cluster_nodes: set[str] = set()

    for sid_a, sid_b in candidate_pairs:
        if (sid_a, sid_b) in name_clash_pairs:
            # Skip pairs already having NAME-CLASH
            continue

        sa = skill_by_id[sid_a]
        sb = skill_by_id[sid_b]

        if same_pack(unit_of[sa.id], unit_of[sb.id]) and not intra:
            continue

        cos, shared_terms = cosine_similarity(vectors[sid_a], vectors[sid_b])
        if cos < info_threshold:
            continue

        total_pairs_count += 1
        raw_pairs.append((sa, sb, cos, shared_terms))

        if cos >= warn_threshold:
            warn_edges.append((sa.id, sb.id))
            cluster_nodes.add(sa.id)
            cluster_nodes.add(sb.id)

    # Sort all pairs descending by cosine
    raw_pairs.sort(key=lambda x: x[2], reverse=True)

    # Cap at most 5 per skill
    skill_pair_counts: dict[str, int] = {}
    capped_pairs: list[tuple[Skill, Skill, float, list[tuple[str, float]]]] = []

    for sa, sb, cos, shared_terms in raw_pairs:
        cnt_a = skill_pair_counts.get(sa.id, 0)
        cnt_b = skill_pair_counts.get(sb.id, 0)
        if cnt_a < 5 and cnt_b < 5:
            capped_pairs.append((sa, sb, cos, shared_terms))
            skill_pair_counts[sa.id] = cnt_a + 1
            skill_pair_counts[sb.id] = cnt_b + 1

    # Generate Findings
    for sa, sb, cos, shared_terms in capped_pairs:
        sev = Severity.WARN if cos >= warn_threshold else Severity.INFO
        if same_pack(unit_of[sa.id], unit_of[sb.id]):
            sev = Severity.INFO

        top_terms = [term for term, _ in shared_terms[:8]]
        evidence = {
            "cosine": round(cos, 3),
            "shared_terms": top_terms,
            "desc_a": sa.description,
            "desc_b": sb.description,
        }

        findings.append(
            Finding(
                rule="OVERLAP",
                severity=sev,
                title=f"{t('rule.OVERLAP.title', lang)} {cos:.2f}: {sa.qualified_name} ↔ {sb.qualified_name}",
                message=t("overlap.msg", lang, cosine=cos, terms=t("label.list_sep", lang).join(top_terms)),
                skills=[make_ref(sa), make_ref(sb)],
                evidence=evidence,
                confidence=round(cos, 3),
                source="static",
                fix=t("overlap.fix", lang, a=sa.qualified_name, b=sb.qualified_name),
            )
        )

    # Compute overlap clusters
    clusters = find_connected_components(cluster_nodes, warn_edges)

    overlap_stats = {
        "overlap_pairs_total": total_pairs_count,
        "overlap_clusters": clusters,
    }

    return findings, overlap_stats
