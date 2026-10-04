from __future__ import annotations

from typing import Any

from skillclash.analyzers.duplicates import check_duplicates
from skillclash.analyzers.greedy import check_greedy
from skillclash.analyzers.overlap import check_overlap
from skillclash.analyzers.references import check_references
from skillclash.analyzers.rule_conflict import check_rule_conflicts
from skillclash.analyzers.spec import check_spec
from skillclash.config import DEFAULT_CONFIG
from skillclash.model import Finding, InstallUnit


def run_analyzers(
    units: list[InstallUnit],
    config: dict[str, Any],
    *,
    lang: str = "zh-TW",
    intra: bool = False,
    include_static: bool = True,
    rule_candidates: bool = False,
) -> tuple[list[Finding], dict[str, Any]]:
    """Run all active analyzers on the given install units.

    ``rule_candidates`` enables the static RULE-CONFLICT detector. Its precision on real packs
    is very low (see docs/calibration.md), so it only runs to feed ``--judge`` or on request.

    Returns:
        (findings, extra_stats)
    """
    findings: list[Finding] = []
    stats: dict[str, Any] = {
        "overlap_pairs_total": 0,
        "overlap_clusters": [],
    }

    if include_static:
        # L0: Spec & source checks
        findings.extend(check_spec(units, lang=lang))

        # L1: Duplicates & Name clashes
        dup_findings, name_clash_pairs = check_duplicates(units, intra=intra, lang=lang)
        findings.extend(dup_findings)

        # L2: Trigger Overlap
        thresholds = {**DEFAULT_CONFIG["thresholds"], **config.get("thresholds", {})}
        warn_th = float(thresholds["overlap_warn"])
        info_th = float(thresholds["overlap_info"])

        overlap_findings, overlap_stats = check_overlap(
            units,
            name_clash_pairs=name_clash_pairs,
            warn_threshold=warn_th,
            info_threshold=info_th,
            intra=intra,
            lang=lang,
        )
        findings.extend(overlap_findings)
        stats.update(overlap_stats)

        # L3: Static Rule Conflicts (candidates only)
        if rule_candidates:
            findings.extend(check_rule_conflicts(units, intra=intra, lang=lang))

        # Greedy descriptions
        greedy_warn = float(thresholds["greedy_warn"])
        greedy_info = float(thresholds["greedy_info"])
        findings.extend(
            check_greedy(
                units,
                warn_threshold=greedy_warn,
                info_threshold=greedy_info,
                lang=lang,
            )
        )

        # File references (broken / absolute paths)
        findings.extend(check_references(units, lang=lang))

    return findings, stats
