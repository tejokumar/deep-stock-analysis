import json
import unittest

from deep_stock_analysis.models import NewsSignal, Stage3Signal
from deep_stock_analysis.sentiment import _parse_sentiment, fallback_sentiment


class SentimentTests(unittest.TestCase):
    def test_parse_xai_sentiment_json(self):
        payload = json.dumps(
            {
                "news_sentiment_score": 82,
                "social_sentiment_score": 50,
                "hype_score": 70,
                "controversy_score": 10,
                "catalyst_believability_score": 76,
                "retail_attention_score": 65,
                "summary": "Catalyst looks substantive but attention is elevated.",
                "bullish_points": ["Customer order evidence"],
                "bearish_points": ["Some hype risk"],
            }
        )

        signal = _parse_sentiment("TEST", payload)

        self.assertEqual(signal.news_sentiment_score, 82)
        self.assertEqual(signal.catalyst_believability_score, 76)
        self.assertIn("Customer order", signal.bullish_points[0])

    def test_fallback_sentiment_uses_news_and_transcript_scores(self):
        stage3 = Stage3Signal("TEST", True, False, 80, "evidence", 90, ["new_cycle"])
        news = NewsSignal("TEST", 100, 95, 0, ["ai_infrastructure"], [], ["headline"])

        signal = fallback_sentiment("TEST", stage3, news)

        self.assertGreaterEqual(signal.catalyst_believability_score, 60)
        self.assertEqual(signal.news_sentiment_score, 95)


if __name__ == "__main__":
    unittest.main()
