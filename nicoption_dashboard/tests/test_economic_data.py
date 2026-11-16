from __future__ import annotations

import csv
import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import pandas as pd
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from bambo_bot.dates import jalali_to_gregorian
from nicoption_dashboard.economic_data import (
    ConcurrentImportError,
    FinpyTSEClient,
    GoogleSheetsClient,
    PriceTodayClient,
    import_rows,
    ingestion_lock,
    normalize_and_validate_rows,
    parse_decimal,
    parse_period_date,
)
from nicoption_dashboard.economic_api import _derived_indicators
from nicoption_dashboard.models import (
    AccountPreference,
    DataIssue,
    DataSource,
    EconomicIndicator,
    IndicatorObservation,
    IndicatorSource,
    IngestionRun,
)


def jalali_date(year: int, month: int, day: int = 1) -> date:
    return date(*jalali_to_gregorian(year, month, day))


class EconomicFixtureMixin:
    def setUp(self):
        super().setUp()
        self.indicator = EconomicIndicator.objects.create(
            code="TEST_INDEX", name_fa="شاخص آزمون", name_en="Test Index",
            kind="official", category="macro", frequency="monthly", unit="index",
            stale_after_days=45,
        )
        self.source = DataSource.objects.create(
            name="Test Official Source", organization="Test Organization",
            source_type="official", is_primary=True,
        )
        IndicatorSource.objects.create(
            indicator=self.indicator, source=self.source, priority=1, is_primary=True,
        )

    def row(self, **overrides):
        row = {
            "indicator_code": self.indicator.code,
            "period_date": "2025-01-01",
            "value": "100.25",
            "unit": "index",
            "published_at": "2025-01-10T10:00:00+00:00",
            "original_source": self.source.name,
            "source_url": "https://example.test/data",
            "status": "published",
            "revision": "0",
            "notes": "test fixture only",
            "external_id": "row-1",
        }
        row.update(overrides)
        return row


class EconomicModelTests(EconomicFixtureMixin, TestCase):
    def observation(self, **overrides):
        values = {
            "indicator": self.indicator, "source": self.source,
            "period_date": date(2025, 1, 1), "value": Decimal("0"),
            "unit": "index", "collected_at": timezone.now(), "revision": 0,
            "status": "published", "content_hash": "a" * 64,
        }
        values.update(overrides)
        return IndicatorObservation.objects.create(**values)

    def test_indicator_code_is_unique_and_immutable(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EconomicIndicator.objects.create(
                    code=self.indicator.code, name_fa="x", name_en="x",
                    kind="official", category="macro", frequency="daily",
                )
        self.indicator.code = "CHANGED"
        with self.assertRaisesMessage(Exception, "قابل تغییر نیست"):
            self.indicator.save()

    def test_zero_is_preserved_as_decimal(self):
        observation = self.observation()
        observation.refresh_from_db()
        self.assertEqual(observation.value, Decimal("0"))

    def test_revision_and_single_current_constraints(self):
        self.observation()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.observation(content_hash="b" * 64)

    def test_published_at_is_really_nullable(self):
        self.assertIsNone(self.observation().published_at)

    def test_expected_series_indexes_exist(self):
        names = {index.name for index in IndicatorObservation._meta.indexes}
        self.assertIn("econ_obs_series_idx", names)
        self.assertIn("econ_obs_current_idx", names)


class EconomicSeedTests(TestCase):
    def test_seed_is_idempotent_has_no_observations_and_preserves_edits(self):
        call_command("seed_economic_indicators", stdout=StringIO())
        indicator = EconomicIndicator.objects.get(code="IR_M2")
        indicator.definition = "manual definition"
        indicator.save()
        call_command("seed_economic_indicators", stdout=StringIO())
        self.assertEqual(EconomicIndicator.objects.count(), 10)
        self.assertEqual(IndicatorObservation.objects.count(), 0)
        self.assertEqual(EconomicIndicator.objects.get(code="IR_M2").definition, "manual definition")
        usd = EconomicIndicator.objects.get(code="IR_USD_FREE_MARKET")
        self.assertEqual((usd.kind, usd.frequency), ("analytical", "monthly"))
        self.assertEqual(usd.source_links.get(is_primary=True).source.name, "PriceToDay")
        tedpix = EconomicIndicator.objects.get(code="IR_TEDPIX")
        self.assertEqual((tedpix.kind, tedpix.frequency), ("official", "monthly"))
        self.assertEqual(tedpix.source_links.get(is_primary=True).source.name, "TSETMC via FinPy-TSE")


class EconomicNormalizationTests(EconomicFixtureMixin, TestCase):
    def test_decimal_normalization(self):
        self.assertEqual(parse_decimal("۱۲۳٬۴۵۶٫۷۸"), Decimal("123456.78"))
        self.assertEqual(parse_decimal("١٢٣٬٤٥٦٫٧٨"), Decimal("123456.78"))
        self.assertEqual(parse_decimal("-1,234.5"), Decimal("-1234.5"))
        self.assertEqual(parse_decimal("0"), Decimal("0"))
        self.assertIsNone(parse_decimal(" "))
        for invalid in ("NaN", "Infinity", "not-a-number"):
            with self.assertRaises(ValueError):
                parse_decimal(invalid)

    def test_period_date_requires_unambiguous_iso(self):
        self.assertEqual(parse_period_date("2025-01-02"), date(2025, 1, 2))
        for invalid in ("1403/01/02", "01/02/03", "2025-13-01", ""):
            with self.assertRaises(ValueError):
                parse_period_date(invalid)

    def test_headers_are_case_insensitive_and_trimmed(self):
        row = {f" {key.upper()} ": value for key, value in self.row().items()}
        normalized, summary = normalize_and_validate_rows([row])
        self.assertEqual(len(normalized), 1)
        self.assertEqual(summary.rejected, 0)

    def test_invalid_url_status_unit_and_unknown_indicator_are_reported(self):
        rows = [
            self.row(source_url="javascript:alert(1)"),
            self.row(status="final"),
            self.row(unit="percent"),
            self.row(indicator_code="UNKNOWN"),
        ]
        _, summary = normalize_and_validate_rows(rows)
        codes = {issue.code for issue in summary.issues}
        self.assertTrue({"invalid_url", "invalid_status", "unit_mismatch", "unknown_indicator"}.issubset(codes))
        self.assertEqual(summary.rejected, 4)


class EconomicImportTests(EconomicFixtureMixin, TestCase):
    def test_insert_duplicate_and_revision_are_idempotent(self):
        first = import_rows([self.row()], channel="csv")
        second = import_rows([self.row()], channel="csv")
        changed = import_rows([self.row(value="101.50")], channel="csv")
        self.assertEqual((first.inserted, second.unchanged, changed.revised), (1, 1, 1))
        observations = IndicatorObservation.objects.order_by("revision")
        self.assertEqual(list(observations.values_list("revision", flat=True)), [0, 1])
        self.assertEqual(list(observations.values_list("is_current_revision", flat=True)), [False, True])
        self.assertEqual(observations.last().supersedes_id, observations.first().pk)

    def test_dry_run_writes_nothing(self):
        summary = import_rows([self.row()], channel="csv", dry_run=True)
        self.assertEqual(summary.inserted, 1)
        self.assertEqual(IndicatorObservation.objects.count(), 0)
        self.assertEqual(IngestionRun.objects.count(), 0)

    def test_non_strict_import_keeps_valid_rows_and_records_safe_issue(self):
        summary = import_rows([self.row(), self.row(indicator_code="UNKNOWN", external_id="bad")], channel="csv")
        self.assertEqual((summary.inserted, summary.rejected), (1, 1))
        self.assertEqual(summary.run.status, IngestionRun.Status.PARTIAL)
        issue = DataIssue.objects.get(issue_code="unknown_indicator")
        self.assertNotIn("value", issue.safe_payload)
        self.assertNotIn("credential", str(issue.safe_payload).lower())

    def test_strict_import_rolls_back_all_observations(self):
        with self.assertRaises(CommandError):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "strict.csv"
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(self.row()))
                    writer.writeheader()
                    writer.writerow(self.row())
                    writer.writerow(self.row(indicator_code="UNKNOWN"))
                call_command("import_economic_csv", str(path), "--strict", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(IndicatorObservation.objects.count(), 0)
        self.assertEqual(IngestionRun.objects.get().status, IngestionRun.Status.FAILED)

    def test_utf8_bom_csv_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(self.row()))
                writer.writeheader()
                writer.writerow(self.row())
            output = StringIO()
            call_command("import_economic_csv", str(path), stdout=output)
        self.assertIn("inserted=1", output.getvalue())

    def test_concurrent_import_lock_is_rejected(self):
        with ingestion_lock():
            with self.assertRaises(ConcurrentImportError):
                with ingestion_lock():
                    pass

    def test_import_query_count_does_not_scale_per_row(self):
        rows = [
            self.row(
                period_date=f"2025-01-{day:02d}",
                value=str(100 + day),
                external_id=f"row-{day}",
            )
            for day in range(1, 21)
        ]
        with CaptureQueriesContext(connection) as queries:
            summary = import_rows(rows, channel="csv")
        self.assertEqual(summary.inserted, 20)
        self.assertLessEqual(len(queries), 16)


class EconomicApiTests(EconomicFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username="economic-user", password="test-password")
        AccountPreference.objects.create(owner=self.user)
        self.client.force_login(self.user)

    def create_observation(self, period_date, value, revision=0, current=True):
        return IndicatorObservation.objects.create(
            indicator=self.indicator, source=self.source, period_date=period_date,
            value=Decimal(value), unit="index", published_at=timezone.now(),
            collected_at=timezone.now(), revision=revision, status="published",
            source_url="https://example.test/data", content_hash=f"{period_date}-{revision}",
            is_current_revision=current,
        )

    def test_api_current_series_change_provenance_and_query_count(self):
        self.create_observation(timezone.localdate() - timedelta(days=60), "100")
        self.create_observation(timezone.localdate() - timedelta(days=30), "110")
        # One query verifies the account's email gate before feature/data access.
        with self.assertNumQueries(8):
            response = self.client.get("/api/economic-indicators")
        self.assertEqual(response.status_code, 200)
        item = response.json()["indicators"][0]
        self.assertEqual([point["value"] for point in item["series"]], ["100.000000000000", "110.000000000000"])
        self.assertRegex(item["current"]["period_date_jalali"], r"^\d{4}/\d{2}/\d{2}$")
        self.assertRegex(item["series"][-1]["period_date_jalali"], r"^\d{4}/\d{2}/\d{2}$")
        self.assertEqual(item["current"]["previous_value"], "100.000000000000")
        self.assertEqual(item["current"]["change"], "10.000000000000")
        self.assertEqual(item["current"]["change_percent"], "10.0")
        self.assertEqual(item["source"]["name"], self.source.name)

    def test_previous_zero_does_not_invent_percentage(self):
        self.create_observation(timezone.localdate() - timedelta(days=2), "0")
        self.create_observation(timezone.localdate() - timedelta(days=1), "1")
        current = self.client.get("/api/economic-indicators").json()["indicators"][0]["current"]
        self.assertEqual(current["change"], "1.000000000000")
        self.assertIsNone(current["change_percent"])

    def test_cpi_point_to_point_inflation_is_calculated_from_same_month_last_year(self):
        EconomicIndicator.objects.create(
            code="IR-INF", name_fa="تورم مصرف‌کننده", name_en="Consumer Inflation",
            kind="official", category="macro", frequency="monthly", unit="درصد",
        )
        cpi = EconomicIndicator.objects.create(
            code="IR_CPI", name_fa="شاخص قیمت مصرف‌کننده", name_en="Consumer Price Index",
            kind="official", category="macro", frequency="monthly", unit="واحد",
        )
        IndicatorSource.objects.create(indicator=cpi, source=self.source, priority=1, is_primary=True)
        for period, value in (
            (date(2025, 8, 1), "200"),
            (date(2025, 9, 1), "250"),
            (date(2026, 8, 1), "220"),
            (date(2026, 9, 1), "300"),
        ):
            IndicatorObservation.objects.create(
                indicator=cpi, source=self.source, period_date=period,
                value=Decimal(value), unit=cpi.unit, published_at=timezone.now(),
                collected_at=timezone.now(), status="published",
                content_hash=f"cpi-{period}",
            )

        indicators = self.client.get("/api/economic-indicators").json()["indicators"]
        item = next(item for item in indicators if item["code"] == "IR-INF")
        monthly = next(item for item in indicators if item["code"] == "IR-INF_MOM")
        current = item["current"]

        self.assertEqual(item["unit"], "درصد")
        self.assertEqual(item["kind"], "analytical")
        self.assertEqual(item["methodology"]["inputs"], ["IR_CPI"])
        self.assertEqual(current["value"], "20.000000000000")
        self.assertEqual(current["previous_value"], "10.000000000000")
        self.assertEqual(current["change"], "10.000000000000")
        self.assertEqual(item["methodology"]["primary_rate"], "yoy")
        self.assertEqual(
            [point["value"] for point in item["series"]],
            ["10.000000000000", "20.000000000000"],
        )
        self.assertEqual(monthly["name_fa"], "تورم مصرف‌کننده ماهانه")
        self.assertEqual(monthly["current"]["value"], "36.363636363636")
        self.assertEqual(monthly["methodology"]["primary_rate"], "mom")
        raw_cpi = next(item for item in indicators if item["code"] == "IR_CPI")
        self.assertEqual(raw_cpi["unit"], "واحد")
        self.assertEqual(raw_cpi["current"]["value"], "300.000000000000")

    def test_cpi_point_to_point_is_null_without_a_valid_prior_year_value(self):
        EconomicIndicator.objects.create(
            code="IR-INF", name_fa="تورم مصرف‌کننده", name_en="Consumer Inflation",
            kind="official", category="macro", frequency="monthly", unit="درصد",
        )
        cpi = EconomicIndicator.objects.create(
            code="IR_CPI", name_fa="شاخص قیمت مصرف‌کننده", name_en="Consumer Price Index",
            kind="official", category="macro", frequency="monthly", unit="واحد",
        )
        IndicatorSource.objects.create(indicator=cpi, source=self.source, priority=1, is_primary=True)
        IndicatorObservation.objects.create(
            indicator=cpi, source=self.source, period_date=date(2026, 9, 1),
            value=Decimal("300"), unit=cpi.unit, collected_at=timezone.now(),
            status="published", content_hash="cpi-without-prior",
        )

        indicators = self.client.get("/api/economic-indicators").json()["indicators"]
        item = next(item for item in indicators if item["code"] == "IR-INF")
        current = item["current"]

        self.assertEqual(item["unit"], "درصد")
        self.assertIsNone(current["value"])
        self.assertEqual(item["series"], [])

    def test_superseded_and_older_than_five_years_are_not_exposed(self):
        old = self.create_observation(timezone.localdate().replace(year=timezone.localdate().year - 6), "50")
        superseded = self.create_observation(timezone.localdate() - timedelta(days=1), "90", current=False)
        current = self.create_observation(timezone.localdate() - timedelta(days=1), "100", revision=1)
        current.supersedes = superseded
        current.save(update_fields=("supersedes",))
        series = self.client.get("/api/economic-indicators").json()["indicators"][0]["series"]
        self.assertEqual([point["value"] for point in series], ["100.000000000000"])
        self.assertNotIn(old.period_date.isoformat(), {point["period_date"] for point in series})

    def test_full_history_requires_real_entitlement_even_for_staff(self):
        self.user.is_staff = True
        self.user.save(update_fields=("is_staff",))
        response = self.client.get("/api/economic-indicators?range=all")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "full_history_subscription_required")

    def test_economic_data_permission_is_enforced_by_api(self):
        preferences = AccountPreference.objects.get(owner=self.user)
        preferences.show_economic_data = False
        preferences.save(update_fields=("show_economic_data",))
        self.assertEqual(self.client.get("/api/economic-indicators").status_code, 403)

    def test_stale_status_uses_indicator_policy(self):
        self.indicator.stale_after_days = 1
        self.indicator.frequency = "daily"
        self.indicator.save(update_fields=("stale_after_days", "frequency"))
        self.create_observation(timezone.localdate() - timedelta(days=3), "100")
        item = self.client.get("/api/economic-indicators").json()["indicators"][0]
        self.assertEqual(item["freshness"]["status"], "stale")

    def test_derived_monetary_metrics_use_decimal_and_matching_periods(self):
        def raw(code, name, values):
            return {
                "code": code,
                "name_fa": name,
                "source": {"name": "بانک مرکزی", "url": "https://example.test"},
                "series": [
                    {
                        "period_date": period.isoformat(), "value": value,
                        "published_at": None, "collected_at": "2026-04-01T00:00:00+00:00",
                        "revision": 0, "status": "published",
                    }
                    for period, value in values
                ],
            }

        payload = _derived_indicators({
            "IR_MONETARY_BASE": raw("IR_MONETARY_BASE", "پایه پولی", [
                (date(2025, 3, 1), "100"), (date(2026, 2, 1), "120"),
                (date(2026, 3, 1), "125"),
            ]),
            "IR_M2": raw("IR_M2", "نقدینگی", [
                (date(2025, 3, 1), "600"), (date(2026, 2, 1), "720"),
                (date(2026, 3, 1), "750"),
            ]),
            "IR_MONEY": raw("IR_MONEY", "پول", [
                (date(2026, 3, 1), "150"),
            ]),
            "IR_USD_FREE_MARKET": raw("IR_USD_FREE_MARKET", "قیمت دلار بازار آزاد", [
                (jalali_date(1403, 12), "100"), (jalali_date(1404, 11), "120"),
                (jalali_date(1404, 12), "150"),
            ]),
            "IR_COIN_BAHAR_AZADI": raw("IR_COIN_BAHAR_AZADI", "قیمت سکه بهار آزادی", [
                (jalali_date(1403, 12), "200"), (jalali_date(1404, 11), "240"),
                (jalali_date(1404, 12), "300"),
            ]),
            "IR_GOLD_18K": raw("IR_GOLD_18K", "قیمت طلای ۱۸ عیار", [
                (jalali_date(1403, 12), "400"), (jalali_date(1404, 11), "500"),
                (jalali_date(1404, 12), "600"),
            ]),
            "IR_TETHER": raw("IR_TETHER", "قیمت تتر", [
                (jalali_date(1403, 12), "100"), (jalali_date(1404, 11), "125"),
                (jalali_date(1404, 12), "150"),
            ]),
            "IR_TEDPIX": {
                **raw("IR_TEDPIX", "شاخص کل بورس تهران", [
                    (jalali_date(1403, 12), "2000000"), (jalali_date(1404, 11), "2400000"),
                    (jalali_date(1404, 12), "3000000"),
                ]),
                "category": "capital",
            },
        })
        by_code = {item["code"]: item for item in payload}

        self.assertEqual(by_code["IR_MONETARY_BASE_YOY_GROWTH"]["current"]["value"], "25.000000000000")
        self.assertEqual(by_code["IR_M2_YOY_GROWTH"]["current"]["value"], "25.000000000000")
        self.assertEqual(by_code["IR_MONETARY_BASE_MOM_GROWTH"]["current"]["value"], "4.166666666667")
        self.assertEqual(by_code["IR_M2_MOM_GROWTH"]["current"]["value"], "4.166666666667")
        self.assertEqual(by_code["IR_MONETARY_BASE_MOM_GROWTH"]["methodology"]["primary_rate"], "mom")
        self.assertEqual(by_code["IR_M2_YOY_GROWTH"]["methodology"]["primary_rate"], "yoy")
        self.assertEqual(by_code["IR_USD_FREE_MARKET_YOY_CHANGE"]["current"]["value"], "50.000000000000")
        self.assertEqual(by_code["IR_USD_FREE_MARKET_MOM_CHANGE"]["current"]["value"], "25.000000000000")
        self.assertEqual(by_code["IR_USD_FREE_MARKET_MOM_CHANGE"]["unit"], "درصد")
        self.assertEqual(by_code["IR_USD_FREE_MARKET_MOM_CHANGE"]["name_fa"], "رشد ماهانه قیمت دلار بازار آزاد")
        self.assertEqual(by_code["IR_COIN_BAHAR_AZADI_YOY_CHANGE"]["current"]["value"], "50.000000000000")
        self.assertEqual(by_code["IR_COIN_BAHAR_AZADI_MOM_CHANGE"]["current"]["value"], "25.000000000000")
        self.assertEqual(by_code["IR_COIN_BAHAR_AZADI_YOY_CHANGE"]["unit"], "درصد")
        self.assertEqual(by_code["IR_GOLD_18K_YOY_CHANGE"]["current"]["value"], "50.000000000000")
        self.assertEqual(by_code["IR_GOLD_18K_MOM_CHANGE"]["current"]["value"], "20.000000000000")
        self.assertEqual(by_code["IR_GOLD_18K_MOM_CHANGE"]["unit"], "درصد")
        self.assertEqual(by_code["IR_TETHER_YOY_CHANGE"]["current"]["value"], "50.000000000000")
        self.assertEqual(by_code["IR_TETHER_MOM_CHANGE"]["current"]["value"], "20.000000000000")
        self.assertEqual(by_code["IR_TETHER_MOM_CHANGE"]["methodology"]["calendar"], "solar_hijri")
        self.assertEqual(by_code["IR_TEDPIX_YOY_CHANGE"]["current"]["value"], "50.000000000000")
        self.assertEqual(by_code["IR_TEDPIX_MOM_CHANGE"]["current"]["value"], "25.000000000000")
        self.assertEqual(by_code["IR_TEDPIX_MOM_CHANGE"]["category"], "capital")
        self.assertEqual(by_code["IR_TEDPIX_MOM_CHANGE"]["methodology"]["calendar"], "solar_hijri")
        self.assertEqual(by_code["IR_MONEY_MULTIPLIER"]["current"]["value"], "6.000000000000")
        self.assertEqual(by_code["IR_QUASI_MONEY_TO_MONEY"]["current"]["value"], "4.000000000000")
        self.assertEqual(by_code["IR_M2_YOY_GROWTH"]["methodology"]["inputs"], ["IR_M2"])

    def test_supporting_money_series_is_not_exposed_as_a_raw_card(self):
        money = EconomicIndicator.objects.create(
            code="IR_MONEY", name_fa="پول", name_en="Money", kind="official",
            category="macro", frequency="monthly", unit="هزار میلیارد ریال",
        )
        IndicatorSource.objects.create(indicator=money, source=self.source, priority=1)
        IndicatorObservation.objects.create(
            indicator=money, source=self.source, period_date=timezone.localdate(),
            value=Decimal("10"), unit=money.unit, collected_at=timezone.now(),
            status="published", content_hash="money-current",
        )

        codes = {item["code"] for item in self.client.get("/api/economic-indicators").json()["indicators"]}

        self.assertNotIn("IR_MONEY", codes)


class EconomicFreshnessTests(EconomicFixtureMixin, TestCase):
    def test_freshness_command_deduplicates_and_resolves_issues(self):
        call_command("check_economic_data_freshness", stdout=StringIO())
        call_command("check_economic_data_freshness", stdout=StringIO())
        self.assertEqual(DataIssue.objects.filter(issue_code="missing_data", resolved_at=None).count(), 1)
        IndicatorObservation.objects.create(
            indicator=self.indicator, source=self.source, period_date=timezone.localdate(),
            value=Decimal("1"), unit="index", collected_at=timezone.now(),
            status="published", content_hash="fresh",
        )
        call_command("check_economic_data_freshness", stdout=StringIO())
        self.assertFalse(DataIssue.objects.filter(issue_code="missing_data", resolved_at=None).exists())


class GoogleSheetsClientTests(TestCase):
    @patch("nicoption_dashboard.economic_data.time.sleep", return_value=None)
    def test_retry_timeout_and_rows_without_logging_credentials(self, _sleep):
        client = GoogleSheetsClient.__new__(GoogleSheetsClient)
        client.timeout = 9
        client.retries = 1
        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {"values": [["indicator_code", "value"], ["TEST", "1"]]}
        client.session = Mock()
        client.session.get.side_effect = [requests.Timeout("secret-token"), success]
        rows = list(client.rows("sheet-id", "Data!A:B"))
        self.assertEqual(rows, [{"indicator_code": "TEST", "value": "1"}])
        self.assertEqual(client.session.get.call_args.kwargs["timeout"], 9)

    def test_google_command_fails_cleanly_without_credentials(self):
        with override_settings(ECONOMIC_GOOGLE_TIMEOUT_SECONDS=1, ECONOMIC_GOOGLE_RETRIES=0):
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaisesMessage(CommandError, "GOOGLE_SERVICE_ACCOUNT_FILE"):
                    call_command("sync_economic_google_sheet", stdout=StringIO(), stderr=StringIO())


class PriceTodayClientTests(TestCase):
    def test_daily_duplicates_are_reduced_to_last_valid_monthly_price(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": True,
            "result": [
                {"price": 100, "time": "2025-01-10T00:00:00.000Z"},
                {"price": 101, "time": "2025-01-10T00:00:00.000Z"},
                {"price": 110, "time": "2025-01-31T00:00:00.000Z"},
                {"price": 120, "time": "2025-02-27T00:00:00.000Z"},
            ],
        }
        session = Mock()
        session.get.return_value = response
        rows, quality = PriceTodayClient(timeout=9, retries=0, session=session).monthly_rows(
            slug="usd", indicator_code="IR_USD_FREE_MARKET",
            source_name="PriceToDay", unit="ریال", from_date=date(2025, 1, 1),
        )

        self.assertEqual(
            [row["period_date"] for row in rows],
            ["2024-12-21", "2025-01-20", "2025-02-19"],
        )
        self.assertEqual([row["value"] for row in rows], ["101", "110", "120"])
        self.assertEqual(
            [row["external_id"] for row in rows],
            [
                "pricetoday:usd:jalali:1403-10",
                "pricetoday:usd:jalali:1403-11",
                "pricetoday:usd:jalali:1403-12",
            ],
        )
        self.assertEqual(quality, {"raw_rows": 4, "unique_days": 3, "duplicate_days": 1, "monthly_rows": 3})
        self.assertEqual(session.get.call_args.kwargs["timeout"], 9)

    def test_norouz_boundary_is_split_into_two_solar_hijri_months(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": True,
            "result": [
                {"price": 100, "time": "2025-03-20T00:00:00.000Z"},
                {"price": 110, "time": "2025-03-21T00:00:00.000Z"},
            ],
        }
        session = Mock()
        session.get.return_value = response

        rows, _ = PriceTodayClient(timeout=9, retries=0, session=session).monthly_rows(
            slug="usd", indicator_code="IR_USD_FREE_MARKET",
            source_name="PriceToDay", unit="ریال", from_date=date(2025, 3, 1),
        )

        self.assertEqual([row["period_date"] for row in rows], ["2025-02-19", "2025-03-21"])
        self.assertEqual([row["value"] for row in rows], ["100", "110"])
        self.assertIn("دوره 1403/12", rows[0]["notes"])
        self.assertIn("دوره 1404/01", rows[1]["notes"])

    def test_invalid_or_unsuccessful_payload_is_rejected(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"success": False, "result": []}
        session = Mock()
        session.get.return_value = response
        client = PriceTodayClient(retries=0, session=session)
        with self.assertRaisesMessage(ValueError, "successful result list"):
            client.monthly_rows(
                slug="usd", indicator_code="IR_USD_FREE_MARKET",
                source_name="PriceToDay", unit="ریال", from_date=date(2025, 1, 1),
            )


class FinpyTSEClientTests(TestCase):
    def test_daily_tedpix_is_reduced_to_last_valid_solar_hijri_monthly_close(self):
        frame = pd.DataFrame({
            "Date": pd.to_datetime([
                "2025-03-20", "2025-03-21", "2025-04-19", "2025-04-21",
            ]),
            "Adj Close": [2_000_000, 2_100_000, 2_200_000, 2_300_000],
        })
        loader = Mock(return_value=frame)

        rows, quality = FinpyTSEClient(retries=0, history_loader=loader).monthly_rows(
            from_date=date(2025, 3, 1),
            to_date=date(2025, 4, 30),
        )

        self.assertEqual([row["period_date"] for row in rows], ["2025-02-19", "2025-03-21", "2025-04-21"])
        self.assertEqual([row["value"] for row in rows], ["2000000", "2200000", "2300000"])
        self.assertEqual(
            [row["external_id"] for row in rows],
            [
                "finpy-tse:tedpix:jalali:1403-12",
                "finpy-tse:tedpix:jalali:1404-01",
                "finpy-tse:tedpix:jalali:1404-02",
            ],
        )
        self.assertEqual(quality, {"raw_rows": 4, "unique_days": 4, "duplicate_days": 0, "monthly_rows": 3})
        loader.assert_called_once_with(
            start_date="1403-12-11",
            end_date="1404-02-10",
            ignore_date=False,
            just_adj_close=True,
            show_weekday=False,
            double_date=True,
        )

    def test_invalid_finpy_tse_frame_is_rejected(self):
        client = FinpyTSEClient(retries=0, history_loader=Mock(return_value=pd.DataFrame({"Date": []})))
        with self.assertRaisesMessage(ValueError, "missing Date or Adj Close"):
            client.monthly_rows(from_date=date(2025, 1, 1), to_date=date(2025, 2, 1))

    @patch("nicoption_dashboard.management.commands.sync_economic_finpy_tse.FinpyTSEClient.monthly_rows")
    def test_sync_command_persists_tedpix_without_partial_fetch(self, monthly_rows):
        call_command("seed_economic_indicators", stdout=StringIO())
        monthly_rows.return_value = ([{
            "indicator_code": "IR_TEDPIX",
            "period_date": "2025-03-21",
            "value": "2500000",
            "unit": "واحد",
            "published_at": "2025-04-19T00:00:00+03:30",
            "original_source": "TSETMC via FinPy-TSE",
            "source_url": FinpyTSEClient.SOURCE_URL,
            "status": "published",
            "revision": "",
            "notes": "test",
            "external_id": "finpy-tse:tedpix:jalali:1404-01",
        }], {"raw_rows": 1, "unique_days": 1, "duplicate_days": 0, "monthly_rows": 1})

        call_command(
            "sync_economic_finpy_tse",
            "--from", "2025-03-01",
            "--to", "2025-04-30",
            "--strict",
            stdout=StringIO(),
        )

        observation = IndicatorObservation.objects.get(indicator__code="IR_TEDPIX")
        self.assertEqual(observation.value, Decimal("2500000"))
        self.assertEqual(observation.source.name, "TSETMC via FinPy-TSE")
        self.assertEqual(observation.external_id, "finpy-tse:tedpix:jalali:1404-01")
