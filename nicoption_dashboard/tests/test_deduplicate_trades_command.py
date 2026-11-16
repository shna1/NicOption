from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from nicoption_dashboard.models import TradeRecord, UnderlyingPositionRecord


class DeduplicateTradesCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dedupe-user")
        self.payload = {
            "status": "open",
            "strategy_type": "covered_call",
            "market": "tehran",
            "asset": "فولاد",
            "option_symbol": "ضفلا1234",
            "entry_date": "2026-09-01",
            "expiry": "2026-10-01",
            "quantity": 1000,
            "entry_base_price": 1200,
            "entry_premium": 100,
            "strike": 1300,
        }

    def create_trade(self, trade_id, **extra):
        payload = {**self.payload, "id": trade_id, **extra}
        return TradeRecord.objects.create(
            id=trade_id, owner=self.user, status="open", payload=payload
        )

    def test_preview_does_not_change_records(self):
        self.create_trade("duplicate-old")
        self.create_trade("duplicate-new", import_source="csv")
        output = StringIO()

        call_command("deduplicate_trades", stdout=output)

        self.assertEqual(TradeRecord.objects.count(), 2)
        self.assertIn("PREVIEW: 1 duplicate groups, 1 extra records", output.getvalue())
        self.assertIn("No records changed", output.getvalue())

    def test_confirm_keeps_referenced_record_and_remaps_metadata(self):
        referenced = self.create_trade("duplicate-old")
        self.create_trade(
            "duplicate-new", import_source="csv", import_fingerprint="fingerprint"
        )
        UnderlyingPositionRecord.objects.create(
            id="underlying-source",
            owner=self.user,
            status="open",
            payload={
                "id": "underlying-source",
                "status": "open",
                "source_trade_id": referenced.id,
            },
        )
        output = StringIO()

        call_command("deduplicate_trades", "--confirm", stdout=output)

        self.assertEqual(TradeRecord.objects.count(), 1)
        kept = TradeRecord.objects.get()
        self.assertEqual(kept.id, referenced.id)
        self.assertEqual(kept.payload["import_fingerprint"], "fingerprint")
        self.assertEqual(
            UnderlyingPositionRecord.objects.get().payload["source_trade_id"],
            referenced.id,
        )
        self.assertIn("Deleted 1 duplicate trade records", output.getvalue())
