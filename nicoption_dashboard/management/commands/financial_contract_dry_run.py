from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from io import StringIO
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from bambo_bot.financial_contract import normalize_exposure
from nicoption_dashboard.models import TradeRecord, UnderlyingPositionRecord


CLASSIFICATIONS = (
    "CONFIRMED_CONTRACT_QUANTITY",
    "CONFIRMED_UNDERLYING_UNITS",
    "AMBIGUOUS",
    "INVALID",
)


def decimal_or_none(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _metadata(record, payload: dict, key: str):
    column_value = getattr(record, key, None)
    return column_value if column_value not in (None, "") else payload.get(key)


def trade_evidence(record: TradeRecord) -> dict:
    payload = record.payload if isinstance(record.payload, dict) else {}
    quantity = decimal_or_none(payload.get("quantity"))
    contract_size = decimal_or_none(
        _metadata(record, payload, "contract_size")
    )
    quantity_kind = _metadata(record, payload, "quantity_kind")
    calculation_version = _metadata(record, payload, "calculation_version")
    currency_unit = _metadata(record, payload, "currency_unit")
    premium = decimal_or_none(payload.get("entry_premium"))
    current_value = (
        quantity * premium
        if quantity is not None and premium is not None
        else None
    )

    classification = "AMBIGUOUS"
    eligible = False
    proposed_value = None
    detected = "unknown"
    if quantity is None or contract_size is None or contract_size <= 0:
        classification = "INVALID"
    elif quantity_kind in {"contract", "unit"} and calculation_version not in (None, ""):
        detected = quantity_kind
        try:
            exposure = normalize_exposure(
                quantity=quantity,
                quantity_kind=quantity_kind,
                contract_size=contract_size,
                calculation_version=calculation_version,
            )
        except ValueError:
            classification = "INVALID"
        else:
            if quantity_kind == "contract":
                classification = "CONFIRMED_CONTRACT_QUANTITY"
                eligible = True
            else:
                classification = "CONFIRMED_UNDERLYING_UNITS"
                eligible = (
                    exposure.contract_quantity
                    == exposure.contract_quantity.to_integral_value()
                )
            proposed_value = (
                exposure.underlying_units * premium
                if premium is not None
                else None
            )

    signed_difference = (
        proposed_value - current_value
        if proposed_value is not None and current_value is not None
        else None
    )
    difference = abs(signed_difference) if signed_difference is not None else None
    relative = (
        difference / abs(current_value)
        if difference is not None and current_value not in (None, Decimal(0))
        else None
    )
    return {
        "record_type": "trade",
        "record_id": record.pk,
        "current_quantity": decimal_text(quantity),
        "current_contract_size": decimal_text(contract_size),
        "current_calculation_version": calculation_version,
        "detected_quantity_semantics": detected,
        "currency_unit": currency_unit,
        "financial_metric": "entry_premium_notional",
        "current_financial_value": decimal_text(current_value),
        "proposed_financial_value": decimal_text(proposed_value),
        "absolute_difference": decimal_text(difference),
        "relative_difference": decimal_text(relative),
        "classification": classification,
        "migration_eligible": eligible,
    }


def underlying_evidence(record: UnderlyingPositionRecord) -> dict:
    payload = record.payload if isinstance(record.payload, dict) else {}
    quantity = decimal_or_none(payload.get("quantity"))
    entry_price = decimal_or_none(payload.get("entry_price"))
    source_contracts = decimal_or_none(payload.get("source_contracts"))
    source_size = decimal_or_none(payload.get("source_contract_size"))
    current_value = (
        quantity * entry_price
        if quantity is not None and entry_price is not None
        else None
    )
    invalid_exercise = (
        payload.get("acquisition_method") == "exercise"
        and quantity is not None
        and source_contracts is not None
        and source_size is not None
        and source_size != 1
        and quantity == source_contracts
    )
    valid = quantity is not None and quantity > 0 and not invalid_exercise
    classification = "CONFIRMED_UNDERLYING_UNITS" if valid else "INVALID"
    return {
        "record_type": "underlying_position",
        "record_id": record.pk,
        "current_quantity": decimal_text(quantity),
        "current_contract_size": decimal_text(source_size),
        "current_calculation_version": _metadata(
            record, payload, "calculation_version"
        ),
        "detected_quantity_semantics": "unit" if valid else "invalid",
        "currency_unit": _metadata(record, payload, "currency_unit"),
        "financial_metric": "entry_position_notional",
        "current_financial_value": decimal_text(current_value),
        "proposed_financial_value": decimal_text(current_value) if valid else None,
        "absolute_difference": "0" if valid and current_value is not None else None,
        "relative_difference": "0" if valid and current_value is not None else None,
        "classification": classification,
        "migration_eligible": valid,
    }


class Command(BaseCommand):
    help = (
        "Produce a read-only financial quantity migration report. "
        "The command never updates records."
    )

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=("json", "csv"), default="json")
        parser.add_argument("--output", help="Optional output path; stdout by default")

    def handle(self, *args, **options):
        records = [
            *(trade_evidence(item) for item in TradeRecord.objects.order_by("id")),
            *(
                underlying_evidence(item)
                for item in UnderlyingPositionRecord.objects.order_by("id")
            ),
        ]
        summary = {classification: 0 for classification in CLASSIFICATIONS}
        for row in records:
            summary[row["classification"]] += 1
        report = {
            "dry_run": True,
            "writes_performed": 0,
            "canonical_currency_unit": "rial",
            "canonical_calculation_version": 8,
            "summary": summary,
            "records": records,
        }

        if options["format"] == "json":
            rendered = json.dumps(report, ensure_ascii=False, indent=2)
        else:
            buffer = StringIO()
            fieldnames = list(records[0]) if records else [
                "record_type", "record_id", "classification", "migration_eligible"
            ]
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
            rendered = buffer.getvalue()

        output = options.get("output")
        if output:
            path = Path(output).expanduser().resolve()
            try:
                path.write_text(rendered + ("" if rendered.endswith("\n") else "\n"), encoding="utf-8")
            except OSError as exc:
                raise CommandError(f"Could not write dry-run report: {exc}") from exc
            self.stdout.write(str(path))
        else:
            self.stdout.write(rendered)
