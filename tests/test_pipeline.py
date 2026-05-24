import unittest
from pathlib import Path
import tempfile

from deep_stock_analysis.config import PipelineConfig
from deep_stock_analysis.pipeline import DiscoveryPipeline
from deep_stock_analysis.models import PriceStats, Ticker
from deep_stock_analysis.providers import SampleProvider
from deep_stock_analysis.state import PipelineState


class PipelineTests(unittest.TestCase):
    def test_sample_pipeline_shortlists_broad_anomalies(self):
        provider = SampleProvider(Path("samples/broad_anomaly_sample.json"))
        config = PipelineConfig(
            polygon_api_key=None,
            fmp_api_key=None,
            state_path=Path(tempfile.gettempdir()) / "deep-stock-test.db",
            shortlist_min_score=30,
        )
        if config.state_path.exists():
            config.state_path.unlink()
        state = PipelineState(config.state_path)
        try:
            pipeline = DiscoveryPipeline(config, state, provider, provider)

            stage1 = pipeline.run_stage1(limit=10, progress_every=0)
            stage2 = pipeline.run_stage2(stage1, progress_every=0)
        finally:
            state.close()
            config.state_path.unlink(missing_ok=True)

        self.assertNotIn("PENNY", {candidate.ticker.symbol for candidate in stage1})
        self.assertGreaterEqual({candidate.symbol for candidate in stage2}, {"MU", "AMD", "SNDK", "ARM"})

    def test_stage1_symbols_uses_requested_universe(self):
        class SymbolProvider:
            def ticker_details(self, symbol):
                return Ticker(symbol=symbol, name=f"{symbol} Co", industry="SEMICONDUCTORS & RELATED DEVICES")

            def price_stats(self, symbol):
                return PriceStats(symbol=symbol, close_price=10, avg_volume_20d=1_000_000)

        state_path = Path(tempfile.gettempdir()) / "deep-stock-symbol-stage1-test.db"
        state_path.unlink(missing_ok=True)
        config = PipelineConfig(polygon_api_key=None, fmp_api_key=None, state_path=state_path)
        state = PipelineState(config.state_path)
        try:
            pipeline = DiscoveryPipeline(config, state, SymbolProvider(), fundamental_provider=None)
            stage1 = pipeline.run_stage1_symbols(["NVDA", "AMD"], progress_every=0)
        finally:
            state.close()
            state_path.unlink(missing_ok=True)

        self.assertEqual([candidate.ticker.symbol for candidate in stage1], ["AMD", "NVDA"])
        self.assertEqual(stage1[0].ticker.industry, "SEMICONDUCTORS & RELATED DEVICES")


if __name__ == "__main__":
    unittest.main()
