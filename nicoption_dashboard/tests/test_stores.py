from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import AccountPreference, TradeRecord, UserAccessProfile
from ..stores import DjangoAccountStore, DjangoTradeStore


class DjangoStoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="store-user")
        self.store = DjangoTradeStore(self.user.pk)
        self.quote = {
            "market": "tehran",
            "asset": "وبملت",
            "symbol": "ضملت9999",
            "base_last": 2400,
            "option_last": 100,
            "strike": 2500,
            "expiry": (date.today() + timedelta(days=30)).isoformat(),
        }
        self.payload = {
            "market": "tehran",
            "strategy_type": "covered_call",
            "asset": "وبملت",
            "option_symbol": "ضملت9999",
            "entry_date": (date.today() - timedelta(days=1)).isoformat(),
            "entry_base_price": 2410,
            "entry_premium": 183,
            "quantity": 1,
            "commission": 0,
            "annual_interest_rate": 40,
        }

    def test_new_user_gets_safe_default_access_role(self):
        self.assertEqual(
            self.user.access_profile.role,
            UserAccessProfile.Role.VIEWER,
        )

    def test_trade_lifecycle_is_persisted_in_orm(self):
        created = self.store.create(self.payload, self.quote)
        self.assertEqual(TradeRecord.objects.count(), 1)
        self.assertEqual(TradeRecord.objects.get().owner, self.user)
        self.assertEqual(self.store.list()[0]["id"], created["id"])

        edited = {**self.payload, "entry_premium": 190}
        self.store.update(created["id"], edited, self.quote)
        self.assertEqual(self.store.list()[0]["entry_premium"], 190)

        self.store.close(
            created["id"], self.quote,
            exit_date=date.today(), exit_method="offset",
            exit_base_price=2390, exit_option_price=120,
            price_confirmed=True,
        )
        self.assertEqual(self.store.list()[0]["status"], "closed")

        self.store.delete(created["id"])
        self.assertFalse(TradeRecord.objects.exists())

    def test_trade_mutation_version_rejects_stale_update(self):
        created = self.store.create(self.payload, self.quote)
        self.assertEqual(created["mutation_version"], 1)

        updated = self.store.update(
            created["id"],
            {**self.payload, "entry_premium": 190, "mutation_version": 1},
            self.quote,
        )
        self.assertEqual(updated["mutation_version"], 2)
        self.assertEqual(TradeRecord.objects.get(pk=created["id"]).mutation_version, 2)

        with self.assertRaisesRegex(ValueError, "همزمان تغییر کرده"):
            self.store.update(
                created["id"],
                {**self.payload, "entry_premium": 195, "mutation_version": 1},
                self.quote,
            )

    def test_account_capital_is_persisted_in_orm(self):
        account = DjangoAccountStore(self.user.pk)
        account.save(1_000_000, 275_000)
        self.assertEqual(account.read()["initial_capital"], 1_000_000)
        self.assertEqual(account.read()["cash_balance"], 275_000)
        self.assertEqual(AccountPreference.objects.count(), 1)
        self.assertEqual(AccountPreference.objects.get().owner, self.user)

    def test_account_money_is_stored_as_decimal_without_float_round_trip(self):
        account = DjangoAccountStore(self.user.pk)
        account.save("123456789.123456", "0.100001")

        preference = AccountPreference.objects.get(owner=self.user)
        self.assertIsInstance(preference.initial_capital, Decimal)
        self.assertIsInstance(preference.cash_balance, Decimal)
        self.assertEqual(preference.initial_capital, Decimal("123456789.123456"))
        self.assertEqual(preference.cash_balance, Decimal("0.100001"))

    def test_account_capital_is_isolated_by_owner(self):
        other_user = get_user_model().objects.create_user(username="account-user")
        DjangoAccountStore(self.user.pk).save(1_000_000)
        DjangoAccountStore(other_user.pk).save(2_000_000)

        self.assertEqual(
            DjangoAccountStore(self.user.pk).read()["initial_capital"],
            1_000_000,
        )
        self.assertEqual(
            DjangoAccountStore(other_user.pk).read()["initial_capital"],
            2_000_000,
        )

    def test_trades_are_isolated_by_owner(self):
        other_user = get_user_model().objects.create_user(username="other-user")
        created = self.store.create(self.payload, self.quote)

        self.assertEqual(DjangoTradeStore(other_user.pk).list(), [])
        self.assertEqual(self.store.list()[0]["id"], created["id"])

    def test_explicit_financial_metadata_round_trips_without_float_conversion(self):
        TradeRecord.objects.create(
            id="metadata-trade",
            owner=self.user,
            quantity_kind="contract",
            contract_size="1000.125000",
            currency_unit="rial",
            calculation_version=8,
            payload={"id": "metadata-trade", "quantity": 2},
        )

        record = self.store.list()[0]

        self.assertEqual(record["quantity_kind"], "contract")
        self.assertEqual(record["contract_size"], "1000.125000")
        self.assertEqual(record["currency_unit"], "rial")
        self.assertEqual(record["calculation_version"], 8)
