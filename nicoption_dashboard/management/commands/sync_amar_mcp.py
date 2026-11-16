from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nicoption_dashboard.amar_mcp import AmarMcpError, collect_amar_snapshot
from nicoption_dashboard.models import StatisticalCenterSnapshot


class Command(BaseCommand):
    help = "Read broad Statistical Centre data through amar-mcp and store a durable snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=1405, help="Jalali publication-calendar year (default: 1405).")
        parser.add_argument("--keep", type=int, default=12, help="Number of snapshots to retain (default: 12).")

    def handle(self, *args, **options):
        year = max(1400, min(int(options["year"]), 1410))
        keep = max(1, min(int(options["keep"]), 100))
        try:
            result = collect_amar_snapshot(year=year)
        except (AmarMcpError, OSError) as exc:
            raise CommandError(f"amar-mcp sync failed: {exc}") from exc
        macro = result.payload.get("macro") or {}
        table_count = sum(len(item.get("tables") or []) for item in macro.values())
        direct_count = sum(
            bool(result.payload.get(key))
            for key in ("labour_force", "youth_unemployment", "gdp_quarterly", "gdp_annual", "population", "calendar")
        )
        if not table_count and not direct_count:
            detail = next(iter(result.errors.values()), "no usable data returned")
            raise CommandError(f"amar-mcp returned no usable data: {detail}")
        with transaction.atomic():
            snapshot = StatisticalCenterSnapshot.objects.create(
                server_name=result.server_name,
                server_version=result.server_version,
                payload=result.payload,
                errors=result.errors,
            )
            stale_ids = list(
                StatisticalCenterSnapshot.objects.order_by("-collected_at", "-pk")
                .values_list("pk", flat=True)[keep:]
            )
            if stale_ids:
                StatisticalCenterSnapshot.objects.filter(pk__in=stale_ids).delete()
        self.stdout.write(self.style.SUCCESS(
            f"snapshot={snapshot.pk} topics={len(macro)} tables={table_count} direct={direct_count} errors={len(result.errors)}"
        ))
