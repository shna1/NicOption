from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nicoption_dashboard.models import (
    AccountPreference,
    TradeRecord,
    UnderlyingPositionRecord,
)


class Command(BaseCommand):
    help = "Assign records created before user ownership to one existing user."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            owner = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("کاربر واردشده وجود ندارد") from exc

        trade_count = TradeRecord.objects.filter(owner__isnull=True).update(owner=owner)
        underlying_count = UnderlyingPositionRecord.objects.filter(
            owner__isnull=True
        ).update(owner=owner)

        legacy_preferences = list(
            AccountPreference.objects.filter(owner__isnull=True).order_by("pk")
        )
        preference_count = len(legacy_preferences)
        if legacy_preferences:
            preference, _ = AccountPreference.objects.get_or_create(owner=owner)
            latest = legacy_preferences[-1]
            preference.initial_capital = latest.initial_capital
            preference.save(update_fields=["initial_capital", "updated_at"])
            AccountPreference.objects.filter(owner__isnull=True).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"{trade_count} معامله، {underlying_count} دارایی پایه و "
                f"{preference_count} تنظیم قدیمی به {owner.username} منتقل شد"
            )
        )
