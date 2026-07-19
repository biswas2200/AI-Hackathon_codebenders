"""
TDD-style tests for app.py. Streamlit modules can be imported and their
functions called outside a real script run context ("bare mode") -- widget
calls return their default values and layout calls no-op harmlessly, which
is enough to exercise the real data-loading, pipeline-invocation, and
recompute logic without spinning up a server.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_app_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    st.cache_data.clear()
    yield


def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


SOURCE = {
    "id": "src_001", "source_type": "interview", "customer_name": "A",
    "segment": "Enterprise", "date": "2026-01-01", "text": "hello world",
}
POINT = {
    "point_id": "src_001_p1", "source_id": "src_001", "source_type": "interview",
    "customer_name": "A", "segment": "Enterprise", "date": "2026-01-01",
    "pain_point": "p", "quote": "q", "use_case": "Billing",
}


def _theme(name, impact_score, segment_breakdown, point_ids=("src_001_p1",)):
    return {
        "theme_name": name, "theme_description": "d", "frequency": len(point_ids),
        "impact_score": impact_score, "segment_breakdown": segment_breakdown,
        "use_case_breakdown": {"Billing": len(point_ids)}, "sample_quotes": ["q"],
        "customers": ["A"], "point_ids": list(point_ids), "executive_summary": "summary",
    }


# ---------------------------------------------------------------------------
# Module sanity
# ---------------------------------------------------------------------------

class TestModuleSanity:
    def test_app_module_has_expected_entrypoints(self):
        assert callable(app.main)
        assert callable(app.run_pipeline)
        assert callable(app.load_sources)
        assert callable(app.load_extracted_points)
        assert callable(app.load_themed_report)

    def test_pipeline_modules_exist_and_are_nonempty(self):
        for module in ("pipeline/extract.py", "pipeline/cluster_score.py", "pipeline/graph_builder.py"):
            path = Path(__file__).resolve().parent.parent / module
            assert path.exists(), f"{module} should exist"
            assert path.stat().st_size > 0, f"{module} should not be empty"

    def test_app_no_longer_references_gemini_api_key(self):
        source = (Path(__file__).resolve().parent.parent / "app.py").read_text()
        assert "GEMINI_API_KEY" not in source
        assert "GROQ_API_KEY" in source


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

class TestLoaders:
    def test_load_sources_returns_none_when_missing(self):
        assert app.load_sources() is None

    def test_load_sources_returns_parsed_json_when_present(self):
        _write_json("data/sources.json", [SOURCE])
        assert app.load_sources() == [SOURCE]

    def test_load_extracted_points_returns_none_when_missing(self):
        assert app.load_extracted_points() is None

    def test_load_extracted_points_returns_parsed_json_when_present(self):
        _write_json("data/extracted_pain_points.json", [POINT])
        assert app.load_extracted_points() == [POINT]

    def test_load_themed_report_returns_none_when_missing(self):
        assert app.load_themed_report() is None

    def test_load_themed_report_returns_parsed_json_when_present(self):
        themes = [_theme("T1", 5, {"Enterprise": 1})]
        _write_json("data/themed_report.json", themes)
        assert app.load_themed_report() == themes


# ---------------------------------------------------------------------------
# run_pipeline()
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_success_runs_extract_then_cluster_score_in_order(self, monkeypatch):
        calls = []

        def fake_run(cmd, capture_output, text, check):
            calls.append(cmd)
            return SimpleNamespace(stdout="ok", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(st, "rerun", lambda: None)

        app.run_pipeline()

        assert calls == [
            ["python3", "pipeline/extract.py"],
            ["python3", "pipeline/cluster_score.py"],
        ]

    def test_success_clears_cache_and_reruns(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", stderr=""))
        rerun_called = []
        monkeypatch.setattr(st, "rerun", lambda: rerun_called.append(True))

        app.run_pipeline()

        assert rerun_called == [True]

    def test_called_process_error_shows_stderr_and_does_not_raise(self, monkeypatch):
        error = subprocess.CalledProcessError(1, ["python3", "pipeline/extract.py"], stderr="boom: rate limited")

        def fake_run(*a, **k):
            raise error

        monkeypatch.setattr(subprocess, "run", fake_run)
        errors_shown = []
        monkeypatch.setattr(st, "error", lambda msg: errors_shown.append(msg))

        app.run_pipeline()  # must not raise

        assert any("boom: rate limited" in msg for msg in errors_shown)

    def test_generic_exception_shows_error_and_does_not_raise(self, monkeypatch):
        def fake_run(*a, **k):
            raise ValueError("unexpected failure")

        monkeypatch.setattr(subprocess, "run", fake_run)
        errors_shown = []
        monkeypatch.setattr(st, "error", lambda msg: errors_shown.append(msg))

        app.run_pipeline()  # must not raise

        assert any("unexpected failure" in msg for msg in errors_shown)

    def test_cached_mode_clears_only_cluster_and_narrative_cache(self, monkeypatch):
        cleared = []
        monkeypatch.setattr(app.llm_utils, "clear_cache", lambda prefixes: cleared.append(prefixes))
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", stderr=""))
        monkeypatch.setattr(st, "rerun", lambda: None)

        app.run_pipeline("cached")

        assert cleared == [["cluster_", "narratives_"]]

    def test_default_mode_is_cached(self, monkeypatch):
        cleared = []
        monkeypatch.setattr(app.llm_utils, "clear_cache", lambda prefixes: cleared.append(prefixes))
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", stderr=""))
        monkeypatch.setattr(st, "rerun", lambda: None)

        app.run_pipeline()

        assert cleared == [["cluster_", "narratives_"]]

    def test_full_mode_clears_the_entire_cache(self, monkeypatch):
        cleared = []
        monkeypatch.setattr(app.llm_utils, "clear_cache", lambda prefixes: cleared.append(prefixes))
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="", stderr=""))
        monkeypatch.setattr(st, "rerun", lambda: None)

        app.run_pipeline("full")

        assert cleared == [None]  # None = clear everything (full live re-run)


# ---------------------------------------------------------------------------
# main() -- guard clauses and live recompute
# ---------------------------------------------------------------------------

class TestMainGuardClauses:
    def test_stops_when_themed_report_missing(self, monkeypatch):
        stop_calls = []

        def fake_stop():
            stop_calls.append(True)
            raise RuntimeError("__STOP__")

        monkeypatch.setattr(st, "stop", fake_stop)

        with pytest.raises(RuntimeError, match="__STOP__"):
            app.main()

        assert stop_calls == [True]

    def test_warns_instead_of_crashing_when_graph_data_missing(self, monkeypatch):
        _write_json("data/themed_report.json", [_theme("T1", 5, {"Enterprise": 1})])
        # sources.json / extracted_pain_points.json intentionally absent

        warnings = []
        monkeypatch.setattr(st.sidebar, "warning", lambda msg: warnings.append(msg))
        monkeypatch.setattr(st, "warning", lambda msg: warnings.append(msg))

        app.main()  # must not raise

        assert any("Run pipeline first" in w or "Missing" in w for w in warnings)


class TestMainLiveRecompute:
    def test_recomputes_impact_score_from_default_segment_weights(self, monkeypatch):
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        # Stored impact_score (999) is deliberately wrong/stale to prove main()
        # recomputes it live rather than trusting the file.
        themes = [_theme("T1", impact_score=999, segment_breakdown={"Enterprise": 2, "Free": 3})]
        _write_json("data/themed_report.json", themes)

        captured = {}
        monkeypatch.setattr(st, "dataframe", lambda df, **kwargs: captured.setdefault("df", df))

        app.main()

        # default weights: Enterprise=5, Free=1 -> 2*5 + 3*1 = 13
        row = captured["df"].iloc[0]
        assert row["Impact Score"] == 13

    def test_resorts_themes_by_recomputed_score_not_stored_score(self, monkeypatch):
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        themes = [
            # stored scores say "Low Recompute" outranks "High Recompute";
            # default-weight recompute should flip that order.
            _theme("Low Recompute", impact_score=999, segment_breakdown={"Free": 1}),
            _theme("High Recompute", impact_score=1, segment_breakdown={"Enterprise": 4}),
        ]
        _write_json("data/themed_report.json", themes)

        captured = {}
        monkeypatch.setattr(st, "dataframe", lambda df, **kwargs: captured.setdefault("df", df))

        app.main()

        ordered_names = list(captured["df"]["Theme"])
        assert ordered_names == ["High Recompute", "Low Recompute"]

    def test_other_unclustered_pinned_last_in_the_live_resort(self, monkeypatch):
        # Even with a recomputed score high enough to top the list, the
        # catch-all must never surface as "Top Priority" in the report.
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        themes = [
            _theme("Other / Unclustered", impact_score=1, segment_breakdown={"Enterprise": 50}),
            _theme("Real Theme A", impact_score=1, segment_breakdown={"Enterprise": 2}),
            _theme("Real Theme B", impact_score=1, segment_breakdown={"Free": 1}),
        ]
        _write_json("data/themed_report.json", themes)

        captured = {}
        monkeypatch.setattr(st, "dataframe", lambda df, **kwargs: captured.setdefault("df", df))

        app.main()

        ordered_names = list(captured["df"]["Theme"])
        assert ordered_names[-1] == "Other / Unclustered"
        assert ordered_names[0] == "Real Theme A"  # highest recomputed real score

    def test_runs_end_to_end_without_error_when_all_data_present(self):
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        _write_json("data/themed_report.json", [_theme("T1", 5, {"Enterprise": 1})])

        app.main()  # must not raise

    def test_graph_iframe_height_covers_canvas_plus_header(self, monkeypatch):
        """The graph iframe is rendered with scrolling=False, so anything
        past its declared height is unreachable -- not just off-screen,
        genuinely unreachable. It must cover the full page graph_builder.py
        returns (750px canvas + the search/zoom toolbar's header, which
        wraps to a second line on narrower viewports), not just the canvas
        alone, or the bottom of the graph is silently clipped with no way
        to scroll to it (confirmed against a real running instance -- a
        950px budget still clipped ~13px at a 956px-wide viewport)."""
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        _write_json("data/themed_report.json", [_theme("T1", 5, {"Enterprise": 1})])

        iframe_calls = []
        html_iframe_calls = []
        
        # Capture both iframe and html_iframe calls
        real_iframe = st.iframe
        monkeypatch.setattr(st, "iframe", lambda **kwargs: iframe_calls.append(kwargs))
        monkeypatch.setattr(app, "html_iframe", lambda *args, **kwargs: html_iframe_calls.append((args, kwargs)))

        app.main()

        # Verify html_iframe was called with correct height and scrolling parameters
        assert len(html_iframe_calls) > 0, "html_iframe should be called"
        args, kwargs = html_iframe_calls[0]
        assert kwargs.get("height", 0) >= 1000, f"Expected height >= 1000, got {kwargs.get('height')}"
        assert kwargs.get("scrolling") is False, f"Expected scrolling=False, got {kwargs.get('scrolling')}"



    def test_dark_mode_toggle_default_passes_dark_theme_to_graph(self, monkeypatch):
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        _write_json("data/themed_report.json", [_theme("T1", 5, {"Enterprise": 1})])

        captured = {}
        monkeypatch.setattr(app, "build_graph_html", lambda *a, **k: captured.update(k) or "<html></html>")

        app.main()

        assert captured.get("theme") == "dark"  # toggle defaults to dark

    def test_light_mode_toggle_passes_light_theme_to_graph(self, monkeypatch):
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        _write_json("data/themed_report.json", [_theme("T1", 5, {"Enterprise": 1})])

        # Force the dark-mode toggle off -> light theme.
        monkeypatch.setattr(st.sidebar, "toggle", lambda *a, **k: False)
        captured = {}
        monkeypatch.setattr(app, "build_graph_html", lambda *a, **k: captured.update(k) or "<html></html>")

        app.main()

        assert captured.get("theme") == "light"


# ---------------------------------------------------------------------------
# apply_theme() -- light-mode CSS must cover the sidebar's own background,
# not just the (transparent) main container
# ---------------------------------------------------------------------------

class TestApplyTheme:
    def test_dark_theme_injects_no_css(self, monkeypatch):
        calls = []
        monkeypatch.setattr(st, "markdown", lambda *a, **k: calls.append(a))
        app.apply_theme("dark")
        assert calls == []

    def test_light_theme_sets_a_background_on_the_element_that_actually_paints_it(self, monkeypatch):
        """stAppViewContainer/stMain are transparent in Streamlit 1.59 --
        the real background lives on stApp/body. A rule that only targets
        stAppViewContainer visibly does nothing (confirmed by inspecting a
        live instance: appBg/mainBg both computed as rgba(0,0,0,0))."""
        calls = []
        monkeypatch.setattr(st, "markdown", lambda *a, **k: calls.append(a[0]))
        app.apply_theme("light")
        css = calls[0]
        assert '[data-testid="stApp"]' in css
        assert "background-color" in css

    def test_light_theme_gives_the_sidebar_its_own_background(self, monkeypatch):
        """stSidebar paints its own separate background and is a descendant
        of stAppViewContainer -- a text-color-only rule scoped to "under
        stAppViewContainer" also matches sidebar text without changing the
        sidebar's (unrelated) background, producing dark-on-dark unreadable
        text. The sidebar needs its own explicit background rule."""
        calls = []
        monkeypatch.setattr(st, "markdown", lambda *a, **k: calls.append(a[0]))
        app.apply_theme("light")
        css = calls[0]
        assert '[data-testid="stSidebar"]' in css
        # the sidebar rule block itself must set a background, not just be
        # incidentally covered by a broader text-color selector
        sidebar_rule_start = css.index('[data-testid="stSidebar"]')
        sidebar_rule_block = css[sidebar_rule_start:sidebar_rule_start + 200]
        assert "background-color" in sidebar_rule_block


# ---------------------------------------------------------------------------
# Top Priority KPI -- must show the full theme name, not truncate it
# ---------------------------------------------------------------------------

class TestTopPriorityDisplay:
    def test_long_theme_name_is_not_truncated(self, monkeypatch):
        """st.metric's value is single-line with an ellipsis once it
        overflows the column -- fine for the other three KPIs (always short
        integers) but a theme name is unbounded length and was getting cut
        off ("Security and Compli..."). The replacement custom block must
        render the full name somewhere in its markdown output."""
        long_name = "Security and Compliance Concerns Across Every Enterprise Segment"
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        _write_json("data/themed_report.json", [_theme(long_name, 5, {"Enterprise": 1})])

        markdown_calls = []
        real_markdown = st.markdown
        monkeypatch.setattr(st, "markdown", lambda *a, **k: (markdown_calls.append(a[0] if a else ""), real_markdown(*a, **k))[0])

        app.main()

        assert any(long_name in call for call in markdown_calls)

    def test_theme_name_with_html_special_characters_is_escaped(self, monkeypatch):
        """Rendered via unsafe_allow_html=True -- an unescaped theme name
        containing HTML-significant characters would break the markup or
        inject markup, since it's LLM-generated content."""
        tricky_name = "Exports & <Reports> Break"
        _write_json("data/sources.json", [SOURCE])
        _write_json("data/extracted_pain_points.json", [POINT])
        _write_json("data/themed_report.json", [_theme(tricky_name, 5, {"Enterprise": 1})])

        markdown_calls = []
        real_markdown = st.markdown
        monkeypatch.setattr(st, "markdown", lambda *a, **k: (markdown_calls.append(a[0] if a else ""), real_markdown(*a, **k))[0])

        app.main()

        assert any("&amp;" in call and "&lt;Reports&gt;" in call for call in markdown_calls)
        assert not any(tricky_name in call for call in markdown_calls)  # raw, unescaped form must not appear
