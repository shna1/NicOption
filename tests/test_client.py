import unittest
from unittest.mock import Mock

from bambo_bot.client import BamboClient, _extract_items
from bambo_bot.config import Settings


class TehranBasePriceRepairTests(unittest.TestCase):
    def test_missing_tehran_symbols_are_recovered_from_strategy_titles(self):
        client = BamboClient(Settings())
        rows = client._repair_tehran_symbols([
            {
                "title": "ضهرم6045 Covered Call Strategy",
                "symbolOption": None,
                "baseSymbol": "اهرم",
            },
            {
                "title": "ضستا5048 Long Underlying Strategy",
                "baseSymbol": "شستا",
            },
            {
                "title": "عنوان نامعتبر",
                "symbolOption": "ضهرم6001",
            },
        ])

        self.assertEqual(rows[0]["symbolOption"], "ضهرم6045")
        self.assertEqual(rows[1]["symbolOption"], "ضستا5048")
        self.assertEqual(rows[2]["symbolOption"], "ضهرم6001")

    def test_deraz_base_price_state_and_itm_are_recalculated(self):
        client = BamboClient(Settings())
        client._hamtaraz_price_loaded = True
        client._hamtaraz_purchase_price = 16_406
        rows = client._repair_tehran_base_prices(
            [{
                "baseSymbol": "هم_وزن",
                "symbolOption": "ضراز8007",
                "askPrice1Base": 28_644,
                "dueDatePrice": 20_000,
                "state": "ITM",
                "itmPercent": 30,
            }]
        )

        self.assertEqual(rows[0]["askPrice1Base"], 16_406)
        self.assertEqual(rows[0]["state"], "OTM")
        self.assertAlmostEqual(
            rows[0]["itmPercent"], (16_406 - 20_000) / 16_406 * 100
        )
        self.assertTrue(rows[0]["_basePriceOverridden"])

    def test_deraz_is_omitted_when_correct_price_is_unavailable(self):
        client = BamboClient(Settings())
        client._hamtaraz_price_loaded = True
        client._hamtaraz_purchase_price = None
        rows = client._repair_tehran_base_prices(
            [{"baseSymbol": "هم_وزن", "symbolOption": "ضراز8007"}]
        )
        self.assertEqual(rows, [])


class GoodsDataRepairTests(unittest.TestCase):
    def test_goods_symbol_is_recovered_and_zrmo_base_price_is_repaired(self):
        client = BamboClient(Settings())
        client._goods_base_price_cache = {"ZRMO": 17_601, "CUMO": None}

        rows = client._repair_goods_rows([
            {
                "title": "ZRMO05C20 Long Call Strategy",
                "baseSymbol": "صندوق طلای کارآمد",
                "askPrice1Base": 399,
                "askPrice1Option": 399,
                "dueDatePrice": 20_000,
            },
            {
                "title": "CUMO05C180 Long Call Strategy",
                "baseSymbol": "دارایی پایه",
                "askPrice1Base": 6_890_000,
                "askPrice1Option": 6_890_000,
                "dueDatePrice": 18_000_000,
            },
        ])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbolOption"], "ZRMO05C20")
        self.assertEqual(rows[0]["askPrice1Base"], 17_601)
        self.assertEqual(rows[0]["state"], "OTM")
        self.assertAlmostEqual(
            rows[0]["itmPercent"], (17_601 - 20_000) / 17_601 * 100
        )
        self.assertTrue(rows[0]["_basePriceOverridden"])

    def test_covered_rows_receive_symbols_from_matching_long_rows(self):
        client = BamboClient(Settings())
        common = {
            "expiration_date": "2026-10-01",
            "dueDatePrice": 19_000,
            "bidPrice1Option": 17_500,
            "askPrice1Option": 17_890,
        }
        enriched = client._enrich_goods_symbols(
            [{**common, "baseSymbol": "درخشان"}],
            [{**common, "title": "DGDY05C19 Long Call Strategy"}],
        )
        self.assertEqual(enriched[0]["symbolOption"], "DGDY05C19")

    def test_covered_call_returns_are_repriced_from_best_bid(self):
        client = BamboClient(Settings())
        client.fetch_rows = lambda strategy: [{
            "baseSymbol": "درخشان",
            "symbolOption": "DGDY05C19",
            "expiration_date": "2026-10-01",
            "days": 161,
            "state": "ITM",
            "value": 1_000,
            "simpleInterestRate": 10.03,
            "interestRate": 22.74,
            "askPrice1Base": 33_401,
            "bidPrice1Option": 17_500,
            "dueDatePrice": 19_000,
            "bep": 15_649,
            "itmPercent": 43.1,
        }]

        contract = client.fetch_contracts()[0]
        expected_expiry = (17_500 - (33_401 - 19_000)) / 33_401 * 100
        self.assertAlmostEqual(contract.expiry_return, expected_expiry)
        self.assertAlmostEqual(
            contract.annual_return, expected_expiry * 365 / 161
        )
        self.assertEqual(contract.breakeven, 33_401 - 17_500)


class IMEDataTests(unittest.TestCase):
    def test_depth_normalizer_keeps_all_available_levels(self):
        row = {
            "CallBidPrice1": 100, "CallBidVolume1": 20,
            "CallAskPrice1": 110, "CallAskVolume1": 30,
            "CallBidPrice5": 80, "CallBidVolume5": 7,
            "CallAskPrice5": 130, "CallAskVolume5": 9,
        }
        levels = BamboClient._normalize_depth_levels(
            row, depth=5,
            bid_price="CallBidPrice{level}", bid_volume="CallBidVolume{level}",
            ask_price="CallAskPrice{level}", ask_volume="CallAskVolume{level}",
        )
        self.assertEqual(len(levels), 5)
        self.assertEqual(levels[0]["bid_price"], 100)
        self.assertEqual(levels[4]["ask_volume"], 9)

    def test_tsetmc_intraday_observations_are_grouped_into_15_minute_candles(self):
        client = BamboClient(Settings())
        info = Mock()
        info.raise_for_status.return_value = None
        info.json.return_value = {"closingPriceInfo": {
            "dEven": 20260912, "hEven": 93100, "pDrCotVal": 120,
        }}
        history = Mock()
        history.raise_for_status.return_value = None
        history.json.return_value = {"closingPriceHistory": [
            {"hEven": 90000, "pDrCotVal": 100},
            {"hEven": 90500, "pDrCotVal": 110},
            {"hEven": 91600, "pDrCotVal": 90},
        ]}
        client.option_session.get = Mock(side_effect=[info, history])

        candles = client.fetch_tsetmc_intraday_candles("123")

        self.assertEqual(len(candles), 3)
        self.assertEqual(candles[0]["open"], 100)
        self.assertEqual(candles[0]["high"], 110)
        self.assertEqual(candles[0]["close"], 110)
        self.assertEqual(candles[1]["timestamp"], "2026-09-12T09:15:00+03:30")

    def test_official_ime_option_and_underlying_quotes_are_joined(self):
        client = BamboClient(Settings())
        rows = client._normalize_ime_goods_rows(
            [{
                "CallContractCode": "CUMO05C180",
                "CallLastTradingPersianDate": "1405/05/19",
                "CallBidPrice1": 6_010_002,
                "CallAskPrice1": 6_199_999,
                "CallLastTradedPrice": 6_400_000,
                "CallLastSettlementPrice": 6_350_000,
                "CallTradesVolume": 40,
                "CallTradesValue": 256_015,
                "CallContractSize": 1,
                "StrikePrice": 18_000_000,
            }],
            [{
                "ContractCode": "CopperCthd",
                "AskPrice1": 24_139_990,
                "BidPrice1": 24_100_000,
                "LastTradedPrice": 24_120_000,
                "LastSettlementPrice": 25_087_558,
            }],
            [],
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["baseSymbol"], "مس کاتد")
        self.assertEqual(row["symbolOption"], "CUMO05C180")
        self.assertEqual(row["askPrice1Base"], 24_139_990)
        self.assertEqual(row["bestAskBase"], 24_139_990)
        self.assertEqual(row["bestBidBase"], 24_100_000)
        self.assertEqual(row["lastTradeBase"], 24_120_000)
        self.assertEqual(row["closingPriceBase"], 25_087_558)
        self.assertEqual(row["bidPrice1Option"], 6_010_002)
        self.assertEqual(row["askPrice1Option"], 6_199_999)
        self.assertEqual(row["optionPrice"], 6_400_000)
        self.assertEqual(row["closingPriceOption"], 6_350_000)
        self.assertEqual(row["volume"], 40)
        self.assertEqual(row["value"], 256_015_000)
        self.assertEqual(row["expiration_date"], "2026-08-10")
        self.assertEqual(row["state"], "ITM")

    def test_ime_fund_uses_best_offer_and_maps_arabic_kaf(self):
        client = BamboClient(Settings())
        rows = client._normalize_ime_goods_rows(
            [{
                "CallContractCode": "KASH05C80",
                "CallLastTradingPersianDate": "1405/06/22",
                "CallBidPrice1": 65_000,
                "StrikePrice": 80_000,
            }],
            [],
            [{
                "Symbol": "كهربا",
                "OfferPrice1": 178_000,
                "LastPrice": 177_900,
                "FinalPrice": 177_800,
            }],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["baseSymbol"], "کهربا")
        self.assertEqual(rows[0]["askPrice1Base"], 178_000)
        self.assertEqual(rows[0]["state"], "ITM")

    def test_every_requested_goods_family_has_an_official_mapping(self):
        expected = {
            "GBMO": "طلای 24 عیار",
            "SLSH": "شمش نقره",
            "NQAB": "صندوق نقره کهکشان فیروزه",
            "CUMO": "مس کاتد",
            "TLME": "صندوق طلای لوتوس",
            "KASH": "کهربا",
            "ZRMO": "صندوق طلای کارآمد",
            "DGDY": "صندوق طلای درخشان",
            "JZMO": "صندوق طلای دنا زاگرس",
        }
        self.assertEqual(
            {symbol: BamboClient._ime_asset_for_symbol(symbol) for symbol in expected},
            expected,
        )

    def test_ime_silver_fund_option_is_joined_to_noghrabi_quote(self):
        client = BamboClient(Settings())
        rows = client._normalize_ime_goods_rows(
            [{
                "CallContractCode": "NQAB05C1200",
                "CallLastTradingPersianDate": "1405/08/23",
                "CallBidPrice1": 2_900,
                "CallAskPrice1": 3_000,
                "CallLastTradedPrice": 3_000,
                "CallTradesVolume": 101,
                "CallTradesValue": 302_800,
                "CallContractSize": 1_000,
                "StrikePrice": 12_000,
            }],
            [],
            [{
                "Symbol": "نقرابي",
                "OfferPrice1": 13_674,
                "DemandPrice1": 13_673,
                "LastPrice": 13_674,
                "FinalPrice": 13_710,
            }],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["baseSymbol"], "صندوق نقره کهکشان فیروزه")
        self.assertEqual(rows[0]["symbolOption"], "NQAB05C1200")
        self.assertEqual(rows[0]["askPrice1Base"], 13_674)
        self.assertEqual(rows[0]["volume"], 101)


class BamboResponseShapeTests(unittest.TestCase):
    def test_legacy_list_response_is_supported(self):
        self.assertEqual(_extract_items([{"id": 1}], "bad"), [{"id": 1}])

    def test_new_items_response_is_supported(self):
        self.assertEqual(
            _extract_items({"items": [{"id": 2}]}, "bad"),
            [{"id": 2}],
        )

    def test_nested_tehran_items_response_is_supported(self):
        self.assertEqual(
            _extract_items({"data": {"items": [{"id": 3}]}}, "bad"),
            [{"id": 3}],
        )

    def test_market_watch_normalization_keeps_all_calls_and_excludes_puts(self):
        rows = BamboClient._normalize_tehran_market_watch_rows([
            {
                "symbol": "ضتاص7011",
                "name": "اختیارخ تاصیکو-20000-05/07/08",
                "base_symbol": "تاصیکو",
                "miladi_due_date": "2026-09-30T00:00:00.000Z",
                "days_until_due": 58,
                "due_date_price": 20_000,
                "last_trade_base": 20_500,
                "ask_price_1_base": 20_600,
                "last_trade_option": 1_899,
                "ask_price_1_option": 1_980,
                "bid_price_1_option": 1_899,
            },
            {
                "symbol": "طتاص7001",
                "name": "اختیارف تاصیکو-8000-05/07/08",
                "base_symbol": "تاصیکو",
            },
        ])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbolOption"], "ضتاص7011")
        self.assertEqual(rows[0]["baseSymbol"], "تاصیکو")
        self.assertEqual(rows[0]["askPrice1Base"], 20_600)
        self.assertEqual(rows[0]["askPrice1Option"], 1_980)
        self.assertEqual(rows[0]["optionPrice"], 1_899)
        self.assertEqual(rows[0]["expiration_date"], "2026-09-30")
        self.assertEqual(rows[0]["state"], "ITM")
        self.assertAlmostEqual(
            rows[0]["itmPercent"], (20_600 - 20_000) / 20_600 * 100
        )

    def test_tehran_contracts_can_be_built_from_complete_market_watch(self):
        client = BamboClient(Settings())
        rows = client._normalize_tehran_market_watch_rows([{
            "symbol": "ضستا6050",
            "name": "اختیارخ شستا-2400-05/06/11",
            "base_symbol": "شستا",
            "miladi_due_date": "2026-09-02T00:00:00.000Z",
            "days_until_due": 25,
            "due_date_price": 2_400,
            "ask_price_1_base": 2_556,
            "last_trade_option": 380,
            "ask_price_1_option": 381,
            "bid_price_1_option": 380,
            "value": 454_996_865_000,
        }])

        contracts = client.fetch_tehran_contracts(rows)

        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0].asset, "شستا")
        self.assertEqual(contracts[0].symbol, "ضستا6050")
        self.assertEqual(contracts[0].state, "ITM")
        self.assertAlmostEqual(contracts[0].expiry_return, 8.763693270735524)
        self.assertAlmostEqual(contracts[0].annual_return, 127.94992175273865)

    def test_tsetmc_call_rows_are_normalized_from_official_fields(self):
        rows = BamboClient._normalize_tsetmc_option_rows([{
            "insCode_C": "62171799977328589",
            "uaInsCode": "17914401175772326",
            "contractSize": 1_000,
            "lVal18AFC_C": "ضهرم5025",
            "lVal30_C": "اختيارخ اهرم-22000-1405/05/28",
            "lval30_UA": "اهرم",
            "pDrCotVal_UA": 48_682,
            "pClosing_UA": 48_527,
            "endDate": "20260819",
            "strikePrice": 22_000,
            "remainedDay": 10,
            "pDrCotVal_C": 26_002,
            "pMeDem_C": 26_002,
            "pMeOf_C": 28_500,
            "qTotTran5J_C": 954,
            "qTotCap_C": 26_249_934_000,
        }])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["baseSymbol"], "اهرم")
        self.assertEqual(row["symbolOption"], "ضهرم5025")
        self.assertEqual(row["askPrice1Base"], 48_682)
        self.assertEqual(row["bidPrice1Option"], 26_002)
        self.assertEqual(row["askPrice1Option"], 28_500)
        self.assertEqual(row["optionPrice"], 26_002)
        self.assertEqual(row["expiration_date"], "2026-08-19")
        self.assertEqual(row["volume"], 954)
        self.assertEqual(row["value"], 26_249_934_000)
        self.assertEqual(row["state"], "ITM")
        self.assertAlmostEqual(row["itmPercent"], (48_682 - 22_000) / 48_682 * 100)

    def test_tsetmc_uses_underlying_close_when_last_trade_is_zero(self):
        rows = BamboClient._normalize_tsetmc_option_rows([{
            "lVal18AFC_C": "ضنمونه",
            "lval30_UA": "نمونه",
            "pDrCotVal_UA": 0,
            "pClosing_UA": 12_000,
            "endDate": "20261201",
            "strikePrice": 13_000,
        }])
        self.assertEqual(rows[0]["askPrice1Base"], 12_000)
        self.assertEqual(rows[0]["state"], "OTM")

    def test_tsetmc_response_is_cached_for_both_strategies(self):
        client = BamboClient(Settings())
        response = Mock()
        response.json.return_value = {"instrumentOptMarketWatch": [{
            "lVal18AFC_C": "ضنمونه",
            "lval30_UA": "نمونه",
            "pDrCotVal_UA": 12_000,
            "endDate": "20261201",
            "strikePrice": 10_000,
        }]}
        client.option_session.get = Mock(return_value=response)

        covered = client.fetch_tehran_rows("covered_call")
        long_rows = client.fetch_tehran_rows("long_underlying")

        self.assertEqual(covered, long_rows)
        client.option_session.get.assert_called_once()
        response.raise_for_status.assert_called_once()

    def test_tsetmc_base_quote_reads_best_ask_and_buy_queue(self):
        client = BamboClient(Settings())
        limits = Mock()
        limits.json.return_value = {"bestLimits": [{
            "number": 1, "pMeDem": 10_500, "pMeOf": 10_550,
            "qTitMeDem": 2_000, "qTitMeOf": 300,
        }]}
        threshold = Mock()
        threshold.json.return_value = {"instrumentInfo": {"staticThreshold": {
            "psGelStaMax": 10_500, "psGelStaMin": 9_500,
        }}}
        status = Mock()
        status.json.return_value = {"closingPriceInfo": {
            "dEven": 20260914,
            "instrumentState": {
                "cEtaval": "IS", "cEtavalTitle": "ممنوع-متوقف",
            },
        }}
        client.option_session.get = Mock(side_effect=[limits, threshold, status])

        quote = client._fetch_tsetmc_base_quote("123")

        self.assertEqual(quote["bestAskBase"], 10_550)
        self.assertEqual(quote["bestBidBase"], 10_500)
        self.assertEqual(quote["baseQueueStatus"], "صف خرید")
        self.assertTrue(quote["baseIsClosed"])
        self.assertEqual(quote["baseTradingStatus"], "ممنوع-متوقف")
        limits.raise_for_status.assert_called_once()
        threshold.raise_for_status.assert_called_once()
        status.raise_for_status.assert_called_once()

    def test_queue_opposite_quote_outside_allowed_range_is_rejected(self):
        row = BamboClient._sanitize_order_book_row({
            "bestBidBase": 10_500,
            "bestAskBase": 10_700,
            "baseQueueStatus": "صف خرید",
            "basePriceMin": 9_500,
            "basePriceMax": 10_500,
            "bidPrice1Option": 500,
            "askPrice1Option": 550,
            "optionQueueStatus": "صف خرید",
            "optionPriceMax": 500,
        })
        self.assertEqual(row["bestBidBase"], 10_500)
        self.assertIsNone(row["bestAskBase"])
        self.assertEqual(row["bidPrice1Option"], 500)
        self.assertIsNone(row["askPrice1Option"])
        self.assertFalse(row["quoteQualityValid"])
        self.assertIn("bestAskBase", row["quoteQualityWarnings"])
        self.assertIn("askPrice1Option", row["quoteQualityWarnings"])


if __name__ == "__main__":
    unittest.main()
