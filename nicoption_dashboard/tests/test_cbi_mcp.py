from django.test import SimpleTestCase, override_settings

from nicoption_dashboard.cbi_mcp import TOOL_CALLS, _series_from_snapshots, collect_cbi_snapshot
from nicoption_dashboard.central_bank_data import _catalog_series


class FakeClient:
    def __init__(self, command, timeout):
        self.command = command
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def initialize(self):
        return {"serverInfo": {"name": "cbi-mcp", "version": "0.1.0"}}

    def call_tool(self, name, arguments):
        if name == "cb_statistics":
            return {"period": "1405 مرداد", "sheet": arguments.get("sheet") or "متغیرهای عمده", "rows": [["شاخص نمونه", 1, 2, 3, 4, 5]]}
        return {"tool": name, "arguments": arguments}


class CbiMcpCollectionTests(SimpleTestCase):
    @override_settings(CBI_MCP_COMMAND="uvx cbi-mcp", CBI_MCP_TIMEOUT_SECONDS=45)
    def test_collects_every_configured_tool_through_mcp_client(self):
        result = collect_cbi_snapshot(client_class=FakeClient)

        self.assertEqual(result.server_name, "cbi-mcp")
        self.assertEqual(result.server_version, "0.1.0")
        self.assertEqual(len(result.payload), len(TOOL_CALLS) + 1)
        self.assertIn("exchange_rates", result.payload)
        self.assertIn("statistics_balance_of_payments", result.payload)
        self.assertIn("publications_interbank_reports", result.payload)
        self.assertIn("statistics_time_series", result.payload)

    def test_balance_of_payments_rows_become_named_monthly_series(self):
        snapshots = [
            {"period": "1405 مرداد", "rows": [["بازار غیررسمی", "اسکناس بازار رسمی", "حواله بازار رسمی", "ترجیحی", "سال ۱۴۰۵"], [190, 185, 154, 28, "مرداد"]]},
            {"period": "1405 تیر", "rows": [["بازار غیررسمی", "اسکناس بازار رسمی", "حواله بازار رسمی", "ترجیحی", "سال ۱۴۰۵"], [180, 170, 150, 28, "تیر"]]},
        ]

        series = _series_from_snapshots("balance_of_payments", snapshots)

        self.assertEqual([item["name"] for item in series], ["بازار غیررسمی", "اسکناس بازار رسمی", "حواله بازار رسمی", "ترجیحی"])
        self.assertEqual(series[0]["points"], [{"period": "1405 تیر", "value": 180}, {"period": "1405 مرداد", "value": 190}])

    def test_monetary_rows_use_latest_balance_not_growth_columns(self):
        snapshots = [
            {"period": "1404 اسفند", "rows": [["پایه پولی", 100, 120, 180, 20, 50, 10, 20]]},
            {"period": "1404 بهمن", "rows": [["پایه پولی", 100, 120, 150, 20, 25, 10, 12]]},
        ]

        series = _series_from_snapshots("monetary", snapshots)

        self.assertEqual(series[0]["points"], [{"period": "1404 بهمن", "value": 150}, {"period": "1404 اسفند", "value": 180}])

    def test_catalog_normalizes_monthly_quarterly_and_annual_series_and_changes(self):
        payload = {"statistics_time_series": {"sections": [{"key": "monetary", "label": "پول", "series": [
            {"name": "ماهانه", "unit": "درصد", "points": [{"period": "1404 فروردین", "value": 10}, {"period": "1404 اردیبهشت", "value": 12}, {"period": "1405 اردیبهشت", "value": 14}]},
            {"name": "فصلی", "unit": "شاخص", "points": [{"period": "1404 بهار", "value": 20}, {"period": "1404 تابستان", "value": 22}]},
            {"name": "سالانه", "unit": "ضریب", "points": [{"period": "1403", "value": 0.2}, {"period": "1404", "value": 0.3}]},
        ]}]}}
        items = _catalog_series(payload)
        self.assertEqual([item["frequency"] for item in items], ["monthly", "quarterly", "annual"])
        self.assertEqual(items[0]["current"]["period_change_value"], None)  # missing 1404/03 through 1405/01
        self.assertEqual(items[0]["current"]["yearly_change_percentage_points"], 2)
        self.assertEqual(items[1]["current"]["period_change_value"], 2)
        self.assertAlmostEqual(items[2]["current"]["yearly_change_coefficient"], 0.1)

    def test_catalog_drops_invalid_and_sorts_points_by_period(self):
        payload = {"statistics_time_series": {"sections": [{"key": "x", "series": [
            {"name": "تست", "unit": "ریال", "points": [
                {"period": "1404 اردیبهشت", "value": 2}, {"period": "1404 فروردین", "value": 1},
                {"period": "1404 خرداد", "value": None}, {"period": "نامعتبر", "value": 3},
            ]}
        ]}]}}
        item = _catalog_series(payload)[0]
        self.assertEqual([point["value"] for point in item["series"]], [1, 2])

    def test_catalog_includes_mcp_annual_and_monthly_inflation(self):
        items = _catalog_series({"inflation": {
            "year": 1405,
            "monthly": [{"month": "فروردین", "rate_pct": 10}, {"month": "اردیبهشت", "rate_pct": 12}],
            "annual": [{"year": 1403, "rate_pct": 20}, {"year": 1404, "rate_pct": 25}],
        }})
        self.assertEqual(len(items), 2)
        self.assertEqual({item["frequency"] for item in items}, {"monthly", "annual"})
        self.assertTrue(all(item["comparison_source"] == "cbi_mcp" for item in items))

    def test_catalog_reads_simple_wide_annual_table(self):
        item = _catalog_series({"statistics_fiscal": {"section": "مالی دولت", "rows": [
            ["شاخص", 1403, 1404], ["درآمدهای دولت", 10, 15], ["هزینه‌های دولت", 8, 11],
        ]}})[0]
        self.assertEqual(item["frequency"], "annual")
        self.assertEqual(item["series"][-1]["yearly_change_value"], 5)

    def test_catalog_merges_duplicate_series_fragments_by_name_and_period(self):
        payload = {"statistics_time_series": {"sections": [{"key": "monetary", "label": "پول", "series": [
            {"name": "پايه پولي (1)", "unit": "هزار میلیارد ریال", "points": [
                {"period": "1404 فروردین", "value": 10}, {"period": "1404 اردیبهشت", "value": 11},
            ]},
            {"name": "پایه پولی از سمت مصارف", "unit": "هزار میلیارد ریال", "points": [
                {"period": "1404 اردیبهشت", "value": 11}, {"period": "1404 خرداد", "value": 12},
            ]},
            {"name": "مانده اجرای عملیات سیاست پولی(2)", "unit": "هزار میلیارد ریال", "points": [
                {"period": "1404 فروردین", "value": 3}, {"period": "1404 اردیبهشت", "value": 4},
            ]},
            {"name": "مانده اجرای عملیات سیاست پولی(3)", "unit": "هزار میلیارد ریال", "points": [
                {"period": "1404 خرداد", "value": 5}, {"period": "1404 تیر", "value": 6},
            ]},
        ]}]}}
        items = _catalog_series(payload)
        self.assertEqual(len(items), 2)
        base = next(item for item in items if item["title_fa"] == "پایه پولی")
        policy_balance = next(item for item in items if item["title_fa"] == "مانده اجرای عملیات سیاست پولی")
        self.assertEqual([point["value"] for point in base["series"]], [10, 11, 12])
        self.assertEqual([point["value"] for point in policy_balance["series"]], [3, 4, 5, 6])
        self.assertEqual(len({base["technical_id"], policy_balance["technical_id"]}), 2)

    def test_catalog_excludes_currency_series(self):
        items = _catalog_series({
            "rate_history": {"currency": "USD", "points": [{"date": "1405/08/07", "rate_irr": 100}, {"date": "1405/08/08", "rate_irr": 101}]},
            "exchange_rates": {"date": "1405/08/08", "rates": [{"code": "USD", "rate_irr": 101}]},
        })
        self.assertEqual(items, [])

    def test_snapshot_collector_merges_duplicate_rows_before_persisting(self):
        snapshots = [
            {"period": "1404 فروردین", "rows": [["پايه پولي (1)", 0, 0, 10], ["پایه پولی از سمت مصارف", 0, 0, 10], ["مانده اجرای عملیات سیاست پولی(2)", 0, 0, 3]]},
            {"period": "1404 اردیبهشت", "rows": [["پايه پولي (1)", 0, 0, 11], ["پایه پولی از سمت مصارف", 0, 0, 11], ["مانده اجرای عملیات سیاست پولی(2)", 0, 0, 4]]},
            {"period": "1404 خرداد", "rows": [["مانده اجرای عملیات سیاست پولی(3)", 0, 0, 5]]},
        ]
        items = _series_from_snapshots("monetary", snapshots)
        self.assertEqual({item["name"] for item in items}, {"پایه پولی", "مانده اجرای عملیات سیاست پولی"})
        self.assertEqual(len(next(item for item in items if item["name"] == "پایه پولی")["points"]), 2)
        self.assertEqual(len(next(item for item in items if item["name"] == "مانده اجرای عملیات سیاست پولی")["points"]), 3)
