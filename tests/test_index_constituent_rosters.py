import unittest

from index_constituent_rosters import (
    parse_nse_constituent_csv,
    parse_bse_sensex_constituents,
)


def nse_csv(count):
    lines = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    for i in range(count):
        lines.append(f"Company {i},Sector,SYM{i:02d},EQ,IN{i:09d}0")
    return ("\n".join(lines) + "\n").encode("utf-8")


def bse_html(codes):
    rows = ["<table><tr><th>Constituents</th><th>Symbol</th><th>Sector</th></tr>"]
    rows.extend(f"<tr><td>Company {i}</td><td>{code}</td><td>Financial Services</td></tr>"
                for i, code in enumerate(codes))
    rows.append("</table>")
    return "".join(rows)


class OfficialRosterCaptureTests(unittest.TestCase):
    def test_nifty_requires_exactly_50_unique_symbol_isin_pairs(self):
        result = parse_nse_constituent_csv(
            nse_csv(50), "NIFTY", "2026-11-09",
            "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
        )
        self.assertEqual(result["expected_count"], 50)
        self.assertEqual(len(result["members"]), 50)
        self.assertEqual(result["members"][0]["symbol"], "SYM00")

    def test_bank_nifty_requires_exactly_14_members(self):
        result = parse_nse_constituent_csv(
            nse_csv(14), "BANKNIFTY", "2026-11-09",
            "https://nsearchives.nseindia.com/content/indices/ind_niftybanklist.csv",
        )
        self.assertEqual(len(result["members"]), 14)

    def test_nse_roster_count_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected 50 members"):
            parse_nse_constituent_csv(
                nse_csv(49), "NIFTY", "2026-11-09",
                "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
            )

    def test_nse_duplicate_isin_is_rejected(self):
        raw = nse_csv(50).decode("utf-8").replace("SYM01,EQ,IN0000000010", "SYM01,EQ,IN0000000000")
        with self.assertRaisesRegex(ValueError, "duplicate symbol or ISIN"):
            parse_nse_constituent_csv(
                raw.encode(), "NIFTY", "2026-11-09",
                "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
            )

    def test_sensex_uses_official_bse_scrip_code_and_same_day_cash_isin(self):
        codes = [str(500000 + i) for i in range(30)]
        archive = {"records": [{
            "date": "2026-11-09",
            "equity_rows": [
                {"instrument_id": code, "isin": f"IN{i:09d}0"}
                for i, code in enumerate(codes)
            ],
        }]}
        result = parse_bse_sensex_constituents(
            bse_html(codes), archive, "2026-11-09",
            "https://www.bseindices.com/constituents/code/16",
        )
        self.assertEqual(result["expected_count"], 30)
        self.assertEqual(len(result["members"]), 30)
        self.assertEqual(result["members"][0]["instrument_id"], "500000")

    def test_sensex_parses_official_bse_constituent_api_json(self):
        codes = [str(500000 + i) for i in range(30)]
        archive = {"records": [{
            "date": "2026-11-09",
            "equity_rows": [
                {"instrument_id": code, "isin": f"IN{i:09d}0"}
                for i, code in enumerate(codes)
            ],
        }]}
        api_payload = {
            "Table": [
                {"SCRIP_CODE": code, "SCRIPNAME": f"Company {i}", "Industry_name": "Sector"}
                for i, code in enumerate(codes)
            ]
        }
        result = parse_bse_sensex_constituents(
            api_payload, archive, "2026-11-09",
            "https://www.bseindices.com/AsiaIndexAPI/api/Codewise_Indices/w?code=16",
        )
        self.assertEqual(len(result["members"]), 30)
        self.assertEqual(result["members"][0]["instrument_id"], "500000")

    def test_sensex_missing_same_day_archive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "same-date BSE cash archive missing"):
            parse_bse_sensex_constituents(
                bse_html([str(500000 + i) for i in range(30)]),
                {"records": []}, "2026-11-09",
                "https://www.bseindices.com/constituents/code/16",
            )

    def test_sensex_requires_30_unique_scrip_codes(self):
        with self.assertRaisesRegex(ValueError, "30 unique BSE scrip codes"):
            parse_bse_sensex_constituents(
                bse_html([str(500000 + i) for i in range(29)]),
                {"records": []}, "2026-11-09",
                "https://www.bseindices.com/constituents/code/16",
            )


if __name__ == "__main__":
    unittest.main()
