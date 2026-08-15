# Repository Guidelines

## Project Structure & Module Organization

Core pipeline code lives in `rag/` and `jobs/`. Use `rag/` for reusable modules such as arXiv fetching, PDF parsing, LLM access, tag normalization, and SQLite storage. Use `jobs/` for runnable entry points like `daily_ingest.py`, `daily_digest.py`, `export_papers.py`, and `ingest_url.py`. Static site assets for GitHub Pages live in `docs/`. Runtime data is stored under `data/` and `logs/`; treat both as generated output, not source. Root scripts such as `run_daily.sh` and `run_local.sh` orchestrate common workflows.

## Build, Test, and Development Commands

Install dependencies with `uv sync`. Run the full daily pipeline with `./run_daily.sh`, or resume an interrupted run with `./run_daily.sh --resume`. Run individual jobs with `uv run python jobs/daily_ingest.py --max-results 10 --days-back 7`, `uv run python jobs/daily_digest.py --today-only`, and `uv run python jobs/export_papers.py`. For local UI checks, use `python3 -m http.server 8080 --directory docs` or `uv run streamlit run app.py`.

## Coding Style & Naming Conventions

Target Python 3.10+ and follow the existing style: 4-space indentation, snake_case for functions and variables, and concise module-level docstrings when useful. Keep new modules focused and place shared logic in `rag/` instead of duplicating it across jobs. Ruff is the configured linter; run `uv run ruff check .`. The project uses a 100-character line length and import sorting via Ruff’s `I` rules.

## Testing Guidelines

There is no dedicated automated test suite yet. For code changes, validate with the narrowest runnable command that exercises the affected path, then run `uv run ruff check .`. Examples: rerun `jobs/export_papers.py` after frontend data changes, or use `jobs/ingest_url.py <arxiv-url>` for single-paper ingestion fixes. If you add tests, place them in a top-level `tests/` package and name files `test_*.py`.

## Commit & Pull Request Guidelines

Recent history uses short prefixes like `feat:` and `fix:` plus occasional automated content updates such as `📚 Update papers 2026-05-24`. Follow the same pattern: imperative subject, specific scope, and no mixed concerns in one commit. Pull requests should describe the user-visible impact, list validation commands, note any config or data migrations, and include screenshots only when `docs/` UI behavior changes.

## Security & Configuration Tips

Keep secrets in `.env`; never commit API keys. Treat `config.yaml`, `data/papers.db`, and generated JSON in `docs/` carefully when changing schemas or export formats, because the daily pipeline and GitHub Pages output depend on them staying compatible.
