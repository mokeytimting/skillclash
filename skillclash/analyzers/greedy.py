from __future__ import annotations

import re
from typing import Any

from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Severity, UnitKind
from skillclash.paths import make_ref

WEIGHT_3_PATTERNS = [
    r"\buse\s+(?:this\s+)?(?:skill\s+)?(?:for|on|with)\s+(?:any|all|every)\b",
    r"\b(?:always|proactively|automatically)\s+(?:use|invoke|trigger|activate|apply)\b",
    r"\bmust\s+(?:be\s+)?(?:used|invoked)\b",
    r"\buse\s+(?:it|this)\s+by\s+default\b",
    r"\buse\s+(?:this\s+skill\s+)?proactively\b",
    r"\bbefore\s+(?:finishing|sending|writing)\s+any\s+(?:reply|response|answer)\b",
    r"一律使用",
    r"都要使用",
    r"都必須使用",
    r"都必须使用",
    r"自动(?:使用|触发|套用|启用)",
    r"自動(?:使用|觸發|套用|啟用)",
]

WEIGHT_2_PATTERNS = [
    r"\bany\s+(?:task|request|question|code|file|project)s?\b",
    r"\b(?:every|all)\s+(?:task|request|conversation|session|message|time)s?\b",
    r"\beven\s+if\s+[\w\s]{0,40}?(?:doesn't|does\s+not|didn't|not)\s+(?:mention|ask|say)\b",
    r"任何(?:任務|任务|請求|请求|時候|时候|情況|情况|問題|问题|程式)",
    r"所有(?:任務|任务|請求|请求|對話|对话|情況|情况)",
    r"即使[\w\s]{0,20}?(?:沒有|没有)(?:提到|要求|說|说)",
]

WEIGHT_1_PATTERNS = [
    r"\bwhenever\b",
    r"\bregardless\b",
    r"\bno\s+matter\b",
    r"不論",
    r"不论",
    r"無論",
    r"无论",
]


def score_greedy_description(
    description: str, lang: str = "zh-TW"
) -> tuple[float, list[dict[str, Any]]]:
    """Score a skill description for over-greedy triggers."""
    if not description:
        return 0.0, []

    desc_lower = description.lower()
    matches: list[dict[str, Any]] = []
    total_score = 0.0

    # Weight 3
    for pat in WEIGHT_3_PATTERNS:
        for m in re.finditer(pat, desc_lower if pat.startswith(r"\b") else description):
            matches.append(
                {
                    "phrase": m.group(0),
                    "weight": 3,
                    "span": [m.start(), m.end()],
                }
            )
            total_score += 3.0

    # Weight 2
    for pat in WEIGHT_2_PATTERNS:
        for m in re.finditer(pat, desc_lower if pat.startswith(r"\b") else description):
            matches.append(
                {
                    "phrase": m.group(0),
                    "weight": 2,
                    "span": [m.start(), m.end()],
                }
            )
            total_score += 2.0

    # Weight 1
    for pat in WEIGHT_1_PATTERNS:
        for m in re.finditer(pat, desc_lower if pat.startswith(r"\b") else description):
            matches.append(
                {
                    "phrase": m.group(0),
                    "weight": 1,
                    "span": [m.start(), m.end()],
                }
            )
            total_score += 1.0

    # Keyword stuffing: len > 600 and > 15 comma/頓號 terms
    if len(description) > 600:
        commas = description.count(",") + description.count("，") + description.count("、")
        if commas >= 15:
            matches.append(
                {
                    "phrase": t("greedy.stuffing", lang, n=commas),
                    "weight": 2,
                    "span": [0, len(description)],
                }
            )
            total_score += 2.0

    return total_score, matches


def check_greedy(
    units: list[InstallUnit],
    *,
    warn_threshold: float = 5.0,
    info_threshold: float = 5.0,
    lang: str = "zh-TW",
) -> list[Finding]:
    """Check for overly greedy descriptions that aggressively hijack user requests."""
    findings: list[Finding] = []

    for u in units:
        if u.kind == UnitKind.MEMORY:
            continue
        for sk in u.skills:
            if not sk.model_invocable or not sk.description:
                continue

            score, matched_phrases = score_greedy_description(sk.description, lang)
            if score < info_threshold:
                continue

            sev = Severity.WARN if score >= warn_threshold else Severity.INFO
            matched_names = [m["phrase"] for m in matched_phrases]

            evidence = {
                "score": score,
                "matches": matched_phrases,
                "description": sk.description,
            }

            findings.append(
                Finding(
                    rule="GREEDY",
                    severity=sev,
                    title=(
                        f"{t('rule.GREEDY.title', lang)}: {sk.qualified_name} "
                        f"({t('label.score', lang)} {score:.1f})"
                    ),
                    message=t(
                        "greedy.msg",
                        lang,
                        score=score,
                        phrases=t("label.list_sep", lang).join(matched_names),
                    ),
                    skills=[make_ref(sk)],
                    evidence=evidence,
                    confidence=min(1.0, score / 10.0),
                    source="static",
                    fix=t("greedy.fix", lang, name=sk.qualified_name),
                )
            )

    return findings
