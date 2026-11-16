import unittest
from datetime import date
from decimal import Decimal

from bambo_bot.financial_rates import (
    calculate_commission,
    resolve_commission_rate,
    resolve_risk_free_rate,
)


class FinancialRateScheduleTests(unittest.TestCase):
    def test_risk_free_snapshot_has_rate_source_version_and_effective_date(self):
        snapshot = resolve_risk_free_rate(as_of=date(2026, 10, 18))

        self.assertEqual(snapshot.rate_percent, Decimal("40"))
        self.assertEqual(snapshot.version, "ir-risk-free-legacy-v1")
        self.assertEqual(snapshot.effective_from, date(2020, 1, 1))
        self.assertEqual(snapshot.source, "legacy-static-unverified")

    def test_explicit_risk_free_override_is_labeled(self):
        snapshot = resolve_risk_free_rate(
            as_of=date(2026, 10, 18),
            override="37.125",
        )

        self.assertEqual(snapshot.rate_percent, Decimal("37.125"))
        self.assertEqual(snapshot.source, "user_override")

    def test_commission_rate_has_reproducible_schedule_metadata(self):
        snapshot = resolve_commission_rate(
            market="tehran",
            kind="option_buy",
            as_of=date(2026, 10, 18),
        )

        self.assertEqual(snapshot.rate, Decimal("0.00103"))
        self.assertEqual(snapshot.version, "ir-fees-legacy-v1")
        self.assertEqual(snapshot.effective_from, date(2020, 1, 1))
        self.assertEqual(snapshot.source, "legacy-static-unverified")
        self.assertEqual(snapshot.rounding_mode, "ROUND_HALF_EVEN")
        self.assertEqual(snapshot.rounding_increment, Decimal("1"))
        self.assertEqual(
            snapshot.rounding_version,
            "nearest-rial-half-even-legacy-v1",
        )

    def test_commission_rounding_is_decimal_explicit_and_reproducible(self):
        low_tie, low_snapshot = calculate_commission(
            market="goods",
            kind="option_buy",
            as_of=date(2026, 10, 18),
            price="1250",
            quantity="1",
        )
        high_tie, high_snapshot = calculate_commission(
            market="goods",
            kind="option_buy",
            as_of=date(2026, 10, 18),
            price="3750",
            quantity="1",
        )

        self.assertEqual(low_tie, Decimal("2"))
        self.assertEqual(high_tie, Decimal("4"))
        self.assertEqual(low_snapshot.rounding_version, high_snapshot.rounding_version)


if __name__ == "__main__":
    unittest.main()
