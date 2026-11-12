"""Tests for conservative CLIENT Futures auto-promotion."""
import json
import tempfile
import unittest
from pathlib import Path

from client_futures_promotion import (
    evaluate_client_futures_promotion, build_client_futures_component,
    load_client_futures_promotion, wilson_lower_bound,
)


def make_check(orientation="direct", hits=11, bullish=7):
    rows = []
    for i in range(14):
        predicted = "BULLISH" if i < bullish else "BEARISH"
        direct_correct = i < hits
        actual = (("UP" if predicted == "BULLISH" else "DOWN") if direct_correct
                  else ("DOWN" if predicted == "BULLISH" else "UP"))
        rows.append({
            "predicted_direction": predicted,
            "actual_direction": actual,
            "correct": direct_correct,
            "contrarian_correct": not direct_correct,
        })
    return {
        "status": "ready", "sample_sessions": 14,
        "first_signal_date": "2026-11-13", "last_signal_date": "2026-12-02",
        "observations": rows,
    }


class ClientFuturesPromotionTests(unittest.TestCase):
    def make_summary(self, hits=11, bullish=7):
        return {
            "status": "exploratory_only",
            "indices": {
                name: {"client_futures_new_14_session_check": make_check(hits=hits, bullish=bullish)}
                for name in ("NIFTY", "SENSEX", "BANKNIFTY")
            },
        }

    def test_wilson_lower_bound(self):
        self.assertGreater(wilson_lower_bound(11, 14), 50.0)
        self.assertLess(wilson_lower_bound(10, 14), 50.0)

    def test_promotes_only_when_all_three_indices_pass_diverse_sample(self):
        result = evaluate_client_futures_promotion(self.make_summary())
        self.assertEqual(result["status"], "promoted")
        self.assertTrue(result["eligible_for_provisional_final"])
        self.assertEqual(result["orientation"], "direct")

    def test_no_promotion_when_one_index_fails(self):
        summary = self.make_summary()
        summary["indices"]["SENSEX"]["client_futures_new_14_session_check"] = make_check(hits=8)
        result = evaluate_client_futures_promotion(summary)
        self.assertFalse(result["eligible_for_provisional_final"])

    def test_no_promotion_without_both_signal_directions(self):
        result = evaluate_client_futures_promotion(self.make_summary(bullish=14))
        self.assertFalse(result["eligible_for_provisional_final"])

    def test_component_respects_validated_orientation_and_scope(self):
        promotion = evaluate_client_futures_promotion(self.make_summary())
        context = {
            "available": True, "source": "NSE official participant OI",
            "source_date": "2026-12-02",
            "evidence_components": {
                "futures_long": {"change": 1000, "previous_gross": 200000},
                "futures_short": {"change": 500, "previous_gross": 50000},
            },
        }
        component = build_client_futures_component(context, "2026-12-02", promotion)
        self.assertIsNotNone(component)
        self.assertAlmostEqual(component["score"], 0.02, places=2)
        self.assertTrue(component["auto_promoted"])
        self.assertTrue(component["not_index_specific"])

    def test_stale_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(json.dumps({"oi_last_date": "2026-11-01"}))
            result = load_client_futures_promotion("2026-11-12", path)
            self.assertEqual(result["status"], "stale_report")
            self.assertFalse(result["eligible_for_provisional_final"])


if __name__ == "__main__":
    unittest.main()
