from decimal import Decimal
import unittest

from bambo_bot.financial_contract import (
    AmbiguousQuantityError,
    CURRENCY_RIAL,
    CURRENCY_TOMAN,
    financial_capabilities,
    normalize_currency,
    normalize_exposure,
    validate_currency_contract,
)


class FinancialContractTests(unittest.TestCase):
    def test_unverified_corporate_actions_are_explicitly_excluded(self):
        capabilities = financial_capabilities()

        self.assertEqual(capabilities["calculation_version"], 8)
        self.assertEqual(capabilities["currency_unit"], "rial")
        corporate_actions = capabilities["corporate_actions"]
        self.assertEqual(corporate_actions["status"], "not_supported")
        self.assertFalse(corporate_actions["automatic_adjustment"])
        self.assertEqual(corporate_actions["supported_events"], [])
        self.assertIn("cash_dividend", corporate_actions["excluded_events"])
        self.assertIn("adjusted_contract_multiplier", corporate_actions["excluded_events"])

    def test_contract_quantity_expands_once_by_contract_size(self):
        exposure = normalize_exposure(
            quantity="2",
            quantity_kind="contract",
            contract_size="1000",
            calculation_version=8,
        )

        self.assertEqual(exposure.contract_quantity, Decimal("2"))
        self.assertEqual(exposure.underlying_units, Decimal("2000"))

    def test_fractional_contract_quantity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            normalize_exposure(
                quantity="1.5",
                quantity_kind="contract",
                contract_size="1000",
                calculation_version=8,
            )

    def test_legacy_unit_quantity_is_not_multiplied_twice(self):
        exposure = normalize_exposure(
            quantity="2000",
            quantity_kind="unit",
            contract_size="1000",
            calculation_version=7,
        )

        self.assertEqual(exposure.underlying_units, Decimal("2000"))
        self.assertEqual(exposure.contract_quantity, Decimal("2"))

    def test_unknown_legacy_semantics_are_not_guessed(self):
        with self.assertRaises(AmbiguousQuantityError):
            normalize_exposure(
                quantity="2",
                quantity_kind=None,
                contract_size="1000",
                calculation_version=7,
            )

    def test_non_integral_unit_conversion_remains_exact_and_explicit(self):
        exposure = normalize_exposure(
            quantity="250",
            quantity_kind="unit",
            contract_size="1000",
            calculation_version=7,
        )

        self.assertEqual(exposure.underlying_units, Decimal("250"))
        self.assertEqual(exposure.contract_quantity, Decimal("0.25"))

    def test_currency_conversion_is_exact_and_centralized(self):
        self.assertEqual(
            normalize_currency(
                "123456789.123456",
                from_unit=CURRENCY_TOMAN,
                to_unit=CURRENCY_RIAL,
            ),
            Decimal("1234567891.234560"),
        )
        self.assertEqual(
            normalize_currency(
                "1234567891.234560",
                from_unit=CURRENCY_RIAL,
                to_unit=CURRENCY_TOMAN,
            ),
            Decimal("123456789.123456"),
        )

    def test_v8_rejects_noncanonical_toman_without_silent_conversion(self):
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_currency_contract(
                currency_unit=CURRENCY_TOMAN,
                calculation_version=8,
            )

        self.assertEqual(
            validate_currency_contract(
                currency_unit=CURRENCY_TOMAN,
                calculation_version=7,
            ),
            CURRENCY_TOMAN,
        )


if __name__ == "__main__":
    unittest.main()
