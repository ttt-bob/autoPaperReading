import unittest
from pathlib import Path

from rag import pdf_parser


class BuildPdfPathTest(unittest.TestCase):
    def test_category_override_controls_pdf_directory(self):
        path, category = pdf_parser.build_pdf_path(
            "2401.00001v1",
            title="A Dataset with no GUI keyword",
            abstract="",
            category_override="gui",
        )

        self.assertEqual(category, "gui")
        self.assertEqual(path, Path("data/pdfs/gui/2401.00001v1.pdf"))


if __name__ == "__main__":
    unittest.main()
