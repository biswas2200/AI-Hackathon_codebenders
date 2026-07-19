#!/usr/bin/env python3
"""
DiscoveryOS Streamlit Dashboard
Two-tab interface: Prioritized Report + Source Graph
With Run Pipeline button and live segment weight sliders
"""

import sys
import streamlit as st
import json
import html
import subprocess
from pathlib import Path
import pandas as pd
from pipeline.graph_builder import build_graph_html
from pipeline import llm_utils


def html_iframe(content: str, height: int = 400, scrolling: bool = True):
    """
    Replacement for deprecated st.components.v1.html().
    Uses st.iframe() with data URI encoding to handle HTML content with scrolling control.
    
    Args:
        content: HTML string to embed
        height: Height of the iframe in pixels
        scrolling: Whether to allow scrolling (controls CSS overflow behavior)
    """
    import base64
    
    # Wrap HTML with CSS to control scrolling and ensure proper sizing
    wrapped_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ margin: 0; padding: 0; overflow: {'auto' if scrolling else 'hidden'}; }}
        html {{ margin: 0; padding: 0; overflow: {'auto' if scrolling else 'hidden'}; }}
    </style>
</head>
<body>
{content}
</body>
</html>'''
    
    # Encode as base64 data URI
    encoded = base64.b64encode(wrapped_html.encode('utf-8')).decode('utf-8')
    data_uri = f"data:text/html;base64,{encoded}"
    
    # Use st.iframe with the data URI
    st.iframe(src=data_uri, height=height, width="stretch")


# Page config
st.set_page_config(layout="wide", page_title="DiscoveryOS - Product Discovery Intelligence")


@st.cache_data
def load_sources():
    """Load sources.json"""
    if not Path("data/sources.json").exists():
        return None
    with open("data/sources.json") as f:
        return json.load(f)


@st.cache_data
def load_extracted_points():
    """Load extracted_pain_points.json"""
    if not Path("data/extracted_pain_points.json").exists():
        return None
    with open("data/extracted_pain_points.json") as f:
        return json.load(f)


@st.cache_data
def load_themed_report():
    """Load themed_report.json"""
    if not Path("data/themed_report.json").exists():
        return None
    with open("data/themed_report.json") as f:
        return json.load(f)


def run_pipeline(mode="cached"):
    """Run the extraction + clustering pipeline live.

    `mode` controls how much of it actually spends real API quota, by
    clearing the appropriate slice of the response cache *before* the
    subprocesses run (extract.py/cluster_score.py transparently re-hit any
    cache entry that's still present, so what's left cached = what stays
    free):
      - "cached": clear only the clustering/narrative cache, leave the
        expensive extraction cache intact -> ~2 real calls, and the themes
        regenerate live each run (slightly different every time).
      - "full":   clear the whole cache -> a full live re-run, ~20 real
        calls (re-extracts every source too).
    Either way the results are written to disk and both tabs refresh.
    """
    try:
        if mode == "full":
            llm_utils.clear_cache(None)
            extract_label = "Extracting pain points live (full re-run)..."
        else:
            llm_utils.clear_cache(["cluster_", "narratives_"])
            extract_label = "Loading extraction (cached)..."

        with st.spinner(extract_label):
            result_extract = subprocess.run(
                [sys.executable, "pipeline/extract.py"],
                capture_output=True,
                text=True,
                check=True
            )
            st.info(result_extract.stdout)

        with st.spinner("Clustering and generating narratives live..."):
            result_cluster = subprocess.run(
                [sys.executable, "pipeline/cluster_score.py"],
                capture_output=True,
                text=True,
                check=True
            )
            st.info(result_cluster.stdout)


        # Fresh JSON is on disk now; drop the @st.cache_data memoization and
        # rerun so both tabs re-read and reflect the new results this session.
        st.cache_data.clear()
        st.rerun()

    except subprocess.CalledProcessError as e:
        st.error(f"Pipeline failed: {e.stderr}")
    except Exception as e:
        st.error(f"Error: {str(e)}")


def apply_theme(theme):
    """Inject a scoped CSS block to flip the main app surfaces for light
    mode. The graph iframe is fully theme-controlled separately (its own
    `theme` arg); this handles the Streamlit chrome. It's a best-effort
    override of the main container background/text -- Streamlit's own
    widgets are themed by .streamlit/config.toml, and a runtime CSS flip
    covers the surfaces that matter (app background, headings, text) without
    fighting every internal widget class.

    Two things confirmed by inspecting the live DOM (Streamlit 1.59):
    - `[data-testid="stAppViewContainer"]` and `[data-testid="stMain"]` are
      both *transparent* -- the actual painted background lives on
      `[data-testid="stApp"]` (and <body>). Setting background on the
      container elements alone visibly did nothing.
    - `[data-testid="stSidebar"]` is a descendant of stAppViewContainer but
      paints its *own* separate background. A text-color rule scoped to
      "everything under stAppViewContainer" therefore also matches the
      sidebar's text -- so a naive fix that only recolors text there
      (without also giving the sidebar its own light background) produces
      dark text on an unchanged dark sidebar: unreadable. Both need
      explicit, paired background + text rules.
    """
    if theme == "light":
        st.markdown(
            """
            <style>
            [data-testid="stApp"], body, [data-testid="stHeader"] {
                background-color: #f7f7f9 !important;
            }
            [data-testid="stSidebar"] {
                background-color: #ffffff !important;
                border-right: 1px solid #e2e2e6;
            }
            [data-testid="stApp"] .stMarkdown,
            [data-testid="stApp"] p,
            [data-testid="stApp"] h1,
            [data-testid="stApp"] h2,
            [data-testid="stApp"] h3,
            [data-testid="stApp"] h4,
            [data-testid="stApp"] label,
            [data-testid="stApp"] [data-testid="stMetricLabel"],
            [data-testid="stApp"] [data-testid="stMetricValue"] {
                color: #1a1a1a !important;
            }
            [data-testid="stApp"] [data-testid="stCaptionContainer"] {
                color: #555555 !important;
            }
            [data-testid="stSidebar"] .stMarkdown,
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] h1,
            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3,
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] [data-testid="stMetricLabel"],
            [data-testid="stSidebar"] [data-testid="stMetricValue"],
            [data-testid="stSidebar"] span,
            [data-testid="stSidebar"] div {
                color: #1a1a1a !important;
            }
            /* Primary button styling for light mode */
            [data-testid="stSidebar"] button {
                color: #1a1a1a !important;
                background-color: #e8e8ec !important;
                border: 1px solid #d0d0d6 !important;
                opacity: 1 !important;
                visibility: visible !important;
            }
            [data-testid="stSidebar"] button:hover {
                background-color: #d8d8dc !important;
            }
            [data-testid="stSidebar"] button:active {
                background-color: #c8c8cc !important;
            }
            /* Button text and nested elements */
            [data-testid="stSidebar"] button,
            [data-testid="stSidebar"] button * {
                color: #1a1a1a !important;
                fill: #1a1a1a !important;
            }
            /* Streamlit button container styles */
            [data-testid="stSidebar"] [role="button"] {
                color: #1a1a1a !important;
                background-color: #e8e8ec !important;
                border: 1px solid #d0d0d6 !important;
                opacity: 1 !important;
                visibility: visible !important;
            }
            [data-testid="stSidebar"] [role="button"]:hover {
                background-color: #d8d8dc !important;
            }
            [data-testid="stSidebar"] [role="button"]:active {
                background-color: #c8c8cc !important;
            }
            /* Button text styling for role="button" */
            [data-testid="stSidebar"] [role="button"],
            [data-testid="stSidebar"] [role="button"] * {
                color: #1a1a1a !important;
                fill: #1a1a1a !important;
            }
            /* SVG icons in buttons */
            [data-testid="stSidebar"] button svg,
            [data-testid="stSidebar"] [role="button"] svg {
                fill: #1a1a1a !important;
                stroke: #1a1a1a !important;
            }
            /* Toggle and checkbox styles */
            [data-testid="stSidebar"] [data-testid="stToggle"] {
                color: #1a1a1a !important;
            }
            [data-testid="stSidebar"] [data-testid="stToggle"] label {
                color: #1a1a1a !important;
            }
            /* Ensure captions are visible */
            [data-testid="stSidebar"] .stCaption {
                color: #555555 !important;
            }
            /* Additional button container styling */
            [data-testid="stSidebar"] .stButton {
                width: 100%;
            }
            [data-testid="stSidebar"] .stButton button {
                width: 100%;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )



def main():
    # Initialize session state for tab selection and theme
    if "selected_tab" not in st.session_state:
        st.session_state.selected_tab = 0
    if "theme_dark_mode" not in st.session_state:
        st.session_state.theme_dark_mode = True
    
    st.title("🔍 DiscoveryOS")
    st.subheader("Product Discovery & User Research Intelligence")

    # Sidebar
    st.sidebar.title("Pipeline & Controls")

    # Appearance: light / dark toggle (default dark). Drives both the
    # Streamlit chrome (via apply_theme CSS) and the graph (via its theme arg).
    # Named color_theme (not `theme`) deliberately -- `theme` is reused as a
    # loop variable further down over the themed_report entries.
    
    # KEY FIX: Use session_state directly without a toggle to prevent reruns
    # The toggle below just updates session_state; it doesn't trigger a rerun itself
    # Instead, we'll detect the change and apply it without losing tab state
    
    with st.sidebar:
        # Use a form to batch the theme change with the rest of the UI updates
        # This prevents the toggle from causing an isolated rerun that resets tabs
        dark_mode_new = st.toggle("🌙 Dark mode", value=st.session_state.theme_dark_mode)
        
        # Update session state if toggle changed
        if dark_mode_new != st.session_state.theme_dark_mode:
            st.session_state.theme_dark_mode = dark_mode_new
    
    color_theme = "dark" if st.session_state.theme_dark_mode else "light"
    # Apply theme CSS
    apply_theme(color_theme)




    full_live = st.sidebar.toggle(
        "Full live re-run",
        value=False,
        help=(
            "Off (green): extraction is served from cache, only clustering + "
            "narratives call the API live (~2 calls). On (red): re-extract "
            "every source too (~20 calls, slower)."
        ),
    )
    if full_live:
        pipeline_mode = "full"
        st.sidebar.markdown(":red[🔴 **Full live** — re-extracts everything · ~20 API calls]")
    else:
        pipeline_mode = "cached"
        st.sidebar.markdown(":green[🟢 **Cached** — extraction cached, clustering runs live · ~2 API calls]")

    # Pipeline control button
    if st.sidebar.button("▶ Run Pipeline", width='stretch'):
        run_pipeline(pipeline_mode)

    st.sidebar.divider()
    
    # Segment weight sliders
    st.sidebar.subheader("Segment Value Weights")
    st.sidebar.caption("Adjust to reweight themes by segment importance (no API calls)")
    
    weights = {
        "Enterprise": st.sidebar.slider("Enterprise", 1, 10, 5),
        "Mid-Market": st.sidebar.slider("Mid-Market", 1, 10, 3),
        "SMB": st.sidebar.slider("SMB", 1, 10, 2),
        "Free": st.sidebar.slider("Free", 1, 10, 1),
    }
    
    st.sidebar.divider()
    
    # Load data
    sources = load_sources()
    points = load_extracted_points()
    themes_raw = load_themed_report()
    
    # Check if themed_report exists
    if themes_raw is None:
        st.error("❌ No data found - please run the pipeline first")
        st.info("**To get started:**")
        st.code("""
export GROQ_API_KEY=your_key
python3 data/generate_synthetic_data.py
python3 pipeline/extract.py
python3 pipeline/cluster_score.py
streamlit run app.py
        """)
        st.stop()
    
    # Live recompute impact scores with slider weights
    themes = []
    for theme in themes_raw:
        recomputed_score = sum(
            weights.get(seg, 1) * count
            for seg, count in theme.get("segment_breakdown", {}).items()
        )
        theme_copy = theme.copy()
        theme_copy["impact_score"] = recomputed_score
        themes.append(theme_copy)
    
    # Re-sort by the recomputed scores, but keep "Other / Unclustered"
    # pinned last (same rule cluster_score.py applies to the file) -- it's a
    # catch-all safety net, not a real prioritized theme, and its aggregate
    # score can be high just from holding many leftover points, so it must
    # never surface as "Top Priority".
    OTHER = "Other / Unclustered"
    themes.sort(key=lambda t: (t["theme_name"] == OTHER, -t["impact_score"]))
    
    # Segment filter
    all_segments = set()
    for theme in themes:
        all_segments.update(theme.get("segment_breakdown", {}).keys())
    
    selected_segments = st.sidebar.multiselect(
        "Filter by Segment",
        sorted(list(all_segments)),
        default=sorted(list(all_segments))
    )
    
    # Filter themes by segment
    filtered_themes = []
    for theme in themes:
        segments_in_theme = set(theme.get("segment_breakdown", {}).keys())
        if segments_in_theme & set(selected_segments):
            filtered_themes.append(theme)
    

    # Create tabs with state preservation using localStorage JavaScript
    # Key insight: When st.sidebar.toggle() changes, it ALWAYS causes a rerun.
    # During rerun, tabs render fresh. We use localStorage + JavaScript to
    # remember which tab was active and restore it after tabs render.
    
    # 1. Inject JavaScript that will run in the browser
    st.markdown(
        """
        <script>
        // Store tab selection in localStorage
        // This persists across Streamlit script reruns
        
        function setupTabPersistence() {
            // Get the saved tab index from localStorage
            const savedTabIndex = localStorage.getItem('discoveryos_active_tab');
            const tabIndexToSelect = savedTabIndex ? parseInt(savedTabIndex) : 0;
            
            // Function to handle tab clicks and save the index
            function attachTabListeners() {
                const tabButtons = document.querySelectorAll('[role="tab"]');
                tabButtons.forEach((button, index) => {
                    // Record when a tab becomes active
                    if (button.getAttribute('aria-selected') === 'true') {
                        localStorage.setItem('discoveryos_active_tab', index.toString());
                    }
                    
                    // Add click listener to save index when user clicks
                    button.addEventListener('click', function() {
                        localStorage.setItem('discoveryos_active_tab', index.toString());
                    });
                });
                
                // After a brief moment, restore the previously active tab
                if (tabIndexToSelect > 0) {
                    setTimeout(function() {
                        const tabs = document.querySelectorAll('[role="tab"]');
                        if (tabs[tabIndexToSelect]) {
                            tabs[tabIndexToSelect].click();
                        }
                    }, 200);
                }
            }
            
            // Attach listeners when page loads
            attachTabListeners();
            
            // Watch for new tabs being added (happens on rerun) and re-attach
            const observer = new MutationObserver(function() {
                // Check if tabs have changed and update listeners
                const tabButtons = document.querySelectorAll('[role="tab"]');
                if (tabButtons.length > 0) {
                    // Restore the saved tab state
                    if (tabIndexToSelect > 0) {
                        setTimeout(function() {
                            const tabs = document.querySelectorAll('[role="tab"]');
                            if (tabs[tabIndexToSelect] && tabs[tabIndexToSelect].getAttribute('aria-selected') !== 'true') {
                                tabs[tabIndexToSelect].click();
                            }
                        }, 100);
                    }
                }
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
        
        // Start the setup when ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupTabPersistence);
        } else {
            setupTabPersistence();
        }
        </script>
        """,
        unsafe_allow_html=True
    )
    
    # 2. Create tabs
    tabs_list = st.tabs(["📊 Prioritized Report", "🕸️ Source Graph"])
    tab1, tab2 = tabs_list[0], tabs_list[1]


    # ===== TAB 1: PRIORITIZED REPORT =====
    with tab1:
        st.header("Problem Space Report")
        
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Themes", len(filtered_themes))
        
        with col2:
            total_points = sum(t["frequency"] for t in filtered_themes)
            st.metric("Total Pain Points", total_points)
        
        with col3:
            all_customers = set()
            for theme in filtered_themes:
                all_customers.update(theme.get("customers", []))
            st.metric("Unique Customers", len(all_customers))
        
        with col4:
            top_theme = filtered_themes[0]["theme_name"] if filtered_themes else "N/A"
            # st.metric's value is single-line with an ellipsis once it
            # doesn't fit the column -- fine for the other three (always
            # short integers) but theme names are unbounded length and were
            # getting cut off ("Security and Compli..."). A custom block
            # with word-wrap instead of a fixed metric font shows the full
            # name, wrapped, at a size that actually fits the column.
            st.markdown(
                f'''
                <div style="display:flex; flex-direction:column; gap:2px; padding-top:2px;">
                    <div style="font-size:0.875rem; opacity:0.7;">Top Priority</div>
                    <div style="font-size:1.35rem; font-weight:600; line-height:1.3;
                                white-space:normal; overflow-wrap:break-word;">
                        {html.escape(top_theme)}
                    </div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
        
        st.divider()
        
        # Themes table
        if filtered_themes:
            table_data = []
            for idx, theme in enumerate(filtered_themes, 1):
                segments = ", ".join(theme.get("segment_breakdown", {}).keys())
                table_data.append({
                    "Rank": idx,
                    "Theme": theme["theme_name"],
                    "Impact Score": round(theme["impact_score"], 1),
                    "Frequency": theme["frequency"],
                    "Segments": segments
                })
            
            st.dataframe(
                pd.DataFrame(table_data),
                width='stretch',
                hide_index=True
            )
        
        st.divider()
        
        # Per-theme details
        for theme in filtered_themes:
            with st.expander(f"📌 {theme['theme_name']} (Score: {round(theme['impact_score'], 1)})"):
                # Executive summary
                st.write("**Executive Summary:**")
                st.write(theme.get("executive_summary", "N/A"))
                
                # Breakdowns
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**By Segment:**")
                    seg_data = theme.get("segment_breakdown", {})
                    st.bar_chart(seg_data)
                
                with col2:
                    st.write("**By Use Case:**")
                    use_data = theme.get("use_case_breakdown", {})
                    st.bar_chart(use_data)
                
                # Quotes
                st.write("**Representative Quotes:**")
                for quote in theme.get("sample_quotes", []):
                    st.caption(f"> {quote}")
                
                # Customers
                st.write(f"**Customers:** {', '.join(theme.get('customers', []))}")
    
    # ===== TAB 2: SOURCE GRAPH =====
    with tab2:
        st.header("Problem Space Graph")
        st.caption("Themes (orange) → Pain Points (gray) → Data Sources (colored by type). Drag to move, scroll to zoom.")
        
        if points is None or sources is None:
            st.warning("⚠️ Missing sources or extracted points. Run pipeline first.")
        else:
            try:
                graph_html = build_graph_html(sources, points, themes_raw, theme=color_theme)
                # 750px canvas + ~150-200px header (title, legend, search/zoom
                # toolbar -- the toolbar's flex row wraps to a second line on
                # narrower viewports, adding more height there) -- with
                # scrolling=False there's no way to reach anything past this
                # height, so it must cover both, not just the canvas alone,
                html_iframe(graph_html, height=1050, scrolling=False)
                # 950 clipped ~13px at a 956px-wide viewport).
            except Exception as e:
                st.error(f"Graph generation failed: {e}")

if __name__ == "__main__":
    main()
