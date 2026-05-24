import tempfile
from pathlib import Path
import unittest

from deep_stock_analysis.paper import TradeCandidate, build_order_plan, latest_report_dir, load_candidates_from_index, write_plan_markdown


class PaperTradingTests(unittest.TestCase):
    def test_latest_report_dir_uses_reverse_time_sort(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "8220_2026-05-24T18-00-00Z").mkdir()
            (root / "8219_2026-05-25T18-00-00Z").mkdir()

            self.assertEqual(latest_report_dir(root).name, "8219_2026-05-25T18-00-00Z")

    def test_load_candidates_from_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.md"
            index.write_text(
                "\n".join(
                    [
                        "| Rank | Symbol | Name | Sub Sector | Score | Action | Thesis | Current | Entry Zone | Analyst Targets L/M/C/H | Recent Target | 2026E Rev | 2026E EPS | 6M | YTD | 3M | 1M | 1W | Today | Believability | Hype | Report |",
                        "| ---: | --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
                        "| 1 | AVAV | AeroVironment | Aerospace/Defense | 114.1 | Early Accumulation Candidate | 81.2/100 | $174.23 | $169.00 to $182.94 |  |  |  |  |  |  |  |  |  |  | 85/100 | 25/100 | [AVAV.md](AVAV.md) |",
                    ]
                )
            )

            candidates = load_candidates_from_index(index)

        self.assertEqual(candidates[0].symbol, "AVAV")
        self.assertEqual(candidates[0].entry_high, 182.94)
        self.assertEqual(candidates[0].believability, 85)

    def test_build_order_plan_buys_targets_and_sells_stops(self):
        candidates = [
            TradeCandidate("AVAV", 1, 114, 174, 169, 183, "Early Accumulation Candidate", 81, 85, 25),
            TradeCandidate("FORM", 2, 111, 129, 125, 136, "Early Accumulation Candidate", 100, 85, 65),
        ]
        account = {"equity": "100000"}
        positions = [
            {"symbol": "OLD", "market_value": "5000", "avg_entry_price": "100", "current_price": "80", "qty": "50"},
        ]

        orders = build_order_plan(candidates, account, positions, {"positions": {"OLD": {"opened_at": "2026-01-01"}}})

        self.assertIn(("OLD", "sell"), {(order.symbol, order.side) for order in orders})
        self.assertIn(("AVAV", "buy"), {(order.symbol, order.side) for order in orders})
        self.assertGreater(next(order.notional for order in orders if order.symbol == "AVAV"), 0)

    def test_write_plan_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper" / "latest-plan.md"
            candidates = [TradeCandidate("AVAV", 1, 114, 174, 169, 183, "Early Accumulation Candidate", 81, 85, 25)]
            orders = build_order_plan(candidates, {"equity": "100000"}, [], {"positions": {}})

            write_plan_markdown(path, Path("reports/example"), candidates, orders, {"equity": "100000"}, execute=False)

            text = path.read_text()

        self.assertIn("# Paper Trading Plan", text)
        self.assertIn("AVAV", text)
        self.assertIn("dry-run", text)


if __name__ == "__main__":
    unittest.main()
