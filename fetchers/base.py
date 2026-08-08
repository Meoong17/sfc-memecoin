"""Base HTTP fetching layer — shared by all fetchers.

Provides:
  - rate-limit guard (token bucket, per-source),
  - retry with exponential backoff on 429/5xx,
  - disk cache (JSON) to avoid re-fetching unchanged data,
  - JSON POST helper for JSON-RPC (Helius/RPC).

Every fetcher inherits from this; producers (data_sources/*) stay unchanged —
they receive the dataclasses the fetchers map into.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from config.settings import RATE_LIMITS


class FetchError(Exception):
    """Raised when a fetch fails after retries."""


class _TokenBucket:
    """Simple token-bucket rate limiter."""

    def __init__(self, per_sec: int) -> None:
        self.rate = max(1, per_sec)
        self.tokens = float(self.rate)
        self.updated = time.monotonic()

    def acquire(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.rate, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < 1.0:
            wait = (1.0 - self.tokens) / self.rate
            time.sleep(wait)
            self.tokens = 0.0
            self.updated = time.monotonic()
        else:
            self.tokens -= 1.0


class BaseFetcher:
    """HTTP fetch base with retry, rate-limit, cache."""

    def __init__(self, *, source: str = "rpc", cache_dir: str | None = None,
                 cache_ttl: int = 300) -> None:
        rl = RATE_LIMITS.get(source, RATE_LIMITS["rpc"])
        self._limiter = _TokenBucket(rl.max_calls_per_sec)
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cache_ttl = cache_ttl
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "sfc-memecoin/0.1"})

    # --- cache ---
    def _cache_path(self, key: str) -> Path | None:
        if self._cache_dir is None:
            return None
        safe = "".join(c if c.isalnum() else "_" for c in key)[:120]
        return self._cache_dir / f"{safe}.json"

    def _cache_get(self, key: str) -> Any | None:
        p = self._cache_path(key)
        if p is None or not p.exists():
            return None
        if time.time() - p.stat().st_mtime > self._cache_ttl:
            return None
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _cache_put(self, key: str, data: Any) -> None:
        p = self._cache_path(key)
        if p is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))

    # --- HTTP primitives ---
    def _get(self, url: str, *, params: dict | None = None,
             headers: dict | None = None, cache_key: str | None = None,
             max_retries: int = 3) -> Any:
        if cache_key is not None:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        for attempt in range(max_retries):
            self._limiter.acquire()
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=30)
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise FetchError(f"GET {url} failed: {e}") from e
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 200:
                data = resp.json()
                if cache_key is not None:
                    self._cache_put(cache_key, data)
                return data
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt == max_retries - 1:
                    raise FetchError(f"GET {url} -> HTTP {resp.status_code}")
                time.sleep(2 ** attempt * 2)
                continue
            raise FetchError(f"GET {url} -> HTTP {resp.status_code}: {resp.text[:200]}")
        raise FetchError(f"GET {url}: exhausted retries")

    def _post_json(self, url: str, payload: dict, *, cache_key: str | None = None,
                   max_retries: int = 3) -> Any:
        if cache_key is not None:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        for attempt in range(max_retries):
            self._limiter.acquire()
            try:
                resp = self.session.post(url, json=payload, timeout=30)
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise FetchError(f"POST {url} failed: {e}") from e
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 200:
                data = resp.json()
                if cache_key is not None:
                    self._cache_put(cache_key, data)
                return data
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt == max_retries - 1:
                    raise FetchError(f"POST {url} -> HTTP {resp.status_code}")
                time.sleep(2 ** attempt * 2)
                continue
            raise FetchError(f"POST {url} -> HTTP {resp.status_code}: {resp.text[:200]}")
        raise FetchError(f"POST {url}: exhausted retries")
