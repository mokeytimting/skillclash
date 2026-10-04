from pathlib import Path
from typing import Any

from skillclash.llm.backend import BaseBackend
from skillclash.llm.route import (
    build_routing_listing,
    run_route_simulation,
    select_target_skills,
)
from skillclash.model import InstallUnit, ScanResult, UnitKind
from skillclash.report.html import generate_html_report
from skillclash.sources.fallback import build_skill_from_file

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class FakePromptGenBackend(BaseBackend):
    def __init__(self, prompts: list[str]):
        super().__init__("fake_gen", "fake", "key", use_cache=False)
        self.prompts = prompts

    def complete_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        return {"prompts": self.prompts}


class FakeRouterBackend(BaseBackend):
    def __init__(self, target_answers: list[str]):
        super().__init__("fake_route", "fake", "key", use_cache=False)
        self.answers = list(target_answers)

    def complete_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        ans = self.answers.pop(0) if self.answers else "none"
        return {"skill": ans}


def test_select_targets_and_build_listing() -> None:
    p1 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_a" / "SKILL.md"
    p2 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_b" / "SKILL.md"

    sk1, _ = build_skill_from_file(p1, "u1", namespaced=True, plugin_name="doc")
    sk2, _ = build_skill_from_file(p2, "u2", namespaced=True, plugin_name="pdf")

    targets = select_target_skills([sk1, sk2], [[sk1.id, sk2.id]], max_skills=10)
    assert len(targets) == 2

    listing_text, names = build_routing_listing([sk1, sk2], targets)
    assert "doc:pdf-processor" in names
    assert "pdf:pdf-helper" in names
    assert "doc:pdf-processor:" in listing_text


def test_route_simulation_steal_and_dead() -> None:
    p1 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_a" / "SKILL.md"
    p2 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_b" / "SKILL.md"

    sk1, _ = build_skill_from_file(p1, "u1", namespaced=True, plugin_name="doc")
    sk2, _ = build_skill_from_file(p2, "u2", namespaced=True, plugin_name="pdf")

    u1 = InstallUnit(id="u1", kind=UnitKind.PLUGIN, label="u1", origin="o1", namespaced=True, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.PLUGIN, label="u2", origin="o2", namespaced=True, skills=[sk2])

    gen_backend = FakePromptGenBackend(["query 1", "query 2"])

    # For sk1 (2 queries * 1 repeat):
    # Query 1 routed to sk2 (stolen!)
    # Query 2 routed to sk2 (stolen!) -> stolen ratio = 1.0 >= 0.25 -> ROUTE-STEAL!
    # For sk2 (2 queries * 1 repeat):
    # Query 1 routed to sk2
    # Query 2 routed to sk2
    router_backend = FakeRouterBackend([
        "pdf:pdf-helper",  # sk1 query 1 -> sk2
        "pdf:pdf-helper",  # sk1 query 2 -> sk2
        "pdf:pdf-helper",  # sk2 query 1 -> sk2
        "pdf:pdf-helper",  # sk2 query 2 -> sk2
    ])

    findings, stats = run_route_simulation(
        [u1, u2],
        gen_backend,
        router_backend,
        max_route_skills=10,
        prompts_per_skill=2,
        repeats=1,
    )

    # Check matrix
    # sk1: [0.0, 1.0]
    # sk2: [0.0, 1.0]
    matrix = stats["matrix"]
    assert matrix[0][1] == 1.0
    assert matrix[0][0] == 0.0
    assert matrix[1][1] == 1.0

    # ROUTE-STEAL should trigger for sk1 -> sk2
    steals = [f for f in findings if f.rule == "ROUTE-STEAL"]
    assert len(steals) >= 1
    assert steals[0].evidence["stolen_ratio"] == 1.0

    # ROUTE-DEAD should trigger for sk1 because hit_rate == 0.0 < 0.25
    deads = [f for f in findings if f.rule == "ROUTE-DEAD"]
    assert len(deads) >= 1
    assert deads[0].skills[0].name == "pdf-processor"


def test_html_report_renders_route_heatmap() -> None:
    p1 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_a" / "SKILL.md"
    sk1, _ = build_skill_from_file(p1, "u1", namespaced=True, plugin_name="doc")
    u1 = InstallUnit(id="u1", kind=UnitKind.PLUGIN, label="u1", origin="o1", namespaced=True, skills=[sk1])

    scan_res = ScanResult(
        units=[u1],
        findings=[],
        stats={
            "route_matrix": {
                "skills": ["doc:pdf-processor"],
                "matrix": [[1.0]],
            }
        },
        config_used={},
    )
    html_out = generate_html_report(scan_res)
    assert 'routeSection' in html_out
    assert 'doc:pdf-processor' in html_out
    assert '100%' in html_out or 'matrix' in html_out
