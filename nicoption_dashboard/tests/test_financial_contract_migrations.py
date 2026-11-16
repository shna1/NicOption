from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class FinancialContractMigrationTests(TransactionTestCase):
    migrate_from = ("nicoption_dashboard", "0007_loginattempt")
    migrate_to = ("nicoption_dashboard", "0009_copy_explicit_financial_metadata")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        TradeRecord = old_apps.get_model("nicoption_dashboard", "TradeRecord")
        TradeRecord.objects.create(
            id="explicit-legacy",
            payload={
                "quantity": 2,
                "quantity_kind": "contract",
                "contract_size": "1000",
                "currency_unit": "rial",
                "calculation_version": 8,
            },
        )
        TradeRecord.objects.create(
            id="ambiguous-legacy",
            payload={"quantity": 2000, "contract_size": 1000},
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_forward_copy_is_conservative_and_schema_rollback_preserves_payload(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        apps = executor.loader.project_state([self.migrate_to]).apps
        TradeRecord = apps.get_model("nicoption_dashboard", "TradeRecord")

        explicit = TradeRecord.objects.get(pk="explicit-legacy")
        ambiguous = TradeRecord.objects.get(pk="ambiguous-legacy")
        self.assertEqual(explicit.quantity_kind, "contract")
        self.assertEqual(str(explicit.contract_size), "1000.000000")
        self.assertEqual(explicit.currency_unit, "rial")
        self.assertEqual(explicit.calculation_version, 8)
        self.assertIsNone(ambiguous.quantity_kind)
        self.assertEqual(str(ambiguous.contract_size), "1000.000000")
        self.assertIsNone(ambiguous.calculation_version)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldTradeRecord = old_apps.get_model("nicoption_dashboard", "TradeRecord")
        self.assertEqual(
            OldTradeRecord.objects.get(pk="explicit-legacy").payload["quantity_kind"],
            "contract",
        )
        self.assertEqual(
            OldTradeRecord.objects.get(pk="ambiguous-legacy").payload["quantity"],
            2000,
        )
