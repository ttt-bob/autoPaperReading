#!/usr/bin/env python3
"""
Sync OS-Agent-Survey paper list and ingest newly added GUI papers.

The stored JSON file is treated as the external-source snapshot. Daily runs only
ingest entries that are newly added to the upstream README after that snapshot,
so historical backlog papers are not imported repeatedly.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
README_URL = (
    "https://raw.githubusercontent.com/OS-Agent-Survey/OS-Agent-Survey/main/README.md"
)
SOURCE_URL = "https://github.com/OS-Agent-Survey/OS-Agent-Survey"
OUTPUT_PATH = ROOT / "data" / "os_agent_survey_papers.json"
DB_PATH = ROOT / "data" / "papers.db"

LOG = logging.getLogger("sync_os_agent_survey")


@dataclass(frozen=True)
class SurveyPaper:
    date: str
    title: str
    url: str
    section: str


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    value = value.replace("&amp;", "&")
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value: str) -> str:
    return re.sub(r"\W+", " ", clean_text(value)).lower().strip()


def normalize_url(url: str) -> str:
    url = clean_text(url)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(f"{SOURCE_URL}/blob/main/", url)


def source_key(paper: SurveyPaper) -> str:
    return f"{normalize_title(paper.title)}|{paper.url.lower()}"


def parse_date(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", value):
        return value.replace("/", "-")
    month_match = re.fullmatch(r"(\d{1,2})/(\d{4})", value)
    if month_match:
        month, year = month_match.groups()
        return f"{year}-{int(month):02d}"
    return value


def sort_date(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}$", value):
        return f"{value}-01"
    return value


def parse_readme(markdown: str) -> list[SurveyPaper]:
    papers: list[SurveyPaper] = []
    section = ""
    list_pattern = re.compile(
        r"^\s*\d+\.\s+\[(\d{4}/\d{2}/\d{2})\]\s+(.+?)\s+"
        r"\[\[paper\]\(([^)]+)\)\]",
        re.IGNORECASE,
    )

    for line in markdown.splitlines():
        heading = re.match(r"^#+\s+(.+)", line)
        if heading:
            section = clean_text(heading.group(1))
            continue

        list_match = list_pattern.match(line)
        if list_match:
            date, title, url = list_match.groups()
            papers.append(
                SurveyPaper(
                    date=parse_date(date),
                    title=clean_text(title),
                    url=normalize_url(url),
                    section=section,
                )
            )
            continue

        if not line.startswith("|") or "[[paper]" not in line:
            continue
        cells = [clean_text(cell) for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].startswith(":") or cells[0].lower() == "paper":
            continue

        link_match = re.search(r"\[\[paper\]\(([^)]+)\)\]", line, re.IGNORECASE)
        if not link_match:
            continue

        date = ""
        for cell in cells:
            if re.fullmatch(r"\d{1,2}/\d{4}", cell):
                date = parse_date(cell)
                break

        papers.append(
            SurveyPaper(
                date=date,
                title=cells[0],
                url=normalize_url(link_match.group(1)),
                section=section or "Tables",
            )
        )

    seen: set[str] = set()
    unique: list[SurveyPaper] = []
    for paper in papers:
        key = source_key(paper)
        if key in seen:
            continue
        seen.add(key)
        unique.append(paper)

    unique.sort(key=lambda paper: (sort_date(paper.date), paper.title.lower()), reverse=True)
    return unique


def read_markdown(readme_url: str, readme_path: Path | None = None) -> str:
    if readme_path:
        return readme_path.read_text(encoding="utf-8")
    response = requests.get(readme_url, timeout=60)
    response.raise_for_status()
    return response.text


def load_previous(path: Path) -> list[SurveyPaper] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    return [
        SurveyPaper(
            date=item.get("date", ""),
            title=item.get("title", ""),
            url=item.get("url", ""),
            section=item.get("section", ""),
        )
        for item in papers
    ]


def write_listing(path: Path, papers: list[SurveyPaper], *, dry_run: bool = False) -> bool:
    payload = {
        "source": SOURCE_URL,
        "generated_at": datetime.now().date().isoformat(),
        "count": len(papers),
        "papers": [asdict(paper) for paper in papers],
    }

    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable_existing = {k: v for k, v in existing.items() if k != "generated_at"}
        comparable_new = {k: v for k, v in payload.items() if k != "generated_at"}
        if comparable_existing == comparable_new:
            LOG.info("OS-Agent-Survey listing already up to date: %s papers", len(papers))
            return False

    if dry_run:
        LOG.info("Dry run: would update %s with %s papers", path, len(papers))
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOG.info("Updated %s: %s papers", path, len(papers))
    return True


def merge_with_previous_snapshot(
    previous: list[SurveyPaper] | None,
    current: list[SurveyPaper],
) -> list[SurveyPaper]:
    """Append newly seen papers without shrinking the committed snapshot."""
    if previous is None:
        return current

    merged = list(previous)
    seen = {source_key(paper) for paper in merged}
    for paper in current:
        key = source_key(paper)
        if key in seen:
            continue
        merged.append(paper)
        seen.add(key)

    merged.sort(key=lambda paper: (sort_date(paper.date), paper.title.lower()), reverse=True)
    return merged


def extract_arxiv_id(value: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?", value)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", value)
    return match.group(1) if match else ""


def is_ingestable_url(url: str) -> bool:
    lower = url.lower()
    return bool(
        extract_arxiv_id(url)
        or lower.endswith(".pdf")
        or "openreview.net/pdf" in lower
        or "proceedings.neurips" in lower
        or "aclanthology.org" in lower
    )


def load_local_index() -> tuple[set[str], set[str], set[str]]:
    if not DB_PATH.exists():
        return set(), set(), set()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT paper_id, title, entry_url, pdf_url FROM papers")
    rows = cur.fetchall()
    conn.close()

    titles: set[str] = set()
    urls: set[str] = set()
    arxiv_ids: set[str] = set()
    for row in rows:
        titles.add(normalize_title(row["title"] or ""))
        for value in (row["paper_id"], row["entry_url"], row["pdf_url"]):
            value = value or ""
            if value:
                urls.add(value.lower())
            arxiv_id = extract_arxiv_id(value)
            if arxiv_id:
                arxiv_ids.add(arxiv_id)
            elif re.fullmatch(r"\d{4}\.\d{4,5}v\d+", value):
                arxiv_ids.add(value.split("v", 1)[0])
    return titles, urls, arxiv_ids


def paper_exists_locally(paper: SurveyPaper, local_index: tuple[set[str], set[str], set[str]]) -> bool:
    titles, urls, arxiv_ids = local_index
    arxiv_id = extract_arxiv_id(paper.url)
    return (
        normalize_title(paper.title) in titles
        or paper.url.lower() in urls
        or bool(arxiv_id and arxiv_id in arxiv_ids)
    )


def ingest_paper(paper: SurveyPaper, *, skip_summary: bool = False) -> bool:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from jobs import ingest_url
    from rag import db

    db.init_db()
    config = ingest_url.load_config()
    kind, url, arxiv_id = ingest_url.parse_input(paper.url)

    if kind == ingest_url.InputKind.ARXIV:
        metadata = ingest_url.fetch_arxiv_paper(arxiv_id or "")
    else:
        metadata = ingest_url.fetch_metadata_from_pdf(url, config, save_category="gui")

    return ingest_url.process_paper(
        metadata,
        config,
        force=False,
        skip_summary=skip_summary,
        save_category="gui",
    )


def sync(args: argparse.Namespace) -> int:
    markdown = read_markdown(args.readme_url, args.readme_path)
    papers = parse_readme(markdown)
    previous = load_previous(args.output)

    if previous is None and not args.ingest_initial:
        LOG.info("No previous snapshot found; creating baseline without ingesting backlog.")
        write_listing(args.output, papers, dry_run=args.dry_run)
        return 0

    previous_keys = {source_key(paper) for paper in previous or []}
    new_entries = [paper for paper in papers if source_key(paper) not in previous_keys]
    local_index = load_local_index()
    candidates = [
        paper
        for paper in new_entries
        if is_ingestable_url(paper.url) and not paper_exists_locally(paper, local_index)
    ]
    if args.max_new is not None:
        candidates = candidates[: args.max_new]

    LOG.info(
        "Parsed %s papers; new since snapshot: %s; ingest candidates: %s",
        len(papers),
        len(new_entries),
        len(candidates),
    )

    if previous is not None and not new_entries:
        LOG.info("No new upstream entries; snapshot unchanged.")
        return 0

    if args.no_ingest or args.dry_run:
        for paper in candidates:
            LOG.info("Candidate: %s | %s | %s", paper.date, paper.title, paper.url)
        write_listing(
            args.output,
            merge_with_previous_snapshot(previous, papers),
            dry_run=args.dry_run,
        )
        return 0

    failures = 0
    saved = 0
    for paper in candidates:
        try:
            LOG.info("Ingesting: %s | %s", paper.date, paper.title)
            if ingest_paper(paper, skip_summary=args.skip_summary):
                saved += 1
        except Exception as exc:
            failures += 1
            LOG.exception("Failed to ingest %s: %s", paper.url, exc)

    if failures:
        LOG.warning("Not updating snapshot because %s candidate(s) failed.", failures)
        return 1

    write_listing(args.output, merge_with_previous_snapshot(previous, papers), dry_run=False)
    LOG.info("OS-Agent-Survey sync done; ingested %s new paper(s).", saved)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme-url", default=README_URL)
    parser.add_argument("--readme-path", type=Path, help="Use a local README file instead of HTTP")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--max-new", type=int, default=None, help="Limit newly discovered papers to ingest")
    parser.add_argument("--no-ingest", action="store_true", help="Only refresh the source listing")
    parser.add_argument("--ingest-initial", action="store_true", help="Ingest entries on first snapshot creation")
    parser.add_argument("--skip-summary", action="store_true", help="Download and store metadata without summary")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print actions without writing")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    raise SystemExit(sync(build_parser().parse_args()))


if __name__ == "__main__":
    main()
