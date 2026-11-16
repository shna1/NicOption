import unittest
from dataclasses import replace

from bambo_bot.models import Contract
from bambo_bot.selector import select_picks, top_unique_contracts


def contract(symbol, state, value, annual, expiry_return):
    return Contract(
        asset="طلای 24 عیار",
        source_asset="طلای 24 عیار",
        symbol=symbol,
        expiry="1405-08-19",
        days=100,
        state=state,
        transaction_value=value,
        annual_return=annual,
        expiry_return=expiry_return,
        base_price=100,
        option_bid=10,
        strike=110,
        breakeven=90,
        itm_percent=5,
    )


class SelectorTests(unittest.TestCase):
    def test_selects_only_two_itm_winners_per_asset_and_expiry(self):
        rows = [
            contract("ITM-A", "ITM", 10, 60, 9),
            contract("ITM-B", "ITM", 20, 50, 12),
            contract("OTM-A", "OTM", 30, 60, 15),
            contract("OTM-B", "OTM", 40, 50, 18),
        ]
        picks = select_picks(rows)[
            ("طلای 24 عیار", "1405-08-19")
        ]
        self.assertEqual([pick.contract.symbol for pick in picks], ["ITM-A", "ITM-B"])
        self.assertTrue(all(pick.contract.state == "ITM" for pick in picks))

    def test_zero_transaction_value_is_eligible(self):
        rows = [contract("ZERO", "ITM", 0, 999, 999), contract("POSITIVE", "ITM", 2, 10, 10)]
        picks = select_picks(rows)[
            ("طلای 24 عیار", "1405-08-19")
        ]
        self.assertTrue(all(pick.contract.symbol == "ZERO" for pick in picks))

    def test_group_is_preserved_when_nothing_is_eligible(self):
        rows = [replace(contract("NO", "ITM", 0, 1, 1), annual_return=None, expiry_return=None)]
        selections = select_picks(rows)
        self.assertIn(("طلای 24 عیار", "1405-08-19"), selections)
        self.assertEqual(selections[("طلای 24 عیار", "1405-08-19")], [])

    def test_annual_return_below_thirty_is_excluded_before_ranking(self):
        rows = [
            contract("BELOW", "ITM", 100, 29.99, 999),
            contract("ELIGIBLE", "ITM", 1, 30, 1),
        ]
        picks = select_picks(rows, min_annual_return=30)[
            ("طلای 24 عیار", "1405-08-19")
        ]
        self.assertTrue(picks)
        self.assertTrue(all(pick.contract.symbol == "ELIGIBLE" for pick in picks))

    def test_tie_is_broken_by_transaction_value(self):
        rows = [contract("LOW", "ITM", 2, 50, 50), contract("HIGH", "ITM", 20, 50, 50)]
        picks = select_picks(rows)[
            ("طلای 24 عیار", "1405-08-19")
        ]
        self.assertTrue(all(pick.contract.symbol == "HIGH" for pick in picks))

    def test_top_five_excludes_zero_transaction_value(self):
        zero = contract("ZERO", "ITM", 0, 999, 99)
        positive = contract("POSITIVE", "ITM", 1, 50, 5)
        selections = {
            ("طلای 24 عیار", zero.expiry): [
                *select_picks([zero])[(zero.asset, zero.expiry)],
                *select_picks([positive])[(positive.asset, positive.expiry)],
            ]
        }
        self.assertEqual([item.symbol for item in top_unique_contracts(selections)], ["POSITIVE"])


if __name__ == "__main__":
    unittest.main()
