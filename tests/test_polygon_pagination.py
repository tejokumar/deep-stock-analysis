import unittest

from deep_stock_analysis.providers import PolygonClient


class FakePolygonClient(PolygonClient):
    def __init__(self):
        super().__init__("test")
        self.calls = 0

    def _get_json(self, path, params):
        self.calls += 1
        return {
            "results": [{"ticker": "A", "type": "CS"}, {"ticker": "B", "type": "CS"}],
            "next_url": "https://api.polygon.io/v3/reference/tickers?cursor=next",
        }

    def _get_json_url(self, url):
        self.calls += 1
        return {"results": [{"ticker": "C", "type": "CS"}]}


class PolygonPaginationTests(unittest.TestCase):
    def test_active_us_equities_follows_next_url(self):
        client = FakePolygonClient()

        tickers = client.active_us_equities(limit=None)

        self.assertEqual([ticker.symbol for ticker in tickers], ["A", "B", "C"])
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
