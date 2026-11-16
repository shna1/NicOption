from datetime import date

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nicoption_dashboard.economic_data import (
    ConcurrentImportError,
    FinpyTSEClient,
    ImportConfigurationError,
    import_rows,
    ingestion_lock,
    parse_period_date,
)
from nicoption_dashboard.models import IngestionRun


class Command(BaseCommand):
    help = "Fetch TEDPIX with FinPy-TSE, reduce daily data to Solar Hijri monthly closes, and persist it."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--from", dest="from_date", default="")
        parser.add_argument("--to", dest="to_date", default="")

    def handle(self, *args, **options):
        today = timezone.localdate()
        default_from = date(today.year - 6, 1, 1)
        try:
            from_date = parse_period_date(options["from_date"]) if options["from_date"] else default_from
            to_date = parse_period_date(options["to_date"]) if options["to_date"] else today
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if to_date < from_date:
            raise CommandError("--to must be on or after --from")

        client = FinpyTSEClient(retries=settings.ECONOMIC_FINPY_TSE_RETRIES)
        try:
            rows, quality = client.monthly_rows(from_date=from_date, to_date=to_date)
            with ingestion_lock():
                summary = import_rows(
                    rows,
                    channel=IngestionRun.Channel.API,
                    dry_run=options["dry_run"],
                    strict=options["strict"],
                    metadata={
                        "provider": "FinPy-TSE",
                        "upstream": "TSETMC",
                        "indicator": "IR_TEDPIX",
                        "from": from_date.isoformat(),
                        "to": to_date.isoformat(),
                        "quality": quality,
                        "aggregation": "last_valid_trading_day_per_solar_hijri_month",
                    },
                )
        except (
            requests.RequestException,
            ImportConfigurationError,
            ConcurrentImportError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise CommandError("FinPy-TSE TEDPIX sync failed without persisting a partial fetch") from exc
        line = " ".join(f"{key}={value}" for key, value in summary.as_dict().items())
        self.stdout.write((self.style.WARNING if summary.rejected else self.style.SUCCESS)(line))
        if options["strict"] and summary.rejected:
            raise CommandError("strict import rejected rows; no observations were written")
