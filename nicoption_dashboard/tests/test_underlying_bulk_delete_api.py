import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from nicoption_dashboard.models import UnderlyingPositionRecord


class UnderlyingBulkDeleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="underlying-bulk-user")
        self.other = get_user_model().objects.create_user(username="other-underlying-user")
        self.client.force_login(self.user)
        self.url = reverse("api-underlyings-bulk-delete")

    def create_position(self, position_id, *, owner=None, status="open"):
        return UnderlyingPositionRecord.objects.create(
            id=position_id,
            owner=owner or self.user,
            status=status,
            payload={
                "id": position_id,
                "status": status,
                "market": "tehran",
                "asset": "فولاد",
                "quantity": 1000,
                "entry_price": 5000,
                "entry_date": "2026-01-01",
            },
        )

    def test_deletes_only_selected_positions_for_owner_and_status(self):
        selected = self.create_position("selected-open")
        retained = self.create_position("retained-open")
        closed = self.create_position("selected-closed", status="closed")
        other = self.create_position("other-open", owner=self.other)

        response = self.client.post(
            self.url,
            data=json.dumps({
                "ids": [selected.id, closed.id, other.id],
                "status": "open",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bulk_deleted"], 1)
        self.assertFalse(UnderlyingPositionRecord.objects.filter(id=selected.id).exists())
        self.assertTrue(UnderlyingPositionRecord.objects.filter(id=retained.id).exists())
        self.assertTrue(UnderlyingPositionRecord.objects.filter(id=closed.id).exists())
        self.assertTrue(UnderlyingPositionRecord.objects.filter(id=other.id).exists())

    def test_rejects_empty_selection(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"ids": [], "status": "closed"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("حداقل یک دارایی پایه", response.json()["error"])

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.post(
            self.url,
            data=json.dumps({"ids": ["selected-open"], "status": "open"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
