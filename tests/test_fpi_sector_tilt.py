import datetime as dt
import unittest

from fpi_sector_tilt import Rows, candidates, number, EQUITY_TOTAL_TOLERANCE_CR


class FpiSectorTiltTests(unittest.TestCase):
    def test_nsdl_equity_flow_column_is_parsed(self):
        cells = ["1", "Test Sector"] + ["0"] * 96
        cells[50] = "-1,234"
        markup = "<table><tr>" + "".join(f"<td>{value}</td>" for value in cells) + "</tr></table>"
        parser = Rows()
        parser.feed(markup)
        self.assertEqual(number(parser.rows[0][50]), -1234.0)

    def test_rounding_tolerance_keeps_consecutive_fortnight(self):
        self.assertEqual(EQUITY_TOTAL_TOLERANCE_CR, 5.0)
        self.assertLessEqual(abs(16618.0 - 16621.0), EQUITY_TOTAL_TOLERANCE_CR)
        self.assertGreater(abs(16614.0 - 16621.0), EQUITY_TOTAL_TOLERANCE_CR)

    def test_missing_or_dash_values_are_not_zero(self):
        self.assertIsNone(number(""))
        self.assertIsNone(number("—"))
        self.assertEqual(number("1,065.5"), 1065.5)

    def test_fortnight_candidates_are_latest_first_and_not_future(self):
        today = dt.date(2026, 11, 13)
        dates = candidates(today)
        self.assertEqual(dates[0], dt.date(2026, 10, 31))
        self.assertEqual(dates[1], dt.date(2026, 10, 15))
        self.assertTrue(all(value <= today for value in dates))
        self.assertEqual(len(dates), 18)


if __name__ == "__main__":
    unittest.main()
