from __future__ import annotations

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from nicoption_dashboard.models import (
    AccountPreference, TradeRecord, UnderlyingPositionRecord,
)


class Command(BaseCommand):
    help = "Export Django trades and account settings to portable JSON files."

    def add_arguments(self, parser):
        parser.add_argument("--directory", default="django-export")
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        try:
            owner = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("کاربر واردشده وجود ندارد") from exc
        directory = Path(options["directory"]).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        trades = [
            dict(payload)
            for payload in TradeRecord.objects.filter(owner=owner).order_by("created_at", "id")
            .values_list("payload", flat=True)
        ]
        preference = AccountPreference.objects.filter(owner=owner).first()
        account = {
            "initial_capital": None if preference is None else preference.initial_capital,
            "cash_balance": None if preference is None else preference.cash_balance,
        }
        underlyings = [
            dict(payload)
            for payload in UnderlyingPositionRecord.objects.filter(owner=owner).order_by("created_at", "id")
            .values_list("payload", flat=True)
        ]
        (directory / "trades.json").write_text(
            json.dumps(trades, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "account.json").write_text(
            json.dumps(account, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "underlying_positions.json").write_text(
            json.dumps(underlyings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.stdout.write(self.style.SUCCESS(
            f"خروجی {len(trades)} معامله و {len(underlyings)} دارایی پایه در {directory} ذخیره شد"
        ))
