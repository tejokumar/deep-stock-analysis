import unittest

from deep_stock_analysis.providers import RoicClient


class FakeRoicClient(RoicClient):
    def __init__(self):
        super().__init__("test")

    def _get_list(self, path, params):
        assert params["period"] == "quarterly"
        if "income-statement" in path:
            return [
                {"is_sales_revenue_turnover": 150, "gross_margin": 48.0},
                {"is_sales_revenue_turnover": 130, "gross_margin": 44.5},
                {"is_sales_revenue_turnover": 120, "gross_margin": 43.0},
                {"is_sales_revenue_turnover": 110, "gross_margin": 42.0},
                {"is_sales_revenue_turnover": 100, "gross_margin": 42.0},
                {"is_sales_revenue_turnover": 95, "gross_margin": 41.0},
            ]
        if "cash-flow" in path:
            return [
                {"cf_cap_expenditures": -90, "cf_free_cash_flow": 15},
                {"cf_cap_expenditures": -50, "cf_free_cash_flow": 8},
                {"cf_cap_expenditures": -45, "cf_free_cash_flow": 7},
                {"cf_cap_expenditures": -42, "cf_free_cash_flow": 6},
                {"cf_cap_expenditures": -50, "cf_free_cash_flow": 5},
            ]
        raise AssertionError(f"Unexpected required endpoint: {path}")

    def _optional_list(self, path, params):
        if "balance-sheet" in path:
            return [{"bs_st_borrow": 10, "bs_lt_borrow": 40, "bs_tot_equity": 250, "bs_goodwill": 0, "bs_intangibles": 0}]
        if "enterprise-value" in path:
            return [{"enterprise_value": 300}]
        return []

    def _optional_get(self, path, params):
        return {"industry": "Semiconductors"}


class RoicClientTests(unittest.TestCase):
    def test_quarterly_fundamentals_compute_pipeline_snapshot(self):
        snapshot = FakeRoicClient().fundamentals("TEST")

        self.assertAlmostEqual(snapshot.revenue_growth, 0.5)
        self.assertAlmostEqual(snapshot.capex_growth_yoy, 0.8)
        self.assertAlmostEqual(snapshot.gross_margin_delta, 0.035)
        self.assertAlmostEqual(snapshot.debt_to_equity, 0.2)
        self.assertAlmostEqual(snapshot.ev_to_tangible_book, 1.2)
        self.assertEqual(snapshot.industry, "Semiconductors")


if __name__ == "__main__":
    unittest.main()
