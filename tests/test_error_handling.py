import unittest
from pathlib import Path
import tempfile

from deep_stock_analysis.config import PipelineConfig
from deep_stock_analysis.models import PriceStats, Stage1Candidate, Ticker
from deep_stock_analysis.pipeline import DiscoveryPipeline
from deep_stock_analysis.providers import ProviderError
from deep_stock_analysis.state import PipelineState


class BrokenFundamentalProvider:
    def fundamentals(self, symbol):
        raise ProviderError("FMP HTTP 403 for /api/v3/financial-growth/TEST")


class ErrorHandlingTests(unittest.TestCase):
    def test_stage2_skips_provider_errors(self):
        state_path = Path(tempfile.gettempdir()) / "deep-stock-error-test.db"
        state_path.unlink(missing_ok=True)
        config = PipelineConfig(None, None, state_path=state_path)
        state = PipelineState(config.state_path)
        try:
            pipeline = DiscoveryPipeline(config, state, universe_provider=None, fundamental_provider=BrokenFundamentalProvider())
            stage1 = [
                Stage1Candidate(
                    ticker=Ticker(symbol="TEST"),
                    price_stats=PriceStats(symbol="TEST", close_price=10, avg_volume_20d=1_000_000),
                )
            ]

            results = pipeline.run_stage2(stage1)
        finally:
            state.close()
            state_path.unlink(missing_ok=True)

        self.assertEqual(results, [])
        self.assertIn("TEST", pipeline.stage2_errors)

    def test_stage2_keeps_price_breakout_when_fundamentals_fail(self):
        state_path = Path(tempfile.gettempdir()) / "deep-stock-price-fallback-test.db"
        state_path.unlink(missing_ok=True)
        config = PipelineConfig(None, None, state_path=state_path, shortlist_min_score=30)
        state = PipelineState(config.state_path)
        try:
            pipeline = DiscoveryPipeline(config, state, universe_provider=None, fundamental_provider=BrokenFundamentalProvider())
            stage1 = [
                Stage1Candidate(
                    ticker=Ticker(symbol="BREAKOUT", industry="Software"),
                    price_stats=PriceStats(
                        symbol="BREAKOUT",
                        close_price=10,
                        avg_volume_20d=1_000_000,
                        return_1m=0.45,
                        return_1w=0.18,
                    ),
                )
            ]

            results = pipeline.run_stage2(stage1)
        finally:
            state.close()
            state_path.unlink(missing_ok=True)

        self.assertEqual([candidate.symbol for candidate in results], ["BREAKOUT"])
        self.assertIn("BREAKOUT", pipeline.stage2_errors)
        self.assertIn("fresh_price_breakout", {hit.name for hit in results[0].hits})


if __name__ == "__main__":
    unittest.main()
