import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from nicoption_dashboard.economic_data import (
    ConcurrentImportError, GoogleSheetsClient, ImportConfigurationError,
    import_rows, ingestion_lock,
)
from nicoption_dashboard.models import IngestionRun


class Command(BaseCommand):
    help = "Read economic observations from Google Sheets API v4 and persist them."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--indicator", default="")
        parser.add_argument("--range", dest="sheet_range", default="")

    def handle(self, *args, **options):
        spreadsheet_id = os.getenv("ECONOMIC_GOOGLE_SHEET_ID", "").strip()
        sheet_range = options["sheet_range"].strip() or os.getenv("ECONOMIC_GOOGLE_SHEET_RANGE", "").strip()
        credential_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        try:
            client = GoogleSheetsClient(
                credential_file,
                timeout=settings.ECONOMIC_GOOGLE_TIMEOUT_SECONDS,
                retries=settings.ECONOMIC_GOOGLE_RETRIES,
            )
            with ingestion_lock():
                summary = import_rows(
                    client.rows(spreadsheet_id, sheet_range),
                    channel=IngestionRun.Channel.GOOGLE_SHEETS,
                    dry_run=options["dry_run"], strict=options["strict"],
                    indicator_code=options["indicator"],
                    metadata={"range": sheet_range, "spreadsheet_configured": bool(spreadsheet_id)},
                )
        except (ImportConfigurationError, ConcurrentImportError, ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError("Google Sheets request failed; credentials and response details were not logged") from exc
        line = " ".join(f"{key}={value}" for key, value in summary.as_dict().items())
        self.stdout.write((self.style.WARNING if summary.rejected else self.style.SUCCESS)(line))
        if options["strict"] and summary.rejected:
            raise CommandError("strict import rejected rows; no observations were written")
