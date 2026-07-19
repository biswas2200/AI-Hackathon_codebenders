"""
TDD-style tests for pipeline/graph_builder.py: three-tier node structure
(theme -> pain point -> source), no tier-skipping edges, source-node
dedup, and per-type coloring. A spy stands in for pyvis.network.Network so
we can assert on exactly which nodes/edges were added, not just grep the
final HTML string.
"""

import pytest

from pipeline import graph_builder


class SpyNetwork:
    """Records add_node/add_edge calls; swaps in for pyvis's Network."""

    last_instance = None

    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs
        self.nodes = []  # list of dicts: {"id":..., **kwargs}
        self.edges = []  # list of (source, target, kwargs)
        SpyNetwork.last_instance = self

    def add_node(self, node_id, **kwargs):
        self.nodes.append({"id": node_id, **kwargs})

    def add_edge(self, source, target, **kwargs):
        self.edges.append((source, target, kwargs))

    def show_buttons(self, *args, **kwargs):
        pass

    def set_options(self, *args, **kwargs):
        pass

    def generate_html(self, *args, **kwargs):
        return "<html><body>spy network</body></html>"

    @property
    def node_ids(self):
        return [n["id"] for n in self.nodes]


@pytest.fixture(autouse=True)
def spy_network(monkeypatch):
    monkeypatch.setattr(graph_builder, "Network", SpyNetwork)
    yield


def _fixture_data():
    sources = [
        {"id": "src_001", "source_type": "interview", "text": "a" * 300, "segment": "Enterprise", "date": "2026-01-01"},
        {"id": "src_002", "source_type": "survey", "text": "short", "segment": "SMB", "date": "2026-01-02"},
        {"id": "src_003", "source_type": "support_ticket", "text": "ticket text", "segment": "Free", "date": "2026-01-03"},
    ]
    points = [
        {"point_id": "src_001_p1", "pain_point": "Exports timeout on large datasets", "quote": "times out",
         "use_case": "Exporting data", "customer_name": "Dana Park", "segment": "Enterprise", "source_id": "src_001"},
        {"point_id": "src_001_p2", "pain_point": "No progress indicator during export", "quote": "no feedback",
         "use_case": "Exporting data", "customer_name": "Dana Park", "segment": "Enterprise", "source_id": "src_001"},
        {"point_id": "src_002_p1", "pain_point": "Confusing onboarding wizard", "quote": "got lost",
         "use_case": "Onboarding / setup", "customer_name": "Sam Lee", "segment": "SMB", "source_id": "src_002"},
        {"point_id": "src_003_p1", "pain_point": "Support response is slow", "quote": "waited days",
         "use_case": "Support", "customer_name": "Priya Nair", "segment": "Free", "source_id": "src_003"},
    ]
    themes = [
        {"theme_name": "Export Performance", "theme_description": "Issues with exporting data",
         "frequency": 2, "impact_score": 15, "segment_breakdown": {"Enterprise": 2},
         "point_ids": ["src_001_p1", "src_001_p2"]},
        {"theme_name": "Onboarding Friction", "theme_description": "Setup is confusing",
         "frequency": 1, "impact_score": 3, "segment_breakdown": {"SMB": 1},
         "point_ids": ["src_002_p1"]},
        {"theme_name": "Support Delays", "theme_description": "Slow support responses",
         "frequency": 1, "impact_score": 1, "segment_breakdown": {"Free": 1},
         "point_ids": ["src_003_p1"]},
    ]
    return sources, points, themes


class TestRealPyvisIntegration:
    """No spy here -- this is the one test that exercises the actual
    installed pyvis Network class, to catch constructor/kwarg mismatches
    (e.g. a `physics` kwarg that a given pyvis version doesn't accept) that
    a spy-based test can't see because it never touches the real API."""

    def test_builds_against_real_pyvis_network(self, monkeypatch):
        monkeypatch.undo()  # restore the real pyvis.network.Network for this test only

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        assert "<html" in html.lower()
        assert "Export Performance" in html

    def test_html_is_standalone_with_no_external_resource_dependencies(self, monkeypatch):
        """cdn_resources must be 'in_line' -- 'local' (the pyvis default)
        emits a <script src="lib/bindings/utils.js"> relative path that
        doesn't exist once this HTML is embedded as a string, and 'remote'
        depends on CDN access that isn't guaranteed (or wanted) for an
        offline demo. Either misconfiguration renders a blank graph panel
        with no visible error."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        assert "lib/bindings" not in html
        assert "cdnjs.cloudflare.com" not in html
        assert "<script>" in html or "<script " in html  # vis-network JS actually inlined

    def test_html_fits_camera_to_graph_after_stabilization(self, monkeypatch):
        """barnes_hut repulsion spreads nodes across a coordinate range far
        larger than the canvas. Without an explicit fit-to-view once
        physics settles, the camera stays at its default 1:1 view and the
        panel renders blank -- nodes exist, just thousands of pixels
        outside the visible area. Confirmed by inspecting a real browser's
        network.getPositions() against network.getViewPosition()."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        assert "stabilizationIterationsDone" in html
        assert "network.fit(" in html
        assert "physics: false" in html  # freeze after settling, or the view goes stale again

    def test_html_forces_canvas_buffer_resize_before_fit(self, monkeypatch):
        """vis-network's <canvas> pixel buffer (width/height attributes) is
        independent of its CSS display size, and its own resize detection
        never fires inside a Streamlit st.components.v1.html() iframe --
        confirmed in a real browser: canvas.width/height stayed 0 forever
        even after fit() computed a correct non-1 scale (network.setSize()
        does not reliably sync it in this context either -- verified by
        instrumenting the live page: canvas dimensions were still 0x0
        immediately after setSize()+redraw()). Set canvas.width/height
        directly from the container's measured rect before every fit."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        assert "canvasEl.width = rect.width" in html
        assert "canvasEl.height = rect.height" in html
        assert "network.redraw()" in html
        # the direct assignment must happen before fit() within doFit(), not after
        assert html.index("canvasEl.width = rect.width") < html.index("network.fit(")

    def test_fit_pulls_back_a_margin_so_labels_are_not_clipped(self, monkeypatch):
        """fit() only accounts for node geometry, not label text -- a node
        sitting exactly at the computed edge still has its label extending
        past it, clipped by the canvas boundary (confirmed visually against
        a real running instance: outermost node labels were cut off at the
        panel edge). Every fit() call must be followed by a moveTo() that
        pulls the scale back a bit, in both the automatic fit and the
        "Fit" button's handler."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        margin_calls = html.count("network.getScale() * 0.82")
        assert margin_calls >= 2  # doFit() and the Fit button's click handler

    def test_zoom_is_clamped_not_unbounded(self, monkeypatch):
        """Scroll-zoom must not be able to zoom out to a vanishing point or
        in to a meaningless blowup -- the 'zoom' handler clamps getScale()
        against MIN_SCALE/MAX_SCALE (derived from the fitted scale) on
        every zoom event, correcting out-of-range values via moveTo()."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        assert 'network.on("zoom"' in html
        assert "MIN_SCALE" in html and "MAX_SCALE" in html
        assert "clampScale" in html

    def test_built_in_navigation_buttons_disabled(self, monkeypatch):
        """pyvis's built-in nav buttons render with no visible icon once
        cdn_resources='in_line' breaks their sprite reference -- they must
        stay off in favor of the custom zoom/search controls below."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        assert '"navigationButtons": false' in html

    def test_light_and_dark_themes_differ_and_default_is_dark(self, monkeypatch):
        """The graph must follow the dashboard's light/dark toggle: dark
        uses the #111318 canvas + light font, light uses a pale canvas +
        dark font. Node *fill* colors (theme orange etc.) are shared and
        must appear in both. Default (no theme arg) stays dark."""
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        dark = graph_builder.build_graph_html(sources, points, themes, theme="dark")
        light = graph_builder.build_graph_html(sources, points, themes, theme="light")
        default = graph_builder.build_graph_html(sources, points, themes)

        assert "#111318" in dark and "#111318" not in light
        assert "#f7f7f9" in light and "#f7f7f9" not in dark
        assert "#1a1a1a" in light  # dark label font in light mode
        assert "#111318" in default  # default is dark
        # shared node fill colors present regardless of theme
        assert "#F2A65A" in dark and "#F2A65A" in light

    def test_unknown_theme_falls_back_to_dark(self, monkeypatch):
        monkeypatch.undo()
        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes, theme="banana")
        assert "#111318" in html

    def test_custom_zoom_and_search_controls_present(self, monkeypatch):
        monkeypatch.undo()

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        for control_id in (
            "graph-search-input", "graph-search-prev", "graph-search-next",
            "graph-search-count", "graph-zoom-in", "graph-zoom-out", "graph-zoom-fit",
        ):
            assert f'id="{control_id}"' in html

    def test_search_index_covers_every_node_with_full_searchable_text(self, monkeypatch):
        """The search box matches against an explicit SEARCH_INDEX (not
        vis-network's internal DataSet), so what's searchable is exactly
        the full pain_point/quote/customer/source text -- not just the
        30-char-truncated on-canvas label."""
        monkeypatch.undo()
        import json as jsonlib

        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)

        start = html.index("var SEARCH_INDEX = ") + len("var SEARCH_INDEX = ")
        end = html.index(";", start)
        index = jsonlib.loads(html[start:end])
        indexed_ids = {item["id"] for item in index}

        assert indexed_ids == (
            {t["theme_name"] for t in themes}
            | {p["point_id"] for p in points}
            | {s["id"] for s in sources}
        )
        # full quote text must be searchable, not just the truncated label
        point_entry = next(item for item in index if item["id"] == "src_001_p1")
        assert "times out" in point_entry["text"]
        assert "Dana Park" in point_entry["text"]


class TestBuildGraphHtmlBasics:
    def test_returns_nonempty_html_string(self):
        sources, points, themes = _fixture_data()
        html = graph_builder.build_graph_html(sources, points, themes)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_empty_inputs_do_not_crash(self):
        html = graph_builder.build_graph_html([], [], [])
        assert isinstance(html, str)
        assert SpyNetwork.last_instance.nodes == []
        assert SpyNetwork.last_instance.edges == []


class TestNodeTiers:
    def test_one_node_per_theme_point_and_source(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        node_ids = SpyNetwork.last_instance.node_ids

        for t in themes:
            assert t["theme_name"] in node_ids
        for p in points:
            assert p["point_id"] in node_ids
        for s in sources:
            assert s["id"] in node_ids

    def test_theme_nodes_use_theme_color(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        theme_nodes = {n["id"]: n for n in SpyNetwork.last_instance.nodes if n["id"] in {t["theme_name"] for t in themes}}
        for node in theme_nodes.values():
            assert node["color"] == "#F2A65A"

    def test_pain_point_nodes_use_point_color(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        point_ids = {p["point_id"] for p in points}
        point_nodes = {n["id"]: n for n in SpyNetwork.last_instance.nodes if n["id"] in point_ids}
        for node in point_nodes.values():
            assert node["color"] == "#8892A6"

    def test_source_nodes_colored_by_source_type(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        by_id = {n["id"]: n for n in SpyNetwork.last_instance.nodes}
        assert by_id["src_001"]["color"] == "#5B8DEF"  # interview
        assert by_id["src_002"]["color"] == "#4CAF7D"  # survey
        assert by_id["src_003"]["color"] == "#B565D9"  # support_ticket

    def test_theme_node_size_scales_with_impact_score(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        by_id = {n["id"]: n for n in SpyNetwork.last_instance.nodes}
        high_impact = by_id["Export Performance"]["size"]  # impact_score 15
        low_impact = by_id["Support Delays"]["size"]  # impact_score 1
        assert high_impact > low_impact

    def test_source_node_referenced_by_multiple_points_is_not_duplicated(self):
        sources, points, themes = _fixture_data()  # src_001 has two points
        graph_builder.build_graph_html(sources, points, themes)
        node_ids = SpyNetwork.last_instance.node_ids
        assert node_ids.count("src_001") == 1


class TestEdgeTiers:
    def test_no_edge_skips_a_tier(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)

        theme_names = {t["theme_name"] for t in themes}
        point_ids = {p["point_id"] for p in points}
        source_ids = {s["id"] for s in sources}

        for a, b, _ in SpyNetwork.last_instance.edges:
            if a in theme_names:
                assert b in point_ids, f"theme edge should land on a pain point, got {b!r}"
            elif a in point_ids:
                assert b in source_ids, f"pain point edge should land on a source, got {b!r}"
            else:
                pytest.fail(f"edge originates from unexpected node: {a!r}")

    def test_every_theme_point_id_produces_a_theme_to_point_edge(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        edges = {(a, b) for a, b, _ in SpyNetwork.last_instance.edges}
        for theme in themes:
            for pid in theme["point_ids"]:
                assert (theme["theme_name"], pid) in edges

    def test_every_point_produces_a_point_to_source_edge(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        edges = {(a, b) for a, b, _ in SpyNetwork.last_instance.edges}
        for point in points:
            assert (point["point_id"], point["source_id"]) in edges


class TestTooltips:
    def test_pain_point_tooltip_includes_quote_and_customer(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        node = next(n for n in SpyNetwork.last_instance.nodes if n["id"] == "src_001_p1")
        assert "times out" in node["title"]
        assert "Dana Park" in node["title"]

    def test_source_tooltip_includes_type_segment_and_snippet(self):
        sources, points, themes = _fixture_data()
        graph_builder.build_graph_html(sources, points, themes)
        node = next(n for n in SpyNetwork.last_instance.nodes if n["id"] == "src_001")
        assert "interview" in node["title"]
        assert "Enterprise" in node["title"]
