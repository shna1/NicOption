from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

try:
    from audit.reference_engine import long_call_mark_to_market
except ModuleNotFoundError:
    long_call_mark_to_market = None
from bambo_bot.trades import quote_key, tehran_today
from nicoption_dashboard.models import TradeRecord
from nicoption_dashboard.services import get_runtime


@skipUnless(long_call_mark_to_market, "private audit reference engine is excluded from the portfolio repository")
class FinancialCrossLayerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cross-layer-user")
        self.client.force_login(self.user)
        get_runtime.cache_clear()
        self.runtime = get_runtime(self.user.pk)

    def tearDown(self):
        get_runtime.cache_clear()

    def test_decimal_value_reconciles_from_database_through_api(self):
        today = tehran_today()
        expiry = today + timedelta(days=30)
        symbol = "ضدقت-آزمون"
        payload = {
            "id": "cross-layer-decimal",
            "status": "open",
            "market": "tehran",
            "strategy_type": "long_call",
            "asset": "دقت",
            "option_symbol": symbol,
            "entry_date": today.isoformat(),
            "entry_base_price": "1.5",
            "entry_premium": "0.1",
            "quantity": 3,
            "exercise_quantity": 0,
            "premium_trade_quantity": 3,
            "commission": "0.2",
            "option_exit_commission_estimate": "0",
            "exercise_commission_estimate": "0",
            "underlying_exit_commission_estimate": "0",
            "strike": "1",
            "expiry": expiry.isoformat(),
            "contract_size": "1",
            "quantity_kind": "contract",
            "currency_unit": "rial",
            "calculation_version": 8,
            "money_values": {
                "entry_base_price": "1.5",
                "entry_premium": "0.1",
                "commission": "0.2",
                "strike": "1",
            },
        }
        TradeRecord.objects.create(
            id=payload["id"],
            owner=self.user,
            status="open",
            payload=payload,
            quantity_kind="contract",
            contract_size=Decimal("1"),
            currency_unit="rial",
            calculation_version=8,
        )
        quote = {
            "market": "tehran",
            "asset": "دقت",
            "symbol": symbol,
            "base_last": "2",
            "option_last": "0.3",
            "strike": "1",
            "expiry": expiry.isoformat(),
            "contract_size": 1,
        }
        generated_at = datetime.now().astimezone().isoformat()

        with patch.multiple(
            self.runtime.cache,
            get=lambda: {"generated_at": generated_at},
            trade_quotes=lambda: {quote_key("tehran", symbol): quote},
        ):
            response = self.client.get("/api/trades")

        self.assertEqual(response.status_code, 200, response.content)
        api_trade = response.json()["trades"][0]
        database_trade = TradeRecord.objects.get(pk=payload["id"])
        reference_profit = long_call_mark_to_market(
            entry_premium="0.1",
            current_premium="0.3",
            multiplier=1,
            contracts=3,
            fees="0.2",
        )

        self.assertEqual(database_trade.payload["money_values"]["entry_premium"], "0.1")
        self.assertEqual(api_trade["money_values"]["invested_capital"], "0.5")
        self.assertEqual(api_trade["money_values"]["long_offset_profit"], "0.4")
        self.assertEqual(Decimal(api_trade["money_values"]["long_offset_profit"]), reference_profit)
