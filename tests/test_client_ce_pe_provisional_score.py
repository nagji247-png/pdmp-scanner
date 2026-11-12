import unittest

from provisional_component_scoring import client_marketwide_components


def sample_context():
    return {
        "available": True,
        "source": "NSE official participant-wise OI",
        "source_date": "2026-11-11",
        "previous_date": "2026-11-09",
        "evidence_components": {
            "ce_long": {"change": 933042},
            "ce_short": {"change": 624696},
            "pe_long": {"change": 295379},
            "pe_short": {"change": 330690},
        },
    }


class ClientCePeProvisionalScoreTests(unittest.TestCase):
    def test_quantity_net_is_included_as_shared_marketwide_component(self):
        result = client_marketwide_components(
            sample_context(), scan_date="2026-11-12", max_age_days=3
        )
        self.assertEqual(set(result), {"client_ce_pe"})
        component = result["client_ce_pe"]
        self.assertAlmostEqual(component["combined_net_change"], 273035)
        self.assertAlmostEqual(component["call_net_change"], 308346)
        self.assertAlmostEqual(component["put_net_change"], -35311)
        self.assertAlmostEqual(component["score"], 1.25, places=2)
        self.assertEqual(component["weight"], 15.0)
        self.assertTrue(component["not_index_specific"])
        self.assertTrue(component["not_validated_predictor"])
        self.assertIn("shared market-wide", component["scope"])

    def test_stale_or_future_dated_context_is_excluded(self):
        stale = sample_context()
        stale["source_date"] = "2026-11-08"
        self.assertEqual(
            client_marketwide_components(stale, scan_date="2026-11-12", max_age_days=3),
            {},
        )
        future = sample_context()
        future["source_date"] = "2026-11-13"
        self.assertEqual(
            client_marketwide_components(future, scan_date="2026-11-12", max_age_days=3),
            {},
        )

    def test_incomplete_four_leg_data_is_not_converted_to_zero(self):
        incomplete = sample_context()
        incomplete["evidence_components"].pop("pe_short")
        self.assertEqual(
            client_marketwide_components(incomplete, scan_date="2026-11-12", max_age_days=3),
            {},
        )

    def test_zero_activity_is_not_fabricated_as_neutral_score(self):
        unchanged = sample_context()
        for item in unchanged["evidence_components"].values():
            item["change"] = 0
        self.assertEqual(
            client_marketwide_components(unchanged, scan_date="2026-11-12", max_age_days=3),
            {},
        )


if __name__ == "__main__":
    unittest.main()
