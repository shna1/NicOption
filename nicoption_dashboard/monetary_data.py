from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from functools import lru_cache
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data" / "monetary"
DATA_FILE = DATA_DIR / "iran_monetary_data_completed.csv"
METADATA_FILES = {
    "all": DATA_DIR / "monetary_columns_all.csv",
    "main": DATA_DIR / "monetary_columns_main.csv",
    "detailed": DATA_DIR / "monetary_columns_detailed.csv",
}
DATE_TECHNICAL_IDS = {"gregorian_date", "jalali_date"}
SUSPICIOUS_JALALI_DATES: set[str] = set()


class MonetaryDataError(RuntimeError):
    """Raised when the packaged monetary dataset or metadata is inconsistent."""


@dataclass(frozen=True)
class MonetaryMetadata:
    column_position: int
    column_name: str
    technical_id: str
    title_fa: str
    unit: str
    unit_scale: str
    frequency: str
    classification: str
    economic_group: str
    metric_type: str
    description_fa: str
    review_status: str
    source_file: str


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise MonetaryDataError(f"فایل داده پولی پیدا نشد: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _metadata(scope: str) -> list[MonetaryMetadata]:
    if scope not in METADATA_FILES:
        raise MonetaryDataError("دامنه شاخص‌های پولی معتبر نیست")
    items = []
    for row in _read_csv(METADATA_FILES[scope]):
        try:
            position = int(row["column_position"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MonetaryDataError(f"column_position نامعتبر در {METADATA_FILES[scope].name}") from exc
        items.append(
            MonetaryMetadata(
                column_position=position,
                column_name=row.get("column_name_in_source", "").strip(),
                technical_id=row.get("technical_id", "").strip(),
                title_fa=row.get("title_fa", "").strip(),
                unit=row.get("unit", "").strip(),
                unit_scale=row.get("unit_scale", "").strip(),
                frequency=row.get("frequency", "").strip(),
                classification=row.get("classification", "").strip(),
                economic_group=row.get("economic_group", "").strip(),
                metric_type=row.get("metric_type", "").strip(),
                description_fa=row.get("classification_reason", "").strip(),
                review_status=row.get("review_status", "").strip(),
                source_file=row.get("source_file", "").strip(),
            )
        )
    return sorted(items, key=lambda item: item.column_position)


def _month_key(jalali_date: str) -> tuple[int, int]:
    try:
        year, month, _ = (int(part) for part in jalali_date.split("-"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise MonetaryDataError(f"تاریخ شمسی نامعتبر است: {jalali_date!r}") from exc
    if not 1 <= month <= 12:
        raise MonetaryDataError(f"ماه شمسی نامعتبر است: {jalali_date!r}")
    return year, month


def _month_index(key: tuple[int, int]) -> int:
    return key[0] * 12 + key[1] - 1


def _format_month(index: int) -> str:
    year, zero_based_month = divmod(index, 12)
    return f"{year:04d}-{zero_based_month + 1:02d}"


def _decimal(value: str | None) -> Decimal | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _growth(current: Decimal | None, baseline: Decimal | None) -> Decimal | None:
    if current is None or baseline is None or baseline == 0:
        return None
    with localcontext() as context:
        context.prec = 38
        return ((current / baseline) - Decimal("1")) * Decimal("100")


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _validate_metadata(all_items: list[MonetaryMetadata], main_items: list[MonetaryMetadata], detailed_items: list[MonetaryMetadata], headers: list[str]) -> list[str]:
    conflicts: list[str] = []
    all_by_id = {item.technical_id: item for item in all_items}
    if len(all_by_id) != len(all_items):
        conflicts.append("technical_id تکراری در monetary_columns_all.csv")
    for scope, items in (("main", main_items), ("detailed", detailed_items)):
        for item in items:
            canonical = all_by_id.get(item.technical_id)
            if canonical is None:
                conflicts.append(f"{item.technical_id} در فایل {scope} وجود دارد اما در فایل all نیست")
                continue
            if item.column_name not in headers:
                conflicts.append(f"ستون {item.column_name} برای {item.technical_id} در فایل داده وجود ندارد")
            for field in ("title_fa", "unit", "unit_scale", "column_position"):
                if getattr(item, field) != getattr(canonical, field):
                    conflicts.append(f"فراداده {field} برای {item.technical_id} بین فایل {scope} و all متفاوت است")
    main_ids = {item.technical_id for item in main_items} - DATE_TECHNICAL_IDS
    detailed_ids = {item.technical_id for item in detailed_items} - DATE_TECHNICAL_IDS
    overlap = sorted(main_ids & detailed_ids)
    if overlap:
        conflicts.append("شاخص مشترک میان main و detailed: " + "، ".join(overlap))
    return conflicts


@lru_cache(maxsize=1)
def monetary_dataset() -> dict:
    all_items = _metadata("all")
    main_items = _metadata("main")
    detailed_items = _metadata("detailed")
    rows = _read_csv(DATA_FILE)
    headers = list(rows[0].keys()) if rows else []
    conflicts = _validate_metadata(all_items, main_items, detailed_items, headers)

    prepared_rows = []
    duplicate_jalali_months: list[str] = []
    duplicate_gregorian_dates: list[str] = []
    seen_months: set[tuple[int, int]] = set()
    seen_gregorian: set[str] = set()
    for row in rows:
        jalali_date = row.get("تاریخ_شمسی", "").strip()
        gregorian_date = row.get("تاریخ_میلادی", "").strip()
        key = _month_key(jalali_date)
        if key in seen_months:
            duplicate_jalali_months.append(f"{key[0]:04d}-{key[1]:02d}")
        seen_months.add(key)
        if gregorian_date in seen_gregorian:
            duplicate_gregorian_dates.append(gregorian_date)
        seen_gregorian.add(gregorian_date)
        prepared_rows.append((key, gregorian_date, jalali_date, row))
    prepared_rows.sort(key=lambda item: _month_index(item[0]))

    missing_months: list[str] = []
    for previous, current in zip(prepared_rows, prepared_rows[1:]):
        previous_index = _month_index(previous[0])
        current_index = _month_index(current[0])
        missing_months.extend(_format_month(index) for index in range(previous_index + 1, current_index))

    metadata_by_scope = {
        "all": [item for item in all_items if item.technical_id not in DATE_TECHNICAL_IDS],
        "main": [item for item in main_items if item.technical_id not in DATE_TECHNICAL_IDS],
        "detailed": [item for item in detailed_items if item.technical_id not in DATE_TECHNICAL_IDS],
    }
    indicators_by_scope: dict[str, list[dict]] = {}
    non_numeric: list[dict] = []
    for scope, items in metadata_by_scope.items():
        indicators = []
        for item in items:
            values_by_month: dict[tuple[int, int], Decimal | None] = {}
            raw_by_month: dict[tuple[int, int], str] = {}
            for key, _, _, row in prepared_rows:
                raw = str(row.get(item.column_name, "") or "").strip()
                value = _decimal(raw)
                values_by_month[key] = value
                raw_by_month[key] = raw
                if raw and value is None:
                    non_numeric.append({"technical_id": item.technical_id, "jalali_month": f"{key[0]:04d}-{key[1]:02d}", "value": raw})
            series = []
            for key, gregorian_date, jalali_date, _ in prepared_rows:
                current = values_by_month[key]
                index = _month_index(key)
                previous_key = divmod(index - 1, 12)
                previous_year_key = divmod(index - 12, 12)
                previous_month = (previous_key[0], previous_key[1] + 1)
                previous_year_month = (previous_year_key[0], previous_year_key[1] + 1)
                series.append(
                    {
                        "date": gregorian_date,
                        "jalali_date": jalali_date,
                        "year_month": f"{key[0]:04d}-{key[1]:02d}",
                        "value": _decimal_text(current),
                        "monthly_growth_percent": _decimal_text(_growth(current, values_by_month.get(previous_month))),
                        "yearly_growth_percent": _decimal_text(_growth(current, values_by_month.get(previous_year_month))),
                        "is_suspicious": jalali_date in SUSPICIOUS_JALALI_DATES,
                        "raw_value": raw_by_month[key] if current is None and raw_by_month[key] else None,
                    }
                )
            available = [point for point in series if point["value"] is not None]
            indicators.append(
                {
                    "technical_id": item.technical_id,
                    "title_fa": item.title_fa,
                    "column_position": item.column_position,
                    "unit": item.unit,
                    "unit_scale": item.unit_scale,
                    "frequency": item.frequency,
                    "classification": item.classification,
                    "economic_group": item.economic_group,
                    "metric_type": item.metric_type,
                    "description_fa": item.description_fa,
                    "review_status": item.review_status,
                    "source_file": item.source_file,
                    "current": available[-1] if available else None,
                    "series": series,
                }
            )
        indicators_by_scope[scope] = indicators

    quality = {
        "row_count": len(rows),
        "missing_months": missing_months,
        "duplicate_jalali_months": duplicate_jalali_months,
        "duplicate_gregorian_dates": duplicate_gregorian_dates,
        "non_numeric_values": non_numeric,
        "metadata_conflicts": conflicts,
        "suspicious_periods": sorted(SUSPICIOUS_JALALI_DATES),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": [DATA_FILE.name, *(path.name for path in METADATA_FILES.values())],
        "quality": quality,
        "indicators": indicators_by_scope,
    }


def monetary_payload(scope: str) -> dict:
    if scope not in {"all", "main", "detailed"}:
        raise MonetaryDataError("scope باید all، main یا detailed باشد")
    dataset = monetary_dataset()
    return {
        "generated_at": dataset["generated_at"],
        "scope": scope,
        "source_files": dataset["source_files"],
        "quality": dataset["quality"],
        "indicators": dataset["indicators"][scope],
    }
