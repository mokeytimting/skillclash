from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import skillclash
from skillclash.model import Finding, InstallUnit, ScanResult, Severity, Skill
from skillclash.parse.tokenize import CJK_CHAR_PATTERN
from skillclash.paths import display_origin, display_path


def estimate_listing_tokens(skill: Skill) -> int:
    """Estimate tokens for listing '- qualified_name: description'.

    Formula: ASCII / 4 + CJK * 1, ceiling.
    """
    line = f"- {skill.qualified_name}: {skill.description}"
    cjk_count = 0
    ascii_count = 0
    for ch in line:
        if CJK_CHAR_PATTERN.match(ch):
            cjk_count += 1
        else:
            ascii_count += 1
    return math.ceil(ascii_count / 4.0) + cjk_count


def generate_json_dict(
    units: list[InstallUnit],
    findings: list[Finding],
    config_used: dict[str, Any],
    args: dict[str, Any] | None = None,
    extra_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the dictionary structure adhering to report/schema.json."""
    all_skills: list[Skill] = []
    unit_records: list[dict[str, Any]] = []
    tokens_by_unit: dict[str, int] = {}
    total_tokens = 0

    for u in units:
        unit_token_sum = 0
        for sk in u.skills:
            all_skills.append(sk)
            est = estimate_listing_tokens(sk)
            unit_token_sum += est

        tokens_by_unit[u.id] = unit_token_sum
        total_tokens += unit_token_sum

        unit_records.append(
            {
                "id": u.id,
                "kind": u.kind.value,
                "label": u.label,
                "origin": display_origin(u.origin),
                "pack": display_origin(u.pack_id),
                "namespaced": u.namespaced,
                "inferred": u.inferred,
                "skill_count": len(u.skills),
                "warnings": list(u.warnings),
            }
        )

    skills_records: list[dict[str, Any]] = []
    for sk in all_skills:
        skills_records.append(
            {
                "id": sk.id,
                "name": sk.name,
                "qualified_name": sk.qualified_name,
                "unit_id": sk.unit_id,
                "path": display_path(sk.path),
                "model_invocable": sk.model_invocable,
                "description": sk.description,
                "listing_tokens_est": estimate_listing_tokens(sk),
            }
        )

    counts_by_severity = {
        Severity.ERROR.value: sum(1 for f in findings if f.severity == Severity.ERROR),
        Severity.WARN.value: sum(1 for f in findings if f.severity == Severity.WARN),
        Severity.INFO.value: sum(1 for f in findings if f.severity == Severity.INFO),
    }

    counts_by_rule: dict[str, int] = {}
    for f in findings:
        counts_by_rule[f.rule] = counts_by_rule.get(f.rule, 0) + 1

    findings_records: list[dict[str, Any]] = []
    for f in findings:
        findings_records.append(
            {
                "fingerprint": f.fingerprint,
                "rule": f.rule,
                "severity": f.severity.value,
                "title": f.title,
                "message": f.message,
                "skills": [
                    {
                        "skill_id": s.skill_id,
                        "name": s.name,
                        "qualified_name": s.qualified_name,
                        "unit_id": s.unit_id,
                        "path": s.path,
                        "line": s.line,
                        "quote": s.quote,
                    }
                    for s in f.skills
                ],
                "evidence": f.evidence,
                "confidence": round(f.confidence, 4),
                "source": f.source,
                "fix": f.fix,
                "suppressed_by": f.suppressed_by,
            }
        )

    stats: dict[str, Any] = {
        "counts_by_severity": counts_by_severity,
        "counts_by_rule": counts_by_rule,
        "overlap_pairs_total": 0,
        "overlap_clusters": [],
        "listing_tokens_est_total": total_tokens,
        "listing_tokens_est_by_unit": tokens_by_unit,
        "dismissed_by_llm": [],
        "route_matrix": {"skills": [], "matrix": []},
        "llm": {},
        "timing_ms": {},
    }
    if extra_stats:
        stats.update(extra_stats)

    out: dict[str, Any] = {
        "tool": "skillclash",
        "version": skillclash.__version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "args": args or {},
        "units": unit_records,
        "skills": skills_records,
        "findings": findings_records,
        "stats": stats,
    }
    return out


def generate_json_str(scan_result: ScanResult, args: dict[str, Any] | None = None) -> str:
    """Serialize scan result to pretty JSON string."""
    data = generate_json_dict(
        scan_result.units,
        scan_result.findings,
        scan_result.config_used,
        args=args,
        extra_stats=scan_result.stats,
    )
    return json.dumps(data, ensure_ascii=False, indent=2)
