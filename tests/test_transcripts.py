import unittest

from deep_stock_analysis.models import Transcript
from deep_stock_analysis.transcripts import score_transcript


class TranscriptTests(unittest.TestCase):
    def test_scores_structural_transcript_above_stage3_boundary(self):
        transcript = Transcript(
            symbol="MU",
            quarter="Q2",
            year=2026,
            content=(
                "We saw record backlog and bookings exceeded shipments. "
                "Customers have reserved capacity under long-term supply agreements. "
                "Higher ASP, favorable pricing, and operating leverage are visible as the production ramp continues."
            ),
        )

        signal = score_transcript(transcript)

        self.assertTrue(signal.backlog_expansion_detected)
        self.assertTrue(signal.capacity_pre_sold)
        self.assertGreaterEqual(signal.pricing_power_indicator, 70)
        self.assertGreaterEqual(signal.pipeline_confidence_score, 85)


if __name__ == "__main__":
    unittest.main()
