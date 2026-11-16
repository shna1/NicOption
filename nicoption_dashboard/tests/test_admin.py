from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from nicoption_dashboard.models import (
    DataSource,
    EconomicIndicator,
    IndicatorObservation,
    IndicatorSource,
    IngestionRun,
)


class GlobalAdminAccessTests(TestCase):
    def test_superuser_can_open_user_management(self):
        admin_user = get_user_model().objects.create_superuser(
            username="global-admin",
            password="test-password",
        )
        self.client.force_login(admin_user)

        response = self.client.get("/admin/auth/user/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مدیریت کل nicoption")

    def test_superuser_can_set_page_access_on_user_change_page(self):
        admin_user = get_user_model().objects.create_superuser(
            username="global-admin",
            password="test-password",
        )
        managed_user = get_user_model().objects.create_user(username="managed-user")
        self.client.force_login(admin_user)

        response = self.client.get(f"/admin/auth/user/{managed_user.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دسترسی به بخش‌های سایت")
        self.assertContains(response, "دسترسی‌های اصلی")
        self.assertContains(response, "بازار آپشن")
        self.assertContains(response, "داده‌های اقتصادی")
        self.assertContains(response, "مقالات")
        self.assertContains(response, "نمایش جریان سفارشات")
        self.assertContains(response, "نمایش بورس کالا")

    def test_regular_staff_user_cannot_manage_users(self):
        staff_user = get_user_model().objects.create_user(
            username="limited-staff",
            password="test-password",
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get("/admin/auth/user/")

        self.assertEqual(response.status_code, 403)


class EconomicDataUpdateAdminTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="economic-admin",
            password="test-password",
        )
        self.indicator = EconomicIndicator.objects.create(
            code="TEST_CPI",
            name_fa="شاخص آزمایشی",
            name_en="Test CPI",
            kind=EconomicIndicator.Kind.OFFICIAL,
            category=EconomicIndicator.Category.MACRO,
            frequency=EconomicIndicator.Frequency.MONTHLY,
            unit="واحد",
        )
        self.source = DataSource.objects.create(
            name="مرکز آمار آزمایشی",
            organization="مرکز آزمایشی",
            source_type=DataSource.SourceType.OFFICIAL,
            is_primary=True,
        )
        IndicatorSource.objects.create(
            indicator=self.indicator,
            source=self.source,
            is_primary=True,
        )
        self.url = reverse(
            "admin:nicoption_dashboard_ingestionrun_data_update"
        )
        self.client.force_login(self.admin_user)

    def test_superuser_can_open_economic_data_update_panel(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بروزرسانی داده‌های اقتصادی")
        self.assertContains(response, "ورود یک مقدار")
        self.assertContains(response, "ورود گروهی CSV")

    def test_manual_value_is_previewed_then_committed(self):
        period = timezone.localdate().replace(day=1)
        preview_response = self.client.post(
            self.url,
            {
                "action": "preview_manual",
                "manual-indicator": self.indicator.pk,
                "manual-source": self.source.pk,
                "manual-period_date": period.isoformat(),
                "manual-value": "۱۲۳٫۵",
                "manual-published_at": "",
                "manual-status": IndicatorObservation.Status.PUBLISHED,
                "manual-source_url": "https://example.com/release",
                "manual-external_id": "release-1",
                "manual-notes": "ورود از پنل مدیریت",
            },
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(IndicatorObservation.objects.count(), 0)
        preview = preview_response.context["preview"]
        self.assertEqual(preview["summary"].inserted, 1)
        self.assertTrue(preview["can_commit"])

        commit_response = self.client.post(
            self.url,
            {
                "action": "commit_preview",
                "preview_token": preview["token"],
            },
        )

        self.assertEqual(commit_response.status_code, 302)
        observation = IndicatorObservation.objects.get()
        self.assertEqual(str(observation.value), "123.500000000000")
        run = IngestionRun.objects.get()
        self.assertEqual(run.channel, IngestionRun.Channel.MANUAL)
        self.assertEqual(run.created_by, self.admin_user)
        self.assertEqual(run.rows_inserted, 1)

    def test_csv_errors_block_strict_commit(self):
        period = timezone.localdate().replace(day=1).isoformat()
        content = (
            "indicator_code,period_date,value,unit,original_source\n"
            f"UNKNOWN,{period},10,واحد,{self.source.name}\n"
        ).encode("utf-8")

        response = self.client.post(
            self.url,
            {
                "action": "preview_csv",
                "csv-strict": "on",
                "csv-file": SimpleUploadedFile(
                    "economic.csv", content, content_type="text/csv"
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["preview"]["summary"].rejected, 1)
        self.assertFalse(response.context["preview"]["can_commit"])
        self.assertContains(response, "کد شاخص در کاتالوگ فعال پیدا نشد")

        forced_commit = self.client.post(
            self.url,
            {
                "action": "commit_preview",
                "preview_token": response.context["preview"]["token"],
            },
        )
        self.assertEqual(forced_commit.status_code, 302)
        self.assertEqual(IndicatorObservation.objects.count(), 0)
        self.assertEqual(IngestionRun.objects.count(), 0)

    def test_regular_staff_cannot_open_update_panel(self):
        staff = get_user_model().objects.create_user(
            username="economic-staff",
            password="test-password",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
