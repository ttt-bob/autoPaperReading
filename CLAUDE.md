# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoPaperReading automatically fetches daily CV papers from arXiv, downloads PDFs, generates Chinese structured summaries via LLM (DeepSeek/Ollama/OpenAI), stores metadata in SQLite, and publishes to GitHub Pages.

## Key Commands

```bash
# Full daily pipeline (fetch → summarize → digest → export → commit → push)
./run_daily.sh

# Resume from interruption
./run_daily.sh --resume

# Backfill specific date via arXiv submittedDate API
./run_daily.sh --date YYYY-MM-DD

# Auto mode for cron/launchd (skips if already succeeded today)
./run_daily.sh --auto

# Override defaults via env vars
MAX_RESULTS=100 DAYS_BACK=30 BATCH_SIZE=15 ./run_daily.sh

# Run individual steps
uv run python jobs/daily_ingest.py --max-results 10 --days-back 7
uv run python jobs/daily_ingest.py --date 2026-05-20
uv run python jobs/daily_digest.py --today-only
uv run python jobs/daily_digest.py --published-date YYYY-MM-DD
uv run python jobs/export_papers.py --cloud

# Manual single-paper ingest
uv run python jobs/ingest_url.py https://arxiv.org/abs/1706.03762
uv run python jobs/ingest_url.py 1706.03762
uv run python jobs/ingest_url.py URL --force

# Backfill missing affiliations (extract from existing summaries, no re-LLM)
uv run python jobs/daily_ingest.py --reprocess-missing

# Tag normalization: preview changes, then apply
uv run python scripts/normalize_tags.py
uv run python scripts/normalize_tags.py --apply

# Export papers.json for frontend
uv run python jobs/export_papers.py
uv run python jobs/export_papers.py --cloud

# Local preview
cd docs && python -m http.server 8080
uv run streamlit run app.py
```

## Architecture

### Data Flow

```
run_daily.sh (orchestrator)
  ├─ daily_ingest.py    — fetch arXiv → download PDF → parse text → LLM summarize → SQLite save
  ├─ daily_digest.py    — query DB by created_at or published date → generate Markdown brief
  ├─ export_papers.py   — dump all papers to docs/papers.json + CSS cache busting
  ├─ git commit         — staged docs/papers.json, docs/favorites.json, docs/index.html
  └─ git push           — push to origin master (HTTPS, credential.helper=store)
```

### Key Modules

| Module | Path | Responsibility |
|--------|------|---------------|
| arxiv_fetcher | `rag/arxiv_fetcher.py` | arXiv API query (supports `submittedDate` range syntax + 429 exponential backoff) |
| pdf_parser | `rag/pdf_parser.py` | PDF download (categorized by task type, 429 retry) and text extraction via PyMuPDF |
| summarizer | `rag/summarizer.py` | LLM summarization, tag inference (constrained to allowed_tags), affiliation extraction |
| tag_utils | `rag/tag_utils.py` | Tag normalization: fuzzy matching, manual mapping, dedup — shared by summarizer + daily_ingest |
| db | `rag/db.py` | SQLite storage (papers, ingest_log, favorite_tags, custom_tags) |
| llm_client | `rag/llm_client.py` | Unified client: DeepSeek > Ollama > OpenAI (auto-detected from env) |
| daily_ingest | `jobs/daily_ingest.py` | Main pipeline: batch fetch → dedup → PDF download → summarize → save → normalize tags |
| normalize_tags | `scripts/normalize_tags.py` | One-time backfill: normalizes existing DB tags to allowed_tags using fuzzy + manual mapping |
| daily_digest | `jobs/daily_digest.py` | Report generation: one-line brief (default) or full Markdown |
| export_papers | `jobs/export_papers.py` | JSON export (includes code_url, local_pdf_path) + CSS version cache busting |
| ingest_url | `jobs/ingest_url.py` | Single-paper URL/ID ingest with retry and force-reprocess |

### Tag Normalization

Tags are normalized through three layers to keep them within `config.yaml` → `allowed_tags`:

1. **LLM prompt constraint** — `rag/summarizer.py` asks LLM to pick only from allowed_tags
2. **Post-filter** — `summarizer.infer_tags_from_summary()` drops tags not in allowed_tags (case-insensitive)
3. **Fuzzy + manual mapping** — shared `rag/tag_utils.py` runs SequenceMatcher + MANUAL_MAP (e.g. `Image-to-Text` → `image captioning`) as a second pass after infer_tags and again in daily_ingest after DB save

Unmatchable tags are **preserved** (not dropped) with a warning to add them to `config.yaml`.

### Database Schema (SQLite: `data/papers.db`)

- **papers**: paper_id (PK), title, authors, abstract, published (ISO date str), summary, tags, affiliations, is_read, is_favorite, created_at, updated_at
- **ingest_log**: run_date, papers_found/new/skipped/failed
- **favorite_tags**: paper_id + tag (unique pair)
- **custom_tags**: user-defined tag presets

Papers are identified by arXiv short ID. `published` is the arXiv submission date; `created_at` is DB insertion time. Duplicates handled via `INSERT OR REPLACE` on `paper_id`.

### run_daily.sh State Machine

State file: `.run_state` (format: `RUN_ID|STEP|TIMESTAMP`)

Steps: `none → ingest → digest → export → commit → push → done`

- `--resume` skips completed steps
- `--auto` writes `.daily_done` on success; subsequent same-day invocations skip
- `set -e` ensures any failure aborts (no partial runs marked done)

### LLM Backend Selection

Priority in `llm_client.py`:
1. DeepSeek API (if `DEEPSEEK_API_KEY` is set in `.env`)
2. Ollama local (if reachable at `OLLAMA_BASE_URL`)
3. OpenAI API (if `OPENAI_API_KEY` is set)

### arXiv API Details

- Endpoint: `https://export.arxiv.org/api/query`
- 1 API call per run (page_size=50, max_results typically 5-10)
- Up to max_results PDF downloads (direct HTTP GET to arxiv.org/pdf/...)
- 429 handling: library retries (num_retries=3) + outer 5-attempt exponential backoff (15-250s)
- `submittedDate:[YYYYMMDD TO YYYYMMDD]` syntax supported for date-specific queries (passes through `arxiv` library unchanged)

## Configuration

- **config.yaml**: topics list, LLM model, per-source limits
- **.env**: API keys (DEEPSEEK_API_KEY, OPENAI_API_KEY, OLLAMA_BASE_URL)
- **pyproject.toml**: uv-managed Python dependencies; no build step
- **.gitignore**: PDFs, database, logs excluded from version control

## Scheduled Automation (macOS)

launchd plist at `~/Library/LaunchAgents/com.user.paperdaily.plist` runs `./run_daily.sh --auto` at 10/12/14/16/18 daily. View: `launchctl list com.user.paperdaily`. Cancel: `launchctl unload ~/Library/LaunchAgents/com.user.paperdaily.plist`.
