import unittest
from types import SimpleNamespace
from unittest.mock import patch

import fetch_and_score as scanner


class ParticipantOIBackfillPolicyTests(unittest.TestCase):
    def test_backfill_target_and_retention_are_two_year_exploratory_window(self):
        self.assertEqual(scanner.PARTICIPANT_OI_BACKFILL_VERSION, 8)
        self.assertEqual(scanner.PARTICIPANT_OI_BACKFILL_TARGET, 500)
        self.assertGreaterEqual(
            scanner.PARTICIPANT_HISTORY_KEEP,
            scanner.PARTICIPANT_OI_BACKFILL_TARGET + 20,
        )

    def test_historical_requests_remain_rate_limited(self):
        self.assertEqual(scanner.PARTICIPANT_OI_BACKFILL_MAX_REQUESTS, 3)
        self.assertEqual(scanner.PARTICIPANT_OI_BACKFILL_RETRY_SECONDS, 86400)
        self.assertEqual(scanner.PARTICIPANT_OI_BACKFILL_CALENDAR_DAYS, 421)

    def test_official_nse_archive_uses_exact_date_and_all_participants(self):
        headers = (
            "Client Type,Future Index Long,Future Index Short,"
            "Option Index Call Long,Option Index Call Short,"
            "Option Index Put Long,Option Index Put Short,"
            "Future Stock Long,Future Stock Short,"
            "Option Stock Call Long,Option Stock Call Short,"
            "Option Stock Put Long,Option Stock Put Short"
        )
        rows = [
            "FII,100,80,200,180,220,210,10,8,20,18,22,21",
            "DII,110,90,210,190,230,220,11,9,21,19,23,22",
            "PRO,120,100,220,200,240,230,12,10,22,20,24,23",
            "CLIENT,130,110,230,210,250,240,13,11,23,21,25,24",
        ]
        response = SimpleNamespace(status_code=200, text="\n".join([headers] + rows))
        with patch.object(scanner, "nse_special_session_dates", return_value=set()):
            with patch.object(scanner.requests, "get", return_value=response) as request:
                result = scanner.fetch_participant_oi(
                    base_date="2025-10-30",
                    lookback_days=0,
                )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["date"], "2025-10-30")
        self.assertEqual(set(result["participants"]), {"FII", "DII", "PRO", "CLIENT"})
        self.assertEqual(result["participants"]["FII"]["future_index_net"], 20)
        self.assertEqual(
            request.call_args.args[0],
            "https://archives.nseindia.com/content/nsccl/fao_participant_oi_30102025.csv",
        )
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
