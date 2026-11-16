from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

from bambo_bot.config import Settings
from nicoption_dashboard.models import (
    AccountPreference, TradeRecord, UnderlyingPositionRecord,
)


class Command(BaseCommand):
    help = "Import portable trade, account and underlying-position JSON files."

    def add_arguments(self, parser):
        defaults = Settings()
        parser.add_argument("--trades", default=str(defaults.trades_file))
        parser.add_argument(
            "--account",
            default=str(defaults.trades_file.with_name("account.json")),
        )
        parser.add_argument(
            "--underlyings",
            default=str(defaults.trades_file.with_name("underlying_positions.json")),
        )
        parser.add_argument(
            "--replace", action="store_true", help="Replace existing database records."
        )
        parser.add_argument(
            "--username",
            required=True,
            help="Owner username for all imported records.",
        )

    @staticmethod
    def load_json(path: Path, fallback):
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"فایل {path} قابل خواندن نیست") from exc

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            owner = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("کاربر واردشده وجود ندارد") from exc
        trades_path = Path(options["trades"]).expanduser().resolve()
        account_path = Path(options["account"]).expanduser().resolve()
        underlyings_path = Path(options["underlyings"]).expanduser().resolve()
        trades = self.load_json(trades_path, [])
        account = self.load_json(account_path, {})
        underlyings = self.load_json(underlyings_path, [])
        if not isinstance(trades, list):
            raise CommandError("ساختار فایل معاملات باید یک فهرست JSON باشد")
        if not isinstance(account, dict):
            raise CommandError("ساختار فایل حساب باید یک شیء JSON باشد")
        if not isinstance(underlyings, list):
            raise CommandError("ساختار فایل دارایی‌های پایه باید یک فهرست JSON باشد")
        if options["replace"]:
            TradeRecord.objects.filter(owner=owner).delete()
            UnderlyingPositionRecord.objects.filter(owner=owner).delete()
            AccountPreference.objects.filter(owner=owner).delete()
        imported = 0
        for payload in trades:
            if not isinstance(payload, dict):
                continue
            item = dict(payload)
            trade_id = str(item.get("id") or uuid4().hex)
            item["id"] = trade_id
            item.setdefault("status", "open")
            TradeRecord.objects.update_or_create(
                id=trade_id,
                defaults={
                    "owner": owner,
                    "status": str(item["status"]),
                    "payload": item,
                },
            )
            imported += 1
        imported_underlyings = 0
        for payload in underlyings:
            if not isinstance(payload, dict):
                continue
            item = dict(payload)
            item_id = str(item.get("id") or uuid4().hex)
            item["id"] = item_id
            item.setdefault("status", "open")
            UnderlyingPositionRecord.objects.update_or_create(
                id=item_id,
                defaults={
                    "owner": owner,
                    "status": str(item["status"]),
                    "payload": item,
                },
            )
            imported_underlyings += 1
        if "initial_capital" in account:
            AccountPreference.objects.update_or_create(
                owner=owner,
                defaults={
                    "initial_capital": account.get("initial_capital"),
                    "cash_balance": account.get("cash_balance"),
                },
            )
        self.stdout.write(self.style.SUCCESS(
            f"{imported} معامله و {imported_underlyings} دارایی پایه وارد شد · منبع: {trades_path}"
        ))
