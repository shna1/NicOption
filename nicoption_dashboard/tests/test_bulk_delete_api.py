import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from nicoption_dashboard.models import TradeRecord


class TradeBulkDeleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="bulk-user")
        self.other = get_user_model().objects.create_user(username="other-bulk-user")
        self.client.force_login(self.user)
        self.url = reverse("api-trades-bulk-delete")

    def create_trade(self, trade_id, *, owner=None, status="open"):
        return TradeRecord.objects.create(
            id=trade_id,
            owner=owner or self.user,
            status=status,
            payload={"id": trade_id, "status": status},
        )

    def test_deletes_only_selected_trades_for_owner_and_status(self):
        selected = self.create_trade("selected-open")
        retained = self.create_trade("retained-open")
        closed = self.create_trade("selected-closed", status="closed")
        other = self.create_trade("other-open", owner=self.other)

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
        self.assertFalse(TradeRecord.objects.filter(id=selected.id).exists())
        self.assertTrue(TradeRecord.objects.filter(id=retained.id).exists())
        self.assertTrue(TradeRecord.objects.filter(id=closed.id).exists())
        self.assertTrue(TradeRecord.objects.filter(id=other.id).exists())

    def test_rejects_empty_selection(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"ids": [], "status": "closed"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("حداقل یک معامله", response.json()["error"])

    def test_requires_authentication(self):
        self.client.logout()

        response = self.client.post(
            self.url,
            data=json.dumps({"ids": ["selected-open"], "status": "open"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
