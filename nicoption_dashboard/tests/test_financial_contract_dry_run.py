from __future__ import annotations

from io import StringIO
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from ..models import TradeRecord, UnderlyingPositionRecord


class FinancialContractDryRunTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="financial-dry-run")

    def test_report_keeps_legacy_trade_ambiguous_and_does_not_write(self):
        record = TradeRecord.objects.create(
            id="legacy-trade",
            owner=self.user,
            payload={
                "strategy_type": "long_call",
                "quantity": 2,
                "contract_size": 1000,
                "entry_premium": 5,
            },
        )
        output = StringIO()

        call_command("financial_contract_dry_run", format="json", stdout=output)

        report = json.loads(output.getvalue())
        row = next(item for item in report["records"] if item["record_id"] == record.id)
        self.assertEqual(row["classification"], "AMBIGUOUS")
        self.assertFalse(row["migration_eligible"])
        self.assertIsNone(row["proposed_financial_value"])
        record.refresh_from_db()
        self.assertIsNone(record.quantity_kind)
        self.assertIsNone(record.calculation_version)

    def test_explicit_contract_metadata_has_decimal_before_after_evidence(self):
        TradeRecord.objects.create(
            id="canonical-trade",
            owner=self.user,
            quantity_kind="contract",
            contract_size="1000",
            currency_unit="rial",
            calculation_version=8,
            payload={
                "strategy_type": "long_call",
                "quantity": 2,
                "contract_size": 1000,
                "entry_premium": 5,
                "quantity_kind": "contract",
                "currency_unit": "rial",
                "calculation_version": 8,
            },
        )
        output = StringIO()

        call_command("financial_contract_dry_run", format="json", stdout=output)

        report = json.loads(output.getvalue())
        row = next(
            item for item in report["records"]
            if item["record_id"] == "canonical-trade"
        )
        self.assertEqual(row["classification"], "CONFIRMED_CONTRACT_QUANTITY")
        self.assertTrue(row["migration_eligible"])
        self.assertEqual(row["current_financial_value"], "10")
        self.assertEqual(row["proposed_financial_value"], "10000")
        self.assertEqual(row["absolute_difference"], "9990")
        self.assertEqual(row["relative_difference"], "999")

    def test_exercise_position_with_unapplied_multiplier_is_invalid(self):
        UnderlyingPositionRecord.objects.create(
            id="bad-exercise-position",
            owner=self.user,
            payload={
                "acquisition_method": "exercise",
                "quantity": 3,
                "entry_price": 1050,
                "source_contracts": 3,
                "source_contract_size": 1000,
            },
        )
        output = StringIO()

        call_command("financial_contract_dry_run", format="json", stdout=output)

        report = json.loads(output.getvalue())
        row = next(
            item for item in report["records"]
            if item["record_id"] == "bad-exercise-position"
        )
        self.assertEqual(row["classification"], "INVALID")
        self.assertFalse(row["migration_eligible"])
        self.assertEqual(report["summary"]["INVALID"], 1)
