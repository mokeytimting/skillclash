from __future__ import annotations

import re
from typing import Any

from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Severity, SkillRef

INLINE_IGNORE_PATTERN = re.compile(
    r"<!--\s*skillclash-ignore:\s*([A-Za-z0-9_*]+)(?:\s+with=([^\s]+))?(?:\s+reason=[\"'](.*?)[\"'])?\s*-->"
)


def parse_inline_suppressions(body: str) -> list[dict[str, Any]]:
    """Parse inline suppression comments from markdown body."""
    suppressions: list[dict[str, Any]] = []
    for m in INLINE_IGNORE_PATTERN.finditer(body):
        rule = m.group(1)
        target = m.group(2)
        reason = m.group(3) or "inline suppression"
        suppressions.append(
            {
                "rule": rule,
                "target": target,
                "reason": reason,
                "origin": "inline",
            }
        )
    return suppressions


def match_skill_identifier(pattern: str, ref: SkillRef) -> bool:
    """Check if a skill reference matches an identifier pattern (id, name, qualified_name)."""
    p = pattern.lower().strip()
    return (
        p == ref.name.lower()
        or p == ref.skill_id.lower()
        or (ref.qualified_name is not None and p == ref.qualified_name.lower())
    )


def apply_suppressions(
    findings: list[Finding],
    units: list[InstallUnit],
    config: dict[str, Any],
    lang: str = "zh-TW",
) -> tuple[list[Finding], list[Finding]]:
    """Apply config severity adjustments, config ignores, inline ignores, and report unused rules.

    Returns:
        (active_findings, suppressed_findings)
    """
    severity_overrides = config.get("severity", {})
    config_ignores = config.get("ignore", [])
    config_overrides = config.get("override", [])

    # Gather inline suppressions per skill
    skill_inline_suppressions: dict[str, list[dict[str, Any]]] = {}
    for u in units:
        for sk in u.skills:
            if "<!--" in sk.body and "skillclash-ignore:" in sk.body:
                inlines = parse_inline_suppressions(sk.body)
                if inlines:
                    skill_inline_suppressions[sk.id] = inlines

    active: list[Finding] = []
    suppressed: list[Finding] = []

    # Track usage of config ignore/override rules
    used_ignores: set[int] = set()
    used_overrides: set[int] = set()

    for f in findings:
        suppressed_reason: str | None = None

        # 1. Config severity overrides
        rule_sev = severity_overrides.get(f.rule)
        if rule_sev:
            rule_sev_lower = str(rule_sev).lower()
            if rule_sev_lower == "off":
                suppressed_reason = f"config: severity {f.rule} is off"
            elif rule_sev_lower in ("info", "warn", "error"):
                f.severity = Severity(rule_sev_lower)

        # 2. Config [[ignore]] rules
        if not suppressed_reason:
            for idx, ign in enumerate(config_ignores):
                target_rule = ign.get("rule", "*")
                if target_rule != "*" and target_rule != f.rule:
                    continue

                # Check skills or pair
                ign_skills = ign.get("skills") or ign.get("pair") or []
                if not ign_skills:
                    # Global rule ignore
                    suppressed_reason = ign.get("reason") or "config: global rule ignore"
                    used_ignores.add(idx)
                    break

                # If pair is specified, both must match
                if "pair" in ign and len(ign_skills) >= 2:
                    if len(f.skills) >= 2:
                        p1, p2 = ign_skills[0], ign_skills[1]
                        match_1 = match_skill_identifier(p1, f.skills[0]) or match_skill_identifier(p1, f.skills[1])
                        match_2 = match_skill_identifier(p2, f.skills[0]) or match_skill_identifier(p2, f.skills[1])
                        if match_1 and match_2:
                            suppressed_reason = ign.get("reason") or "config: ignore pair"
                            used_ignores.add(idx)
                            break
                else:
                    # Any of the skills match
                    for pattern in ign_skills:
                        if any(match_skill_identifier(pattern, s) for s in f.skills):
                            suppressed_reason = ign.get("reason") or f"config: ignore skill {pattern}"
                            used_ignores.add(idx)
                            break
                    if suppressed_reason:
                        break

        # 3. Config [[override]] rules (specifically for RULE-CONFLICT topics)
        if not suppressed_reason and f.rule == "RULE-CONFLICT":
            for idx, ovr in enumerate(config_overrides):
                ovr_skill = ovr.get("skill", "")
                ovr_topics = set(ovr.get("topics", []))
                reason = ovr.get("reason") or "config: deliberate override"

                if any(match_skill_identifier(ovr_skill, s) for s in f.skills):
                    shared_in_evidence = set(f.evidence.get("shared_topics", []))
                    if shared_in_evidence & ovr_topics:
                        suppressed_reason = reason
                        used_overrides.add(idx)
                        break

        # 4. Inline comment suppressions
        if not suppressed_reason:
            for sref in f.skills:
                inlines = skill_inline_suppressions.get(sref.skill_id, [])
                for inl in inlines:
                    if inl["rule"] == "*" or inl["rule"] == f.rule:
                        target = inl.get("target")
                        if not target:
                            suppressed_reason = f"inline: {inl['reason']}"
                            break
                        # Check target
                        other_skills = [s for s in f.skills if s.skill_id != sref.skill_id]
                        if any(match_skill_identifier(target, o) for o in other_skills):
                            suppressed_reason = f"inline: {inl['reason']}"
                            break
                if suppressed_reason:
                    break

        if suppressed_reason:
            f.suppressed_by = suppressed_reason
            suppressed.append(f)
        else:
            active.append(f)

    # 5. Check for unused config ignore/override rules -> SUPPRESS-UNUSED (INFO)
    for idx, ign in enumerate(config_ignores):
        if idx not in used_ignores:
            desc_rule = ign.get("rule", "*")
            active.append(
                Finding(
                    rule="SUPPRESS-UNUSED",
                    severity=Severity.INFO,
                    title=f"{t('rule.SUPPRESS-UNUSED.title', lang)}: {desc_rule}",
                    message=t("suppress.unused.msg", lang, rule=desc_rule, reason=ign.get("reason", "")),
                    skills=[],
                    evidence={"config_ignore": ign},
                    confidence=1.0,
                    source="static",
                    fix=t("suppress.unused.fix", lang),
                )
            )

    return active, suppressed
