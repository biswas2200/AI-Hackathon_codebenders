#!/usr/bin/env python3
"""
Cluster pain points into themes and score by business impact.
Reads: data/extracted_pain_points.json
Outputs: data/themed_report.json
"""

import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Running as `python pipeline/cluster_score.py` puts pipeline/ on sys.path,
# not the project root -- add the root so `from pipeline import llm_utils`
# (an absolute package import) resolves regardless of how this is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.llm_utils import load_dotenv

load_dotenv()

# Check for API key
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    print("ERROR: GROQ_API_KEY environment variable not set")
    print("Please set: export GROQ_API_KEY=your_key")
    print("Get a free key at https://console.groq.com")
    exit(1)

from groq import Groq

from pipeline import llm_utils

client = Groq(api_key=api_key)
MODEL = "llama-3.3-70b-versatile"

# Segment weights (placeholder for real ARR/deal-size data)
SEGMENT_WEIGHT = {
    "Enterprise": 5,
    "Mid-Market": 3,
    "SMB": 2,
    "Free": 1
}

CLUSTERING_PROMPT_TEMPLATE = """Below is a JSON array of customer pain points extracted from product
research (interviews, surveys, support tickets) for a B2B SaaS analytics
product.

Many of these describe the SAME underlying problem in different words
(e.g. "exports time out" and "CSV export failed after 25 minutes" are the
same theme). Customers with different technical fluency may describe the
same problem in very different words -- cluster by underlying root cause,
not by shared keywords or phrasing style.

Group them into a small number of THEMES (aim for 5-9 themes, don't
over-split). Return your answer as a JSON object with a single key
"themes", containing an array. Each item:
- "theme_name": short punchy name (3-6 words)
- "theme_description": 1-2 sentence neutral description of the underlying
  problem
- "point_ids": list of point_id values (from the input) belonging to this
  theme

IMPORTANT: assign EVERY point_id from the input to exactly one theme. Do
not drop or omit any point_id. If a point genuinely doesn't fit an existing
theme, put it in the nearest reasonable theme rather than leaving it out --
every input point_id must appear in exactly one theme's "point_ids" list.

PAIN POINTS:
{points}"""

NARRATIVE_PROMPT_TEMPLATE = """You are writing product roadmap "problem space" report entries for a PM
audience. Below is a JSON array of themes. For EACH theme, write a tight
2-3 sentence executive summary explaining the problem and why it matters
for the business (reference segment/frequency naturally, don't just
restate the numbers). Do not use marketing language. Be direct and
specific.

Return your answer as a JSON object with a single key "summaries",
containing an array, one object per theme:
- "theme_name": copy the input theme_name exactly -- used to match this
  summary back to the right theme
- "executive_summary": the 2-3 sentence narrative, plain text (not
  markdown)

THEMES:
{themes_json}"""


def _hash_ids(ids):
    return hashlib.sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:16]


def _build_theme(theme_name, theme_description, point_ids, points_by_id):
    theme_points = [points_by_id[pid] for pid in point_ids if pid in points_by_id]

    segment_breakdown = defaultdict(int)
    use_case_breakdown = defaultdict(int)
    customers = set()
    quotes = []

    for p in theme_points:
        segment_breakdown[p["segment"]] += 1
        use_case_breakdown[p["use_case"]] += 1
        customers.add(p["customer_name"])
        if p["quote"] and len(quotes) < 5:
            quotes.append(p["quote"])

    impact_score = sum(SEGMENT_WEIGHT.get(p["segment"], 1) for p in theme_points)

    return {
        "theme_name": theme_name,
        "theme_description": theme_description,
        "frequency": len(theme_points),
        "impact_score": impact_score,
        "segment_breakdown": dict(segment_breakdown),
        "use_case_breakdown": dict(use_case_breakdown),
        "sample_quotes": quotes,
        "customers": sorted(customers),
        "point_ids": [pid for pid in point_ids if pid in points_by_id],
        "executive_summary": ""  # filled in by the narrative call below
    }


def cluster_and_score():
    """Main clustering and scoring function."""

    # Load extracted pain points
    with open("data/extracted_pain_points.json") as f:
        points = json.load(f)

    start_call_count = llm_utils.real_call_count()

    print(f"Clustering {len(points)} pain points...")
    print()

    points_by_id = {p["point_id"]: p for p in points}

    slim_points = [
        {"point_id": p["point_id"], "pain_point": p["pain_point"], "use_case": p["use_case"]}
        for p in points
    ]

    # --- 1. Clustering call (one call for the whole dataset) ---
    print("[1/2] Clustering pain points...", end=" ", flush=True)

    cluster_cache_key = "cluster_" + _hash_ids(points_by_id.keys())
    clustering_response = llm_utils.call_groq(
        client, MODEL,
        CLUSTERING_PROMPT_TEMPLATE.format(points=json.dumps(slim_points)),
        json_mode=True,
        cache_key=cluster_cache_key
    )

    try:
        themes_data = json.loads(clustering_response)["themes"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"✗ JSON parse failed")
        print(f"Response: {clustering_response[:200]}")
        raise SystemExit(1) from e

    # Handle both dict and list formats from the API
    if isinstance(themes_data, dict):
        themes_raw = list(themes_data.values())
    else:
        themes_raw = themes_data

    print(f"✓ ({len(themes_raw)} themes)")

    # --- Orphaned point check (required, not optional) ---
    all_point_ids = set(points_by_id.keys())
    clustered_point_ids = set()
    for theme in themes_raw:
        clustered_point_ids.update(theme.get("point_ids", []))
    orphaned_ids = all_point_ids - clustered_point_ids

    if orphaned_ids:
        print(f"⚠ Found {len(orphaned_ids)} orphaned points, creating 'Other / Unclustered' theme")

    # --- Assemble themes with computed scores/breakdowns ---
    themes = []
    for theme_idx, theme_raw in enumerate(themes_raw, 1):
        theme_name = theme_raw.get("theme_name", f"Theme {theme_idx}")
        point_ids = theme_raw.get("point_ids", [])
        valid_point_ids = [pid for pid in point_ids if pid in points_by_id]
        if not valid_point_ids:
            continue
        themes.append(_build_theme(
            theme_name, theme_raw.get("theme_description", ""), valid_point_ids, points_by_id
        ))

    if orphaned_ids:
        themes.append(_build_theme(
            "Other / Unclustered",
            "Pain points that did not cluster with other themes.",
            list(orphaned_ids), points_by_id
        ))

    # --- 2. Narrative call (ONE call covering every theme) ---
    print("[2/2] Generating narratives...", end=" ", flush=True)

    narrative_payload = [
        {
            "theme_name": t["theme_name"],
            "theme_description": t["theme_description"],
            "frequency": t["frequency"],
            "segment_breakdown": t["segment_breakdown"],
            "sample_quotes": t["sample_quotes"],
        }
        for t in themes
    ]
    narrative_cache_key = "narratives_" + _hash_ids(t["theme_name"] for t in themes)

    try:
        narrative_response = llm_utils.call_groq(
            client, MODEL,
            NARRATIVE_PROMPT_TEMPLATE.format(themes_json=json.dumps(narrative_payload)),
            json_mode=True,
            cache_key=narrative_cache_key
        )
        summaries_by_name = {
            s["theme_name"]: s["executive_summary"]
            for s in json.loads(narrative_response)["summaries"]
        }
        for theme in themes:
            theme["executive_summary"] = summaries_by_name.get(
                theme["theme_name"],
                f"{theme['theme_description']} This issue affects {len(theme['segment_breakdown'])} customer segments."
            )
        print("✓")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"✗ (narrative parse failed, using fallback descriptions: {e})")
        for theme in themes:
            theme["executive_summary"] = (
                f"{theme['theme_description']} This issue affects {len(theme['segment_breakdown'])} customer segments."
            )

    # Sort by impact_score descending, but always keep "Other / Unclustered"
    # last regardless of its score. It's a catch-all safety net, not a real
    # prioritized theme -- letting it surface as "Top Priority" (it can
    # accumulate a high aggregate score just by holding many leftover points)
    # would be misleading in the report.
    OTHER = "Other / Unclustered"
    themes.sort(key=lambda t: (t["theme_name"] == OTHER, -t["impact_score"]))

    # Write output
    os.makedirs("data", exist_ok=True)
    with open("data/themed_report.json", "w") as f:
        json.dump(themes, f, indent=2)

    real_calls_this_stage = llm_utils.real_call_count() - start_call_count
    combined_real_calls = llm_utils.real_call_count()

    print()
    print(f"✓ Clustering complete")
    print(f"  Total themes: {len(themes)}")
    total_frequency = sum(t["frequency"] for t in themes)
    print(f"  Total points covered: {total_frequency}")
    print(f"  Real API calls this stage: {real_calls_this_stage}")
    print(f"  Combined real API calls (extract + cluster): {combined_real_calls}")
    print(f"  Written to: data/themed_report.json")

    # Verification
    if total_frequency != len(points):
        print(f"⚠ WARNING: Point count mismatch - extracted {len(points)}, but themed {total_frequency}")
    else:
        print(f"✓ Point reconciliation OK: {len(points)} points = {total_frequency} frequencies")


if __name__ == "__main__":
    cluster_and_score()
