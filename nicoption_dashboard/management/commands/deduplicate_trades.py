from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nicoption_dashboard.models import TradeRecord, UnderlyingPositionRecord
from nicoption_dashboard.trade_imports import _identity_key


REFERENCE_FIELDS = ("source_trade_id", "parent_trade_id")


class Command(BaseCommand):
    help = "Preview or remove duplicate trades using their stable financial identity."

    def add_arguments(self, parser):
        parser.add_argument("--username")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        queryset = TradeRecord.objects.select_related("owner").order_by(
            "owner_id", "created_at", "id"
        )
        username = str(options.get("username") or "").strip()
        if username:
            if not get_user_model().objects.filter(username=username).exists():
                raise CommandError("کاربر واردشده وجود ندارد")
            queryset = queryset.filter(owner__username=username)

        records = list(queryset)
        groups = defaultdict(list)
        for record in records:
            payload = {**record.payload, "status": record.payload.get("status") or record.status}
            groups[(record.owner_id, _identity_key(payload, model_type="trade"))].append(record)
        duplicate_groups = [items for items in groups.values() if len(items) > 1]
        referenced_ids = self._referenced_trade_ids(records)
        plan = [self._plan_group(items, referenced_ids) for items in duplicate_groups]
        extra_count = sum(len(item["remove"]) for item in plan)

        mode = "DELETE" if options["confirm"] else "PREVIEW"
        self.stdout.write(f"{mode}: {len(plan)} duplicate groups, {extra_count} extra records")
        for item in plan:
            owner = item["keep"].owner.username if item["keep"].owner else "legacy"
            removed = ", ".join(record.id for record in item["remove"])
            self.stdout.write(f"- {owner}: keep={item['keep'].id} remove={removed}")

        if not options["confirm"]:
            self.stdout.write("No records changed. Run again with --confirm to delete extras.")
            return
        with transaction.atomic():
            for item in plan:
                self._apply_group(item)
        self.stdout.write(self.style.SUCCESS(f"Deleted {extra_count} duplicate trade records."))

    @staticmethod
    def _referenced_trade_ids(records):
        referenced = set()
        for record in records:
            for field in REFERENCE_FIELDS:
                value = str(record.payload.get(field) or "").strip()
                if value:
                    referenced.add(value)
        for payload in UnderlyingPositionRecord.objects.values_list("payload", flat=True):
            value = str(payload.get("source_trade_id") or "").strip()
            if value:
                referenced.add(value)
        return referenced

    @staticmethod
    def _plan_group(records, referenced_ids):
        def rank(record):
            populated = sum(value not in (None, "", [], {}) for value in record.payload.values())
            return (record.id in referenced_ids, populated, -record.created_at.timestamp())

        keep = max(records, key=rank)
        return {"keep": keep, "remove": [record for record in records if record.pk != keep.pk]}

    @staticmethod
    def _apply_group(plan):
        keep = plan["keep"]
        remove = plan["remove"]
        removed_ids = {record.id for record in remove}
        merged = dict(keep.payload)
        for record in remove:
            for key, value in record.payload.items():
                if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    merged[key] = value
        merged["id"] = keep.id
        keep.payload = merged
        keep.save(update_fields=["payload", "updated_at"])

        for record in TradeRecord.objects.filter(owner_id=keep.owner_id):
            payload = dict(record.payload)
            changed = False
            for field in REFERENCE_FIELDS:
                if str(payload.get(field) or "") in removed_ids:
                    payload[field] = keep.id
                    changed = True
            if changed:
                record.payload = payload
                record.save(update_fields=["payload", "updated_at"])
        for position in UnderlyingPositionRecord.objects.filter(owner_id=keep.owner_id):
            payload = dict(position.payload)
            if str(payload.get("source_trade_id") or "") in removed_ids:
                payload["source_trade_id"] = keep.id
                position.payload = payload
                position.save(update_fields=["payload", "updated_at"])
        TradeRecord.objects.filter(id__in=removed_ids, owner_id=keep.owner_id).delete()
