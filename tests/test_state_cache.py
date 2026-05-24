import unittest
from pathlib import Path
import tempfile

from deep_stock_analysis.models import FundamentalSnapshot, PriceStats, SieveHit, Stage1Candidate, Stage2Candidate, Ticker
from deep_stock_analysis.state import PipelineState


class StateCacheTests(unittest.TestCase):
    def test_load_cached_stage1_and_stage2(self):
        path = Path(tempfile.gettempdir()) / "deep-stock-state-cache-test.db"
        path.unlink(missing_ok=True)
        state = PipelineState(path)
        try:
            state.save_stage1(
                [
                    Stage1Candidate(
                        ticker=Ticker(symbol="TEST", name="Test Co", exchange="XNAS"),
                        price_stats=PriceStats(symbol="TEST", close_price=10, avg_volume_20d=1_000_000, volatility_6m=0.05),
                    )
                ]
            )
            state.save_stage2(
                [
                    Stage2Candidate(
                        symbol="TEST",
                        score=42,
                        hits=[SieveHit("revenue_acceleration", 16, "Revenue acceleration")],
                        snapshot=FundamentalSnapshot(symbol="TEST", revenue_growth=0.2),
                        current_price=10,
                        volatility_6m=0.05,
                    )
                ]
            )

            stage1 = state.load_stage1()
            stage2 = state.load_stage2()
        finally:
            state.close()
            path.unlink(missing_ok=True)

        self.assertEqual(stage1[0].ticker.symbol, "TEST")
        self.assertEqual(stage2[0].current_price, 10)
        self.assertEqual(stage2[0].hits[0].name, "revenue_acceleration")


if __name__ == "__main__":
    unittest.main()
