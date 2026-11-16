import unittest

from bambo_bot.option_math import call_greeks_from_price, call_greeks_from_volatility


class OptionMathTests(unittest.TestCase):
    def test_recovers_black_scholes_delta_from_market_price(self):
        result = call_greeks_from_price(100, 100, 365, 10.4506, 5)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.implied_volatility, 0.20, places=3)
        self.assertAlmostEqual(result.delta, 0.6368, places=3)

    def test_quote_outside_no_arbitrage_bounds_has_no_delta(self):
        self.assertIsNone(call_greeks_from_price(100, 80, 30, 1, 40))

    def test_reference_volatility_produces_fallback_delta(self):
        result = call_greeks_from_volatility(100, 80, 30, 40, 0.35)
        self.assertIsNotNone(result)
        self.assertGreater(result.delta, 0.5)
        self.assertLessEqual(result.delta, 1.0)


if __name__ == "__main__":
    unittest.main()
