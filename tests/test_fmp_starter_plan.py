import unittest

from deep_stock_analysis.providers import FmpClient


class FakeStarterFmpClient(FmpClient):
    def __init__(self):
        super().__init__("test", fundamental_period="annual")

    def _get_list(self, path, params):
        assert path.startswith("/stable/")
        assert params["symbol"] == "TEST"
        if "income-statement" in path:
            return [
                {"revenue": 1200, "grossProfit": 540},
                {"revenue": 1000, "grossProfit": 400},
                {"revenue": 900, "grossProfit": 315},
            ]
        if "balance-sheet-statement" in path:
            return [{"totalDebt": 100, "totalStockholdersEquity": 500}]
        if "cash-flow-statement" in path:
            return [
                {"operatingCashFlow": 220, "capitalExpenditure": -90},
                {"operatingCashFlow": 160, "capitalExpenditure": -50},
            ]
        if "ratios" in path:
            return [{"debtEquityRatio": 0.2}]
        if "profile" in path:
            return [{"industry": "Semiconductors"}]
        raise AssertionError(f"Unexpected endpoint: {path}")


class FmpStarterPlanTests(unittest.TestCase):
    def test_annual_fundamentals_compute_metrics_without_financial_growth_endpoint(self):
        snapshot = FakeStarterFmpClient().fundamentals("TEST")

        self.assertEqual(snapshot.symbol, "TEST")
        self.assertAlmostEqual(snapshot.revenue_growth, 0.2)
        self.assertAlmostEqual(snapshot.capex_growth_yoy, 0.8)
        self.assertAlmostEqual(snapshot.gross_margin_delta, 0.05)
        self.assertAlmostEqual(snapshot.debt_to_equity, 0.2)
        self.assertEqual(snapshot.industry, "Semiconductors")


if __name__ == "__main__":
    unittest.main()
