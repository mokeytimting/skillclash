from __future__ import annotations

from pathlib import Path
from typing import Any

from skillclash.model import InstallUnit, UnitKind
from skillclash.paths import display_path
from skillclash.sources.github import fetch_github_repo, parse_github_spec
from skillclash.sources.local import (
    resolve_local_sources,
    scan_installed_plugins,
    scan_project_skills,
    scan_user_skills,
)
from skillclash.sources.marketplace import parse_repo


def resolve_sources(
    specs: list[str],
    *,
    offline: bool = False,
    refresh: bool = False,
    no_follow_external: bool = False,
    project_path: str | Path | None = None,
    extra_excludes: list[str] | None = None,
) -> tuple[list[InstallUnit], dict[str, Any]]:
    """Resolve a list of source specs into InstallUnits and stats."""
    units: list[InstallUnit] = []
    seen_specs: set[str] = set()
    stats: dict[str, Any] = {
        "disabled_plugins_count": 0,
        "fetch_errors": [],
    }

    proj_root = Path(project_path).resolve() if project_path else None

    for spec in specs:
        s_clean = spec.strip()
        if not s_clean or s_clean in seen_specs:
            continue
        seen_specs.add(s_clean)

        if s_clean == "local":
            loc_units, dis = resolve_local_sources(proj_root)
            units.extend(loc_units)
            stats["disabled_plugins_count"] += dis

        elif s_clean == "user":
            u_unit = scan_user_skills()
            if u_unit:
                units.append(u_unit)

        elif s_clean == "project" or s_clean.startswith("project:"):
            p_dir = proj_root
            if ":" in s_clean:
                p_dir = Path(s_clean.split(":", 1)[1]).resolve()
            p_unit = scan_project_skills(p_dir)
            if p_unit:
                units.append(p_unit)

        elif s_clean == "plugins":
            pl_units, dis = scan_installed_plugins()
            units.extend(pl_units)
            stats["disabled_plugins_count"] += dis

        elif s_clean.startswith("gh:") or "github.com/" in s_clean:
            owner, repo, ref, plugin_filter = parse_github_spec(s_clean)
            cloned_dir, sha, err = fetch_github_repo(
                owner,
                repo,
                ref,
                offline=offline,
                refresh=refresh,
            )
            origin_label = f"gh:{owner}/{repo}" + (f"@{sha[:7]}" if sha else "")
            if err:
                stats["fetch_errors"].append((s_clean, err))
                err_unit = InstallUnit(
                    id=f"dir:{origin_label}",
                    kind=UnitKind.DIR,
                    label=f"{owner}/{repo}",
                    origin=origin_label,
                    namespaced=False,
                    warnings=[f"SRC-FETCH: {err}"],
                )
                units.append(err_unit)
            elif cloned_dir:
                parsed_units = parse_repo(
                    cloned_dir,
                    origin=origin_label,
                    plugin_filter=plugin_filter,
                    offline=offline,
                    refresh=refresh,
                    no_follow_external=no_follow_external,
                    extra_excludes=extra_excludes,
                    is_local=False,
                )
                units.extend(parsed_units)

        else:
            # Local directory path
            dir_path = Path(s_clean).resolve()
            if dir_path.is_dir():
                origin_label = display_path(dir_path)
                parsed_units = parse_repo(
                    dir_path,
                    origin=origin_label,
                    offline=offline,
                    refresh=refresh,
                    no_follow_external=no_follow_external,
                    extra_excludes=extra_excludes,
                    is_local=True,
                )
                units.extend(parsed_units)
            else:
                stats["fetch_errors"].append((s_clean, f"Path not found: {s_clean}"))
                err_unit = InstallUnit(
                    id=f"dir:{s_clean}",
                    kind=UnitKind.DIR,
                    label=s_clean,
                    origin=s_clean,
                    namespaced=False,
                    warnings=[f"SRC-FETCH: Path does not exist {s_clean}"],
                )
                units.append(err_unit)

    return units, stats
