from __future__ import annotations

import os
import sys

import skillclash
from skillclash.i18n import t
from skillclash.model import ScanResult, Severity, Skill
from skillclash.report.json_out import estimate_listing_tokens

SEVERITY_ORDER = {
    Severity.ERROR: 0,
    Severity.WARN: 1,
    Severity.INFO: 2,
}

SEVERITY_ICON = {
    Severity.ERROR: "🔴",
    Severity.WARN: "🟠",
    Severity.INFO: "🟡",
}


def should_use_color() -> bool:
    """Check whether ANSI colors should be enabled."""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


def format_text_report(
    scan_result: ScanResult,
    min_severity: Severity = Severity.WARN,
    lang: str = "zh-TW",
) -> str:
    """Generate ANSI/plain text report for terminal output."""
    color = should_use_color()

    YELLOW = "\033[93m" if color else ""
    BLUE = "\033[94m" if color else ""
    GRAY = "\033[90m" if color else ""
    BOLD = "\033[1m" if color else ""
    RESET = "\033[0m" if color else ""

    units = scan_result.units
    findings = [f for f in scan_result.findings if not f.suppressed_by]
    shown_suppressed = [f for f in scan_result.findings if f.suppressed_by]
    suppressed_count = scan_result.stats.get("suppressed_count", 0)

    all_skills: list[Skill] = [sk for u in units for sk in u.skills]
    non_invocable_count = sum(1 for sk in all_skills if not sk.model_invocable)

    lines: list[str] = []
    header = t(
        "summary.scanned",
        lang,
        tool="skillclash",
        version=skillclash.__version__,
        units=len(units),
        skills=len(all_skills),
        non_invocable=non_invocable_count,
    )
    lines.append(f"{BOLD}{header}{RESET}")
    lines.append("")

    lines.append(
        t(
            "summary.counts",
            lang,
            errors=sum(1 for f in findings if f.severity == Severity.ERROR),
            warns=sum(1 for f in findings if f.severity == Severity.WARN),
            infos=sum(1 for f in findings if f.severity == Severity.INFO),
        )
    )

    threshold_order = SEVERITY_ORDER[min_severity]
    visible = [f for f in findings if SEVERITY_ORDER[f.severity] <= threshold_order]
    visible += shown_suppressed
    hidden = len(findings) - (len(visible) - len(shown_suppressed))
    if hidden:
        lines.append(t("summary.hidden", lang, n=hidden))
    if suppressed_count and not shown_suppressed:
        lines.append(t("summary.suppressed", lang, n=suppressed_count))
    lines.append("")

    visible.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.rule, f.title))

    for f in visible:
        icon = SEVERITY_ICON.get(f.severity, "⚪")
        suffix = f"  {GRAY}[suppressed: {f.suppressed_by}]{RESET}" if f.suppressed_by else ""
        lines.append(f"{icon} {BOLD}{f.rule}{RESET}  {f.title}{suffix}")

        for i, sref in enumerate(f.skills):
            prefix = "   ├" if i < len(f.skills) - 1 else "   └"
            loc = f":{sref.line}" if sref.line else ""
            lines.append(f"{prefix} {BLUE}{sref.unit_id}{RESET}  {sref.path}{loc}")

        if f.message:
            for msg_line in f.message.splitlines():
                lines.append(f"   {msg_line}")

        if f.rule not in ("RULE-CONFLICT",):  # RULE-CONFLICT already quotes both sides
            for sref in f.skills:
                if sref.quote:
                    clean_quote = sref.quote.replace("\n", " ").strip()
                    if len(clean_quote) > 100:
                        clean_quote = clean_quote[:97] + "..."
                    lines.append(f"   {GRAY}\"{clean_quote}\"{RESET}")

        if f.fix:
            lines.append(f"   {YELLOW}{t('label.fix', lang)}: {f.fix}{RESET}")

        lines.append("")

    total_tokens = sum(estimate_listing_tokens(sk) for sk in all_skills if sk.model_invocable)
    new_ids = set(scan_result.stats.get("new_unit_ids", []))
    if new_ids:
        new_src_tokens = sum(
            estimate_listing_tokens(sk)
            for u in units
            if u.id in new_ids
            for sk in u.skills
            if sk.model_invocable
        )
        lines.append(t("summary.tokens_new", lang, total=total_tokens, new_src=new_src_tokens))
    else:
        lines.append(t("summary.tokens", lang, total=total_tokens))

    return "\n".join(lines)
