import unittest
from urllib.parse import unquote

from bambo_bot.history import COMMODITY_HISTORIES, PriceHistoryClient


class _Response:
    def __init__(self, query):
        self.query = query

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "instrumentSearch": [
                {"lVal18AFC": self.query, "insCode": "123", "lastDate": 1, "flow": 1}
            ]
        }


class _Session:
    def __init__(self):
        self.queries = []

    def get(self, url, timeout):
        query = unquote(url.rsplit("/", 1)[-1])
        self.queries.append(query)
        return _Response(query)


class PriceHistoryTests(unittest.TestCase):
    def test_lotus_uses_gold_symbol_before_fund_name(self):
        client = PriceHistoryClient.__new__(PriceHistoryClient)
        client.session = _Session()
        client.settings = type("Settings", (), {"http_timeout_seconds": 10})()
        result = client._resolve("صندوق طلای لوتوس", "صندوق طلای لوتوس")
        self.assertEqual(client.session.queries[0], "طلا")
        self.assertEqual(result["lVal18AFC"], "طلا")

    def test_hamtaraz_uses_its_tsetmc_symbol_with_space(self):
        client = PriceHistoryClient.__new__(PriceHistoryClient)
        client.session = _Session()
        client.settings = type("Settings", (), {"http_timeout_seconds": 10})()
        result = client._resolve("هم‌تراز", "هم_وزن")
        self.assertEqual(client.session.queries[0], "هم تراز")
        self.assertEqual(result["lVal18AFC"], "هم تراز")

    def test_current_purchase_price_prefers_best_ask(self):
        class QuoteSession:
            def get(self, url, timeout):
                class Response:
                    def raise_for_status(self):
                        return None

                    def json(self):
                        return {"bestLimits": [{"number": 1, "pMeOf": 16420}]}

                return Response()

        client = PriceHistoryClient.__new__(PriceHistoryClient)
        client.session = QuoteSession()
        client.settings = type("Settings", (), {"http_timeout_seconds": 10})()
        client._resolve = lambda asset, source: {"insCode": "123"}
        self.assertEqual(
            client.fetch_current_purchase_price("هم‌تراز", "هم_وزن"), 16420
        )

    def test_current_purchase_price_falls_back_to_last_trade(self):
        class QuoteSession:
            def get(self, url, timeout):
                class Response:
                    def __init__(self, target):
                        self.target = target

                    def raise_for_status(self):
                        return None

                    def json(self):
                        if "BestLimits" in self.target:
                            return {"bestLimits": [{"number": 1, "pMeOf": 0}]}
                        return {"closingPriceInfo": {"pDrCotVal": 16406}}

                return Response(url)

        client = PriceHistoryClient.__new__(PriceHistoryClient)
        client.session = QuoteSession()
        client.settings = type("Settings", (), {"http_timeout_seconds": 10})()
        client._resolve = lambda asset, source: {"insCode": "123"}
        self.assertEqual(
            client.fetch_current_purchase_price("هم‌تراز", "هم_وزن"), 16406
        )

    def test_gold_bar_history_uses_tenth_gram_scale(self):
        class CommodityResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [["250,000,000", "245,000,000", "255,000,000", "250,000,000", "", "", "2026/07/17", ""]]}

        class CommoditySession:
            def get(self, url, params, timeout):
                self.url = url
                self.params = params
                return CommodityResponse()

        client = PriceHistoryClient.__new__(PriceHistoryClient)
        client.session = CommoditySession()
        client.settings = type("Settings", (), {"http_timeout_seconds": 10})()
        result = client._fetch_commodity_history("طلای 24 عیار", COMMODITY_HISTORIES["طلای 24 عیار"])
        self.assertEqual(result["symbol"], "شمش طلا")
        self.assertEqual(result["points"][0]["price"], 25_000_000)
        self.assertEqual(result["points"][0]["low"], 24_500_000)
        self.assertEqual(result["points"][0]["high"], 25_500_000)


if __name__ == "__main__":
    unittest.main()
