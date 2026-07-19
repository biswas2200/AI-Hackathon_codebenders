"""
TDD-style unit tests for pipeline/llm_utils.py: the RateLimiter, the
cache/checkpoint layer, mock mode, and the retry/backoff behavior of
call_groq. No real network calls are made anywhere in this file.
"""

import json
import os
import time
from types import SimpleNamespace

import httpx
import pytest
from groq import RateLimitError

from pipeline import llm_utils
from pipeline.llm_utils import RateLimiter, call_groq, rate_limiter_for


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_llm_utils(tmp_path, monkeypatch):
    """Every test gets a scratch cache dir, a clean rate-limiter registry,
    and DISCOVERYOS_MOCK unset unless the test opts in."""
    cache_dir = tmp_path / ".cache"
    monkeypatch.setattr(llm_utils, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(llm_utils, "CALL_COUNT_FILE", cache_dir / "_real_call_count.json")
    monkeypatch.setattr(llm_utils, "_rate_limiters", {})
    monkeypatch.delenv("DISCOVERYOS_MOCK", raising=False)
    yield


def _make_rate_limit_error(retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code=429, headers=headers, request=request)
    return RateLimitError("rate limited", response=response, body={"error": {"message": "rate limited"}})


class FakeCompletions:
    """Stand-in for client.chat.completions. `responses` is a queue of
    either a response-text string (success) or an Exception instance."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.call_kwargs = []

    def create(self, **kwargs):
        self.calls += 1
        self.call_kwargs.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))])


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


# ---------------------------------------------------------------------------
# load_dotenv
# ---------------------------------------------------------------------------

class TestLoadDotenv:
    def test_loads_key_value_pairs_into_environ(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SOME_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("SOME_TEST_KEY=hello\n")
        llm_utils.load_dotenv(env_file)
        assert os.environ.get("SOME_TEST_KEY") == "hello"
        monkeypatch.delenv("SOME_TEST_KEY", raising=False)

    def test_existing_environment_variable_wins_over_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOME_TEST_KEY", "from-shell")
        env_file = tmp_path / ".env"
        env_file.write_text("SOME_TEST_KEY=from-file\n")
        llm_utils.load_dotenv(env_file)
        assert os.environ["SOME_TEST_KEY"] == "from-shell"

    def test_missing_file_is_a_silent_no_op(self, tmp_path):
        llm_utils.load_dotenv(tmp_path / "does_not_exist.env")  # must not raise

    def test_comments_blanks_and_quotes_are_handled(self, tmp_path, monkeypatch):
        monkeypatch.delenv("QUOTED_TEST_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('# a comment\n\nQUOTED_TEST_KEY="quoted value"\nmalformed-line\n')
        llm_utils.load_dotenv(env_file)
        assert os.environ.get("QUOTED_TEST_KEY") == "quoted value"
        monkeypatch.delenv("QUOTED_TEST_KEY", raising=False)


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_rejects_nonpositive_rpm(self):
        with pytest.raises(ValueError):
            RateLimiter(rpm=0)
        with pytest.raises(ValueError):
            RateLimiter(rpm=-5)

    def test_burst_up_to_capacity_is_immediate(self):
        limiter = RateLimiter(rpm=60, capacity=3)
        start = time.monotonic()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    def test_blocks_once_capacity_exhausted(self):
        # 600 rpm -> 10 tokens/sec -> waiting for 1 token takes ~0.1s
        limiter = RateLimiter(rpm=600, capacity=1)
        limiter.acquire()  # consumes the initial token immediately
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08

    def test_tokens_refill_over_time(self):
        limiter = RateLimiter(rpm=600, capacity=1)
        limiter.acquire()
        time.sleep(0.15)  # enough time to refill at least one token
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05


class TestRateLimiterFor:
    def test_same_model_returns_same_instance(self):
        a = rate_limiter_for("llama-3.1-8b-instant")
        b = rate_limiter_for("llama-3.1-8b-instant")
        assert a is b

    def test_different_models_get_independent_limiters(self):
        a = rate_limiter_for("llama-3.1-8b-instant")
        b = rate_limiter_for("llama-3.3-70b-versatile")
        assert a is not b

    def test_unknown_model_falls_back_to_default_rpm(self):
        limiter = rate_limiter_for("some-future-model")
        assert limiter.refill_rate == pytest.approx(llm_utils.DEFAULT_RPM / 60.0)


# ---------------------------------------------------------------------------
# Cache (a.k.a. checkpointing)
# ---------------------------------------------------------------------------

class TestCache:
    def test_write_then_read_roundtrip(self):
        llm_utils._write_cache("some_key", '{"hello": "world"}')
        assert llm_utils._read_cache("some_key") == '{"hello": "world"}'

    def test_missing_key_returns_none(self):
        assert llm_utils._read_cache("never_written") is None

    def test_cache_path_is_sha256_of_key(self):
        import hashlib
        key = "extract_batch_abc123"
        expected = hashlib.sha256(key.encode("utf-8")).hexdigest()
        path = llm_utils._cache_path(key)
        assert path.name == f"{expected}.json"

    def test_different_keys_do_not_collide(self):
        llm_utils._write_cache("key_a", "response_a")
        llm_utils._write_cache("key_b", "response_b")
        assert llm_utils._read_cache("key_a") == "response_a"
        assert llm_utils._read_cache("key_b") == "response_b"

    def test_call_groq_cache_hit_never_touches_client(self):
        llm_utils._write_cache("precomputed", "cached response text")
        client = FakeClient(responses=[AssertionError("should not be called")])
        result = call_groq(client, "llama-3.1-8b-instant", "any prompt", cache_key="precomputed")
        assert result == "cached response text"
        assert client.chat.completions.calls == 0

    def test_call_groq_cache_hit_skips_rate_limiter(self, monkeypatch):
        llm_utils._write_cache("precomputed", "cached response text")
        client = FakeClient(responses=[])

        def _boom(model):
            raise AssertionError("rate limiter should not be invoked on a cache hit")

        monkeypatch.setattr(llm_utils, "rate_limiter_for", _boom)
        result = call_groq(client, "llama-3.1-8b-instant", "any prompt", cache_key="precomputed")
        assert result == "cached response text"

    def test_call_groq_real_call_writes_cache_for_next_time(self):
        client = FakeClient(responses=['{"pain_points": []}'])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="fresh_key")
        assert llm_utils._read_cache("fresh_key") == '{"pain_points": []}'

    def test_call_groq_second_call_with_same_key_hits_cache(self):
        client = FakeClient(responses=['{"pain_points": []}'])
        first = call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="repeat_key")
        second = call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="repeat_key")
        assert first == second
        assert client.chat.completions.calls == 1  # only the first call hit the network


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

class TestMockMode:
    def test_is_mock_mode_reflects_live_env(self, monkeypatch):
        assert llm_utils.is_mock_mode() is False
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        assert llm_utils.is_mock_mode() is True

    def test_mock_extraction_returns_one_point_per_source(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        sources = [{"id": "src_001", "text": "..."}, {"id": "src_002", "text": "..."}]
        prompt = "some prompt preamble\nSOURCES:\n" + json.dumps(sources)
        response = call_groq(None, "llama-3.1-8b-instant", prompt, cache_key="extract_batch_abc")
        parsed = json.loads(response)
        assert [p["source_id"] for p in parsed["pain_points"]] == ["src_001", "src_002"]

    def test_mock_extraction_is_deterministic(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        sources = [{"id": "src_001", "text": "..."}]
        prompt = "SOURCES:\n" + json.dumps(sources)
        r1 = call_groq(None, "llama-3.1-8b-instant", prompt, cache_key="extract_batch_x")
        llm_utils._cache_path("extract_batch_x").unlink()  # force recompute, not a cache hit
        r2 = call_groq(None, "llama-3.1-8b-instant", prompt, cache_key="extract_batch_x")
        assert r1 == r2

    def test_mock_clustering_drops_exactly_two_point_ids(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [{"point_id": f"src_{i:03d}_p1", "pain_point": "x", "use_case": "y"} for i in range(1, 8)]
        prompt = "PAIN POINTS:\n" + json.dumps(points)
        response = call_groq(None, "llama-3.3-70b-versatile", prompt, cache_key="cluster_xyz")
        themes = json.loads(response)["themes"]

        all_input_ids = {p["point_id"] for p in points}
        clustered_ids = {pid for t in themes for pid in t["point_ids"]}
        orphaned = all_input_ids - clustered_ids

        assert len(orphaned) == 2
        assert 1 <= len(themes) <= 3

    def test_mock_clustering_produces_valid_theme_shape(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [{"point_id": f"src_{i:03d}_p1"} for i in range(1, 6)]
        prompt = "PAIN POINTS:\n" + json.dumps(points)
        response = call_groq(None, "llama-3.3-70b-versatile", prompt, cache_key="cluster_shape")
        themes = json.loads(response)["themes"]
        for theme in themes:
            assert "theme_name" in theme
            assert "theme_description" in theme
            assert "point_ids" in theme
            assert len(theme["point_ids"]) > 0

    def test_mock_narrative_matches_every_theme_by_name(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        themes = [{"theme_name": "Slow Exports"}, {"theme_name": "Confusing Onboarding"}]
        prompt = "THEMES:\n" + json.dumps(themes)
        response = call_groq(None, "llama-3.3-70b-versatile", prompt, cache_key="narratives_abc")
        summaries = json.loads(response)["summaries"]
        names = {s["theme_name"] for s in summaries}
        assert names == {"Slow Exports", "Confusing Onboarding"}
        assert all(s["executive_summary"] for s in summaries)

    def test_mock_mode_requires_cache_key(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        with pytest.raises(ValueError):
            call_groq(None, "llama-3.1-8b-instant", "SOURCES:\n[]", cache_key=None)

    def test_mock_mode_unknown_cache_key_prefix_raises(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        with pytest.raises(ValueError):
            call_groq(None, "llama-3.1-8b-instant", "SOURCES:\n[]", cache_key="totally_unrecognized_prefix")

    def test_mock_mode_never_touches_rate_limiter(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")

        def _boom(model):
            raise AssertionError("rate limiter should not be invoked in mock mode")

        monkeypatch.setattr(llm_utils, "rate_limiter_for", _boom)
        prompt = "SOURCES:\n" + json.dumps([{"id": "src_001", "text": "..."}])
        call_groq(None, "llama-3.1-8b-instant", prompt, cache_key="extract_batch_nolimiter")

    def test_mock_mode_does_not_increment_real_call_count(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        llm_utils.reset_call_count()
        prompt = "SOURCES:\n" + json.dumps([{"id": "src_001", "text": "..."}])
        call_groq(None, "llama-3.1-8b-instant", prompt, cache_key="extract_batch_countcheck")
        assert llm_utils.real_call_count() == 0


# ---------------------------------------------------------------------------
# Real-call path: retries, backoff, call counting
# ---------------------------------------------------------------------------

class TestRealCallRetryAndCounting:
    def test_successful_call_increments_real_call_count(self):
        llm_utils.reset_call_count()
        client = FakeClient(responses=['{"ok": true}'])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="k1")
        assert llm_utils.real_call_count() == 1

    def test_cache_hit_does_not_increment_real_call_count(self):
        llm_utils.reset_call_count()
        client = FakeClient(responses=['{"ok": true}', AssertionError("should not be called again")])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="k2")
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="k2")
        assert llm_utils.real_call_count() == 1

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        client = FakeClient(responses=[_make_rate_limit_error(retry_after=3), '{"ok": true}'])
        llm_utils.reset_call_count()

        result = call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="retry_key")

        assert result == '{"ok": true}'
        assert client.chat.completions.calls == 2
        assert llm_utils.real_call_count() == 1  # only the successful attempt counts
        assert 3.0 in sleeps  # honored the Retry-After header

    def test_uses_retry_after_header_when_present(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        client = FakeClient(responses=[_make_rate_limit_error(retry_after=7), '{"ok": true}'])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="header_key")
        assert sleeps == [7.0]

    def test_falls_back_to_default_backoff_when_no_header(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
        client = FakeClient(responses=[_make_rate_limit_error(retry_after=None), '{"ok": true}'])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="no_header_key")
        assert sleeps == [llm_utils.DEFAULT_RETRY_AFTER_SECONDS]

    def test_gives_up_after_max_attempts_with_clear_error(self, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda s: None)
        client = FakeClient(responses=[_make_rate_limit_error(), _make_rate_limit_error()])
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="doomed_key")
        assert client.chat.completions.calls == llm_utils.MAX_ATTEMPTS

    def test_exhausted_retries_do_not_write_a_cache_entry(self, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda s: None)
        client = FakeClient(responses=[_make_rate_limit_error(), _make_rate_limit_error()])
        with pytest.raises(RuntimeError):
            call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="never_cached")
        assert llm_utils._read_cache("never_cached") is None

    def test_non_rate_limit_exception_propagates_immediately_without_retry(self):
        client = FakeClient(responses=[ValueError("boom")])
        with pytest.raises(ValueError, match="boom"):
            call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="value_error_key")
        assert client.chat.completions.calls == 1

    def test_real_call_uses_json_object_response_format_by_default(self):
        client = FakeClient(responses=['{"ok": true}'])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="fmt_key")
        kwargs = client.chat.completions.call_kwargs[0]
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_json_mode_false_omits_response_format(self):
        client = FakeClient(responses=["plain text"])
        call_groq(client, "llama-3.1-8b-instant", "prompt", json_mode=False, cache_key="fmt_key2")
        kwargs = client.chat.completions.call_kwargs[0]
        assert kwargs["response_format"] is None

    def test_call_without_cache_key_still_hits_real_client(self):
        client = FakeClient(responses=['{"ok": true}'])
        result = call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key=None)
        assert result == '{"ok": true}'
        assert client.chat.completions.calls == 1


# ---------------------------------------------------------------------------
# Call-count reset / combined-total bookkeeping (used across extract.py and
# cluster_score.py to print a combined real-call total)
# ---------------------------------------------------------------------------

class TestCallCountBookkeeping:
    def test_reset_zeroes_the_counter(self):
        client = FakeClient(responses=['{"ok": true}'])
        call_groq(client, "llama-3.1-8b-instant", "prompt", cache_key="a")
        assert llm_utils.real_call_count() == 1
        llm_utils.reset_call_count()
        assert llm_utils.real_call_count() == 0

    def test_count_accumulates_across_simulated_stages(self):
        llm_utils.reset_call_count()
        extract_client = FakeClient(responses=['{"a": 1}', '{"b": 2}'])
        call_groq(extract_client, "llama-3.1-8b-instant", "p1", cache_key="stage1_a")
        call_groq(extract_client, "llama-3.1-8b-instant", "p2", cache_key="stage1_b")
        after_extract = llm_utils.real_call_count()
        assert after_extract == 2

        cluster_client = FakeClient(responses=['{"c": 3}'])
        call_groq(cluster_client, "llama-3.3-70b-versatile", "p3", cache_key="stage2_a")
        combined = llm_utils.real_call_count()
        assert combined == 3


# ---------------------------------------------------------------------------
# clear_cache (drives the app's pipeline-mode switch)
# ---------------------------------------------------------------------------

class TestClearCache:
    def _seed(self):
        llm_utils._write_cache("extract_batch_aaa", "e1")
        llm_utils._write_cache("extract_batch_bbb", "e2")
        llm_utils._write_cache("cluster_ccc", "c1")
        llm_utils._write_cache("narratives_ddd", "n1")

    def test_prefix_clears_only_matching_entries(self):
        self._seed()
        removed = llm_utils.clear_cache(["cluster_", "narratives_"])
        assert removed == 2
        # extraction survives -> a rerun would be cheap
        assert llm_utils._read_cache("extract_batch_aaa") == "e1"
        assert llm_utils._read_cache("extract_batch_bbb") == "e2"
        # cluster/narrative gone -> a rerun re-calls them
        assert llm_utils._read_cache("cluster_ccc") is None
        assert llm_utils._read_cache("narratives_ddd") is None

    def test_none_clears_everything(self):
        self._seed()
        removed = llm_utils.clear_cache(None)
        assert removed == 4
        for key in ("extract_batch_aaa", "extract_batch_bbb", "cluster_ccc", "narratives_ddd"):
            assert llm_utils._read_cache(key) is None

    def test_never_deletes_the_call_count_file(self):
        self._seed()
        llm_utils.reset_call_count()
        assert llm_utils.CALL_COUNT_FILE.exists()
        llm_utils.clear_cache(None)
        assert llm_utils.CALL_COUNT_FILE.exists()

    def test_missing_cache_dir_is_a_no_op(self, tmp_path, monkeypatch):
        monkeypatch.setattr(llm_utils, "CACHE_DIR", tmp_path / "does_not_exist")
        assert llm_utils.clear_cache(None) == 0

    def test_returns_zero_when_no_entries_match(self):
        self._seed()
        assert llm_utils.clear_cache(["no_such_prefix_"]) == 0


# ---------------------------------------------------------------------------
# MODEL_LIMITS (accuracy against the account's Settings -> Limits page)
# ---------------------------------------------------------------------------

class TestModelLimits:
    def test_both_models_are_30_rpm(self):
        assert llm_utils.MODEL_LIMITS["llama-3.1-8b-instant"]["rpm"] == 30
        assert llm_utils.MODEL_LIMITS["llama-3.3-70b-versatile"]["rpm"] == 30

    def test_model_rpm_is_derived_from_model_limits(self):
        for model, limits in llm_utils.MODEL_LIMITS.items():
            assert llm_utils.MODEL_RPM[model] == limits["rpm"]

    def test_per_model_rpd_reflects_the_documented_split(self):
        # the whole reason extraction and clustering use different models
        assert llm_utils.MODEL_LIMITS["llama-3.1-8b-instant"]["rpd"] == 14400
        assert llm_utils.MODEL_LIMITS["llama-3.3-70b-versatile"]["rpd"] == 1000
