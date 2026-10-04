from __future__ import annotations

import re

from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Severity, SkillRef, UnitKind
from skillclash.paths import display_origin, make_ref

# agentskills.io: 1-64 chars, a-z 0-9 and hyphens, no leading/trailing or consecutive hyphens
KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DESC_MAX = 1024
CJK_CHAR_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def is_cjk_dominant(text: str) -> bool:
    """Check if text is predominantly Chinese/Japanese/Korean characters."""
    cjk_count = sum(1 for ch in text if CJK_CHAR_PATTERN.match(ch))
    return cjk_count >= (len(text) * 0.25)


def check_spec(units: list[InstallUnit], lang: str = "zh-TW") -> list[Finding]:
    """Run L0 specification and source error checks."""
    findings: list[Finding] = []

    for unit in units:
        # Check source-level warnings (SRC-FETCH, SRC-UNSUPPORTED, SRC-STUB-BROKEN)
        for warn in unit.warnings:
            if "SRC-FETCH:" in warn:
                findings.append(
                    Finding(
                        rule="SRC-FETCH",
                        severity=Severity.ERROR,
                        title=t("rule.SRC-FETCH.title", lang),
                        message=f"{t('rule.SRC-FETCH.desc', lang)} ({display_origin(unit.origin)})",
                        skills=[
                            SkillRef(
                                skill_id=unit.id,
                                name=unit.label,
                                unit_id=unit.id,
                                path=display_origin(unit.origin),
                                quote=warn[:200],
                            )
                        ],
                        evidence={"warning": warn},
                        confidence=1.0,
                        source="static",
                    )
                )
            elif "SRC-UNSUPPORTED:" in warn:
                findings.append(
                    Finding(
                        rule="SRC-UNSUPPORTED",
                        severity=Severity.INFO,
                        title=t("rule.SRC-UNSUPPORTED.title", lang),
                        message=f"{t('rule.SRC-UNSUPPORTED.desc', lang)} ({warn})",
                        skills=[
                            SkillRef(
                                skill_id=unit.id,
                                name=unit.label,
                                unit_id=unit.id,
                                path=display_origin(unit.origin),
                                quote=warn[:200],
                            )
                        ],
                        evidence={"warning": warn},
                        confidence=1.0,
                        source="static",
                    )
                )
            elif "Broken or invalid stub" in warn:
                findings.append(
                    Finding(
                        rule="SRC-STUB-BROKEN",
                        severity=Severity.WARN,
                        title=t("rule.SRC-STUB-BROKEN.title", lang),
                        message=f"{t('rule.SRC-STUB-BROKEN.desc', lang)} ({warn})",
                        skills=[
                            SkillRef(
                                skill_id=unit.id,
                                name=unit.label,
                                unit_id=unit.id,
                                path=display_origin(unit.origin),
                                quote=warn[:200],
                            )
                        ],
                        evidence={"warning": warn},
                        confidence=1.0,
                        source="static",
                    )
                )

        # Skip detailed checks for memory units
        if unit.kind == UnitKind.MEMORY:
            continue

        for sk in unit.skills:
            ref = make_ref(sk)

            # SPEC-NO-FRONTMATTER
            if sk.frontmatter_error == "missing":
                findings.append(
                    Finding(
                        rule="SPEC-NO-FRONTMATTER",
                        severity=Severity.ERROR,
                        title=t("rule.SPEC-NO-FRONTMATTER.title", lang),
                        message=t("rule.SPEC-NO-FRONTMATTER.desc", lang),
                        skills=[ref],
                        evidence={"path": ref.path},
                        confidence=1.0,
                        source="static",
                        fix=t("spec.fix.no_frontmatter", lang),
                    )
                )
                continue

            # SPEC-BAD-YAML
            if sk.frontmatter_error and sk.frontmatter_error != "missing":
                findings.append(
                    Finding(
                        rule="SPEC-BAD-YAML",
                        severity=Severity.ERROR,
                        title=t("rule.SPEC-BAD-YAML.title", lang),
                        message=f"{t('rule.SPEC-BAD-YAML.desc', lang)} ({sk.frontmatter_error})",
                        skills=[ref],
                        evidence={"error": sk.frontmatter_error},
                        confidence=1.0,
                        source="static",
                        fix=t("spec.fix.bad_yaml", lang),
                    )
                )

            # SPEC-NO-NAME
            has_explicit_name = "name" in sk.frontmatter and bool(sk.frontmatter["name"])
            if not has_explicit_name:
                findings.append(
                    Finding(
                        rule="SPEC-NO-NAME",
                        severity=Severity.WARN,
                        title=t("rule.SPEC-NO-NAME.title", lang),
                        message=t("rule.SPEC-NO-NAME.desc", lang),
                        skills=[ref],
                        evidence={"fallback_name": sk.name},
                        confidence=1.0,
                        source="static",
                        fix=t("spec.fix.no_name", lang, dir=sk.dir.name),
                    )
                )

            # SPEC-NAME-FORMAT
            if has_explicit_name:
                raw_name = str(sk.frontmatter["name"]).strip()
                if (
                    len(raw_name) < 1
                    or len(raw_name) > 64
                    or not KEBAB_CASE_PATTERN.match(raw_name)
                ):
                    findings.append(
                        Finding(
                            rule="SPEC-NAME-FORMAT",
                            severity=Severity.WARN,
                            title=t("rule.SPEC-NAME-FORMAT.title", lang),
                            message=f"{t('rule.SPEC-NAME-FORMAT.desc', lang)} ({t('spec.current', lang, v=raw_name)})",
                            skills=[ref],
                            evidence={"name": raw_name, "len": len(raw_name)},
                            confidence=1.0,
                            source="static",
                            fix=t("spec.fix.name_format", lang),
                        )
                    )

            # SPEC-NAME-DIR
            if has_explicit_name and sk.name != sk.dir.name:
                findings.append(
                    Finding(
                        rule="SPEC-NAME-DIR",
                        severity=Severity.INFO,
                        title=t("rule.SPEC-NAME-DIR.title", lang),
                        message=f"{t('rule.SPEC-NAME-DIR.desc', lang)} (name='{sk.name}', dir='{sk.dir.name}')",
                        skills=[ref],
                        evidence={"name": sk.name, "dir": sk.dir.name},
                        confidence=1.0,
                        source="static",
                        fix=t("spec.fix.name_dir", lang),
                    )
                )

            # SPEC-NO-DESC
            if not sk.description:
                findings.append(
                    Finding(
                        rule="SPEC-NO-DESC",
                        severity=Severity.ERROR,
                        title=t("rule.SPEC-NO-DESC.title", lang),
                        message=t("rule.SPEC-NO-DESC.desc", lang),
                        skills=[ref],
                        evidence={"path": ref.path},
                        confidence=1.0,
                        source="static",
                        fix=t("spec.fix.no_desc", lang),
                    )
                )
            else:
                desc_len = len(sk.description)
                # SPEC-DESC-LONG
                if desc_len > DESC_MAX:
                    findings.append(
                        Finding(
                            rule="SPEC-DESC-LONG",
                            severity=Severity.WARN,
                            title=t("rule.SPEC-DESC-LONG.title", lang),
                            message=f"{t('rule.SPEC-DESC-LONG.desc', lang)} ({t('spec.length', lang, n=desc_len, max=DESC_MAX)})",
                            skills=[ref],
                            evidence={"length": desc_len},
                            confidence=1.0,
                            source="static",
                            fix=t("spec.fix.desc_long", lang),
                        )
                    )
                else:
                    # SPEC-DESC-SHORT
                    is_cjk = is_cjk_dominant(sk.description)
                    min_len = 15 if is_cjk else 40
                    if desc_len < min_len:
                        findings.append(
                            Finding(
                                rule="SPEC-DESC-SHORT",
                                severity=Severity.INFO,
                                title=t("rule.SPEC-DESC-SHORT.title", lang),
                                message=f"{t('rule.SPEC-DESC-SHORT.desc', lang)} ({t('spec.length_min', lang, n=desc_len, min=min_len)})",
                                skills=[ref],
                                evidence={"length": desc_len, "min_required": min_len},
                                confidence=1.0,
                                source="static",
                                fix=t("spec.fix.desc_short", lang),
                            )
                        )

    return findings
