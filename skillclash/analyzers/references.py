from __future__ import annotations

import re

from skillclash.i18n import t
from skillclash.model import Finding, InstallUnit, Severity, UnitKind
from skillclash.paths import display_path, make_ref

USER_HOME_PATTERN = re.compile(r"^(?:[A-Za-z]:)?[\\/](?:Users|home)[\\/]", re.IGNORECASE)


def check_references(
    units: list[InstallUnit],
    lang: str = "zh-TW",
) -> list[Finding]:
    """Report missing bundled files (REF-BROKEN) and machine-specific paths (REF-ABSPATH)."""
    findings: list[Finding] = []

    for u in units:
        if u.kind == UnitKind.MEMORY:
            continue

        is_remote = u.origin.startswith("gh:")

        for sk in u.skills:
            for ref in sk.refs:
                if ref.absolute:
                    local_and_present = not is_remote and ref.exists is True
                    # Paths inside someone's home directory are almost always accidental;
                    # other drive paths are usually examples (C:\app, D:\project\dist).
                    user_specific = bool(USER_HOME_PATTERN.search(ref.raw))
                    findings.append(
                        Finding(
                            rule="REF-ABSPATH",
                            severity=Severity.WARN if user_specific else Severity.INFO,
                            title=f"{t('rule.REF-ABSPATH.title', lang)}: {ref.raw}",
                            message=t(
                                "ref_abs.local" if local_and_present else "ref_abs.remote",
                                lang,
                                raw=ref.raw,
                            ),
                            skills=[make_ref(sk, line=ref.line, quote=ref.raw)],
                            evidence={"raw": ref.raw, "line": ref.line, "exists": ref.exists},
                            confidence=1.0,
                            source="static",
                            fix=t("ref_abs.fix", lang),
                        )
                    )
                elif ref.exists is False:
                    findings.append(
                        Finding(
                            rule="REF-BROKEN",
                            severity=Severity.WARN,
                            title=f"{t('rule.REF-BROKEN.title', lang)}: {ref.raw}",
                            message=t("ref_broken.msg", lang, raw=ref.raw),
                            skills=[make_ref(sk, line=ref.line, quote=ref.raw)],
                            evidence={
                                "raw": ref.raw,
                                "resolved": display_path(ref.resolved) if ref.resolved else None,
                                "line": ref.line,
                            },
                            confidence=1.0,
                            source="static",
                            fix=t("ref_broken.fix", lang, raw=ref.raw),
                        )
                    )

    return findings
