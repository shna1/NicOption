import unittest

from bambo_bot.scoring import covered_call_score


class CoveredCallScoringTests(unittest.TestCase):
    def test_score_is_bounded_and_components_reconcile(self):
        result = covered_call_score(
            annual_return=70, premium=150, base_price=1000,
            option_delta=0.75, delta_estimated=False,
            transaction_value=100, liquidity_universe=[10, 50, 100],
            days=45, quote_gap_percent=2,
        )
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertAlmostEqual(result["score"], sum(result["components"].values()), places=1)
        self.assertEqual(result["downside_protection_percent"], 15)

    def test_zero_liquidity_and_very_short_expiry_are_penalized(self):
        strong = covered_call_score(
            annual_return=70, premium=150, base_price=1000, option_delta=0.75,
            delta_estimated=False, transaction_value=100,
            liquidity_universe=[10, 100], days=45, quote_gap_percent=1,
        )
        weak = covered_call_score(
            annual_return=70, premium=150, base_price=1000, option_delta=0.75,
            delta_estimated=False, transaction_value=0,
            liquidity_universe=[10, 100], days=2, quote_gap_percent=30,
        )
        self.assertGreater(strong["score"], weak["score"])


if __name__ == "__main__":
    unittest.main()
