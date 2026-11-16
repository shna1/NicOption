from django.core.management.base import BaseCommand, CommandError

from nicoption_dashboard.economic_data import ConcurrentImportError, import_rows, ingestion_lock, iter_csv_rows
from nicoption_dashboard.models import IngestionRun


class Command(BaseCommand):
    help = "Import canonical economic observations from a UTF-8 CSV file."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--indicator", default="")

    def handle(self, *args, **options):
        try:
            with ingestion_lock():
                summary = import_rows(
                    iter_csv_rows(options["path"]), channel=IngestionRun.Channel.CSV,
                    dry_run=options["dry_run"], strict=options["strict"],
                    indicator_code=options["indicator"], metadata={"filename": "<redacted>"},
                )
        except (OSError, ValueError, ConcurrentImportError) as exc:
            raise CommandError(str(exc)) from exc
        line = " ".join(f"{key}={value}" for key, value in summary.as_dict().items())
        self.stdout.write((self.style.WARNING if summary.rejected else self.style.SUCCESS)(line))
        if options["strict"] and summary.rejected:
            raise CommandError("strict import rejected rows; no observations were written")
