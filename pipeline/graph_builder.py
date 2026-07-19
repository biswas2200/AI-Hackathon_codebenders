#!/usr/bin/env python3
"""
Build an interactive force-directed graph visualization of themes, pain points, and sources.
Uses pyvis for physics-based layout (like Obsidian graph view).
"""

import json
from collections import defaultdict

from pyvis.network import Network


# Per-theme palette. Node *fill* colors (theme/point/source) are shared --
# they read fine on both light and dark backgrounds -- only the canvas
# background, label font, edges, and header text swap between themes.
THEME_PALETTES = {
    "dark": {
        "bgcolor": "#111318",
        "font_color": "#e8e8e8",
        "theme_edge": "#555555",
        "source_edge": "#444444",
        "header_bg": "#111318",
        "header_text": "#e8e8e8",
        "legend_text": "#aaaaaa",
        "control_bg": "#1c2029",
        "control_border": "#3a3f4b",
    },
    "light": {
        "bgcolor": "#f7f7f9",
        "font_color": "#1a1a1a",
        "theme_edge": "#b8bcc6",
        "source_edge": "#cfd2da",
        "header_bg": "#f7f7f9",
        "header_text": "#1a1a1a",
        "legend_text": "#555555",
        "control_bg": "#ffffff",
        "control_border": "#c9ccd4",
    },
}


def build_graph_html(sources, points, themes, height="750px", theme="dark"):
    """
    Build an interactive HTML graph visualization.

    Args:
        sources: list of source dicts with id, source_type, text, segment, date
        points: list of pain point dicts with point_id, pain_point, quote, use_case, customer_name, segment
        themes: list of theme dicts with theme_name, theme_description, frequency, impact_score, segment_breakdown
        height: CSS height of the graph container
        theme: "dark" (default) or "light" -- controls canvas background,
            label font, edge, and header colors so the graph matches the
            dashboard's light/dark toggle. Node fill colors are unchanged.

    Returns:
        HTML string ready to embed in an iframe
    """

    palette = THEME_PALETTES.get(theme, THEME_PALETTES["dark"])

    # Create network with theme-appropriate background. Physics is enabled
    # via set_options() below, not a constructor kwarg -- pyvis 0.3.2's
    # Network.__init__ doesn't accept `physics`. cdn_resources="in_line" is
    # required, not cosmetic: the default ("local") references a lib/
    # folder that doesn't exist once this HTML is embedded as a string in
    # an iframe, and "remote" silently fails offline -- "in_line" embeds
    # vis-network's JS/CSS directly so the returned HTML is truly
    # standalone, per this function's contract.
    net = Network(
        height=height,
        bgcolor=palette["bgcolor"],
        font_color=palette["font_color"],
        directed=True,
        notebook=False,
        cdn_resources="in_line"
    )

    # Configure physics (barnes_hut repelling layout) and interaction in one
    # shot. Not calling show_buttons() -- it's not in the spec, and on pyvis
    # 0.3.2 calling it both before and after set_options() crashes
    # (set_options() replaces net.options with a plain dict, and the second
    # show_buttons() call then tries to set an attribute on that dict).
    #
    # Two deliberate choices here:
    #  - "stabilization": physics runs a bounded number of iterations then
    #    stops and auto-fits (fit: true). Without a bound, barnes_hut vs. the
    #    very weak centralGravity never converges at this node count -- left
    #    running, the whole graph slowly drifts off-canvas ("the graph got
    #    lost"). The tail script below freezes physics for good once this
    #    fires, so it can't resume drifting later.
    #  - "navigationButtons": false -- pyvis 0.3.2's built-in nav buttons
    #    depend on an icon sprite that vis-network's bundled CSS references
    #    by a path that doesn't survive cdn_resources="in_line" embedding,
    #    so the buttons render with no visible icon (clickable but
    #    invisible). Replaced below by plain-text/unicode custom buttons
    #    that don't depend on any external asset.
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "barnesHut": {
                "gravitationalConstant": -26000,
                "centralGravity": 0.005,
                "springLength": 200,
                "springConstant": 0.04
            },
            "stabilization": {
                "enabled": true,
                "iterations": 400,
                "fit": true
            }
        },
        "interaction": {
            "navigationButtons": false,
            "keyboard": true,
            "zoomView": true
        }
    }
    """)

    # Track added nodes to avoid duplicates
    added_nodes = set()

    # Parallel search index (id/type/searchable text) embedded into the
    # page as JSON -- the search box below matches against this rather than
    # vis-network's internal DataSet, so exactly what's searchable (full
    # pain point text, quotes, customer names, source snippets -- not just
    # the truncated on-canvas label) is explicit and independent of pyvis
    # internals.
    search_index = []

    # Add THEME nodes
    for theme in themes:
        theme_name = theme.get("theme_name", "Unknown")
        impact_score = theme.get("impact_score", 0)
        frequency = theme.get("frequency", 0)
        description = theme.get("theme_description", "")

        node_size = max(16 + impact_score, 30)
        tooltip = f"{theme_name}\nFrequency: {frequency}\nImpact Score: {impact_score}\n\n{description}"

        if theme_name not in added_nodes:
            net.add_node(
                theme_name,
                label=theme_name,
                title=tooltip,
                color="#F2A65A",
                size=node_size,
                shape="dot",
                font={"size": 14, "color": palette["font_color"]}
            )
            added_nodes.add(theme_name)
            search_index.append({
                "id": theme_name, "type": "Theme", "label": theme_name,
                "text": f"{theme_name} {description}"
            })

    # Add PAIN POINT nodes and edges to themes
    for point in points:
        point_id = point.get("point_id", "unknown")
        pain_point_text = point.get("pain_point", "")[:30]

        if point_id not in added_nodes:
            quote = point.get("quote", "")
            use_case = point.get("use_case", "")
            customer = point.get("customer_name", "")
            segment = point.get("segment", "")

            tooltip = f"{point.get('pain_point', '')}\nQuote: {quote}\nUse Case: {use_case}\nCustomer: {customer}\nSegment: {segment}"

            net.add_node(
                point_id,
                label=pain_point_text,
                title=tooltip,
                color="#8892A6",
                size=8,
                shape="dot",
                font={"size": 10, "color": palette["font_color"]}
            )
            added_nodes.add(point_id)
            search_index.append({
                "id": point_id, "type": "Pain point", "label": point.get("pain_point", point_id),
                "text": f"{point.get('pain_point', '')} {quote} {use_case} {customer} {segment} {point_id}"
            })

    # Add SOURCE nodes
    source_colors = {
        "interview": "#5B8DEF",
        "survey": "#4CAF7D",
        "support_ticket": "#B565D9"
    }

    for source in sources:
        source_id = source.get("id", "unknown")
        source_type = source.get("source_type", "unknown")
        segment = source.get("segment", "")
        date = source.get("date", "")
        text = source.get("text", "")[:180]  # 180 char snippet

        if source_id not in added_nodes:
            color = source_colors.get(source_type, "#999999")
            tooltip = f"{source_type}\nSegment: {segment}\nDate: {date}\nText: {text}"

            net.add_node(
                source_id,
                label=source_id,
                title=tooltip,
                color=color,
                size=6,
                shape="dot",
                font={"size": 8, "color": palette["font_color"]}
            )
            added_nodes.add(source_id)
            search_index.append({
                "id": source_id, "type": "Source", "label": source_id,
                "text": f"{source_id} {source_type} {segment} {date} {text}"
            })

    # Add edges: THEME -> PAIN_POINT
    for theme in themes:
        theme_name = theme.get("theme_name", "")
        point_ids = theme.get("point_ids", [])

        for point_id in point_ids:
            net.add_edge(theme_name, point_id, color=palette["theme_edge"], width=1, arrows="to")

    # Add edges: PAIN_POINT -> SOURCE
    point_id_to_source_id = defaultdict(list)

    # Build mapping from point_id to source_id by matching through extracted points
    for point in points:
        point_id = point.get("point_id", "")
        source_id = point.get("source_id", "")
        if point_id and source_id:
            point_id_to_source_id[point_id].append(source_id)

    # Add point-to-source edges
    for point_id, source_ids in point_id_to_source_id.items():
        for source_id in source_ids:
            net.add_edge(point_id, source_id, color=palette["source_edge"], width=0.5, arrows="to")

    # Get HTML
    html = net.generate_html(notebook=False)

    # Header: color legend + search box + zoom controls. Living in the
    # header (not floating over the canvas) means it can never overlap or
    # intercept clicks meant for the graph itself, and it's always visible
    # regardless of physics/pan/zoom state.
    btn_style = (
        "background: {control_bg}; color: {header_text}; border: 1px solid {control_border}; "
        "border-radius: 4px; padding: 6px 12px; font-size: 12px; cursor: pointer; white-space: nowrap;"
    ).format(**palette)
    header = '''<body style="background-color: {header_bg}; color: {header_text};">
        <div style="padding: 16px 20px 12px 20px; color: {header_text}; font-family: sans-serif;">
            <h3 style="margin: 0 0 6px 0;">Customer Problem Space Graph</h3>
            <p style="font-size: 12px; color: {legend_text}; margin: 0 0 4px 0;">
                <strong>Color Legend:</strong>
                <span style="color: #F2A65A;">&#9679; Themes</span> |
                <span style="color: #8892A6;">&#9679; Pain Points</span> |
                <span style="color: #5B8DEF;">&#9679; Interviews</span> |
                <span style="color: #4CAF7D;">&#9679; Surveys</span> |
                <span style="color: #B565D9;">&#9679; Support Tickets</span>
            </p>
            <p style="font-size: 12px; color: {legend_text}; margin: 0 0 10px 0;">Drag to move, scroll to zoom, click to select</p>
            <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 8px;">
                <input id="graph-search-input" type="text" placeholder="Search pain points, themes, sources..."
                    autocomplete="off"
                    style="flex: 1 1 260px; min-width: 200px; background: {control_bg}; color: {header_text};
                           border: 1px solid {control_border}; border-radius: 4px; padding: 6px 10px; font-size: 13px;" />
                <button id="graph-search-prev" title="Previous match" type="button" style="{btn_style}">&#8593; Prev</button>
                <button id="graph-search-next" title="Next match" type="button" style="{btn_style}">&#8595; Next</button>
                <span id="graph-search-count" style="font-size: 12px; color: {legend_text}; min-width: 52px; text-align: center;"></span>
                <span style="width: 1px; align-self: stretch; background: {control_border}; margin: 0 4px;"></span>
                <button id="graph-zoom-out" title="Zoom out" type="button" style="{btn_style}">&minus; Zoom out</button>
                <button id="graph-zoom-fit" title="Fit graph to view" type="button" style="{btn_style}">&#9678; Fit</button>
                <button id="graph-zoom-in" title="Zoom in" type="button" style="{btn_style}">&plus; Zoom in</button>
            </div>
            <p id="graph-search-empty" style="font-size: 12px; color: #d98c8c; margin: 6px 0 0 0; display: none;">No matches</p>
        </div>
        '''.format(btn_style=btn_style, **palette)

    enhanced_html = html.replace('<body>', header)

    # barnes_hut repulsion (gravitationalConstant -26000) against a very
    # weak centralGravity (0.005) never actually converges at this node
    # count -- left running, physics keeps drifting nodes further apart
    # indefinitely. Freeze physics once stabilized (nodes stay individually
    # draggable afterward; physics just stops fighting the camera), and
    # zoom is clamped to a range relative to the fitted scale so scrolling
    # can't zoom out to a vanishing point or in to a meaningless blowup.
    tail_script = '''<script>
        if (typeof network !== "undefined") {
            var SEARCH_INDEX = ''' + json.dumps(search_index) + ''';
            var searchMatches = [];
            var searchCursor = -1;
            var baseScale = network.getScale() || 1;
            var MIN_SCALE = baseScale * 0.15;
            var MAX_SCALE = baseScale * 12;

            function clampScale(s) {
                return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
            }

            function doFit() {
                // vis-network's <canvas> pixel-buffer width/height
                // *attributes* (the actual drawable bitmap resolution --
                // nothing can render onto a canvas whose width/height
                // attributes are 0, regardless of its CSS size or what
                // scale fit() computes) aren't kept in sync by
                // network.setSize()/redraw() in this context, so set them
                // directly from the container's live measured size.
                var canvasEl = network.canvas.frame.canvas;
                var rect = document.getElementById("mynetwork").getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    canvasEl.width = rect.width;
                    canvasEl.height = rect.height;
                }
                network.redraw();
                network.fit({animation: false});
                // fit() only accounts for node geometry, not label text --
                // a node sitting exactly at the computed edge still has its
                // label extending past it, which then gets clipped by the
                // canvas boundary. Pull back an extra margin so nodes
                // (and their labels) settle comfortably inside the visible
                // area instead of flush against the edge.
                network.moveTo({scale: network.getScale() * 0.82, animation: false});
                baseScale = network.getScale() || baseScale;
                MIN_SCALE = baseScale * 0.15;
                MAX_SCALE = baseScale * 12;
            }

            // Freeze physics as soon as it settles (visibility-independent
            // -- this can safely happen while the panel is still hidden).
            network.once("stabilizationIterationsDone", function () {
                network.setOptions({physics: false});
            });

            // Streamlit renders every tab's content into the DOM up front
            // and only toggles which one is display:block -- this graph's
            // <iframe> (and everything inside it, including physics
            // stabilization) runs its scripts while still display:none if
            // the "Source Graph" tab isn't the active one yet. An element
            // inside a display:none ancestor always measures 0x0 via
            // getBoundingClientRect(), and nothing (stabilization events,
            // ResizeObserver, window "resize", fixed-delay timers) fires
            // when a display:none -> block toggle later makes it visible.
            // Poll until the container actually has a nonzero size, fit
            // once, then stop -- this is the one signal that's true
            // regardless of *why* it was hidden or *when* it becomes
            // visible, so it doesn't matter whether Streamlit is still
            // laying the iframe out, the tab is still hidden, or both.
            var gotFirstFit = false;
            var pollHandle = setInterval(function () {
                var rect = document.getElementById("mynetwork").getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    doFit();
                    gotFirstFit = true;
                    clearInterval(pollHandle);
                }
            }, 200);
            // Polling is cheap (one getBoundingClientRect() every 200ms),
            // and the user may not click over to this tab for a while --
            // give up only after a generous ceiling, not a short one that
            // would leave the graph permanently un-fitted if they're slower
            // than that to switch tabs.
            setTimeout(function () { clearInterval(pollHandle); }, 300000);

            // Re-fit on later genuine resizes (browser window resize, or
            // Streamlit resizing the outer iframe) once already visible.
            window.addEventListener("resize", function () {
                if (gotFirstFit) { doFit(); }
            });

            // Prevent the wheel/pinch zoom from running away to a vanishing
            // point (zoomed out) or a meaningless blowup (zoomed in).
            network.on("zoom", function () {
                var s = network.getScale();
                var clamped = clampScale(s);
                if (clamped !== s) {
                    network.moveTo({scale: clamped});
                }
            });

            // --- Search -------------------------------------------------
            function normalize(s) { return (s || "").toLowerCase(); }

            function updateCount() {
                var countEl = document.getElementById("graph-search-count");
                var emptyEl = document.getElementById("graph-search-empty");
                var query = document.getElementById("graph-search-input").value;
                if (!query) {
                    countEl.textContent = "";
                    emptyEl.style.display = "none";
                } else if (searchMatches.length === 0) {
                    countEl.textContent = "";
                    emptyEl.style.display = "block";
                } else {
                    countEl.textContent = (searchCursor + 1) + " / " + searchMatches.length;
                    emptyEl.style.display = "none";
                }
            }

            function focusMatch() {
                if (searchCursor < 0 || searchCursor >= searchMatches.length) { return; }
                var id = searchMatches[searchCursor];
                network.selectNodes([id]);
                network.focus(id, {
                    scale: Math.max(baseScale * 2.5, 1),
                    animation: {duration: 300, easingFunction: "easeInOutQuad"}
                });
            }

            function runSearch(query) {
                query = normalize(query);
                if (!query) {
                    searchMatches = [];
                    searchCursor = -1;
                    network.unselectAll();
                    updateCount();
                    return;
                }
                searchMatches = SEARCH_INDEX.filter(function (item) {
                    return normalize(item.text).indexOf(query) !== -1;
                }).map(function (item) { return item.id; });
                searchCursor = searchMatches.length > 0 ? 0 : -1;
                updateCount();
                focusMatch();
            }

            function nextMatch() {
                if (!searchMatches.length) { return; }
                searchCursor = (searchCursor + 1) % searchMatches.length;
                focusMatch();
                updateCount();
            }

            function prevMatch() {
                if (!searchMatches.length) { return; }
                searchCursor = (searchCursor - 1 + searchMatches.length) % searchMatches.length;
                focusMatch();
                updateCount();
            }

            var searchInput = document.getElementById("graph-search-input");
            searchInput.addEventListener("input", function (e) { runSearch(e.target.value); });
            searchInput.addEventListener("keydown", function (e) {
                if (e.key === "Enter") {
                    e.preventDefault();
                    if (e.shiftKey) { prevMatch(); } else if (searchCursor === -1) { runSearch(searchInput.value); } else { nextMatch(); }
                } else if (e.key === "Escape") {
                    searchInput.value = "";
                    runSearch("");
                }
            });
            document.getElementById("graph-search-next").addEventListener("click", nextMatch);
            document.getElementById("graph-search-prev").addEventListener("click", prevMatch);

            // --- Zoom buttons --------------------------------------------
            document.getElementById("graph-zoom-in").addEventListener("click", function () {
                network.moveTo({scale: clampScale(network.getScale() * 1.3), animation: {duration: 200}});
            });
            document.getElementById("graph-zoom-out").addEventListener("click", function () {
                network.moveTo({scale: clampScale(network.getScale() / 1.3), animation: {duration: 200}});
            });
            document.getElementById("graph-zoom-fit").addEventListener("click", function () {
                network.fit({animation: {duration: 300}});
                // Match doFit()'s margin so a manual re-fit doesn't put
                // node labels flush against the canvas edge either.
                setTimeout(function () {
                    network.moveTo({scale: network.getScale() * 0.82, animation: {duration: 200}});
                }, 300);
            });
        }
        </script>
        </body>'''

    enhanced_html = enhanced_html.replace('</body>', tail_script)

    return enhanced_html


if __name__ == "__main__":
    # Test with mock data
    mock_sources = [
        {"id": "src_001", "source_type": "interview", "text": "Test interview about export issues", "segment": "Enterprise", "date": "2024-01-15"}
    ]
    mock_points = [
        {"point_id": "src_001_p1", "pain_point": "Exports timeout on large datasets", "quote": "times out", "use_case": "Exporting data", "customer_name": "Dana Park", "segment": "Enterprise", "source_id": "src_001"}
    ]
    mock_themes = [
        {"theme_name": "Export Performance", "theme_description": "Issues with exporting data", "frequency": 5, "impact_score": 15, "segment_breakdown": {"Enterprise": 5}, "point_ids": ["src_001_p1"]}
    ]

    html = build_graph_html(mock_sources, mock_points, mock_themes)

    print(f"✓ Generated HTML graph ({len(html)} bytes)")
    print(f"  Contains '<html': {'<html' in html}")
    print(f"  Contains theme name: {'Export Performance' in html}")
    print(f"  Contains node colors: {'#F2A65A' in html and '#8892A6' in html}")
