import datetime as dt
import unittest
from unittest import mock

import fetch_and_score


HEADER = (
    "Client Type,Future Index Long,Future Index Short,Option Index Call Long,"
    "Option Index Call Short,Option Index Put Long,Option Index Put Short,"
    "Future Stock Long,Future Stock Short,Option Stock Call Long,"
    "Option Stock Call Short,Option Stock Put Long,Option Stock Put Short"
)


def participant_csv():
    rows = ["NSE participant-wise OI report", HEADER]
    for name, offset in (("FII", 1), ("DII", 2), ("PRO", 3), ("CLIENT", 4)):
        rows.append(",".join([name] + [str(100 + offset + i) for i in range(12)]))
    return "\n".join(rows)


def complete_participants():
    fields = (
        "future_index_long", "future_index_short",
        "index_call_long", "index_call_short",
        "index_put_long", "index_put_short",
    )
    return {
        group: {field: 100 + i for i, field in enumerate(fields)}
        for group in ("FII", "DII", "PRO", "CLIENT")
    }


def archive_with_250_records():
    special = set(fetch_and_score.SPECIAL_SESSION_OI_DATES)
    records = []
    day = dt.date(2025, 1, 1)
    while len(records) < 250:
        value = day.isoformat()
        if value not in special:
            records.append({
                "date": value,
                "participants": {group: {} for group in ("FII", "DII", "PRO", "CLIENT")},
            })
        day += dt.timedelta(days=1)
    return {
        "records": records,
        "backfill": {"version": 6, "status": "complete"},
    }


class FakeResponse:
    status_code = 200
    text = participant_csv()


class ParticipantOISpecialSessionTests(unittest.TestCase):
    def test_exact_weekend_date_mode_fetches_official_csv(self):
        with mock.patch.object(fetch_and_score.requests, "get", return_value=FakeResponse()) as request:
            result = fetch_and_score.fetch_participant_oi(
                base_date=dt.date(2026, 2, 1),
                lookback_days=0,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["date"], "2026-02-01")
        self.assertIn("01022026", request.call_args.args[0])

    def test_normal_lookback_still_skips_weekend_dates(self):
        with mock.patch.object(fetch_and_score.requests, "get", return_value=FakeResponse()) as request:
            result = fetch_and_score.fetch_participant_oi(
                base_date=dt.date(2026, 2, 1),
                lookback_days=7,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["date"], "2026-01-30")
        self.assertIn("30012026", request.call_args.args[0])

    def test_special_session_backfill_adds_only_verified_exact_dates(self):
        archive_input = archive_with_250_records()
        calls = []

        def fake_fetch(base_date=None, lookback_days=7):
            calls.append((base_date, lookback_days))
            return {
                "ok": True,
                "stale": False,
                "date": base_date.isoformat(),
                "source": "NSE official participant-wise OI",
                "scope": "Index F&O participant totals",
                "participants": complete_participants(),
            }

        with mock.patch.object(fetch_and_score, "load_json", return_value=archive_input), \
             mock.patch.object(fetch_and_score, "fetch_participant_oi", side_effect=fake_fetch):
            archive = fetch_and_score.update_participant_oi_history()

        self.assertEqual(len(calls), 2)
        self.assertTrue(all(lookback == 0 for _, lookback in calls))
        self.assertEqual(archive["special_session_backfill"]["status"], "complete")
        self.assertEqual(archive["special_session_backfill"]["sessions_added"], 2)
        self.assertEqual(archive["special_session_backfill"]["missing_dates"], [])
        dates = {row["date"] for row in archive["records"]}
        self.assertTrue(set(fetch_and_score.SPECIAL_SESSION_OI_DATES).issubset(dates))

    def test_special_session_backfill_retries_no_more_than_daily(self):
        archive_input = archive_with_250_records()
        now = dt.datetime.now(dt.timezone.utc)
        archive_input["special_session_backfill"] = {
            "version": 1,
            "status": "partial",
            "attempted_at": now.isoformat().replace("+00:00", "Z"),
            "missing_dates": list(fetch_and_score.SPECIAL_SESSION_OI_DATES),
        }
        with mock.patch.object(fetch_and_score, "load_json", return_value=archive_input), \
             mock.patch.object(fetch_and_score, "fetch_participant_oi") as fetch:
            archive = fetch_and_score.update_participant_oi_history()
        fetch.assert_not_called()
        self.assertEqual(
            archive["special_session_backfill"]["missing_dates"],
            list(fetch_and_score.SPECIAL_SESSION_OI_DATES),
        )


if __name__ == "__main__":
    unittest.main()
