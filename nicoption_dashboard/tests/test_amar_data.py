from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from unittest.mock import patch
from unittest import skipUnless

from nicoption_dashboard.amar_data import amar_comparison_catalog, amar_snapshot_payload
from nicoption_dashboard.amar_mcp import AmarMcpResult
from nicoption_dashboard.models import StatisticalCenterSnapshot
from nicoption_dashboard.statistical_center_data import METADATA_FILE


def sample_payload():
    return {
        "labour_force": {
            "unemployment": [
                {"period": "پاییز 1404", "country": 7.6, "urban": 8.2, "rural": 5.8},
                {"period": "تابستان 1404", "country": 7.3, "urban": 8.0, "rural": 5.2},
            ],
            "participation": [{"period": "پاییز 1404", "country": 41.2}],
        },
        "youth_unemployment": {
            "youth_unemployment": [{"period": "پاییز 1404", "country": 21.0}],
        },
        "gdp_quarterly": {
            "series": [{
                "period": "1404-Q3",
                "growth_pct": 2.1,
                "gdp_ex_oil_pct": 2.4,
                "agriculture_pct": -1.0,
                "industry_pct": 1.7,
                "services_pct": 3.2,
            }],
        },
        "population": {
            "census": "1395 (2016)",
            "country": {"population": 79_926_270, "households": 24_196_035},
        },
        "calendar": {"year": 1405, "count": 1, "items": [{"month": 12, "day": 1, "product": "محصول"}]},
        "macro": {
            "population": {
                "label": "جمعیت، نیروی انسانی و آموزش",
                "collection": "new",
                "source_org": "مرکز آمار ایران",
                "description": "شرح",
                "source": {"release": 100},
                "tables": [{
                    "n": 1,
                    "title": "جمعیت",
                    "source": "مرکز آمار ایران",
                    "columns": ["جمعیت"],
                    "total_rows": 1,
                    "rows": [["1404", 90_000_000]],
                }],
            },
            "housing": {
                "label": "مسکن و ساختمان تکمیلی",
                "collection": "complementary",
                "source_org": "مرکز آمار ایران و بانک مرکزی",
                "description": "شرح",
                "source": {"release": 100},
                "tables": [],
            },
        },
        "travel_tables": [{
            "id": 21835,
            "title": "سری زمانی تعداد سفرها",
            "period": "بهار 1387 تا تابستان 1404",
            "frequency": "فصلی",
            "table": {"rows": [
                [1, "عنوان جدول", None, None, None, None],
                [2, "وضعیت سفر", 1387, 1387, 1404, 1404],
                [3, None, "بهار", "تابستان", "بهار", "تابستان"],
                [4, "سفر رفته", 10, 12, 15, 16],
                [5, "سفر نرفته", 20, 18, 17, 14],
            ]},
        }],
        "releases": {"tourism": {"results": [{"id": 7, "title": "گردشگری"}]}},
    }


class AmarDataTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="amar-user")
        self.client.force_login(self.user)

    def test_payload_separates_new_and_complementary_topics(self):
        StatisticalCenterSnapshot.objects.create(server_version="0.1.1", payload=sample_payload())

        payload = amar_snapshot_payload()

        self.assertTrue(payload["available"])
        self.assertEqual(payload["summary"]["new_topics"], 1)
        self.assertEqual(payload["summary"]["complementary_topics"], 1)
        self.assertEqual(payload["summary"]["tables"], 1)

    def test_topic_api_returns_selected_tables_and_rejects_unknown_topic(self):
        StatisticalCenterSnapshot.objects.create(payload=sample_payload())

        response = self.client.get("/api/amar-statistics?topic=population")
        unknown = self.client.get("/api/amar-statistics?topic=unknown")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_topic"]["tables"][0]["title"], "جمعیت")
        self.assertEqual(unknown.status_code, 404)

    def test_comparison_catalog_contains_labour_and_gdp_series_in_date_order(self):
        StatisticalCenterSnapshot.objects.create(payload=sample_payload())

        catalog = amar_comparison_catalog()
        codes = {item["code"] for item in catalog}
        unemployment = next(item for item in catalog if item["code"] == "AMAR:UNEMPLOYMENT")

        self.assertIn("AMAR:PARTICIPATION", codes)
        self.assertIn("AMAR:GDP_GROWTH", codes)
        self.assertEqual(unemployment["comparison_source"], "amar_mcp")
        self.assertEqual([point["value"] for point in unemployment["series"]], [7.3, 7.6])
        self.assertAlmostEqual(unemployment["series"][-1]["period_change_percentage_points"], 0.3)

    @skipUnless(METADATA_FILE.exists(), "prepared Statistical Center data is excluded from the portfolio repository")
    def test_statistical_center_catalog_includes_mcp_unemployment_series(self):
        StatisticalCenterSnapshot.objects.create(payload=sample_payload())

        response = self.client.get("/api/statistical-center-indicators?q=نرخ+بیکاری")

        self.assertEqual(response.status_code, 200)
        unemployment = [
            item for item in response.json()["amar_mcp_series"]
            if "نرخ بیکاری" in item["name_fa"]
        ]
        self.assertTrue(unemployment)
        self.assertEqual(unemployment[0]["series"][-1]["value"], 7.6)

    @skipUnless(METADATA_FILE.exists(), "prepared Statistical Center data is excluded from the portfolio repository")
    def test_statistical_center_catalog_includes_annual_household_gini_series(self):
        payload = sample_payload()
        payload["macro"]["household"] = {
            "label": "بودجه خانوار و توزیع درآمد",
            "tables": [{
                "n": 1,
                "title": "ضریب جینی",
                "columns": ["کل", "شهری", "روستایی"],
                "rows": [[1403, 0.387, 0.3689, 0.3532], [1404, 0.3849, 0.3686, 0.3543]],
            }],
        }
        StatisticalCenterSnapshot.objects.create(payload=payload)

        response = self.client.get("/api/statistical-center-indicators?q=ضریب+جینی")

        self.assertEqual(response.status_code, 200)
        gini_series = [item for item in response.json()["amar_mcp_series"] if "ضریب جینی" in item["name_fa"]]
        self.assertEqual(len(gini_series), 3)
        self.assertTrue(all(item["frequency"] == "annual" for item in gini_series))
        self.assertEqual(gini_series[0]["series"][-1]["value"], 0.3849)
        self.assertAlmostEqual(gini_series[0]["series"][-1]["period_change_coefficient"], -0.0021)
        self.assertAlmostEqual(gini_series[0]["series"][-1]["yearly_change_coefficient"], -0.0021)

    @skipUnless(METADATA_FILE.exists(), "prepared Statistical Center data is excluded from the portfolio repository")
    def test_statistical_center_catalog_includes_travel_time_series(self):
        StatisticalCenterSnapshot.objects.create(payload=sample_payload())

        response = self.client.get("/api/statistical-center-indicators?q=سفر")

        self.assertEqual(response.status_code, 200)
        travel = [item for item in response.json()["amar_mcp_series"] if "سفر" in item["name_fa"]]
        self.assertTrue(travel)
        self.assertEqual(travel[0]["frequency"], "quarterly")
        self.assertEqual([point["value"] for point in travel[0]["series"]], [10, 12, 15, 16])

    def test_statistical_center_page_includes_both_collections_application(self):
        response = self.client.get("/statistical-center")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="amarStatisticsApp"')
        self.assertNotContains(response, 'src="/amar-statistics.js')
        self.assertContains(response, 'id="statisticalCenterApp"')

    @patch("nicoption_dashboard.management.commands.sync_amar_mcp.collect_amar_snapshot")
    def test_sync_rejects_an_empty_upstream_result_without_replacing_snapshot(self, collect):
        existing = StatisticalCenterSnapshot.objects.create(payload=sample_payload())
        collect.return_value = AmarMcpResult(
            server_name="amar-mcp",
            server_version="0.1.1",
            payload={"macro": {"population": {"tables": []}}, "releases": {}},
            errors={"macro.population.inventory": "upstream unavailable"},
        )

        with self.assertRaisesMessage(CommandError, "no usable data"):
            call_command("sync_amar_mcp")

        self.assertEqual(list(StatisticalCenterSnapshot.objects.values_list("pk", flat=True)), [existing.pk])
