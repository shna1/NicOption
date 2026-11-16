from datetime import date

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from nicoption_dashboard.economic_data import (
    ConcurrentImportError,
    PriceTodayClient,
    import_rows,
    ingestion_lock,
    parse_period_date,
)
from nicoption_dashboard.models import IngestionRun


ASSETS = (
    ("usd", "IR_USD_FREE_MARKET"),
    ("coin-baharazadi-market", "IR_COIN_BAHAR_AZADI"),
    ("gold-18k", "IR_GOLD_18K"),
    ("tether", "IR_TETHER"),
)


class Command(BaseCommand):
    help = "Fetch PriceToDay daily market data, reduce it to Solar Hijri monthly closes, and persist it."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--asset", choices=[slug for slug, _ in ASSETS], default="")
        parser.add_argument("--from", dest="from_date", default="")
        parser.add_argument("--to", dest="to_date", default="")

    def handle(self, *args, **options):
        today = timezone.localdate()
        default_from = date(today.year - 1, 1, 1)
        try:
            from_date = parse_period_date(options["from_date"]) if options["from_date"] else default_from
            to_date = parse_period_date(options["to_date"]) if options["to_date"] else None
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if to_date and to_date < from_date:
            raise CommandError("--to must be on or after --from")

        selected = [item for item in ASSETS if not options["asset"] or item[0] == options["asset"]]
        client = PriceTodayClient(
            timeout=settings.ECONOMIC_PRICETODAY_TIMEOUT_SECONDS,
            retries=settings.ECONOMIC_PRICETODAY_RETRIES,
        )
        rows = []
        quality = {}
        try:
            for slug, code in selected:
                asset_rows, asset_quality = client.monthly_rows(
                    slug=slug,
                    indicator_code=code,
                    source_name="PriceToDay",
                    unit="ریال",
                    from_date=from_date,
                    to_date=to_date,
                )
                rows.extend(asset_rows)
                quality[slug] = asset_quality
            with ingestion_lock():
                summary = import_rows(
                    rows,
                    channel=IngestionRun.Channel.API,
                    dry_run=options["dry_run"],
                    strict=options["strict"],
                    metadata={
                        "provider": "PriceToDay",
                        "from": from_date.isoformat(),
                        "to": to_date.isoformat() if to_date else None,
                        "assets": [slug for slug, _ in selected],
                        "quality": quality,
                        "aggregation": "last_valid_daily_price_per_solar_hijri_month",
                    },
                )
        except (requests.RequestException, ValueError, ConcurrentImportError) as exc:
            raise CommandError("PriceToDay sync failed without persisting a partial fetch") from exc
        line = " ".join(f"{key}={value}" for key, value in summary.as_dict().items())
        self.stdout.write((self.style.WARNING if summary.rejected else self.style.SUCCESS)(line))
        if options["strict"] and summary.rejected:
            raise CommandError("strict import rejected rows; no observations were written")
