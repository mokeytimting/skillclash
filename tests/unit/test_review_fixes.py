"""Regression tests for problems found when reviewing the first implementation."""

import json
import re
from pathlib import Path

import pytest

from skillclash import cli
from skillclash.analyzers import run_analyzers
from skillclash.analyzers.duplicates import compare_skill_versions
from skillclash.model import InstallUnit, Severity, UnitKind
from skillclash.parse.refs import extract_refs
from skillclash.parse.rules import extract_rules
from skillclash.sources.fallback import build_skill_from_file

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
CJK = re.compile(r"[\u4e00-\u9fff]")


def _skill_dir(tmp_path: Path, name: str, body: str, *, subdirs: tuple[str, ...] = ()) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True)
    for sub in subdirs:
        (d / sub).mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill {name} for regression checks of the analyzer.\n---\n{body}\n",
        encoding="utf-8",
    )
    return d


# --- REF-* false positives -------------------------------------------------

def test_refs_ignore_urls_commands_and_user_project_paths(tmp_path: Path) -> None:
    body = "\n".join([
        "See `https://raw.githubusercontent.com/org/repo/main/README.md` for details.",
        "Unzip and edit `word/document.xml` inside the docx.",
        "Create `scripts/deploy.sh` in your project.",
        "Personal skills live in `~/.claude/skills/`.",
        "Example: /home/user/project/app.py and C:\\path\\to\\file.txt",
    ])
    refs = extract_refs(body, skill_dir=tmp_path, plugin_root=None, line_offset=1, is_local=False)
    assert refs == []


def test_refs_check_bundled_files_and_strip_command_args(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "bundled", "", subdirs=("scripts",))
    (skill / "scripts" / "ok.py").write_text("", encoding="utf-8")
    body = "\n".join([
        "Run `python scripts/ok.py --input deck.pptx [prefix]`.",
        "Then `scripts/missing.py unpacked/`.",
        "Or ${CLAUDE_SKILL_DIR}/scripts/ok.py",
    ])
    refs = extract_refs(body, skill_dir=skill, plugin_root=None, line_offset=1, is_local=False)
    by_raw = {r.raw: r for r in refs}
    assert by_raw["scripts/ok.py"].exists is True
    assert by_raw["scripts/missing.py"].exists is False
    assert by_raw["${CLAUDE_SKILL_DIR}/scripts/ok.py"].exists is True
    assert not any(" " in r.raw for r in refs)


def test_refs_flag_machine_specific_absolute_paths(tmp_path: Path) -> None:
    body = "Run C:\\mcp_tools\\ds.py and /Users/kevin/tools/run.sh"
    refs = extract_refs(body, skill_dir=tmp_path, plugin_root=None, line_offset=1, is_local=False)
    assert {r.raw for r in refs if r.absolute} == {"C:\\mcp_tools\\ds.py", "/Users/kevin/tools/run.sh"}


# --- rule extraction --------------------------------------------------------

def test_rules_ignore_chinese_words_that_only_contain_markers() -> None:
    body = "- 這是特別重要的類別識別流程說明\n- 這個步驟不可能失敗所以照常處理資料"
    assert extract_rules(body, line_offset=1) == []
    neg = extract_rules("- 別自己重跑已通過的測試檔案", line_offset=1)
    assert neg and neg[0].polarity == -1


# --- packs: plugins from one marketplace are not install-time clashes -------

def _unit(uid: str, pack: str, skill_path: Path) -> InstallUnit:
    sk, _ = build_skill_from_file(skill_path, uid, namespaced=True, plugin_name=uid)
    return InstallUnit(id=uid, kind=UnitKind.PLUGIN, label=uid, origin="gh:o/r",
                       namespaced=True, skills=[sk], pack=pack)


def test_same_pack_pairs_skipped_unless_intra() -> None:
    p = FIXTURES_DIR / "conflict_drift" / "drift_v1" / "SKILL.md"
    units = [_unit("bundle", "gh:o/r", p), _unit("single", "gh:o/r", p)]
    findings, _ = run_analyzers(units, {})
    assert not [f for f in findings if f.rule in ("NAME-CLASH", "OVERLAP", "DUP-CONTENT")]

    findings, _ = run_analyzers(units, {}, intra=True)
    clash = [f for f in findings if f.rule == "NAME-CLASH"]
    assert clash and clash[0].severity == Severity.INFO


def test_version_compare_is_numeric() -> None:
    a, _ = build_skill_from_file(FIXTURES_DIR / "conflict_drift" / "drift_v1" / "SKILL.md", "a", False)
    b, _ = build_skill_from_file(FIXTURES_DIR / "conflict_drift" / "drift_v2" / "SKILL.md", "b", False)
    a.frontmatter["version"], b.frontmatter["version"] = "1.10.0", "1.9.0"
    assert compare_skill_versions(a, b) == "a"
    b.frontmatter.pop("version")
    assert compare_skill_versions(a, b) is None


# --- CLI behaviour ------------------------------------------------------------

@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = FIXTURES_DIR / "home"
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("SKILLCLASH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json_report(args: list[str], out: Path) -> tuple[int, dict]:
    code = cli.main([*args, "--format", "json", "-o", str(out), "--lang", "en", "--quiet"])
    return code, json.loads(out.read_text(encoding="utf-8"))


def test_preflight_only_reports_findings_touching_new_source(isolated_home: Path) -> None:
    new_src = isolated_home / "newpack"
    (new_src / "skills").mkdir(parents=True)
    src = FIXTURES_DIR / "home" / ".claude" / "skills" / "normal-skill" / "SKILL.md"
    (new_src / "skills" / "normal-skill").mkdir()
    (new_src / "skills" / "normal-skill" / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    _, data = _json_report(["preflight", str(new_src), "--min-severity", "info"], isolated_home / "r.json")
    new_ids = set(data["stats"]["new_unit_ids"])
    assert new_ids
    assert data["findings"], "expected the copied skill to clash with the installed one"
    for f in data["findings"]:
        assert any(s["unit_id"] in new_ids for s in f["skills"]), f["rule"]


def test_exit_code_ignores_suppressed_findings(isolated_home: Path) -> None:
    code, data = _json_report(["audit"], isolated_home / "a.json")
    assert code == 1 and any(f["severity"] == "error" for f in data["findings"])

    (isolated_home / ".skillclash.toml").write_text(
        '[[ignore]]\nrule = "*"\nreason = "test"\n', encoding="utf-8"
    )
    code, data = _json_report(["audit"], isolated_home / "b.json")
    assert code == 0
    assert data["findings"] == []


def test_english_reports_have_no_chinese_messages_and_no_home_paths(isolated_home: Path) -> None:
    _, data = _json_report(["audit", "--min-severity", "info"], isolated_home / "en.json")
    home = str(FIXTURES_DIR / "home")
    text = json.dumps(data, ensure_ascii=False)
    for form in (home, home.replace("\\", "/"), json.dumps(home)[1:-1]):
        assert form not in text
    for f in data["findings"]:
        if f["rule"] == "RULE-CONFLICT":
            continue  # quotes Chinese fixture text verbatim
        assert not CJK.search(f["title"] + f["message"] + (f["fix"] or "")), f
