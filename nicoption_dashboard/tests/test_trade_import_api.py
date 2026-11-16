import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from bambo_bot.dates import format_jalali_date
from bambo_bot.trades import tehran_today
from nicoption_dashboard.models import TradeRecord, UnderlyingPositionRecord
from nicoption_dashboard.trade_imports import parse_trade_csv


OPEN_HEADERS = [
    "استراتژی", "بازار", "دارایی پایه", "نماد اختیار", "تاریخ ورود",
    "تاریخ سررسید", "تعداد کل", "تعداد با هدف اعمال",
    "تعداد نوسان‌گیری پرمیوم", "قیمت پایه ورود", "پرمیوم ورود",
    "قیمت اعمال", "کارمزد ورود",
]

MIXED_OPEN_HEADERS = [
    "نوع موقعیت", "بازار", "دارایی پایه", "نماد اختیار",
    "روش خرید دارایی پایه", "قرارداد منبع اعمال", "تاریخ ورود",
    "تاریخ سررسید", "تعداد کل", "تعداد با هدف اعمال",
    "تعداد نوسان‌گیری پرمیوم", "تعداد اولیه دارایی پایه",
    "تعداد آزاد دارایی پایه", "تعداد تخصیص‌یافته به کاوردکال",
    "قیمت پایه ورود", "قیمت پایه جاری", "پرمیوم ورود", "قیمت اعمال",
    "کارمزد ورود",
]

MIXED_CLOSED_HEADERS = [
    "نوع موقعیت", "بازار", "دارایی پایه", "نماد اختیار",
    "روش خرید دارایی پایه", "قرارداد منبع اعمال", "تاریخ ورود",
    "تاریخ خروج", "روش خروج", "تعداد کل", "تعداد با هدف اعمال",
    "تعداد نوسان‌گیری پرمیوم", "قیمت پایه ورود", "پرمیوم ورود",
    "قیمت اعمال", "قیمت پایه خروج", "قیمت اختیار خروج",
    "روز تا سررسید در ورود", "سود یا زیان قطعی",
    "بازده قطعی (درصد)", "بازده سالانه‌شده (درصد)", "روز نگهداری",
    "کارمزد ورود", "کارمزد خروج", "یادداشت",
]


def open_csv_file(*, invalid=False, duplicate=False, name="open.csv"):
    today = tehran_today()
    row = [
        "خرید اختیار خرید", "بورس کالا", "صندوق طلا", "TESTC100",
        format_jalali_date(today - timedelta(days=10)),
        format_jalali_date(today + timedelta(days=40)),
        "10", "2", "8", "150000", "25000", "100000", "0",
    ]
    if invalid:
        row[10] = "عدد-نامعتبر"
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(OPEN_HEADERS)
    writer.writerow(row)
    if duplicate:
        writer.writerow(row)
    return SimpleUploadedFile(
        name,
        ("\ufeff" + output.getvalue()).encode("utf-8"),
        content_type="text/csv",
    )


def csv_file(headers, rows, *, name):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return SimpleUploadedFile(
        name,
        ("\ufeff" + output.getvalue()).encode("utf-8"),
        content_type="text/csv",
    )


class TradeImportApiV1Tests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="import-user", password="test-password"
        )
        self.client.force_authenticate(self.user)
        self.url = reverse("api-v1:trade-import")

    def test_preview_validates_without_writing(self):
        response = self.client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": False},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "preview")
        self.assertEqual(response.data["valid"], 1)
        self.assertEqual(response.data["invalid"], 0)
        self.assertEqual(response.data["valid_trades"], 1)
        self.assertEqual(response.data["valid_underlyings"], 0)
        self.assertEqual(TradeRecord.objects.count(), 0)

    def test_confirm_imports_and_repeated_file_is_skipped(self):
        first = self.client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": True},
            format="multipart",
        )
        second = self.client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": True},
            format="multipart",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["imported"], 1)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.data["imported"], 0)
        self.assertEqual(second.data["skipped"], 1)
        record = TradeRecord.objects.get()
        self.assertEqual(record.owner, self.user)
        self.assertEqual(record.status, "open")

    def test_same_file_is_isolated_between_users(self):
        self.client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": True},
            format="multipart",
        )
        other = get_user_model().objects.create_user(username="other-import-user")
        self.client.force_authenticate(other)

        response = self.client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": True},
            format="multipart",
        )

        self.assertEqual(response.data["imported"], 1)
        self.assertEqual(TradeRecord.objects.count(), 2)
        self.assertSetEqual(
            set(TradeRecord.objects.values_list("owner_id", flat=True)),
            {self.user.pk, other.pk},
        )

    def test_duplicate_rows_inside_one_file_are_skipped(self):
        response = self.client.post(
            self.url,
            {
                "file": open_csv_file(duplicate=True),
                "status": "open",
                "confirm": True,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["imported"], 1)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(TradeRecord.objects.count(), 1)

    def test_existing_legacy_trade_with_different_id_is_not_imported_again(self):
        parsed = parse_trade_csv(
            open_csv_file(), owner_id=self.user.pk, status="open"
        )
        legacy_payload = dict(parsed.records[0])
        legacy_payload.pop("_record_type")
        legacy_payload.pop("import_fingerprint")
        legacy_payload["id"] = "legacy-trade-id"
        TradeRecord.objects.create(
            id=legacy_payload["id"], owner=self.user,
            status="open", payload=legacy_payload,
        )

        response = self.client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": True},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["imported"], 0)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(TradeRecord.objects.count(), 1)

    def test_existing_underlying_with_different_id_is_not_imported_again(self):
        today = tehran_today()
        row = {
            "نوع موقعیت": "خرید دارایی پایه",
            "بازار": "بورس کالا",
            "دارایی پایه": "طلای 24 عیار",
            "روش خرید دارایی پایه": "خرید مستقیم دارایی پایه",
            "تاریخ ورود": format_jalali_date(today - timedelta(days=10)),
            "تعداد کل": "7",
            "تعداد اولیه دارایی پایه": "7",
            "تعداد آزاد دارایی پایه": "7",
            "تعداد تخصیص‌یافته به کاوردکال": "0",
            "قیمت پایه ورود": "28248990",
            "کارمزد ورود": "0",
        }
        parsed = parse_trade_csv(
            csv_file(MIXED_OPEN_HEADERS, [row], name="base.csv"),
            owner_id=self.user.pk,
            status="open",
        )
        legacy_payload = dict(parsed.records[0])
        legacy_payload.pop("_record_type")
        legacy_payload.pop("import_fingerprint")
        legacy_payload["id"] = "legacy-underlying-id"
        UnderlyingPositionRecord.objects.create(
            id=legacy_payload["id"], owner=self.user,
            status="open", payload=legacy_payload,
        )

        response = self.client.post(
            self.url,
            {
                "file": csv_file(MIXED_OPEN_HEADERS, [row], name="base.csv"),
                "status": "open",
                "confirm": True,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["imported"], 0)
        self.assertEqual(response.data["skipped"], 1)
        self.assertEqual(UnderlyingPositionRecord.objects.count(), 1)

    def test_invalid_file_is_never_partially_imported(self):
        response = self.client.post(
            self.url,
            {"file": open_csv_file(invalid=True), "status": "open", "confirm": True},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["invalid"], 1)
        self.assertEqual(TradeRecord.objects.count(), 0)

    def test_requires_authentication(self):
        response = APIClient().post(
            self.url,
            {"file": open_csv_file(), "status": "open"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_session_import_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username="import-user", password="test-password"))

        response = client.post(
            self.url,
            {"file": open_csv_file(), "status": "open", "confirm": True},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(TradeRecord.objects.count(), 0)

    def test_mixed_open_file_dispatches_underlying_without_option_fields(self):
        today = tehran_today()
        rows = [
            {
                "نوع موقعیت": "خرید دارایی پایه",
                "بازار": "بورس کالا",
                "دارایی پایه": "طلای 24 عیار",
                "روش خرید دارایی پایه": "خرید مستقیم دارایی پایه",
                "تاریخ ورود": format_jalali_date(today - timedelta(days=10)),
                "تعداد کل": "7",
                "تعداد اولیه دارایی پایه": "7",
                "تعداد آزاد دارایی پایه": "7",
                "تعداد تخصیص‌یافته به کاوردکال": "0",
                "قیمت پایه ورود": "28248990",
                "قیمت پایه جاری": "31922000",
                "کارمزد ورود": "0",
            },
            {
                "نوع موقعیت": "خرید اختیار خرید",
                "بازار": "بورس کالا",
                "دارایی پایه": "صندوق طلا",
                "نماد اختیار": "TESTC100",
                "تاریخ ورود": format_jalali_date(today - timedelta(days=10)),
                "تاریخ سررسید": format_jalali_date(today + timedelta(days=40)),
                "تعداد کل": "10",
                "تعداد با هدف اعمال": "2",
                "تعداد نوسان‌گیری پرمیوم": "8",
                "قیمت پایه ورود": "150000",
                "پرمیوم ورود": "25000",
                "قیمت اعمال": "100000",
                "کارمزد ورود": "0",
            },
        ]

        response = self.client.post(
            self.url,
            {
                "file": csv_file(MIXED_OPEN_HEADERS, rows, name="mixed-open.csv"),
                "status": "open",
                "confirm": True,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["imported"], 2)
        self.assertEqual(response.data["valid_trades"], 1)
        self.assertEqual(response.data["valid_underlyings"], 1)
        self.assertEqual(TradeRecord.objects.count(), 1)
        position = UnderlyingPositionRecord.objects.get()
        self.assertEqual(position.owner, self.user)
        self.assertEqual(position.status, "open")
        self.assertEqual(position.payload["acquisition_method"], "direct")
        self.assertEqual(position.payload["quantity"], 7)
        self.assertNotIn("option_symbol", position.payload)

    def test_closed_underlying_imports_exercise_origin_and_is_idempotent(self):
        today = tehran_today()
        row = {
            "نوع موقعیت": "خرید دارایی پایه",
            "بازار": "بورس تهران",
            "دارایی پایه": "فولاد",
            "روش خرید دارایی پایه": "خرید از طریق اعمال اختیار خرید",
            "قرارداد منبع اعمال": "ضفلا1234",
            "تاریخ ورود": format_jalali_date(today - timedelta(days=30)),
            "تاریخ خروج": format_jalali_date(today - timedelta(days=5)),
            "تعداد کل": "1000",
            "قیمت پایه ورود": "1200",
            "قیمت پایه خروج": "1500",
            "سود یا زیان قطعی": "300000",
            "بازده قطعی (درصد)": "25",
            "بازده سالانه‌شده (درصد)": "365",
            "روز نگهداری": "25",
            "کارمزد ورود": "0",
            "کارمزد خروج": "0",
            "یادداشت": "فروش دارایی اعمال‌شده",
        }
        payload = {
            "file": csv_file(MIXED_CLOSED_HEADERS, [row], name="closed-base.csv"),
            "status": "closed",
            "confirm": True,
        }

        first = self.client.post(self.url, payload, format="multipart")
        payload["file"] = csv_file(
            MIXED_CLOSED_HEADERS, [row], name="closed-base.csv"
        )
        second = self.client.post(self.url, payload, format="multipart")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["imported"], 1)
        self.assertEqual(second.data["imported"], 0)
        self.assertEqual(second.data["skipped"], 1)
        position = UnderlyingPositionRecord.objects.get()
        self.assertEqual(position.status, "closed")
        self.assertEqual(position.payload["acquisition_method"], "exercise")
        self.assertEqual(position.payload["source_option_symbol"], "ضفلا1234")
        self.assertEqual(position.payload["exit_price"], 1500)
