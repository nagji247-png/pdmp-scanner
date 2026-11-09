import csv
import io
import unittest
from unittest.mock import Mock

from bse_cm_bhavcopy_archive import parse_bse_cm_csv, fetch_official_bse_cm_bhavcopy


HEADERS = [
    "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "TckrSymb", "SctySrs",
    "ISIN", "TradDt", "BizDt", "OpnPric", "HghPric", "LwPric",
    "ClsPric", "PrvsClsgPric", "TtlTradgVol",
]


def payload(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def row(code="500001", symbol="ABC", isin="INE000A01001", close="105"):
    return {
        "Sgmt": "CM", "Src": "BSE", "FinInstrmTp": "STK",
        "FinInstrmId": code, "TckrSymb": symbol, "SctySrs": "A",
        "ISIN": isin, "TradDt": "2026-11-06", "BizDt": "2026-11-06",
        "OpnPric": "100", "HghPric": "110", "LwPric": "99",
        "ClsPric": close, "PrvsClsgPric": "100", "TtlTradgVol": "1000",
    }


class BseCashArchiveTests(unittest.TestCase):
    def test_parses_bse_scrip_code_isin_and_cash_prices(self):
        rows = [row(str(500000 + i), f"SYM{i}", f"INE{i:07d}A01001") for i in range(500)]
        parsed = parse_bse_cm_csv(payload(rows), "2026-11-06")
        self.assertEqual(len(parsed), 500)
        self.assertEqual(parsed[0]["instrument_id"], "500000")
        self.assertEqual(parsed[0]["isin"], "INE0000000A01001")
        self.assertEqual(parsed[0]["close"], 105.0)
        self.assertEqual(parsed[0]["previous_close"], 100.0)

    def test_rejects_wrong_trade_date(self):
        bad = row()
        bad["TradDt"] = "2026-11-05"
        with self.assertRaisesRegex(ValueError, "trade date mismatch"):
            parse_bse_cm_csv(payload([bad] * 500), "2026-11-06")

    def test_rejects_duplicate_scrip_code(self):
        with self.assertRaisesRegex(ValueError, "duplicate BSE scrip code"):
            parse_bse_cm_csv(payload([row(), row()] + [row(str(500002 + i)) for i in range(498)]), "2026-11-06")

    def test_rejects_invalid_ohlc(self):
        bad = row()
        bad["LwPric"] = "111"
        with self.assertRaisesRegex(ValueError, "inconsistent BSE OHLC"):
            parse_bse_cm_csv(payload([bad] + [row(str(500002 + i)) for i in range(499)]), "2026-11-06")

    def test_rejects_wrong_schema(self):
        with self.assertRaisesRegex(ValueError, "missing columns"):
            parse_bse_cm_csv(b"Sgmt,Src\nCM,BSE\n", "2026-11-06")

    def test_download_makes_exactly_one_official_request(self):
        session = Mock()
        response = Mock(status_code=200, content=b"csv")
        session.get.return_value = response
        body, url = fetch_official_bse_cm_bhavcopy("2026-11-06", session=session)
        self.assertEqual(body, b"csv")
        self.assertEqual(
            url,
            "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_20261106_F_0000.csv",
        )
        self.assertEqual(session.get.call_count, 1)

    def test_http_error_does_not_retry(self):
        session = Mock()
        session.get.return_value = Mock(status_code=404, content=b"")
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            fetch_official_bse_cm_bhavcopy("2026-11-06", session=session)
        self.assertEqual(session.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
