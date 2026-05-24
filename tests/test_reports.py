import unittest

from deep_stock_analysis.models import AnalystConsensus, FundamentalSnapshot, NewsSignal, SieveHit, Stage2Candidate, Stage3Signal
from deep_stock_analysis.reports import build_report, classify_archetype


class ReportTests(unittest.TestCase):
    def test_classifies_capacity_ramp_with_presold_capacity(self):
        stage2 = Stage2Candidate(
            symbol="MU",
            score=82,
            hits=[SieveHit("capex_divergence", 24, "CapEx growth YoY 55%")],
            snapshot=FundamentalSnapshot(symbol="MU", industry="Semiconductors"),
        )
        stage3 = Stage3Signal(
            ticker="MU",
            backlog_expansion_detected=True,
            capacity_pre_sold=True,
            pricing_power_indicator=90,
            textual_evidence_excerpt="record backlog and reserved capacity",
            pipeline_confidence_score=100,
            detected_themes=["backlog_expansion", "capacity_pre_sold", "pricing_power", "new_cycle"],
        )

        self.assertEqual(classify_archetype(stage2, stage3), "Capacity Ramp / Pre-Sold Demand")
        report = build_report(stage2, stage3)
        self.assertIn("Catalyst-Linked Timeline", report.markdown)
        self.assertIn("reserved capacity", report.markdown)

    def test_report_provides_automated_action_not_manual_review(self):
        stage2 = Stage2Candidate(
            symbol="AAOI",
            score=36,
            hits=[SieveHit("revenue_acceleration", 16, "Revenue growth acceleration improved 17%")],
            snapshot=FundamentalSnapshot(symbol="AAOI", gross_margin_delta=-0.02, revenue_growth_acceleration=0.17),
            current_price=181.49,
            volatility_6m=0.10,
        )
        stage3 = Stage3Signal(
            ticker="AAOI",
            backlog_expansion_detected=True,
            capacity_pre_sold=False,
            pricing_power_indicator=90,
            textual_evidence_excerpt="accelerating customer demand",
            pipeline_confidence_score=90,
            detected_themes=["backlog_expansion", "pricing_power", "operating_leverage", "new_cycle"],
        )
        analyst = AnalystConsensus(symbol="AAOI", recent_target_avg=160, recent_target_count=1)

        news = NewsSignal(
            ticker="AAOI",
            catalyst_score=82,
            sentiment_score=88,
            risk_score=0,
            detected_themes=["ai_infrastructure", "customer_win"],
            evidence_headlines=["AAOI wins AI infrastructure contract award"],
        )

        report = build_report(stage2, stage3, analyst, news)

        self.assertIn("Bot action:", report.markdown)
        self.assertIn("Preferred entry zone:", report.markdown)
        self.assertIn("News Catalyst", report.markdown)
        self.assertIn("AAOI wins AI infrastructure", report.markdown)
        self.assertNotIn("manual review", report.markdown.lower())


if __name__ == "__main__":
    unittest.main()
