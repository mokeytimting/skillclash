from __future__ import annotations

import re
from typing import Any

from skillclash.i18n import t
from skillclash.llm.backend import LLMBackend
from skillclash.llm.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_USER_PROMPT_TEMPLATE
from skillclash.model import Finding, InstallUnit, Severity, Skill


def normalize_whitespace_for_quote_check(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def verify_quote_presence(quote: str, full_text: str) -> bool:
    """Verify that quote actually appears in full_text ignoring whitespace and case."""
    if not quote or not full_text:
        return False
    q_norm = normalize_whitespace_for_quote_check(quote)
    if len(q_norm) < 4:
        return True
    f_norm = normalize_whitespace_for_quote_check(full_text)
    return q_norm in f_norm


def prepare_excerpts(skill: Skill, rule: str, evidence: dict[str, Any], side: str = "a") -> str:
    """Prepare relevant excerpts (up to 3,000 chars) for judge prompt.

    ``side`` is "a" or "b": which half of each rule pair belongs to this skill.
    """
    if rule == "RULE-CONFLICT":
        lines = skill.body.splitlines()
        target_lines = set()
        for rp in evidence.get("rule_pairs", []):
            line_no = rp.get(f"{side}_line")
            if line_no:
                # 1 line before and after
                idx = line_no - skill.body_line_offset
                for offset in (-1, 0, 1):
                    if 0 <= idx + offset < len(lines):
                        target_lines.add(idx + offset)

        if target_lines:
            excerpt_lines = [lines[i] for i in sorted(target_lines)]
            return "\n".join(excerpt_lines)[:3000]

    # Default / OVERLAP: first 40 lines
    lines = skill.body.splitlines()[:40]
    return "\n".join(lines)[:3000]


def run_judge(
    findings: list[Finding],
    units: list[InstallUnit],
    backend: LLMBackend,
    *,
    limit: int = 50,
    max_calls: int = 300,
    lang: str = "zh-TW",
) -> tuple[list[Finding], list[dict[str, Any]], bool]:
    """Run L4 LLM judgment on OVERLAP and RULE-CONFLICT candidates.

    Returns:
        (updated_findings, dismissed_by_llm, truncated)
    """
    skill_map: dict[str, Skill] = {}
    for u in units:
        for sk in u.skills:
            skill_map[sk.id] = sk

    # Candidates: OVERLAP or RULE-CONFLICT
    candidates = [f for f in findings if f.rule in ("OVERLAP", "RULE-CONFLICT")]
    candidates.sort(key=lambda f: f.confidence, reverse=True)
    targets = candidates[:limit]

    updated_findings: list[Finding] = []
    dismissed_by_llm: list[dict[str, Any]] = []
    target_fps = {f.fingerprint for f in targets}

    calls_made = 0
    truncated = False
    lang_name = "Traditional Chinese (繁體中文)" if lang == "zh-TW" else "English"

    for f in findings:
        if f.fingerprint not in target_fps:
            updated_findings.append(f)
            continue

        if calls_made >= max_calls:
            truncated = True
            updated_findings.append(f)
            continue

        if len(f.skills) < 2:
            updated_findings.append(f)
            continue

        sa = skill_map.get(f.skills[0].skill_id)
        sb = skill_map.get(f.skills[1].skill_id)

        if not sa or not sb:
            updated_findings.append(f)
            continue

        excerpts_a = prepare_excerpts(sa, f.rule, f.evidence, side="a")
        excerpts_b = prepare_excerpts(sb, f.rule, f.evidence, side="b")

        user_prompt = JUDGE_USER_PROMPT_TEMPLATE.format(
            qualified_name_a=sa.qualified_name,
            description_a=sa.description,
            excerpts_a=excerpts_a,
            qualified_name_b=sb.qualified_name,
            description_b=sb.description,
            excerpts_b=excerpts_b,
            reason=f.message,
            lang_name=lang_name,
        )

        calls_made += 1
        judge_res = None
        try:
            judge_res = backend.complete_json(JUDGE_SYSTEM_PROMPT, user_prompt)
        except Exception:
            # Retry once
            if calls_made < max_calls:
                calls_made += 1
                try:
                    retry_prompt = user_prompt + "\n\nCRITICAL: Please respond with valid JSON only."
                    judge_res = backend.complete_json(JUDGE_SYSTEM_PROMPT, retry_prompt)
                except Exception as e:
                    f.evidence["judge_error"] = str(e)

        if not judge_res or "verdict" not in judge_res:
            updated_findings.append(f)
            continue

        verdict = str(judge_res.get("verdict", "")).lower()
        conf = float(judge_res.get("confidence", 0.5))
        quote_a = str(judge_res.get("quote_a", ""))
        quote_b = str(judge_res.get("quote_b", ""))
        explanation = str(judge_res.get("explanation", ""))
        suggested_fix = str(judge_res.get("suggested_fix", ""))

        # 5. Verify quotes against actual body
        quote_a_ok = verify_quote_presence(quote_a, sa.body)
        quote_b_ok = verify_quote_presence(quote_b, sb.body)

        if (quote_a and not quote_a_ok) or (quote_b and not quote_b_ok):
            conf *= 0.5
            f.evidence["quote_unverified"] = True

        f.evidence["llm_verdict"] = verdict
        f.evidence["llm_explanation"] = explanation
        f.evidence["llm_quote_a"] = quote_a
        f.evidence["llm_quote_b"] = quote_b
        f.confidence = conf
        f.source = "llm"
        if suggested_fix:
            f.fix = suggested_fix

        # 4. Handle verdict transitions
        if verdict == "conflict" and conf >= 0.6:
            f.severity = Severity.WARN
            if f.rule == "RULE-CONFLICT":
                f.title = t("rule.RULE-CONFLICT.title_confirmed", lang)
            updated_findings.append(f)

        elif verdict == "overlap":
            f.severity = Severity.WARN
            if f.rule == "RULE-CONFLICT":
                f.rule = "OVERLAP"
                f.severity = Severity.INFO
                f.title = f"{t('rule.OVERLAP.title', lang)}: {sa.qualified_name} ↔ {sb.qualified_name}"
            updated_findings.append(f)

        elif verdict in ("compatible", "unrelated") and conf >= 0.7:
            # Dismiss finding
            dismissed_by_llm.append(
                {
                    "fingerprint": f.fingerprint,
                    "rule": f.rule,
                    "skills": [s.skill_id for s in f.skills],
                    "verdict": verdict,
                    "confidence": conf,
                    "explanation": explanation,
                }
            )
        else:
            updated_findings.append(f)

    return updated_findings, dismissed_by_llm, truncated
