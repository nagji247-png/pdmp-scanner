import unittest
from datetime import date
from unittest.mock import Mock

from tradingview_front_month import (
    contract_code_matches_expiry,
    contract_code_month,
    fetch_front_month_code,
    parse_front_month,
    select_front_month_quote,
)


class TradingViewFrontMonthTests(unittest.TestCase):
    def test_parses_gold_front_month_from_visible_html(self):
        html = "<div>Contract highlights</div><span>Front month</span><b>GOLDZ2026</b>"
        self.assertEqual(parse_front_month(html, "GOLD"), "GOLDZ2026")

    def test_parses_silver_front_month_from_plain_text(self):
        text = "Volume Open interest Contract size 30 KG Front month SILVERZ2026"
        self.assertEqual(parse_front_month(text, "SILVER"), "SILVERZ2026")

    def test_does_not_pick_nearest_contract_when_front_month_missing(self):
        text = "Nearest contracts GOLDZ2026 Dec 2026 GOLDG2027 Feb 2027"
        self.assertIsNone(parse_front_month(text, "GOLD"))

    def test_rejects_wrong_symbol_and_malformed_code(self):
        self.assertIsNone(parse_front_month("Front month GOLDZ2026", "SILVER"))
        self.assertIsNone(parse_front_month("Front month GOLDI2026", "GOLD"))
        self.assertIsNone(parse_front_month("Front month GOLDZ26", "GOLD"))

    def test_decodes_standard_month_codes(self):
        self.assertEqual(contract_code_month("GOLDZ2026", "GOLD"), (2026, 12))
        self.assertEqual(contract_code_month("SILVERH2027", "SILVER"), (2027, 3))
        self.assertIsNone(contract_code_month("GOLDM2026", "SILVER"))

    def test_matches_expiry_month_and_year(self):
        self.assertTrue(contract_code_matches_expiry("GOLDZ2026", "GOLD", date(2026, 12, 4)))
        self.assertFalse(contract_code_matches_expiry("GOLDZ2026", "GOLD", date(2027, 2, 5)))
        self.assertTrue(contract_code_matches_expiry("SILVERH2027", "SILVER", date(2027, 3, 5)))

    def test_fetch_reads_explicit_label_and_sets_timeout(self):
        response = Mock()
        response.text = "<span>Front month</span><b>GOLDZ2026</b>"
        get = Mock(return_value=response)
        self.assertEqual(fetch_front_month_code("GOLD", get), "GOLDZ2026")
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["timeout"], 12)

    def test_fetch_failure_returns_none(self):
        get = Mock(side_effect=TimeoutError("blocked"))
        self.assertIsNone(fetch_front_month_code("SILVER", get))

    def test_selects_matching_mcx_expiry_not_highest_oi(self):
        feb = {"symbol": "GOLD", "expiry": "2027-02-05", "open_interest": 50000, "price": 128104}
        dec = {"symbol": "GOLD", "expiry": "2026-12-04", "open_interest": 6000, "price": 125534}
        self.assertEqual(select_front_month_quote([feb, dec], "GOLD", "GOLDZ2026"), dec)

    def test_missing_or_ambiguous_match_is_not_guessed(self):
        dec = {"symbol": "GOLD", "expiry": "2026-12-04", "price": 125534}
        self.assertIsNone(select_front_month_quote([dec], "GOLD", None))
        self.assertIsNone(select_front_month_quote([], "GOLD", "GOLDZ2026"))
        self.assertIsNone(select_front_month_quote([dec, dict(dec)], "GOLD", "GOLDZ2026"))

    def test_full_size_symbol_is_required(self):
        mini = {"symbol": "GOLDM", "expiry": "2026-12-04", "price": 125000}
        missing_symbol = {"expiry": "2026-12-04", "price": 125000}
        self.assertIsNone(select_front_month_quote([mini], "GOLD", "GOLDZ2026"))
        self.assertIsNone(select_front_month_quote([missing_symbol], "GOLD", "GOLDZ2026"))


if __name__ == "__main__":
    unittest.main()
