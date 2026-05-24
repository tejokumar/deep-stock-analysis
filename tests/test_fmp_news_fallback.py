import unittest

from deep_stock_analysis.providers import FmpClient, ProviderError


class FakeNewsFallbackFmpClient(FmpClient):
    def __init__(self):
        super().__init__("test")

    def _get_list(self, path, params):
        if "earning_call_transcript" in path:
            raise ProviderError("FMP HTTP 403 for transcript")
        if path == "/stable/news/stock":
            return [
                {
                    "title": "TEST wins contract award",
                    "text": "The company announced a strategic partnership and long-term supply agreement.",
                }
            ]
        raise AssertionError(f"Unexpected endpoint: {path}")


class FmpNewsFallbackTests(unittest.TestCase):
    def test_latest_transcript_falls_back_to_stock_news(self):
        transcript = FakeNewsFallbackFmpClient().latest_transcript("TEST")

        self.assertIsNotNone(transcript)
        self.assertIn("contract award", transcript.content)
        self.assertIn("supply agreement", transcript.content)


if __name__ == "__main__":
    unittest.main()
