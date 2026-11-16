from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import connection, close_old_connections
from django.test import TransactionTestCase

from ..models import TradeRecord, UnderlyingPositionRecord
from ..stores import DjangoTradeStore, DjangoUnderlyingPositionStore


class PostgreSQLMutationConcurrencyTests(TransactionTestCase):
    """Exercise the row-lock contract with independent DB connections."""

    reset_sequences = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-specific concurrency verification")
        self.user = get_user_model().objects.create_user(username="pg-race-user")
        self.quote = {
            "market": "tehran",
            "asset": "وبملت",
            "symbol": "ضملت-race",
            "base_last": 2400,
            "option_last": 100,
            "strike": 2500,
            "contract_size": 1000,
            "expiry": (date.today() + timedelta(days=30)).isoformat(),
        }
        self.payload = {
            "market": "tehran",
            "strategy_type": "covered_call",
            "asset": "وبملت",
            "option_symbol": "ضملت-race",
            "entry_date": (date.today() - timedelta(days=1)).isoformat(),
            "entry_base_price": 2410,
            "entry_premium": 183,
            "quantity": 1,
            "commission": 0,
            "quantity_kind": "contract",
            "currency_unit": "rial",
            "calculation_version": 8,
        }

    @staticmethod
    def _run_workers(*workers):
        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = [executor.submit(worker) for worker in workers]
            return [future.result(timeout=10) for future in futures]

    def test_same_version_concurrent_updates_have_one_winner(self):
        created = DjangoTradeStore(self.user.pk).create(self.payload, self.quote)
        barrier = Barrier(2)

        def update(premium):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                result = DjangoTradeStore(self.user.pk).update(
                    created["id"],
                    {
                        **self.payload,
                        "entry_premium": premium,
                        "mutation_version": 1,
                    },
                    self.quote,
                )
                return "updated", result["mutation_version"]
            except ValueError as exc:
                return "rejected", str(exc)
            finally:
                connection.close()

        results = self._run_workers(
            lambda: update(190),
            lambda: update(195),
        )

        self.assertEqual(sorted(result[0] for result in results), ["rejected", "updated"])
        self.assertIn(("updated", 2), results)
        rejected = next(result[1] for result in results if result[0] == "rejected")
        self.assertIn("همزمان تغییر کرده", rejected)
        self.assertEqual(
            TradeRecord.objects.get(pk=created["id"]).mutation_version,
            2,
        )

    def test_concurrent_creates_do_not_lose_a_trade(self):
        barrier = Barrier(2)

        def create(suffix):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                result = DjangoTradeStore(self.user.pk).create(
                    {
                        **self.payload,
                        "option_symbol": f"ضملت-race-{suffix}",
                    },
                    {**self.quote, "symbol": f"ضملت-race-{suffix}"},
                )
                return result["id"]
            finally:
                connection.close()

        ids = self._run_workers(lambda: create("a"), lambda: create("b"))

        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(TradeRecord.objects.filter(owner=self.user).count(), 2)

    def test_concurrent_underlying_sales_cannot_oversell_inventory(self):
        position = DjangoUnderlyingPositionStore(self.user.pk).create({
            "market": "tehran",
            "asset": "وبملت",
            "acquisition_method": "direct",
            "entry_date": (date.today() - timedelta(days=1)).isoformat(),
            "entry_price": 2400,
            "quantity": 10,
            "commission": 0,
            "quantity_kind": "unit",
            "currency_unit": "rial",
            "calculation_version": 8,
        })
        barrier = Barrier(2)

        def sell():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                result = DjangoUnderlyingPositionStore(self.user.pk).sell_quantity(
                    position["id"],
                    7,
                    exit_date=date.today(),
                    exit_price=2500,
                    exit_commission=0,
                )
                return "sold", result["quantity"]
            except ValueError as exc:
                return "rejected", str(exc)
            finally:
                connection.close()

        results = self._run_workers(sell, sell)

        self.assertEqual(sorted(result[0] for result in results), ["rejected", "sold"])
        rejected = next(result[1] for result in results if result[0] == "rejected")
        self.assertIn("بیشتر از موجودی", rejected)
        rows = list(
            UnderlyingPositionRecord.objects.filter(owner=self.user).values_list(
                "status", "payload"
            )
        )
        open_quantities = [row[1]["quantity"] for row in rows if row[0] == "open"]
        closed_quantities = [row[1]["quantity"] for row in rows if row[0] == "closed"]
        self.assertEqual(open_quantities, [3.0])
        self.assertEqual(closed_quantities, [7.0])
