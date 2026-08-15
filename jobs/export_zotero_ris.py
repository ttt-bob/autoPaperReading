"""Export papers as Zotero-friendly RIS files grouped by PDF folder."""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "papers.db"
PDF_ROOT = ROOT / "data" / "pdfs"
OUT_DIR = ROOT / "data" / "zotero_import"


RIS_TAGS = {
    "TY",
    "ID",
    "TI",
    "AU",
    "AB",
    "PY",
    "KW",
    "UR",
    "L1",
    "N1",
    "ER",
}


def clean_ris_text(value: str | None) -> str:
    """Keep RIS field values on one logical line."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def multiline_field(tag: str, value: str | None) -> list[str]:
    if tag not in RIS_TAGS:
        raise ValueError(f"Unknown RIS tag: {tag}")
    if not value:
        return []

    lines = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.rstrip()
        if line:
            lines.append(f"{tag}  - {line}")
    return lines


def split_authors(authors: str | None) -> list[str]:
    if not authors:
        return []
    return [a.strip() for a in authors.split(",") if a.strip()]


def split_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    return [t.strip() for t in tags.split(",") if t.strip()]


def published_year(published: str | None) -> str:
    if not published:
        return ""
    match = re.match(r"(\d{4})", published)
    return match.group(1) if match else ""


def find_local_pdfs() -> dict[str, Path]:
    pdfs = {}
    for path in PDF_ROOT.glob("*/*.pdf"):
        pdfs[path.stem] = path
    return pdfs


def load_papers() -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT paper_id, title, authors, abstract, published, pdf_url, entry_url, summary, tags
            FROM papers
            ORDER BY lower(title)
            """
        )
        return list(cur.fetchall())
    finally:
        conn.close()


def paper_to_ris(row: sqlite3.Row, pdf_path: Path, category: str) -> str:
    lines = [
        "TY  - JOUR",
        f"ID  - {clean_ris_text(row['paper_id'])}",
        f"TI  - {clean_ris_text(row['title'])}",
    ]

    for author in split_authors(row["authors"]):
        lines.append(f"AU  - {clean_ris_text(author)}")

    year = published_year(row["published"])
    if year:
        lines.append(f"PY  - {year}")

    abstract = clean_ris_text(row["abstract"])
    if abstract:
        lines.append(f"AB  - {abstract}")

    for tag in split_tags(row["tags"]):
        lines.append(f"KW  - {clean_ris_text(tag)}")
    lines.append(f"KW  - {clean_ris_text(category)}")

    url = clean_ris_text(row["entry_url"] or row["pdf_url"])
    if url:
        lines.append(f"UR  - {url}")

    lines.append(f"L1  - {pdf_path.resolve().as_uri()}")

    note_header = (
        f"分类: {category}\n"
        f"arXiv: {row['paper_id']}\n"
        f"PDF: {row['pdf_url'] or ''}\n\n"
        "自动总结:\n"
    )
    lines.extend(multiline_field("N1", note_header + (row["summary"] or "")))
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"


def write_ris_files(output_dir: Path) -> tuple[int, dict[str, int], int]:
    pdfs = find_local_pdfs()
    grouped: dict[str, list[str]] = defaultdict(list)
    missing_pdf = 0

    for row in load_papers():
        pdf_path = pdfs.get(row["paper_id"])
        if not pdf_path:
            missing_pdf += 1
            continue
        category = pdf_path.parent.name
        grouped[category].append(paper_to_ris(row, pdf_path, category))

    output_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    all_records = []
    for category in sorted(grouped):
        records = grouped[category]
        counts[category] = len(records)
        all_records.extend(records)
        (output_dir / f"{category}.ris").write_text("\n".join(records), encoding="utf-8")

    (output_dir / "all_papers.ris").write_text("\n".join(all_records), encoding="utf-8")
    return sum(counts.values()), counts, missing_pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR,
        help="Directory for generated RIS files.",
    )
    args = parser.parse_args()

    total, counts, missing_pdf = write_ris_files(args.out_dir)
    print(f"Exported {total} papers to {args.out_dir}")
    for category, count in sorted(counts.items()):
        print(f"- {category}: {count}")
    if missing_pdf:
        print(f"Skipped {missing_pdf} database records without a local PDF")


if __name__ == "__main__":
    main()
