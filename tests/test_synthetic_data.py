"""
TDD-style tests for data/generate_synthetic_data.py. Runs in an isolated
tmp directory so it never depends on (or clobbers) a real data/sources.json
left over from a previous run.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))
from generate_synthetic_data import generate_synthetic_data  # noqa: E402

VALID_SOURCE_TYPES = {"interview", "survey", "support_ticket"}
VALID_SEGMENTS = {"Enterprise", "Mid-Market", "SMB", "Free"}


@pytest.fixture()
def sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    generate_synthetic_data()
    with open("data/sources.json") as f:
        return json.load(f)


class TestOutputFile:
    def test_sources_json_is_written(self, sources):
        assert Path("data/sources.json").exists()

    def test_at_least_80_sources(self, sources):
        # Grown from the original ~48 to ~90 for a richer-looking demo
        # (Rev 7). Floor at 80 to lock in the larger volume without being
        # brittle about the exact count.
        assert len(sources) >= 80

    def test_ids_are_unique(self, sources):
        ids = [s["id"] for s in sources]
        assert len(ids) == len(set(ids))

    def test_ids_follow_src_nnn_format(self, sources):
        for s in sources:
            assert s["id"].startswith("src_")
            assert s["id"][4:].isdigit()


class TestSchema:
    def test_required_fields_present(self, sources):
        required = {"id", "source_type", "customer_name", "segment", "date", "text"}
        for s in sources:
            assert required.issubset(s.keys())

    def test_source_type_is_valid(self, sources):
        for s in sources:
            assert s["source_type"] in VALID_SOURCE_TYPES

    def test_segment_is_valid(self, sources):
        for s in sources:
            assert s["segment"] in VALID_SEGMENTS

    def test_date_is_iso_format(self, sources):
        for s in sources:
            datetime.strptime(s["date"], "%Y-%m-%d")  # raises if malformed

    def test_text_is_nonempty(self, sources):
        for s in sources:
            assert s["text"].strip()


class TestDistribution:
    def test_all_four_segments_represented(self, sources):
        segments = {s["segment"] for s in sources}
        assert segments == VALID_SEGMENTS

    def test_all_three_source_types_represented(self, sources):
        types = {s["source_type"] for s in sources}
        assert types == VALID_SOURCE_TYPES

    def test_recurring_export_problem_appears_multiple_times(self, sources):
        texts = [s["text"].lower() for s in sources]
        export_count = sum(1 for t in texts if "export" in t or "download" in t)
        assert export_count >= 3

    def test_recurring_integration_problem_appears_multiple_times(self, sources):
        texts = [s["text"].lower() for s in sources]
        integration_count = sum(1 for t in texts if "integrat" in t or "sync" in t)
        assert integration_count >= 2


class TestCrossVocabularyStressTestCase:
    """Section 4's deliberate pair: an Enterprise source describing the
    export-timeout failure in technical language, and a Free/SMB source
    describing the *same* underlying failure in casual language with
    almost no shared keywords. This is what makes the clustering
    root-cause-vs-vocabulary check in cluster_score.py meaningful."""

    def test_formal_enterprise_technical_description_exists(self, sources):
        formal = [
            s for s in sources
            if s["segment"] == "Enterprise"
            and any(kw in s["text"].lower() for kw in ("40k", "timeout", "bulk export", "50k rows"))
        ]
        assert formal, "expected a technical/formal Enterprise description of the export failure"

    def test_casual_free_or_smb_description_exists(self, sources):
        casual = [
            s for s in sources
            if s["segment"] in ("Free", "SMB")
            and any(kw in s["text"].lower() for kw in ("spinner", "spins", "forever", "broken every time"))
        ]
        assert casual, "expected a casual Free/SMB description of the same export failure"


class TestRunIsIdempotentAcrossInvocations:
    def test_running_twice_overwrites_rather_than_appends(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        generate_synthetic_data()
        with open("data/sources.json") as f:
            first_count = len(json.load(f))

        generate_synthetic_data()
        with open("data/sources.json") as f:
            second_count = len(json.load(f))

        assert first_count == second_count
