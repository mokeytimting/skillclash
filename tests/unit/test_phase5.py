import json
from pathlib import Path

from skillclash.analyzers import run_analyzers
from skillclash.ecosystem import build_ecosystem_site
from skillclash.model import Severity
from skillclash.sources.marketplace import parse_repo

ROOT_DIR = Path(__file__).parent.parent.parent
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures"


def test_plugin_structure_and_self_scan() -> None:
    plugin_dir = ROOT_DIR / "plugin"
    assert (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
    assert (plugin_dir / "skills" / "skillclash" / "SKILL.md").is_file()
    assert (ROOT_DIR / ".claude-plugin" / "marketplace.json").is_file()

    # Self-scan: must have 0 findings with Severity >= WARN
    units = parse_repo(plugin_dir, origin=str(plugin_dir), is_local=True)
    assert sum(len(u.skills) for u in units) == 1
    findings, _ = run_analyzers(units, {})
    severe = [f for f in findings if f.severity in (Severity.ERROR, Severity.WARN)]
    assert severe == [], severe


def test_hooks_json_uses_matcher_groups() -> None:
    """Claude Code expects event -> [ {matcher, hooks: [handler]} ], not a flat handler list."""
    data = json.loads((ROOT_DIR / "plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    groups = data["hooks"]["SessionStart"]
    assert isinstance(groups, list) and groups
    for group in groups:
        assert "hooks" in group
        for handler in group["hooks"]:
            assert handler["type"] == "command"
            assert handler["command"].startswith("skillclash ")


def test_ecosystem_build_offline(tmp_path: Path) -> None:
    packs_file = tmp_path / "packs.toml"
    a = (FIXTURES_DIR / "conflict_drift" / "drift_v1").as_posix()
    b = (FIXTURES_DIR / "conflict_drift" / "drift_v2").as_posix()
    packs_file.write_text(
        f'[[packs]]\nname = "pack-a"\norigin = "{a}"\n\n[[packs]]\nname = "pack-b"\norigin = "{b}"\n',
        encoding="utf-8",
    )
    out_dir = tmp_path / "site"
    assert build_ecosystem_site(packs_file, out_dir, offline=True) == 0

    index = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "ecosystem map" in index
    assert "pack-a" in index and "pack-b" in index
    repack = (out_dir / "repack.html").read_text(encoding="utf-8")
    assert "drifted" in repack
