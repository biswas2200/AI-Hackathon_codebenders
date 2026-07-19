#!/usr/bin/env python3
"""
Extract discrete pain points from raw customer research using Groq.
Reads: data/sources.json
Outputs: data/extracted_pain_points.json
"""

import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Running as `python pipeline/extract.py` puts pipeline/ on sys.path, not
# the project root -- add the root so `from pipeline import llm_utils` (an
# absolute package import) resolves regardless of how this script is invoked.
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
MODEL = "llama-3.1-8b-instant"

PRODUCT_NAME = "DataVault"

# Batch size is driven by this model's 6K TPM ceiling, not call-count
# economics -- RPD is generous (14.4K/day) so token volume per minute is
# the binding constraint here.
BATCH_SIZE = 5
LONG_BATCH_SIZE = 3
LONG_TEXT_CHAR_THRESHOLD = 4000

PROMPT_TEMPLATE = """You are analyzing raw product research data (interview transcripts, survey
responses, support tickets) for a B2B SaaS analytics product called
{PRODUCT_NAME}.

Below is a JSON array of sources, each with an "id" and "text". For EACH
source, extract every DISTINCT pain point / problem the customer describes.
Ignore small talk, praise, or interviewer questions. A source may yield 0,
1, or several pain points.

Return your answer as a JSON object with a single key "pain_points",
containing an array. Each item in the array:
- "source_id": the id of the source this pain point came from
- "pain_point": a short (5-12 word) neutral description of the problem
- "quote": the most representative short excerpt from the text supporting
  it (max ~20 words)
- "use_case": what the customer was doing when they hit it (e.g.
  "Exporting data", "Onboarding / setup", "Integrations", "Billing",
  "Dashboard / reporting", "Support")

If a source has no pain points, it simply contributes no items to the
array -- don't include empty placeholders.

SOURCES:
{sources_batch_json}"""


def _make_batches(sources):
    """Split sources into batches of BATCH_SIZE, dropping to LONG_BATCH_SIZE
    when a batch's combined text is long enough to risk the 6K TPM ceiling."""
    batches = []
    i = 0
    n = len(sources)
    while i < n:
        candidate = sources[i:i + BATCH_SIZE]
        if sum(len(s["text"]) for s in candidate) > LONG_TEXT_CHAR_THRESHOLD:
            candidate = sources[i:i + LONG_BATCH_SIZE]
        batches.append(candidate)
        i += len(candidate)
    return batches


def _batch_cache_key(batch):
    ids = sorted(s["id"] for s in batch)
    digest = hashlib.sha256("|".join(ids).encode("utf-8")).hexdigest()[:16]
    return f"extract_batch_{digest}"


def extract_pain_points():
    """Main extraction function."""

    # Load sources
    with open("data/sources.json") as f:
        sources = json.load(f)

    sources_by_id = {s["id"]: s for s in sources}
    batches = _make_batches(sources)

    llm_utils.reset_call_count()
    start_call_count = llm_utils.real_call_count()

    extracted_points = []
    failed_batches = []
    point_count_by_source = defaultdict(int)

    print(f"Extracting pain points from {len(sources)} sources in {len(batches)} batches...")
    print()

    for batch_idx, batch in enumerate(batches, 1):
        batch_ids = [s["id"] for s in batch]
        print(f"[batch {batch_idx}/{len(batches)}] extracting {len(batch)} sources ({', '.join(batch_ids)})...",
              end=" ", flush=True)

        sources_batch_json = json.dumps([{"id": s["id"], "text": s["text"]} for s in batch])
        prompt = PROMPT_TEMPLATE.format(
            PRODUCT_NAME=PRODUCT_NAME,
            sources_batch_json=sources_batch_json
        )
        cache_key = _batch_cache_key(batch)

        try:
            response_text = llm_utils.call_groq(
                client, MODEL, prompt, json_mode=True, cache_key=cache_key
            )
            batch_points = json.loads(response_text)["pain_points"]
        except Exception as e:
            print(f"✗ (batch failed: {str(e)[:80]}, skipping)")
            failed_batches.append((batch_ids, str(e)))
            continue

        for point in batch_points:
            source_id = point.get("source_id")
            source = sources_by_id.get(source_id)
            if source is None:
                continue  # model hallucinated a source_id not in this batch

            point_count_by_source[source_id] += 1
            point_id = f"{source_id}_p{point_count_by_source[source_id]}"

            extracted_points.append({
                "point_id": point_id,
                "source_id": source_id,
                "source_type": source["source_type"],
                "customer_name": source["customer_name"],
                "segment": source["segment"],
                "date": source["date"],
                "pain_point": point.get("pain_point", ""),
                "quote": point.get("quote", ""),
                "use_case": point.get("use_case", "")
            })

        print(f"✓ ({len(batch_points)} points)")

    # Write output
    os.makedirs("data", exist_ok=True)
    with open("data/extracted_pain_points.json", "w") as f:
        json.dump(extracted_points, f, indent=2)

    real_calls_this_stage = llm_utils.real_call_count() - start_call_count

    print()
    print(f"✓ Extraction complete")
    print(f"  Total points extracted: {len(extracted_points)}")
    if failed_batches:
        print(f"  Failed batches: {len(failed_batches)}")
        for batch_ids, err in failed_batches[:3]:
            print(f"    - {batch_ids}: {err[:80]}")
    print(f"  Real API calls this stage: {real_calls_this_stage}")
    print(f"  Written to: data/extracted_pain_points.json")


if __name__ == "__main__":
    extract_pain_points()
