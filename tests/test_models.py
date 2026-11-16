import unittest

from bambo_bot.models import Contract, reprice_covered_contract


class ContractTests(unittest.TestCase):
    def test_covered_call_uses_best_bid_and_source_returns(self):
        contract = Contract.from_api(
            {
                "baseSymbol": "خودرو",
                "symbolOption": "ضخود",
                "expiration_date": "2026-08-17T00:00:00.000Z",
                "days": 30,
                "state": "ITM",
                "value": 10,
                "askPrice1Base": 100,
                "bidPrice1Option": 5,
                "optionPrice": 10,
                "dueDatePrice": 105,
                "interestRate": 44,
                "simpleInterestRate": 3.5,
                "bep": 95,
            },
            "خودرو",
        )
        self.assertEqual(contract.option_bid, 5)
        self.assertEqual(contract.option_last, 10)
        self.assertEqual(contract.option_gap_percent, 50)
        self.assertEqual(contract.breakeven, 95)
        self.assertEqual(contract.expiry_return, 3.5)
        self.assertEqual(contract.annual_return, 44)

    def test_annual_return_is_derived_when_bambo_omits_it(self):
        contract = Contract.from_api(
            {
                "baseSymbol": "وبملت",
                "symbolOption": "ضملت6040",
                "expiration_date": "2026-08-24T00:00:00.000Z",
                "days": 30,
                "state": "ITM",
                "value": 1000,
                "simpleInterestRate": 6,
                "askPrice1Base": 1000,
                "bidPrice1Option": 100,
                "dueDatePrice": 950,
            },
            "وبملت",
        )
        self.assertEqual(contract.expiry_return, 6)
        self.assertEqual(contract.annual_return, 73)

    def test_source_annual_return_still_takes_precedence(self):
        contract = Contract.from_api(
            {
                "baseSymbol": "وبملت",
                "symbolOption": "ضملت6040",
                "expiration_date": "2026-08-24T00:00:00.000Z",
                "days": 30,
                "state": "ITM",
                "value": 1000,
                "simpleInterestRate": 6,
                "interestRate": 81.5,
                "askPrice1Base": 1000,
                "bidPrice1Option": 100,
                "dueDatePrice": 950,
            },
            "وبملت",
        )
        self.assertEqual(contract.annual_return, 81.5)

    def test_covered_call_can_be_repriced_from_last_trade(self):
        contract = Contract(
            asset="خودرو", source_asset="خودرو", symbol="ضخود", expiry="2026-08-17",
            days=30, state="ITM", transaction_value=10, annual_return=1,
            expiry_return=1, base_price=100, option_bid=5, option_last=10,
            strike=95, breakeven=95, itm_percent=5,
        )
        repriced = reprice_covered_contract(contract, "last")
        self.assertEqual(repriced.expiry_return, 5)
        self.assertAlmostEqual(repriced.annual_return, 60.8333333333)
        self.assertEqual(repriced.breakeven, 90)


if __name__ == "__main__":
    unittest.main()
