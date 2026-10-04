"""Sanity checks against real skill packs. Run with: pytest -m network

Ranges (not exact values) because the upstream repos keep changing.
Set SKILLCLASH_CACHE_DIR to reuse existing clones.
"""

import os
from pathlib import Path

import pytest

from skillclash.analyzers import run_analyzers
from skillclash.parse.stub import is_stub_candidate, resolve_stub
from skillclash.sources import resolve_sources

pytestmark = pytest.mark.network


def _resolve(spec: str):
    units, stats = resolve_sources([spec])
    if stats["fetch_errors"]:
        pytest.skip(f"could not fetch {spec}: {stats['fetch_errors']}")
    return units


def test_ecc_skill_count_matches_its_manifest() -> None:
    """Check 1: ECC says it ships 293 skills; mirrors (.cursor, .kiro, docs/ja-JP...) must not be counted."""
    units = _resolve("gh:affaan-m/ECC")
    total = sum(len(u.skills) for u in units)
    assert 234 <= total <= 352, total


def test_claude_skills_plugins_and_stubs() -> None:
    """Check 2: >=70 plugins, 300-450 skills, and git symlink stubs resolve on this platform."""
    units = _resolve("gh:alirezarezvani/claude-skills")
    plugins = [u for u in units if u.namespaced]
    assert len(plugins) >= 70, len(plugins)
    total = sum(len(u.skills) for u in units)
    assert 300 <= total <= 450, total

    repo = Path(units[0].skills[0].path).parents[0]
    while repo.parent != repo and not (repo / ".git").exists():
        repo = repo.parent
    stubs = [p for p in repo.rglob("SKILL.md") if is_stub_candidate(p)]
    if os.name == "nt":
        assert stubs, "expected git to store symlinks as text stubs on Windows"
    if stubs:
        resolved = [resolve_stub(p, repo_root=repo) for p in stubs]
        assert sum(r is not None for r in resolved) / len(stubs) > 0.9


@pytest.mark.parametrize("spec", ["gh:affaan-m/ECC", "gh:obra/superpowers"])
def test_single_repo_has_no_mirror_duplicates(spec: str) -> None:
    """Check 3: even comparing a repo against itself (--intra), mirror copies must not show up."""
    units = _resolve(spec)
    findings, _ = run_analyzers(units, {}, intra=True)
    dups = [f for f in findings if f.rule == "DUP-CONTENT"]
    total = sum(len(u.skills) for u in units)
    assert len(dups) <= max(2, total * 0.02), [f.title for f in dups[:10]]
