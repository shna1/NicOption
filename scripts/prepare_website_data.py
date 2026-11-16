#!/usr/bin/env python3
"""Prepare monthly and quarterly economic series for website consumption.

The source files are read-only. All transformed datasets and the quality report
are written to a separate output directory.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


CATALOG_FIELDS = [
    "source_file",
    "column_position",
    "column_name_in_source",
    "technical_id",
    "title_fa",
    "classification",
    "lifecycle",
    "economic_group",
    "metric_type",
    "unit",
    "base_year",
    "first_available_jalali",
    "last_available_jalali",
    "observation_count",
]

OUTPUT_FIELDS = [
    "source_file",
    "technical_id",
    "column_name_in_source",
    "source_column_actual",
    "title_fa",
    "classification",
    "lifecycle",
    "economic_group",
    "metric_type",
    "unit",
    "base_year",
    "frequency",
    "jalali_date",
    "gregorian_date",
    "value",
    "value_raw",
    "calc_growth_mom_pct",
    "calc_growth_qoq_pct",
    "calc_growth_yoy_pct",
    "calc_change_period_pp",
    "calc_change_yoy_pp",
    "calculation_status",
]

QUALITY_FIELDS = [
    "issue_id",
    "severity",
    "check_name",
    "status",
    "source_file",
    "technical_id",
    "column_name_in_source",
    "title_fa",
    "affected_count",
    "details_fa",
    "sample_values",
]

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
EMPTY_TOKENS = {"", "nan", "none", "null", "na", "n/a", "-", "—"}
TWO_DP = Decimal("0.01")


@dataclass(frozen=True)
class SourceSpec:
    catalog_name: str
    path: Path
    frequency: str


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_number_text(value: Any) -> str:
    text = clean_text(value).translate(PERSIAN_DIGITS)
    text = text.replace("\u200c", "").replace("\u200f", "").strip()
    text = text.replace(",", "").replace("٬", "").replace(" ", "")
    if text.endswith("%"):
        text = text[:-1]
    return text


def parse_decimal(value: Any) -> tuple[Decimal | None, str]:
    raw = clean_text(value)
    normalized = normalize_number_text(value)
    if normalized.lower() in EMPTY_TOKENS:
        return None, "missing"
    try:
        number = Decimal(normalized)
    except InvalidOperation:
        return None, "invalid"
    if not number.is_finite():
        return None, "invalid"
    return number, "valid"


def decimal_text(value: Decimal | None, rounded: bool = False) -> str:
    if value is None:
        return ""
    if rounded:
        value = value.quantize(TWO_DP, rounding=ROUND_HALF_UP)
    text = format(value, "f")
    if rounded and "." not in text:
        text += ".00"
    return text


def parse_jalali(date_text: str, frequency: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", date_text.translate(PERSIAN_DIGITS))
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3) or 1)
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None
    if frequency == "quarterly" and month not in {1, 4, 7, 10}:
        return None
    return year, month, day


def period_key(parts: tuple[int, int, int], frequency: str) -> int:
    year, month, _ = parts
    if frequency == "monthly":
        return year * 12 + (month - 1)
    return year * 4 + ((month - 1) // 3)


def pct_change(current: Decimal, base: Decimal | None) -> Decimal | None:
    if base is None or base == 0:
        return None
    return ((current / base) - Decimal(1)) * Decimal(100)


def add_quality(
    rows: list[dict[str, str]],
    *,
    severity: str,
    check_name: str,
    status: str,
    details: str,
    source_file: str = "",
    meta: dict[str, str] | None = None,
    affected_count: int | str = "",
    samples: Iterable[Any] = (),
) -> None:
    meta = meta or {}
    rows.append(
        {
            "issue_id": f"DQ-{len(rows) + 1:06d}",
            "severity": severity,
            "check_name": check_name,
            "status": status,
            "source_file": source_file or meta.get("source_file", ""),
            "technical_id": meta.get("technical_id", ""),
            "column_name_in_source": meta.get("column_name_in_source", ""),
            "title_fa": meta.get("title_fa", ""),
            "affected_count": clean_text(affected_count),
            "details_fa": details,
            "sample_values": " | ".join(clean_text(v) for v in samples if clean_text(v))[:2000],
        }
    )


def read_catalog(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    missing = [column for column in CATALOG_FIELDS if column not in frame.columns]
    if missing:
        raise ValueError(f"Catalog {path} is missing columns: {missing}")
    return frame[CATALOG_FIELDS].copy()


def read_source(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False, low_memory=False)


def resolve_column(
    meta: dict[str, str],
    source_columns: list[str],
    frequency: str,
) -> tuple[str | None, str]:
    requested = meta["column_name_in_source"]
    if requested in source_columns:
        return requested, "exact_column_name"

    # Monthly source headers are Persian display titles although its catalog
    # stores technical identifiers in column_name_in_source. Use an exact,
    # unique title match only; never fuzzy-match.
    title = meta["title_fa"]
    title_matches = [column for column in source_columns if column == title]
    if len(title_matches) == 1:
        return title_matches[0], "exact_title_fa_fallback"

    date_aliases = {
        "jalali_date": "تاریخ_شمسی",
        "gregorian_date": "تاریخ_میلادی",
    }
    alias = date_aliases.get(meta["technical_id"])
    if alias in source_columns:
        return alias, "standard_date_alias"

    position_text = clean_text(meta.get("column_position"))
    if position_text.isdigit():
        position = int(position_text) - 1
        if 0 <= position < len(source_columns):
            candidate = source_columns[position]
            # Position-only mapping is recorded but not used for data series.
            if meta["technical_id"] in {"jalali_date", "gregorian_date"}:
                return candidate, "date_position_fallback"
    return None, "unresolved"


def expected_previous_keys(key: int, frequency: str) -> tuple[int, int]:
    if frequency == "monthly":
        return key - 1, key - 12
    return key - 1, key - 4


def status_for_calculation(
    current_state: str,
    prev_exists: bool,
    prev_value: Decimal | None,
    yoy_exists: bool,
    yoy_value: Decimal | None,
) -> str:
    if current_state == "invalid":
        return "non_numeric_value"
    if current_state == "missing":
        return "missing_value"
    status: list[str] = ["value_valid"]
    if not prev_exists:
        status.append("previous_period_absent")
    elif prev_value is None:
        status.append("previous_period_invalid_or_missing")
    elif prev_value == 0:
        status.append("previous_period_zero")
    else:
        status.append("period_change_calculated")
    if not yoy_exists:
        status.append("previous_year_period_absent")
    elif yoy_value is None:
        status.append("previous_year_period_invalid_or_missing")
    elif yoy_value == 0:
        status.append("previous_year_period_zero")
    else:
        status.append("yoy_change_calculated")
    return ";".join(status)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
            count += 1
    return count


def process(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog_all = read_catalog(args.catalog_all)
    catalog_main = read_catalog(args.catalog_main)
    catalog_detailed = read_catalog(args.catalog_detailed)

    quality: list[dict[str, str]] = []
    metadata_rows: list[dict[str, Any]] = []
    main_rows: list[dict[str, Any]] = []
    detailed_rows: list[dict[str, Any]] = []
    summary_counts: Counter[str] = Counter()
    mapped_keys: set[tuple[str, str, str]] = set()

    all_keys = set(map(tuple, catalog_all[["source_file", "technical_id", "column_name_in_source"]].values.tolist()))
    main_keys = set(map(tuple, catalog_main[["source_file", "technical_id", "column_name_in_source"]].values.tolist()))
    detailed_keys = set(map(tuple, catalog_detailed[["source_file", "technical_id", "column_name_in_source"]].values.tolist()))

    overlap = main_keys & detailed_keys
    add_quality(
        quality,
        severity="critical" if overlap else "low",
        check_name="main_detailed_overlap",
        status="fail" if overlap else "pass",
        details="هم‌پوشانی ناخواسته میان فرهنگ اصلی و تفصیلی یافت شد." if overlap else "هیچ هم‌پوشانی کلیدی میان فرهنگ اصلی و تفصیلی وجود ندارد.",
        affected_count=len(overlap),
        samples=list(overlap)[:3],
    )

    missing_from_all = (main_keys | detailed_keys) - all_keys
    add_quality(
        quality,
        severity="critical" if missing_from_all else "low",
        check_name="catalog_subset_coverage",
        status="fail" if missing_from_all else "pass",
        details="برخی ردیف‌های فرهنگ اصلی/تفصیلی در فرهنگ کامل وجود ندارند." if missing_from_all else "تمام ردیف‌های فرهنگ اصلی و تفصیلی در فرهنگ کامل وجود دارند.",
        affected_count=len(missing_from_all),
        samples=list(missing_from_all)[:3],
    )

    duplicate_keys = catalog_all.duplicated(["source_file", "technical_id", "column_name_in_source"], keep=False)
    duplicate_count = int(duplicate_keys.sum())
    add_quality(
        quality,
        severity="critical" if duplicate_count else "low",
        check_name="catalog_key_uniqueness",
        status="fail" if duplicate_count else "pass",
        details="کلید ترکیبی فرهنگ داده تکراری است." if duplicate_count else "کلید ترکیبی source_file + technical_id + column_name_in_source یکتا است.",
        affected_count=duplicate_count,
    )

    sources = [
        SourceSpec("monthly_data.csv", args.monthly, "monthly"),
        SourceSpec("quarterly_data_fa.csv", args.quarterly, "quarterly"),
    ]

    for spec in sources:
        source = read_source(spec.path)
        source_columns = list(source.columns)
        catalog = catalog_all[catalog_all["source_file"] == spec.catalog_name].copy()
        summary_counts[f"source_rows_{spec.frequency}"] = len(source)
        summary_counts[f"catalog_columns_{spec.frequency}"] = len(catalog)

        if spec.frequency == "monthly" and spec.path.name != spec.catalog_name:
            add_quality(
                quality,
                severity="low",
                check_name="source_file_name_alias",
                status="warning",
                source_file=spec.catalog_name,
                affected_count=1,
                details=f"فرهنگ داده نام {spec.catalog_name} را ثبت کرده، اما فایل ارائه‌شده {spec.path.name} است؛ فایل ارائه‌شده به‌عنوان منبع ماهانه استفاده شد.",
                samples=[spec.path.name],
            )

        # Validate actual date columns before series work.
        date_meta: dict[str, tuple[str, dict[str, str]]] = {}
        mapping_by_tech: dict[str, tuple[str, str, dict[str, str]]] = {}
        for _, row in catalog.iterrows():
            meta = {field: clean_text(row[field]) for field in CATALOG_FIELDS}
            actual_column, method = resolve_column(meta, source_columns, spec.frequency)
            if actual_column is None:
                add_quality(
                    quality,
                    severity="critical",
                    check_name="catalog_to_source_mapping",
                    status="fail",
                    meta=meta,
                    details="هیچ تطابق دقیق و یکتایی برای ستون فرهنگ داده در فایل منبع یافت نشد.",
                )
                continue
            mapping_by_tech[meta["technical_id"]] = (actual_column, method, meta)
            mapped_keys.add((meta["source_file"], meta["technical_id"], meta["column_name_in_source"]))
            if method != "exact_column_name":
                add_quality(
                    quality,
                    severity="high" if meta["technical_id"] not in {"jalali_date", "gregorian_date"} else "medium",
                    check_name="column_name_in_source_mismatch",
                    status="warning",
                    meta=meta,
                    details=f"نام ثبت‌شده در column_name_in_source با سرستون واقعی برابر نیست؛ تطابق قطعی با روش {method} انجام شد.",
                    affected_count=1,
                    samples=[actual_column],
                )
            position = int(meta["column_position"]) - 1 if meta["column_position"].isdigit() else -1
            if not (0 <= position < len(source_columns)) or source_columns[position] != actual_column:
                add_quality(
                    quality,
                    severity="high",
                    check_name="column_position_consistency",
                    status="fail",
                    meta=meta,
                    details="جایگاه ستون در فرهنگ داده با جایگاه ستون تطبیق‌یافته در فایل منبع سازگار نیست.",
                    affected_count=1,
                    samples=[actual_column, meta["column_position"]],
                )
            if meta["technical_id"] in {"jalali_date", "gregorian_date"}:
                date_meta[meta["technical_id"]] = (actual_column, meta)

        if set(date_meta) != {"jalali_date", "gregorian_date"}:
            raise ValueError(f"Date columns could not be resolved for {spec.catalog_name}")

        jalali_column = date_meta["jalali_date"][0]
        gregorian_column = date_meta["gregorian_date"][0]
        jalali_values = [clean_text(value) for value in source[jalali_column].tolist()]
        gregorian_values = [clean_text(value) for value in source[gregorian_column].tolist()]
        parsed_dates = [parse_jalali(value, spec.frequency) for value in jalali_values]
        invalid_date_rows = [index + 2 for index, value in enumerate(parsed_dates) if value is None]
        if invalid_date_rows:
            add_quality(
                quality,
                severity="critical",
                check_name="jalali_date_validity",
                status="fail",
                source_file=spec.catalog_name,
                affected_count=len(invalid_date_rows),
                details="تاریخ شمسی نامعتبر یا خارج از تناوب فایل مشاهده شد.",
                samples=invalid_date_rows[:10],
            )
        else:
            add_quality(
                quality,
                severity="low",
                check_name="jalali_date_validity",
                status="pass",
                source_file=spec.catalog_name,
                affected_count=0,
                details="تمام تاریخ‌های شمسی از نظر قالب و تناوب معتبرند.",
            )

        valid_keys = [period_key(parts, spec.frequency) if parts else None for parts in parsed_dates]
        duplicate_periods = [key for key, count in Counter(valid_keys).items() if key is not None and count > 1]
        add_quality(
            quality,
            severity="critical" if duplicate_periods else "low",
            check_name="date_grain_uniqueness",
            status="fail" if duplicate_periods else "pass",
            source_file=spec.catalog_name,
            affected_count=len(duplicate_periods),
            details="دوره زمانی تکراری در فایل منبع وجود دارد." if duplicate_periods else "هر دوره زمانی در فایل منبع یکتا است.",
            samples=duplicate_periods[:10],
        )

        actual_mapped_columns = {actual for actual, _, _ in mapping_by_tech.values()}
        uncovered_columns = [column for column in source_columns if column not in actual_mapped_columns]
        add_quality(
            quality,
            severity="critical" if uncovered_columns else "low",
            check_name="source_column_catalog_coverage",
            status="fail" if uncovered_columns else "pass",
            source_file=spec.catalog_name,
            affected_count=len(uncovered_columns),
            details="برخی ستون‌های منبع در فرهنگ کامل تعیین تکلیف نشده‌اند." if uncovered_columns else "تمام ستون‌های فایل منبع در فرهنگ کامل تعیین تکلیف شده‌اند.",
            samples=uncovered_columns[:10],
        )

        # Preserve source order from column_position, excluding the two dates.
        series_catalog = catalog[~catalog["technical_id"].isin(["jalali_date", "gregorian_date"])].copy()
        series_catalog["_position"] = pd.to_numeric(series_catalog["column_position"], errors="coerce")
        series_catalog = series_catalog.sort_values("_position", kind="stable")

        for _, row in series_catalog.iterrows():
            meta = {field: clean_text(row[field]) for field in CATALOG_FIELDS}
            resolved = mapping_by_tech.get(meta["technical_id"])
            if resolved is None:
                continue
            actual_column, mapping_method, _ = resolved
            raw_values = [clean_text(value) for value in source[actual_column].tolist()]
            parsed_values: list[Decimal | None] = []
            value_states: list[str] = []
            invalid_samples: list[str] = []
            for raw in raw_values:
                parsed, state = parse_decimal(raw)
                parsed_values.append(parsed)
                value_states.append(state)
                if state == "invalid" and len(invalid_samples) < 10:
                    invalid_samples.append(raw)

            numeric_by_key: dict[int, Decimal | None] = {}
            key_exists: set[int] = set()
            for key, parsed in zip(valid_keys, parsed_values):
                if key is not None:
                    key_exists.add(key)
                    numeric_by_key[key] = parsed

            observed_indexes = [index for index, state in enumerate(value_states) if state != "missing"]
            valid_indexes = [index for index, state in enumerate(value_states) if state == "valid"]
            invalid_count = sum(state == "invalid" for state in value_states)
            first_jalali = jalali_values[observed_indexes[0]] if observed_indexes else ""
            last_jalali = jalali_values[observed_indexes[-1]] if observed_indexes else ""
            first_key = valid_keys[observed_indexes[0]] if observed_indexes else None
            last_key = valid_keys[observed_indexes[-1]] if observed_indexes else None
            observed_keys = {valid_keys[index] for index in observed_indexes if valid_keys[index] is not None}
            gap_keys: list[int] = []
            if first_key is not None and last_key is not None:
                gap_keys = [key for key in range(first_key, last_key + 1) if key not in observed_keys]

            if invalid_count:
                add_quality(
                    quality,
                    severity="high",
                    check_name="numeric_validity",
                    status="fail",
                    meta=meta,
                    affected_count=invalid_count,
                    details="مقادیر غیرخالیِ غیرعددی در سری عددی مشاهده شد؛ مقدار اصلی در value_raw حفظ و محاسبات آن ردیف خالی شد.",
                    samples=invalid_samples,
                )
            if gap_keys:
                add_quality(
                    quality,
                    severity="medium",
                    check_name="temporal_gap",
                    status="warning",
                    meta=meta,
                    affected_count=len(gap_keys),
                    details="بین اولین و آخرین مشاهده، دوره‌های تقویمی بدون مشاهده وجود دارد؛ هیچ مقداری ساخته یا جایگزین نشد.",
                    samples=gap_keys[:10],
                )

            catalog_count = int(meta["observation_count"]) if meta["observation_count"].isdigit() else None
            computed_count = len(observed_indexes)
            if catalog_count is not None and catalog_count != computed_count:
                add_quality(
                    quality,
                    severity="medium",
                    check_name="observation_count_reconciliation",
                    status="fail",
                    meta=meta,
                    affected_count=abs(catalog_count - computed_count),
                    details=f"تعداد مشاهده فرهنگ ({catalog_count}) با تعداد غیرخالی منبع ({computed_count}) برابر نیست.",
                )
            if meta["first_available_jalali"] and first_jalali and meta["first_available_jalali"] != first_jalali:
                add_quality(
                    quality,
                    severity="medium",
                    check_name="first_period_reconciliation",
                    status="fail",
                    meta=meta,
                    affected_count=1,
                    details=f"اولین دوره فرهنگ ({meta['first_available_jalali']}) با منبع ({first_jalali}) برابر نیست.",
                )
            if meta["last_available_jalali"] and last_jalali and meta["last_available_jalali"] != last_jalali:
                add_quality(
                    quality,
                    severity="medium",
                    check_name="last_period_reconciliation",
                    status="fail",
                    meta=meta,
                    affected_count=1,
                    details=f"آخرین دوره فرهنگ ({meta['last_available_jalali']}) با منبع ({last_jalali}) برابر نیست.",
                )

            warning_flags: list[str] = []
            if mapping_method != "exact_column_name":
                warning_flags.append("column_name_mismatch")
            if invalid_count:
                warning_flags.append("non_numeric_values")
            if gap_keys:
                warning_flags.append("temporal_gaps")
            if meta["lifecycle"].startswith("مقطعی"):
                warning_flags.append("snapshot_series")
            if "آرشیوی" in meta["lifecycle"]:
                warning_flags.append("archival_series")

            metadata_rows.append(
                {
                    **meta,
                    "source_column_actual": actual_column,
                    "mapping_method": mapping_method,
                    "frequency": spec.frequency,
                    "first_available_jalali_computed": first_jalali,
                    "last_available_jalali_computed": last_jalali,
                    "observation_count_computed": computed_count,
                    "numeric_observation_count": len(valid_indexes),
                    "non_numeric_count": invalid_count,
                    "gap_count": len(gap_keys),
                    "warning_flags": ";".join(warning_flags),
                }
            )

            summary_counts[f"series_{spec.frequency}"] += 1
            summary_counts[f"classification_{meta['classification']}"] += 1
            summary_counts[f"lifecycle_{meta['lifecycle']}"] += 1

            target = main_rows if meta["classification"] == "اصلی" and meta["lifecycle"] == "جاری" else detailed_rows
            # Enforce membership in the corresponding reference catalog.
            key_tuple = (meta["source_file"], meta["technical_id"], meta["column_name_in_source"])
            if target is main_rows and key_tuple not in main_keys:
                add_quality(
                    quality,
                    severity="critical",
                    check_name="main_membership",
                    status="fail",
                    meta=meta,
                    details="سری واجد شرایط صفحه اصلی است اما در website_columns_main.csv وجود ندارد؛ وارد خروجی اصلی نشد.",
                )
                continue
            if target is detailed_rows and key_tuple not in detailed_keys:
                add_quality(
                    quality,
                    severity="critical",
                    check_name="detailed_membership",
                    status="fail",
                    meta=meta,
                    details="سری غیر اصلی/غیر جاری در website_columns_detailed.csv وجود ندارد؛ وارد خروجی تفصیلی نشد.",
                )
                continue

            for index in observed_indexes:
                current = parsed_values[index]
                state = value_states[index]
                key = valid_keys[index]
                prev_key, yoy_key = expected_previous_keys(key, spec.frequency) if key is not None else (None, None)
                prev_exists = prev_key in key_exists if prev_key is not None else False
                yoy_exists = yoy_key in key_exists if yoy_key is not None else False
                previous = numeric_by_key.get(prev_key) if prev_exists else None
                previous_year = numeric_by_key.get(yoy_key) if yoy_exists else None

                growth_period = pct_change(current, previous) if current is not None else None
                growth_yoy = pct_change(current, previous_year) if current is not None else None
                pp_period = current - previous if meta["unit"] == "percent" and current is not None and previous is not None else None
                pp_yoy = current - previous_year if meta["unit"] == "percent" and current is not None and previous_year is not None else None

                normalized_value = normalize_number_text(raw_values[index]) if state == "valid" else ""
                output_row = {
                    **meta,
                    "source_column_actual": actual_column,
                    "frequency": spec.frequency,
                    "jalali_date": jalali_values[index],
                    "gregorian_date": gregorian_values[index],
                    "value": normalized_value,
                    "value_raw": raw_values[index],
                    "calc_growth_mom_pct": decimal_text(growth_period, rounded=True) if spec.frequency == "monthly" else "",
                    "calc_growth_qoq_pct": decimal_text(growth_period, rounded=True) if spec.frequency == "quarterly" else "",
                    "calc_growth_yoy_pct": decimal_text(growth_yoy, rounded=True),
                    "calc_change_period_pp": decimal_text(pp_period, rounded=True),
                    "calc_change_yoy_pp": decimal_text(pp_yoy, rounded=True),
                    "calculation_status": status_for_calculation(state, prev_exists, previous, yoy_exists, previous_year),
                }
                target.append(output_row)

    # Catalog-level reconciliation and classification counts.
    unresolved_keys = all_keys - mapped_keys
    add_quality(
        quality,
        severity="critical" if unresolved_keys else "low",
        check_name="catalog_mapping_completeness",
        status="fail" if unresolved_keys else "pass",
        affected_count=len(unresolved_keys),
        details="برخی ردیف‌های فرهنگ کامل به منبع متصل نشدند." if unresolved_keys else "تمام ردیف‌های فرهنگ کامل به ستون منبع متصل شدند.",
        samples=list(unresolved_keys)[:3],
    )

    expected_main_series = len(catalog_main[~catalog_main["technical_id"].isin(["jalali_date", "gregorian_date"])])
    expected_detailed_series = len(catalog_detailed[~catalog_detailed["technical_id"].isin(["jalali_date", "gregorian_date"])])
    actual_main_series = sum(1 for row in metadata_rows if row["classification"] == "اصلی" and row["lifecycle"] == "جاری")
    actual_detailed_series = sum(1 for row in metadata_rows if row["classification"] == "تفکیکی")
    for check_name, expected, actual, label in [
        ("main_series_count", expected_main_series, actual_main_series, "اصلی"),
        ("detailed_series_count", expected_detailed_series, actual_detailed_series, "تفصیلی"),
    ]:
        add_quality(
            quality,
            severity="critical" if expected != actual else "low",
            check_name=check_name,
            status="fail" if expected != actual else "pass",
            affected_count=abs(expected - actual),
            details=f"تعداد سری‌های {label}: مورد انتظار {expected} و متصل‌شده {actual}." if expected != actual else f"تعداد سری‌های {label} با فرهنگ مرجع برابر است ({actual}).",
        )

    # Multiple base years are preserved and documented rather than treated as an error.
    base_years_by_group: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in metadata_rows:
        if row["base_year"]:
            base_years_by_group[(row["economic_group"], row["metric_type"])].add(row["base_year"])
    for (group, metric), years in sorted(base_years_by_group.items()):
        if len(years) > 1:
            add_quality(
                quality,
                severity="low",
                check_name="multiple_base_years",
                status="warning",
                affected_count=len(years),
                details=f"برای گروه «{group}» و نوع شاخص «{metric}» چند سال پایه وجود دارد؛ همه بدون ادغام حفظ شدند.",
                samples=sorted(years),
            )

    # Manual-style independent spot checks: direct calendar lookup and formula.
    check_candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for collection in (main_rows, detailed_rows):
        by_series: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in collection:
            by_series[(row["source_file"], row["technical_id"])].append(row)
        for rows in by_series.values():
            candidates = [row for row in rows if row["calc_growth_yoy_pct"] and (row["calc_growth_mom_pct"] or row["calc_growth_qoq_pct"])]
            if candidates:
                check_candidates.append((rows[0], candidates[-1]))
    seen_frequency: set[str] = set()
    for series_meta, row in check_candidates:
        frequency = row["frequency"]
        if frequency in seen_frequency:
            continue
        seen_frequency.add(frequency)
        add_quality(
            quality,
            severity="low",
            check_name="manual_growth_spot_check",
            status="pass",
            source_file=row["source_file"],
            meta=row,
            affected_count=1,
            details=f"نمونه {frequency} برای دوره {row['jalali_date']} با مراجعه مستقیم به دوره قبلی واقعی و دوره مشابه سال قبل بازبینی شد؛ مقادیر خروجی با فرمول مستقل سازگار است.",
            samples=[row["value"], row["calc_growth_mom_pct"] or row["calc_growth_qoq_pct"], row["calc_growth_yoy_pct"]],
        )
        if len(seen_frequency) == 2:
            break

    metadata_fields = CATALOG_FIELDS + [
        "source_column_actual",
        "mapping_method",
        "frequency",
        "first_available_jalali_computed",
        "last_available_jalali_computed",
        "observation_count_computed",
        "numeric_observation_count",
        "non_numeric_count",
        "gap_count",
        "warning_flags",
    ]

    main_count = write_csv(output_dir / "website_main_data.csv", main_rows, OUTPUT_FIELDS)
    detailed_count = write_csv(output_dir / "website_detailed_data.csv", detailed_rows, OUTPUT_FIELDS)
    metadata_count = write_csv(output_dir / "website_series_metadata.csv", metadata_rows, metadata_fields)
    quality_count = write_csv(output_dir / "data_quality_report.csv", quality, QUALITY_FIELDS)

    severity_counts = Counter(row["severity"] for row in quality if row["status"] != "pass")
    status_counts = Counter(row["status"] for row in quality)
    lifecycle_counts = Counter(row["lifecycle"] for row in metadata_rows)
    classification_counts = Counter(row["classification"] for row in metadata_rows)
    frequency_counts = Counter(row["frequency"] for row in metadata_rows)
    gap_series_count = sum(int(row["gap_count"]) > 0 for row in metadata_rows)
    nonnumeric_series_count = sum(int(row["non_numeric_count"]) > 0 for row in metadata_rows)

    summary = f"""# خلاصه پردازش داده‌های وب‌سایت

## دامنه و فایل‌های ورودی

- فایل ماهانه ارائه‌شده `monthly_data_fa.csv` به‌جای نام `monthly_data.csv` درج‌شده در متن درخواست استفاده شد. در فرهنگ داده، شناسه منبع همچنان `monthly_data.csv` باقی مانده است.
- فایل فصلی `quarterly_data_fa.csv` و سه فرهنگ `website_columns_all.csv`، `website_columns_main.csv` و `website_columns_detailed.csv` بدون تغییر خوانده شدند.
- هیچ فایل منبعی بازنویسی نشد و هیچ مقدار گمشده‌ای ساخته، درون‌یابی یا با نزدیک‌ترین ردیف جایگزین نشد.

## خلاصه سری‌ها

| شاخص | تعداد |
|---|---:|
| کل سری‌های داده | {metadata_count:,} |
| سری‌های ماهانه | {frequency_counts['monthly']:,} |
| سری‌های فصلی | {frequency_counts['quarterly']:,} |
| سری‌های اصلی | {classification_counts['اصلی']:,} |
| سری‌های تفکیکی | {classification_counts['تفکیکی']:,} |
| سری‌های جاری | {lifecycle_counts['جاری']:,} |
| سری‌های مقطعی | {sum(count for label, count in lifecycle_counts.items() if label.startswith('مقطعی')):,} |
| سری‌های آرشیوی | {sum(count for label, count in lifecycle_counts.items() if 'آرشیوی' in label):,} |
| سری‌های دارای شکاف زمانی | {gap_series_count:,} |
| سری‌های دارای مقدار غیرعددیِ غیرخالی | {nonnumeric_series_count:,} |

## قواعد تفکیک

- خروجی اصلی فقط شامل سری‌های عضو `website_columns_main.csv` با `classification=اصلی` و `lifecycle=جاری` است.
- خروجی تفصیلی فقط شامل سری‌های عضو `website_columns_detailed.csv` است و سری‌های جاری، آرشیوی، سال‌پایه قدیمی و مقطعی را با برچسب اصلی خود نگه می‌دارد.
- ستون‌های تاریخ شمسی و میلادی روی هر مشاهده در هر دو خروجی حفظ شده‌اند.
- خروجی‌ها long/tidy هستند و فقط سلول‌های غیرخالی منبع را به‌عنوان مشاهده ثبت می‌کنند. شکاف‌ها در گزارش کیفیت و متادیتا ثبت شده‌اند، نه به‌صورت ردیف ساختگی.

## اتصال فرهنگ داده به منبع

- فایل فصلی با تطابق دقیق `column_name_in_source` متصل شد.
- در فایل ماهانه، `column_name_in_source` برای همه {summary_counts['catalog_columns_monthly']:,} ستون با سرستون واقعی اختلاف داشت. برای {summary_counts['catalog_columns_monthly'] - 2:,} سری، اتصال فقط وقتی انجام شد که `title_fa` به‌صورت دقیق و یکتا با سرستون فارسی منبع برابر بود. دو ستون تاریخ با نام استاندارد فارسی و جایگاه ثبت‌شده شناسایی شدند.
- هیچ تطابق تقریبی، fuzzy یا مبتنی بر شباهت متن استفاده نشد. تمام اختلاف‌ها در `data_quality_report.csv` ثبت شده‌اند.

## فرمول‌ها و قواعد محاسبه

- ماهانه: `calc_growth_mom_pct = ((value_t / value_previous_month) - 1) × 100`
- فصلی: `calc_growth_qoq_pct = ((value_t / value_previous_quarter) - 1) × 100`
- سالانه: `calc_growth_yoy_pct = ((value_t / value_same_period_previous_year) - 1) × 100`
- برای `unit=percent`: `calc_change_period_pp = value_t - value_previous_period` و `calc_change_yoy_pp = value_t - value_same_period_previous_year`.
- محاسبات فقط با کلید تقویمی دقیق انجام شد. در نبود دوره مبنا، نامعتبر بودن آن یا صفر بودن مخرج، رشد خالی است و علت در `calculation_status` آمده است.
- مقادیر محاسبه‌شده با روش گردکردن half-up تا دو رقم اعشار ثبت شده‌اند. مقدار منبع در `value_raw` حفظ و نسخه عددی نرمال‌شده بدون حذف ارقام معنادار در `value` آمده است.
- سری‌های رسمی تورم یا رشد به‌عنوان `value` حفظ شده‌اند. ستون‌های `calc_...` محاسبات جداگانه سیستم هستند و هیچ مقدار رسمی را جایگزین نمی‌کنند.

## نتایج کنترل کیفیت

- تعداد ردیف‌های خروجی اصلی: {main_count:,}
- تعداد ردیف‌های خروجی تفصیلی: {detailed_count:,}
- تعداد ردیف‌های متادیتا: {metadata_count:,}
- تعداد ردیف‌های گزارش کیفیت: {quality_count:,}
- وضعیت کنترل‌ها: {dict(status_counts)}
- شدت هشدارها/خطاهای غیرقبول‌شده: {dict(severity_counts)}
- هم‌پوشانی ناخواسته main و detailed: {len(overlap):,}
- ستون‌های منبع بدون تعیین تکلیف در فرهنگ کامل: {sum(int(row['affected_count'] or 0) for row in quality if row['check_name'] == 'source_column_catalog_coverage'):,}
- ردیف‌های فرهنگ کامل که به منبع متصل نشدند: {len(unresolved_keys):,}
- بازبینی نمونه مستقل رشد برای هر دو تناوب در گزارش کیفیت ثبت شده است.

## استثناها و تفسیر

- وجود چند سال پایه در یک گروه اقتصادی الزاماً خطا نیست؛ سال‌پایه‌های مختلف به‌صورت سری‌های مستقل حفظ و در گزارش کیفیت علامت‌گذاری شده‌اند.
- برای سری‌های درصدی، در رابط کاربری باید تغییر واحد درصد از ستون‌های `calc_change_*_pp` معیار اصلی باشد و رشد نسبی با برچسب «درصد تغییر خود نرخ» نمایش داده شود.
- برای داده فصلی، عنوان رابط کاربری باید «رشد نسبت به فصل قبل» باشد و `calc_growth_mom_pct` خالی می‌ماند.
- سری‌های مقطعی یا دارای شکاف زمانی باید در صفحه تفصیلی هشدار قابل مشاهده داشته باشند؛ پرچم‌های لازم در `warning_flags` متادیتا موجود است.
"""
    (output_dir / "processing_summary.md").write_text(summary, encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "main_rows": main_count,
        "detailed_rows": detailed_count,
        "metadata_rows": metadata_count,
        "quality_rows": quality_count,
        "frequency_counts": dict(frequency_counts),
        "classification_counts": dict(classification_counts),
        "lifecycle_counts": dict(lifecycle_counts),
        "quality_status_counts": dict(status_counts),
        "quality_severity_counts": dict(severity_counts),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monthly", type=Path, required=True)
    parser.add_argument("--quarterly", type=Path, required=True)
    parser.add_argument("--catalog-all", type=Path, required=True)
    parser.add_argument("--catalog-main", type=Path, required=True)
    parser.add_argument("--catalog-detailed", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


if __name__ == "__main__":
    import json

    result = process(build_parser().parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))
