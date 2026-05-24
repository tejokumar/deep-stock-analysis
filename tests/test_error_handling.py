import unittest

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
        config = PipelineConfig(None, None, state_path="/private/tmp/deep-stock-error-test.db")
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

        self.assertEqual(results, [])
        self.assertIn("TEST", pipeline.stage2_errors)


if __name__ == "__main__":
    unittest.main()
