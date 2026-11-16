from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AccountMoneyMigrationTests(TransactionTestCase):
    migrate_from = ("nicoption_dashboard", "0010_trade_mutation_safety")
    migrate_to = ("nicoption_dashboard", "0011_account_money_decimal")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        User = old_apps.get_model("auth", "User")
        AccountPreference = old_apps.get_model(
            "nicoption_dashboard", "AccountPreference"
        )
        owner = User.objects.create(username="money-migration-owner")
        AccountPreference.objects.create(
            owner_id=owner.pk,
            initial_capital=123456789.125,
            cash_balance=0.125,
        )
        self.owner_id = owner.pk

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_forward_and_reverse_preserve_representable_legacy_values(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        apps = executor.loader.project_state([self.migrate_to]).apps
        AccountPreference = apps.get_model(
            "nicoption_dashboard", "AccountPreference"
        )
        preference = AccountPreference.objects.get(owner_id=self.owner_id)

        self.assertEqual(
            preference.initial_capital,
            Decimal("123456789.125000"),
        )
        self.assertEqual(preference.cash_balance, Decimal("0.125000"))

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldAccountPreference = old_apps.get_model(
            "nicoption_dashboard", "AccountPreference"
        )
        restored = OldAccountPreference.objects.get(owner_id=self.owner_id)
        self.assertEqual(restored.initial_capital, 123456789.125)
        self.assertEqual(restored.cash_balance, 0.125)
