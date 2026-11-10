import datetime as dt
import unittest
from unittest.mock import Mock

import verify_special_session_participant_oi as audit


HEADER = (
    "Client Type,Future Index Long,Future Index Short,Option Index Call Long,"
    "Option Index Call Short,Option Index Put Long,Option Index Put Short,"
    "Future Stock Long,Future Stock Short,Option Stock Call Long,"
    "Option Stock Call Short,Option Stock Put Long,Option Stock Put Short"
)


def csv_text():
    rows = ["NSE participant-wise OI report", HEADER]
    for name, offset in (("FII", 1), ("DII", 2), ("PRO", 3), ("CLIENT", 4)):
        values = [str(100 + offset + i) for i in range(12)]
        rows.append(",".join([name] + values))
    return "\n".join(rows)


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")


class SpecialSessionOIArchiveTests(unittest.TestCase):
    def test_parse_complete_csv_after_preamble(self):
        parsed = audit.parse_participant_csv(csv_text())
        self.assertEqual(parsed["status"], "available_complete")
        self.assertEqual(set(parsed["participants"]), {"FII", "DII", "PRO", "CLIENT"})
        self.assertEqual(parsed["participants"]["CLIENT"]["future_index_long"], 104)
        self.assertEqual(parsed["participants"]["FII"]["index_put_short"], 106)

    def test_parse_missing_required_column_as_incomplete(self):
        text = csv_text().replace(",Option Index Put Short", "")
        parsed = audit.parse_participant_csv(text)
        self.assertEqual(parsed["status"], "available_incomplete")
        self.assertIn("index_put_short", parsed["missing_columns"])

    def test_parse_missing_participant_as_incomplete(self):
        text = "\n".join(line for line in csv_text().splitlines() if not line.startswith("PRO,"))
        parsed = audit.parse_participant_csv(text)
        self.assertEqual(parsed["status"], "available_incomplete")
        self.assertIn("PRO", parsed["missing_participants"])

    def test_audit_reports_404_without_claiming_file_exists(self):
        session = Mock()
        session.get.return_value = FakeResponse(404)
        result = audit.audit_one_date(dt.date(2026, 2, 1), session=session)
        self.assertEqual(result["availability_status"], "not_found")
        self.assertEqual(result["http_status"], 404)
        self.assertNotIn("participants", result)

    def test_audit_reports_complete_csv(self):
        session = Mock()
        session.get.return_value = FakeResponse(200, csv_text())
        result = audit.audit_one_date(dt.date(2026, 11, 8), session=session)
        self.assertEqual(result["availability_status"], "available_complete")
        self.assertEqual(sorted(result["participants"]), ["CLIENT", "DII", "FII", "PRO"])

    def test_run_audit_uses_one_request_per_exact_date(self):
        session = Mock()
        session.get.side_effect = [FakeResponse(404), FakeResponse(404)]
        sleeps = []
        report = audit.run_audit(
            [dt.date(2026, 2, 1), dt.date(2026, 11, 8)],
            session=session,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(report["provider_calls"], 2)
        self.assertEqual(len(session.get.call_args_list), 2)
        self.assertEqual(sleeps, [0.5])
        self.assertFalse(report["production_archive_changed"])


if __name__ == "__main__":
    unittest.main()
