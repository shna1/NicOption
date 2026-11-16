from decimal import Decimal, InvalidOperation

from django.db import migrations


def copy_explicit_metadata(apps, schema_editor):
    TradeRecord = apps.get_model("nicoption_dashboard", "TradeRecord")
    UnderlyingPositionRecord = apps.get_model(
        "nicoption_dashboard", "UnderlyingPositionRecord"
    )

    for record in TradeRecord.objects.iterator():
        payload = record.payload if isinstance(record.payload, dict) else {}
        fields = []
        kind = payload.get("quantity_kind")
        if record.quantity_kind is None and kind in {"contract", "unit"}:
            record.quantity_kind = kind
            fields.append("quantity_kind")
        if record.contract_size is None and payload.get("contract_size") not in (None, ""):
            try:
                size = Decimal(str(payload["contract_size"]))
            except (InvalidOperation, TypeError, ValueError):
                size = None
            if size is not None and size.is_finite() and size > 0:
                record.contract_size = size
                fields.append("contract_size")
        currency = payload.get("currency_unit")
        if record.currency_unit is None and currency in {"rial", "toman"}:
            record.currency_unit = currency
            fields.append("currency_unit")
        version = payload.get("calculation_version")
        if (
            record.calculation_version is None
            and isinstance(version, int)
            and not isinstance(version, bool)
            and version > 0
        ):
            record.calculation_version = version
            fields.append("calculation_version")
        if fields:
            record.save(update_fields=fields)

    for record in UnderlyingPositionRecord.objects.iterator():
        payload = record.payload if isinstance(record.payload, dict) else {}
        fields = []
        if record.quantity_kind is None and payload.get("quantity_kind") == "unit":
            record.quantity_kind = "unit"
            fields.append("quantity_kind")
        currency = payload.get("currency_unit")
        if record.currency_unit is None and currency in {"rial", "toman"}:
            record.currency_unit = currency
            fields.append("currency_unit")
        version = payload.get("calculation_version")
        if (
            record.calculation_version is None
            and isinstance(version, int)
            and not isinstance(version, bool)
            and version > 0
        ):
            record.calculation_version = version
            fields.append("calculation_version")
        if fields:
            record.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [("nicoption_dashboard", "0008_financial_contract_metadata")]

    operations = [
        migrations.RunPython(copy_explicit_metadata, migrations.RunPython.noop),
    ]
