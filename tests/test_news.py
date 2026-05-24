import unittest

from deep_stock_analysis.models import NewsArticle
from deep_stock_analysis.news import news_to_stage3_signal, score_news


class NewsTests(unittest.TestCase):
    def test_scores_news_catalyst_and_converts_to_stage_signal(self):
        signal = score_news(
            "TEST",
            [
                NewsArticle(
                    symbol="TEST",
                    title="TEST wins AI infrastructure contract award",
                    description="The customer win includes a long-term supply agreement and production ramp.",
                )
            ],
        )

        self.assertGreaterEqual(signal.catalyst_score, 25)
        self.assertIn("customer_win", signal.detected_themes)

        stage3 = news_to_stage3_signal(signal)

        self.assertTrue(stage3.backlog_expansion_detected)
        self.assertTrue(any(theme.startswith("news_") for theme in stage3.detected_themes))


if __name__ == "__main__":
    unittest.main()
