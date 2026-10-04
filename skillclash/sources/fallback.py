from __future__ import annotations

import os
import re
from pathlib import Path

from skillclash.model import InstallUnit, Skill, UnitKind
from skillclash.parse.frontmatter import parse_skill_file
from skillclash.parse.refs import extract_refs
from skillclash.parse.rules import extract_rules
from skillclash.parse.stub import resolve_stub
from skillclash.paths import display_path

EXCLUDE_DIRS = frozenset([
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".claude", ".cursor", ".kiro", ".gemini", ".codex", ".codex-plugin",
    ".agents", ".opencode", ".windsurf", ".github", "docs", "i18n", "locales",
    "translations", "test", "tests", "fixtures", "__tests__",
])

LOCALE_DIR_PATTERN = re.compile(r"^[a-z]{2}([-_][A-Za-z]{2,4})?$")


def is_excluded_dir(name: str, extra_excludes: list[str] | None = None) -> bool:
    """Check whether a directory name should be skipped during skill search."""
    if name in EXCLUDE_DIRS:
        return True
    if extra_excludes and name in extra_excludes:
        return True
    if LOCALE_DIR_PATTERN.match(name):
        return True
    return False


def build_skill_from_file(
    file_path: Path,
    unit_id: str,
    namespaced: bool,
    plugin_name: str | None = None,
    plugin_root: Path | None = None,
    repo_root: Path | None = None,
    is_local: bool = True,
) -> tuple[Skill | None, str | None]:
    """Resolve stub, parse frontmatter, extract rules and refs, and return Skill instance."""
    resolved_path = resolve_stub(file_path, repo_root=repo_root)
    if not resolved_path:
        return None, f"Broken or invalid stub at {display_path(file_path)}"

    fm, body, body_line_offset, fm_err = parse_skill_file(resolved_path)

    # Name determination
    dir_name = resolved_path.parent.name
    raw_name = fm.get("name")
    if raw_name:
        name = str(raw_name).strip()
    else:
        name = dir_name

    qualified_name = f"{plugin_name}:{name}" if (namespaced and plugin_name) else name
    skill_id = f"{unit_id}#{name}"

    desc = str(fm.get("description", "")).strip()

    # disable-model-invocation
    dmi = fm.get("disable-model-invocation", False)
    if isinstance(dmi, str):
        dmi = dmi.lower() in ("true", "1", "yes")
    model_invocable = not bool(dmi)

    skill_dir = resolved_path.parent
    rules = extract_rules(body, body_line_offset)
    refs = extract_refs(body, skill_dir, plugin_root, body_line_offset, is_local=is_local)

    skill = Skill(
        id=skill_id,
        name=name,
        qualified_name=qualified_name,
        description=desc,
        body=body,
        path=resolved_path,
        dir=skill_dir,
        unit_id=unit_id,
        frontmatter=fm,
        frontmatter_error=fm_err,
        model_invocable=model_invocable,
        body_line_offset=body_line_offset,
        rules=rules,
        refs=refs,
    )
    return skill, None


def scan_fallback_repo(
    root: Path,
    origin: str,
    extra_excludes: list[str] | None = None,
    is_local: bool = True,
) -> InstallUnit:
    """Recursively scan root directory for all SKILL.md, excluding mirrors and noise dirs."""
    unit_id = f"dir:{origin}"
    label = root.name
    unit = InstallUnit(
        id=unit_id,
        kind=UnitKind.DIR,
        label=label,
        origin=origin,
        namespaced=False,
        inferred=True,
        priority=0,
        pack=origin.split("@", 1)[0] if origin.startswith("gh:") else origin,
    )

    seen_paths: set[Path] = set()
    name_seen: dict[str, Path] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        # Filter dirnames in-place to prune walk
        dirnames[:] = [d for d in dirnames if not is_excluded_dir(d, extra_excludes)]

        for fname in filenames:
            if fname.lower() == "skill.md":
                fpath = Path(dirpath) / fname
                skill, warn = build_skill_from_file(
                    fpath,
                    unit_id,
                    namespaced=False,
                    plugin_root=root,
                    repo_root=root,
                    is_local=is_local,
                )
                if warn:
                    unit.warnings.append(warn)
                if skill:
                    # Deduplicate by resolved real path
                    if skill.path in seen_paths:
                        continue
                    seen_paths.add(skill.path)

                    if skill.name in name_seen:
                        unit.warnings.append(
                            f"Multiple skills with same name '{skill.name}' in same unit: "
                            f"{display_path(skill.path)} and {display_path(name_seen[skill.name])}"
                        )
                    else:
                        name_seen[skill.name] = skill.path

                    unit.skills.append(skill)

    return unit
