from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    # Calibrated on 11 public packs; see docs/calibration.md
    "thresholds": {
        "overlap_warn": 0.25,
        "overlap_info": 0.20,
        "greedy_warn": 5.0,
        "greedy_info": 5.0,  # scores 3-4.9 were right only 2/9 times, so no INFO level
    },
    "severity": {},
    "ignore": [],
    "override": [],
    "sources": {
        "exclude_dirs_extra": [],
    },
    "tokenize": {
        "stopwords_extra": [],
        "template_words_extra": [],
    },
}


def find_config_file(explicit_path: str | Path | None = None) -> Path | None:
    """Find .skillclash.toml in standard locations."""
    if explicit_path:
        p = Path(explicit_path)
        return p if p.is_file() else None

    # 1. Current working directory
    cwd_path = Path.cwd() / ".skillclash.toml"
    if cwd_path.is_file():
        return cwd_path

    # 2. Upwards to git root
    curr = Path.cwd()
    for parent in [curr, *curr.parents]:
        git_dir = parent / ".git"
        candidate = parent / ".skillclash.toml"
        if candidate.is_file():
            return candidate
        if git_dir.is_dir() or git_dir.is_file():
            break

    # 3. User config directory
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            user_cfg = Path(app_data) / "skillclash" / "config.toml"
            if user_cfg.is_file():
                return user_cfg
    else:
        user_cfg = Path.home() / ".config" / "skillclash" / "config.toml"
        if user_cfg.is_file():
            return user_cfg

    return None


def load_config(explicit_path: str | Path | None = None) -> tuple[dict[str, Any], Path | None]:
    """Load configuration dictionary merged with defaults."""
    cfg_file = find_config_file(explicit_path)
    merged: dict[str, Any] = {
        "thresholds": dict(DEFAULT_CONFIG["thresholds"]),
        "severity": dict(DEFAULT_CONFIG["severity"]),
        "ignore": list(DEFAULT_CONFIG["ignore"]),
        "override": list(DEFAULT_CONFIG["override"]),
        "sources": dict(DEFAULT_CONFIG["sources"]),
        "tokenize": dict(DEFAULT_CONFIG["tokenize"]),
    }

    if cfg_file and cfg_file.is_file():
        with open(cfg_file, "rb") as f:
            data = tomllib.load(f)
        for section, val in data.items():
            if isinstance(val, dict) and section in merged and isinstance(merged[section], dict):
                merged[section].update(val)
            else:
                merged[section] = val

    return merged, cfg_file
