from __future__ import annotations

import os
import sys
from pathlib import Path


def get_cache_root() -> Path:
    """Return cache root directory based on platform or environment."""
    env_override = os.environ.get("SKILLCLASH_CACHE_DIR")
    if env_override:
        p = Path(env_override)
        p.mkdir(parents=True, exist_ok=True)
        return p

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            cache_dir = Path(local_app_data) / "skillclash"
        else:
            user_profile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
            cache_dir = Path(user_profile) / "AppData" / "Local" / "skillclash"
    else:
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            cache_dir = Path(xdg_cache) / "skillclash"
        else:
            home = os.environ.get("HOME") or "."
            cache_dir = Path(home) / ".cache" / "skillclash"

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        test_file = cache_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        return cache_dir
    except (PermissionError, OSError):
        fallback_dir = Path.cwd() / ".cache" / "skillclash"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir


def get_repo_cache_dir(owner: str, repo: str) -> Path:
    """Return short path for cloned repository cache: <cache>/r/<owner>__<repo>."""
    repo_dir = get_cache_root() / "r" / f"{owner}__{repo}"
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    return repo_dir


def get_llm_cache_dir() -> Path:
    """Return LLM responses cache directory: <cache>/llm/."""
    llm_dir = get_cache_root() / "llm"
    llm_dir.mkdir(parents=True, exist_ok=True)
    return llm_dir
