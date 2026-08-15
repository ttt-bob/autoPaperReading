import unittest

from jobs.sync_os_agent_survey import (
    SurveyPaper,
    merge_with_previous_snapshot,
    parse_readme,
    source_key,
)


class ParseReadmeTest(unittest.TestCase):
    def test_parses_full_list_and_table_entries(self):
        markdown = """
## Tables

| Paper | Model | Date | Link |
|:------|:------|:-----|:-----|
| OS-ATLAS: A Foundation Action Model for Generalist GUI Agents | OS-Atlas | 10/2024 | [[paper](https://arxiv.org/abs/2410.23218)] |

### Safety & Privacy
1. [2025/02/18] Evaluating the Robustness of Multimodal Agents Against Active Environmental Injection Attacks [[paper](https://arxiv.org/abs/2502.13053)]
2. [2024/10/23] MobileSafetyBench: Evaluating Safety of Autonomous Agents in Mobile Device Control. [[paper](https://arxiv.org/abs/2410.17520)]
"""

        papers = parse_readme(markdown)

        self.assertEqual(len(papers), 3)
        self.assertEqual(
            papers[0].title,
            "Evaluating the Robustness of Multimodal Agents Against Active Environmental Injection Attacks",
        )
        self.assertEqual(papers[0].date, "2025-02-18")
        self.assertEqual(papers[0].section, "Safety & Privacy")
        self.assertEqual(papers[-1].date, "2024-10")

    def test_source_key_matches_same_title_url(self):
        left = SurveyPaper("2025-02-18", "A  GUI   Paper!", "https://arxiv.org/abs/1", "A")
        right = SurveyPaper("2025-02-18", "A GUI Paper", "https://arxiv.org/abs/1", "B")

        self.assertEqual(source_key(left), source_key(right))

    def test_merge_snapshot_preserves_existing_entries_and_appends_new_ones(self):
        previous = [
            SurveyPaper("2024-01-01", "Old Paper", "https://arxiv.org/abs/1", "A"),
            SurveyPaper("2024-01-01", "Old Paper", "https://arxiv.org/abs/1", "A duplicate"),
        ]
        current = [
            SurveyPaper("2025-01-01", "New Paper", "https://arxiv.org/abs/2", "B"),
            SurveyPaper("2024-01-01", "Old Paper", "https://arxiv.org/abs/1", "A"),
        ]

        merged = merge_with_previous_snapshot(previous, current)

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0].title, "New Paper")


if __name__ == "__main__":
    unittest.main()
