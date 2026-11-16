from __future__ import annotations

from datetime import timedelta
from io import StringIO
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from nicoption_dashboard.models import TradeMutationRequest


class PruneTradeMutationRequestsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="idempotency-owner")

    def create_request(self, key_hash: str, *, age_days: int):
        record = TradeMutationRequest.objects.create(
            owner=self.user,
            operation="trade.create",
            key_hash=key_hash,
            request_hash=f"request-{key_hash}",
            trade_id=f"trade-{key_hash}",
        )
        TradeMutationRequest.objects.filter(pk=record.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
        record.refresh_from_db()
        return record

    def run_command(self, *args):
        output = StringIO()
        call_command("prune_trade_mutation_requests", *args, stdout=output)
        return json.loads(output.getvalue())

    def test_dry_run_is_default_and_does_not_delete_records(self):
        self.create_request("old", age_days=31)
        self.create_request("recent", age_days=2)

        report = self.run_command("--older-than-days", "30")

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["eligible_count"], 1)
        self.assertEqual(report["deleted_count"], 0)
        self.assertEqual(report["writes_performed"], 0)
        self.assertEqual(TradeMutationRequest.objects.count(), 2)

    def test_confirm_deletes_only_records_older_than_cutoff(self):
        old = self.create_request("old", age_days=31)
        recent = self.create_request("recent", age_days=2)

        report = self.run_command("--older-than-days", "30", "--confirm")

        self.assertFalse(report["dry_run"])
        self.assertEqual(report["eligible_count"], 1)
        self.assertEqual(report["deleted_count"], 1)
        self.assertEqual(report["writes_performed"], 1)
        self.assertFalse(TradeMutationRequest.objects.filter(pk=old.pk).exists())
        self.assertTrue(TradeMutationRequest.objects.filter(pk=recent.pk).exists())

    def test_non_positive_retention_window_is_rejected(self):
        with self.assertRaisesMessage(
            CommandError, "--older-than-days must be at least 1"
        ):
            call_command("prune_trade_mutation_requests", "--older-than-days", "0")
