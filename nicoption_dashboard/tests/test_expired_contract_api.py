import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from bambo_bot.trades import tehran_today
from nicoption_dashboard.models import TradeMutationRequest, TradeRecord
from nicoption_dashboard.services import get_runtime


class ExpiredContractApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="expired-contract-user")
        self.client.force_login(self.user)
        get_runtime.cache_clear()
        self.runtime = get_runtime(self.user.pk)

    def tearDown(self):
        get_runtime.cache_clear()

    def payload(self, **changes):
        expiry = tehran_today() - timedelta(days=1)
        payload = {
            "market": "tehran",
            "strategy_type": "long_call",
            "asset": "اهرم",
            "option_symbol": "ضهرم-منقضی",
            "contract_entry_mode": "manual_expired",
            "manual_option_symbol": "ضهرم-منقضی",
            "manual_strike": 12_500,
            "manual_expiry": expiry.isoformat(),
            "manual_contract_size": 1000,
            "entry_date": (expiry - timedelta(days=10)).isoformat(),
            "entry_base_price": 13_000,
            "entry_premium": 350,
            "exercise_quantity": 1,
            "premium_trade_quantity": 0,
            "commission": 12,
            "price_confirmed": True,
        }
        payload.update(changes)
        return payload

    def market_cache(self):
        generated_at = datetime.now().astimezone().isoformat()
        return patch.multiple(
            self.runtime.cache,
            get=lambda: {"generated_at": generated_at},
            trade_quotes=lambda: {},
        )

    def test_create_and_edit_expired_contract_without_live_quote(self):
        with self.market_cache():
            created = self.client.post(
                "/api/trades",
                data=json.dumps(self.payload()),
                content_type="application/json",
            )
        self.assertEqual(created.status_code, 201, created.content)
        created_trade = created.json()["trades"][0]
        self.assertEqual(created_trade["quantity"], 1)
        self.assertEqual(created_trade["underlying_units"], 1000)
        self.assertEqual(created_trade["invested_capital"], 350_012)
        record = TradeRecord.objects.get(owner=self.user)
        self.assertEqual(record.payload["contract_entry_mode"], "manual_expired")
        self.assertEqual(record.payload["strike"], 12_500)
        self.assertEqual(record.quantity_kind, "contract")
        self.assertEqual(record.currency_unit, "rial")
        self.assertEqual(record.calculation_version, 8)
        self.assertEqual(str(record.contract_size), "1000.000000")

        with self.market_cache():
            updated = self.client.put(
                f"/api/trades/{record.id}",
                data=json.dumps(self.payload(manual_strike=13_000)),
                content_type="application/json",
            )
        self.assertEqual(updated.status_code, 200, updated.content)
        record.refresh_from_db()
        self.assertEqual(record.payload["strike"], 13_000)

    def test_future_contract_cannot_bypass_live_market_lookup(self):
        with self.market_cache():
            response = self.client.post(
                "/api/trades",
                data=json.dumps(self.payload(
                    manual_expiry=(tehran_today() + timedelta(days=1)).isoformat(),
                )),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("گذشته یا امروز", response.json()["error"])
        self.assertFalse(TradeRecord.objects.filter(owner=self.user).exists())

    def test_create_trade_idempotency_key_prevents_retry_duplicate(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "expired-create-1"}
        with self.market_cache():
            first = self.client.post(
                "/api/trades", data=json.dumps(self.payload()),
                content_type="application/json", **headers,
            )
            retry = self.client.post(
                "/api/trades", data=json.dumps(self.payload()),
                content_type="application/json", **headers,
            )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(TradeRecord.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(TradeMutationRequest.objects.filter(owner=self.user).count(), 1)

    def test_reusing_idempotency_key_for_different_payload_is_conflict(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "expired-create-conflict"}
        with self.market_cache():
            first = self.client.post(
                "/api/trades", data=json.dumps(self.payload()),
                content_type="application/json", **headers,
            )
            conflict = self.client.post(
                "/api/trades", data=json.dumps(self.payload(entry_premium=351)),
                content_type="application/json", **headers,
            )
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(TradeRecord.objects.filter(owner=self.user).count(), 1)
