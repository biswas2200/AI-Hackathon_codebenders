"""
TDD-style tests for pipeline/extract.py: batching, point_id assembly,
checkpointing (via the shared cache), and per-batch failure isolation.
No real network calls are made anywhere in this file.
"""

import json
import os
from types import SimpleNamespace

os.environ.setdefault("GROQ_API_KEY", "test-key-for-unit-tests")

import pytest

from pipeline import extract as extract_module
from pipeline import llm_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(id_, text="Some customer research text.", **overrides):
    source = {
        "id": id_,
        "source_type": "interview",
        "customer_name": f"Customer {id_}",
        "segment": "Enterprise",
        "date": "2026-01-01",
        "text": text,
    }
    source.update(overrides)
    return source


class RecordingFakeClient:
    """Stub Groq client for the non-mock code path. Inspects the prompt to
    return one pain point per source id it sees, like the mock fixture does,
    but going through extract.py's *real* (non-mock) call_groq branch --
    this is what exercises the rate limiter / cache-write / call-count path."""

    def __init__(self, failing_batch_ids=None):
        self.failing_batch_ids = set(failing_batch_ids or [])
        self.calls = 0
        self.chat = SimpleNamespace(completions=self)

    def create(self, model, messages, response_format=None):
        self.calls += 1
        prompt = messages[0]["content"]
        marker = "SOURCES:\n"
        sources = json.loads(prompt[prompt.rindex(marker) + len(marker):])
        batch_ids = tuple(sorted(s["id"] for s in sources))
        if batch_ids in self.failing_batch_ids:
            raise ValueError(f"simulated failure for batch {batch_ids}")
        pain_points = [
            {
                "source_id": s["id"],
                "pain_point": "Mocked pain point",
                "quote": "mocked quote",
                "use_case": "Dashboard / reporting",
            }
            for s in sources
        ]
        content = json.dumps({"pain_points": pain_points})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture(autouse=True)
def isolate_pipeline_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.delenv("DISCOVERYOS_MOCK", raising=False)
    monkeypatch.setattr(llm_utils, "_rate_limiters", {})
    yield


def _write_sources(sources):
    with open("data/sources.json", "w") as f:
        json.dump(sources, f)


def _load_extracted():
    with open("data/extracted_pain_points.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# _make_batches
# ---------------------------------------------------------------------------

class TestMakeBatches:
    def test_empty_sources_yields_no_batches(self):
        assert extract_module._make_batches([]) == []

    def test_splits_into_batches_of_five_by_default(self):
        sources = [_make_source(f"src_{i:03d}", text="short") for i in range(12)]
        batches = extract_module._make_batches(sources)
        assert [len(b) for b in batches] == [5, 5, 2]

    def test_single_source_is_its_own_batch(self):
        sources = [_make_source("src_001", text="short")]
        batches = extract_module._make_batches(sources)
        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_long_combined_text_drops_batch_size_to_three(self):
        long_text = "x" * 1000  # 5 of these = 5000 chars > threshold
        sources = [_make_source(f"src_{i:03d}", text=long_text) for i in range(5)]
        batches = extract_module._make_batches(sources)
        assert len(batches[0]) == extract_module.LONG_BATCH_SIZE

    def test_short_combined_text_keeps_full_batch_size(self):
        sources = [_make_source(f"src_{i:03d}", text="short") for i in range(5)]
        batches = extract_module._make_batches(sources)
        assert len(batches[0]) == extract_module.BATCH_SIZE

    def test_all_sources_are_covered_exactly_once(self):
        sources = [_make_source(f"src_{i:03d}", text="short") for i in range(17)]
        batches = extract_module._make_batches(sources)
        seen_ids = [s["id"] for batch in batches for s in batch]
        assert sorted(seen_ids) == sorted(s["id"] for s in sources)


class TestBatchCacheKey:
    def test_deterministic_regardless_of_source_order(self):
        batch_a = [_make_source("src_001"), _make_source("src_002")]
        batch_b = [_make_source("src_002"), _make_source("src_001")]
        assert extract_module._batch_cache_key(batch_a) == extract_module._batch_cache_key(batch_b)

    def test_different_batches_get_different_keys(self):
        batch_a = [_make_source("src_001")]
        batch_b = [_make_source("src_002")]
        assert extract_module._batch_cache_key(batch_a) != extract_module._batch_cache_key(batch_b)

    def test_key_has_extract_batch_prefix(self):
        key = extract_module._batch_cache_key([_make_source("src_001")])
        assert key.startswith("extract_batch_")


# ---------------------------------------------------------------------------
# extract_pain_points() -- mock mode
# ---------------------------------------------------------------------------

class TestExtractPainPointsMockMode:
    def test_produces_one_point_per_source_and_matches_schema(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        sources = [_make_source(f"src_{i:03d}") for i in range(1, 4)]
        _write_sources(sources)

        extract_module.extract_pain_points()
        points = _load_extracted()

        assert len(points) == 3
        for point, source in zip(points, sources):
            assert point["point_id"] == f"{source['id']}_p1"
            assert point["source_id"] == source["id"]
            assert point["source_type"] == source["source_type"]
            assert point["customer_name"] == source["customer_name"]
            assert point["segment"] == source["segment"]
            assert point["date"] == source["date"]
            assert "pain_point" in point
            assert "quote" in point
            assert "use_case" in point

    def test_handles_more_sources_than_one_batch(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        sources = [_make_source(f"src_{i:03d}") for i in range(1, 13)]  # 3 batches
        _write_sources(sources)

        extract_module.extract_pain_points()
        points = _load_extracted()

        assert {p["source_id"] for p in points} == {s["id"] for s in sources}

    def test_zero_sources_produces_empty_output(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        _write_sources([])
        extract_module.extract_pain_points()
        assert _load_extracted() == []


# ---------------------------------------------------------------------------
# extract_pain_points() -- real (non-mock) path via a stub client
# ---------------------------------------------------------------------------

class TestExtractPainPointsRealPath:
    def test_calls_client_once_per_batch(self, monkeypatch):
        sources = [_make_source(f"src_{i:03d}") for i in range(1, 8)]  # batches of 5, 2
        _write_sources(sources)
        fake_client = RecordingFakeClient()
        monkeypatch.setattr(extract_module, "client", fake_client)

        extract_module.extract_pain_points()

        assert fake_client.calls == 2
        points = _load_extracted()
        assert len(points) == 7

    def test_rerun_hits_cache_and_makes_no_new_calls(self, monkeypatch):
        sources = [_make_source(f"src_{i:03d}") for i in range(1, 8)]
        _write_sources(sources)
        fake_client = RecordingFakeClient()
        monkeypatch.setattr(extract_module, "client", fake_client)

        extract_module.extract_pain_points()
        assert fake_client.calls == 2

        extract_module.extract_pain_points()  # checkpointed rerun
        assert fake_client.calls == 2  # no new real calls

    def test_multiple_points_from_same_source_get_incrementing_point_ids(self, monkeypatch):
        sources = [_make_source("src_001")]
        _write_sources(sources)

        def fake_create(model, messages, response_format=None):
            content = json.dumps({"pain_points": [
                {"source_id": "src_001", "pain_point": "first problem", "quote": "q1", "use_case": "Billing"},
                {"source_id": "src_001", "pain_point": "second problem", "quote": "q2", "use_case": "Support"},
            ]})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        stub = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        monkeypatch.setattr(extract_module, "client", stub)

        extract_module.extract_pain_points()
        points = _load_extracted()

        assert [p["point_id"] for p in points] == ["src_001_p1", "src_001_p2"]

    def test_one_failed_batch_does_not_lose_other_batches(self, monkeypatch):
        sources = [_make_source(f"src_{i:03d}") for i in range(1, 8)]  # batches: [1..5], [6,7]
        _write_sources(sources)
        failing_ids = tuple(sorted(s["id"] for s in sources[:5]))
        fake_client = RecordingFakeClient(failing_batch_ids=[failing_ids])
        monkeypatch.setattr(extract_module, "client", fake_client)

        extract_module.extract_pain_points()  # must not raise
        points = _load_extracted()

        # only the second batch's sources made it through
        assert {p["source_id"] for p in points} == {"src_006", "src_007"}

    def test_hallucinated_source_id_in_response_is_ignored(self, monkeypatch):
        sources = [_make_source("src_001")]
        _write_sources(sources)

        def fake_create(model, messages, response_format=None):
            content = json.dumps({"pain_points": [
                {"source_id": "src_999_not_in_batch", "pain_point": "ghost", "quote": "q", "use_case": "Billing"},
            ]})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        stub = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        monkeypatch.setattr(extract_module, "client", stub)

        extract_module.extract_pain_points()  # must not raise
        assert _load_extracted() == []

    def test_real_call_count_is_reported(self, monkeypatch, capsys):
        sources = [_make_source(f"src_{i:03d}") for i in range(1, 8)]
        _write_sources(sources)
        fake_client = RecordingFakeClient()
        monkeypatch.setattr(extract_module, "client", fake_client)

        extract_module.extract_pain_points()
        out = capsys.readouterr().out
        assert "Real API calls this stage: 2" in out
