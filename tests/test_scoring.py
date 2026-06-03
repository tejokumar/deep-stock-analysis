import unittest

from deep_stock_analysis.models import FundamentalSnapshot, PriceStats
from deep_stock_analysis.scoring import score_candidate


class ScoringTests(unittest.TestCase):
    def test_scores_multi_signal_candidate_above_shortlist_threshold(self):
        snapshot = FundamentalSnapshot(
            symbol="MU",
            capex_growth_yoy=0.5,
            gross_margin_delta=0.03,
            revenue_growth=0.02,
            ev_to_tangible_book=1.5,
            industry="Semiconductors",
            debt_to_equity=0.2,
            revenue_growth_acceleration=0.09,
        )
        stats = PriceStats(symbol="MU", close_price=80, avg_volume_20d=1_000_000, volatility_6m=0.03)

        candidate = score_candidate(snapshot, stats)

        self.assertGreaterEqual(candidate.score, 55)
        self.assertGreaterEqual(
            {hit.name for hit in candidate.hits},
            {"capex_divergence", "margin_acceleration", "revenue_acceleration"},
        )

    def test_scores_asset_discount_without_hardware_bonus_lower(self):
        snapshot = FundamentalSnapshot(symbol="VALUE", ev_to_tangible_book=0.9, industry="Retail")

        candidate = score_candidate(snapshot)

        self.assertEqual(candidate.score, 13.0)

    def test_scores_fresh_price_breakout_without_fundamental_hit(self):
        snapshot = FundamentalSnapshot(symbol="BREAKOUT", industry="Software")
        stats = PriceStats(
            symbol="BREAKOUT",
            close_price=100,
            avg_volume_20d=1_000_000,
            return_3m=0.08,
            return_1m=0.42,
            return_1w=0.16,
            return_1d=0.02,
        )

        candidate = score_candidate(snapshot, stats)

        self.assertGreaterEqual(candidate.score, 30)
        self.assertIn("fresh_price_breakout", {hit.name for hit in candidate.hits})


if __name__ == "__main__":
    unittest.main()
