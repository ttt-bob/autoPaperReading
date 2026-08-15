"""Export paper summaries into an Obsidian vault."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "papers.db"
PDF_ROOT = ROOT / "data" / "pdfs"
DEFAULT_VAULT = ROOT / "data" / "obsidian_vault"
UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|#\[\]^]+')


def slugify(value: str, max_len: int = 90) -> str:
    value = UNSAFE_FILENAME_CHARS.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_len].strip() or "untitled"


def yaml_scalar(value: str | None) -> str:
    if not value:
        return '""'
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def wiki_target(path: Path) -> str:
    return path.with_suffix("").as_posix()


def wiki_link(path: Path, label: str | None = None) -> str:
    target = wiki_target(path)
    if label and label != target:
        return f"[[{target}|{label}]]"
    return f"[[{target}]]"


def find_local_pdfs() -> dict[str, Path]:
    return {path.stem: path for path in PDF_ROOT.glob("*/*.pdf")}


def load_papers() -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT paper_id, title, authors, abstract, published,
                   pdf_url, entry_url, summary, tags, affiliations, created_at
            FROM papers
            ORDER BY published DESC, paper_id
            """
        )
        return list(cur.fetchall())
    finally:
        conn.close()


def make_note(
    row: sqlite3.Row,
    pdf_path: Path | None,
    category: str,
    category_note: Path,
    tag_notes: dict[str, Path],
    related: list[tuple[sqlite3.Row, Path]],
) -> str:
    tags = split_csv(row["tags"])
    tag_lines = "\n".join(f"  - {yaml_scalar(tag)}" for tag in tags)
    if not tag_lines:
        tag_lines = "  []"

    pdf_uri = pdf_path.resolve().as_uri() if pdf_path else ""
    published = (row["published"] or "")[:10]
    tag_links = [wiki_link(tag_notes[tag], tag) for tag in tags if tag in tag_notes]

    lines = [
        "---",
        f"paper_id: {yaml_scalar(row['paper_id'])}",
        f"title: {yaml_scalar(row['title'])}",
        f"category: {yaml_scalar(category)}",
        f"published: {yaml_scalar(published)}",
        f"arxiv: {yaml_scalar(row['entry_url'])}",
        f"pdf_url: {yaml_scalar(row['pdf_url'])}",
        f"local_pdf: {yaml_scalar(pdf_uri)}",
        "tags:",
        tag_lines,
        "---",
        "",
        f"# {row['title'] or row['paper_id']}",
        "",
        f"- Paper ID: `{row['paper_id']}`",
        f"- Category: {wiki_link(category_note, category)}",
        f"- Authors: {row['authors'] or ''}",
        f"- Published: {published}",
        f"- arXiv: {row['entry_url'] or ''}",
    ]
    if pdf_uri:
        lines.append(f"- Local PDF: [Open PDF]({pdf_uri})")
    if row["pdf_url"]:
        lines.append(f"- Online PDF: {row['pdf_url']}")
    if tag_links:
        lines.append(f"- Tags: {', '.join(tag_links)}")
    if row["affiliations"]:
        lines.append(f"- Affiliations: {row['affiliations']}")
    if related:
        lines.extend(["", "## Related Papers", ""])
        for related_row, related_path in related:
            title = related_row["title"] or related_row["paper_id"]
            lines.append(f"- {wiki_link(related_path, title)}")

    lines.extend(
        [
            "",
            "## Abstract",
            "",
            row["abstract"] or "",
            "",
            "## 自动总结",
            "",
            row["summary"] or "",
            "",
        ]
    )
    return "\n".join(lines)


def export_notes(vault_dir: Path) -> tuple[int, dict[str, int]]:
    pdfs = find_local_pdfs()
    counts: dict[str, int] = {}
    papers = load_papers()
    note_paths: dict[str, Path] = {}
    paper_categories: dict[str, str] = {}
    tag_notes: dict[str, Path] = {}
    papers_by_tag: dict[str, list[sqlite3.Row]] = {}

    (vault_dir / ".obsidian").mkdir(parents=True, exist_ok=True)
    (vault_dir / ".obsidian" / "app.json").write_text(
        '{\n  "alwaysUpdateLinks": true,\n  "newFileLocation": "current",\n'
        '  "attachmentFolderPath": "attachments"\n}\n',
        encoding="utf-8",
    )
    (vault_dir / ".obsidian" / "graph.json").write_text(
        '{\n  "showTags": true,\n  "showAttachments": false,\n'
        '  "hideUnresolved": false,\n  "showOrphans": true\n}\n',
        encoding="utf-8",
    )

    index_lines = [
        "# Auto Paper Reading",
        "",
        "This vault is generated from `data/papers.db`.",
        "",
        "## Categories",
        "",
    ]

    for row in papers:
        pdf_path = pdfs.get(row["paper_id"])
        category = pdf_path.parent.name if pdf_path else "uncategorized"
        paper_categories[row["paper_id"]] = category
        filename = f"{row['paper_id']} - {slugify(row['title'] or '')}.md"
        note_paths[row["paper_id"]] = Path(category) / filename
        counts[category] = counts.get(category, 0) + 1
        for tag in split_csv(row["tags"]):
            tag_notes.setdefault(tag, Path("_tags") / f"{slugify(tag, 60)}.md")
            papers_by_tag.setdefault(tag, []).append(row)

    total = 0
    for row in papers:
        pdf_path = pdfs.get(row["paper_id"])
        category = paper_categories[row["paper_id"]]
        category_dir = vault_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        seen: set[str] = set()
        related: list[tuple[sqlite3.Row, Path]] = []
        for tag in split_csv(row["tags"]):
            for related_row in papers_by_tag.get(tag, []):
                paper_id = related_row["paper_id"]
                if paper_id == row["paper_id"] or paper_id in seen:
                    continue
                seen.add(paper_id)
                related.append((related_row, note_paths[paper_id]))
                if len(related) >= 8:
                    break
            if len(related) >= 8:
                break

        note_path = vault_dir / note_paths[row["paper_id"]]
        category_note = Path("_categories") / f"{slugify(category, 60)}.md"
        note_path.write_text(
            make_note(row, pdf_path, category, category_note, tag_notes, related),
            encoding="utf-8",
        )
        total += 1

    categories_dir = vault_dir / "_categories"
    categories_dir.mkdir(parents=True, exist_ok=True)
    for category in sorted(counts):
        category_note = Path("_categories") / f"{slugify(category, 60)}.md"
        index_lines.append(f"- {wiki_link(category_note, category)}: {counts[category]}")
        category_lines = [
            "---",
            f"category: {yaml_scalar(category)}",
            "---",
            "",
            f"# {category}",
            "",
        ]
        for row in papers:
            if paper_categories[row["paper_id"]] == category:
                category_lines.append(f"- {wiki_link(note_paths[row['paper_id']], row['title'])}")
        (vault_dir / category_note).write_text("\n".join(category_lines), encoding="utf-8")

    tags_dir = vault_dir / "_tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    index_lines.extend(["", "## Tags", ""])
    for tag in sorted(tag_notes, key=str.lower):
        tag_note = tag_notes[tag]
        tag_rows = papers_by_tag.get(tag, [])
        index_lines.append(f"- {wiki_link(tag_note, tag)}: {len(tag_rows)}")
        tag_lines = [
            "---",
            f"tag: {yaml_scalar(tag)}",
            "---",
            "",
            f"# {tag}",
            "",
        ]
        for row in tag_rows:
            tag_lines.append(f"- {wiki_link(note_paths[row['paper_id']], row['title'])}")
        (vault_dir / tag_note).write_text("\n".join(tag_lines), encoding="utf-8")

    index_lines.append("")
    (vault_dir / "README.md").write_text("\n".join(index_lines), encoding="utf-8")

    return total, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help="Obsidian vault directory to write.",
    )
    args = parser.parse_args()

    total, counts = export_notes(args.vault)
    print(f"✅ Obsidian notes exported: {args.vault}")
    print(f"   Papers: {total}")
    for category, count in sorted(counts.items()):
        print(f"   - {category}: {count}")


if __name__ == "__main__":
    main()
