"""HTTP access with per-host rate limits, retries and a local response cache."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import __version__

# Minimum seconds between request starts per host. arXiv asks for one request every
# three seconds; DBLP asks for restraint; Crossref and OpenAlex allow ~10/s on polite use.
MIN_INTERVAL = {
    "api.crossref.org": 0.1,
    "api.openalex.org": 0.1,
    "doi.org": 0.2,
    "dblp.org": 1.0,
    "export.arxiv.org": 3.0,
    "eutils.ncbi.nlm.nih.gov": 0.34,
    "api.semanticscholar.org": 1.0,
}
_CACHEABLE = {200, 404}
_RETRY = {429, 500, 502, 503, 504}
_ATTEMPTS = 4


class Offline(Exception):
    """Raised in offline mode when a response is not in the cache."""


@dataclass
class Response:
    status: int
    text: str

    def json(self):
        return json.loads(self.text)


def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if not base and os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
    return Path(base or Path.home() / ".cache") / "reference-verifier" / "cache.sqlite3"


class Cache:
    """Successful and not-found responses, kept for `ttl_days` so reruns are instant."""

    def __init__(self, path: Path, ttl_days: float = 30):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS http (key TEXT PRIMARY KEY, status INTEGER, body TEXT, fetched REAL)")
        self._db.commit()
        self._lock = threading.Lock()
        self._ttl = ttl_days * 86400

    def get(self, key: str) -> Response | None:
        with self._lock:
            row = self._db.execute("SELECT status, body, fetched FROM http WHERE key = ?", (key,)).fetchone()
        if row and time.time() - row[2] < self._ttl:
            return Response(row[0], row[1])
        return None

    def put(self, key: str, resp: Response) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO http VALUES (?, ?, ?, ?)", (key, resp.status, resp.text, time.time())
            )
            self._db.commit()


class Http:
    def __init__(self, mailto: str | None = None, cache: Cache | None = None, offline: bool = False, timeout: float = 20.0):
        contact = f"; mailto:{mailto}" if mailto else ""
        ua = f"reference-verifier/{__version__} (+https://github.com/the-aurora-lab/reference-verifier{contact})"
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": ua})
        self.cache = cache
        self.offline = offline
        self._host_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last: dict[str, float] = {}
        self.calls: Counter[str] = Counter()  # network requests per host, for the summary

    @staticmethod
    def _key(url: str, params: dict | None, headers: dict | None, secret: tuple[str, ...]) -> str:
        public = sorted((k, str(v)) for k, v in (params or {}).items() if k not in secret)
        accept = (headers or {}).get("Accept", "")  # other headers (API keys) never enter the cache key
        return hashlib.sha256(json.dumps([url, public, accept]).encode()).hexdigest()

    def _wait(self, host: str) -> None:
        gap = MIN_INTERVAL.get(host, 0.2)
        with self._host_locks[host]:
            elapsed = time.monotonic() - self._last.get(host, 0.0)
            if elapsed < gap:
                time.sleep(gap - elapsed)
            self._last[host] = time.monotonic()

    def get(self, url: str, params: dict | None = None, headers: dict | None = None, secret: tuple[str, ...] = ()) -> Response:
        key = self._key(url, params, headers, secret)
        if self.cache:
            hit = self.cache.get(key)
            if hit:
                return hit
        if self.offline:
            raise Offline(url)
        host = httpx.URL(url).host
        for attempt in range(_ATTEMPTS):
            self._wait(host)
            try:
                r = self._client.get(url, params=params, headers=headers)
            except httpx.TransportError:
                if attempt == _ATTEMPTS - 1:
                    raise
                time.sleep(2**attempt)
                continue
            self.calls[host] += 1
            if r.status_code in _RETRY and attempt < _ATTEMPTS - 1:
                wait = _retry_after(r, 2**attempt)
                if wait is not None:
                    time.sleep(wait)
                    continue
            resp = Response(r.status_code, r.text)
            if self.cache and r.status_code in _CACHEABLE:
                self.cache.put(key, resp)
            return resp
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._client.close()


def _retry_after(r: httpx.Response, default: float) -> float | None:
    """Seconds to wait before retrying, or None when the server asks for more than 30 s
    (an exhausted daily budget, for example): then the caller moves on to the next source."""
    try:
        wait = float(r.headers.get("retry-after", default))
    except ValueError:
        return default
    return wait if wait <= 30.0 else None
