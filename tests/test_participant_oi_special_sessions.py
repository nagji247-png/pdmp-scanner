import datetime as dt
import unittest
from unittest import mock

import fetch_and_score


CSV = """Client Type,Future Index Long,Future Index Short,Option Index Call Long,Option Index Call Short,Option Index Put Long,Option Index Put Short,Future Stock Long,Future Stock Short,Option Stock Call Long,Option Stock Call Short,Option Stock Put Long,Option Stock Put Short
Client,100,90,200,190,220,210,300,290,400,390,420,410
DII,110,80,210,180,230,200,310,280,410,380,430,400
FII,120,70,220,170,240,190,320,270,420,370,440,390
Pro,130,60,230,160,250,180,330,260,430,360,450,380
"""


def participant_snapshot(date):
    fields = {
        "future_index_long": 100, "future_index_short": 90,
        "index_call_long": 200, "index_call_short": 190,
        "index_put_long": 220, "index_put_short": 210,
    }
    return {
        "ok": True,
        "stale": False,
        "date": date,
        "source": "NSE official participant-wise OI",
        "scope": "Index F&O participant totals",
        "participants": {
            group: dict(fields) for group in ("FII", "DII", "PRO", "CLIENT")
        },
    }


class ParticipantOISpecialSessionTests(unittest.TestCase):
    def test_fetch_allows_official_sunday_session_and_uses_exact_nse_file(self):
        calendar = {"special_sessions": {"2026-11-08": {"name": "Muhurat"}}}
        response = mock.Mock(status_code=200, text=CSV)
        with mock.patch.object(fetch_and_score, "load_json", return_value=calendar), \
             mock.patch.object(fetch_and_score.requests, "get", return_value=response) as request:
            result = fetch_and_score.fetch_participant_oi(
                base_date="2026-11-08", lookback_days=0
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["date"], "2026-11-08")
        self.assertEqual(set(result["participants"]), {"FII", "DII", "PRO", "CLIENT"})
        request.assert_called_once()
        self.assertIn("fao_participant_oi_08112026.csv", request.call_args.args[0])

    def test_regular_weekend_without_calendar_entry_is_not_requested(self):
        calendar = {"special_sessions": {"2026-11-08": {"name": "Muhurat"}}}
        with mock.patch.object(fetch_and_score, "load_json", return_value=calendar), \
             mock.patch.object(fetch_and_score.requests, "get") as request:
            result = fetch_and_score.fetch_participant_oi(
                base_date="2026-11-07", lookback_days=0
            )
        self.assertFalse(result["ok"])
        request.assert_not_called()

    def test_backfill_checks_missing_special_sessions_even_after_target_met(self):
        start = dt.date(2025, 1, 1)
        records = [
            {"date": (start + dt.timedelta(days=i)).isoformat(),
             "source": "NSE official participant-wise OI",
             "scope": "Index F&O participant totals",
             "participants": participant_snapshot("2025-01-01")["participants"]}
            for i in range(252)
        ]
        archive = {
            "records": records,
            "backfill": {
                "version": 6,
                "attempted_at": "2026-11-10T00:00Z",
                "target_sessions": 250,
            },
        }
        calendar = {
            "special_sessions": {
                "2026-02-01": {"name": "Budget trading"},
                "2026-11-08": {"name": "Muhurat"},
            }
        }
        with mock.patch.object(
            fetch_and_score, "load_json", side_effect=[archive, calendar]
        ), mock.patch.object(
            fetch_and_score, "fetch_participant_oi",
            side_effect=[
                participant_snapshot("2026-02-01"),
                participant_snapshot("2026-11-08"),
            ],
        ) as fetch:
            result = fetch_and_score.update_participant_oi_history()
        dates = {row["date"] for row in result["records"]}
        self.assertTrue({"2026-02-01", "2026-11-08"}.issubset(dates))
        self.assertEqual(len(result["records"]), 254)
        self.assertEqual(result["backfill"]["sessions_added"], 2)
        self.assertEqual(result["backfill"]["missing_special_dates"], [])
        self.assertEqual(fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
