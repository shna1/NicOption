from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient


class HistoryApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="history-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    def test_asset_query_parameter_is_required(self):
        response = self.client.get(reverse("api-v1:history"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("asset", response.data)

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_fetches_history_with_validated_query(self, get_runtime):
        expected_payload = {
            "asset": "فولاد",
            "items": [],
        }
        runtime = get_runtime.return_value
        runtime.history.fetch.return_value = expected_payload

        response = self.client.get(
            reverse("api-v1:history"),
            {
                "asset": "  فولاد  ",
                "source_asset": "  فولاد  ",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, expected_payload)
        runtime.history.fetch.assert_called_once_with("فولاد", "فولاد")

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_bad_gateway_when_history_provider_fails(self, get_runtime):
        runtime = get_runtime.return_value
        runtime.history.fetch.side_effect = RuntimeError(
            "internal provider connection detail"
        )

        response = self.client.get(
            reverse("api-v1:history"),
            {"asset": "فولاد"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            str(response.data["detail"]),
            "دریافت تاریخچه قیمت ناموفق بود.",
        )
        self.assertNotIn(
            "internal provider connection detail",
            str(response.data),
        )

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_requires_authentication(self, get_runtime):
        anonymous_client = APIClient()

        response = anonymous_client.get(
            reverse("api-v1:history"),
            {"asset": "فولاد"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        get_runtime.assert_not_called()

class OrderBookCatalogApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="catalog-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_order_book_catalog(self, get_runtime):
        expected_payload = {
            "instruments": [
                {
                    "market": "tehran",
                    "instrument_type": "option",
                    "symbol": "ضفلا",
                    "asset": "فولاد",
                    "ins_code": "12345",
                },
            ],
        }
        runtime = get_runtime.return_value
        runtime.cache.order_flow_catalog.return_value = expected_payload

        response = self.client.get(
            reverse("api-v1:order-book-catalog"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data,
            expected_payload,
        )
        runtime.cache.order_flow_catalog.assert_called_once_with()

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_requires_authentication(self, get_runtime):
        anonymous_client = APIClient()

        response = anonymous_client.get(
            reverse("api-v1:order-book-catalog"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        get_runtime.assert_not_called()


    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_bad_gateway_when_catalog_service_fails(
        self,
        get_runtime,
         ):
        runtime = get_runtime.return_value
        runtime.cache.order_flow_catalog.side_effect = RuntimeError(
            "internal market provider detail"
        )

        response = self.client.get(
            reverse("api-v1:order-book-catalog"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_502_BAD_GATEWAY,
        )
        self.assertEqual(
            str(response.data["detail"]),
            "دریافت فهرست جریان سفارش‌ها ناموفق بود.",
        )
        self.assertNotIn(
            "internal market provider detail",
            str(response.data),
        )


class OrderBookApiV1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="order-book-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    def test_symbol_query_parameter_is_required(self):
        response = self.client.get(
            reverse("api-v1:order-book"),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("symbol", response.data)


    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_fetches_order_book_with_validated_query(
        self,
        get_runtime,
    ):
        expected_payload = {
            "symbol": "فولاد",
            "levels": [],
        }
        runtime = get_runtime.return_value
        runtime.cache.order_flow.return_value = expected_payload

        response = self.client.get(
            reverse("api-v1:order-book"),
            {
                "symbol": "  فولاد  ",
                "refresh": "true",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data,
            expected_payload,
        )
        runtime.cache.order_flow.assert_called_once_with(
            market="tehran",
            instrument_type="option",
            symbol="فولاد",
            force=True,
        )

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_rejects_invalid_choice_parameters(
        self,
        get_runtime,
    ):
        invalid_queries = (
            (
                {
                    "symbol": "فولاد",
                    "market": "invalid-market",
                },
                "market",
            ),
            (
                {
                    "symbol": "فولاد",
                    "instrument_type": "invalid-type",
                },
                "instrument_type",
            ),
        )

        for query, expected_field in invalid_queries:
            with self.subTest(query=query):
                response = self.client.get(
                    reverse("api-v1:order-book"),
                    query,
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertIn(
                    expected_field,
                    response.data,
                )

        get_runtime.assert_not_called()

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_not_found_when_symbol_is_not_in_catalog(
        self,
        get_runtime,
    ):
        runtime = get_runtime.return_value
        runtime.cache.order_flow.side_effect = KeyError(
            "نماد انتخاب‌شده در فهرست جاری بازار پیدا نشد"
        )

        response = self.client.get(
            reverse("api-v1:order-book"),
            {
                "market": "tehran",
                "instrument_type": "option",
                "symbol": "ناشناخته",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            str(response.data["detail"]),
            "نماد انتخاب‌شده در فهرست جاری بازار پیدا نشد.",
        )

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_bad_gateway_when_order_book_provider_fails(
        self,
        get_runtime,
    ):
        runtime = get_runtime.return_value
        runtime.cache.order_flow.side_effect = RuntimeError(
            "internal upstream connection detail"
        )

        response = self.client.get(
            reverse("api-v1:order-book"),
            {
                "market": "tehran",
                "instrument_type": "option",
                "symbol": "فولاد",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_502_BAD_GATEWAY,
        )
        self.assertEqual(
            str(response.data["detail"]),
            "دریافت جریان سفارش‌ها ناموفق بود.",
        )
        self.assertNotIn(
            "internal upstream connection detail",
            str(response.data),
        )

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_requires_authentication(self, get_runtime):
        anonymous_client = APIClient()

        response = anonymous_client.get(
            reverse("api-v1:order-book"),
            {
                "market": "tehran",
                "instrument_type": "option",
                "symbol": "فولاد",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        get_runtime.assert_not_called()


class CoveredScoreApiV1Tests(TestCase):
    payload = {
        "market": "tehran",
        "asset": "فولاد",
        "symbol": "ضفلا",
        "base_price": 1_000,
        "premium": 100,
        "strike": 950,
        "days": 30,
        "transaction_value": "",
        "option_last": 110,
    }

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="covered-score-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    def test_requires_core_financial_inputs(self):
        response = self.client.post(
            reverse("api-v1:covered-score"),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            set(response.data),
            {
                "base_price",
                "premium",
                "strike",
                "days",
            },
        )

    @patch("nicoption_dashboard.api.v1.views.calculate_custom_covered_call")
    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_calculates_score_with_normalized_input(
        self,
        get_runtime,
        calculate_custom_covered_call,
    ):
        expected_payload = {
            "covered_score": 82,
            "covered_score_label": "مناسب",
        }
        runtime = get_runtime.return_value
        runtime.settings.long_underlying_interest_rate = 42
        runtime.cache.get.return_value = {
            "covered_call": [
                {
                    "market": "tehran",
                    "items": [
                        {"transaction_value": 10},
                        {"transaction_value": 100},
                    ],
                },
                {
                    "market": "goods",
                    "items": [{"transaction_value": 1_000}],
                },
            ]
        }
        calculate_custom_covered_call.return_value = expected_payload

        response = self.client.post(
            reverse("api-v1:covered-score"),
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, expected_payload)
        calculate_custom_covered_call.assert_called_once_with(
            {
                "market": "tehran",
                "asset": "فولاد",
                "symbol": "ضفلا",
                "base_price": 1_000.0,
                "premium": 100.0,
                "strike": 950.0,
                "days": 30.0,
                "transaction_value": None,
                "option_last": 110.0,
            },
            [10, 100],
            42,
        )

    @patch("nicoption_dashboard.api.v1.views.calculate_custom_covered_call")
    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_bad_request_for_financial_validation_error(
        self,
        get_runtime,
        calculate_custom_covered_call,
    ):
        runtime = get_runtime.return_value
        runtime.cache.get.return_value = {"covered_call": []}
        calculate_custom_covered_call.side_effect = ValueError(
            "قیمت پایه، اعمال و روز تا سررسید باید مثبت باشند"
        )

        response = self.client.post(
            reverse("api-v1:covered-score"),
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data,
            {
                "detail": "قیمت پایه، اعمال و روز تا سررسید باید مثبت باشند",
            },
        )

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_returns_bad_gateway_without_leaking_internal_error(
        self,
        get_runtime,
    ):
        runtime = get_runtime.return_value
        runtime.cache.get.side_effect = ValueError(
            "internal market provider detail"
        )

        response = self.client.post(
            reverse("api-v1:covered-score"),
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_502_BAD_GATEWAY,
        )
        self.assertEqual(
            str(response.data["detail"]),
            "محاسبه امتیاز کاوردکال ناموفق بود.",
        )
        self.assertNotIn(
            "internal market provider detail",
            str(response.data),
        )

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_requires_authentication(self, get_runtime):
        anonymous_client = APIClient()

        response = anonymous_client.post(
            reverse("api-v1:covered-score"),
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        get_runtime.assert_not_called()

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_requires_csrf_for_authenticated_session(self, get_runtime):
        session_client = APIClient(enforce_csrf_checks=True)
        logged_in = session_client.login(
            username="covered-score-user",
            password="test-password",
        )
        self.assertTrue(logged_in)

        response = session_client.post(
            reverse("api-v1:covered-score"),
            self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        get_runtime.assert_not_called()
