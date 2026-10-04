from __future__ import annotations

from pathlib import Path

from skillclash.cache import get_cache_root
from skillclash.model import InstallUnit, Skill, SkillRef


def display_path(path: str | Path | None) -> str:
    """Render a path without leaking the local machine layout.

    Cached GitHub clones become ``gh:owner/repo/<rel>``; paths under the home
    directory become ``~/<rel>``; anything else is returned in POSIX form.
    """
    if path is None:
        return ""
    p = Path(path)
    try:
        rel = p.resolve().relative_to((get_cache_root() / "r").resolve())
        head, *rest = rel.parts
        owner, _, repo = head.partition("__")
        return f"gh:{owner}/{repo}" + ("/" + "/".join(rest) if rest else "")
    except (ValueError, OSError):
        pass
    try:
        rel = p.resolve().relative_to(Path.home().resolve())
        return "~/" + rel.as_posix()
    except (ValueError, OSError):
        return p.as_posix()


def display_origin(origin: str) -> str:
    """Origins are either ``gh:`` specs or local paths; only the latter need masking."""
    if origin.startswith("gh:"):
        return origin
    return display_path(origin)


def make_ref(skill: Skill, *, line: int | None = 1, quote: str | None = None) -> SkillRef:
    if quote is None:
        quote = skill.description[:200] if skill.description else skill.name
    return SkillRef(
        skill_id=skill.id,
        name=skill.name,
        unit_id=skill.unit_id,
        path=display_path(skill.path),
        line=line,
        quote=quote,
        qualified_name=skill.qualified_name,
    )


def same_pack(unit_a: InstallUnit, unit_b: InstallUnit) -> bool:
    return unit_a.pack_id == unit_b.pack_id


def units_by_skill(units: list[InstallUnit]) -> dict[str, InstallUnit]:
    """Map skill id -> the unit that actually contains the skill."""
    return {sk.id: u for u in units for sk in u.skills}
