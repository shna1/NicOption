from __future__ import annotations

import csv
import io
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from django.conf import settings


DATA_DIR = Path(settings.BASE_DIR) / "outputs" / "website_data_prepared"
METADATA_FILE = DATA_DIR / "website_series_metadata.csv"
INDEX_FILE = DATA_DIR / "website_series_index.json"
DEFINITIONS_FILE = Path(settings.BASE_DIR) / "statistical_center_indicators_definitions.csv"
SOURCE_URL = "https://amar.org.ir/statistical-information/statid/28595"
MAX_PAGE_SIZE = 50
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
JALALI_SEASONS = ("بهار", "تابستان", "پاییز", "زمستان")
JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)


class StatisticalCenterDataError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def statistical_center_definitions() -> dict[str, str]:
    """Load user-authored one-line descriptions keyed by indicator identifier."""
    if not DEFINITIONS_FILE.exists():
        return {}
    with DEFINITIONS_FILE.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row.get("شناسه", "").strip(): row.get("تعریف شاخص (توسط شما تکمیل شود)", "").strip()
            for row in csv.DictReader(stream)
            if row.get("شناسه", "").strip()
            and row.get("تعریف شاخص (توسط شما تکمیل شود)", "").strip()
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise StatisticalCenterDataError(f"فایل {path.name} مرکز آمار پیدا نشد")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip()


def _series_key(row: dict[str, str]) -> str:
    return f"{row.get('source_file', '').strip()}::{row.get('technical_id', '').strip()}"


def _clean_title_part(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"^\s*(?:جدول\s*)?\d+\s*[-–—]\s*", "", text)
    text = re.sub(r"^\s*سری\s+زمانی\s+", "", text)
    text = re.sub(r"^\s*درصد\s+تغییر(?=ماهانه|نقطه)", "درصد تغییر ", text)
    annual_inflation = re.search(r"\(\s*نرخ\s+تورم\s+([^)]+)\)", text)
    point_in_time_inflation = re.search(r"\(\s*تورم\s+نقطه\s+به\s+نقطه\s+([^)]+)\)", text)
    if text.strip().startswith("درصد تغییر") and annual_inflation:
        text = f"نرخ تورم سالانه {annual_inflation.group(1).strip()}"
    elif text.strip().startswith("درصد تغییر") and point_in_time_inflation:
        text = f"تورم نقطه‌به‌نقطه {point_in_time_inflation.group(1).strip()}"
    else:
        producer_point_in_time = re.match(
            r"^درصد\s+تغییرات\s+شاخص\s+قیمت\s+(تولید\s*کننده.+?)\s+فصل\s+جاری\s+نسبت\s+به\s+فصل\s+مشابه\s+سال\s+قبل.*?\(\s*تورم\s+نقطه\s+به\s+نقطه\s*\)",
            text,
        )
        if producer_point_in_time:
            text = f"تورم {producer_point_in_time.group(1).strip()} فصل جاری (نقطه‌به‌نقطه)"
        text = re.sub(
            r"^سری\s+زمانی\s+نرخ\s+تورم\s+دوازده\s+ماهه\s+",
            "نرخ تورم سالانه ",
            text,
        )
        text = re.sub(
            r"^نرخ\s+تورم\s+دوازده\s+ماهه\s+",
            "نرخ تورم سالانه ",
            text,
        )
        text = re.sub(r"^سری\s+زمانی\s+", "", text)
        text = re.sub(
            r"^درصد\s+تغییر\s+ماهانه\s+شاخص\s+قیمت\s+مصرف\s*کننده\s+",
            "تورم ماهانه ",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+شاخص\s+قیمت\s+مصرف\s*کننده\s+(.+?)\s+نسبت\s+به\s+ماه\s+مشابه\s+سال\s+قبل",
            r"تورم نقطه‌به‌نقطه \1",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+شاخص\s+قیمت\s+مصرف\s*کننده\s+(.+?)\s+نسبت\s+به\s+ماه\s+قبل",
            r"تورم ماهانه \1",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+تورم\s+نقطه\s+به\s+نقطه\s+شاخص\s+قیمت\s+",
            "تورم نقطه‌به‌نقطه ",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+نقطه\s+به\s+نقطه\s+شاخص(?:\s+کل)?\s+(?:قیمت\s+)?",
            "تورم نقطه‌به‌نقطه ",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+ماهانه\s+شاخص(?:\s+کل)?\s+(?:قیمت\s+)?",
            "تورم ماهانه ",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+شاخص\s+قیمت\s+(.+?)(?:در\s+)?(?:چهار|۴|4)\s*فصل\s+منتهی\s+به\s+(?:فصل|دوره)\s+(?:مورد\s+نظر|جاری)\s+نسبت\s+به\s+دوره\s+مشابه\s+سال\s+قبل(?:\s*\(\s*نرخ\s+تورم\s*\))?",
            r"نرخ تورم سالانه \1",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+شاخص\s+قیمت\s+(.+?)\s+نسبت\s+به\s+(?:ماه|فصل)\s+مشابه\s+سال\s+قبل(?:\s*\([^)]*\))?",
            r"تورم نقطه‌به‌نقطه \1",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+فصلی\s+شاخص\s+قیمت\s+(.+?)\s+به\s+تفکیک",
            r"تورم فصلی \1 به تفکیک",
            text,
        )
        text = re.sub(
            r"^درصد\s+تغییر\s+شاخص\s+قیمت\s+(.+?)\s+نسبت\s+به\s+فصل\s+قبل",
            r"تورم فصلی \1",
            text,
        )
        text = re.sub(r"^درصد\s+تغییرات\s+شاخص\s+قیمت\s+", "تورم قیمت ", text)
        text = re.sub(r"^درصد\s+تغییرات\s+", "تورم ", text)
    text = re.sub(r"^\s*(?:جدول\s*)?\d+\s*[-–—]\s*", "", text)
    text = re.sub(r"\s*:\s*(?:بهار|تابستان|پاییز|زمستان)\s*[۰-۹0-9]{4}\s*$", "", text)
    text = re.sub(r"\s*\(?\s*بر\s*مبنای\s+سال\s+پایه\s+100\s*=\s*[۰-۹0-9]{4}\s*\)?", "", text)
    text = re.sub(r"\s+(?:بر\s*مبنای\s+)?سال\s+پایه\s+100\s*=\s*[۰-۹0-9]{4}\s*", " ", text)
    text = re.sub(r"\s+100\s*=\s*[۰-۹0-9]{4}\s*$", "", text)
    text = re.sub(r"\s+به\s+تفکیک\s+(?:فصل\s*/?\s*ماه|فصل|ماه)\b.*$", "", text)
    text = re.sub(r"\s+به\s+تفکیک\s+استان\b", "", text)
    text = re.sub(r"^\*+", "", text)
    text = re.sub(r"\s*\((?:ریال|درصد)\)\s*$", "", text)
    text = re.sub(r"\bقیمت\s+تولید\s+کننده\b", "قیمت تولیدکننده", text)
    text = re.sub(r"\bتولید\s+کننده\b", "تولیدکننده", text)
    text = re.sub(r"\bقیمت\s+مصرف\s+کننده\b", "قیمت مصرف‌کننده", text)
    text = re.sub(r"\bخانوار\s+های\b", "خانوارهای", text)
    text = re.sub(r"\bبخش\s+های\b", "بخش‌های", text)
    text = re.sub(r"\bگروه\s+های\b", "گروه‌های", text)
    text = re.sub(r"\bفعالیت\s+های\b", "فعالیت‌های", text)
    text = re.sub(r"\bنهاده\s+های\b", "نهاده‌های", text)
    text = re.sub(r"\bساختمان\s+های\b", "ساختمان‌های", text)
    text = re.sub(r"\bدهک\s+های\b", "دهک‌های", text)
    text = re.sub(r"\bهزینه\s+ای\b", "هزینه‌ای", text)
    text = re.sub(r"\bخوراکیها\b", "خوراکی‌ها", text)
    text = re.sub(r"\bآشامیدنیها\b", "آشامیدنی‌ها", text)
    text = re.sub(r"\bروغنها\b", "روغن‌ها", text)
    text = re.sub(r"\bفعالیتها\b", "فعالیت‌ها", text)
    text = re.sub(r"\bنقطه\s+به\s+نقطه\b", "نقطه‌به‌نقطه", text)
    if text.startswith("تورم ماهانه"):
        text = re.sub(r"\s+نسبت\s+به\s+ماه\s+قبل", "", text)
    text = re.sub(r"\s+و\s*خدمات\b", " و خدمات", text)
    text = text.replace("درصد تغییرات", "تورم")
    text = re.sub(r"\s+", " ", text).strip(" |،؛-–—")
    return text.translate(PERSIAN_DIGITS)


def _professional_title(row: dict[str, str]) -> str:
    raw_parts = [part for part in str(row.get("title_fa") or "").split("|") if part.strip()]
    parts: list[str] = []
    normalized_parts: set[str] = set()
    for raw_part in raw_parts:
        part = _clean_title_part(raw_part)
        if not part or part == "قیمت واحد":
            continue
        key = _normalized(part)
        if key in normalized_parts:
            continue
        normalized_parts.add(key)
        parts.append(part)
    raw_title = _normalized(row.get("title_fa", ""))
    detail = parts[-1] if len(parts) > 1 else ""
    if (
        row.get("economic_group") == "شاخص قیمت تولیدکننده کل و بخش‌های اصلی"
        and "درصد تغییرات شاخص قیمت تولیدکننده کل فصل جاری" in raw_title
        and "فصل مشابه سال قبل" in raw_title
        and detail
    ):
        return f"تورم تولیدکننده کل فصل جاری (نقطه‌به‌نقطه) بخش {detail}"
    if (
        row.get("economic_group") == "تورم و شاخص قیمت به تفکیک دهک"
        and "خوراکیها" in raw_title
        and "نقطه به نقطه" in raw_title
        and detail
    ):
        return f"تورم خوراکی‌ها، آشامیدنی‌ها و دخانیات کالاها و خدمات مصرفی (نقطه‌به‌نقطه) {detail}"
    if (
        row.get("economic_group") == "نهاده‌ها و مصالح ساختمان"
        and "درصد تغییرات شاخص قیمت نهاده های ساختمان های مسکونی شهر تهران" in raw_title
        and "چهار فصل منتهی به فصل مورد نظر" in raw_title
        and detail
    ):
        return f"تورم قیمت نهاده‌های ساختمان‌های مسکونی شهر تهران (نقطه‌به‌نقطه) — {detail}"
    if detail and parts[0].startswith("تورم") and "تولیدکننده" in parts[0]:
        return f"{parts[0]} بخش {detail}"
    return " — ".join(parts) or str(row.get("economic_group") or row.get("title_fa") or "").strip()


def _jalali_period_label(value: str, frequency: str) -> str:
    match = re.match(r"^\s*([0-9۰-۹]{4})[-/]([0-9۰-۹]{1,2})", str(value or ""))
    if not match:
        return str(value or "")
    year_text, month_text = match.groups()
    normalized_month = month_text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    month = int(normalized_month)
    if not 1 <= month <= 12:
        return str(value or "")
    period_name = JALALI_SEASONS[(month - 1) // 3] if frequency == "quarterly" else JALALI_MONTHS[month - 1]
    return f"{period_name} {year_text.translate(PERSIAN_DIGITS)}"


@lru_cache(maxsize=1)
def statistical_center_dataset() -> dict:
    rows = _read_csv(METADATA_FILE)
    if not INDEX_FILE.exists():
        raise StatisticalCenterDataError("نمایه داده‌های مرکز آمار ساخته نشده است")
    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    if index.get("version") != 1:
        raise StatisticalCenterDataError("نسخه نمایه داده‌های مرکز آمار پشتیبانی نمی‌شود")
    for filename, expected in index.get("files", {}).items():
        data_path = DATA_DIR / filename
        if not data_path.exists() or data_path.stat().st_size != expected.get("size"):
            raise StatisticalCenterDataError(
                f"فایل {filename} با نمایه مرکز آمار همگام نیست؛ نمایه را بازسازی کنید"
            )
    items = []
    by_key = {}
    for row in rows:
        key = _series_key(row)
        indexed = index.get("series", {}).get(key)
        if not indexed:
            raise StatisticalCenterDataError(f"سری {key} در نمایه داده پیدا نشد")
        item = {
            "series_key": key,
            "technical_id": row.get("technical_id", ""),
            "title_fa": row.get("title_fa", ""),
            "display_title_fa": _professional_title(row),
            "classification": row.get("classification", ""),
            "lifecycle": row.get("lifecycle", ""),
            "economic_group": row.get("economic_group", ""),
            "metric_type": row.get("metric_type", ""),
            "unit": row.get("unit", ""),
            "base_year": row.get("base_year", ""),
            "frequency": row.get("frequency", ""),
            "first_available_jalali": row.get("first_available_jalali_computed") or row.get("first_available_jalali", ""),
            "last_available_jalali": row.get("last_available_jalali_computed") or row.get("last_available_jalali", ""),
            "observation_count": int(row.get("observation_count_computed") or row.get("observation_count") or 0),
            "gap_count": int(row.get("gap_count") or 0),
            "warning_flags": [flag for flag in row.get("warning_flags", "").split(";") if flag],
            "latest": indexed.get("latest"),
        }
        item["description_fa"] = statistical_center_definitions().get(item["technical_id"], "")
        item["first_available_label_fa"] = _jalali_period_label(item["first_available_jalali"], item["frequency"])
        item["last_available_label_fa"] = _jalali_period_label(item["last_available_jalali"], item["frequency"])
        item["_search"] = _normalized(" ".join(str(value) for value in item.values() if not isinstance(value, (dict, list))))
        items.append(item)
        by_key[key] = item
    items.sort(key=lambda item: (item["classification"] != "اصلی", item["economic_group"], item["title_fa"], item["series_key"]))
    generated_at = datetime.fromtimestamp(max(METADATA_FILE.stat().st_mtime, INDEX_FILE.stat().st_mtime), tz=timezone.utc).isoformat()
    return {
        "generated_at": generated_at,
        "items": items,
        "by_key": by_key,
        "index": index,
        "groups": sorted({item["economic_group"] for item in items}),
        "lifecycles": sorted({item["lifecycle"] for item in items}),
        "metric_types": sorted({item["metric_type"] for item in items}),
    }


def _bounded_int(value: str | None, *, default: int, minimum: int, maximum: int, name: str) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError) as exc:
        raise StatisticalCenterDataError(f"{name} باید عدد صحیح باشد") from exc
    if not minimum <= parsed <= maximum:
        raise StatisticalCenterDataError(f"{name} باید بین {minimum} و {maximum} باشد")
    return parsed


def _indexed_rows(item: dict, indexed: dict) -> list[dict[str, str]]:
    path = DATA_DIR / indexed["file"]
    with path.open("rb") as stream:
        header = stream.readline().decode("utf-8-sig")
        chunks = []
        for start, end in indexed["ranges"]:
            stream.seek(start)
            chunks.append(stream.read(end - start).decode("utf-8"))
    return [
        row for row in csv.DictReader(io.StringIO(header + "".join(chunks)))
        if row.get("value") not in (None, "")
    ]


def _catalog_analytics(item: dict, indexed: dict) -> dict:
    rows = _indexed_rows(item, indexed)
    if not rows:
        return {"change_3m": None, "change_3m_kind": "percent", "percentile_2y": None, "trend_2y": [], "signal": 0}

    latest = rows[-1]
    latest_date = datetime.fromisoformat(latest["gregorian_date"])
    window_months = 24 if item["frequency"] == "monthly" else 8
    trend_rows = rows[-window_months:]
    values = [float(row["value"]) for row in trend_rows]
    latest_value = values[-1]
    percentile = round(sum(value <= latest_value for value in values) / len(values) * 100)

    target_month_index = latest_date.year * 12 + latest_date.month - 4
    prior = next((
        row for row in reversed(rows[:-1])
        if datetime.fromisoformat(row["gregorian_date"]).year * 12
        + datetime.fromisoformat(row["gregorian_date"]).month - 1 <= target_month_index
    ), None)
    change = None
    kind = "point" if item["unit"] == "percent" else "percent"
    if prior:
        prior_value = float(prior["value"])
        if kind == "point":
            change = latest_value - prior_value
        elif prior_value:
            change = (latest_value / prior_value - 1) * 100
    rounded_change = round(change, 2) if change is not None else None
    signal = 1 if rounded_change is not None and rounded_change > 0 else -1 if rounded_change is not None and rounded_change < 0 else 0
    return {
        "change_3m": rounded_change,
        "change_3m_kind": kind,
        "percentile_2y": percentile,
        "trend_2y": [
            {"date": row["gregorian_date"], "value": row["value"]}
            for row in trend_rows
        ],
        "signal": signal,
    }


def statistical_center_catalog(params) -> dict:
    dataset = statistical_center_dataset()
    query = str(params.get("q") or "").strip()
    if len(query) > 120:
        raise StatisticalCenterDataError("عبارت جست‌وجو بیش از حد طولانی است")
    filters = {
        "classification": str(params.get("classification") or "اصلی").strip(),
        "frequency": str(params.get("frequency") or "all").strip(),
        "economic_group": str(params.get("economic_group") or "all").strip(),
        "lifecycle": str(params.get("lifecycle") or "جاری").strip(),
    }
    page = _bounded_int(params.get("page"), default=1, minimum=1, maximum=10000, name="صفحه")
    page_size = _bounded_int(params.get("page_size"), default=25, minimum=10, maximum=MAX_PAGE_SIZE, name="تعداد ردیف")
    normalized_query = _normalized(query)
    filtered = []
    for item in dataset["items"]:
        if normalized_query and normalized_query not in item["_search"]:
            continue
        if any(value != "all" and item[key] != value for key, value in filters.items()):
            continue
        filtered.append(item)
    total = len(filtered)
    pages = max(1, math.ceil(total / page_size))
    page = min(page, pages)
    start = (page - 1) * page_size
    public_items = []
    for item in filtered[start:start + page_size]:
        public_item = {key: value for key, value in item.items() if not key.startswith("_")}
        indexed = dataset["index"]["series"].get(item["series_key"])
        public_items.append({**public_item, "analytics": _catalog_analytics(item, indexed) if indexed else {}})
    all_items = dataset["items"]
    return {
        "generated_at": dataset["generated_at"],
        "source": {"name": "مرکز آمار ایران", "url": SOURCE_URL},
        "summary": {
            "total_series": len(all_items),
            "main_series": sum(item["classification"] == "اصلی" for item in all_items),
            "detailed_series": sum(item["classification"] == "تفکیکی" for item in all_items),
            "monthly_series": sum(item["frequency"] == "monthly" for item in all_items),
            "quarterly_series": sum(item["frequency"] == "quarterly" for item in all_items),
        },
        "facets": {
            "economic_groups": dataset["groups"],
            "lifecycles": dataset["lifecycles"],
            "metric_types": dataset["metric_types"],
        },
        "filters": {"q": query, **filters},
        "pagination": {"page": page, "page_size": page_size, "total": total, "pages": pages},
        "indicators": public_items,
    }


def statistical_center_comparison_catalog() -> list[dict]:
    """Return the complete lightweight catalog for the trend comparison picker.

    Series values remain lazy-loaded through ``statistical_center_series`` so the
    comparison page can expose every available series without reading every CSV
    file or shipping thousands of observations on initial load.
    """
    dataset = statistical_center_dataset()
    return [
        {key: value for key, value in item.items() if not key.startswith("_")}
        for item in dataset["items"]
    ]


def statistical_center_series(series_key: str) -> dict:
    dataset = statistical_center_dataset()
    item = dataset["by_key"].get(series_key)
    indexed = dataset["index"].get("series", {}).get(series_key)
    if not item or not indexed:
        raise KeyError("سری مرکز آمار پیدا نشد")
    rows = _indexed_rows(item, indexed)
    series = [
        {
            "period_date": row.get("gregorian_date"),
            "period_date_jalali": row.get("jalali_date"),
            "period_label_fa": _jalali_period_label(row.get("jalali_date", ""), item["frequency"]),
            "value": row.get("value"),
            "period_change_percent": row.get("calc_growth_mom_pct") or row.get("calc_growth_qoq_pct") or None,
            "yearly_change_percent": row.get("calc_growth_yoy_pct") or None,
            "period_change_percentage_points": row.get("calc_change_period_pp") or None,
            "yearly_change_percentage_points": row.get("calc_change_yoy_pp") or None,
            "calculation_status": row.get("calculation_status", ""),
        }
        for row in rows
        if row.get("value") not in (None, "")
    ]
    public_item = {key: value for key, value in item.items() if not key.startswith("_")}
    return {
        "generated_at": dataset["generated_at"],
        "source": {"name": "مرکز آمار ایران", "url": SOURCE_URL},
        "indicator": {**public_item, "series": series},
    }
