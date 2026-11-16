from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nicoption_dashboard.cbi_mcp import CbiMcpError, collect_cbi_snapshot
from nicoption_dashboard.models import CentralBankSnapshot


class Command(BaseCommand):
    help = "Read Central Bank public data through cbi-mcp and store a durable snapshot."

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=12, help="Number of snapshots to retain (default: 12).")

    def handle(self, *args, **options):
        keep = max(1, min(int(options["keep"]), 100))
        try:
            result = collect_cbi_snapshot()
        except (CbiMcpError, OSError) as exc:
            raise CommandError(f"cbi-mcp sync failed: {exc}") from exc
        if not result.payload:
            raise CommandError("cbi-mcp returned no usable tool results")
        with transaction.atomic():
            snapshot = CentralBankSnapshot.objects.create(
                server_name=result.server_name,
                server_version=result.server_version,
                payload=result.payload,
                errors=result.errors,
            )
            stale_ids = list(
                CentralBankSnapshot.objects.order_by("-collected_at", "-pk")
                .values_list("pk", flat=True)[keep:]
            )
            if stale_ids:
                CentralBankSnapshot.objects.filter(pk__in=stale_ids).delete()
        self.stdout.write(self.style.SUCCESS(
            f"snapshot={snapshot.pk} tools={len(result.payload)} errors={len(result.errors)}"
        ))
