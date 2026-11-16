from __future__ import annotations

from datetime import timedelta
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from nicoption_dashboard.models import TradeMutationRequest


class Command(BaseCommand):
    help = (
        "Preview or delete expired trade idempotency records. "
        "The command is read-only unless --confirm is supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than-days",
            type=int,
            required=True,
            help="Only target records strictly older than this many days.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Delete the matching idempotency records.",
        )

    def handle(self, *args, **options):
        older_than_days = options["older_than_days"]
        if older_than_days < 1:
            raise CommandError("--older-than-days must be at least 1")

        cutoff = timezone.now() - timedelta(days=older_than_days)
        queryset = TradeMutationRequest.objects.filter(created_at__lt=cutoff)
        eligible_count = queryset.count()
        confirmed = bool(options["confirm"])
        deleted_count = 0

        if confirmed and eligible_count:
            with transaction.atomic():
                deleted_count, deleted_by_model = queryset.delete()
            deleted_count = deleted_by_model.get(
                TradeMutationRequest._meta.label,
                deleted_count,
            )

        report = {
            "dry_run": not confirmed,
            "older_than_days": older_than_days,
            "cutoff": cutoff.isoformat(),
            "eligible_count": eligible_count,
            "deleted_count": deleted_count,
            "writes_performed": deleted_count,
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
