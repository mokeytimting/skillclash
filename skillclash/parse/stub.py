from __future__ import annotations

import re
from pathlib import Path

STUB_PATH_PATTERN = re.compile(r"^[\w./\\-]+$")


def is_stub_candidate(path: Path) -> str | None:
    """Check if file matches criteria for a git symlink text stub.

    Returns the stripped target path string if it is a stub, else None.
    """
    try:
        stat = path.stat()
        if stat.st_size >= 512:
            return None
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return None

    if "\n" in text or "\r" in text:
        return None
    if "---" in text:
        return None
    if ("/" not in text) and ("\\" not in text):
        return None
    if not STUB_PATH_PATTERN.match(text):
        return None

    return text


def resolve_stub(
    path: Path,
    max_depth: int = 5,
    repo_root: Path | None = None,
) -> Path | None:
    """Resolve a symlink stub text file up to max_depth hops.

    Returns the final resolved Path to an existing file, or None if invalid/broken.
    """
    current = path
    seen = {path.resolve()}

    for _ in range(max_depth):
        target_str = is_stub_candidate(current)
        if not target_str:
            # Not a stub, current is the real file
            if current.is_file():
                return current
            return None

        # Resolve relative to current file's directory
        resolved = (current.parent / target_str).resolve()

        if resolved in seen:
            # Loop detected
            return None
        seen.add(resolved)

        if repo_root:
            try:
                resolved.relative_to(repo_root.resolve())
            except ValueError:
                # Escaped repo root
                return None

        if resolved.is_dir():
            skill_md = resolved / "SKILL.md"
            if skill_md.is_file():
                current = skill_md
            else:
                return None
        elif resolved.is_file():
            current = resolved
        else:
            return None

    if current.is_file() and not is_stub_candidate(current):
        return current
    return None
