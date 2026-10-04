from pathlib import Path

from skillclash.analyzers import run_analyzers
from skillclash.analyzers.duplicates import check_duplicates
from skillclash.analyzers.greedy import check_greedy
from skillclash.analyzers.overlap import check_overlap
from skillclash.analyzers.references import check_references
from skillclash.analyzers.rule_conflict import check_rule_conflicts
from skillclash.model import InstallUnit, ScanResult, Severity, UnitKind
from skillclash.report.html import generate_html_report
from skillclash.sources.fallback import build_skill_from_file
from skillclash.suppress import apply_suppressions

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_name_clash_drifted() -> None:
    path1 = FIXTURES_DIR / "conflict_drift" / "drift_v1" / "SKILL.md"
    path2 = FIXTURES_DIR / "conflict_drift" / "drift_v2" / "SKILL.md"

    sk1, _ = build_skill_from_file(path1, "u1", namespaced=False)
    sk2, _ = build_skill_from_file(path2, "u2", namespaced=False)

    u1 = InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="o2", namespaced=False, skills=[sk2])

    findings, clash_pairs = check_duplicates([u1, u2])
    assert len(clash_pairs) == 1
    assert any(f.rule == "NAME-CLASH" for f in findings)
    f = next(f for f in findings if f.rule == "NAME-CLASH")
    assert f.severity == Severity.ERROR
    assert f.evidence["variant"] == "drifted"
    assert f.evidence["newer"] == "u2"


def test_overlap_pdf_vs_unrelated() -> None:
    p_pdf1 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_a" / "SKILL.md"
    p_pdf2 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_b" / "SKILL.md"
    p_cook = FIXTURES_DIR / "conflict_drift" / "cooking_chef" / "SKILL.md"

    sk1, _ = build_skill_from_file(p_pdf1, "u1", namespaced=True, plugin_name="doc")
    sk2, _ = build_skill_from_file(p_pdf2, "u2", namespaced=True, plugin_name="pdf")
    sk3, _ = build_skill_from_file(p_cook, "u3", namespaced=True, plugin_name="cook")

    u1 = InstallUnit(id="u1", kind=UnitKind.PLUGIN, label="u1", origin="o1", namespaced=True, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.PLUGIN, label="u2", origin="o2", namespaced=True, skills=[sk2])
    u3 = InstallUnit(id="u3", kind=UnitKind.PLUGIN, label="u3", origin="o3", namespaced=True, skills=[sk3])

    findings, stats = check_overlap([u1, u2, u3], name_clash_pairs=set())
    # PDF pair must trigger OVERLAP
    pdf_overlap = [f for f in findings if "pdf" in f.skills[0].name and "pdf" in f.skills[1].name]
    assert len(pdf_overlap) == 1
    assert pdf_overlap[0].evidence["cosine"] >= 0.45
    assert pdf_overlap[0].severity == Severity.WARN

    # Cooking skill must NOT trigger OVERLAP with PDF tools
    cook_overlap = [f for f in findings if "cooking" in f.skills[0].name or "cooking" in f.skills[1].name]
    assert len(cook_overlap) == 0


def test_rule_conflict_en_and_zh() -> None:
    p_en_a = FIXTURES_DIR / "conflict_drift" / "rule_en_a" / "SKILL.md"
    p_en_b = FIXTURES_DIR / "conflict_drift" / "rule_en_b" / "SKILL.md"
    p_zh_a = FIXTURES_DIR / "conflict_drift" / "rule_zh_a" / "SKILL.md"
    p_zh_b = FIXTURES_DIR / "conflict_drift" / "rule_zh_b" / "SKILL.md"

    sk_en_a, _ = build_skill_from_file(p_en_a, "u1", False)
    sk_en_b, _ = build_skill_from_file(p_en_b, "u2", False)
    sk_zh_a, _ = build_skill_from_file(p_zh_a, "u3", False)
    sk_zh_b, _ = build_skill_from_file(p_zh_b, "u4", False)

    u_en = [
        InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False, skills=[sk_en_a]),
        InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="o2", namespaced=False, skills=[sk_en_b]),
    ]
    findings_en = check_rule_conflicts(u_en)
    assert any(f.rule == "RULE-CONFLICT" for f in findings_en)
    f_en = next(f for f in findings_en if f.rule == "RULE-CONFLICT")
    assert f_en.severity == Severity.INFO
    assert "test" in f_en.evidence["shared_topics"]

    u_zh = [
        InstallUnit(id="u3", kind=UnitKind.DIR, label="u3", origin="o3", namespaced=False, skills=[sk_zh_a]),
        InstallUnit(id="u4", kind=UnitKind.DIR, label="u4", origin="o4", namespaced=False, skills=[sk_zh_b]),
    ]
    findings_zh = check_rule_conflicts(u_zh)
    assert any(f.rule == "RULE-CONFLICT" for f in findings_zh)


def test_greedy_description() -> None:
    p_greedy = FIXTURES_DIR / "conflict_drift" / "greedy_skill" / "SKILL.md"
    p_normal = FIXTURES_DIR / "conflict_drift" / "normal_greedless" / "SKILL.md"

    sk_g, _ = build_skill_from_file(p_greedy, "u1", False)
    sk_n, _ = build_skill_from_file(p_normal, "u2", False)

    u = [
        InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False, skills=[sk_g]),
        InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="o2", namespaced=False, skills=[sk_n]),
    ]
    findings = check_greedy(u)
    assert len(findings) == 1
    assert findings[0].skills[0].name == "greedy-skill"
    assert findings[0].severity == Severity.WARN
    assert findings[0].evidence["score"] >= 5.0


def test_references_broken_and_abspath() -> None:
    p_abs = FIXTURES_DIR / "home" / ".claude" / "skills" / "abspath-ref" / "SKILL.md"
    p_broken = FIXTURES_DIR / "home" / ".claude" / "skills" / "missing-ref" / "SKILL.md"

    sk_abs, _ = build_skill_from_file(p_abs, "u1", False, is_local=False)
    sk_brk, _ = build_skill_from_file(p_broken, "u2", False, is_local=False)

    u = [
        InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="gh:o/r", namespaced=False, skills=[sk_abs]),
        InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="gh:o/r", namespaced=False, skills=[sk_brk]),
    ]
    findings = check_references(u)
    assert any(f.rule == "REF-ABSPATH" for f in findings)
    assert any(f.rule == "REF-BROKEN" for f in findings)
    f_brk = next(f for f in findings if f.rule == "REF-BROKEN")
    assert f_brk.severity == Severity.WARN


def test_suppression_mechanism() -> None:
    p_pdf1 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_a" / "SKILL.md"
    p_pdf2 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_b" / "SKILL.md"

    sk1, _ = build_skill_from_file(p_pdf1, "u1", namespaced=True, plugin_name="doc")
    sk2, _ = build_skill_from_file(p_pdf2, "u2", namespaced=True, plugin_name="pdf")

    u1 = InstallUnit(id="u1", kind=UnitKind.PLUGIN, label="u1", origin="o1", namespaced=True, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.PLUGIN, label="u2", origin="o2", namespaced=True, skills=[sk2])

    config = {
        "severity": {
            "GREEDY": "off",
        },
        "ignore": [
            {
                "rule": "OVERLAP",
                "pair": ["pdf-processor", "pdf-helper"],
                "reason": "Verified non-competing tools",
            },
            {
                "rule": "SPEC-NO-DESC",
                "reason": "Unused whitelist rule",
            },
        ],
    }

    findings, stats = run_analyzers([u1, u2], config)
    active, suppressed = apply_suppressions(findings, [u1, u2], config)

    # Overlap between pdf tools must be suppressed
    supp_rules = [f.rule for f in suppressed]
    assert "OVERLAP" in supp_rules

    # Unused whitelist rule must emit SUPPRESS-UNUSED in active
    active_rules = [f.rule for f in active]
    assert "SUPPRESS-UNUSED" in active_rules


def test_html_report_xss_protection() -> None:
    sk = build_skill_from_file(
        FIXTURES_DIR / "conflict_drift" / "normal_greedless" / "SKILL.md",
        "u_xss",
        False,
    )[0]
    assert sk is not None
    sk.name = "<script>alert(1)</script>"
    sk.description = "<img src=x onerror=alert(2)>"

    u = InstallUnit(id="u_xss", kind=UnitKind.DIR, label="XSS Test", origin="test", namespaced=False, skills=[sk])
    findings, stats = run_analyzers([u], {})

    scan_res = ScanResult(units=[u], findings=findings, stats=stats, config_used={})
    html_out = generate_html_report(scan_res)

    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out or "\\u003cscript" in html_out
