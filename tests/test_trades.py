import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from bambo_bot.trades import (
    AccountStore,
    TradeStore,
    UnderlyingPositionStore,
    exercise_underlying_terms,
    prepare_underlying_payload,
    tehran_today,
    build_account_growth,
    build_covered_profit_recognition,
    build_portfolio_asset_ledger,
    build_quote_map,
    build_underlying_quote_map,
    calculate_trade_snapshot,
    calculate_underlying_snapshot,
    quote_key,
    resolve_trade_quote,
    select_trade_valuation_quote,
    summarize_closed_trades,
    summarize_open_trades,
    underlying_allocations,
    underlying_quote_key,
    validate_underlying_link,
    validate_underlying_position_change,
)


class TradeCalculationTests(unittest.TestCase):
    def test_asset_ledger_uses_legacy_covered_call_inputs_as_collateral(self):
        ledger = build_portfolio_asset_ledger(
            [{
                "status": "open", "strategy_type": "covered_call",
                "market": "tehran", "asset": "فولاد", "quantity": 300,
                "entry_base_price": 100, "current_base_price": 120,
                "underlying_position_id": None,
            }],
            [{
                "status": "open", "market": "tehran", "asset": "فولاد",
                "quantity": 700, "available_quantity": 700,
                "allocated_quantity": 0, "entry_price": 100,
                "commission": 0, "current_price": 120,
            }],
            cash_balance=25_000,
        )

        self.assertEqual(ledger["base"]["cost"], 100_000)
        self.assertEqual(ledger["free"]["cost"], 70_000)
        self.assertEqual(ledger["collateral"]["cost"], 30_000)
        self.assertEqual(ledger["free"]["price_profit"], 14_000)
        self.assertEqual(ledger["collateral"]["price_profit"], 6_000)
        self.assertEqual(ledger["collateral"]["legacy_trade_count"], 1)
        self.assertEqual(ledger["profit_policy"], "collateral_base_profit_is_informational_only")

    def test_asset_ledger_does_not_duplicate_linked_covered_collateral(self):
        ledger = build_portfolio_asset_ledger(
            [{
                "status": "open", "strategy_type": "covered_call",
                "market": "tehran", "asset": "فولاد", "quantity": 300,
                "entry_base_price": 100, "current_base_price": 120,
                "underlying_position_id": "base-1",
            }],
            [{
                "id": "base-1", "status": "open", "market": "tehran",
                "asset": "فولاد", "quantity": 1_000,
                "available_quantity": 700, "allocated_quantity": 300,
                "entry_price": 100, "commission": 0, "current_price": 120,
            }],
        )

        self.assertEqual(ledger["base"]["quantity"], 1_000)
        self.assertEqual(ledger["collateral"]["quantity"], 300)
        self.assertEqual(ledger["collateral"]["price_profit"], 6_000)
        self.assertEqual(ledger["collateral"]["legacy_trade_count"], 0)

    def test_closed_summary_reports_profit_duration_and_capital_day_yoy(self):
        trades = [
            {
                "status": "closed", "realized_profit": 100,
                "invested_capital": 1_000, "invested_days": 10,
                "asset": "فولاد", "strategy_type": "covered_call",
            },
            {
                "status": "closed", "realized_profit": -20,
                "invested_capital": 500, "invested_days": 20,
                "asset": "فولاد", "strategy_type": "long_call",
            },
            {"status": "open", "realized_profit": 999},
        ]
        result = summarize_closed_trades(trades)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["losses"], 1)
        self.assertEqual(result["net_profit"], 80)
        self.assertAlmostEqual(result["profit_percent"], 80 / 1500 * 100)
        self.assertEqual(result["average_holding_days"], 15)
        self.assertAlmostEqual(
            result["annualized_return_percent"],
            80 / (1000 * 10 + 500 * 20) * 365 * 100,
        )
        self.assertEqual(result["by_asset"][0]["asset"], "فولاد")
        self.assertEqual(result["by_asset"][0]["invested_capital"], 1500)
        self.assertEqual(result["by_asset"][0]["net_profit"], 80)
        self.assertAlmostEqual(result["by_asset"][0]["profit_percent"], 80 / 1500 * 100)
        self.assertEqual(result["by_asset"][0]["liquidity_share_percent"], 100)

    def test_closed_summary_evaluates_covered_call_strategy_components(self):
        trades = [
            {
                "status": "closed", "strategy_type": "covered_call",
                "entry_base_price": 100, "exit_base_price": 140,
                "entry_premium": 10, "strike": 120, "quantity": 2,
                "underlying_units": 2, "option_profit": 18,
                "realized_profit": 58, "realized_profit_percent": 58 / 182 * 100,
                "invested_capital": 182, "invested_days": 30,
                "exit_method": "exercise", "asset": "نمونه",
            },
            {
                "status": "closed", "strategy_type": "covered_call",
                "entry_base_price": 100, "exit_base_price": 80,
                "entry_premium": 8, "strike": 110, "quantity": 1,
                "underlying_units": 1, "option_profit": 7,
                "realized_profit": -13, "realized_profit_percent": -13 / 93 * 100,
                "invested_capital": 93, "invested_days": 20,
                "exit_method": "offset", "asset": "نمونه",
            },
        ]
        covered = summarize_closed_trades(trades)["covered_call"]
        self.assertEqual(covered["count"], 2)
        self.assertEqual(covered["total_premium_received"], 28)
        self.assertEqual(covered["premium_income_net"], 25)
        self.assertAlmostEqual(covered["premium_retained_percent"], 25 / 28 * 100)
        self.assertEqual(covered["assignment_rate_percent"], 50)
        self.assertEqual(covered["rolled_rate_percent"], 0)
        self.assertEqual(covered["share_return"], 60)
        self.assertEqual(covered["foregone_upside"], 40)
        self.assertEqual(covered["reconstructed_return"], 45)
        self.assertEqual(covered["covered_return"], 45)
        self.assertEqual(covered["holding_return"], 60)
        self.assertEqual(covered["covered_vs_holding"], -15)
        self.assertEqual(covered["holding_downside_loss"], 20)
        self.assertEqual(covered["covered_downside_loss"], 13)
        self.assertEqual(covered["drawdown_reduction"], 7)
        self.assertEqual(covered["drawdown_reduction_percent"], 35)

    def setUp(self):
        self.trade = {
            "id": "one",
            "status": "open",
            "market": "tehran",
            "asset": "نمونه",
            "option_symbol": "ضنمونه",
            "entry_date": "2026-07-29",
            "entry_base_price": 2410,
            "entry_premium": 183,
            "quantity": 1,
            "commission": 0,
            "strike": 2400,
            "expiry": "2026-08-28",
        }
        self.quote = {
            "base_price": 2361.8,
            "base_last": 2361.8,
            "option_exit_ask": 10,
            "option_last": 10,
            "strike": 2400,
            "expiry": "2026-08-28",
        }

    def test_reports_option_only_and_full_covered_call_profit(self):
        result = calculate_trade_snapshot(
            self.trade, self.quote, as_of=date(2026, 8, 3)
        )
        self.assertEqual(result["entry_days"], 30)
        self.assertEqual(result["elapsed_days"], 5)
        self.assertEqual(result["invested_days"], 5)
        self.assertAlmostEqual(result["strategy_progress_percent"], 5 / 30 * 100)
        self.assertAlmostEqual(result["expected_profit"], 173)
        self.assertAlmostEqual(result["expected_profit_percent"], 173 / 2227 * 100)
        self.assertAlmostEqual(result["option_profit"], 173)
        self.assertAlmostEqual(result["option_profit_fulfillment_percent"], 100)
        self.assertAlmostEqual(result["base_profit"], -48.2)
        self.assertAlmostEqual(result["total_profit"], 124.8)
        self.assertAlmostEqual(result["total_profit_percent"], 124.8 / 2227 * 100)
        self.assertAlmostEqual(
            result["current_itm_percent"],
            (2361.8 - 2400) / 2361.8 * 100,
            places=2,
        )
        self.assertEqual(result["current_moneyness"], "OTM")
        self.assertIsNotNone(result["current_option_delta"])
        self.assertAlmostEqual(
            result["total_profit_fulfillment_percent"], 124.8 / 173 * 100
        )
        self.assertAlmostEqual(result["covered_liquidation_profit"], 124.8)
        self.assertAlmostEqual(result["covered_option_only_profit"], 173)
        self.assertAlmostEqual(result["covered_hold_profit"], 173)
        self.assertAlmostEqual(result["covered_best_profit"], 173)
        self.assertEqual(
            result["covered_best_decision"], "نگهداری پوزیشن کاوردکال"
        )

    def test_reports_covered_call_position_indicators(self):
        trade = {
            **self.trade,
            "entry_base_price": 100,
            "entry_premium": 10,
            "quantity": 2,
            "commission": 2,
            "strike": 120,
        }
        quote = {**self.quote, "base_last": 130, "option_last": 18, "strike": 120}
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))

        self.assertEqual(result["covered_position_status"], "open")
        self.assertEqual(result["covered_net_premium_received"], 18)
        self.assertEqual(result["covered_net_premium_per_unit"], 9)
        self.assertAlmostEqual(result["covered_premium_return_percent"], 18 / 182 * 100)
        self.assertAlmostEqual(result["covered_premium_return_yoy"], 18 / 182 * 100 * 365 / 30)
        self.assertEqual(result["covered_strike_distance"], -10)
        self.assertAlmostEqual(result["covered_strike_distance_percent"], -10 / 130 * 100)
        self.assertEqual(result["covered_breakeven"], 91)
        self.assertEqual(result["covered_max_profit"], 58)
        self.assertEqual(result["covered_downside_protection_percent"], 9)
        self.assertEqual(result["covered_base_change_profit"], 60)
        self.assertEqual(result["covered_option_change_profit"], -18)
        self.assertEqual(result["covered_combined_change_profit"], 42)
        self.assertEqual(result["covered_foregone_upside"], 18)
        self.assertGreaterEqual(result["covered_assignment_probability"], 0)
        self.assertLessEqual(result["covered_assignment_probability"], 100)
        self.assertEqual(
            result["covered_assignment_probability_model"],
            "Black–Scholes N(d2), q=0",
        )

    def test_open_covered_call_deducts_only_commissions_for_each_scenario(self):
        trade = {
            **self.trade,
            "entry_base_price": 100,
            "entry_premium": 10,
            "strike": 120,
            "quantity": 2,
            "commission": 2,
            "option_exit_commission_estimate": 3,
            "exercise_commission_estimate": 5,
            "underlying_exit_commission_estimate": 7,
        }
        quote = {**self.quote, "base_last": 130, "option_last": 18, "strike": 120}
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))

        self.assertEqual(result["option_offset_total_commission"], 5)
        self.assertEqual(result["exercise_total_commission"], 7)
        self.assertEqual(result["offset_and_sell_total_commission"], 12)
        self.assertEqual(result["covered_option_only_profit"], -21)
        self.assertEqual(result["covered_liquidation_profit"], 32)
        self.assertEqual(result["covered_hold_profit"], 53)
        self.assertEqual(result["covered_max_profit"], 53)
        self.assertEqual(result["covered_breakeven"], 93.5)
        self.assertEqual(result["covered_downside_protection_percent"], 6.5)

    def test_closed_trade_uses_actual_exit_commission_without_estimate_double_count(self):
        trade = {
            **self.trade,
            "status": "closed",
            "exit_method": "offset",
            "exit_date": "2026-08-03",
            "exit_base_price": 130,
            "exit_option_price": 18,
            "entry_base_price": 100,
            "entry_premium": 10,
            "strike": 120,
            "quantity": 2,
            "commission": 2,
            "exit_commission": 11,
            "option_exit_commission_estimate": 300,
            "exercise_commission_estimate": 500,
            "underlying_exit_commission_estimate": 700,
        }
        result = calculate_trade_snapshot(trade, None, as_of=date(2026, 8, 8))

        self.assertEqual(result["realized_commission"], 13)
        self.assertEqual(result["offset_and_sell_total_commission"], 13)
        self.assertEqual(result["realized_profit"], 31)

    def test_open_long_call_deducts_route_specific_commissions(self):
        trade = {
            **self.trade,
            "strategy_type": "long_call",
            "entry_base_price": 1000,
            "entry_premium": 100,
            "strike": 900,
            "quantity": 2,
            "commission": 2,
            "option_exit_commission_estimate": 3,
            "exercise_commission_estimate": 5,
            "underlying_exit_commission_estimate": 7,
        }
        quote = {**self.quote, "base_last": 1100, "option_last": 130, "strike": 900}
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))

        self.assertEqual(result["long_offset_profit"], 55)
        self.assertEqual(result["exercise_and_sell_total_commission"], 14)
        self.assertEqual(result["long_exercise_profit"], 186)
        self.assertEqual(result["long_exercise_breakeven"], 1007)

    def test_covered_call_exercise_status_is_explicit(self):
        trade = {
            **self.trade,
            "status": "closed",
            "exit_date": "2026-08-03",
            "exit_base_price": 2500,
            "exit_option_price": 100,
            "exit_method": "exercise",
        }
        result = calculate_trade_snapshot(trade, None, as_of=date(2026, 8, 3))
        self.assertEqual(result["covered_position_status"], "exercised")

    def test_fulfillment_is_unavailable_when_expected_profit_is_zero(self):
        trade = {**self.trade, "entry_base_price": 2410, "entry_premium": 10}
        quote = {**self.quote, "strike": 2400}
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))
        self.assertEqual(result["expected_profit"], 0)
        self.assertIsNone(result["option_profit_fulfillment_percent"])
        self.assertIsNone(result["total_profit_fulfillment_percent"])

    def test_covered_hold_is_independent_of_selected_current_base_price(self):
        quote = {
            **self.quote,
            "base_last": 2500,
            "base_bid": 2450,
            "option_last": 10,
        }
        last_quote = select_trade_valuation_quote(
            quote, "covered_call", covered_base_basis="last"
        )
        bid_quote = select_trade_valuation_quote(
            quote, "covered_call", covered_base_basis="bid"
        )
        last_result = calculate_trade_snapshot(
            self.trade, last_quote, as_of=date(2026, 8, 3)
        )
        bid_result = calculate_trade_snapshot(
            self.trade, bid_quote, as_of=date(2026, 8, 3)
        )
        self.assertEqual(last_result["covered_exercise_profit_per_unit"], -10)
        self.assertEqual(last_result["covered_hold_profit"], 173)
        self.assertEqual(last_result["base_valuation_basis"], "آخرین معامله")
        self.assertEqual(bid_result["covered_exercise_profit_per_unit"], -10)
        self.assertEqual(bid_result["covered_hold_profit"], 173)
        self.assertEqual(bid_result["base_valuation_basis"], "بهترین پیشنهاد خرید")

    def test_covered_hold_uses_strike_minus_entry_plus_received_premium(self):
        trade = {
            **self.trade,
            "entry_base_price": 2_858_000,
            "entry_premium": 99_000,
            "quantity": 9,
            "strike": 3_000_000,
        }
        quote = {
            **self.quote,
            "base_last": 3_023_000,
            "option_last": 86_000,
            "strike": 3_000_000,
        }
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))
        self.assertEqual(result["covered_exercise_profit_per_unit"], 142_000)
        self.assertEqual(result["covered_hold_premium_per_unit"], 99_000)
        self.assertEqual(result["covered_hold_profit"], 2_169_000)
        self.assertEqual(result["covered_liquidation_profit"], 1_602_000)
        self.assertAlmostEqual(
            result["total_profit_fulfillment_percent"],
            1_602_000 / 2_169_000 * 100,
        )

    def test_zatas_7010_hold_profit_matches_user_example(self):
        trade = {
            **self.trade,
            "asset": "تاصیکو", "option_symbol": "ضتاص7010",
            "entry_base_price": 17_180, "entry_premium": 1_887,
            "quantity": 10_000, "strike": 18_000,
        }
        quote = {
            **self.quote,
            "base_last": 22_180, "option_last": 1_000,
            "strike": 18_000,
        }
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))
        self.assertEqual(result["covered_exercise_profit_per_unit"], 820)
        self.assertEqual(result["covered_hold_premium_per_unit"], 1_887)
        self.assertEqual(result["covered_hold_profit"], 27_070_000)

    def test_open_covered_call_profit_uses_last_trades_not_order_book(self):
        quote = {
            **self.quote,
            "base_price": 2500,
            "base_last": 2350,
            "option_exit_ask": 30,
            "option_last": 12,
        }
        result = calculate_trade_snapshot(self.trade, quote, as_of=date(2026, 8, 3))
        self.assertEqual(result["current_base_price"], 2350)
        self.assertEqual(result["current_option_exit_price"], 12)
        self.assertEqual(result["option_valuation_basis"], "آخرین معامله")
        self.assertEqual(result["option_profit"], 171)
        self.assertEqual(result["total_profit"], 111)

    def test_quote_map_uses_best_sell_price_for_option_exit(self):
        rows = [{
            "baseSymbol": "اهرم",
            "symbolOption": "ضهرم6045",
            "askPrice1Base": 2361.8,
            "lastTradeBase": 2355,
            "bestBidBase": 2348,
            "askPrice1Option": 10,
            "bidPrice1Option": 8,
            "dueDatePrice": 2400,
            "expiration_date": "2026-08-28T00:00:00.000Z",
            "days": 25,
        }]
        quote = build_quote_map([], rows)["tehran|ضهرم6045"]
        self.assertEqual(quote["option_exit_ask"], 10)
        self.assertEqual(quote["option_exit_bid"], 8)
        self.assertEqual(quote["base_last"], 2355)
        self.assertEqual(quote["base_bid"], 2348)

    def test_goods_gregorian_normalized_expiry_is_not_reparsed_as_jalali(self):
        rows = [{
            "baseSymbol": "طلای 24 عیار",
            "symbolOption": "GBAB05C2000",
            "askPrice1Base": 26_148_000,
            "lastTradeBase": 26_148_000,
            "askPrice1Option": 8_650_000,
            "bidPrice1Option": 8_300_000,
            "optionPrice": 8_650_000,
            "dueDatePrice": 20_000_000,
            "expiration_date": "2026-11-10",
            "days": 83,
        }]
        quote = build_quote_map(rows, [])["goods|GBAB05C2000"]
        self.assertEqual(quote["expiry"], "2026-11-10")
        self.assertEqual(quote["days"], 83)

    def test_trade_valuation_basis_can_be_selected_per_strategy(self):
        quote = {
            "base_last": 1000, "base_bid": 995, "base_ask": 1005,
            "option_last": 80, "option_exit_ask": 85, "option_exit_bid": 75,
        }
        covered = select_trade_valuation_quote(
            quote, "covered_call", covered_option_basis="ask", covered_base_basis="bid"
        )
        self.assertEqual(covered["option_last"], 85)
        self.assertEqual(covered["base_last"], 995)
        self.assertEqual(covered["valuation_option_label"], "بهترین پیشنهاد فروش")
        self.assertEqual(covered["valuation_base_label"], "بهترین پیشنهاد خرید")
        long_call = select_trade_valuation_quote(
            quote, "long_call", long_option_basis="bid", long_base_basis="bid"
        )
        self.assertEqual(long_call["option_last"], 75)
        self.assertEqual(long_call["base_last"], 995)
        self.assertEqual(long_call["valuation_option_label"], "بهترین پیشنهاد خرید")
        self.assertEqual(long_call["valuation_base_label"], "بهترین پیشنهاد خرید")
        long_ask = select_trade_valuation_quote(
            quote, "long_call", long_option_basis="ask", long_base_basis="ask"
        )
        self.assertEqual(long_ask["option_last"], 85)
        self.assertEqual(long_ask["base_last"], 1005)
        self.assertEqual(long_ask["valuation_option_label"], "بهترین پیشنهاد فروش")
        self.assertEqual(long_ask["valuation_base_label"], "بهترین پیشنهاد فروش")

    def test_previous_day_prices_are_tagged_and_used_when_live_prices_missing(self):
        rows = [{
            "baseSymbol": "اهرم", "symbolOption": "ضهرم6045",
            "askPrice1Base": 1000, "previousPriceBase": 990,
            "previousPriceOption": 75, "dueDatePrice": 900,
            "expiration_date": "2026-08-28", "days": 5,
        }]
        quote = build_quote_map([], rows)["tehran|ضهرم6045"]
        self.assertEqual(quote["base_last"], 990)
        self.assertEqual(quote["option_last"], 75)
        self.assertTrue(quote["base_last_is_previous_day"])
        self.assertTrue(quote["option_last_is_previous_day"])
        selected = select_trade_valuation_quote(
            quote, "covered_call", covered_option_basis="ask",
            covered_base_basis="bid",
        )
        self.assertEqual(selected["base_last"], 990)
        self.assertEqual(selected["option_last"], 75)
        self.assertTrue(selected["selected_base_is_previous_day"])
        self.assertTrue(selected["selected_option_is_previous_day"])

    def test_closed_underlying_suppresses_open_trade_profit(self):
        quote = {
            "asset": "فزر", "strike": 190_000,
            "expiry": (tehran_today() + timedelta(days=6)).isoformat(),
            "base_last": 292_100, "base_last_raw": 292_100,
            "option_last": 113_999, "option_last_raw": 113_999,
            "base_bid": 292_100, "option_exit_ask": 113_999,
            "base_is_closed": True,
            "base_market_status": "ممنوع-متوقف",
        }
        trade = {
            "status": "open", "strategy_type": "covered_call",
            "market": "tehran", "asset": "فزر", "option_symbol": "ضفزر621",
            "entry_date": (tehran_today() - timedelta(days=27)).isoformat(),
            "entry_base_price": 195_600, "entry_premium": 21_001,
            "quantity": 4_000, "commission": 0,
            "strike": 190_000, "expiry": quote["expiry"],
        }
        snapshot = calculate_trade_snapshot(trade, quote, as_of=tehran_today())
        self.assertTrue(snapshot["base_is_closed"])
        self.assertEqual(snapshot["base_market_status"], "ممنوع-متوقف")
        self.assertEqual(snapshot["data_status"], "base_closed")
        for key in (
            "expected_profit", "covered_hold_profit", "covered_liquidation_profit",
            "covered_option_only_profit", "all_offset_and_sell_profit",
            "covered_best_profit", "total_profit", "option_profit", "base_profit",
        ):
            self.assertIsNone(snapshot.get(key), key)

    def test_underlying_quote_prefers_today_trade_and_matches_asset_aliases(self):
        quotes = {
            "goods|old": {
                "market": "goods", "asset": "طلای 24 عیار",
                "base_last": 100, "base_bid": 99, "base_ask": 101,
                "base_last_is_previous_day": True,
            },
            "goods|live": {
                "market": "goods", "asset": "طلای 24 عیار",
                "base_last": 110, "base_bid": 109, "base_ask": 111,
                "base_last_is_previous_day": False,
            },
        }
        mapped = build_underlying_quote_map(quotes)
        key = underlying_quote_key("goods", "شمش طلا")
        self.assertEqual(mapped[key]["last"], 110)
        self.assertFalse(mapped[key]["last_is_previous_day"])
        self.assertEqual(
            underlying_quote_key("tehran", "هم تراز"),
            underlying_quote_key("tehran", "هم‌تراز"),
        )
        self.assertEqual(
            underlying_quote_key("tehran", "طلای 24 عیار"),
            underlying_quote_key("goods", "شمش طلا"),
        )

    def test_commodity_underlying_repairs_wrong_market_and_updates_profit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "طلای 24 عیار",
                "acquisition_method": "direct",
                "entry_date": (tehran_today() - timedelta(days=2)).isoformat(),
                "entry_price": 28_000_000, "quantity": 2, "commission": 0,
            })
            self.assertEqual(position["market"], "goods")
            snapshot = calculate_underlying_snapshot(
                {**position, "market": "tehran"},
                {"market": "goods", "last": 29_000_000, "bid": 28_990_000, "ask": 29_010_000},
                as_of=tehran_today(),
            )
            self.assertEqual(snapshot["market"], "goods")
            self.assertEqual(snapshot["current_price"], 29_000_000)
            self.assertEqual(snapshot["profit"], 2_000_000)

    def test_liquidating_all_covered_legs_uses_option_ask_and_base_bid(self):
        quote = {
            **self.quote, "base_bid": 2350, "base_ask": 2370,
            "option_exit_ask": 15, "option_exit_bid": 9, "option_last": 12,
        }
        result = calculate_trade_snapshot(self.trade, quote, as_of=date(2026, 8, 3))
        expected = (183 - 15) + (2350 - 2410)
        self.assertEqual(result["all_offset_and_sell_profit"], expected)
        self.assertAlmostEqual(
            result["all_offset_and_sell_percent"], expected / 2227 * 100
        )
        summary = summarize_open_trades([result])
        self.assertEqual(
            summary["covered_call"]["all_offset_and_sell_profit"], expected
        )

    def test_quote_key_normalizes_arabic_yeh_from_tsetmc(self):
        rows = [{
            "baseSymbol": "فملي",
            "symbolOption": "ضملي7068",
            "askPrice1Base": 17_710,
            "askPrice1Option": 4_880,
            "bidPrice1Option": 4_712,
            "optionPrice": 4_715,
            "dueDatePrice": 15_714,
            "expiration_date": "2026-09-30",
            "days": 51,
        }]
        quotes = build_quote_map([], rows)

        quote = quotes[quote_key("tehran", "ضملی7068")]
        self.assertEqual(quote["symbol"], "ضملی7068")
        self.assertEqual(quote["base_price"], 17_710)
        self.assertEqual(quote["option_exit_ask"], 4_880)
        self.assertEqual(quote["option_last"], 4_715)

    def test_quote_map_exposes_latest_option_trade(self):
        rows = [{
            "baseSymbol": "اهرم",
            "symbolOption": "ضهرم6045",
            "askPrice1Base": 2361.8,
            "askPrice1Option": 240,
            "bidPrice1Option": 230,
            "optionPrice": 225,
            "dueDatePrice": 2400,
            "expiration_date": "2026-08-28T00:00:00.000Z",
            "days": 25,
        }]
        quote = build_quote_map([], rows)["tehran|ضهرم6045"]
        self.assertEqual(quote["option_last"], 225)

    def test_long_call_reports_premium_growth_and_exercise_formula(self):
        trade = {
            **self.trade,
            "strategy_type": "long_call",
            "annual_interest_rate": 40,
        }
        quote = {
            **self.quote,
            "option_exit_bid": 230,
            "option_last": 225,
        }
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))
        period_rate = 0.40 * 30 / 365
        self.assertAlmostEqual(result["period_interest_rate"], period_rate)
        self.assertAlmostEqual(result["premium_profit"], 42)
        self.assertAlmostEqual(result["premium_growth_percent"], 42 / 183 * 100)
        self.assertAlmostEqual(
            result["exercise_profit_percent"],
            (((period_rate - 1) * 2400) + 183) / 2410 * 100,
        )
        self.assertEqual(result["exercise_plus_premium"], 2583)
        interest_cost = 2400 * period_rate
        adjusted_total = 2583 - interest_cost
        self.assertAlmostEqual(result["exercise_interest_cost"], interest_cost)
        self.assertAlmostEqual(
            result["interest_adjusted_exercise_plus_premium"], adjusted_total
        )
        self.assertAlmostEqual(
            result["exercise_premium_vs_base_percent"],
            (adjusted_total - 2410) / 2410 * 100,
        )
        self.assertAlmostEqual(
            result["base_price_change_percent"],
            (2361.8 - 2410) / 2410 * 100,
        )
        self.assertAlmostEqual(
            result["premium_price_change_percent"],
            (225 - 183) / 183 * 100,
        )
        self.assertEqual(result["current_option_exit_price"], 225)
        self.assertEqual(result["option_valuation_basis"], "آخرین معامله")
        self.assertEqual(result["long_offset_profit"], 42)
        self.assertAlmostEqual(result["long_offset_profit_percent"], 42 / 183 * 100)
        self.assertEqual(result["long_exercise_breakeven"], 2583)
        self.assertEqual(result["long_exercise_required_cash"], 2400)
        self.assertEqual(result["exercise_allocation_required_cash"], 0)
        self.assertEqual(result["long_exercise_profit"], 2361.8 - 2583)
        self.assertAlmostEqual(
            result["long_exercise_profit_percent"],
            (2361.8 - 2583) / 2583 * 100,
        )

    def test_long_call_allocation_reconciles_both_profit_objectives(self):
        trade = {
            **self.trade,
            "strategy_type": "long_call",
            "entry_base_price": 1000,
            "entry_premium": 100,
            "strike": 900,
            "quantity": 5,
            "exercise_quantity": 2,
            "premium_trade_quantity": 3,
            "commission": 50,
        }
        quote = {
            **self.quote,
            "base_last": 1100,
            "option_last": 130,
            "strike": 900,
        }
        result = calculate_trade_snapshot(trade, quote, as_of=date(2026, 8, 3))
        self.assertEqual(result["quantity"], 5)
        self.assertEqual(result["premium_profit"], 60)
        self.assertEqual(result["exercise_allocation_profit"], 180)
        self.assertEqual(result["long_exercise_required_cash"], 4500)
        self.assertEqual(result["exercise_allocation_required_cash"], 1800)
        self.assertEqual(result["long_combined_profit"], 240)
        self.assertAlmostEqual(result["long_combined_profit_percent"], 240 / 550 * 100)

    def test_closed_long_call_reports_realized_and_annualized_return(self):
        trade = {
            **self.trade,
            "status": "closed",
            "strategy_type": "long_call",
            "annual_interest_rate": 40,
            "commission": 2,
            "exit_commission": 3,
            "exit_date": "2026-08-03",
            "exit_base_price": 2361.8,
            "exit_option_price": 230,
        }
        result = calculate_trade_snapshot(trade, None, as_of=date(2026, 8, 8))
        invested_capital = 183 + 2
        realized_profit = 230 - 183 - 2 - 3
        self.assertEqual(result["realized_profit"], realized_profit)
        self.assertAlmostEqual(
            result["realized_profit_percent"],
            realized_profit / invested_capital * 100,
        )
        self.assertAlmostEqual(
            result["realized_profit_yoy"],
            realized_profit / invested_capital * 100 * 365 / 5,
        )

    def test_open_trade_summary_reconciles_strategy_and_total_metrics(self):
        trades = [
            {
                "status": "open",
                "strategy_type": "covered_call",
                "asset": "فولاد",
                "invested_capital": 1000,
                "expected_profit": 120,
                "option_profit": 150,
                "total_profit": 90,
                "entry_days": 30,
                "invested_days": 10,
            },
            {
                "status": "open",
                "strategy_type": "covered_call",
                "asset": "فولاد",
                "invested_capital": 2000,
                "expected_profit": 200,
                "option_profit": None,
                "total_profit": None,
                "entry_days": 60,
                "invested_days": 20,
            },
            {
                "status": "open",
                "strategy_type": "long_call",
                "asset": "خودرو",
                "invested_capital": 500,
                "premium_profit": -25,
                "invested_days": 10,
                "long_exercise_required_cash": 9000,
                "exercise_allocation_required_cash": 3600,
            },
            {
                "status": "open",
                "strategy_type": "long_call",
                "asset": "خودرو",
                "invested_capital": 700,
                "premium_profit": None,
                "invested_days": 20,
                "long_exercise_required_cash": 6000,
                "exercise_allocation_required_cash": 0,
            },
            {
                "status": "closed",
                "strategy_type": "covered_call",
                "invested_capital": 9999,
                "expected_profit": 9999,
            },
        ]

        summary = summarize_open_trades(trades)

        self.assertEqual(summary["covered_call"]["invested_capital"], 3000)
        self.assertEqual(summary["covered_call"]["expected_profit"], 320)
        self.assertEqual(summary["covered_call"]["best_decision_profit"], 350)
        self.assertEqual(summary["covered_call"]["valued_count"], 2)
        self.assertEqual(summary["covered_call"]["fluctuation_profit"], 90)
        self.assertEqual(summary["covered_call"]["fluctuation_valued_count"], 1)
        self.assertEqual(summary["long_call"]["invested_capital"], 1200)
        self.assertEqual(summary["long_call"]["premium_profit"], -25)
        self.assertEqual(summary["long_call"]["exercise_required_cash"], 15000)
        self.assertEqual(
            summary["long_call"]["exercise_allocation_required_cash"], 3600
        )
        self.assertAlmostEqual(
            summary["covered_call"]["hold_yoy"],
            320 / 3000 * 100 * 365 / ((1000 * 30 + 2000 * 60) / 3000),
        )
        self.assertAlmostEqual(
            summary["long_call"]["combined_yoy"],
            -25 / 500 * 100 * 365 / 10,
        )
        self.assertEqual(summary["long_call"]["valued_count"], 1)
        self.assertEqual(summary["long_call"]["fluctuation_profit"], -25)
        self.assertEqual(summary["long_call"]["fluctuation_valued_count"], 1)
        self.assertEqual(summary["total"]["invested_capital"], 4200)
        self.assertEqual(summary["total"]["selected_profit"], 65)
        self.assertAlmostEqual(
            summary["total"]["selected_profit_percent"], 65 / 4200 * 100
        )
        self.assertEqual(summary["total"]["valued_count"], 2)
        assets = {item["asset"]: item for item in summary["by_asset"]}
        self.assertEqual(assets["فولاد"]["invested_capital"], 3000)
        self.assertEqual(assets["فولاد"]["selected_profit"], 90)
        self.assertEqual(assets["خودرو"]["invested_capital"], 1200)
        self.assertEqual(assets["خودرو"]["selected_profit"], -25)
        self.assertAlmostEqual(assets["فولاد"]["liquidity_share_percent"], 3000 / 4200 * 100)
        self.assertAlmostEqual(assets["خودرو"]["liquidity_share_percent"], 1200 / 4200 * 100)

    def test_open_summary_reports_free_underlying_separately_from_strategies(self):
        today = tehran_today()
        position = {
            "id": "base-1", "status": "open", "market": "tehran",
            "asset": "فولاد", "entry_date": (today - timedelta(days=10)).isoformat(),
            "entry_price": 1_000, "quantity": 1_000, "commission": 0,
        }
        underlying = calculate_underlying_snapshot(
            position, {"last": 1_100}, as_of=today, allocated_quantity=600,
        )
        covered = {
            "id": "covered-1", "status": "open", "strategy_type": "covered_call",
            "asset": "فولاد", "invested_capital": 600_000,
            "expected_profit": 60_000, "entry_days": 30, "invested_days": 10,
        }

        summary = summarize_open_trades([covered], [underlying])

        self.assertEqual(underlying["available_quantity"], 400)
        self.assertEqual(summary["underlying"]["invested_capital"], 400_000)
        self.assertEqual(summary["underlying"]["profit"], 40_000)
        self.assertEqual(summary["total"]["invested_capital"], 600_000)
        self.assertEqual(summary["total"]["selected_profit"], 0)
        self.assertEqual(summary["total"]["valued_count"], 0)
        self.assertEqual(summary["by_asset"][0]["underlying_count"], 0)

    def test_account_growth_combines_realized_and_open_mark_to_market(self):
        trades = [
            {
                "status": "closed", "strategy_type": "covered_call",
                "entry_date": "2026-07-20", "exit_date": "2026-08-08",
                "invested_capital": 1_000, "realized_profit": 120,
            },
            {
                "status": "open", "strategy_type": "covered_call",
                "entry_date": "2026-08-01", "invested_capital": 2_000,
                "total_profit": 80,
            },
            {
                "status": "open", "strategy_type": "long_call",
                "entry_date": "2026-08-02", "invested_capital": 500,
                "premium_profit": -20,
            },
        ]

        growth = build_account_growth(trades, as_of=date(2026, 8, 11))

        self.assertEqual(growth["realized_profit"], 120)
        self.assertEqual(growth["open_mark_profit"], 60)
        self.assertEqual(growth["total_profit"], 180)
        self.assertEqual(growth["invested_capital"], 3_500)
        self.assertAlmostEqual(growth["return_percent"], 180 / 3_500 * 100)
        self.assertEqual(growth["points"][-1]["date"], "2026-08-11")
        self.assertEqual(growth["points"][-1]["value"], 180)
        self.assertEqual(growth["initial_capital"], 3_500)
        self.assertEqual(growth["initial_capital_source"], "estimated")
        self.assertEqual(growth["current_equity"], 3_680)
        self.assertEqual(growth["points"][-1]["equity"], 3_680)
        self.assertAlmostEqual(growth["average_holding_days"], (19 + 10 + 9) / 3)
        self.assertEqual(growth["max_drawdown_percent"], 0)
        self.assertEqual(growth["drawdown_method"], "observed_event_points")
        self.assertEqual(growth["drawdown_scope_label"], "افت سرمایه در نقاط ثبت‑شده")
        self.assertFalse(growth["drawdown_is_daily"])
        self.assertEqual(growth["drawdown_observation_count"], len(growth["points"]))
        self.assertIn("روزانه", growth["drawdown_limitation"])
        self.assertIsNotNone(growth["average_monthly_return_percent"])
        self.assertIsNotNone(growth["average_annual_return_percent"])
        self.assertTrue(growth["points"][-1]["is_current"])

    def test_account_growth_uses_explicit_capital_and_reports_mdd(self):
        trades = [
            {
                "status": "closed", "strategy_type": "covered_call",
                "entry_date": "2026-07-01", "exit_date": "2026-07-10",
                "invested_capital": 600, "realized_profit": 200,
            },
            {
                "status": "closed", "strategy_type": "long_call",
                "entry_date": "2026-07-02", "exit_date": "2026-07-20",
                "invested_capital": 300, "realized_profit": -300,
            },
        ]
        growth = build_account_growth(
            trades, as_of=date(2026, 7, 20), initial_capital=1_000
        )
        self.assertEqual(growth["initial_capital"], 1_000)
        self.assertEqual(growth["initial_capital_source"], "user")
        self.assertEqual(growth["current_equity"], 900)
        self.assertAlmostEqual(growth["max_drawdown_percent"], 25)
        self.assertEqual(growth["max_drawdown_amount"], 300)
        self.assertEqual(growth["max_drawdown_peak_date"], "2026-07-10")
        self.assertEqual(growth["max_drawdown_trough_date"], "2026-07-20")
        self.assertEqual(growth["drawdown_method"], "observed_event_points")
        self.assertFalse(growth["drawdown_is_daily"])
        self.assertEqual(growth["drawdown_observation_count"], len(growth["points"]))
        self.assertEqual(growth["average_holding_days_covered_call"], 9)
        self.assertEqual(growth["average_holding_days_long_call"], 18)

    def test_covered_profit_recognition_uses_actual_closed_and_two_open_bases(self):
        trades = [
            {
                "id": "open", "status": "open", "strategy_type": "covered_call",
                "market": "tehran", "asset": "اهرم", "option_symbol": "ضهرم",
                "entry_date": "2026-08-01", "expiry": "2026-09-18",
                "expiry_display": "1405/06/27", "remaining_days": 30,
                "total_profit": 100, "expected_profit": 150,
            },
            {
                "id": "closed", "status": "closed", "strategy_type": "covered_call",
                "market": "tehran", "asset": "خودرو", "option_symbol": "ضخود",
                "entry_date": "2026-07-01", "exit_date": "2026-07-11",
                "expiry": "2026-08-01", "expiry_display": "1405/05/10",
                "realized_profit": 50,
            },
            {
                "id": "long", "status": "closed", "strategy_type": "long_call",
                "entry_date": "2026-07-01", "realized_profit": 999,
            },
        ]

        result = build_covered_profit_recognition(
            trades, as_of=date(2026, 8, 19), initial_capital=1_000
        )

        self.assertEqual(result["trade_count"], 3)
        self.assertEqual(result["covered_trade_count"], 2)
        self.assertEqual(result["long_trade_count"], 1)
        self.assertEqual(result["closed_realized_profit"], 50)
        self.assertEqual(result["current_profit"], 150)
        self.assertEqual(result["final_profit"], 200)
        self.assertEqual(result["remaining_days_to_last"], 30)
        self.assertEqual(result["elapsed_days"], 49)
        self.assertEqual(result["horizon_days"], 79)
        self.assertAlmostEqual(result["current_scaled"]["return_percent"], 15)
        self.assertAlmostEqual(result["current_scaled"]["monthly_return_percent"], 15 * 30 / 49)
        self.assertAlmostEqual(result["final_scaled"]["annual_return_percent"], 20 * 365 / 79)
        self.assertEqual(result["details"][0]["current_basis"], "آفست اختیار و فروش پایه")

    def test_profit_recognition_separates_premium_and_underlying_modes(self):
        trades = [
            {
                "id": "cc", "status": "open", "strategy_type": "covered_call",
                "market": "tehran", "asset": "الف", "option_symbol": "ضالف",
                "entry_date": "2026-08-01", "expiry": "2026-09-18",
                "option_profit": 80, "total_profit": 50, "expected_profit": 120,
                "entry_base_price": 1000, "current_base_price": 970,
                "base_profit": -30, "quantity": 1,
            },
            {
                "id": "lc", "status": "open", "strategy_type": "long_call",
                "market": "tehran", "asset": "ب", "option_symbol": "ضب",
                "entry_date": "2026-08-02", "expiry": "2026-09-20",
                "premium_profit": 40, "exercise_today_profit": -10,
                "exercise_today_cost_gap": 10,
            },
            {
                "id": "ex", "status": "closed", "strategy_type": "long_call",
                "market": "tehran", "asset": "ج", "option_symbol": "ضج",
                "entry_date": "2026-07-01", "exit_date": "2026-08-10",
                "expiry": "2026-08-10", "exit_method": "exercise",
                "realized_profit": 25, "post_exercise_base_profit": 15,
                "strike": 900, "exit_base_price": 950,
                "tracked_base_price": 965, "quantity": 1,
            },
        ]
        result = build_covered_profit_recognition(
            trades, as_of=date(2026, 8, 19), initial_capital=1_000
        )
        self.assertEqual(result["combined"]["option_only_profit"], 145)
        self.assertEqual(result["combined"]["with_underlying_profit"], 80)
        self.assertEqual(result["long_call"]["open_premium_profit"], 40)
        self.assertEqual(result["long_call"]["open_exercise_profit"], -10)
        self.assertEqual(len(result["underlying_positions"]), 2)


class TradeStoreTests(unittest.TestCase):
    def test_expired_contract_can_be_created_from_explicit_manual_metadata(self):
        expiry = tehran_today() - timedelta(days=1)
        payload = {
            "market": "tehran", "strategy_type": "long_call",
            "asset": "اهرم", "manual_option_symbol": "ضهرم-قدیمی",
            "contract_entry_mode": "manual_expired",
            "manual_strike": 12_500, "manual_expiry": expiry.isoformat(),
            "manual_contract_size": 1000,
            "entry_date": (expiry - timedelta(days=20)).isoformat(),
            "entry_base_price": 13_000, "entry_premium": 350,
            "exercise_quantity": 1, "premium_trade_quantity": 0,
            "commission": 12,
        }
        quote = resolve_trade_quote(payload, None)

        with tempfile.TemporaryDirectory() as directory:
            created = TradeStore(Path(directory) / "trades.json").create(payload, quote)

        self.assertEqual(created["option_symbol"], "ضهرم-قدیمی")
        self.assertEqual(created["strike"], 12_500)
        self.assertEqual(created["expiry"], expiry.isoformat())
        self.assertEqual(created["contract_size"], 1000)
        self.assertEqual(created["contract_entry_mode"], "manual_expired")

    def test_manual_contract_rejects_a_future_expiry(self):
        payload = {
            "market": "tehran", "asset": "اهرم",
            "manual_option_symbol": "ضهرم-آتی",
            "contract_entry_mode": "manual_expired",
            "manual_strike": 12_500,
            "manual_expiry": (tehran_today() + timedelta(days=1)).isoformat(),
            "manual_contract_size": 1000,
        }

        with self.assertRaisesRegex(ValueError, "گذشته یا امروز"):
            resolve_trade_quote(payload, None)

        payload["manual_expiry"] = "تاریخ نامعتبر"
        with self.assertRaisesRegex(ValueError, "تاریخ سررسید.*معتبر نیست"):
            resolve_trade_quote(payload, None)

    def test_entry_date_can_be_created_and_edited_one_day_after_tehran_today(self):
        quote = {
            "asset": "وبملت", "strike": 1454,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_price": 1424, "option_last": 121.93,
        }
        payload = {
            "market": "tehran", "strategy_type": "covered_call",
            "asset": "وبملت", "option_symbol": "ضملت7044",
            "entry_date": tehran_today().isoformat(),
            "entry_base_price": 1424, "entry_premium": 121.93,
            "quantity": 1, "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            future_entry = tehran_today() + timedelta(days=1)
            updated = store.update(
                created["id"],
                {**payload, "entry_date": future_entry.isoformat()},
                quote,
            )
            self.assertEqual(updated["entry_date"], future_entry.isoformat())
            self.assertEqual(
                updated["entry_days_to_expiry"],
                (date.fromisoformat(quote["expiry"]) - future_entry).days,
            )

    def test_entry_date_more_than_one_day_after_tehran_today_is_rejected(self):
        quote = {
            "asset": "وبملت", "strike": 1454,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_price": 1424,
        }
        payload = {
            "market": "tehran", "strategy_type": "covered_call",
            "asset": "وبملت", "option_symbol": "ضملت7044",
            "entry_date": (tehran_today() + timedelta(days=2)).isoformat(),
            "entry_base_price": 1424, "entry_premium": 121.93,
            "quantity": 1, "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            with self.assertRaisesRegex(ValueError, "یک روز بعد"):
                store.create(payload, quote)

    def test_account_store_persists_and_can_return_to_auto_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.json")
            self.assertIsNone(store.read()["initial_capital"])
            store.save(1_250_000, 250_000)
            self.assertEqual(store.read()["initial_capital"], 1_250_000)
            self.assertEqual(store.read()["cash_balance"], 250_000)
            store.save(None)
            self.assertIsNone(store.read()["initial_capital"])

    def test_v8_trade_rejects_toman_instead_of_silent_tenfold_error(self):
        quote = {
            "asset": "اهرم",
            "strike": 2400,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": 2500,
            "option_last": 180,
            "contract_size": 1000,
        }
        payload = {
            "market": "tehran",
            "strategy_type": "long_call",
            "asset": "اهرم",
            "option_symbol": "ضهرم6045",
            "entry_date": tehran_today().isoformat(),
            "entry_base_price": 2500,
            "entry_premium": 180,
            "quantity": 1,
            "commission": 0,
            "quantity_kind": "contract",
            "currency_unit": "toman",
            "calculation_version": 8,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            with self.assertRaisesRegex(ValueError, "canonical"):
                store.create(payload, quote)

            legacy = store.create(
                {
                    **payload,
                    "quantity_kind": "unit",
                    "calculation_version": 7,
                },
                quote,
            )
            self.assertEqual(legacy["currency_unit"], "toman")

    def test_v8_trade_preserves_exact_money_inputs_and_calculated_capital(self):
        quote = {
            "asset": "اهرم",
            "strike": "2400.000001",
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": "2500.000001",
            "option_last": "0.223456789123456789",
            "contract_size": 1000,
        }
        payload = {
            "market": "tehran",
            "strategy_type": "long_call",
            "asset": "اهرم",
            "option_symbol": "ضهرم6045",
            "entry_date": tehran_today().isoformat(),
            "entry_base_price": "2500.000001",
            "entry_premium": "0.123456789123456789",
            "quantity": 3,
            "commission": "0.000001",
            "quantity_kind": "contract",
            "currency_unit": "rial",
            "calculation_version": 8,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            self.assertEqual(
                created["money_values"]["entry_premium"],
                "0.123456789123456789",
            )
            self.assertEqual(
                created["risk_free_rate_version"],
                "ir-risk-free-legacy-v1",
            )
            self.assertEqual(
                created["commission_schedule_version"],
                "ir-fees-legacy-v1",
            )
            self.assertEqual(
                created["commission_rounding_mode"],
                "ROUND_HALF_EVEN",
            )
            self.assertEqual(
                created["commission_rounding_increment"],
                "1",
            )
            self.assertEqual(
                created["commission_rounding_version"],
                "nearest-rial-half-even-legacy-v1",
            )
            snapshot = calculate_trade_snapshot(
                created,
                quote,
                as_of=tehran_today(),
            )
            self.assertEqual(
                snapshot["money_values"]["invested_capital"],
                "370.370368370370367",
            )

    def test_v8_long_call_secondary_money_values_avoid_float_round_trip(self):
        quote = {
            "asset": "اهرم",
            "strike": "1",
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": "2",
            "option_last": "0.3",
            "contract_size": 1,
        }
        payload = {
            "market": "tehran",
            "strategy_type": "long_call",
            "asset": "اهرم",
            "option_symbol": "ضهرم-decimal",
            "entry_date": tehran_today().isoformat(),
            "entry_base_price": "1.5",
            "entry_premium": "0.1",
            "quantity": 3,
            "commission": "0.2",
            "option_exit_commission_estimate": "0",
            "exercise_commission_estimate": "0",
            "underlying_exit_commission_estimate": "0",
            "quantity_kind": "contract",
            "currency_unit": "rial",
            "calculation_version": 8,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            snapshot = calculate_trade_snapshot(
                store.create(payload, quote), quote, as_of=tehran_today()
            )

        self.assertEqual(snapshot["money_values"]["invested_capital"], "0.5")
        self.assertEqual(snapshot["money_values"]["premium_profit"], "0.4")
        self.assertEqual(snapshot["money_values"]["long_offset_profit"], "0.4")

    def test_v8_covered_call_secondary_money_values_are_decimal_native(self):
        quote = {
            "asset": "اهرم",
            "strike": "1.5",
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": "1.4",
            "option_last": "0.05",
            "contract_size": 1,
        }
        payload = {
            "market": "tehran",
            "strategy_type": "covered_call",
            "asset": "اهرم",
            "option_symbol": "ضهرم-covered-decimal",
            "entry_date": tehran_today().isoformat(),
            "entry_base_price": "1.2",
            "entry_premium": "0.1",
            "quantity": 3,
            "commission": "0",
            "option_exit_commission_estimate": "0",
            "exercise_commission_estimate": "0",
            "underlying_exit_commission_estimate": "0",
            "quantity_kind": "contract",
            "currency_unit": "rial",
            "calculation_version": 8,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            snapshot = calculate_trade_snapshot(
                store.create(payload, quote), quote, as_of=tehran_today()
            )

        money = snapshot["money_values"]
        self.assertEqual(money["invested_capital"], "3.3")
        self.assertEqual(money["expected_profit"], "1.2")
        self.assertEqual(money["covered_option_change_profit"], "0.15")
        self.assertEqual(money["covered_combined_change_profit"], "0.75")

    def test_v8_underlying_preserves_exact_money_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(
                Path(directory) / "underlying_positions.json"
            )
            created = store.create({
                "market": "tehran",
                "asset": "فولاد",
                "acquisition_method": "direct",
                "entry_date": tehran_today().isoformat(),
                "entry_price": "123.123456789123456789",
                "quantity": 2,
                "commission": "0.000001",
                "quantity_kind": "unit",
                "currency_unit": "rial",
                "calculation_version": 8,
            })
            self.assertEqual(
                created["money_values"]["entry_price"],
                "123.123456789123456789",
            )
            self.assertEqual(
                created["commission_rounding_version"],
                "nearest-rial-half-even-legacy-v1",
            )
            snapshot = calculate_underlying_snapshot(
                created,
                {"last": "124.123456789123456789"},
                as_of=tehran_today(),
            )
            self.assertEqual(
                snapshot["money_values"]["invested_capital"],
                "246.246914578246913578",
            )

    def test_v8_underlying_profit_is_recomputed_from_decimal_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(
                Path(directory) / "underlying_positions.json"
            )
            position = store.create({
                "market": "tehran",
                "asset": "فولاد",
                "acquisition_method": "direct",
                "entry_date": tehran_today().isoformat(),
                "entry_price": "0.1",
                "quantity": 3,
                "commission": "0.2",
                "quantity_kind": "unit",
                "currency_unit": "rial",
                "calculation_version": 8,
            })
            snapshot = calculate_underlying_snapshot(
                position, {"last": "0.3"}, as_of=tehran_today()
            )

        self.assertEqual(snapshot["money_values"]["invested_capital"], "0.5")
        self.assertEqual(snapshot["money_values"]["profit"], "0.4")

    def test_trade_is_persisted_and_deleted(self):
        quote = {
            "asset": "اهرم",
            "strike": 2400,
            "expiry": "2026-08-28",
            "base_price": 2361.8,
            "option_exit_ask": 10,
        }
        payload = {
            "market": "tehran",
            "asset": "اهرم",
            "option_symbol": "ضهرم6045",
            "entry_date": "1405/05/07",
            "entry_base_price": 2410,
            "entry_premium": 183,
            "quantity": 1,
            "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            self.assertEqual(store.list()[0]["id"], created["id"])
            self.assertAlmostEqual(created["entry_itm_percent"], (2410 - 2400) / 2410 * 100, places=2)
            self.assertIn(created["entry_moneyness"], {"ITM", "ATM", "OTM"})
            self.assertIsNotNone(created["entry_option_delta"])
            self.assertIsNotNone(created["entry_strategy_delta"])
            store.delete(created["id"])
            self.assertEqual(store.list(), [])

    def test_long_call_is_closed_at_last_trades(self):
        quote = {
            "asset": "اهرم",
            "strike": 2400,
            "expiry": "2026-08-28",
            "base_price": 2361.8,
            "base_last": 2350,
            "option_exit_ask": 240,
            "option_exit_bid": 230,
            "option_last": 225,
        }
        payload = {
            "strategy_type": "long_call",
            "market": "tehran",
            "asset": "اهرم",
            "option_symbol": "ضهرم6045",
            "entry_date": "1405/05/07",
            "entry_base_price": 2410,
            "entry_premium": 183,
            "annual_interest_rate": 40,
            "quantity": 1,
            "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                price_confirmed=True,
            )
            self.assertEqual(closed["exit_option_price"], 225)
            self.assertEqual(closed["exit_base_price"], 2350)
            self.assertEqual(closed["exit_price_basis"], "last_trade")
            self.assertTrue(closed["exit_price_confirmed"])

    def test_long_call_allocations_are_saved_and_editable_while_open(self):
        quote = {
            "asset": "اهرم", "strike": 2400, "expiry": "2026-08-28",
            "base_price": 2500, "base_last": 2490, "option_last": 210,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 2410, "entry_premium": 183,
            "exercise_quantity": 2, "premium_trade_quantity": 3,
            "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            self.assertEqual(created["quantity"], 5)
            self.assertEqual(created["exercise_quantity"], 2)
            self.assertEqual(created["premium_trade_quantity"], 3)
            updated = store.update(
                created["id"],
                {**payload, "exercise_quantity": 4, "premium_trade_quantity": 1},
                quote,
            )
            self.assertEqual(updated["quantity"], 5)
            self.assertEqual(updated["exercise_quantity"], 4)
            self.assertEqual(updated["premium_trade_quantity"], 1)

    def test_mixed_long_call_exit_uses_each_allocated_quantity(self):
        quote = {
            "asset": "اهرم", "strike": 900, "expiry": "2026-08-28",
            "base_price": 1100, "base_last": 1100, "option_last": 130,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 1000, "entry_premium": 100,
            "exercise_quantity": 2, "premium_trade_quantity": 3,
            "commission": 50,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                exit_method="mixed", price_confirmed=True,
            )
            snapshot = calculate_trade_snapshot(closed, quote, as_of=date(2026, 8, 3))
            self.assertEqual(snapshot["exit_method"], "mixed")
            # Legacy closed rows without an exit fee receive the same automatic
            # fee estimate as the close form, so reports remain net of costs.
            self.assertEqual(snapshot["realized_profit"], 232)
            self.assertTrue(snapshot["exit_commission_auto_calculated"])

    def test_partial_covered_close_creates_closed_slice_and_keeps_remainder_open(self):
        quote = {
            "asset": "اهرم", "strike": 2400, "expiry": "2026-08-28",
            "base_price": 2500, "base_last": 2490, "option_last": 120,
        }
        payload = {
            "strategy_type": "covered_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 2410, "entry_premium": 183,
            "quantity": 10, "commission": 100,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                close_quantity=4, price_confirmed=True,
            )
            records = store.list()
            remaining = next(item for item in records if item["status"] == "open")
            self.assertEqual(len(records), 2)
            self.assertEqual(remaining["quantity"], 6)
            self.assertEqual(remaining["commission"], 60)
            self.assertEqual(closed["quantity"], 4)
            self.assertEqual(closed["commission"], 40)
            self.assertTrue(closed["partial_close"])
            self.assertEqual(closed["parent_trade_id"], created["id"])

    def test_partial_long_close_reconciles_both_allocation_remainders(self):
        quote = {
            "asset": "اهرم", "strike": 900, "expiry": "2026-08-28",
            "base_price": 1100, "base_last": 1100, "option_last": 130,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 1000, "entry_premium": 100,
            "exercise_quantity": 4, "premium_trade_quantity": 6,
            "commission": 100,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                close_exercise_quantity=1, close_premium_trade_quantity=2,
                exit_method="mixed", price_confirmed=True,
            )
            remaining = next(item for item in store.list() if item["status"] == "open")
            self.assertEqual(closed["quantity"], 3)
            self.assertEqual(closed["exercise_quantity"], 1)
            self.assertEqual(closed["premium_trade_quantity"], 2)
            self.assertEqual(remaining["quantity"], 7)
            self.assertEqual(remaining["exercise_quantity"], 3)
            self.assertEqual(remaining["premium_trade_quantity"], 4)
            self.assertAlmostEqual(closed["commission"] + remaining["commission"], 100)

    def test_long_call_can_reallocate_all_premium_contracts_to_exercise_on_close(self):
        quote = {
            "asset": "اهرم", "strike": 900, "expiry": "2026-08-28",
            "base_price": 1100, "base_last": 1100, "option_last": 130,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 1000, "entry_premium": 100,
            "exercise_quantity": 0, "premium_trade_quantity": 3,
            "commission": 30,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                close_exercise_quantity=3, close_premium_trade_quantity=0,
                price_confirmed=True,
            )
            self.assertEqual(closed["status"], "closed")
            self.assertEqual(closed["exit_method"], "exercise")
            self.assertEqual(closed["quantity"], 3)
            self.assertEqual(closed["exercise_quantity"], 3)
            self.assertEqual(closed["premium_trade_quantity"], 0)

    def test_partial_long_close_can_exercise_contracts_initially_for_premium(self):
        quote = {
            "asset": "اهرم", "strike": 900, "expiry": "2026-08-28",
            "base_price": 1100, "base_last": 1100, "option_last": 130,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 1000, "entry_premium": 100,
            "exercise_quantity": 0, "premium_trade_quantity": 10,
            "commission": 100,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                close_exercise_quantity=4, close_premium_trade_quantity=0,
                price_confirmed=True,
            )
            remaining = next(item for item in store.list() if item["status"] == "open")
            self.assertEqual(closed["exit_method"], "exercise")
            self.assertEqual(closed["exercise_quantity"], 4)
            self.assertEqual(closed["premium_trade_quantity"], 0)
            self.assertEqual(remaining["quantity"], 6)
            self.assertEqual(remaining["exercise_quantity"], 0)
            self.assertEqual(remaining["premium_trade_quantity"], 6)

    def test_long_call_close_rejects_reallocated_total_above_remaining_quantity(self):
        quote = {
            "asset": "اهرم", "strike": 900, "expiry": "2026-08-28",
            "base_price": 1100, "base_last": 1100, "option_last": 130,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 1000, "entry_premium": 100,
            "exercise_quantity": 0, "premium_trade_quantity": 3,
            "commission": 30,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            with self.assertRaisesRegex(ValueError, "بیشتر از مانده معامله"):
                store.close(
                    created["id"], quote, exit_date=date(2026, 8, 3),
                    close_exercise_quantity=3, close_premium_trade_quantity=1,
                    price_confirmed=True,
                )

    def test_long_call_exercise_uses_strike_and_persists_exit_analytics(self):
        quote = {
            "asset": "اهرم", "strike": 2400, "expiry": "2026-08-28",
            "base_price": 2600, "option_exit_ask": 230,
            "base_last": 2590, "option_exit_bid": 225, "option_last": 228,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 2410, "entry_premium": 183,
            "annual_interest_rate": 40, "quantity": 1, "commission": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                exit_method="exercise", exit_commission=3, price_confirmed=True,
            )
            self.assertEqual(closed["exit_method"], "exercise")
            self.assertEqual(closed["exit_option_price"], 228)
            self.assertAlmostEqual(closed["exit_itm_percent"], (2590 - 2400) / 2590 * 100, places=2)
            self.assertIsNotNone(closed["exit_option_delta"])
            snapshot = calculate_trade_snapshot(closed, quote, as_of=date(2026, 8, 8))
            self.assertEqual(snapshot["realized_profit"], 2590 - 2400 - 183 - 2 - 3)

    def test_long_call_exercise_accepts_manual_premium_snapshot(self):
        quote = {
            "asset": "اهرم", "strike": 2400, "expiry": "2026-08-28",
            "base_price": 2600, "option_exit_bid": 225, "option_last": 228,
            "base_last": 2590,
        }
        payload = {
            "strategy_type": "long_call", "market": "tehran", "asset": "اهرم",
            "option_symbol": "ضهرم6045", "entry_date": "1405/05/07",
            "entry_base_price": 2410, "entry_premium": 183,
            "quantity": 1, "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                exit_method="exercise", exit_option_price=77, price_confirmed=True,
            )
            self.assertEqual(closed["exit_option_price"], 77)

    def test_covered_call_assignment_sells_underlying_at_strike(self):
        quote = {
            "asset": "اهرم", "strike": 2400, "expiry": "2026-08-28",
            "base_price": 2600, "option_exit_ask": 230,
            "base_last": 2590, "option_last": 228,
        }
        payload = {
            "market": "tehran", "asset": "اهرم", "option_symbol": "ضهرم6045",
            "entry_date": "1405/05/07", "entry_base_price": 2410,
            "entry_premium": 183, "quantity": 1, "commission": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"], quote, exit_date=date(2026, 8, 3),
                exit_method="exercise", exit_commission=3, price_confirmed=True,
            )
            snapshot = calculate_trade_snapshot(closed, quote, as_of=date(2026, 8, 8))
            self.assertEqual(snapshot["settlement_base_price"], 2400)
            self.assertEqual(snapshot["realized_profit"], 2400 - 2410 + 183 - 2 - 3)

    def test_manual_exit_prices_commission_and_note_are_persisted(self):
        quote = {
            "asset": "اهرم",
            "strike": 2400,
            "expiry": "2026-08-28",
            "base_price": 2361.8,
            "option_exit_ask": 10,
        }
        payload = {
            "market": "tehran",
            "asset": "اهرم",
            "option_symbol": "ضهرم6045",
            "entry_date": "1405/05/07",
            "entry_base_price": 2410,
            "entry_premium": 183,
            "quantity": 1,
            "commission": 2,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            closed = store.close(
                created["id"],
                quote,
                exit_date=date(2026, 8, 3),
                exit_base_price=2350,
                exit_option_price=12,
                exit_commission=3,
                exit_note="خروج دستی",
                price_confirmed=True,
            )
            persisted = store.list()[0]
            self.assertEqual(closed["exit_base_price"], 2350)
            self.assertEqual(closed["exit_option_price"], 12)
            self.assertEqual(persisted["exit_commission"], 3)
            self.assertEqual(persisted["exit_note"], "خروج دستی")

            snapshot = calculate_trade_snapshot(
                persisted, quote, as_of=date(2026, 8, 8)
            )
            self.assertEqual(snapshot["realized_commission"], 5)
            self.assertAlmostEqual(snapshot["option_profit"], 166)
            self.assertAlmostEqual(snapshot["total_profit"], 106)
            self.assertAlmostEqual(snapshot["realized_profit"], 106)
            self.assertAlmostEqual(
                snapshot["realized_profit_percent"], 106 / 2229 * 100
            )
            self.assertAlmostEqual(
                snapshot["realized_profit_yoy"], 106 / 2229 * 100 * 365 / 5
            )

    def test_close_requires_explicit_price_confirmation(self):
        quote = {
            "asset": "اهرم", "strike": 2400, "expiry": "2026-08-28",
            "base_price": 2361.8, "base_last": 2350,
            "option_exit_ask": 10, "option_last": 12,
        }
        payload = {
            "market": "tehran", "asset": "اهرم", "option_symbol": "ضهرم6045",
            "entry_date": "1405/05/07", "entry_base_price": 2410,
            "entry_premium": 183, "quantity": 1, "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            created = store.create(payload, quote)
            with self.assertRaisesRegex(ValueError, "تأیید"):
                store.close(created["id"], quote, exit_date=date(2026, 8, 3))


class UnderlyingPositionTests(unittest.TestCase):
    def test_v8_contract_count_scales_money_once_for_supported_multipliers(self):
        for contract_size in (1, 250, 1000):
            with self.subTest(contract_size=contract_size):
                quote = {
                    "asset": "اهرم", "strike": 1000,
                    "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
                    "base_last": 1200, "option_last": 70,
                    "contract_size": contract_size,
                }
                trade = {
                    "status": "open", "strategy_type": "long_call",
                    "market": "tehran", "asset": "اهرم",
                    "option_symbol": "ضهرم0001",
                    "entry_date": (tehran_today() - timedelta(days=5)).isoformat(),
                    "entry_base_price": 1100, "entry_premium": 50,
                    "quantity": 2, "exercise_quantity": 0,
                    "premium_trade_quantity": 2,
                    "contract_size": contract_size,
                    "quantity_kind": "contract", "currency_unit": "rial",
                    "calculation_version": 8,
                    "commission": 0, "strike": 1000,
                    "expiry": quote["expiry"],
                }
                snapshot = calculate_trade_snapshot(
                    trade, quote, as_of=tehran_today()
                )
                units = 2 * contract_size
                self.assertEqual(snapshot["underlying_units"], units)
                self.assertEqual(snapshot["invested_capital"], 50 * units)
                self.assertEqual(snapshot["long_offset_profit"], 20 * units)
                self.assertEqual(snapshot["long_offset_profit_percent"], 40)

    def test_v8_covered_call_collateral_uses_contracts_times_multiplier(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "فولاد", "acquisition_method": "direct",
                "entry_date": tehran_today().isoformat(), "entry_price": 1000,
                "quantity": 2000, "commission": 0,
            })
            quote = {"asset": "فولاد", "contract_size": 1000}
            payload = {
                "strategy_type": "covered_call", "market": "tehran",
                "asset": "فولاد", "underlying_position_id": position["id"],
                "quantity": 2, "quantity_kind": "contract",
                "currency_unit": "rial", "calculation_version": 8,
            }
            validate_underlying_link(payload, store.list(), [], quote)
            trades = [{**payload, "id": "trade-1", "status": "open",
                       "contract_size": 1000}]
            self.assertEqual(underlying_allocations(trades)[position["id"]], 2000)
            with self.assertRaisesRegex(ValueError, "موجودی آزاد"):
                validate_underlying_link(
                    {**payload, "quantity": 3}, store.list(), [], quote
                )

    def test_v8_exercise_converts_contracts_to_underlying_units(self):
        trade = {
            "id": "long-exercised-v8", "status": "closed",
            "strategy_type": "long_call", "exit_method": "mixed",
            "exit_date": tehran_today().isoformat(), "market": "tehran",
            "asset": "فولاد", "option_symbol": "ضفلا0001",
            "quantity": 3, "exercise_quantity": 1,
            "premium_trade_quantity": 1, "contract_size": 1000,
            "quantity_kind": "contract", "currency_unit": "rial",
            "calculation_version": 8, "strike": 2000,
            "entry_premium": 300, "entry_base_price": 2400,
            "annual_interest_rate": 40,
            "entry_date": (tehran_today() - timedelta(days=10)).isoformat(),
            "expiry": (tehran_today() + timedelta(days=20)).isoformat(),
        }
        terms = exercise_underlying_terms(trade)
        self.assertEqual(terms["source_contracts"], 1)
        self.assertEqual(terms["quantity"], 1000)

    def test_v8_partial_then_full_exercise_reconciles_contracts_and_inventory(self):
        quote = {
            "asset": "اهرم", "strike": 1000,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": 1200, "option_last": 70, "contract_size": 1000,
        }
        payload = {
            "market": "tehran", "strategy_type": "long_call",
            "asset": "اهرم", "option_symbol": "ضهرم0002",
            "entry_date": (tehran_today() - timedelta(days=5)).isoformat(),
            "entry_base_price": 1100, "entry_premium": 50,
            "exercise_quantity": 0, "premium_trade_quantity": 3,
            "quantity_kind": "contract", "currency_unit": "rial",
            "calculation_version": 8, "commission": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            trade_store = TradeStore(Path(directory) / "trades.json")
            underlying_store = UnderlyingPositionStore(
                Path(directory) / "underlying_positions.json"
            )
            created = trade_store.create(payload, quote)
            partial = trade_store.close(
                created["id"], quote, exit_date=tehran_today(),
                exit_method="exercise", exit_base_price=1200,
                exit_option_price=0, price_confirmed=True,
                close_exercise_quantity=1, close_premium_trade_quantity=0,
            )
            first_inventory = underlying_store.create_from_exercise(partial)
            remaining = next(
                item for item in trade_store.list() if item["id"] == created["id"]
            )
            self.assertEqual(partial["quantity"], 1)
            self.assertEqual(first_inventory["quantity"], 1000)
            self.assertEqual(remaining["quantity"], 2)
            self.assertEqual(remaining["premium_trade_quantity"], 2)

            final = trade_store.close(
                created["id"], quote, exit_date=tehran_today(),
                exit_method="exercise", exit_base_price=1200,
                exit_option_price=0, price_confirmed=True,
                close_exercise_quantity=2, close_premium_trade_quantity=0,
            )
            second_inventory = underlying_store.create_from_exercise(final)
            self.assertEqual(final["quantity"], 2)
            self.assertEqual(second_inventory["quantity"], 2000)
            self.assertEqual(
                sum(item["quantity"] for item in underlying_store.list()), 3000
            )

    def test_v8_rejects_fractional_contract_quantities(self):
        quote = {
            "asset": "اهرم", "strike": 1000,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "contract_size": 250,
        }
        payload = {
            "market": "tehran", "strategy_type": "long_call",
            "asset": "اهرم", "option_symbol": "ضهرم0001",
            "entry_date": tehran_today().isoformat(),
            "entry_base_price": 1100, "entry_premium": 50,
            "exercise_quantity": 0, "premium_trade_quantity": 1.5,
            "quantity_kind": "contract", "currency_unit": "rial",
            "calculation_version": 8,
        }
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            with self.assertRaisesRegex(ValueError, "whole number|عدد صحیح"):
                store.create(payload, quote)

    def test_covered_call_quantity_is_final_and_is_not_multiplied(self):
        quote = {
            "asset": "فولاد", "strike": 1000,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": 1080, "option_last": 40, "contract_size": 1000,
        }
        trade = {
            "status": "open", "strategy_type": "covered_call",
            "market": "tehran", "asset": "فولاد", "option_symbol": "ضفلا0001",
            "entry_date": (tehran_today() - timedelta(days=5)).isoformat(),
            "entry_base_price": 1050, "entry_premium": 50,
            "quantity": 2000, "contract_size": 1000, "commission": 0,
            "strike": 1000, "expiry": quote["expiry"],
        }
        snapshot = calculate_trade_snapshot(trade, quote, as_of=tehran_today())
        self.assertEqual(snapshot["underlying_units"], 2000)
        self.assertEqual(snapshot["invested_capital"], 2_000_000)
        self.assertEqual(snapshot["total_profit"], 80_000)
        expected_risk_free = 2_000_000 * 0.40 * 5 / 365
        self.assertAlmostEqual(snapshot["risk_free_profit"], expected_risk_free)
        self.assertEqual(snapshot["risk_free_days"], 5)
        self.assertAlmostEqual(
            snapshot["strategy_to_risk_free_multiple"],
            80_000 / expected_risk_free,
        )

    def test_long_call_quantity_is_already_final_and_is_not_multiplied(self):
        quote = {
            "asset": "اهرم", "strike": 1000,
            "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
            "base_last": 1200, "option_last": 70, "contract_size": 1000,
        }
        trade = {
            "status": "open", "strategy_type": "long_call",
            "market": "tehran", "asset": "اهرم", "option_symbol": "ضهرم0001",
            "entry_date": (tehran_today() - timedelta(days=5)).isoformat(),
            "entry_base_price": 1100, "entry_premium": 50,
            "quantity": 2, "exercise_quantity": 0,
            "premium_trade_quantity": 2, "contract_size": 1000,
            "commission": 0, "strike": 1000, "expiry": quote["expiry"],
        }
        snapshot = calculate_trade_snapshot(trade, quote, as_of=tehran_today())
        self.assertEqual(snapshot["underlying_units"], 2)
        self.assertEqual(snapshot["invested_capital"], 100)
        self.assertEqual(snapshot["long_offset_profit"], 40)
        self.assertEqual(snapshot["long_exercise_required_cash"], 2000)
        expected_risk_free = 100 * 0.40 * 5 / 365
        self.assertAlmostEqual(snapshot["risk_free_profit"], expected_risk_free)
        self.assertAlmostEqual(
            snapshot["strategy_to_risk_free_multiple"],
            snapshot["long_combined_profit"] / expected_risk_free,
        )

    def test_link_allocation_uses_real_underlying_units(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "فولاد", "acquisition_method": "direct",
                "entry_date": tehran_today().isoformat(), "entry_price": 1000,
                "quantity": 2000, "commission": 0,
            })
            quote = {"asset": "فولاد", "contract_size": 1000}
            payload = {
                "strategy_type": "covered_call", "market": "tehran", "asset": "فولاد",
                "underlying_position_id": position["id"], "quantity": 2000,
            }
            validate_underlying_link(payload, store.list(), [], quote)
            trades = [{**payload, "id": "trade-1", "status": "open", "contract_size": 1000}]
            self.assertEqual(underlying_allocations(trades)[position["id"]], 2000)
            snapshot = calculate_underlying_snapshot(
                position, {"last": 1100}, as_of=tehran_today(),
                allocated_quantity=2000,
            )
            self.assertEqual(snapshot["available_quantity"], 0)
            self.assertEqual(snapshot["invested_capital"], 0)
            with self.assertRaisesRegex(ValueError, "قابل حذف نیست"):
                validate_underlying_position_change(
                    position["id"], None, store.list(), trades, deleting=True,
                )

    def test_exercise_creates_units_at_break_even_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create_from_exercise({
                "id": "closed-long", "status": "closed", "strategy_type": "long_call",
                "exit_method": "exercise", "market": "tehran", "asset": "فولاد",
                "exit_date": tehran_today().isoformat(), "exercise_quantity": 3,
                "quantity": 3, "contract_size": 1000, "strike": 1000,
                "entry_premium": 50, "commission": 1500, "exit_commission": 1500,
                "entry_base_price": 1100, "annual_interest_rate": 40,
                "entry_date": (tehran_today() - timedelta(days=30)).isoformat(),
                "expiry": tehran_today().isoformat(),
            })
            self.assertEqual(position["quantity"], 3)
            expected = 1000 / (1.40 ** (30 / 365)) + 50
            self.assertAlmostEqual(position["entry_price"], expected)
            self.assertEqual(position["exercise_entry_mode"], "trade")
            self.assertAlmostEqual(
                position["relative_advantage_percent"],
                (1100 - expected) / 1100 * 100,
            )

    def test_exercise_underlying_form_uses_risk_free_adjusted_relative_advantage(self):
        trade = {
            "id": "long-exercised", "status": "closed", "strategy_type": "long_call",
            "exit_method": "exercise", "exit_date": tehran_today().isoformat(),
            "market": "tehran", "asset": "فولاد", "option_symbol": "ضفلا0001",
            "quantity": 2, "exercise_quantity": 1, "contract_size": 1000,
            "strike": 2000, "entry_premium": 300, "entry_base_price": 2400,
            "annual_interest_rate": 40,
            "entry_date": (tehran_today() - timedelta(days=10)).isoformat(),
            "expiry": (tehran_today() + timedelta(days=20)).isoformat(),
        }
        terms = exercise_underlying_terms(trade)
        expected = 2000 / (1.40 ** (10 / 365)) + 300
        self.assertAlmostEqual(terms["entry_price"], expected)
        self.assertEqual(terms["quantity"], 1)
        prepared = prepare_underlying_payload({
            "acquisition_method": "exercise", "exercise_entry_mode": "trade",
            "source_trade_id": "long-exercised", "entry_date": tehran_today().isoformat(),
            "commission": 0,
        }, [trade])
        self.assertAlmostEqual(prepared["entry_price"], expected)
        self.assertAlmostEqual(
            prepared["relative_advantage_percent"],
            (2400 - expected) / 2400 * 100,
        )

    def test_released_collateral_reprices_only_released_free_quantity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "فولاد", "acquisition_method": "direct",
                "entry_date": (tehran_today() - timedelta(days=20)).isoformat(),
                "entry_price": 1000, "quantity": 100, "commission": 0,
            })
            first = store.rebase_released_quantity(
                position["id"], 25,
                release_date=tehran_today(), release_price=1200,
                other_allocated_quantity=25, source_trade_id="covered-1",
            )
            self.assertAlmostEqual(first["entry_price"], (50 * 1000 + 25 * 1200) / 75)
            second = store.rebase_released_quantity(
                position["id"], 25,
                release_date=tehran_today(), release_price=1300,
                other_allocated_quantity=0, source_trade_id="covered-2",
            )
            self.assertAlmostEqual(second["entry_price"], 1125)
            self.assertEqual(len(second["cost_basis_events"]), 2)
            self.assertEqual(second["original_entry_price"], 1000)

    def test_covered_sale_audit_record_can_be_excluded_from_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "فولاد", "acquisition_method": "direct",
                "entry_date": (tehran_today() - timedelta(days=10)).isoformat(),
                "entry_price": 900, "quantity": 1000, "commission": 0,
            })
            closed = store.sell_quantity(
                position["id"], 1000, exit_date=tehran_today(), exit_price=1100,
                source_trade_id="covered-close", exclude_from_portfolio=True,
            )
            snapshot = calculate_underlying_snapshot(
                closed, None, as_of=tehran_today(), allocated_quantity=0,
            )
            self.assertTrue(snapshot["portfolio_excluded"])
            summary = summarize_closed_trades([], [snapshot])
            self.assertEqual(summary["count"], 0)
            growth = build_account_growth(
                [], as_of=tehran_today(), initial_capital=1_000_000,
                underlying_positions=[snapshot],
            )
            self.assertEqual(growth["total_profit"], 0)

    def test_underlying_explicit_zero_commissions_remain_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "فولاد", "acquisition_method": "direct",
                "entry_date": (tehran_today() - timedelta(days=3)).isoformat(),
                "entry_price": 1000, "quantity": 250,
                "commission": 0, "commission_source": "actual",
            })
            closed = store.sell_quantity(
                position["id"], 250, exit_date=tehran_today(), exit_price=1100,
                exit_commission=0, exit_commission_source="actual",
            )
            snapshot = calculate_underlying_snapshot(closed, None, as_of=tehran_today())
            self.assertEqual(snapshot["commission"], 0)
            self.assertEqual(snapshot["commission_source"], "actual")
            self.assertEqual(snapshot["exit_commission"], 0)
            self.assertEqual(snapshot["exit_commission_source"], "actual")
            self.assertFalse(snapshot["commission_auto_calculated"])
            self.assertFalse(snapshot["exit_commission_auto_calculated"])

    def test_underlying_missing_commissions_are_estimated_and_labeled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = UnderlyingPositionStore(Path(directory) / "underlying_positions.json")
            position = store.create({
                "market": "tehran", "asset": "فولاد", "acquisition_method": "direct",
                "entry_date": (tehran_today() - timedelta(days=3)).isoformat(),
                "entry_price": 1000, "quantity": 250, "commission": None,
            })
            self.assertGreater(position["commission"], 0)
            self.assertEqual(position["commission_source"], "estimated")
            closed = store.sell_quantity(
                position["id"], 250, exit_date=tehran_today(), exit_price=1100,
                exit_commission=None,
            )
            snapshot = calculate_underlying_snapshot(closed, None, as_of=tehran_today())
            self.assertGreater(snapshot["exit_commission"], 0)
            self.assertEqual(snapshot["exit_commission_source"], "estimated")
            self.assertTrue(snapshot["exit_commission_auto_calculated"])

    def test_v8_explicit_zero_commissions_are_not_reestimated(self):
        today = tehran_today()
        trade = {
            "id": "zero-fee", "status": "closed", "strategy_type": "long_call",
            "market": "tehran", "asset": "فولاد", "option_symbol": "ضفلا0001",
            "entry_date": (today - timedelta(days=10)).isoformat(),
            "exit_date": today.isoformat(), "expiry": (today + timedelta(days=20)).isoformat(),
            "entry_base_price": 1000, "exit_base_price": 1100,
            "entry_premium": 50, "exit_option_price": 80, "strike": 1000,
            "quantity": 2, "exercise_quantity": 0, "premium_trade_quantity": 2,
            "contract_size": 250, "quantity_kind": "contract",
            "currency_unit": "rial", "calculation_version": 8,
            "commission": 0, "commission_source": "actual",
            "exit_commission": 0, "exit_commission_source": "actual",
        }
        snapshot = calculate_trade_snapshot(trade, None, as_of=today)
        self.assertEqual(snapshot["commission"], 0)
        self.assertEqual(snapshot["exit_commission"], 0)
        self.assertEqual(snapshot["realized_commission"], 0)
        self.assertEqual(snapshot["realized_profit"], 15_000)

    def test_v8_null_commissions_are_estimated_and_labeled(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TradeStore(Path(directory) / "trades.json")
            quote = {
                "asset": "فولاد", "symbol": "ضفلا0001", "strike": 1000,
                "expiry": (tehran_today() + timedelta(days=30)).isoformat(),
                "contract_size": 1000,
            }
            created = store.create({
                "market": "tehran", "strategy_type": "long_call",
                "asset": "فولاد", "option_symbol": "ضفلا0001",
                "entry_date": tehran_today().isoformat(), "entry_base_price": 1100,
                "entry_premium": 50, "quantity": 1,
                "quantity_kind": "contract", "currency_unit": "rial",
                "calculation_version": 8, "commission": None,
            }, quote)
            self.assertEqual(created["commission_source"], "estimated")
            self.assertGreater(created["commission"], 0)

    def test_v8_exercise_cost_basis_uses_simple_act_365(self):
        today = tehran_today()
        terms = exercise_underlying_terms({
            "id": "simple-interest", "status": "closed",
            "strategy_type": "long_call", "exit_method": "exercise",
            "market": "tehran", "asset": "فولاد",
            "entry_date": (today - timedelta(days=365)).isoformat(),
            "exit_date": today.isoformat(), "quantity": 1, "exercise_quantity": 1,
            "contract_size": 1000, "quantity_kind": "contract",
            "currency_unit": "rial", "calculation_version": 8,
            "strike": 1000, "entry_premium": 50, "entry_base_price": 1100,
            "annual_interest_rate": 40,
        })
        self.assertEqual(terms["interest_convention"], "simple")
        self.assertEqual(terms["interest_day_count"], "ACT/365")
        self.assertEqual(terms["adjusted_strike"], 600)
        self.assertEqual(terms["entry_price"], 650)

    def test_v7_exercise_cost_basis_keeps_compound_legacy_semantics(self):
        today = tehran_today()
        terms = exercise_underlying_terms({
            "id": "legacy-interest", "status": "closed",
            "strategy_type": "long_call", "exit_method": "exercise",
            "market": "tehran", "asset": "فولاد",
            "entry_date": (today - timedelta(days=365)).isoformat(),
            "exit_date": today.isoformat(), "quantity": 1, "exercise_quantity": 1,
            "contract_size": 1000, "calculation_version": 7,
            "strike": 1000, "entry_premium": 50, "entry_base_price": 1100,
            "annual_interest_rate": 40,
        })
        self.assertEqual(terms["interest_convention"], "compound_legacy")
        self.assertAlmostEqual(terms["adjusted_strike"], 1000 / 1.4)


if __name__ == "__main__":
    unittest.main()
