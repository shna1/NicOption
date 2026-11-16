import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from bambo_bot.commodity_fx import build_commodity_fx_payload


class CommodityFxTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"ContractCode": "GoldBar", "BidPrice1": 31_250_000, "AskPrice1": 31_270_000, "LastTradedPrice": 31_260_000},
            {"ContractCode": "SilverBar", "BidPrice1": 5_030_000, "AskPrice1": 5_050_000, "LastTradedPrice": 5_040_000},
            {"ContractCode": "CopperCthd", "BidPrice1": 26_900_000, "AskPrice1": 27_000_000, "LastTradedPrice": 26_950_000},
            {"ContractCode": "GoldCoin", "BidPrice1": 2_330_000_000, "AskPrice1": 2_340_000_000, "LastTradedPrice": 2_335_000_000},
        ]
        self.benchmarks = {"gc": 4476.6, "si": 66.748, "hg": 6.6825}
        self.dates = {key: "2026-09-04" for key in self.benchmarks}

    def test_all_four_ime_certificates_are_reported(self):
        payload = build_commodity_fx_payload(
            self.rows, self.benchmarks, self.dates, 2_265_000, "2026-09-05",
            generated_at=datetime(2026, 9, 5, 12, tzinfo=ZoneInfo("Asia/Tehran")),
        )
        self.assertEqual([item["id"] for item in payload["assets"]], ["silver", "copper", "gold", "coin"])
        self.assertEqual(payload["free_market"]["price_toman"], 226_500)

    def test_gold_quote_uses_one_tenth_gram_and_995_purity(self):
        payload = build_commodity_fx_payload(
            self.rows, self.benchmarks, self.dates, 2_265_000, "2026-09-05"
        )
        gold = next(item for item in payload["assets"] if item["id"] == "gold")
        last = next(item for item in gold["quotes"] if item["id"] == "last")
        self.assertAlmostEqual(gold["usd_value_per_certificate"], 14.32064019, places=6)
        self.assertAlmostEqual(last["implied_usd_toman"], 218_286.33, places=1)
        self.assertLess(last["difference_percent"], 0)

    def test_coin_uses_fine_gold_content(self):
        payload = build_commodity_fx_payload(
            self.rows, self.benchmarks, self.dates, 2_265_000, "2026-09-05"
        )
        coin = next(item for item in payload["assets"] if item["id"] == "coin")
        self.assertAlmostEqual(coin["usd_value_per_certificate"], 1053.8813867, places=5)

    def test_copper_converts_one_kilogram_from_dollars_per_pound(self):
        payload = build_commodity_fx_payload(
            self.rows, self.benchmarks, self.dates, 2_265_000, "2026-09-05"
        )
        copper = next(item for item in payload["assets"] if item["id"] == "copper")
        last = next(item for item in copper["quotes"] if item["id"] == "last")
        self.assertAlmostEqual(copper["usd_value_per_certificate"], 14.73239067, places=6)
        self.assertAlmostEqual(last["implied_usd_toman"], 182_930.26, places=1)
        self.assertIn("۲٫۲۰۴۶۲", copper["conversion"]["formula"])
        self.assertIn("یک کیلوگرم", copper["conversion"]["note"])


if __name__ == "__main__":
    unittest.main()
