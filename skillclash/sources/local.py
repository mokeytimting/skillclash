from __future__ import annotations

import json
import os
from pathlib import Path

from skillclash.model import InstallUnit, Skill, UnitKind
from skillclash.parse.rules import extract_rules
from skillclash.paths import display_path
from skillclash.sources.fallback import build_skill_from_file
from skillclash.sources.marketplace import parse_repo


def get_claude_home() -> Path:
    """Return ~/.claude directory path respecting HOME / USERPROFILE environment."""
    home_dir = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
    return Path(home_dir) / ".claude"


def find_git_root(start_dir: Path | None = None) -> Path | None:
    """Find git root starting from given directory or cwd."""
    curr = (start_dir or Path.cwd()).resolve()
    for parent in [curr, *curr.parents]:
        if (parent / ".git").exists():
            return parent
    return curr  # Fallback to current dir if no git root


def scan_user_skills() -> InstallUnit | None:
    """Scan ~/.claude/skills/*/SKILL.md."""
    claude_home = get_claude_home()
    skills_dir = claude_home / "skills"
    if not skills_dir.is_dir():
        return None

    unit = InstallUnit(
        id="user",
        kind=UnitKind.USER,
        label="User Skills (~/.claude/skills)",
        origin=display_path(skills_dir),
        namespaced=False,
        priority=50,  # F1: personal > project
    )

    for item in sorted(skills_dir.iterdir()):
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.is_file():
                sk, warn = build_skill_from_file(
                    skill_md,
                    unit_id="user",
                    namespaced=False,
                    is_local=True,
                )
                if warn:
                    unit.warnings.append(warn)
                if sk:
                    unit.skills.append(sk)

    return unit if unit.skills or unit.warnings else None


def scan_project_skills(project_root: Path | None = None) -> InstallUnit | None:
    """Scan <project_root>/.claude/skills/*/SKILL.md."""
    root = project_root or find_git_root()
    if not root:
        return None

    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return None

    unit = InstallUnit(
        id=f"project:{root.name}",
        kind=UnitKind.PROJECT,
        label=f"Project Skills ({root.name})",
        origin=display_path(skills_dir),
        namespaced=False,
        priority=10,  # F1: project lower than user
    )

    for item in sorted(skills_dir.iterdir()):
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.is_file():
                sk, warn = build_skill_from_file(
                    skill_md,
                    unit_id=unit.id,
                    namespaced=False,
                    is_local=True,
                )
                if warn:
                    unit.warnings.append(warn)
                if sk:
                    unit.skills.append(sk)

    return unit if unit.skills or unit.warnings else None


def scan_installed_plugins() -> tuple[list[InstallUnit], int]:
    """Scan ~/.claude/plugins/installed_plugins.json and cross-check enabledPlugins.

    Returns:
        (units, disabled_count)
    """
    claude_home = get_claude_home()
    installed_file = claude_home / "plugins" / "installed_plugins.json"
    settings_file = claude_home / "settings.json"

    if not installed_file.is_file():
        return [], 0

    try:
        installed_data = json.loads(installed_file.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return [], 0

    enabled_plugins_set: set[str] | None = None
    if settings_file.is_file():
        try:
            settings_data = json.loads(settings_file.read_text(encoding="utf-8", errors="replace"))
            # Only read enabledPlugins per 0.3 strict rules
            ep = settings_data.get("enabledPlugins")
            if isinstance(ep, list):
                enabled_plugins_set = set(ep)
            elif isinstance(ep, dict):
                enabled_plugins_set = {k for k, v in ep.items() if v}
        except Exception:
            pass

    units: list[InstallUnit] = []
    disabled_count = 0

    # installed_plugins.json structure can be dict or list of plugin records
    plugin_items = (
        installed_data.items()
        if isinstance(installed_data, dict)
        else [(p.get("name", f"p_{i}"), p) for i, p in enumerate(installed_data)]
    )

    for p_key, p_info in plugin_items:
        if not isinstance(p_info, dict):
            continue
        p_name = p_info.get("name") or p_key

        # Check enabled state
        if enabled_plugins_set is not None:
            if p_name not in enabled_plugins_set and p_key not in enabled_plugins_set:
                disabled_count += 1
                continue

        p_install_path = p_info.get("installPath") or p_info.get("path")
        if p_install_path and Path(p_install_path).is_dir():
            p_root = Path(p_install_path)
            sub_units = parse_repo(p_root, origin=display_path(p_root), is_local=True)
            units.extend(sub_units)

    return units, disabled_count


def scan_memory_files(project_root: Path | None = None) -> list[InstallUnit]:
    """Scan CLAUDE.md files as UnitKind.MEMORY (participates only in RULE-CONFLICT)."""
    claude_home = get_claude_home()
    root = project_root or find_git_root()

    memory_units: list[InstallUnit] = []
    candidates = [
        (claude_home / "CLAUDE.md", "CLAUDE.md (user)", "user_memory"),
    ]
    if root:
        candidates.extend([
            (root / "CLAUDE.md", "CLAUDE.md (project)", "project_memory"),
            (root / ".claude" / "CLAUDE.md", "CLAUDE.md (project-claude)", "project_claude_memory"),
        ])

    for fpath, label, uid in candidates:
        if fpath.is_file():
            try:
                body = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rules = extract_rules(body, line_offset=1)
            sk = Skill(
                id=f"memory:{uid}#{label}",
                name=label,
                qualified_name=label,
                description=f"Persistent instructions from {label}",
                body=body,
                path=fpath,
                dir=fpath.parent,
                unit_id=f"memory:{uid}",
                frontmatter={},
                frontmatter_error=None,
                model_invocable=False,  # Does not participate in OVERLAP/ROUTE
                body_line_offset=1,
                rules=rules,
            )
            unit = InstallUnit(
                id=f"memory:{uid}",
                kind=UnitKind.MEMORY,
                label=label,
                origin=display_path(fpath),
                namespaced=False,
                priority=0,
                skills=[sk],
            )
            memory_units.append(unit)

    return memory_units


def resolve_local_sources(
    project_root: Path | None = None,
    include_user: bool = True,
    include_project: bool = True,
    include_plugins: bool = True,
    include_memory: bool = True,
) -> tuple[list[InstallUnit], int]:
    """Resolve all local sources into InstallUnits."""
    units: list[InstallUnit] = []
    disabled_count = 0

    if include_user:
        u_unit = scan_user_skills()
        if u_unit:
            units.append(u_unit)

    if include_project:
        p_unit = scan_project_skills(project_root)
        if p_unit:
            units.append(p_unit)

    if include_plugins:
        pl_units, dis = scan_installed_plugins()
        units.extend(pl_units)
        disabled_count += dis

    if include_memory:
        mem_units = scan_memory_files(project_root)
        units.extend(mem_units)

    return units, disabled_count
