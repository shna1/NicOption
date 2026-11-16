import re

from django.contrib.auth import get_user_model
from django.test import TestCase

from nicoption_dashboard.statistical_center_data import (
    statistical_center_catalog,
    statistical_center_dataset,
    statistical_center_series,
)


class StatisticalCenterDatasetTests(TestCase):
    def setUp(self):
        statistical_center_dataset.cache_clear()

    def test_catalog_has_all_prepared_series_and_defaults_to_current_main(self):
        payload = statistical_center_catalog({})

        self.assertEqual(payload["summary"]["total_series"], 1817)
        self.assertEqual(payload["summary"]["main_series"], 48)
        self.assertEqual(payload["summary"]["detailed_series"], 1769)
        self.assertEqual(payload["summary"]["monthly_series"], 851)
        self.assertEqual(payload["summary"]["quarterly_series"], 966)
        self.assertEqual(payload["pagination"]["total"], 48)
        self.assertEqual(len(payload["indicators"]), 25)
        self.assertTrue(all(item["classification"] == "اصلی" for item in payload["indicators"]))
        self.assertTrue(all(item["lifecycle"] == "جاری" for item in payload["indicators"]))
        analytics = payload["indicators"][0]["analytics"]
        self.assertIn(analytics["signal"], {-1, 0, 1})
        self.assertGreaterEqual(analytics["percentile_2y"], 0)
        self.assertLessEqual(analytics["percentile_2y"], 100)
        self.assertGreaterEqual(len(analytics["trend_2y"]), 2)
        self.assertLessEqual(len(analytics["trend_2y"]), 24)

    def test_catalog_supports_server_filters_search_and_pagination(self):
        payload = statistical_center_catalog({
            "classification": "all",
            "lifecycle": "all",
            "frequency": "monthly",
            "economic_group": "شاخص قیمت مصرف‌کننده شهری",
            "q": "تورم نقطه به نقطه",
            "page_size": "10",
        })

        self.assertGreater(payload["pagination"]["total"], 0)
        self.assertLessEqual(len(payload["indicators"]), 10)
        self.assertTrue(all(item["frequency"] == "monthly" for item in payload["indicators"]))
        self.assertTrue(all(item["economic_group"] == "شاخص قیمت مصرف‌کننده شهری" for item in payload["indicators"]))
        self.assertRegex(
            payload["indicators"][0]["last_available_label_fa"],
            r"^(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند) [۰-۹]{4}$",
        )

    def test_series_reads_only_requested_indexed_range(self):
        catalog = statistical_center_catalog({"page_size": "10"})
        selected = catalog["indicators"][0]
        payload = statistical_center_series(selected["series_key"])

        self.assertEqual(payload["indicator"]["series_key"], selected["series_key"])
        self.assertEqual(len(payload["indicator"]["series"]), selected["observation_count"])
        self.assertEqual(payload["source"]["name"], "مرکز آمار ایران")
        self.assertTrue(payload["indicator"]["series"][0]["period_date"])

    def test_titles_are_professional_and_quarterly_periods_use_seasons(self):
        catalog = statistical_center_catalog({
            "classification": "all",
            "lifecycle": "all",
            "frequency": "quarterly",
            "page_size": "50",
        })
        selected = catalog["indicators"][0]

        self.assertNotIn("جدول", selected["display_title_fa"])
        self.assertNotIn("به تفکیک فصل", selected["display_title_fa"])
        self.assertRegex(selected["last_available_label_fa"], r"^(بهار|تابستان|پاییز|زمستان) [۰-۹]{4}$")

        payload = statistical_center_series(selected["series_key"])
        labels = [point["period_label_fa"] for point in payload["indicator"]["series"]]
        self.assertTrue(all(re.match(r"^(بهار|تابستان|پاییز|زمستان) [۰-۹]{4}$", label) for label in labels))
        self.assertEqual(payload["indicator"]["title_fa"], selected["title_fa"])

    def test_professional_title_removes_source_header_noise_but_keeps_dimensions(self):
        catalog = statistical_center_catalog({
            "classification": "all",
            "lifecycle": "all",
            "frequency": "quarterly",
            "economic_group": "نهاده‌ها و مصالح ساختمان",
            "page_size": "10",
        })
        title = catalog["indicators"][0]["display_title_fa"]

        self.assertNotIn("جدول", title)
        self.assertNotIn("بهار 1405", title)
        self.assertIn(" — ", title)

        inflation = statistical_center_catalog({
            "classification": "all",
            "lifecycle": "all",
            "economic_group": "شاخص قیمت مصرف‌کننده روستایی",
            "q": "نرخ تورم دوازده ماهه",
            "page_size": "10",
        })["indicators"][0]["display_title_fa"]
        self.assertTrue(inflation.startswith("نرخ تورم سالانه "))
        self.assertNotIn("درصد تغییر شاخص", inflation)

    def test_requested_professional_inflation_title_templates(self):
        items = statistical_center_dataset()["items"]
        producer = next(
            item for item in items
            if "درصد تغییرات شاخص قیمت تولیدکننده کل فصل جاری" in item["title_fa"]
            and "تولید، انتقال و توزیع برق" in item["title_fa"]
        )
        decile = next(
            item for item in items
            if "درصد تغییر تورم نقطه به نقطه شاخص قیمت خوراکیها" in item["title_fa"]
            and item["title_fa"].endswith("دهک اول")
        )
        building = next(
            item for item in items
            if "درصد تغییرات شاخص قیمت نهاده های ساختمان های مسکونی شهر تهران" in item["title_fa"]
            and "چهار فصل منتهی به فصل مورد نظر" in item["title_fa"]
            and item["title_fa"].endswith("زمستان")
        )

        self.assertEqual(
            producer["display_title_fa"],
            "تورم تولیدکننده کل فصل جاری (نقطه‌به‌نقطه) بخش تولید، انتقال و توزیع برق",
        )
        self.assertEqual(
            decile["display_title_fa"],
            "تورم خوراکی‌ها، آشامیدنی‌ها و دخانیات کالاها و خدمات مصرفی (نقطه‌به‌نقطه) دهک اول",
        )
        self.assertEqual(
            building["display_title_fa"],
            "تورم قیمت نهاده‌های ساختمان‌های مسکونی شهر تهران (نقطه‌به‌نقطه) — زمستان",
        )
        self.assertFalse(
            any("درصد تغییرات" in item["display_title_fa"] for item in items),
            "عبارت فنی «درصد تغییرات» نباید در عنوان نمایشی باقی بماند",
        )

    def test_consumer_price_change_titles_use_common_inflation_terms(self):
        items = statistical_center_dataset()["items"]
        hormozgan_rural = next(
            item for item in items
            if item["economic_group"] == "شاخص قیمت مصرف‌کننده روستایی"
            and "نسبت به ماه مشابه سال قبل" in item["title_fa"]
            and item["title_fa"].endswith("هرمزگان")
        )
        self.assertEqual(
            hormozgan_rural["display_title_fa"],
            "تورم نقطه‌به‌نقطه خانوارهای روستایی — هرمزگان",
        )
        consumer_items = [
            item for item in items
            if item["economic_group"] in {
                "شاخص قیمت مصرف‌کننده روستایی",
                "شاخص قیمت مصرف‌کننده شهری",
                "تورم و شاخص قیمت به تفکیک دهک",
            }
        ]
        self.assertFalse(
            any(item["display_title_fa"].startswith("درصد تغییر") for item in consumer_items),
            "عنوان نمایشی شاخص‌های تورمی باید از واژه‌های رایج تورم استفاده کند",
        )
        self.assertFalse(
            any(item["display_title_fa"].startswith("درصد تغییر") for item in items),
            "هیچ شاخص تورمی نباید با عبارت فنی «درصد تغییر» نمایش داده شود",
        )


class StatisticalCenterApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="statistical-center-user")
        self.client.force_login(self.user)

    def test_catalog_and_series_endpoints(self):
        catalog_response = self.client.get("/api/statistical-center-indicators")
        self.assertEqual(catalog_response.status_code, 200)
        self.assertIn("amar_mcp_series", catalog_response.json())
        self.assertIsInstance(catalog_response.json()["amar_mcp_series"], list)
        selected = catalog_response.json()["indicators"][0]

        series_response = self.client.get(
            "/api/statistical-center-series",
            {"series_key": selected["series_key"]},
        )
        self.assertEqual(series_response.status_code, 200)
        self.assertEqual(series_response.json()["indicator"]["series_key"], selected["series_key"])
        self.assertEqual(series_response.headers["Cache-Control"], "no-store")

    def test_api_rejects_bad_page_and_requires_authentication(self):
        response = self.client.get("/api/statistical-center-indicators?page_size=500")
        self.assertEqual(response.status_code, 422)

        self.client.logout()
        self.assertEqual(self.client.get("/api/statistical-center-indicators").status_code, 403)
        self.assertEqual(self.client.get("/api/statistical-center-series?series_key=x").status_code, 403)
