import unittest

from bambo_bot.long_underlying import (
    build_volume_map,
    calculate_profit_percent,
    select_positive_opportunities,
)


def row(symbol="TLTR05C110", option_bid=235000, strike=1100000):
    return {
        "baseSymbol": "صندوق طلای لوتوس",
        "symbolOption": symbol,
        "expiration_date": "1405-04-28",
        "days": 1,
        "state": "ITM",
        "itmPercent": 12.5,
        "askPrice1Base": 1360009,
        "bidPrice1Option": option_bid,
        "optionPrice": option_bid,
        "dueDatePrice": strike,
        "value": 497263,
        "volume": 10,
    }


class LongUnderlyingTests(unittest.TestCase):
    def test_formula_can_use_best_ask_basis(self):
        row = {
            "askPrice1Base": 1_200,
            "bidPrice1Option": 100,
            "askPrice1Option": 115,
            "dueDatePrice": 1_000,
            "days": 30,
        }
        result = calculate_profit_percent(row, 40, price_basis="ask")
        expected = (1_200 - (1_000 + 115 - 1_000 * .40 * 30 / 365)) / 1_200 * 100
        self.assertAlmostEqual(result, round(expected, 2))

    def test_formula_uses_interest_adjusted_exercise_plus_premium(self):
        self.assertEqual(calculate_profit_percent(row(), 40), 1.93)

    def test_formula_uses_best_bid_instead_of_last_trade(self):
        item = row()
        item["optionPrice"] = 1
        self.assertEqual(calculate_profit_percent(item, 40), 1.93)

    def test_formula_can_use_last_trade_basis(self):
        item = row()
        item["optionPrice"] = 250000
        self.assertEqual(
            calculate_profit_percent(item, 40, price_basis="last", option_last=250000),
            0.82,
        )

    def test_zatas_7004_changes_decision_when_last_trade_is_used(self):
        item = {
            "baseSymbol": "تاصیکو",
            "symbolOption": "ضتاص7004",
            "expiration_date": "2026-09-30",
            "days": 50,
            "state": "ITM",
            "itmPercent": 48.38,
            "askPrice1Base": 21_310,
            "bidPrice1Option": 10_100,
            "optionPrice": 11_000,
            "dueDatePrice": 11_000,
            "value": 110_000_000,
            "volume": 10,
        }
        self.assertEqual(calculate_profit_percent(item, 40), 3.81)
        self.assertEqual(
            calculate_profit_percent(
                item, 40, price_basis="last", option_last=11_000
            ),
            -0.41,
        )
        self.assertNotIn(
            ("تاصیکو", "2026-09-30"),
            select_positive_opportunities(
                [item], 40, price_basis="last"
            ),
        )

    def test_quote_gap_compares_best_ask_with_last_trade(self):
        item = row()
        item["optionPrice"] = 250000
        item["askPrice1Option"] = 260000
        opportunity = select_positive_opportunities([item], 40)[
            ("صندوق طلای لوتوس", "1405-04-28")
        ][0]
        self.assertEqual(opportunity.option_bid, 235000)
        self.assertEqual(opportunity.option_ask, 260000)
        self.assertEqual(opportunity.option_last, 250000)
        self.assertEqual(opportunity.option_gap_percent, 4.0)
        self.assertEqual(opportunity.itm_percent, 12.5)

    def test_only_positive_profit_is_selected(self):
        rows = [row("POSITIVE"), row("NEGATIVE", option_bid=400000)]
        selected = select_positive_opportunities(rows, 40)
        items = selected[("صندوق طلای لوتوس", "1405-04-28")]
        self.assertEqual([item.symbol for item in items], ["POSITIVE"])

    def test_positive_rows_are_sorted_by_profit(self):
        rows = [row("LOW", option_bid=250000), row("HIGH", option_bid=200000)]
        items = select_positive_opportunities(rows, 40)[
            ("صندوق طلای لوتوس", "1405-04-28")
        ]
        self.assertEqual([item.symbol for item in items], ["HIGH", "LOW"])

    def test_zero_volume_is_excluded(self):
        rows = [row("ZERO"), row("ACTIVE")]
        selected = select_positive_opportunities(
            rows,
            40,
            {"ZERO": 0, "ACTIVE": 2},
        )
        items = selected[("صندوق طلای لوتوس", "1405-04-28")]
        self.assertEqual([item.symbol for item in items], ["ACTIVE"])

    def test_volume_map_uses_option_goods_volume(self):
        volume_map = build_volume_map(
            [
                {"code_id": "A", "vol_transaction": 12},
                {"symbol": "B", "vol_transaction": None},
            ]
        )
        self.assertEqual(volume_map, {"A": 12, "B": 0})

    def test_goods_last_price_map_uses_close_price(self):
        from bambo_bot.long_underlying import build_option_last_price_map

        result = build_option_last_price_map(
            [{"code_id": "A", "close_price": 125}, {"symbol": "B", "close_price": 0}]
        )
        self.assertEqual(result, {"A": 125})


if __name__ == "__main__":
    unittest.main()
