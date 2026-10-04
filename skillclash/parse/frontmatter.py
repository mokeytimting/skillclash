from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def parse_skill_file(path: Path) -> tuple[dict[str, Any], str, int, str | None]:
    """Parse SKILL.md file into (frontmatter, body, body_line_offset, error).

    Returns:
        frontmatter: parsed dictionary of frontmatter fields.
        body: markdown body text after frontmatter.
        body_line_offset: 1-based line number where body starts.
        error: None, 'missing', 'not_mapping', or 'invalid_yaml: <reason>'.
    """
    try:
        raw_bytes = path.read_bytes()
    except Exception as e:
        return {}, "", 1, f"read_error: {e}"

    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raw_bytes = raw_bytes[3:]

    text = raw_bytes.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    if not lines or lines[0].strip() != "---":
        return {}, text, 1, "missing"

    # Find second lone '---'
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return {}, text, 1, "missing"

    fm_raw = "\n".join(lines[1:end_idx])
    body_lines = lines[end_idx + 1 :]
    body = "\n".join(body_lines)
    body_line_offset = end_idx + 2  # 1-based: line after second '---'

    fm_dict: dict[str, Any] = {}
    error: str | None = None

    try:
        loaded = yaml.safe_load(fm_raw)
        if loaded is None:
            fm_dict = {}
        elif not isinstance(loaded, dict):
            error = "not_mapping"
            fm_dict = {}
        else:
            fm_dict = loaded
    except Exception as e:
        err_first_line = str(e).splitlines()[0] if str(e) else "parse error"
        error = f"invalid_yaml: {err_first_line}"
        # Fallback rescue for name and description
        rescued: dict[str, Any] = {}
        pattern = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
        for line in fm_raw.splitlines():
            m = pattern.match(line.strip())
            if m:
                k, v = m.group(1), m.group(2).strip()
                if (v.startswith('"') and v.endswith('"')) or (
                    v.startswith("'") and v.endswith("'")
                ):
                    v = v[1:-1]
                rescued[k] = v
        if "name" in rescued or "description" in rescued:
            fm_dict = rescued

    # Normalization
    if "name" in fm_dict and fm_dict["name"] is not None:
        fm_dict["name"] = str(fm_dict["name"]).strip()
    if "description" in fm_dict and fm_dict["description"] is not None:
        desc_str = str(fm_dict["description"]).strip()
        # Compress consecutive whitespace to single space
        fm_dict["description"] = re.sub(r"\s+", " ", desc_str)

    return fm_dict, body, body_line_offset, error
