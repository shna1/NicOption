from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from nicoption_dashboard.models import AccountPreference


class UserPreferencesApiV1Tests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="preferences-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    def test_returns_default_preferences(self):
        response = self.client.get(reverse("api-v1:preferences"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "show_overview": True,
                "show_articles": True,
                "show_option_market": True,
                "show_economic_data": True,
                "show_market": True,
                "show_tehran_options": True,
                "show_order_flow": True,
                "show_commodity_exchange": True,
                "show_trades": True,
                "show_closed_trades": True,
                "show_profit_recognition": True,
                "show_calculator": True,
                "show_settings": True,
                "show_forecast": True,
            },
        )

    def test_superuser_always_receives_access_to_every_page(self):
        admin = get_user_model().objects.create_superuser(
            username="site-admin",
            password="test-password",
            email="admin@example.com",
        )
        AccountPreference.objects.create(owner=admin, show_overview=False)
        self.client.force_authenticate(user=admin)

        response = self.client.get(reverse("api-v1:preferences"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(all(response.data.values()))

    def test_user_cannot_update_preferences_through_public_api(self):
        preference = AccountPreference.objects.create(
            owner=self.user,
            show_order_flow=True,
        )

        response = self.client.patch(
            reverse("api-v1:preferences"),
            {"show_order_flow": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        preference.refresh_from_db()
        self.assertTrue(preference.show_order_flow)

    def test_option_market_parent_disables_every_child_permission(self):
        AccountPreference.objects.create(
            owner=self.user,
            show_option_market=False,
            show_market=True,
            show_tehran_options=True,
            show_trades=True,
        )

        response = self.client.get(reverse("api-v1:preferences"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["show_option_market"])
        self.assertFalse(response.data["show_market"])
        self.assertFalse(response.data["show_tehran_options"])
        self.assertFalse(response.data["show_trades"])
        self.assertTrue(response.data["show_economic_data"])

    def test_requires_authentication(self):
        response = APIClient().get(reverse("api-v1:preferences"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("nicoption_dashboard.api.v1.views.get_runtime")
    def test_disabled_order_flow_cannot_be_bypassed_via_api(self, get_runtime):
        AccountPreference.objects.create(owner=self.user, show_order_flow=False)

        response = self.client.get(
            reverse("api-v1:order-book"),
            {"symbol": "فولاد"},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        get_runtime.assert_not_called()
