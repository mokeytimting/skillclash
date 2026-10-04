from __future__ import annotations

from typing import Any

from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Rule, Severity, Skill
from skillclash.paths import make_ref, same_pack, units_by_skill


def compare_rules(
    rule_a: Rule,
    rule_b: Rule,
) -> tuple[float, set[str]] | None:
    """Compare two rules; return (score, shared_topics) if conflicting."""
    if rule_a.polarity == rule_b.polarity:
        return None

    shared = rule_a.topic & rule_b.topic
    if len(shared) < 2:
        return None

    union = rule_a.topic | rule_b.topic
    jaccard = len(shared) / len(union) if union else 0.0

    if jaccard < 0.35:
        return None

    score = jaccard * (rule_a.strength + rule_b.strength) / 4.0
    return score, shared


def check_rule_conflicts(
    units: list[InstallUnit],
    *,
    intra: bool = False,
    lang: str = "zh-TW",
) -> list[Finding]:
    """Analyze L3 static rule conflicts across install units (including MEMORY)."""
    findings: list[Finding] = []

    # Gather all skills with rules
    unit_of = units_by_skill(units)
    all_skills: list[Skill] = []
    for u in units:
        for sk in u.skills:
            if sk.rules:
                all_skills.append(sk)

    if len(all_skills) < 2:
        return findings

    checked_pairs: set[tuple[str, str]] = set()

    for i in range(len(all_skills)):
        for j in range(i + 1, len(all_skills)):
            sa, sb = all_skills[i], all_skills[j]
            if sa.unit_id == sb.unit_id and not intra:
                continue
            if same_pack(unit_of[sa.id], unit_of[sb.id]) and not intra:
                continue

            if sa.id > sb.id:
                sa, sb = sb, sa

            pair_key = (sa.id, sb.id)
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            # Compare all rule combinations
            conflict_evidence: list[dict[str, Any]] = []
            all_shared_topics: set[str] = set()

            for ra in sa.rules:
                for rb in sb.rules:
                    res = compare_rules(ra, rb)
                    if res:
                        score, shared = res
                        all_shared_topics.update(shared)
                        conflict_evidence.append(
                            {
                                "a_text": ra.text,
                                "a_line": ra.line,
                                "a_pol": ra.polarity,
                                "b_text": rb.text,
                                "b_line": rb.line,
                                "b_pol": rb.polarity,
                                "score": round(score, 3),
                                "shared_topics": sorted(shared),
                            }
                        )

            if not conflict_evidence:
                continue

            # Keep top 3 highest scoring rule pairs
            conflict_evidence.sort(key=lambda x: x["score"], reverse=True)
            top_3 = conflict_evidence[:3]
            max_score = top_3[0]["score"]

            quote_a = top_3[0]["a_text"]
            quote_b = top_3[0]["b_text"]
            topics = sorted(all_shared_topics)

            msg = t(
                "rule_conflict.msg",
                lang,
                topics=t("label.list_sep", lang).join(topics),
                la=top_3[0]["a_line"],
                qa=quote_a,
                lb=top_3[0]["b_line"],
                qb=quote_b,
            )

            evidence = {
                "max_score": max_score,
                "shared_topics": topics,
                "rule_pairs": top_3,
            }

            findings.append(
                Finding(
                    rule="RULE-CONFLICT",
                    severity=Severity.INFO,  # Static detection alone is never above INFO
                    title=f"{t('rule.RULE-CONFLICT.title', lang)}: {sa.qualified_name} ↔ {sb.qualified_name}",
                    message=msg,
                    skills=[
                        make_ref(sa, line=top_3[0]["a_line"], quote=quote_a),
                        make_ref(sb, line=top_3[0]["b_line"], quote=quote_b),
                    ],
                    evidence=evidence,
                    confidence=round(max_score, 3),
                    source="static",
                    fix=t("rule_conflict.fix", lang, a=sa.qualified_name, b=sb.qualified_name),
                )
            )

    return findings
