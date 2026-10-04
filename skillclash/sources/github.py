from __future__ import annotations

import os
import subprocess
from pathlib import Path

from skillclash.cache import get_repo_cache_dir


def parse_github_spec(spec: str) -> tuple[str, str, str | None, str | None]:
    """Parse spec into (owner, repo, ref, plugin_filter).

    Examples:
        gh:owner/repo -> (owner, repo, None, None)
        gh:owner/repo@v1 -> (owner, repo, 'v1', None)
        gh:owner/repo#plugin -> (owner, repo, None, 'plugin')
        gh:owner/repo@v1#plugin -> (owner, repo, 'v1', 'plugin')
        https://github.com/owner/repo.git -> (owner, repo, None, None)
    """
    plugin_filter: str | None = None
    if "#" in spec:
        spec, plugin_filter = spec.split("#", 1)

    ref: str | None = None
    if "@" in spec and not spec.startswith("http"):
        spec, ref = spec.split("@", 1)

    if spec.startswith("gh:"):
        spec = spec[3:]
    elif spec.startswith("https://github.com/"):
        spec = spec[len("https://github.com/") :]
        if spec.endswith(".git"):
            spec = spec[:-4]
    elif spec.startswith("http://github.com/"):
        spec = spec[len("http://github.com/") :]
        if spec.endswith(".git"):
            spec = spec[:-4]

    parts = spec.strip("/").split("/")
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
    else:
        owner, repo = "unknown", parts[0] if parts else "unknown"

    return owner, repo, ref, plugin_filter


def fetch_github_repo(
    owner: str,
    repo: str,
    ref: str | None = None,
    *,
    offline: bool = False,
    refresh: bool = False,
) -> tuple[Path | None, str | None, str | None]:
    """Clone or update a remote GitHub repo into short-path cache.

    Returns:
        (cache_dir, commit_sha, error_message)
    """
    target_dir = get_repo_cache_dir(owner, repo)
    git_dir = target_dir / ".git"

    if offline:
        if git_dir.exists():
            sha = _get_sha(target_dir)
            return target_dir, sha, None
        return None, None, f"Offline mode: repo {owner}/{repo} not in cache."

    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"

    repo_url = f"https://github.com/{owner}/{repo}.git"

    if git_dir.exists():
        if refresh:
            try:
                fetch_cmd = ["git", "-c", "http.sslBackend=openssl", "fetch", "--depth", "1", "origin"]
                if ref:
                    fetch_cmd.append(ref)
                subprocess.run(
                    fetch_cmd,
                    cwd=target_dir,
                    env=env,
                    capture_output=True,
                    timeout=180,
                    check=True,
                )
                subprocess.run(
                    ["git", "reset", "--hard", "FETCH_HEAD"],
                    cwd=target_dir,
                    env=env,
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
            except (subprocess.SubprocessError, OSError) as e:
                return None, None, f"Failed to refresh {owner}/{repo}: {_git_error(e)}"
        sha = _get_sha(target_dir)
        return target_dir, sha, None

    # Clone fresh
    cmd = [
        "git",
        "-c",
        "http.sslBackend=openssl",
        "-c",
        "core.longpaths=true",
        "-c",
        "core.symlinks=false",
        "clone",
        "--depth",
        "1",
    ]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([repo_url, str(target_dir)])

    try:
        subprocess.run(cmd, env=env, capture_output=True, timeout=180, check=True)
        sha = _get_sha(target_dir)
        return target_dir, sha, None
    except (subprocess.SubprocessError, OSError) as e:
        return None, None, f"Failed to clone {owner}/{repo}: {_git_error(e)}"


def _git_error(e: BaseException) -> str:
    """Short, path-free description of a git failure."""
    if isinstance(e, subprocess.TimeoutExpired):
        return "timed out"
    if isinstance(e, subprocess.CalledProcessError):
        stderr = (e.stderr or b"").decode("utf-8", errors="replace").strip().splitlines()
        tail = next((ln for ln in reversed(stderr) if ln.strip()), "")
        return f"git exited with {e.returncode}" + (f": {tail}" if tail else "")
    if isinstance(e, FileNotFoundError):
        return "git is not installed or not on PATH"
    return type(e).__name__


def _get_sha(repo_dir: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"
