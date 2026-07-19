#!/usr/bin/env python3
"""
Shared LLM plumbing for the pipeline: response caching (which doubles as
checkpointing), mock mode, and rate-limit-aware calls to Groq.

extract.py and cluster_score.py both import this and never call the Groq
SDK directly.
"""

import hashlib
import json
import os
import threading
import time
from pathlib import Path

from groq import RateLimitError

CACHE_DIR = Path("data/.cache")
CALL_COUNT_FILE = CACHE_DIR / "_real_call_count.json"

# Real per-model rate limits, transcribed from the account's own
# GroqCloud Settings -> Limits page (the authoritative source -- do not
# trust general blog estimates over this). Both models are 30 RPM; RPD and
# TPM differ sharply, which is why extraction (high call volume) and
# clustering/narratives (low volume, reasoning-heavy) are routed to
# different models.
#
# NOTE: only RPM is actively enforced client-side, via the token-bucket
# RateLimiter below. RPD and TPM are documented here for accuracy but are
# NOT hard-enforced in-process -- a TPM overage surfaces as a 429, which
# the retry/backoff in call_groq() catches and waits out. That's an
# intentional simplicity trade-off for a single-process demo (see spec
# non-goals): RPM pacing prevents the common burst problem, and the
# reactive 429 handler covers the rarer token-rate case.
MODEL_LIMITS = {
    "llama-3.1-8b-instant": {"rpm": 30, "rpd": 14400, "tpm": 6000, "tpd": 500000},
    "llama-3.3-70b-versatile": {"rpm": 30, "rpd": 1000, "tpm": 12000, "tpd": 100000},
}
# Derived RPM lookup used by the limiter (kept as its own name for the
# limiter's call sites and tests).
MODEL_RPM = {model: limits["rpm"] for model, limits in MODEL_LIMITS.items()}
DEFAULT_RPM = 30
RATE_LIMITER_CAPACITY = 5

DEFAULT_RETRY_AFTER_SECONDS = 20
MAX_ATTEMPTS = 2


def load_dotenv(path=None):
    """Minimal .env loader (KEY=value lines; # comments and blanks skipped).
    Values already present in the real environment always win -- an
    exported GROQ_API_KEY overrides whatever the file says. Hand-rolled to
    avoid adding python-dotenv to the fixed dependency list for what is a
    five-line parse."""
    if path is None:
        path = Path(__file__).resolve().parent.parent / ".env"
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def is_mock_mode():
    """Live re-check of DISCOVERYOS_MOCK, not a value frozen at import time."""
    return os.environ.get("DISCOVERYOS_MOCK") == "1"


# Kept for spec-literal parity; call_groq itself uses is_mock_mode() so
# toggling the env var after import (as tests do) still takes effect.
MOCK_MODE = is_mock_mode()


class RateLimiter:
    """Minimal token-bucket limiter. .acquire() blocks until a token is free."""

    def __init__(self, rpm, capacity=RATE_LIMITER_CAPACITY):
        if rpm <= 0:
            raise ValueError("rpm must be positive")
        self.capacity = capacity
        self.refill_rate = rpm / 60.0  # tokens per second
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

    def acquire(self):
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.refill_rate
            time.sleep(wait)


_rate_limiters = {}
_rate_limiters_lock = threading.Lock()


def rate_limiter_for(model):
    """One RateLimiter instance per model, created lazily."""
    with _rate_limiters_lock:
        limiter = _rate_limiters.get(model)
        if limiter is None:
            rpm = MODEL_RPM.get(model, DEFAULT_RPM)
            limiter = RateLimiter(rpm)
            _rate_limiters[model] = limiter
        return limiter


def _cache_path(cache_key):
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _read_cache(cache_key):
    path = _cache_path(cache_key)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)["response"]


def _write_cache(cache_key, response_text):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_key)
    with open(path, "w") as f:
        json.dump({"cache_key": cache_key, "response": response_text}, f)


def clear_cache(prefixes=None):
    """Delete cached LLM responses so the next run re-calls the API.

    Cache filenames are opaque sha256 hashes, so matching by prefix means
    reading each file's stored `cache_key` field. This is what the app's
    pipeline-mode switch uses:
      - `prefixes=["cluster_", "narratives_"]` clears only the
        clustering/narrative responses, leaving the expensive extraction
        cache intact -> a rerun re-spends ~2 real calls, not ~20.
      - `prefixes=None` clears everything (a full live re-run) except the
        `_real_call_count.json` bookkeeping file.

    Returns the number of cache entries removed.
    """
    if not CACHE_DIR.exists():
        return 0
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        if path.name == CALL_COUNT_FILE.name:
            continue
        if prefixes is None:
            path.unlink()
            removed += 1
            continue
        try:
            with open(path) as f:
                key = json.load(f).get("cache_key", "")
        except (json.JSONDecodeError, OSError):
            continue
        if any(key.startswith(p) for p in prefixes):
            path.unlink()
            removed += 1
    return removed


def reset_call_count():
    """Zero the shared real-call counter. Call once at the start of a fresh
    pipeline run (extract.py does this) so cluster_score.py's later read
    reflects only this run, not leftover state from a prior one."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CALL_COUNT_FILE, "w") as f:
        json.dump({"count": 0}, f)


def real_call_count():
    if not CALL_COUNT_FILE.exists():
        return 0
    try:
        with open(CALL_COUNT_FILE) as f:
            return json.load(f).get("count", 0)
    except (json.JSONDecodeError, OSError):
        return 0


def _increment_call_count():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    current = real_call_count()
    current += 1
    with open(CALL_COUNT_FILE, "w") as f:
        json.dump({"count": current}, f)
    return current


def _extract_retry_after(err):
    """Best-effort extraction of a Retry-After hint from a RateLimitError."""
    response = getattr(err, "response", None)
    if response is not None:
        header_val = response.headers.get("retry-after")
        if header_val is not None:
            try:
                return float(header_val)
            except (TypeError, ValueError):
                pass
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        err_obj = body.get("error", {}) if isinstance(body.get("error"), dict) else {}
        for key in ("retry_after", "retry_after_ms"):
            val = err_obj.get(key)
            if val is not None:
                try:
                    val = float(val)
                    return val / 1000.0 if key.endswith("_ms") else val
                except (TypeError, ValueError):
                    pass
    return None


def _mock_extract_response(prompt):
    marker = "SOURCES:\n"
    idx = prompt.rindex(marker)
    sources = json.loads(prompt[idx + len(marker):])
    pain_points = [
        {
            "source_id": s["id"],
            "pain_point": "Mocked pain point for testing",
            "quote": "mocked quote excerpt",
            "use_case": "Dashboard / reporting",
        }
        for s in sources
    ]
    return json.dumps({"pain_points": pain_points})


def _mock_cluster_response(prompt):
    marker = "PAIN POINTS:\n"
    idx = prompt.rindex(marker)
    points = json.loads(prompt[idx + len(marker):])
    point_ids = [p["point_id"] for p in points]

    # Deliberately drop up to 2 point_ids from every theme -- this is the
    # fixture that proves the orphaned-point safety net actually works.
    dropped = point_ids[:2]
    remaining = point_ids[2:]

    n_groups = min(3, max(1, len(remaining)))
    groups = [[] for _ in range(n_groups)]
    for i, pid in enumerate(remaining):
        groups[i % n_groups].append(pid)

    themes = [
        {
            "theme_name": f"Mock Theme {i}",
            "theme_description": f"Mock description for theme {i}",
            "point_ids": group,
        }
        for i, group in enumerate(groups, 1)
        if group
    ]
    if not themes and dropped:
        # Degenerate case (<=2 total points): still return a valid, empty
        # theme list so the orphan check has something to catch.
        themes = []
    return json.dumps({"themes": themes})


def _mock_narrative_response(prompt):
    marker = "THEMES:\n"
    idx = prompt.rindex(marker)
    themes = json.loads(prompt[idx + len(marker):])
    summaries = [
        {
            "theme_name": t["theme_name"],
            "executive_summary": f"[MOCK SUMMARY] Placeholder narrative for {t['theme_name']}.",
        }
        for t in themes
    ]
    return json.dumps({"summaries": summaries})


def _mock_response(cache_key, prompt):
    if not cache_key:
        raise ValueError(
            "Mock mode requires a deterministic cache_key so the mock "
            "fixture knows which canned response to return."
        )
    if cache_key.startswith("extract_batch_"):
        return _mock_extract_response(prompt)
    if cache_key.startswith("cluster_"):
        return _mock_cluster_response(prompt)
    if cache_key.startswith("narratives_"):
        return _mock_narrative_response(prompt)
    raise ValueError(f"No mock fixture registered for cache_key prefix: {cache_key!r}")


def call_groq(client, model, prompt, json_mode=True, cache_key=None):
    """Call Groq's chat completions API, or short-circuit via cache/mock.

    Returns the raw response text (a JSON string, when json_mode=True).
    """
    if cache_key:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    if is_mock_mode():
        response_text = _mock_response(cache_key, prompt)
        if cache_key:
            _write_cache(cache_key, response_text)
        return response_text

    rate_limiter_for(model).acquire()

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"} if json_mode else None,
            )
            response_text = completion.choices[0].message.content
            _increment_call_count()
            if cache_key:
                _write_cache(cache_key, response_text)
            return response_text
        except RateLimitError as e:
            last_error = e
            if attempt < MAX_ATTEMPTS:
                retry_after = _extract_retry_after(e)
                if retry_after is None:
                    retry_after = DEFAULT_RETRY_AFTER_SECONDS
                print(
                    f"\n  ↳ rate limited on {model}, retrying in {retry_after:.0f}s "
                    f"(attempt {attempt}/{MAX_ATTEMPTS})...",
                    end=" ",
                    flush=True,
                )
                time.sleep(retry_after)

    raise RuntimeError(
        f"Rate limit exceeded for model '{model}' after {MAX_ATTEMPTS} attempts. "
        f"Check remaining quota at https://console.groq.com (Settings -> Limits) "
        f"before running again."
    ) from last_error
