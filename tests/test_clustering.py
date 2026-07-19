"""
TDD-style tests for pipeline/cluster_score.py: impact scoring, the
orphaned-point safety net, point reconciliation, and the single-batched-
narrative-call requirement (one call for every theme, not one per theme).
No real network calls are made anywhere in this file.
"""

import json
import os
from types import SimpleNamespace

os.environ.setdefault("GROQ_API_KEY", "test-key-for-unit-tests")

import pytest

from pipeline import cluster_score as cluster_module
from pipeline import llm_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_point(point_id, segment="Enterprise", use_case="Dashboard / reporting", quote="a quote"):
    source_id = point_id.split("_p")[0]
    return {
        "point_id": point_id,
        "source_id": source_id,
        "source_type": "interview",
        "customer_name": f"Customer {source_id}",
        "segment": segment,
        "date": "2026-01-01",
        "pain_point": "Some pain point",
        "quote": quote,
        "use_case": use_case,
    }


class RecordingFakeClient:
    """Dispatches by prompt content: clustering prompts contain 'PAIN
    POINTS:', narrative prompts contain 'THEMES:'. Records which stage was
    called, in order, so tests can assert call counts and ordering."""

    def __init__(self, cluster_response=None, narrative_response=None,
                 cluster_error=None, narrative_error=None):
        self.calls = []
        self.chat = SimpleNamespace(completions=self)
        self.cluster_response = cluster_response
        self.narrative_response = narrative_response
        self.cluster_error = cluster_error
        self.narrative_error = narrative_error

    def create(self, model, messages, response_format=None):
        prompt = messages[0]["content"]
        if "PAIN POINTS:" in prompt:
            self.calls.append("cluster")
            if self.cluster_error:
                raise self.cluster_error
            content = self.cluster_response
        elif "THEMES:" in prompt:
            self.calls.append("narrative")
            if self.narrative_error:
                raise self.narrative_error
            content = self.narrative_response
        else:
            raise AssertionError(f"unrecognized prompt shape: {prompt[:80]!r}")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture(autouse=True)
def isolate_pipeline_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.delenv("DISCOVERYOS_MOCK", raising=False)
    monkeypatch.setattr(llm_utils, "_rate_limiters", {})
    yield


def _write_extracted(points):
    with open("data/extracted_pain_points.json", "w") as f:
        json.dump(points, f)


def _load_themed_report():
    with open("data/themed_report.json") as f:
        return json.load(f)


def _cluster_response(theme_specs):
    """theme_specs: list of (theme_name, description, [point_ids])"""
    return json.dumps({"themes": [
        {"theme_name": name, "theme_description": desc, "point_ids": ids}
        for name, desc, ids in theme_specs
    ]})


def _narrative_response(theme_names):
    return json.dumps({"summaries": [
        {"theme_name": name, "executive_summary": f"Narrative for {name}."}
        for name in theme_names
    ]})


# ---------------------------------------------------------------------------
# Prompt template regression guards
# ---------------------------------------------------------------------------

class TestPromptTemplates:
    def test_clustering_prompt_mentions_root_cause_over_keywords(self):
        assert "root cause" in cluster_module.CLUSTERING_PROMPT_TEMPLATE.lower()

    def test_clustering_prompt_contains_json_keyword(self):
        # Groq's json_object response_format requires "json" somewhere in the prompt.
        assert "json" in cluster_module.CLUSTERING_PROMPT_TEMPLATE.lower()

    def test_narrative_prompt_contains_json_keyword(self):
        assert "json" in cluster_module.NARRATIVE_PROMPT_TEMPLATE.lower()


# ---------------------------------------------------------------------------
# _hash_ids / _build_theme (unit level)
# ---------------------------------------------------------------------------

class TestHashIds:
    def test_deterministic_regardless_of_order(self):
        assert cluster_module._hash_ids(["b", "a", "c"]) == cluster_module._hash_ids(["a", "c", "b"])

    def test_different_id_sets_hash_differently(self):
        assert cluster_module._hash_ids(["a"]) != cluster_module._hash_ids(["b"])


class TestBuildTheme:
    def test_computes_impact_score_from_segment_weights(self):
        points_by_id = {
            "p1": _make_point("src_001_p1", segment="Enterprise"),  # weight 5
            "p2": _make_point("src_002_p1", segment="Free"),        # weight 1
        }
        theme = cluster_module._build_theme("T", "desc", ["p1", "p2"], points_by_id)
        assert theme["impact_score"] == 6

    def test_segment_and_use_case_breakdowns(self):
        points_by_id = {
            "p1": _make_point("src_001_p1", segment="Enterprise", use_case="Billing"),
            "p2": _make_point("src_002_p1", segment="Enterprise", use_case="Support"),
        }
        theme = cluster_module._build_theme("T", "desc", ["p1", "p2"], points_by_id)
        assert theme["segment_breakdown"] == {"Enterprise": 2}
        assert theme["use_case_breakdown"] == {"Billing": 1, "Support": 1}

    def test_sample_quotes_capped_at_five(self):
        points_by_id = {
            f"p{i}": _make_point(f"src_{i:03d}_p1", quote=f"quote {i}") for i in range(8)
        }
        theme = cluster_module._build_theme("T", "desc", list(points_by_id.keys()), points_by_id)
        assert len(theme["sample_quotes"]) == 5

    def test_unknown_point_ids_are_dropped_silently(self):
        points_by_id = {"p1": _make_point("src_001_p1")}
        theme = cluster_module._build_theme("T", "desc", ["p1", "does_not_exist"], points_by_id)
        assert theme["point_ids"] == ["p1"]
        assert theme["frequency"] == 1

    def test_customers_are_sorted(self):
        points_by_id = {
            "p1": {**_make_point("src_001_p1"), "customer_name": "Zed"},
            "p2": {**_make_point("src_002_p1"), "customer_name": "Anna"},
        }
        theme = cluster_module._build_theme("T", "desc", ["p1", "p2"], points_by_id)
        assert theme["customers"] == ["Anna", "Zed"]


# ---------------------------------------------------------------------------
# cluster_and_score() -- mock mode
# ---------------------------------------------------------------------------

class TestClusterAndScoreMockMode:
    def test_output_matches_schema_contract(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [_make_point(f"src_{i:03d}_p1") for i in range(1, 6)]
        _write_extracted(points)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()

        assert isinstance(themes, list)
        required_keys = {
            "theme_name", "theme_description", "frequency", "impact_score",
            "segment_breakdown", "use_case_breakdown", "sample_quotes",
            "customers", "point_ids", "executive_summary",
        }
        for theme in themes:
            assert required_keys.issubset(theme.keys())

    def test_dropped_points_land_in_other_unclustered_theme(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [_make_point(f"src_{i:03d}_p1") for i in range(1, 6)]  # 5 points
        _write_extracted(points)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()

        other = next((t for t in themes if t["theme_name"] == "Other / Unclustered"), None)
        assert other is not None
        assert other["frequency"] == 2  # the mock fixture drops exactly 2

    def test_point_reconciliation_holds_even_with_orphans(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [_make_point(f"src_{i:03d}_p1") for i in range(1, 9)]
        _write_extracted(points)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()

        assert sum(t["frequency"] for t in themes) == len(points)

    def test_real_themes_sorted_descending_by_impact_score(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [_make_point(f"src_{i:03d}_p1", segment="Enterprise") for i in range(1, 9)]
        _write_extracted(points)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()
        # "Other / Unclustered" is pinned last regardless of score, so only
        # the real themes must be in descending order.
        real_scores = [t["impact_score"] for t in themes if t["theme_name"] != "Other / Unclustered"]
        assert real_scores == sorted(real_scores, reverse=True)

    def test_other_unclustered_always_sorts_last_even_with_top_score(self, monkeypatch):
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        # Many points -> the mock's 2 dropped ids become "Other", but real
        # themes hold the rest. Give the dropped points the heaviest segment
        # so "Other" would rank #1 on raw score if not pinned last.
        points = [_make_point("src_001_p1", segment="Enterprise"),
                  _make_point("src_002_p1", segment="Enterprise")]
        points += [_make_point(f"src_{i:03d}_p1", segment="Free") for i in range(3, 8)]
        _write_extracted(points)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()
        other = next((t for t in themes if t["theme_name"] == "Other / Unclustered"), None)
        assert other is not None
        assert themes[-1]["theme_name"] == "Other / Unclustered"
        assert themes[0]["theme_name"] != "Other / Unclustered"

    def test_no_orphans_when_all_points_fit_in_two_or_fewer(self, monkeypatch):
        # mock fixture drops the first 2 ids; with exactly 2 points that's everything
        monkeypatch.setenv("DISCOVERYOS_MOCK", "1")
        points = [_make_point("src_001_p1"), _make_point("src_002_p1")]
        _write_extracted(points)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()
        total = sum(t["frequency"] for t in themes)
        assert total == 2  # still fully reconciled via the orphan theme


# ---------------------------------------------------------------------------
# cluster_and_score() -- real (non-mock) path via a stub client
# ---------------------------------------------------------------------------

class TestClusterAndScoreRealPath:
    def test_exactly_two_calls_regardless_of_theme_count(self, monkeypatch):
        """Narrative generation must be ONE batched call covering every
        theme, not one call per theme -- this is the Rev 3/Rev 4 call-count
        win the spec is built around."""
        points = [_make_point(f"src_{i:03d}_p1") for i in range(1, 10)]
        _write_extracted(points)

        theme_specs = [
            ("Theme A", "desc a", ["src_001_p1", "src_002_p1", "src_003_p1"]),
            ("Theme B", "desc b", ["src_004_p1", "src_005_p1", "src_006_p1"]),
            ("Theme C", "desc c", ["src_007_p1", "src_008_p1", "src_009_p1"]),
        ]
        fake_client = RecordingFakeClient(
            cluster_response=_cluster_response(theme_specs),
            narrative_response=_narrative_response(["Theme A", "Theme B", "Theme C"]),
        )
        monkeypatch.setattr(cluster_module, "client", fake_client)

        cluster_module.cluster_and_score()

        assert fake_client.calls == ["cluster", "narrative"]

    def test_executive_summaries_matched_back_by_theme_name(self, monkeypatch):
        points = [_make_point("src_001_p1"), _make_point("src_002_p1")]
        _write_extracted(points)

        fake_client = RecordingFakeClient(
            cluster_response=_cluster_response([("Only Theme", "desc", ["src_001_p1", "src_002_p1"])]),
            narrative_response=_narrative_response(["Only Theme"]),
        )
        monkeypatch.setattr(cluster_module, "client", fake_client)

        cluster_module.cluster_and_score()
        themes = _load_themed_report()

        assert themes[0]["executive_summary"] == "Narrative for Only Theme."

    def test_rerun_hits_cache_and_makes_no_new_calls(self, monkeypatch):
        points = [_make_point("src_001_p1"), _make_point("src_002_p1")]
        _write_extracted(points)

        fake_client = RecordingFakeClient(
            cluster_response=_cluster_response([("Only Theme", "desc", ["src_001_p1", "src_002_p1"])]),
            narrative_response=_narrative_response(["Only Theme"]),
        )
        monkeypatch.setattr(cluster_module, "client", fake_client)

        cluster_module.cluster_and_score()
        assert len(fake_client.calls) == 2

        cluster_module.cluster_and_score()  # checkpointed rerun
        assert len(fake_client.calls) == 2  # no new calls

    def test_narrative_parse_failure_falls_back_without_crashing(self, monkeypatch):
        points = [_make_point("src_001_p1")]
        _write_extracted(points)

        fake_client = RecordingFakeClient(
            cluster_response=_cluster_response([("Only Theme", "desc", ["src_001_p1"])]),
            narrative_response="not valid json",
        )
        monkeypatch.setattr(cluster_module, "client", fake_client)

        cluster_module.cluster_and_score()  # must not raise
        themes = _load_themed_report()
        assert themes[0]["executive_summary"]  # fallback text, non-empty

    def test_clustering_parse_failure_exits_cleanly(self, monkeypatch):
        points = [_make_point("src_001_p1")]
        _write_extracted(points)

        fake_client = RecordingFakeClient(cluster_response="not valid json")
        monkeypatch.setattr(cluster_module, "client", fake_client)

        with pytest.raises(SystemExit):
            cluster_module.cluster_and_score()

    def test_combined_real_call_count_is_reported(self, monkeypatch, capsys):
        points = [_make_point("src_001_p1"), _make_point("src_002_p1")]
        _write_extracted(points)

        # simulate extract.py already having made 8 real calls this run
        llm_utils.reset_call_count()
        for _ in range(8):
            llm_utils._increment_call_count()

        fake_client = RecordingFakeClient(
            cluster_response=_cluster_response([("Only Theme", "desc", ["src_001_p1", "src_002_p1"])]),
            narrative_response=_narrative_response(["Only Theme"]),
        )
        monkeypatch.setattr(cluster_module, "client", fake_client)

        cluster_module.cluster_and_score()
        out = capsys.readouterr().out

        assert "Real API calls this stage: 2" in out
        assert "Combined real API calls (extract + cluster): 10" in out
