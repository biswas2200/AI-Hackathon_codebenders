# DiscoveryOS — Build Specification

Build a Python prototype called **DiscoveryOS**: it ingests scattered product
research (interview transcripts, survey responses, support tickets), extracts
discrete customer pain points with an LLM, clusters near-duplicate pain
points into themes, scores themes by frequency × customer segment value, and
renders the result as a Streamlit dashboard with two views — a prioritized
report, and a force-directed traceability graph (Theme → Pain Point →
Source).

This is a hackathon prototype. Prioritize a working end-to-end pipeline over
polish. Do not add features not listed below.

**Rev 2 changes** (in response to external critique): added an in-UI "Run
Pipeline" button (§9) so the demo doesn't depend on terminal commands,
added live segment-weight sliders (§9) so priority re-sorts interactively
without new LLM calls, added an orphaned-point safety net (§7) so the
clustering call can't silently drop data, and added a deliberate
cross-vocabulary stress-test case (§4) to actually verify — not assume —
that clustering groups by root cause rather than surface wording. Batch
clustering was considered and explicitly rejected — see §10 for why.

**Rev 3 changes** (real account hit its actual rate limit — 5 RPM / 20 RPD
observed on Gemini 2.5 Flash, far tighter than any published estimate,
including the wrong one earlier in this doc's history): added a shared
`llm_utils.py` (§5) providing response caching, mock mode, and rate-limit-
aware retry/backoff, so dev iteration never re-spends real quota. Rewrote
extraction to batch 8-10 sources per call instead of 1 (§6: ~39 calls → 4-5)
and narrative generation to one call instead of one-per-theme (§7: ~9
calls → 1). Combined real-call budget for a full run: ~6-7, down from ~48.

**Rev 4 changes** (switched LLM provider from Gemini to Groq — the daily
lockout in Rev 3 made Gemini unusable for the rest of that day, and Groq's
free tier gives ~250-14,400 RPD depending on model, confirmed against both
an account screenshot and Groq's own docs, vs. Gemini's observed 20/day):
replaced the `google-genai` SDK with `groq` (OpenAI-compatible chat
completions API) throughout. Split model usage by task instead of one
model for everything: `llama-3.1-8b-instant` for high-volume extraction
(§6, RPD-generous but only 6K TPM, so batch size dropped to 4-5 sources),
`llama-3.3-70b-versatile` for clustering and narratives (§7, the calls
where reasoning quality matters most). The caching/mock-mode/retry design
from Rev 3 (§5) carries over unchanged in shape, just retargeted to the
new SDK's call signature and error types.

**Rev 5 changes**: added proactive per-model rate limiting (§5,
token-bucket) ahead of the reactive 429 handling from Rev 3 — the prior
design only reacted to a rate-limit error after it happened; this paces
requests to avoid triggering one in the first place, which is the standard
client-side pattern for LLM API consumption. Also made checkpointing an
explicit, named property of the existing cache (it was already there as a
side effect of deterministic cache keys, just undocumented) — a run that
dies partway through extraction resumes from where it stopped on rerun,
rather than re-spending quota on batches that already succeeded. See §10
for why no distributed-systems machinery (Redis, multi-worker locking, a
job queue) belongs in this build regardless.

**Rev 6 changes** (graph tab was unusable in the real embedded environment
— reported directly against a running instance, not caught by unit tests
that swap in a fake `pyvis.network.Network`): fixed four real, stacked
bugs in `pipeline/graph_builder.py` (§8) found only by driving an actual
browser against the actual Streamlit app, and added the interaction
controls needed to use the graph at real data volumes. In order hit:
`Network(..., physics=True)` doesn't exist as a constructor kwarg on the
installed pyvis version (crash); calling `show_buttons()` both before and
after `set_options()` crashes on the same version (crash); the default
`cdn_resources="local"` emits a `<script src="lib/bindings/utils.js">`
relative path that doesn't exist once this HTML is a string embedded in an
iframe, so vis-network's JS silently never loads (blank panel, no error) —
fixed by `cdn_resources="in_line"`, which embeds the JS/CSS directly; and
even once nodes existed, barnes_hut's -26000 gravitational constant vs. a
very weak centralGravity never converges, so the camera drifted away from
the graph with no bound in either direction ("the graph got lost") unless
something explicitly stopped physics and re-fit the view. Root-caused via
live instrumentation (not guessing): physics needed a bounded
`stabilization` pass that freezes physics once settled, and even then the
`<canvas>` element's pixel-buffer `width`/`height` *attributes* (distinct
from its CSS display size) stayed at their 0x0 initial value forever,
because vis-network's own resize detection never fires reliably inside a
Streamlit `st.components.v1.html()` iframe — confirmed by watching
`canvas.width` stay 0 through `network.setSize()` + `redraw()` + a forced
layout flush, all of which are supposed to sync it and didn't. The actual
fix sets `canvas.width`/`height` directly from the container's measured
rect. That still weren't enough on its own: Streamlit renders every tab's
content into the DOM up front and only toggles which one is
`display:block`, so all of the above (stabilization, `ResizeObserver`,
fixed-delay retries) can run — and silently fail to measure anything —
while the "Source Graph" tab is still hidden, since anything inside a
`display:none` ancestor always measures 0x0 regardless of its own CSS.
Fixed by polling every 200ms until the container's measured size is
actually nonzero, then fitting once and stopping — the one signal that's
true regardless of *why* or *when* the panel became visible, rather than
guessing at a delay. On top of those fixes: pyvis's built-in navigation
buttons (`"navigationButtons": true`) render with no visible icon under
`cdn_resources="in_line"` (their sprite reference doesn't survive
inlining) — clickable but invisible, which is worse than not having them
— so they're off in favor of custom plain-text/unicode zoom-in/zoom-out/
fit buttons that don't depend on any external asset. Added a client-side
zoom clamp (`network.on("zoom", ...)`, bounds relative to the fitted
scale) so scroll/pinch zoom can't run out to a vanishing point or in to a
meaningless blowup in either direction. Added a search box (matches
against an explicit `SEARCH_INDEX` built alongside the nodes — full
pain_point/quote/customer/source text, not just the truncated on-canvas
label) with prev/next cycling that calls `network.focus()` on the matching
node — necessary once the dataset is large enough that finding one node by
eye/scroll isn't practical. Also, `fit()` only accounts for node geometry,
not label text, so nodes at the computed edge still had their labels
clipped by the canvas boundary — pull back an extra ~18% after every fit
(both the automatic one and the "Fit" button's) so nodes and their labels
settle inside the visible area, not flush against it. And the toolbar
above added real height that `app.py`'s `st.components.v1.html(...,
height=770, scrolling=False)` was never widened to cover — with
`scrolling=False` there's no way to reach anything past a fixed height, so
the bottom of the graph was being silently clipped; bumped to
`height=1050` (§9) to cover the full page (750px canvas + ~150-200px
header — the toolbar's flex row wraps to a second line on narrower
viewports, adding more height there), not just the canvas alone. A first
attempt at `height=950` still clipped ~13px at a 956px-wide viewport,
confirmed against a real running instance. See §8 for the updated
concrete requirements.

**Rev 7 changes** (turn the working pipeline into a *professional demo
app*): (1) Grew the synthetic dataset from ~48 to ~90 sources (§4) —
richer graph/report — by adding recurring problems (data accuracy, mobile,
RBAC, API rate limits, alerting, collaboration) and more standalone
sources, keeping all four segments, three source types, and the
cross-vocabulary export stress pair. (2) Added an **in-app pipeline-mode
switch** (§9): green = "cached" (extraction served from the shipped cache,
only clustering + narratives run live ≈ 2 real calls, and the themes
regenerate slightly differently each run), red = "full live" (clear the
whole cache, re-extract everything ≈ 20 calls). It's built on a new
`llm_utils.clear_cache(prefixes)` (§5) that clears cache entries by
`cache_key` prefix — cached mode clears `cluster_`/`narratives_` only,
full mode clears all. Both modes write results to disk and refresh both
tabs. (3) Added a **light/dark toggle** (§9): the graph is fully
theme-aware via a new `theme` arg to `build_graph_html` (§8, swaps canvas
bg / label font / edge / header colors; node fill colors are shared), and
a `.streamlit/config.toml` sets the polished dark default plus a
best-effort CSS flip for the Streamlit chrome. (4) Transcribed the real
per-model limits from the account's Settings→Limits page into a documented
`MODEL_LIMITS` dict (§5) — both models 30 RPM, but 8b = 14.4K RPD / 6K TPM
vs 70b = 1K RPD / 12K TPM; only RPM is enforced client-side (the retry
handler covers TPM 429s). (5) The demo baseline is a **precompiled real
run** shipped in `data/` (§11): one 20-call run generated the real 93
pain points / 10 themes plus the extraction cache, so the app opens
populated and cached-mode Run Pipeline costs ~2 calls. That run surfaced
one quality issue — the clustering model left 22 of 93 points unclustered,
and the catch-all "Other / Unclustered" (which aggregates a high score
from holding many points) was ranking as "Top Priority"; fixed with two
no-API changes (regenerated off the *cached* clustering response, 0 new
calls): pin "Other / Unclustered" last in both `cluster_score.py` and
`app.py`'s live re-sort regardless of score, and strengthen the clustering
prompt (§7) to require assigning every point_id so future live runs drop
fewer. NOTE on process: all dev/testing was done in mock mode; exactly one
real ~20-call run was spent, then reused — the earlier 48-source real data
couldn't be reused because the volume changed.

---

## 1. Fixed tech stack — do not substitute

- Python 3.10+
- `groq` SDK for LLM calls (`from groq import Groq`) — OpenAI-compatible
  chat completions API, not the `google-genai`/Gemini SDK used in earlier
  revisions of this spec (see Rev 4 note above for why the switch happened)
- `streamlit` for the UI — not FastAPI, not Flask, not Dash. No separate
  frontend/backend split. This is a single-process local app.
- `pyvis` for the graph visualization (wraps vis.js, gives physics-based
  drag/zoom graphs — this is what renders the Obsidian-style node view)
- `pandas` for the tabular views
- No database. All state is flat JSON files on disk. No auth, no
  multi-user concerns, no deployment config.

**Two models, routed by task, not one model for everything:**
- `llama-3.1-8b-instant` for extraction (§6) — mechanical structured
  extraction, high call volume, needs the generous 14.4K RPD headroom this
  model gets. Its trade-off is a tight 6K TPM, so batch size is capped
  accordingly (§6).
- `llama-3.3-70b-versatile` for clustering and narrative generation (§7) —
  these are the calls where reasoning quality actually matters (this is
  the exact task the cross-vocabulary stress test in §4 is checking), and
  at only 1-2 calls total, its lower 1K RPD is irrelevant.

Auth: `GROQ_API_KEY` environment variable, read via `os.environ`. Fail
loudly with a clear message if unset — do not silently fall back to a mock.
Get a free key at https://console.groq.com — no credit card required.

**Rate limit reality check — read before writing any pipeline code**: do
not hardcode an assumed RPM/RPD/TPM budget anywhere without checking it
against the account's own dashboard first (Settings → Limits in the Groq
console). The numbers in this spec (30 RPM across all models; RPD ranging
250-14,400 depending on model; TPM ranging 6K-70K depending on model) come
from an actual account screenshot and are corroborated by Groq's own
published docs — trust them more than any general blog estimate, but still
verify against the live dashboard before a real run, the same lesson
learned the hard way with Gemini's free tier in an earlier revision.

---

## 2. Directory structure

```
discoveryos/
├── requirements.txt
├── README.md
├── data/
│   ├── generate_synthetic_data.py   # writes sources.json, no API key needed
│   ├── sources.json                 # generated
│   ├── extracted_pain_points.json   # generated by pipeline/extract.py
│   ├── themed_report.json           # generated by pipeline/cluster_score.py
│   └── .cache/                      # cached raw API responses, keyed by content hash
├── pipeline/
│   ├── llm_utils.py                 # shared: caching, mock mode, rate-limit handling
│   ├── extract.py
│   ├── cluster_score.py
│   └── graph_builder.py
└── app.py
```

---

## 3. Data contracts — exact schemas, do not deviate

**`data/sources.json`** (list of raw research items):
```json
{
  "id": "src_001",
  "source_type": "interview | survey | support_ticket",
  "customer_name": "string",
  "segment": "Enterprise | Mid-Market | SMB | Free",
  "date": "YYYY-MM-DD",
  "text": "raw transcript / response / ticket body"
}
```

**`data/extracted_pain_points.json`** (list, output of extraction stage):
```json
{
  "point_id": "src_001_p1",
  "source_id": "src_001",
  "source_type": "copied from source",
  "customer_name": "copied from source",
  "segment": "copied from source",
  "date": "copied from source",
  "pain_point": "short neutral 5-12 word description",
  "quote": "verbatim short excerpt, max ~20 words",
  "use_case": "Exporting data | Onboarding / setup | Integrations | Billing | Dashboard / reporting | Support"
}
```

**`data/themed_report.json`** (list, output of clustering/scoring stage):
```json
{
  "theme_name": "short punchy 3-6 word name",
  "theme_description": "1-2 sentence neutral description",
  "frequency": 8,
  "impact_score": 27,
  "segment_breakdown": {"Enterprise": 5, "SMB": 3},
  "use_case_breakdown": {"Exporting data": 8},
  "sample_quotes": ["...", "..."],
  "customers": ["Dana Park", "..."],
  "point_ids": ["src_001_p1", "..."],
  "executive_summary": "2-3 sentence PM-facing narrative, generated by LLM"
}
```
Sorted descending by `impact_score`.

---

## 4. Stage: `data/generate_synthetic_data.py`

Pure Python, no API calls, no dependencies beyond stdlib. Generates a
synthetic dataset for a fictional B2B SaaS analytics product (pick a name).

Requirements:
- ~90 total sources (Rev 7 — grown from the original ~35-40 for a
  richer-looking demo; the test floor is 80): mix of `interview` (longer,
  multi-topic, 2-3 paragraphs, includes an "Interviewer:" / customer
  speaker back-and-forth), `survey` (one sentence, single topic), and
  `support_ticket` (terse, problem-first, ticket-number style)
- 4 customer segments represented: `Enterprise`, `Mid-Market`, `SMB`, `Free`
- **Critical**: the data must contain the same underlying problems phrased
  differently across multiple sources and source types, so clustering has
  real signal to find (not just theater). Pick 5-8 recurring problems, e.g.:
  slow/failing large exports, a third-party integration silently breaking,
  confusing onboarding with no guided setup, unclear billing/invoicing,
  slow dashboard load times, no reusable report templates, degrading
  support response times. Each recurring problem should appear ~4-8 times
  across different sources/segments/wording.
- **Deliberate stress-test case**: for at least one recurring problem,
  include one Enterprise-segment source describing it in technical/formal
  register (e.g. "bulk export operations time out on datasets exceeding
  40k rows") and one Free or SMB-segment source describing the *identical*
  underlying failure in casual, non-technical language with almost no
  shared keywords (e.g. "the download thing just spins forever and never
  finishes, so annoying"). This exists to test whether clustering groups by
  root cause or by surface vocabulary — see §7 verification step.
- Output: `data/sources.json` matching the schema in §3.
- Print a summary count on completion (total sources, breakdown by type).

---

## 5. Shared module: `pipeline/llm_utils.py`

**Why this exists**: even on Groq's more generous free tier, an unbatched
pipeline making 1 call per source plus 1 call per theme (~48 calls) is
wasteful, and the fast extraction model's 6K TPM ceiling (§1) can still be
blown by an oversized batch. This module is what makes every real call
count, and lets the rest of the pipeline be tested without spending real
calls at all. Both `extract.py` and `cluster_score.py` import this and
never call the Groq SDK directly.

**`MODEL_LIMITS` — accurate to the account (Rev 7)**
- A dict of the real per-model limits transcribed from the account's own
  GroqCloud Settings→Limits page: `llama-3.1-8b-instant` = 30 RPM / 14.4K
  RPD / 6K TPM; `llama-3.3-70b-versatile` = 30 RPM / 1K RPD / 12K TPM.
  `MODEL_RPM` is derived from it for the limiter. Only RPM is enforced
  client-side (via `RateLimiter`); RPD/TPM are documented for accuracy but
  a TPM overage just surfaces as a 429 the retry handler waits out — an
  intentional simplicity trade-off for a single-process demo.

**`clear_cache(prefixes=None)` — drives the demo's pipeline-mode switch (Rev 7)**
- Deletes cache entries by their stored `cache_key` prefix (filenames are
  opaque sha256 hashes, so it reads each file's `cache_key`).
  `prefixes=["cluster_", "narratives_"]` clears only the clustering/
  narrative responses (leaving extraction cached → a rerun re-spends ~2
  calls); `prefixes=None` clears everything except the call-count file (a
  full live re-run). Never touches `_real_call_count.json`. The app's
  green/red switch (§9) calls this before launching the pipeline
  subprocesses.

**`RateLimiter` — proactive pacing, not just reactive retry (new in Rev 5)**
- A minimal token-bucket limiter, one instance per model (rate limits on
  Groq are enforced per-model, not globally — confirmed on the account's
  own Settings → Limits page, where each model row has its own separate
  RPM). Bucket capacity ~5 (allows a small natural burst), refill rate =
  `model_rpm / 60` tokens/second. Before every real call, `.acquire()`
  blocks (sleeps) until a token is available — this is what actually keeps
  the pipeline under the limit, rather than firing calls as fast as
  possible and hoping the account's remaining headroom absorbs it.
- This sits *in front of* the try/except 429 handling below, not instead
  of it — proactive pacing prevents most 429s from happening at all;
  reactive retry-with-backoff is the fallback for the ones that still
  slip through (e.g. if the account's real limit is lower than assumed, or
  another process is sharing the same key). Both layers exist because
  token-bucket pacing is the standard client-side pattern for LLM API
  consumption — it's what keeps a burst-prone loop (like the batch loop in
  §6) from ever looking like abuse to begin with, rather than apologizing
  for it after the fact.
- Skip the limiter entirely on a cache hit or in mock mode — there's no
  real network call to pace.

**`call_groq(client, model, prompt, json_mode=True, cache_key=None)`**
- If `cache_key` is given: before calling the API, check
  `data/.cache/{sha256(cache_key)}.json`. If present, load and return it —
  zero network calls. After any successful real call, write the response
  there before returning. This means re-running the pipeline after editing
  downstream code (Streamlit, graph builder, scoring math) never re-spends
  quota on extraction/clustering work that already succeeded. **This
  doubles as checkpointing** — if a run dies partway through §6's batch
  loop (crash, exhausted quota, network drop), rerunning the same script
  re-hits the cache for every batch that already succeeded and only spends
  real calls on the batches that didn't. Don't build a separate resume/
  checkpoint mechanism — the cache already is one, as long as
  `cache_key` is deterministic per batch (it is: hash of that batch's
  source ids) rather than including anything that changes between runs
  (like a timestamp).
- Call `rate_limiter_for(model).acquire()` immediately before the real
  network call (not before the cache check — a cache hit shouldn't wait on
  a rate limit it isn't using).
- Call shape: `client.chat.completions.create(model=model, messages=[
  {"role": "user", "content": prompt}], response_format={"type":
  "json_object"} if json_mode else None)`. Groq's API is OpenAI-compatible
  — response text is `response.choices[0].message.content`, not a
  Gemini-style `.text` attribute. Note: OpenAI-style `json_object` mode
  requires the word "json" to appear somewhere in the prompt itself, which
  every prompt template in §6-§7 already satisfies — don't strip that
  wording out during any future edit. Before finalizing, check whether
  Groq's docs currently offer a stricter schema-constrained mode (an
  equivalent of OpenAI's `json_schema` strict mode) beyond plain
  `json_object` — use it if available, since it further reduces malformed-
  JSON risk; fall back to `json_object` plus the existing try/except
  parsing if not.
- Wrap the real call in try/except for rate-limit errors (HTTP 429) as a
  fallback behind the proactive limiter above. Groq's 429 responses
  typically include a `Retry-After` header or an equivalent field in the
  error body — read it if present and sleep that exact duration before one
  retry. If no such header is available, fall back to: sleep ~20s and
  retry, up to 2 attempts, then **stop immediately** with a clear message
  pointing at the account's Groq console limits page rather than
  continuing to loop.

**`MOCK_MODE = os.environ.get("DISCOVERYOS_MOCK") == "1"`**
- When set, `call_groq` never touches the network — it returns
  hand-written, deterministic canned responses instead (not random; the
  same input should always produce the same fake output).
- Purpose: build and re-run the *entire* pipeline — schema handling, the
  orphaned-point safety net, the Streamlit UI, the graph — as many times as
  needed with zero real API spend. Reserve actual `GROQ_API_KEY` calls for
  one or two final integration runs, not for routine dev iteration.

**Mock fixtures required:**
- Mock batched-extraction response: given a batch of sources, return one
  plausible hardcoded pain point per source. Doesn't need to be smart —
  it's testing plumbing, not model quality.
- Mock clustering response: given a list of point_ids, group them into 2-3
  fake themes and **deliberately exclude 2 point_ids from every theme**.
  This isn't a bug — it's the fixture that proves the orphaned-point safety
  net in `cluster_score.py` actually works, without needing to hope the
  real model happens to drop something during your one precious real run.
- Mock narrative response: a fixed placeholder string per theme.

---

## 6. Stage: `pipeline/extract.py`

Reads `data/sources.json`. Extracts pain points in **batches of 4-5
sources per call** using `llama-3.1-8b-instant`. Batch size here is driven
by that model's 6K TPM ceiling (§1), not by call-count economics — RPD is
generous (14.4K/day) so call count isn't the binding constraint on this
model; token volume per minute is. If a batch's combined source text is
unusually long (e.g. several full interview transcripts land in the same
batch), drop to 3 sources for that batch rather than risk a TPM error.

**Exact prompt template to use (array of sources in, array of pain points
out, one call per batch):**
```
You are analyzing raw product research data (interview transcripts, survey
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
array — don't include empty placeholders.

SOURCES:
{sources_batch_json}
```

Note the response is wrapped in a top-level `{"pain_points": [...]}`
object rather than a bare array — Groq's `json_object` mode requires the
response be a JSON *object*, not a top-level array, which differs from how
the equivalent Gemini prompt was structured in earlier revisions. Unwrap
`response["pain_points"]` after parsing. This same wrapping requirement
applies to the clustering and narrative prompts in §7.

Implementation requirements:
- Split `sources.json` into batches of 4-5. Build `sources_batch_json` as
  `[{"id": ..., "text": ...}, ...]` per batch.
- Call via `call_groq(client, "llama-3.1-8b-instant", prompt,
  json_mode=True, cache_key=f"extract_batch_{hash of this batch's source
  ids}")`.
- Wrap `json.loads(response)["pain_points"]` in try/except; on failure,
  log a warning naming the batch and skip only that batch — a bad batch
  shouldn't cost you the other sources' worth of extraction.
- The model only returns `source_id`/`pain_point`/`quote`/`use_case`; look
  up `source_type`/`customer_name`/`segment`/`date` from the original
  source record by `source_id` to assemble the full
  `extracted_pain_points.json` schema (§3). Generate `point_id` as
  `{source_id}_p{n}` (n = running count within that source).
- Print progress per batch (`[batch i/total] extracting {n} sources...`)
  and a final total.
- Write final list to `data/extracted_pain_points.json`.
- **Expected real call count at batch size 4-5 across ~39 sources: 8-10
  calls.** Print this count at the end — still trivial against a 14.4K/day
  budget.

---

## 7. Stage: `pipeline/cluster_score.py`

Reads `data/extracted_pain_points.json`. **One** `llama-3.3-70b-versatile`
call clusters all points into themes (this was already a single call in
prior revisions — no change to call count here, and still correctly not
split into batches, see §10 for why that stays true). Narrative
generation: **one single call covering every theme**, also on
`llama-3.3-70b-versatile`, not one call per theme.

**Exact clustering prompt template:**
```
Below is a JSON array of customer pain points extracted from product
research (interviews, surveys, support tickets) for a B2B SaaS analytics
product.

Many of these describe the SAME underlying problem in different words
(e.g. "exports time out" and "CSV export failed after 25 minutes" are the
same theme).

Group them into a small number of THEMES (aim for 5-9 themes, don't
over-split). Return your answer as a JSON object with a single key
"themes", containing an array. Each item:
- "theme_name": short punchy name (3-6 words)
- "theme_description": 1-2 sentence neutral description of the underlying
  problem
- "point_ids": list of point_id values (from the input) belonging to this
  theme

PAIN POINTS:
{points}
```

**Exact narrative prompt template (ONE call, covering every theme at
once):**
```
You are writing product roadmap "problem space" report entries for a PM
audience. Below is a JSON array of themes. For EACH theme, write a tight
2-3 sentence executive summary explaining the problem and why it matters
for the business (reference segment/frequency naturally, don't just
restate the numbers). Do not use marketing language. Be direct and
specific.

Return your answer as a JSON object with a single key "summaries",
containing an array, one object per theme:
- "theme_name": copy the input theme_name exactly — used to match this
  summary back to the right theme
- "executive_summary": the 2-3 sentence narrative, plain text (not
  markdown)

THEMES:
{themes_json}
```

Implementation requirements:
- Clustering call: `call_groq(client, "llama-3.3-70b-versatile", prompt,
  json_mode=True, cache_key="cluster_" + hash of the full sorted point_id
  list)`. Unwrap `response["themes"]`.
- Narrative call: `call_groq(client, "llama-3.3-70b-versatile", prompt,
  json_mode=True, cache_key="narratives_" + hash of the theme name list)`
  — build `themes_json` from every theme's name/description/frequency/
  segments/sample quotes in one payload, send once, unwrap
  `response["summaries"]`, match `executive_summary` back onto each theme
  by `theme_name`.
- Segment weight table (business-value proxy — flag in code comments that
  these are placeholders for real ARR/deal-size data):
  ```python
  SEGMENT_WEIGHT = {"Enterprise": 5, "Mid-Market": 3, "SMB": 2, "Free": 1}
  ```
- `impact_score` = sum of `SEGMENT_WEIGHT[point.segment]` across all points
  in the theme (not just frequency — a theme with 3 Enterprise mentions
  should outrank one with 5 Free-tier mentions).
- Compute `segment_breakdown` and `use_case_breakdown` as counts per theme.
- `sample_quotes`: cap at 5 per theme.
- Sort final list descending by `impact_score`, **but pin
  `"Other / Unclustered"` last regardless of its score (Rev 7)** — it's a
  catch-all safety net, not a real prioritized theme, and it can accrue a
  high aggregate score just by holding many leftover points, which would
  misleadingly surface it as "Top Priority". `app.py`'s live weight-based
  re-sort applies the same rule (both use `sort(key=lambda t:
  (t["theme_name"] == "Other / Unclustered", -t["impact_score"]))`).
- The clustering prompt (Rev 7) also explicitly requires assigning **every**
  input `point_id` to exactly one theme (don't drop any) — a real run left
  22/93 points unclustered before this line was added.
- **Orphaned point check (required, not optional)**: the clustering call is
  not guaranteed to include every `point_id` it was given — the model can
  drop points without erroring (and does, at volume — see the 22/93 note
  above). After parsing the clustering response, compute
  `orphaned_ids = set(all extracted point_ids) - set(all point_ids across
  all returned themes)`. If non-empty, create one additional theme named
  `"Other / Unclustered"` containing those points (impact_score computed
  the same way as any other theme) and print a warning with the count. Never let extracted points silently vanish between
  `extracted_pain_points.json` and `themed_report.json` — the totals must
  reconcile. **This is directly testable in mock mode** — see §5's mock
  clustering fixture, which deliberately drops 2 point_ids on purpose.
- **Verification step for the stress-test case in §4**: after running,
  manually check whether the deliberate cross-vocabulary pair (Enterprise
  technical phrasing vs. Free/SMB casual phrasing of the same failure)
  landed in the same theme or split into two. If it split, strengthen the
  clustering prompt with an explicit line like: "Customers with different
  technical fluency may describe the same problem in very different words —
  cluster by underlying root cause, not by shared keywords or phrasing
  style." Don't assume the current prompt handles this correctly without
  checking — it's untested, and a smaller/faster model handling extraction
  vs. a larger model handling clustering makes this check more important,
  not less — verify `llama-3.3-70b-versatile` actually clears this bar.
- Write to `data/themed_report.json`.
- **Expected real call count for this whole stage: 2 (one clustering +
  one batched narrative call), down from ~9.** Print the running total of
  real (non-cached, non-mock) calls made across both `extract.py` and
  `cluster_score.py` combined — this is the number to check against the
  Groq console's remaining daily quota (Settings → Limits) before running
  anything again.

---

## 8. Stage: `pipeline/graph_builder.py`

A standalone function, not tied to Streamlit, so it's independently
testable:

```python
def build_graph_html(sources, points, themes, height="750px", theme="dark") -> str:
    ...
```

Requirements:
- **`theme` param (Rev 7)**: `"dark"` (default) or `"light"`, driven by the
  dashboard's appearance toggle (§9). It swaps the canvas background, node
  label font, edge colors, and header text between a `THEME_PALETTES`
  dark/light pair; node *fill* colors (theme orange, point gray, source
  colors) are shared because they read fine on both. Unknown values fall
  back to dark.
- Use `pyvis.network.Network` with a theme-appropriate background (dark =
  `bgcolor="#111318"`, `font_color="#e8e8e8"`; light = `#f7f7f9` /
  `#1a1a1a`), `cdn_resources="in_line"` (not the default
  `"local"`, which references a `lib/` folder that doesn't exist once this
  HTML is a string embedded in an iframe — see Rev 6). Physics via
  `barnes_hut` (repelling force layout, not a fixed hierarchical tree —
  nodes should settle organically like Obsidian's graph view), with a
  bounded `stabilization` pass (`iterations`, `fit: true`) — unbounded
  barnes_hut against a weak `centralGravity` never converges at real node
  counts and the graph drifts off-canvas indefinitely (Rev 6).
- Three node tiers, one edge type between each adjacent tier (no edges
  skipping a tier):
  - **Theme nodes**: color `#F2A65A`, size scales with `impact_score`
    (`16 + impact_score`), tooltip shows description + frequency + score
  - **Pain point nodes**: color `#8892A6`, fixed small size (~8), label
    truncated to ~30 chars, tooltip shows the full quote + use case +
    customer + segment
  - **Source nodes**: color keyed by `source_type` — interview `#5B8DEF`,
    survey `#4CAF7D`, support_ticket `#B565D9` — size ~6, tooltip shows
    source_type + segment + date + a text snippet (~180 chars)
  - Deduplicate source nodes (a source can be linked from multiple pain
    points, don't create it twice).
  - Build a parallel `search_index` alongside the nodes: `{id, type,
    label, text}` per node, where `text` is the full searchable content
    (pain_point + quote + use_case + customer + segment for a point;
    theme_name + description for a theme; id + type + segment + date +
    text snippet for a source) — not just the truncated on-canvas label.
    Embed it as a JSON literal in the page for the search box below.
- Edges: theme→point and point→source, dark subtle colors, no labels.
- **Do not enable pyvis's built-in `navigationButtons`** — under
  `cdn_resources="in_line"` they render with no visible icon (clickable
  but invisible, confirmed against a live instance — see Rev 6). Instead,
  inject custom plain-text/unicode zoom-in / zoom-out / fit buttons (no
  external asset dependency) into the header, plus a search `<input>` with
  prev/next buttons and a match counter that filters `search_index` and
  calls `network.focus(id, {...})` on the matching node.
- Client-side zoom clamp: on the `"zoom"` event, if `network.getScale()`
  falls outside `[MIN_SCALE, MAX_SCALE]` (bounds set relative to the
  scale `fit()` lands on, e.g. `0.15x`–`12x` of it), correct it via
  `network.moveTo({scale: clamped})` — unclamped scroll/pinch zoom can
  otherwise reach a vanishing point or a meaningless blowup in either
  direction.
- After every `fit()` (both the automatic one and the "Fit" button's),
  pull back an extra ~18% (`network.moveTo({scale: network.getScale() *
  0.82})`) — `fit()` only accounts for node geometry, not label text, so a
  node sitting exactly at the computed edge still has its label extending
  past it and getting clipped by the canvas boundary.
- **Visibility-aware fit, not a fixed-delay one**: freeze physics
  (`network.setOptions({physics: false})`) as soon as
  `"stabilizationIterationsDone"` fires (safe regardless of visibility),
  but do **not** assume that's also the right moment to fit the camera —
  Streamlit renders every tab's content into the DOM up front and only
  toggles which one is `display:block`, so this iframe's own script (and
  anything timer- or event-based inside it: `ResizeObserver`, `"resize"`,
  fixed-delay `setTimeout`s) can run to completion while the "Source
  Graph" tab is still hidden, and `getBoundingClientRect()` on anything
  inside a `display:none` ancestor always measures 0x0 regardless of its
  own CSS. Poll (e.g. every 200ms, with a generous give-up ceiling) until
  the graph container's measured rect is actually nonzero, **then**: set
  the `<canvas>` element's `width`/`height` *attributes* directly from
  that measured rect (vis-network's own `setSize()`/`redraw()` did not
  reliably sync that internal pixel buffer in this context — confirmed by
  live instrumentation showing `canvas.width` stuck at 0 even immediately
  after both), call `network.redraw()`, then `network.fit()`. Stop
  polling once this first fit succeeds; re-fit only on later genuine
  `window` resize events after that.
- Return `net.generate_html(notebook=False)` — a full standalone HTML
  string ready to embed in an iframe.
- **Test this module in isolation before wiring it into app.py** — but
  know the limits of a unit test here: a test that swaps in a fake
  `pyvis.network.Network` (as this build's own test suite does for most
  cases) can verify node/edge wiring and that specific JS snippets are
  present in the output string, but it cannot catch a real pyvis
  constructor-kwarg mismatch, a real vis-network runtime rendering bug, or
  a real Streamlit tab-visibility timing issue — all of which were found
  in this build only by driving an actual browser against the actual
  running app (Rev 6). Keep at least one test that builds against the
  *real* `pyvis.network.Network` (assert `"<html"` and an expected theme
  name appear), but treat "the unit tests pass" and "the graph actually
  renders in the browser" as two separate claims, and check the second
  one directly before calling this stage done.

---

## 9. Stage: `app.py`

Streamlit, single file, `st.set_page_config(layout="wide")`. Two tabs via
`st.tabs([...])`:

**Sidebar — Pipeline Control** (new, top of sidebar, above the segment
filter):
- **Pipeline-mode switch (Rev 7)**: an `st.toggle("Full live re-run")` with
  a colored status line below it — green `🟢 Cached` (off, default) vs red
  `🔴 Full live` (on). `run_pipeline(mode)` calls
  `llm_utils.clear_cache(...)` before the subprocesses: cached mode clears
  only `["cluster_", "narratives_"]` (extraction stays cached → ~2 real
  calls, themes regenerate live), full mode clears everything (~20 calls,
  re-extracts). This is the demo's "prove it's live but keep it cheap"
  control; the ~2-call cached path is the default and the recommended
  on-stage path.
- `st.button("▶ Run Pipeline")`. On click, run `pipeline/extract.py` then
  `pipeline/cluster_score.py` as blocking `subprocess.run([...], check=True)`
  calls, each wrapped in its own `st.spinner("...")` so the UI shows what
  stage is active. On success: `st.cache_data.clear()` (so the cached JSON
  loads fresh) then `st.rerun()` — results persist to disk and both tabs
  refresh. On failure (`CalledProcessError`): show `st.error` with the
  captured stderr, don't crash the app.
- **Appearance toggle (Rev 7)**: `st.toggle("🌙 Dark mode", value=True)`
  drives a `color_theme` of `"dark"`/`"light"` (named that, not `theme`,
  because `theme` is reused as a loop variable over the report entries —
  the collision silently passed a theme *dict* to the graph and crashed
  the tab until caught by a test). It's passed to `build_graph_html(...,
  theme=color_theme)` (fully theme-aware graph) and drives an
  `apply_theme()` CSS injection for the Streamlit chrome (best-effort —
  the graph is the fully-controlled part; Streamlit's own widgets are
  themed by `.streamlit/config.toml`).
- This does not need to be async or backgrounded — a synchronous blocking
  call with a spinner is the correct amount of engineering for this
  prototype. Do not add threading, job queues, or websocket progress
  streaming — that's scope creep for a 24-hour build.
- Keep the existing terminal-command flow working too (documented in
  README) — the button is an additional path, not a replacement. If the
  button fails for any environment reason, the demo still has a fallback.

**Sidebar — Segment Weights** (new, below pipeline control, above segment
filter):
- Four `st.slider` controls (range 1-10), one per segment, defaulting to
  the `SEGMENT_WEIGHT` values from `cluster_score.py` (Enterprise=5,
  Mid-Market=3, SMB=2, Free=1).
- These recompute `impact_score` **client-side in Streamlit**, live, as the
  user drags — `sum(slider_value[segment] * count for segment, count in
  theme["segment_breakdown"].items())` — and re-sort the theme list before
  rendering. This must never trigger new LLM calls; `segment_breakdown`
  counts are already stored per theme from the pipeline run, so this is a
  pure recompute over existing data. This is the "watch it re-prioritize
  live" demo moment — cheap to build, good payoff.

**Tab 1 — "📊 Prioritized Report"**
- Sidebar: multiselect filter by segment (options = union of all
  `segment_breakdown` keys across themes, default = all selected)
- 4 KPI columns (`st.metric`): theme count, total pain point count, distinct
  customer count, top-priority theme name — all recomputed against the
  filtered theme list
- `st.dataframe` table: Theme / Impact score / Frequency / Segments,
  sorted by the existing `impact_score` order
- Per-theme `st.expander`: executive summary text, two side-by-side
  `st.bar_chart` (segment breakdown, use-case breakdown), representative
  quotes as blockquotes, customer list

**Tab 2 — "🕸️ Source Graph"**
- One-line caption explaining the color legend (theme/point/interview/
  survey/ticket) and that it's draggable/zoomable
- Calls `build_graph_html(sources, points, themes)` and renders via
  `st.components.v1.html(graph_html, height=1050, scrolling=False)` —
  with `scrolling=False` there's no way to reach anything past this
  height, so it must cover the full returned page (750px canvas + the
  ~150-200px header this stage's search/zoom toolbar added in Rev 6,
  including the toolbar wrapping to a second line on narrower viewports),
  not just the canvas alone, or the bottom of the graph is silently
  clipped with no way to scroll to it (found against a real running
  instance, not caught by any unit test — see Rev 6).
- If `extracted_pain_points.json` or `sources.json` aren't found, show a
  `st.warning`, don't crash

Top-level: if `themed_report.json` doesn't exist, show `st.error` with the
exact pipeline commands to run first, then `st.stop()` — don't let the rest
of the file execute against missing data.

Load all three JSON files with `@st.cache_data`.

---

## 10. Non-goals — do not implement these

- Audio/video transcription (Whisper or otherwise) — text sources only
- FastAPI, Flask, or any separate backend/API layer
- Authentication, multi-user support, or a database
- Persistence across pipeline runs (each run overwrites the JSON files —
  no versioning/history needed for this prototype)
- True real-time/streaming pipeline progress (line-by-line log streaming
  from the subprocess) — the blocking-call-plus-spinner approach in §9 is
  sufficient; don't build a job queue or websocket layer for this
- **Any distributed-systems machinery** (Redis-backed rate limiting,
  multi-worker coordination, distributed locks, a message queue): this is
  a single local process by design (§1). The in-process token-bucket
  limiter and local file cache in §5 are sufficient and correct for that —
  don't reach for infrastructure that solves a multi-node problem this
  system doesn't have.
- **Batch clustering by use-case** (splitting the theme-clustering call
  into multiple smaller calls — not the same thing as the extraction/
  narrative call batching adopted in §6-§7, see the note there):
  considered and rejected for this build. At ~60-90 extracted pain points
  (~2-3K tokens as slim JSON), the dataset is nowhere near
  `llama-3.3-70b-versatile`'s context window (128K-token class) — there is
  no actual context-limit risk at this scale, only at genuinely
  production-scale volume. Splitting the clustering call now would add
  cross-batch theme-merging logic (a theme can legitimately span multiple
  use_cases) for zero benefit at current scale, and would *increase* call
  count in a budget where every call is scarce — the opposite of what's
  needed. The real risk this suggestion was pointing at — the model
  silently omitting point_ids — is handled directly via the orphaned-point
  check in §7 instead, which fixes the actual failure mode without adding
  unneeded architecture or spending
  more of the daily quota.

---

## 11. Acceptance criteria

The build is done when this sequence works with no manual intervention
beyond setting the API key:

```bash
pip install -r requirements.txt
export GROQ_API_KEY=...

# dev loop: build and re-test everything below with zero real API spend
export DISCOVERYOS_MOCK=1
python data/generate_synthetic_data.py
python pipeline/extract.py
python pipeline/cluster_score.py
streamlit run app.py

# once mock mode looks right end-to-end, do ONE real run
unset DISCOVERYOS_MOCK
python pipeline/extract.py
python pipeline/cluster_score.py
streamlit run app.py
```

Both tabs render without errors against the generated data, in both mock
and real mode. The graph tab shows a connected, physics-settled node
cluster (not a blank panel, not an unstyled default vis.js dump). Every
theme in Tab 1 is clickable/traceable to at least one source node in
Tab 2.

Additionally:
- The real run above makes **10-12 total API calls** (8-10 batched
  extraction on `llama-3.1-8b-instant` + 1 clustering + 1 batched
  narratives, both on `llama-3.3-70b-versatile`), not ~48. `extract.py`
  and `cluster_score.py` each print their own call count and a combined
  total at the end — check that total against the account's remaining
  daily quota in the Groq console (Settings → Limits) before running
  anything again.
- In mock mode, the deliberately-dropped 2 point_ids from §5's mock
  clustering fixture show up in an `"Other / Unclustered"` theme — this
  proves the orphaned-point safety net works without needing to wait for
  the real model to drop something by chance.
- **Checkpointing**: kill `pipeline/extract.py` partway through (e.g.
  Ctrl+C after 3 of 8 batches complete), then rerun it. The 3 completed
  batches must not re-call the API — check the printed call count reflects
  only the remaining batches. If a rerun re-processes everything from
  scratch, the cache key isn't deterministic (§5) and needs fixing.
- **Rate limiting**: during a real run, no call should fire faster than
  the configured token-bucket rate allows for that model — if the 8-10
  extraction calls complete in under a couple seconds total, the limiter
  isn't actually pacing anything and needs a second look.
- Clicking "▶ Run Pipeline" from a clean `data/` directory (no
  `extracted_pain_points.json` or `themed_report.json` present) produces a
  fully populated dashboard with no terminal interaction at all.
- Dragging any segment weight slider visibly re-sorts the Tab 1 theme table
  with no delay and no new API calls (check this by watching for network
  activity — there should be none).
- The count of pain points in `extracted_pain_points.json` equals the sum
  of `frequency` across every theme in `themed_report.json`, including the
  `"Other / Unclustered"` theme if one was created. If these numbers don't
  match in a *real* (non-mock) run, the orphaned-point check in §7 has a
  bug — data is being lost silently, which is the one failure mode this
  spec explicitly guards against.
- The deliberate cross-vocabulary source pair from §4 lands in the same
  theme in a real run. If not, the clustering prompt was strengthened per
  the §7 verification step — confirm that happened, don't leave it
  unresolved.

If anything in this spec is ambiguous or the model/library behaves
differently than described (e.g. a Groq SDK method signature has changed,
or a stricter JSON schema mode is available beyond `json_object`),
implement the closest reasonable interpretation and leave a comment marking
the deviation — don't silently guess.
