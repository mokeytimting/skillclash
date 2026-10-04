import skillclash
from skillclash.model import Finding, Severity, SkillRef


def test_version() -> None:
    assert skillclash.__version__ == "0.1.0"


def test_finding_fingerprint() -> None:
    finding = Finding(
        rule="NAME-CLASH",
        severity=Severity.ERROR,
        title="Clash",
        message="Message",
        skills=[
            SkillRef(skill_id="b", name="b", unit_id="u2", path="p2"),
            SkillRef(skill_id="a", name="a", unit_id="u1", path="p1"),
        ],
        evidence={},
        confidence=1.0,
        source="static",
    )
    # Check fingerprint calculation
    fp1 = finding.fingerprint
    assert len(fp1) == 12

    # Swap skills order, fingerprint must remain identical
    finding2 = Finding(
        rule="NAME-CLASH",
        severity=Severity.ERROR,
        title="Clash",
        message="Message",
        skills=[
            SkillRef(skill_id="a", name="a", unit_id="u1", path="p1"),
            SkillRef(skill_id="b", name="b", unit_id="u2", path="p2"),
        ],
        evidence={},
        confidence=1.0,
        source="static",
    )
    assert finding2.fingerprint == fp1
