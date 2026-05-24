import unittest

from deep_stock_analysis.models import AnalystConsensus
from deep_stock_analysis.reports import analyst_estimates_section


class AnalystEstimateTests(unittest.TestCase):
    def test_analyst_section_includes_price_target_and_upside(self):
        analyst = AnalystConsensus(
            symbol="AAOI",
            target_low=125,
            target_median=180,
            target_consensus=220,
            target_high=260,
            recent_target_avg=230,
            recent_target_count=2,
            estimated_revenue=1_100_000_000,
            estimated_eps=2.5,
            num_analysts_revenue=3,
            num_analysts_eps=4,
            estimate_period="annual",
            estimate_year=2027,
        )

        section = analyst_estimates_section(analyst, current_price=200)

        self.assertIn("$220.00", section)
        self.assertIn("10.0%", section)
        self.assertIn("$230.00", section)
        self.assertIn("$1,100,000,000.00", section)


if __name__ == "__main__":
    unittest.main()
