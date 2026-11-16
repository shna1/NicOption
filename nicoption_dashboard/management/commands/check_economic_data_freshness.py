from django.core.management.base import BaseCommand
from django.utils import timezone

from nicoption_dashboard.models import DataIssue, EconomicIndicator, IndicatorObservation
from nicoption_dashboard.economic_data import freshness_deadline


class Command(BaseCommand):
    help = "Record deduplicated missing/stale issues for active economic indicators."

    def handle(self, *args, **options):
        today = timezone.localdate()
        opened = resolved = 0
        for indicator in EconomicIndicator.objects.filter(is_active=True):
            latest = IndicatorObservation.objects.filter(indicator=indicator, is_current_revision=True).order_by("-period_date").first()
            code = "missing_data" if latest is None else "stale_data"
            stale = latest is None or freshness_deadline(indicator, latest.period_date) < today
            existing = DataIssue.objects.filter(indicator=indicator, ingestion_run__isnull=True, issue_code__in=("missing_data", "stale_data"), resolved_at__isnull=True)
            if stale:
                existing.exclude(issue_code=code).update(resolved_at=timezone.now(), resolution_notes="Superseded by a newer freshness state")
                _, created = DataIssue.objects.get_or_create(
                    indicator=indicator, ingestion_run=None, issue_code=code, resolved_at=None,
                    defaults={
                        "severity": DataIssue.Severity.WARNING,
                        "message": "No current observation is available" if latest is None else "Latest observation exceeds the configured freshness threshold",
                        "safe_payload": {"indicator_code": indicator.code, "latest_period": latest.period_date.isoformat() if latest else None},
                    },
                )
                opened += int(created)
            else:
                resolved += existing.update(resolved_at=timezone.now(), resolution_notes="Fresh data is available")
        self.stdout.write(self.style.SUCCESS(f"opened={opened} resolved={resolved}"))
