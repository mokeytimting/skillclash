"""Cross-pack checks against real skill packs. Run with: pytest -m network"""

import time

import pytest

from skillclash.analyzers import run_analyzers
from skillclash.sources import resolve_sources

pytestmark = pytest.mark.network

CORPUS = [
    "gh:anthropics/skills", "gh:obra/superpowers", "gh:mattpocock/skills",
    "gh:addyosmani/agent-skills", "gh:alirezarezvani/claude-skills",
    "gh:affaan-m/ECC", "gh:garrytan/gstack", "gh:pbakaus/impeccable",
    "gh:DietrichGebert/ponytail", "gh:JuliusBrussee/caveman", "gh:thedotmack/claude-mem",
]


def _resolve(specs: list[str]):
    units, stats = resolve_sources(specs)
    if stats["fetch_errors"]:
        pytest.skip(f"could not fetch: {stats['fetch_errors']}")
    return units


def _clashes(findings, name: str):
    return [f for f in findings if f.rule == "NAME-CLASH" and any(s.name.lower() == name for s in f.skills)]


def test_tdd_name_clash_between_superpowers_and_agent_skills() -> None:
    """Check 4."""
    units = _resolve(["gh:obra/superpowers", "gh:addyosmani/agent-skills"])
    findings, _ = run_analyzers(units, {})
    assert _clashes(findings, "test-driven-development")


def test_caveman_name_clash_with_variant() -> None:
    """Check 5."""
    units = _resolve(["gh:JuliusBrussee/caveman", "gh:alirezarezvani/claude-skills"])
    findings, _ = run_analyzers(units, {})
    clashes = _clashes(findings, "caveman")
    assert clashes
    assert all(f.evidence["variant"] in ("identical", "drifted", "different") for f in clashes)


def test_full_corpus_static_analysis_is_fast() -> None:
    """Check 6: L0-L3 over all 11 packs in under 60 s (clone time excluded)."""
    units = _resolve(CORPUS)
    assert len({u.pack_id for u in units}) == len(CORPUS)
    t0 = time.perf_counter()
    run_analyzers(units, {})
    assert time.perf_counter() - t0 < 60
