import json
from pathlib import Path

from skillclash.analyzers.spec import check_spec
from skillclash.parse.frontmatter import parse_skill_file
from skillclash.parse.refs import extract_refs
from skillclash.parse.rules import extract_rules
from skillclash.parse.stub import resolve_stub
from skillclash.parse.tokenize import tokenize
from skillclash.report.json_out import generate_json_dict
from skillclash.sources.fallback import scan_fallback_repo
from skillclash.sources.marketplace import parse_repo

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_parse_frontmatter_normal() -> None:
    p = FIXTURES_DIR / "home" / ".claude" / "skills" / "normal-skill" / "SKILL.md"
    fm, body, offset, err = parse_skill_file(p)
    assert err is None
    assert fm["name"] == "normal-skill"
    assert "normal skill for unit testing" in fm["description"]
    assert offset == 6
    assert "Normal Skill Body" in body


def test_parse_frontmatter_missing() -> None:
    p = FIXTURES_DIR / "home" / ".claude" / "skills" / "no-frontmatter" / "SKILL.md"
    fm, body, offset, err = parse_skill_file(p)
    assert err == "missing"
    assert fm == {}
    assert offset == 1
    assert "No Frontmatter Skill" in body


def test_parse_frontmatter_bad_yaml() -> None:
    p = FIXTURES_DIR / "home" / ".claude" / "skills" / "bad-yaml" / "SKILL.md"
    fm, body, offset, err = parse_skill_file(p)
    assert err is not None
    assert err.startswith("invalid_yaml")
    # Rescued name
    assert fm.get("name") == "bad-yaml"


def test_parse_frontmatter_multiline() -> None:
    p = FIXTURES_DIR / "home" / ".claude" / "skills" / "multiline-desc" / "SKILL.md"
    fm, body, offset, err = parse_skill_file(p)
    assert err is None
    assert fm["name"] == "multiline-desc"
    assert "spans multiple lines and should be folded cleanly" in fm["description"]


def test_stub_resolution() -> None:
    stubs_dir = FIXTURES_DIR / "repo_stubs"
    # 1. Valid stub
    valid_stub = stubs_dir / "valid_stub" / "SKILL.md"
    resolved = resolve_stub(valid_stub, repo_root=stubs_dir)
    assert resolved is not None
    assert resolved.name == "SKILL.md"
    assert resolved.parent.name == "real"

    # 2. Broken stub
    broken_stub = stubs_dir / "broken_stub" / "SKILL.md"
    assert resolve_stub(broken_stub, repo_root=stubs_dir) is None

    # 3. Circular stub
    circular_stub = stubs_dir / "circular_stub" / "SKILL.md"
    assert resolve_stub(circular_stub, repo_root=stubs_dir) is None


def test_tokenize_en_and_cjk() -> None:
    tokens = tokenize("Use this skill to extract PDF text and fill forms 處理繁體中文資料")
    assert "pdf" in tokens
    assert "extract" in tokens
    assert "form" in tokens
    # Template words 'use', 'skill' should be removed
    assert "use" not in tokens
    assert "skill" not in tokens
    # CJK bigrams
    assert "處理" in tokens or "繁體" in tokens


def test_rules_extraction() -> None:
    body = """
    - Always verify that inputs are properly formatted.
    - Never deploy directly to production without review.
    - 建議優先使用 UTF-8 編碼。
    - 禁止未經備份刪除資料。
    """
    rules = extract_rules(body, line_offset=1)
    assert len(rules) >= 4
    pols = {r.polarity for r in rules}
    assert 1 in pols
    assert -1 in pols


def test_refs_extraction() -> None:
    body = "Run script at `C:\\tools\\x.py` or see [doc](references/missing.md)"
    refs = extract_refs(body, skill_dir=Path("."), plugin_root=None, line_offset=1, is_local=False)
    assert len(refs) == 2
    abs_ref = next(r for r in refs if r.absolute)
    assert "x.py" in abs_ref.raw
    rel_ref = next(r for r in refs if not r.absolute)
    assert "missing.md" in rel_ref.raw
    assert rel_ref.exists is False


def test_repo_mirrors_deduplication() -> None:
    repo_dir = FIXTURES_DIR / "repo_mirrors"
    unit = scan_fallback_repo(repo_dir, origin="mirrors")
    # Must only find 1 skill (original), .cursor/.kiro/docs/ja-JP must be pruned
    assert len(unit.skills) == 1
    assert unit.skills[0].dir.name == "original"


def test_repo_marketplace_parsing() -> None:
    repo_dir = FIXTURES_DIR / "repo_marketplace"
    units = parse_repo(repo_dir, origin="test-mp")
    assert len(units) == 3
    names = {u.label for u in units}
    assert names == {"local-doc", "self-plugin", "unsupported-plugin"}

    # Check unsupported plugin warning
    unsupported = next(u for u in units if u.label == "unsupported-plugin")
    assert any("SRC-UNSUPPORTED" in w for w in unsupported.warnings)


def test_spec_checks() -> None:
    repo_dir = FIXTURES_DIR / "repo_marketplace"
    units = parse_repo(repo_dir, origin="test-mp")
    findings = check_spec(units)
    assert any(f.rule == "SRC-UNSUPPORTED" for f in findings)


def test_json_schema_validation() -> None:
    repo_dir = FIXTURES_DIR / "repo_marketplace"
    units = parse_repo(repo_dir, origin="test-mp")
    findings = check_spec(units)

    data = generate_json_dict(units, findings, config_used={})
    schema_path = Path(__file__).parent.parent.parent / "skillclash" / "report" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Validate required top level keys
    for req in schema["required"]:
        assert req in data, f"Missing required top-level key {req}"

    # Validate units, skills, findings
    for u in data["units"]:
        for req in schema["properties"]["units"]["items"]["required"]:
            assert req in u, f"Unit missing {req}"

    for s in data["skills"]:
        for req in schema["properties"]["skills"]["items"]["required"]:
            assert req in s, f"Skill missing {req}"

    for f in data["findings"]:
        for req in schema["properties"]["findings"]["items"]["required"]:
            assert req in f, f"Finding missing {req}"
