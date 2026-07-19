# DiscoveryOS: Product Discovery & User Research Intelligence 

https://ai-hackathoncodebenders-h6depjf2v27vqmyjcac8ao.streamlit.app/

![Status](https://img.shields.io/badge/status-production--ready-brightgreen)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 🎯 The Problem: Why DiscoveryOS Exists

### The Challenge

Customer research is scattered and ignored:

- **🔍 Fragmented sources**: Insights live in recordings, transcripts, notes, support tickets, and surveys — spread across different systems and platforms with no unified view
- **🧠 Reliance on memory**: When planning roadmaps, teams rely on what they remember ("I think someone mentioned X") instead of checking actual evidence
- **❌ Missed insights**: Valuable customer feedback gets lost because no one systematically connects the patterns across multiple sources
- **📊 Poor prioritization**: Teams build the wrong features for the wrong users because decisions are based on intuition, not data

### The Outcome

- ❌ Misaligned product roadmaps
- ❌ Wasted engineering effort
- ❌ Missed revenue opportunities
- ❌ Increased customer churn

---

## 💡 The Solution: What DiscoveryOS Does

**An AI-powered research analyst** that ingests messy, fragmented customer data and outputs clean, actionable insights ready for roadmap planning.

### Input Pipeline

DiscoveryOS accepts and processes:
- Interview recordings & transcripts
- Survey responses
- Support conversations & tickets
- Customer call notes
- User research documents

### The AI Analysis Engine

The system performs:

1. **Extract pain points** — Identify what problems customers mention across all sources
2. **Find patterns** — Discover which problems repeat and with what frequency
3. **Segment by user type** — Understand which problems affect which customer segments
4. **Score business impact** — Determine which problems matter most (revenue impact, churn rate, scale)
5. **Connect the dots** — Link insights across sources to reveal systemic issues

### Output: Prioritized Problem Space Report

A structured, actionable report organized by four key dimensions:

#### **1. Themes**
Problem categories extracted from all sources
- Example: "Data export friction," "Onboarding confusion," "Integration gaps," "Analytics reporting delays"

#### **2. User Segments**
Which customer types experience which problems
- Example: "Enterprise IT teams," "Mid-market operations," "Solo freelancers," "Non-technical founders"

#### **3. Frequency**
How often each problem is mentioned across data sources
- Example: "Mentioned in 18 of 50 interviews," "3 support tickets per week," "Present in 45% of survey responses"

#### **4. Business Impact**
Why solving this problem matters to the business
- Example: "Affects $5M revenue at risk," "70% of high-value customer churn cite this," "Blocks expansion into enterprise segment"

---

## 🏗️ Architecture Overview

```
Data Sources (interviews, surveys, tickets)
        ↓
┌─────────────────────────────────────┐
│  Pipeline Stage 1: Extract          │
│  ├─ Groq API: llama-3.1-8b          │
│  └─ 4-5 sources per batch           │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│  Pipeline Stage 2: Cluster & Score  │
│  ├─ Groq API: llama-3.3-70b         │
│  ├─ Cluster themes                  │
│  └─ Generate narratives             │
└─────────────────────────────────────┘
        ↓
┌─────────────────────────────────────┐
│  Dashboard Display (Streamlit)      │
│  ├─ Tab 1: Prioritized Report       │
│  ├─ Tab 2: Interactive Graph        │
│  └─ Live segment weight controls    │
└─────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Groq API key (free tier available at https://console.groq.com)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/discoveryos.git
cd discoveryos

# Install dependencies
pip install -r requirements.txt

# Set your Groq API key
export GROQ_API_KEY=your_key_here
```

### Running the App

```bash
# Generate synthetic data
python data/generate_synthetic_data.py

# Run the pipeline (extract → cluster → score)
python pipeline/extract.py
python pipeline/cluster_score.py

# Launch the dashboard
streamlit run app.py
```

The app will open at `http://localhost:8501`

### Using the In-App Pipeline Control

1. **Pipeline Mode Toggle** (Green/Red):
   - 🟢 **Cached** (default): Use cached extraction, only run clustering (~2 API calls, cheap)
   - 🔴 **Full live**: Re-extract everything (~20 API calls, slower but fresh)

2. **Segment Weight Sliders**: Drag to re-prioritize themes live (no API calls)

3. **Dark/Light Toggle**: Switch graph theme

---

## 📊 Dashboard Features

### Tab 1: 📊 Prioritized Report

- **KPI Metrics**: Theme count, pain points, distinct customers, top priority
- **Sortable Table**: Themes ranked by business impact
- **Interactive Expansion**: Per-theme summaries, charts, quotes, customer lists
- **Segment Filter**: Focus on specific customer segments

### Tab 2: 🕸️ Source Graph

- **Interactive Force-Directed Graph**: Obsidian-style visualization
- **Three Node Types**:
  - 🟠 **Themes** (orange) - sized by impact score
  - ⚫ **Pain Points** (gray) - connected to themes
  - 🔵 **Sources** (colored) - interviews, surveys, support tickets
- **Controls**:
  - Drag to move, scroll to zoom, click to select
  - Search bar with prev/next navigation
  - Zoom in/out/fit buttons
  - Zoom clamping prevents getting lost

---

## 🛠️ Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **LLM Provider** | Groq (llama-3.1-8b, llama-3.3-70b) | Fast, cost-effective extraction & clustering |
| **Dashboard** | Streamlit | Interactive web UI, no separate backend |
| **Graph Viz** | pyvis + vis.js | Physics-based node graph |
| **Data Storage** | JSON files | Persistent state on disk |
| **Caching** | File-based cache | Avoid re-spending API quota |
| **Rate Limiting** | Token bucket | Proactive pacing, prevent 429 errors |

---

## 📈 API Call Efficiency

**Goal**: Minimize Groq API usage while maximizing data quality

### Batching Strategy
- **Extraction**: 4-5 sources per call (respects 6K TPM limit)
- **Clustering**: 1 call for all themes
- **Narratives**: 1 batched call for all summaries

### Real Run Statistics
- ✅ **Extraction**: 8-10 calls (vs. 40+ unbatched)
- ✅ **Clustering**: 2 calls (1 cluster + 1 narratives)
- ✅ **Total**: ~10-12 calls per full run
- ✅ **Cost**: ~$0.01-0.02 per complete run

### Caching Advantage
- **First run**: Full pipeline with real API calls
- **Cached run**: Only ~2 new API calls (clustering + narratives only)
- **Resume support**: Killed mid-run? Restart picks up from cache

---

## 🧪 Testing

### Mock Mode (Zero API Cost)

```bash
# Test the entire pipeline without spending API quota
export DISCOVERYOS_MOCK=1
python data/generate_synthetic_data.py
python pipeline/extract.py
python pipeline/cluster_score.py
streamlit run app.py
```

### Real Integration Test

```bash
# One real run to verify everything works end-to-end
unset DISCOVERYOS_MOCK
python pipeline/extract.py
python pipeline/cluster_score.py
streamlit run app.py
```

---

## 📁 Project Structure

```
discoveryos/
├── README.md                          # This file
├── PROBLEM_STATEMENT.md               # Detailed problem definition
├── SOLUTION_DISCOVERY_OS.md           # Technical specification
├── requirements.txt                   # Python dependencies
├── app.py                             # Main Streamlit dashboard
├── main.py                            # Entry point
├── data/
│   ├── generate_synthetic_data.py     # Generate test data
│   ├── sources.json                   # Input data (generated)
│   ├── extracted_pain_points.json     # Stage 1 output
│   ├── themed_report.json             # Stage 2 output
│   └── .cache/                        # LLM response cache
├── pipeline/
│   ├── llm_utils.py                   # Shared: caching, rate limiting, mock mode
│   ├── extract.py                     # Stage 1: Extract pain points
│   ├── cluster_score.py               # Stage 2: Cluster & score themes
│   └── graph_builder.py               # Graph visualization builder
└── .streamlit/
    └── config.toml                    # Streamlit configuration
```

---

## 🔑 Key Features

### ✅ Intelligent Extraction
- Extracts distinct pain points from raw customer data
- Preserves customer context (segment, source type, date)
- Captures representative quotes and use cases

### ✅ Smart Clustering
- Groups semantically similar pain points regardless of wording
- Cross-vocabulary matching (technical vs. non-technical)
- Handles orphaned points with safety net

### ✅ Business Impact Scoring
- Weights customers by segment (Enterprise > SMB > Free)
- Calculates impact score: `sum(segment_weight × frequency)`
- Ranks themes by real business value, not just frequency

### ✅ Live Re-Prioritization
- Drag segment weight sliders to re-sort instantly
- No API calls needed (pure client-side math)
- Watch themes reorder based on your business assumptions

### ✅ Full Traceability
- Click any theme → see all pain points in it
- Click any pain point → see source quote + context
- Verify every insight traces back to original customer voice

### ✅ Efficient API Usage
- Batched extraction (4-5 sources per call)
- Response caching (avoid re-spending quota)
- Rate limiting (stay under RPM/TPM limits)
- Mock mode for dev iteration

---

## 📋 Data Schemas

### Input: sources.json
```json
{
  "id": "src_001",
  "source_type": "interview|survey|support_ticket",
  "customer_name": "Dana Park",
  "segment": "Enterprise|Mid-Market|SMB|Free",
  "date": "2024-01-15",
  "text": "raw customer research text"
}
```

### Output: themed_report.json
```json
{
  "theme_name": "Export Performance Issues",
  "theme_description": "Bulk data exports time out on large datasets",
  "frequency": 8,
  "impact_score": 27,
  "segment_breakdown": {"Enterprise": 5, "SMB": 3},
  "sample_quotes": ["exports just spin forever", "bulk exports fail"],
  "customers": ["Dana Park", "..."],
  "point_ids": ["src_001_p1", "..."],
  "executive_summary": "8 customers across Enterprise/SMB segments report..."
}
```

---

## 🚦 Rate Limiting & API Safety

DiscoveryOS implements multi-layer protection:

1. **Proactive Rate Limiting**: Token bucket algorithm prevents hitting limits
2. **Reactive Retry**: Handles 429 errors with exponential backoff
3. **Response Caching**: Avoids re-spending quota on same inputs
4. **Checkpointing**: Resume from cache if interrupted mid-run
5. **Call Tracking**: Monitor real API usage vs. daily budget

**Groq Free Tier Limits** (verified from account dashboard):
- `llama-3.1-8b-instant`: 30 RPM, 14.4K RPD, 6K TPM
- `llama-3.3-70b-versatile`: 30 RPM, 1K RPD, 12K TPM

---

## 🤖 LLM Models Used

### Extraction: `llama-3.1-8b-instant`
- **Why**: Fast, cost-effective, generous RPD for batched calls
- **Task**: Mechanical pain point extraction
- **Calls per run**: 8-10 (batched)

### Clustering & Narratives: `llama-3.3-70b-versatile`
- **Why**: Superior reasoning for semantic clustering
- **Tasks**: Group similar pain points, generate narratives
- **Calls per run**: 2 (1 cluster + 1 batched narratives)

---

## 📊 Example Output

### Prioritized Report Shows:
```
Top Priority: Export Performance (Impact Score: 27)
├─ Frequency: 8 customers
├─ Segments: 5 Enterprise, 3 SMB
├─ Quote: "bulk exports just time out and never finish"
└─ Executive Summary: Enterprise customers report consistent failures 
   with large dataset exports (40k+ rows), causing ~2 day delays in 
   reporting workflows. This blocks expansion into data warehouse segment.
```

### Graph Visualization:
```
                    [Export Performance] (orange, large)
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
   [Export timeout]  [Batch fails]      [CSV errors]
        ↓                   ↓                   ↓
   [Interview-001]  [Support-003]      [Survey-015]
```

---

## 🔄 Workflow Example

### Step 1: Prepare Data
```bash
python data/generate_synthetic_data.py
# → Creates data/sources.json with ~90 synthetic sources
```

### Step 2: Run Pipeline
```bash
python pipeline/extract.py
# → Calls Groq 8-10 times
# → Outputs: data/extracted_pain_points.json

python pipeline/cluster_score.py
# → Calls Groq 2 times
# → Outputs: data/themed_report.json
```

### Step 3: Explore in Dashboard
```bash
streamlit run app.py
# → Launch browser to http://localhost:8501
# → See prioritized report in Tab 1
# → Explore graph in Tab 2
# → Adjust segment weights live
```

---

## 🎓 What This Project Demonstrates

✅ **LLM Integration**: Efficient, batched, cached Groq API calls
✅ **Data Processing**: Multi-stage pipeline with deterministic caching
✅ **UI/UX**: Interactive Streamlit dashboard with live reactivity
✅ **Graph Visualization**: Physics-based force-directed graph
✅ **Rate Limiting**: Token bucket + retry backoff
✅ **Testing**: Mock mode for zero-cost iteration
✅ **Data Traceability**: Full audit trail from insight back to source

---

## 🛡️ Non-Goals (What This Isn't)

❌ **NOT** a summarization tool that condenses conversations
❌ **NOT** a note-taking system
❌ **NOT** a simple transcript parser
❌ **NOT** a multi-user SaaS platform
❌ **NOT** a distributed system (single-process by design)

---

## 📝 Documentation

- **[PROBLEM_STATEMENT.md](./PROBLEM_STATEMENT.md)** - Detailed problem analysis
- **[SOLUTION_DISCOVERY_OS.md](./SOLUTION_DISCOVERY_OS.md)** - Complete technical specification (Rev 7)
- **[This README](./README.md)** - Quick start and overview

---

## 🤝 Contributing

Contributions welcome! Areas for enhancement:

- [ ] Multi-file upload (CSV, PDF, etc.)
- [ ] Real-time transcription integration (Whisper)
- [ ] Export reports to various formats (PDF, PowerPoint)
- [ ] Advanced filtering and grouping
- [ ] Historical tracking (compare reports across time)

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🙋 Support

Having issues?

1. **Check mock mode first**: `export DISCOVERYOS_MOCK=1` to test without API
2. **Verify API key**: `echo $GROQ_API_KEY`
3. **Check Groq dashboard**: https://console.groq.com → Settings → Limits
4. **Review logs**: Pipeline stages print detailed progress

---

## 🎯 Success Criteria Met

✅ Evidence-backed insights (traced to source data)
✅ Ranked by business impact (not just frequency)
✅ Segment-aware analysis
✅ Actionable for roadmap planning
✅ Comprehensive coverage (no insights lost)
✅ Scalable to hundreds of sources

---

## 🚀 Deployment Ready

This project is **production-ready**:

- ✅ All Streamlit deprecations migrated (`st.components.v1.html` → `st.iframe`)
- ✅ Groq API integration verified
- ✅ Rate limiting implemented
- ✅ Caching working correctly
- ✅ Mock mode for testing
- ✅ Error handling robust

---

## 📞 Contact

Questions? Issues? Suggestions?

Open an issue on GitHub or reach out directly.

---

**Built with ❤️ for product teams who want to make data-driven decisions**

*Last Updated: July 2026*
*DiscoveryOS - Turn scattered research into clear product priorities*
