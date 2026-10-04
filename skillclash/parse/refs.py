from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from skillclash.model import FileRef

# Absolute paths that are tied to one machine. `~/` is deliberately NOT here:
# `~/.claude/skills/...` resolves on every machine.
WIN_ABS_PATTERN = re.compile(r"(?<![\w/\\.\-])([A-Za-z]:[\\/][^\s`'\"<>|*?()\[\]]+)")
FRAGMENT_PATTERN = re.compile(r"(#.*|:\d+(?::\d+)?)$")  # path.md#anchor, file.py:42, file.ts:8:3
POSIX_ABS_PATTERN = re.compile(r"(?<![\w.~/:])(/(?:Users|home)/([^\s`'\"<>|*?/()\[\]]+)/[^\s`'\"<>|*?()\[\]]*)")
PLACEHOLDER_USERS = frozenset([
    "user", "username", "user-name", "you", "your", "yourname", "your-name", "your_name", "me",
    "name", "example", "foo", "bar", "alice", "bob", "jdoe", "john", "johndoe", "dev",
    "$user", "${user}", "%username%", "<user>", "<username>", "runner",
])
PLACEHOLDER_HINTS = ("path/to", "path\\to", "your", "<", "example", "xxx", "...")

MD_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\s*\)")
TOKEN_SPLIT_PATTERN = re.compile(r"[\s`'\"()<>\[\],;|=]+")
VAR_PREFIX_PATTERN = re.compile(r"^\$\{?(CLAUDE_SKILL_DIR|CLAUDE_PLUGIN_ROOT)\}?[\\/]")
SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

# Directories the Agent Skills spec (and common practice) uses for bundled files.
BUNDLE_DIRS = frozenset([
    "references", "reference", "scripts", "script", "assets", "templates", "template",
    "examples", "resources",
])
TRAILING_PUNCT = ".,:;!?"


def _is_placeholder(path: str) -> bool:
    low = path.lower()
    return any(h in low for h in PLACEHOLDER_HINTS)


def _is_template(path: str) -> bool:
    return any(c in path for c in ("*", "{", "}", "<", ">", "[", "]")) or "$" in path


def _absolute_refs(line: str, line_num: int, is_local: bool) -> list[FileRef]:
    refs: list[FileRef] = []
    for m in WIN_ABS_PATTERN.finditer(line):
        raw = m.group(1).rstrip(TRAILING_PUNCT)
        if _is_placeholder(raw) or "%" in raw:
            continue
        p = Path(raw)
        refs.append(FileRef(raw=raw, resolved=p, line=line_num, absolute=True,
                            exists=p.exists() if is_local else None))
    for m in POSIX_ABS_PATTERN.finditer(line):
        raw, user = m.group(1).rstrip(TRAILING_PUNCT), m.group(2)
        if user.lower() in PLACEHOLDER_USERS or _is_placeholder(raw):
            continue
        p = Path(raw)
        refs.append(FileRef(raw=raw, resolved=p, line=line_num, absolute=True,
                            exists=p.exists() if is_local else None))
    return refs


def _resolve(rel: str, bases: list[Path]) -> tuple[Path, bool]:
    first = (bases[0] / rel).resolve()
    for base in bases:
        candidate = (base / rel).resolve()
        if candidate.exists():
            return candidate, True
    return first, False


def _bundled_token(
    token: str,
    skill_dir: Path,
    plugin_root: Path | None,
) -> tuple[str, list[Path]] | None:
    """Return (relative path, base dirs) if the token looks like a file bundled with the skill.

    Tokens with an explicit ${CLAUDE_SKILL_DIR}/${CLAUDE_PLUGIN_ROOT} prefix are always checked.
    Bare `scripts/x.py` style tokens are relative to the skill directory (Agent Skills spec) and are
    only checked when that top-level directory exists there; otherwise the text is usually about
    the user's own project or is an example.
    """
    token = FRAGMENT_PATTERN.sub("", token.rstrip(TRAILING_PUNCT)).rstrip(TRAILING_PUNCT)
    m = VAR_PREFIX_PATTERN.match(token)
    if m:
        rest = token[m.end():]
        if not rest or _is_template(rest):
            return None
        if m.group(1) == "CLAUDE_PLUGIN_ROOT":
            return (rest, [plugin_root]) if plugin_root else None
        return rest, [skill_dir]

    norm = token.replace("\\", "/")
    if "/" not in norm or _is_template(norm) or SCHEME_PATTERN.match(norm):
        return None
    first_seg = norm.split("/", 1)[0]
    if first_seg not in BUNDLE_DIRS:
        return None
    if not (skill_dir / first_seg).is_dir():
        return None
    return norm, [skill_dir]


def extract_refs(
    body: str,
    skill_dir: Path,
    plugin_root: Path | None,
    line_offset: int,
    is_local: bool = True,
) -> list[FileRef]:
    """Extract machine-specific absolute paths and references to bundled files."""
    refs: list[FileRef] = []
    seen_raw: set[str] = set()

    def add(ref: FileRef) -> None:
        if ref.raw not in seen_raw:
            seen_raw.add(ref.raw)
            refs.append(ref)

    for idx, line in enumerate(body.splitlines()):
        line_num = line_offset + idx

        for ref in _absolute_refs(line, line_num, is_local):
            add(ref)

        # Explicit markdown links / images are always meant to resolve.
        for m in MD_LINK_PATTERN.finditer(line):
            target = unquote(m.group(1).split("#", 1)[0].split("?", 1)[0]).strip()
            if (
                not target
                or target.startswith(("/", "#"))
                or SCHEME_PATTERN.match(target)
                or _is_template(target)
                or ("." not in target and "/" not in target)  # placeholders like [title](url)
            ):
                continue
            var = _bundled_token(target, skill_dir, plugin_root) if target.startswith("$") else None
            if target.startswith("$") and var is None:
                continue
            rel, bases = var if var else (target, [b for b in (skill_dir, plugin_root) if b])
            resolved, exists = _resolve(rel, bases)
            add(FileRef(raw=target, resolved=resolved, line=line_num, absolute=False, exists=exists))

        # Paths mentioned in prose, inline code or code blocks (e.g. `python scripts/x.py --y`).
        for token in TOKEN_SPLIT_PATTERN.split(line):
            if not token or token in seen_raw:
                continue
            hit = _bundled_token(token, skill_dir, plugin_root)
            if not hit:
                continue
            rel, bases = hit
            raw = FRAGMENT_PATTERN.sub("", token.rstrip(TRAILING_PUNCT)).rstrip(TRAILING_PUNCT)
            if raw in seen_raw:
                continue
            resolved, exists = _resolve(rel, bases)
            add(FileRef(raw=raw, resolved=resolved, line=line_num, absolute=False, exists=exists))

    return refs
