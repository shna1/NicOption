from decimal import Decimal, localcontext
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.management import call_command

from nicoption_dashboard.cbi_mcp import CbiMcpResult

from nicoption_dashboard.monetary_data import monetary_dataset, monetary_payload
from nicoption_dashboard.models import CentralBankSnapshot


class MonetaryDatasetTests(TestCase):
    def setUp(self):
        monetary_dataset.cache_clear()

    def test_metadata_scopes_are_complete_ordered_and_disjoint(self):
        main = monetary_payload("main")["indicators"]
        detailed = monetary_payload("detailed")["indicators"]

        self.assertEqual(len(main), 7)
        self.assertEqual(len(detailed), 9)
        self.assertEqual(
            [item["technical_id"] for item in main],
            [
                "base_money",
                "liquidity_multiplier",
                "liquidity",
                "money",
                "banknotes_coins_public",
                "demand_deposits",
                "quasi_money",
            ],
        )
        self.assertFalse(
            {item["technical_id"] for item in main}
            & {item["technical_id"] for item in detailed}
        )
        self.assertEqual(
            [item["column_position"] for item in main],
            sorted(item["column_position"] for item in main),
        )

    def test_growth_uses_calendar_month_keys_not_adjacent_rows(self):
        liquidity = next(
            item
            for item in monetary_payload("main")["indicators"]
            if item["technical_id"] == "liquidity"
        )
        points = {point["year_month"]: point for point in liquidity["series"]}
        current = points["1404-12"]

        with localcontext() as context:
            context.prec = 38
            expected_monthly = (
                Decimal(current["value"]) / Decimal(points["1404-11"]["value"]) - 1
            ) * 100
            expected_yearly = (
                Decimal(current["value"]) / Decimal(points["1403-12"]["value"]) - 1
            ) * 100
        self.assertEqual(Decimal(current["monthly_growth_percent"]), expected_monthly)
        self.assertEqual(Decimal(current["yearly_growth_percent"]), expected_yearly)

        # 1383-10 and 1383-11 are missing; the following month must not use
        # the previous physical row as a monthly baseline.
        self.assertIsNone(points["1383-12"]["monthly_growth_percent"])

    def test_all_scope_contains_every_non_date_indicator(self):
        indicators = monetary_payload("all")["indicators"]

        self.assertEqual(len(indicators), 16)
        self.assertEqual(
            {item["technical_id"] for item in indicators},
            {item["technical_id"] for item in monetary_payload("main")["indicators"]}
            | {item["technical_id"] for item in monetary_payload("detailed")["indicators"]},
        )
        self.assertTrue(all(item["description_fa"] for item in indicators))
        base_money = next(item for item in indicators if item["technical_id"] == "base_money")
        self.assertIn("عرضه پول", base_money["description_fa"])

    def test_quality_report_has_no_suspicious_rows_and_preserves_missing_months(self):
        payload = monetary_payload("main")
        quality = payload["quality"]

        self.assertEqual(quality["row_count"], 263)
        self.assertEqual(len(quality["missing_months"]), 14)
        self.assertEqual(quality["duplicate_jalali_months"], [])
        self.assertEqual(quality["duplicate_gregorian_dates"], [])
        self.assertEqual(quality["non_numeric_values"], [])
        self.assertEqual(quality["metadata_conflicts"], [])
        self.assertEqual(quality["suspicious_periods"], [])
        liquidity = next(
            item for item in payload["indicators"] if item["technical_id"] == "liquidity"
        )
        suspicious = [point for point in liquidity["series"] if point["is_suspicious"]]
        self.assertEqual(suspicious, [])
        expected = {
            "base_money": ("6039.7", "8599.9"),
            "liquidity_multiplier": ("8.001", "7.369"),
            "liquidity": ("48324.4", "63376.8"),
            "money": ("9865.8", "16296.9"),
            "banknotes_coins_public": ("864.3", "1226.1"),
            "demand_deposits": ("9001.5", "15070.8"),
            "quasi_money": ("38458.6", "47079.9"),
            "qard_al_hasana_savings": ("3261.7", "5497.3"),
            "short_term_deposits": ("13634.7", "15931.3"),
            "one_year_deposits": ("10687.5", "14739.5"),
            "two_year_deposits": ("9602.1", "6868.3"),
            "three_year_deposits": ("0.1", "2346.8"),
            "four_year_deposits": ("3.7", "3.6"),
            "five_year_deposits": ("61.4", "63.7"),
            "long_term_deposits_total": ("20354.8", "24021.9"),
            "other_deposits": ("1207.4", "1629.4"),
        }
        for indicator in monetary_payload("all")["indicators"]:
            points = {point["year_month"]: point for point in indicator["series"]}
            self.assertEqual(
                (points["1400-12"]["value"], points["1401-12"]["value"]),
                expected[indicator["technical_id"]],
            )


class MonetaryApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="monetary-user")
        self.client.force_login(self.user)

    def test_monetary_api_returns_requested_scope(self):
        response = self.client.get("/api/monetary-indicators?scope=detailed")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "detailed")
        self.assertEqual(len(response.json()["indicators"]), 9)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_monetary_api_returns_all_bank_indicators(self):
        response = self.client.get("/api/monetary-indicators?scope=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "all")
        self.assertEqual(len(response.json()["indicators"]), 16)

    def test_monetary_api_rejects_unknown_scope(self):
        response = self.client.get("/api/monetary-indicators?scope=unknown")

        self.assertEqual(response.status_code, 422)
        self.assertIn("scope", response.json()["error"])

    def test_monetary_page_and_api_require_authentication(self):
        self.client.logout()

        page = self.client.get("/monetary-details")
        api = self.client.get("/api/monetary-indicators")

        self.assertEqual(page.status_code, 302)
        self.assertIn("/login?next=%2Fmonetary-details", page.url)
        self.assertEqual(api.status_code, 403)

    def test_central_bank_snapshot_api_returns_mcp_provenance_and_data(self):
        CentralBankSnapshot.objects.create(
            server_name="cbi-mcp",
            server_version="0.1.0",
            payload={"exchange_rates": {"date": "1405/08/09", "rates": [{"code": "USD", "rate_irr": 1871664}]},
                     "rate_history": {"currency": "USD", "points": [{"date": "1405/08/09", "rate_irr": 1871664}]},
                     "statistics_balance_of_payments": {"rows": [["بازار غیررسمی", 1]]},
                     "statistics_time_series": {"sections": [{"key": "balance_of_payments", "series": []}]}},
            errors={"statistics_fiscal": "temporarily unavailable"},
        )

        response = self.client.get("/api/central-bank-snapshot")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["available"])
        self.assertEqual(response.json()["source"]["author"], "سپهر رادمرد")
        self.assertNotIn("exchange_rates", response.json()["data"])
        self.assertNotIn("rate_history", response.json()["data"])
        self.assertNotIn("statistics_balance_of_payments", response.json()["data"])
        self.assertNotIn("balance_of_payments", [item["key"] for item in response.json()["data"]["statistics_time_series"]["sections"]])

    def test_central_bank_snapshot_api_exposes_shared_catalog_series(self):
        CentralBankSnapshot.objects.create(server_name="cbi-mcp", server_version="0.1.0", payload={
            "statistics_time_series": {"sections": [{"key": "monetary", "label": "پول و اعتبار", "series": [
                {"name": "نقدینگی", "unit": "هزار میلیارد ریال", "points": [
                    {"period": "1404 فروردین", "value": 10}, {"period": "1404 اردیبهشت", "value": 12},
                ]},
            ]}]},
        })
        item = self.client.get("/api/central-bank-snapshot").json()["series_catalog"][0]
        self.assertTrue(item["technical_id"].startswith("CBI:"))
        self.assertEqual(item["comparison_source"], "cbi_mcp")
        self.assertEqual(item["current"]["value"], 12)
        self.assertEqual(item["current"]["period_change_value"], 2)

    def test_open_market_history_uses_its_own_group_and_multi_period_series(self):
        CentralBankSnapshot.objects.create(server_name="cbi-mcp", server_version="0.1.0", payload={
            "statistics_time_series": {"sections": [{"key": "monetary", "label": "پول و اعتبار", "series": [
                {"name": "مانده اجرای عملیات سیاست پولی(2)", "unit": "هزار میلیارد ریال", "points": [
                    {"period": "1404 فروردین", "value": 3}, {"period": "1404 اردیبهشت", "value": 4},
                ]},
            ]}]},
            "open_market": {"latest": {"date": "1405/07/27", "repo": {"orders_accepted": 700, "outstanding": 700}}},
        })
        payload = self.client.get("/api/central-bank-snapshot").json()
        item = next(i for i in payload["series_catalog"] if i["title_fa"] == "مانده اجرای عملیات سیاست پولی")
        self.assertEqual(item["economic_group"], "عملیات بازار باز")
        self.assertEqual(len(item["series"]), 2)
        self.assertFalse(any(i["title_fa"] in {"سفارش پذیرفته‌شده ریپو", "مانده ریپو"} for i in payload["series_catalog"]))

    @patch("nicoption_dashboard.management.commands.sync_cbi_mcp.collect_cbi_snapshot")
    def test_sync_command_persists_collected_series_payload(self, collect):
        collect.return_value = CbiMcpResult("cbi-mcp", "0.1.0", {
            "statistics_time_series": {"sections": [{"key": "monetary", "series": [{"name": "سری ذخیره‌شده", "points": [
                {"period": "1404 فروردین", "value": 1}, {"period": "1404 اردیبهشت", "value": 2},
            ]}]}]},
        }, {})
        call_command("sync_cbi_mcp")
        saved = CentralBankSnapshot.objects.latest("collected_at")
        self.assertEqual(saved.payload["statistics_time_series"]["sections"][0]["series"][0]["name"], "سری ذخیره‌شده")

    def test_central_bank_snapshot_api_has_explicit_empty_state(self):
        response = self.client.get("/api/central-bank-snapshot")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(response.json()["source"]["organization"], "بانک مرکزی جمهوری اسلامی ایران")

    def test_central_bank_snapshot_api_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/central-bank-snapshot").status_code, 403)
