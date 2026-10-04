from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from skillclash.model import InstallUnit, UnitKind
from skillclash.sources.fallback import (
    build_skill_from_file,
    is_excluded_dir,
    scan_fallback_repo,
)
from skillclash.sources.github import fetch_github_repo


def _join(base: Path, rel: str) -> Path:
    """Join a manifest-relative path ("./skills", "skills/", "./") onto base."""
    return (base / rel).resolve() if rel not in ("", ".", "./") else base.resolve()


def _skill_paths(base: Path, raw: object) -> list[Path]:
    items = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    return [_join(base, s) for s in items if isinstance(s, str)]


def _pack_of(origin: str) -> str:
    """All plugins published from one repo/marketplace share a pack: gh:owner/repo@sha -> gh:owner/repo."""
    return origin.split("@", 1)[0] if origin.startswith("gh:") else origin


def _repo_slug(origin: str) -> str:
    return _pack_of(origin)[3:].lower() if origin.startswith("gh:") else ""


def find_skills_in_path(
    base_dir: Path,
    unit_id: str,
    plugin_name: str,
    plugin_root: Path,
    repo_root: Path,
    extra_excludes: list[str] | None = None,
    is_local: bool = True,
) -> tuple[list[Any], list[str]]:
    """Scan base_dir for skills according to 7.4 rule 1c."""
    skills: list[Any] = []
    warnings: list[str] = []
    seen_paths: set[Path] = set()

    if not base_dir.exists():
        return skills, warnings

    # If base_dir itself has SKILL.md
    direct_skill = base_dir / "SKILL.md"
    if direct_skill.is_file():
        sk, warn = build_skill_from_file(
            direct_skill,
            unit_id,
            namespaced=True,
            plugin_name=plugin_name,
            plugin_root=plugin_root,
            repo_root=repo_root,
            is_local=is_local,
        )
        if warn:
            warnings.append(warn)
        if sk:
            skills.append(sk)
        return skills, warnings

    # Otherwise recursively search downwards; once SKILL.md found in a directory, do not search deeper
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d, extra_excludes)]
        for f in files:
            if f.lower() == "skill.md":
                fpath = Path(root) / f
                sk, warn = build_skill_from_file(
                    fpath,
                    unit_id,
                    namespaced=True,
                    plugin_name=plugin_name,
                    plugin_root=plugin_root,
                    repo_root=repo_root,
                    is_local=is_local,
                )
                if warn:
                    warnings.append(warn)
                if sk and sk.path not in seen_paths:
                    seen_paths.add(sk.path)
                    skills.append(sk)
                # Found SKILL.md in this folder -> prune child dirs
                dirs.clear()
                break

    return skills, warnings


def parse_repo(
    repo_root: Path,
    origin: str,
    *,
    plugin_filter: str | None = None,
    offline: bool = False,
    refresh: bool = False,
    no_follow_external: bool = False,
    extra_excludes: list[str] | None = None,
    is_local: bool = True,
) -> list[InstallUnit]:
    """Parse a repo root according to Section 7.4."""
    mp_json_path = repo_root / ".claude-plugin" / "marketplace.json"
    plugin_json_path = repo_root / ".claude-plugin" / "plugin.json"

    if mp_json_path.is_file():
        return _parse_marketplace_json(
            mp_json_path,
            repo_root,
            origin,
            plugin_filter=plugin_filter,
            offline=offline,
            refresh=refresh,
            no_follow_external=no_follow_external,
            extra_excludes=extra_excludes,
            is_local=is_local,
        )
    elif plugin_json_path.is_file():
        return _parse_single_plugin_json(
            plugin_json_path,
            repo_root,
            origin,
            plugin_filter=plugin_filter,
            extra_excludes=extra_excludes,
            is_local=is_local,
        )
    else:
        unit = scan_fallback_repo(repo_root, origin, extra_excludes, is_local=is_local)
        return [unit]


def _parse_marketplace_json(
    mp_path: Path,
    repo_root: Path,
    origin: str,
    plugin_filter: str | None,
    offline: bool,
    refresh: bool,
    no_follow_external: bool,
    extra_excludes: list[str] | None,
    is_local: bool,
) -> list[InstallUnit]:
    try:
        data = json.loads(mp_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        unit = InstallUnit(
            id=f"dir:{origin}",
            kind=UnitKind.DIR,
            label=repo_root.name,
            origin=origin,
            namespaced=False,
            warnings=[f"Failed to read marketplace.json: {e}"],
            pack=_pack_of(origin),
        )
        return [unit]

    mp_name = data.get("name") or repo_root.name
    pack = _pack_of(origin)
    self_slug = _repo_slug(origin)
    plugins_list = data.get("plugins") or []
    units: list[InstallUnit] = []

    for p_entry in plugins_list:
        if not isinstance(p_entry, dict):
            continue
        p_name = p_entry.get("name") or "unnamed"
        if plugin_filter and p_name != plugin_filter:
            continue

        p_source = p_entry.get("source")
        plugin_root: Path | None = None
        warnings: list[str] = []

        # 1a. Parse source
        if isinstance(p_source, str):
            # Relative path
            plugin_root = _join(repo_root, p_source)
        elif isinstance(p_source, dict):
            src_type = p_source.get("source")
            if src_type == "github":
                gh_repo = p_source.get("repo", "")
                # Points back at the repo we are already reading
                if gh_repo and (
                    gh_repo.lower() == self_slug
                    or repo_root.name.lower() == gh_repo.replace("/", "__").lower()
                ):
                    plugin_root = repo_root
                else:
                    if no_follow_external:
                        warnings.append(f"External repo {gh_repo} skipped (--no-follow-external)")
                    else:
                        parts = gh_repo.split("/")
                        if len(parts) == 2:
                            cloned_dir, _, err = fetch_github_repo(
                                parts[0],
                                parts[1],
                                p_source.get("ref"),
                                offline=offline,
                                refresh=refresh,
                            )
                            if err:
                                warnings.append(f"Failed to clone external repo {gh_repo}: {err}")
                            else:
                                plugin_root = cloned_dir
            elif src_type == "url":
                url = p_source.get("url", "")
                if "github.com" in url:
                    # Parse owner/repo from url
                    m = url.replace(".git", "").rstrip("/").split("/")
                    if len(m) >= 2:
                        owner, rname = m[-2], m[-1]
                        if no_follow_external:
                            warnings.append(f"External url {url} skipped (--no-follow-external)")
                        else:
                            cloned_dir, _, err = fetch_github_repo(
                                owner,
                                rname,
                                p_source.get("ref"),
                                offline=offline,
                                refresh=refresh,
                            )
                            if err:
                                warnings.append(f"Failed to clone external url {url}: {err}")
                            else:
                                plugin_root = cloned_dir
                else:
                    warnings.append(f"SRC-UNSUPPORTED: source url {url}")
            else:
                warnings.append(f"SRC-UNSUPPORTED: source type {src_type}")
        else:
            warnings.append(f"SRC-UNSUPPORTED: invalid source {p_source}")

        if not plugin_root or not plugin_root.exists():
            unit = InstallUnit(
                id=f"plugin:{mp_name}/{p_name}",
                kind=UnitKind.PLUGIN,
                label=p_name,
                origin=origin,
                namespaced=True,
                warnings=warnings,
                pack=pack,
            )
            units.append(unit)
            continue

        # 1b. Determine skill paths
        skill_paths: list[Path] = []
        if "skills" in p_entry:
            skill_paths = _skill_paths(plugin_root, p_entry["skills"])
        else:
            # Check plugin.json in plugin_root
            sub_pjson = plugin_root / ".claude-plugin" / "plugin.json"
            if sub_pjson.is_file():
                try:
                    pdata = json.loads(sub_pjson.read_text(encoding="utf-8", errors="replace"))
                    if "skills" in pdata:
                        skill_paths = _skill_paths(plugin_root, pdata["skills"])
                except (OSError, ValueError):
                    warnings.append(f"Failed to read {sub_pjson.name} for plugin {p_name}")

        if not skill_paths:
            # Default to <plugin_root>/skills/
            default_skills_dir = plugin_root / "skills"
            if default_skills_dir.exists():
                skill_paths = [default_skills_dir]
            else:
                skill_paths = [plugin_root]

        unit_id = f"plugin:{mp_name}/{p_name}"
        unit = InstallUnit(
            id=unit_id,
            kind=UnitKind.PLUGIN,
            label=p_name,
            origin=origin,
            namespaced=True,
            warnings=warnings,
            pack=pack,
        )

        seen_unit_paths: set[Path] = set()
        name_seen: dict[str, Path] = {}

        for sp in skill_paths:
            s_list, s_warns = find_skills_in_path(
                sp,
                unit_id,
                plugin_name=p_name,
                plugin_root=plugin_root,
                repo_root=repo_root,
                extra_excludes=extra_excludes,
                is_local=is_local,
            )
            unit.warnings.extend(s_warns)
            for sk in s_list:
                if sk.path in seen_unit_paths:
                    continue
                seen_unit_paths.add(sk.path)

                if sk.name in name_seen:
                    unit.warnings.append(
                        f"Multiple skills with same name '{sk.name}' in same plugin: "
                        f"{sk.path} and {name_seen[sk.name]}"
                    )
                else:
                    name_seen[sk.name] = sk.path

                unit.skills.append(sk)

        units.append(unit)

    return units


def _parse_single_plugin_json(
    pjson_path: Path,
    repo_root: Path,
    origin: str,
    plugin_filter: str | None,
    extra_excludes: list[str] | None,
    is_local: bool,
) -> list[InstallUnit]:
    try:
        pdata = json.loads(pjson_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        unit = InstallUnit(
            id=f"dir:{origin}",
            kind=UnitKind.DIR,
            label=repo_root.name,
            origin=origin,
            namespaced=False,
            warnings=[f"Failed to read plugin.json: {e}"],
            pack=_pack_of(origin),
        )
        return [unit]

    p_name = pdata.get("name") or repo_root.name
    if plugin_filter and p_name != plugin_filter:
        return []

    skill_paths: list[Path] = []
    if "skills" in pdata:
        skill_paths = _skill_paths(repo_root, pdata["skills"])
    else:
        default_skills = repo_root / "skills"
        if default_skills.exists():
            skill_paths = [default_skills]
        else:
            skill_paths = [repo_root]

    unit_id = f"plugin:{repo_root.name}/{p_name}"
    unit = InstallUnit(
        id=unit_id,
        kind=UnitKind.PLUGIN,
        label=p_name,
        origin=origin,
        namespaced=True,
        pack=_pack_of(origin),
    )

    seen_unit_paths: set[Path] = set()
    name_seen: dict[str, Path] = {}

    for sp in skill_paths:
        s_list, s_warns = find_skills_in_path(
            sp,
            unit_id,
            plugin_name=p_name,
            plugin_root=repo_root,
            repo_root=repo_root,
            extra_excludes=extra_excludes,
            is_local=is_local,
        )
        unit.warnings.extend(s_warns)
        for sk in s_list:
            if sk.path in seen_unit_paths:
                continue
            seen_unit_paths.add(sk.path)

            if sk.name in name_seen:
                unit.warnings.append(
                    f"Multiple skills with same name '{sk.name}' in same plugin: "
                    f"{sk.path} and {name_seen[sk.name]}"
                )
            else:
                name_seen[sk.name] = sk.path

            unit.skills.append(sk)

    return [unit]
