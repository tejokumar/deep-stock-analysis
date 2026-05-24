import unittest

from deep_stock_analysis.cli import _apply_worker_overrides, _parse_symbols, filter_reports
from deep_stock_analysis.config import PipelineConfig
from deep_stock_analysis.models import Stage4Report
from deep_stock_analysis.state import PipelineState


class CliOptionTests(unittest.TestCase):
    def test_parse_symbols_dedupes_and_preserves_order(self):
        self.assertEqual(_parse_symbols("nvda, AVGO\nmsft nvda LGF.A"), ["NVDA", "AVGO", "MSFT", "LGF.A"])

    def test_high_conviction_report_filter(self):
        state = PipelineState(":memory:")
        try:
            reports = [
                Stage4Report(
                    symbol="GOOD",
                    archetype="test",
                    confidence_score=95,
                    markdown="\n".join(
                        [
                            "- Bot action: Early Accumulation Candidate",
                            "- Thesis score: 90/100",
                            "believability 85/100",
                            "hype 20/100",
                        ]
                    ),
                ),
                Stage4Report(
                    symbol="WEAK",
                    archetype="test",
                    confidence_score=80,
                    markdown="\n".join(
                        [
                            "- Bot action: Watch",
                            "- Thesis score: 50/100",
                            "believability 55/100",
                            "hype 20/100",
                        ]
                    ),
                ),
            ]

            filtered = filter_reports(reports, state, high_conviction_only=True, min_report_score=80)
        finally:
            state.close()

        self.assertEqual([report.symbol for report in filtered], ["GOOD"])

    def test_worker_overrides_apply_to_config(self):
        class Args:
            stage1_workers = 12
            stage2_workers = None
            stage3_workers = 4
            news_workers = None
            sentiment_workers = 2
            stage4_workers = 6

        config = PipelineConfig(None, None, ":memory:", max_workers=5)

        updated = _apply_worker_overrides(config, Args())

        self.assertEqual(updated.stage1_workers, 12)
        self.assertIsNone(updated.stage2_workers)
        self.assertEqual(updated.stage3_workers, 4)
        self.assertEqual(updated.sentiment_workers, 2)
        self.assertEqual(updated.stage4_workers, 6)


if __name__ == "__main__":
    unittest.main()
