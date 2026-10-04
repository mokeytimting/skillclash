from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from skillclash.cache import get_llm_cache_dir
from skillclash.parse.tokenize import CJK_CHAR_PATTERN


def estimate_tokens(text: str) -> int:
    """Estimate token count: ASCII / 4 + CJK * 1."""
    if not text:
        return 0
    cjk = sum(1 for ch in text if CJK_CHAR_PATTERN.match(ch))
    ascii_len = len(text) - cjk
    return (ascii_len // 4) + cjk


def extract_json_from_response(raw_text: str) -> dict[str, Any]:
    """Parse JSON directly, or extract substring from first { to last }."""
    raw = raw_text.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Extract first { to last }
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = raw[first_brace : last_brace + 1]
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data

    raise ValueError(f"Could not extract valid JSON from response: {raw[:100]}...")


class LLMBackend(Protocol):
    name: str
    model: str

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        cache_key_extra: str = "",
    ) -> dict[str, Any]:
        """Send chat prompt and return parsed JSON."""
        ...


class BaseBackend:
    def __init__(
        self,
        name: str,
        model: str,
        api_key: str | None,
        use_cache: bool = True,
    ):
        self.name = name
        self.model = model
        self._api_key = api_key
        self.use_cache = use_cache
        self.stats: dict[str, int] = {
            "calls": 0,
            "cache_hits": 0,
            "prompt_tokens_est": 0,
            "completion_tokens_est": 0,
        }

    def _get_cache_path(self, system: str, user: str, temperature: float, extra: str) -> Path:
        raw_key = f"{self.name}|{self.model}|{system}|{user}|{temperature}|{extra}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        cache_dir = get_llm_cache_dir()
        return cache_dir / f"{digest}.json"

    def _load_cache(self, cache_path: Path) -> dict[str, Any] | None:
        if not self.use_cache:
            return None
        if cache_path.is_file():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                self.stats["cache_hits"] += 1
                return data
            except Exception:
                return None
        return None

    def _save_cache(self, cache_path: Path, data: dict[str, Any]) -> None:
        if not self.use_cache:
            return
        try:
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


class OpenAICompatBackend(BaseBackend):
    """OpenAI-compatible chat completions backend (DeepSeek / OpenAI)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        use_cache: bool = True,
    ):
        key = (
            api_key
            or os.environ.get("SKILLCLASH_OPENAI_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        url = (
            base_url
            or os.environ.get("SKILLCLASH_OPENAI_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        m = (
            model
            or os.environ.get("SKILLCLASH_JUDGE_MODEL")
            or "deepseek-chat"
        )
        super().__init__("openai_compat", m, key, use_cache=use_cache)
        self.base_url = url.rstrip("/")

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        cache_key_extra: str = "",
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ValueError(
                "Missing API key: set DEEPSEEK_API_KEY or SKILLCLASH_OPENAI_API_KEY."
            )

        cache_path = self._get_cache_path(system, user, temperature, cache_key_extra)
        cached = self._load_cache(cache_path)
        if cached is not None:
            return cached

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        endpoint = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        self.stats["prompt_tokens_est"] += estimate_tokens(system) + estimate_tokens(user)
        self.stats["calls"] += 1

        last_err = None
        for attempt, delay in enumerate([1, 2, 4]):
            try:
                req = urllib.request.Request(endpoint, data=body_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    content = resp_data["choices"][0]["message"]["content"]
                    parsed = extract_json_from_response(content)
                    self.stats["completion_tokens_est"] += estimate_tokens(content)
                    self._save_cache(cache_path, parsed)
                    return parsed
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(delay)
                    continue
                raise
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError(f"OpenAICompatBackend request failed after 3 retries: {last_err}")


class AnthropicBackend(BaseBackend):
    """Anthropic Messages API backend."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        use_cache: bool = True,
    ):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        m = model or os.environ.get("SKILLCLASH_ROUTE_MODEL") or "claude-sonnet-5-5"
        super().__init__("anthropic", m, key, use_cache=use_cache)
        self.endpoint = "https://api.anthropic.com/v1/messages"

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 800,
        temperature: float = 0.0,
        cache_key_extra: str = "",
    ) -> dict[str, Any]:
        if not self._api_key:
            raise ValueError("Missing API key: set ANTHROPIC_API_KEY.")

        cache_path = self._get_cache_path(system, user, temperature, cache_key_extra)
        cached = self._load_cache(cache_path)
        if cached is not None:
            return cached

        payload = {
            "model": self.model,
            "system": system,
            "messages": [
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }

        self.stats["prompt_tokens_est"] += estimate_tokens(system) + estimate_tokens(user)
        self.stats["calls"] += 1

        last_err = None
        for attempt, delay in enumerate([1, 2, 4]):
            try:
                req = urllib.request.Request(self.endpoint, data=body_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    content_blocks = resp_data.get("content", [])
                    text_parts = [b.get("text", "") for b in content_blocks if b.get("type") == "text"]
                    full_text = "\n".join(text_parts)
                    parsed = extract_json_from_response(full_text)
                    self.stats["completion_tokens_est"] += estimate_tokens(full_text)
                    self._save_cache(cache_path, parsed)
                    return parsed
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(delay)
                    continue
                raise
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError(f"AnthropicBackend request failed after 3 retries: {last_err}")
