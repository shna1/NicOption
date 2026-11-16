import unittest

from datetime import date, datetime
from zoneinfo import ZoneInfo

from bambo_bot.dates import (
    format_jalali_datetime,
    format_market_expiry,
    gregorian_to_jalali,
    jalali_to_gregorian,
    parse_user_date,
)


class DateTests(unittest.TestCase):
    def test_jalali_input_converts_to_gregorian(self):
        self.assertEqual(jalali_to_gregorian(1405, 5, 12), (2026, 8, 3))
        self.assertEqual(parse_user_date("۱۴۰۵/۰۵/۱۲"), date(2026, 8, 3))
        self.assertEqual(parse_user_date("1405-08-19"), date(2026, 11, 10))

    def test_known_gregorian_date_converts_to_jalali(self):
        self.assertEqual(gregorian_to_jalali(2026, 7, 18), (1405, 4, 27))

    def test_all_market_expiries_use_jalali_slash_format(self):
        self.assertEqual(format_market_expiry("2026-09-16", "tehran"), "1405/06/25")
        self.assertEqual(format_market_expiry("1405-06-01", "goods"), "1405/06/01")
        self.assertEqual(format_market_expiry("2026-11-10", "goods"), "1405/08/19")

    def test_datetime_is_rendered_with_jalali_date(self):
        value = datetime(2026, 7, 18, 14, 35, tzinfo=ZoneInfo("Asia/Tehran"))
        self.assertEqual(format_jalali_datetime(value), "1405/04/27 14:35")


if __name__ == "__main__":
    unittest.main()
