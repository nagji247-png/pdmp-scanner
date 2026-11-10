import unittest
from datetime import datetime, timezone
from unittest import mock

import fetch_and_score


class ContrarianSessionDateTests(unittest.TestCase):
    def test_indian_event_date_uses_ist_after_utc_midnight_rollover(self):
        # 00:30 IST on 10 Nov is still 19:00 UTC on 9 Nov.
        scan_time = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
        self.assertEqual(
            fetch_and_score.contrarian_event_date("^NSEI", scan_time),
            "2026-11-10",
        )
        self.assertEqual(
            fetch_and_score.contrarian_event_date("RELIANCE.NS", scan_time),
            "2026-11-10",
        )

    def test_non_indian_symbol_keeps_utc_session_date(self):
        scan_time = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
        self.assertEqual(
            fetch_and_score.contrarian_event_date("^IXIC", scan_time),
            "2026-11-09",
        )

    def test_same_calendar_day_close_is_not_used_as_next_session_result(self):
        scan_time = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
        event_date = fetch_and_score.contrarian_event_date("^NSEI", scan_time)
        events = [{
            "key": f"{event_date}|NIFTY",
            "date": event_date,
            "instrument": "NIFTY",
            "score": 7.0,
            "outcome": None,
            "next_change": None,
        }]
        returns = {
            "2026-11-10": 0.45,  # same IST calendar date as the event
            "2026-11-11": -0.70, # first later session
        }
        with mock.patch.object(fetch_and_score, "SKIP_EVENTS", False):
            fetch_and_score.update_contrarian(
                events, "NIFTY", 0, event_date, returns, "^NSEI"
            )
        self.assertEqual(events[0]["next_change"], -0.70)
        self.assertEqual(events[0]["outcome"], "reversed")

    def test_archived_pending_instrument_passes_its_symbol_to_updater(self):
        scan_time = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
        with mock.patch.object(fetch_and_score, "update_contrarian") as updater:
            updated = fetch_and_score.update_archived_contrarian_pending(
                [], "RAYMOND", scan_time, {"2026-11-11": 0.5}
            )
        self.assertTrue(updated)
        updater.assert_called_once_with(
            [], "RAYMOND", 0, "2026-11-10",
            {"2026-11-11": 0.5}, "RAYMOND.NS",
        )

    def test_unknown_archived_instrument_is_not_sent_to_price_updater(self):
        with mock.patch.object(fetch_and_score, "update_contrarian") as updater:
            updated = fetch_and_score.update_archived_contrarian_pending(
                [], "UNKNOWN", datetime(2026, 11, 10, tzinfo=timezone.utc), {}
            )
        self.assertFalse(updated)
        updater.assert_not_called()


if __name__ == "__main__":
    unittest.main()
