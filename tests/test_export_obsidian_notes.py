import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jobs import export_obsidian_notes


class ExportNotesTest(unittest.TestCase):
    def test_exports_note_when_title_contains_path_separators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "papers.db"
            pdf_root = root / "pdfs"
            vault = root / "vault"
            pdf_root.mkdir()
            self._create_db(
                db_path,
                title="PerceptUI: LLM Agents as Human-Aligned Synthetic Users for UI/UX Evaluation",
            )

            with (
                patch.object(export_obsidian_notes, "DB_PATH", db_path),
                patch.object(export_obsidian_notes, "PDF_ROOT", pdf_root),
            ):
                total, counts = export_obsidian_notes.export_notes(vault)

            self.assertEqual(total, 1)
            self.assertEqual(counts, {"uncategorized": 1})
            note_files = list((vault / "uncategorized").glob("*.md"))
            self.assertEqual(len(note_files), 1)
            self.assertNotIn("/", note_files[0].name)
            self.assertIn("UI UX Evaluation", note_files[0].name)

    def _create_db(self, db_path: Path, title: str) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT,
                    authors TEXT,
                    abstract TEXT,
                    published TEXT,
                    pdf_url TEXT,
                    entry_url TEXT,
                    summary TEXT,
                    tags TEXT,
                    affiliations TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO papers (
                    paper_id, title, authors, abstract, published,
                    pdf_url, entry_url, summary, tags, affiliations, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2606.05697v1",
                    title,
                    "A. Author",
                    "Abstract",
                    "2026-06-01",
                    "https://arxiv.org/pdf/2606.05697v1",
                    "https://arxiv.org/abs/2606.05697v1",
                    "Summary",
                    "gui",
                    "",
                    "2026-06-24",
                ),
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
