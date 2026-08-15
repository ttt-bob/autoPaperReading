import hashlib
import tempfile
import unittest
from pathlib import Path

from jobs.ingest_url import InputKind, _build_pdf_url_download_path, load_inputs, parse_input


class LoadInputsTest(unittest.TestCase):
    def test_combines_cli_inputs_and_file_inputs_ignoring_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "urls.txt"
            path.write_text(
                "\n".join(
                    [
                        "",
                        "# awesome-gui-agent",
                        "https://arxiv.org/abs/1802.08802",
                        "  https://arxiv.org/pdf/2408.00203  ",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                load_inputs(["1706.03762"], str(path)),
                [
                    "1706.03762",
                    "https://arxiv.org/abs/1802.08802",
                    "https://arxiv.org/pdf/2408.00203",
                ],
            )


class ParseInputTest(unittest.TestCase):
    def test_arxiv_version_suffix_is_normalized_for_api_queries(self):
        raw = "https://arxiv.org/abs/2504.12679v1"

        self.assertEqual(parse_input(raw), (InputKind.ARXIV, raw, "2504.12679"))
        self.assertEqual(parse_input("2407.09295v2"), (InputKind.ARXIV, "2407.09295v2", "2407.09295"))

    def test_arxiv_html_url_is_supported(self):
        raw = "https://arxiv.org/html/2407.09295v2"

        self.assertEqual(parse_input(raw), (InputKind.ARXIV, raw, "2407.09295"))

    def test_pdf_download_endpoint_without_pdf_suffix_is_supported(self):
        urls = [
            "https://ojs.aaai.org/index.php/AAAI/article/download/37715/41677",
            (
                "https://www.sciencedirect.com/science/article/pii/S0924271624003563/"
                "pdfft?isDTMRedir=true&download=true"
            ),
            "https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=10637992",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(parse_input(url), (InputKind.PDF_URL, url, None))


class PdfUrlDownloadPathTest(unittest.TestCase):
    def test_save_category_controls_pdf_url_download_path(self):
        url = "https://example.com/paper.pdf"
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]

        paper_id, path = _build_pdf_url_download_path(url, "gui")

        self.assertEqual(paper_id, f"pdf_{digest}")
        self.assertEqual(path, Path(f"data/pdfs/gui/pdf_{digest}.pdf"))


if __name__ == "__main__":
    unittest.main()
