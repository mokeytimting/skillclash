import urllib.request
from pathlib import Path
from typing import Any

import pytest

from skillclash.analyzers import run_analyzers
from skillclash.llm.backend import (
    BaseBackend,
    OpenAICompatBackend,
    extract_json_from_response,
)
from skillclash.llm.judge import run_judge, verify_quote_presence
from skillclash.model import Finding, InstallUnit, ScanResult, Severity, SkillRef, UnitKind
from skillclash.report.html import generate_html_report
from skillclash.report.json_out import generate_json_str
from skillclash.report.text import format_text_report
from skillclash.sources.fallback import build_skill_from_file

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class FakeBackend(BaseBackend):
    def __init__(self, canned_responses: list[dict[str, Any]] | None = None):
        super().__init__("fake", "fake-model", "fake-key", use_cache=False)
        self.responses = list(canned_responses or [])
        self.call_history: list[tuple[str, str]] = []

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        cache_key_extra: str = "",
    ) -> dict[str, Any]:
        self.call_history.append((system, user))
        cache_path = self._get_cache_path(system, user, temperature, cache_key_extra)
        cached = self._load_cache(cache_path)
        if cached is not None:
            return cached

        self.stats["calls"] += 1
        if self.responses:
            resp = self.responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            self._save_cache(cache_path, resp)
            return resp
        default_resp = {"verdict": "compatible", "confidence": 0.9}
        self._save_cache(cache_path, default_resp)
        return default_resp


def test_extract_json_robustness() -> None:
    # Direct valid json
    assert extract_json_from_response('{"a": 1}') == {"a": 1}
    # Surrounding markdown / text
    raw = 'Here is the result:\n```json\n{"verdict": "conflict", "confidence": 0.8}\n```\nHope this helps!'
    extracted = extract_json_from_response(raw)
    assert extracted["verdict"] == "conflict"
    assert extracted["confidence"] == 0.8


def test_quote_verification() -> None:
    full_text = "Always make sure to verify unit tests before committing code to main branch."
    assert verify_quote_presence("verify unit tests before committing", full_text) is True
    assert verify_quote_presence("never write any unit tests", full_text) is False


def test_judge_conflict_upgrade() -> None:
    p_en_a = FIXTURES_DIR / "conflict_drift" / "rule_en_a" / "SKILL.md"
    p_en_b = FIXTURES_DIR / "conflict_drift" / "rule_en_b" / "SKILL.md"

    sk1, _ = build_skill_from_file(p_en_a, "u1", False)
    sk2, _ = build_skill_from_file(p_en_b, "u2", False)

    u1 = InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="o2", namespaced=False, skills=[sk2])

    f = Finding(
        rule="RULE-CONFLICT",
        severity=Severity.INFO,
        title="Rule Conflict",
        message="Conflicting rules",
        skills=[
            SkillRef(skill_id=sk1.id, name=sk1.name, unit_id=sk1.unit_id, path=str(sk1.path)),
            SkillRef(skill_id=sk2.id, name=sk2.name, unit_id=sk2.unit_id, path=str(sk2.path)),
        ],
        evidence={},
        confidence=0.5,
        source="static",
    )

    fake_resp = {
        "verdict": "conflict",
        "confidence": 0.85,
        "quote_a": "Always run the tests",
        "quote_b": "Never run tests yourself",
        "explanation": "Direct contradiction regarding test execution.",
        "suggested_fix": "Standardize test responsibility.",
    }
    backend = FakeBackend([fake_resp])

    updated, dismissed, trunc = run_judge([f], [u1, u2], backend)
    assert len(updated) == 1
    assert updated[0].severity == Severity.WARN
    assert updated[0].source == "llm"
    assert updated[0].confidence == 0.85
    assert len(dismissed) == 0


def test_judge_compatible_dismissal() -> None:
    p_en_a = FIXTURES_DIR / "conflict_drift" / "rule_en_a" / "SKILL.md"
    p_en_b = FIXTURES_DIR / "conflict_drift" / "rule_en_b" / "SKILL.md"

    sk1, _ = build_skill_from_file(p_en_a, "u1", False)
    sk2, _ = build_skill_from_file(p_en_b, "u2", False)

    u1 = InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="o2", namespaced=False, skills=[sk2])

    f = Finding(
        rule="OVERLAP",
        severity=Severity.INFO,
        title="Overlap",
        message="Potential overlap",
        skills=[
            SkillRef(skill_id=sk1.id, name=sk1.name, unit_id=sk1.unit_id, path=str(sk1.path)),
            SkillRef(skill_id=sk2.id, name=sk2.name, unit_id=sk2.unit_id, path=str(sk2.path)),
        ],
        evidence={},
        confidence=0.4,
        source="static",
    )

    fake_resp = {
        "verdict": "compatible",
        "confidence": 0.9,
        "explanation": "These two skills operate in entirely separate scenarios.",
    }
    backend = FakeBackend([fake_resp])

    updated, dismissed, trunc = run_judge([f], [u1, u2], backend)
    assert len(updated) == 0
    assert len(dismissed) == 1
    assert dismissed[0]["fingerprint"] == f.fingerprint


def test_judge_quote_unverified_halves_confidence() -> None:
    p_en_a = FIXTURES_DIR / "conflict_drift" / "rule_en_a" / "SKILL.md"
    p_en_b = FIXTURES_DIR / "conflict_drift" / "rule_en_b" / "SKILL.md"

    sk1, _ = build_skill_from_file(p_en_a, "u1", False)
    sk2, _ = build_skill_from_file(p_en_b, "u2", False)

    u1 = InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False, skills=[sk1])
    u2 = InstallUnit(id="u2", kind=UnitKind.DIR, label="u2", origin="o2", namespaced=False, skills=[sk2])

    f = Finding(
        rule="RULE-CONFLICT",
        severity=Severity.INFO,
        title="Rule Conflict",
        message="Conflicting rules",
        skills=[
            SkillRef(skill_id=sk1.id, name=sk1.name, unit_id=sk1.unit_id, path=str(sk1.path)),
            SkillRef(skill_id=sk2.id, name=sk2.name, unit_id=sk2.unit_id, path=str(sk2.path)),
        ],
        evidence={},
        confidence=0.5,
        source="static",
    )

    # Hallucinated quote
    fake_resp = {
        "verdict": "conflict",
        "confidence": 0.8,
        "quote_a": "This sentence does not exist anywhere in skill body!",
        "quote_b": "Neither does this completely made up string!",
    }
    backend = FakeBackend([fake_resp])

    updated, dismissed, trunc = run_judge([f], [u1, u2], backend)
    assert len(updated) == 1
    assert updated[0].evidence.get("quote_unverified") is True
    # Confidence should be halved: 0.8 / 2 = 0.4
    assert abs(updated[0].confidence - 0.4) < 1e-5


def test_api_key_privacy_defense(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement: Never leak or print API keys in outputs, reports, logs."""
    fake_secret = "sk-test-SHOULD-NOT-APPEAR-ANYWHERE-SECRET-999"
    monkeypatch.setenv("DEEPSEEK_API_KEY", fake_secret)
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_secret)

    backend = OpenAICompatBackend()
    assert backend._api_key == fake_secret

    # Run scan result rendering
    u = InstallUnit(id="u1", kind=UnitKind.DIR, label="u1", origin="o1", namespaced=False)
    f = Finding(
        rule="SPEC-NO-DESC",
        severity=Severity.ERROR,
        title="No desc",
        message="Missing description",
        skills=[],
        evidence={},
        confidence=1.0,
        source="static",
    )
    scan_res = ScanResult(units=[u], findings=[f], stats={"llm": backend.stats}, config_used={})

    text_rep = format_text_report(scan_res)
    json_rep = generate_json_str(scan_res)
    html_rep = generate_html_report(scan_res)

    assert fake_secret not in text_rep
    assert fake_secret not in json_rep
    assert fake_secret not in html_rep


def test_default_mode_never_connects_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requirement: Core static analysis (L0-L3) never touches the network or calls urlopen."""
    def forbidden_urlopen(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Network call was attempted in default static mode!")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)

    p1 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_a" / "SKILL.md"
    p2 = FIXTURES_DIR / "conflict_drift" / "pdf_tools_b" / "SKILL.md"
    sk1, _ = build_skill_from_file(p1, "u1", False)
    sk2, _ = build_skill_from_file(p2, "u2", False)
    u = InstallUnit(id="u", kind=UnitKind.DIR, label="u", origin="local", namespaced=False, skills=[sk1, sk2])

    findings, stats = run_analyzers([u], {})
    assert len(findings) > 0  # Static analysis runs cleanly without network!
