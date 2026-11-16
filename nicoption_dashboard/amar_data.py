from __future__ import annotations

import re
from datetime import date
from typing import Any

from django.utils import timezone

from bambo_bot.dates import gregorian_to_jalali, jalali_to_gregorian

from .models import StatisticalCenterSnapshot
from .statistical_center_data import statistical_center_definitions


class AmarSnapshotError(RuntimeError):
    pass


SOURCE = {
    "name": "amar-mcp",
    "organization": "مرکز آمار ایران",
    "adapter": "غیررسمی و فقط‌خواندنی",
    "author": "سپهر رادمرد",
    "repository": "https://github.com/sepehr071/amar-mcp",
}
SEASONS = {"بهار": 1, "تابستان": 2, "پاییز": 3, "زمستان": 4}


def _snapshot():
    return StatisticalCenterSnapshot.objects.order_by("-collected_at", "-pk").first()


def _calendar_items(payload: dict) -> list[dict]:
    items = list((payload.get("calendar") or {}).get("items") or [])
    today = timezone.localdate()
    jy, jm, jd = gregorian_to_jalali(today.year, today.month, today.day)
    upcoming = [item for item in items if (int(item.get("month") or 0), int(item.get("day") or 0)) >= (jm, jd)]
    return (upcoming or items)[0:12]


def amar_snapshot_payload(*, topic: str = "") -> dict:
    snapshot = _snapshot()
    source = dict(SOURCE)
    if snapshot is None:
        return {
            "available": False,
            "generated_at": None,
            "source": source,
            "summary": {"topics": 0, "tables": 0, "new_topics": 0, "complementary_topics": 0},
            "direct": {},
            "topics": [],
            "calendar": {"count": 0, "items": []},
            "releases": {},
            "errors": {},
        }
    payload = snapshot.payload or {}
    macro = payload.get("macro") or {}
    if topic and topic not in macro:
        raise AmarSnapshotError("موضوع آماری در تصویر amar-mcp پیدا نشد")
    age = timezone.now() - snapshot.collected_at
    source["name"] = snapshot.server_name
    topics = [
        {
            "id": key,
            "label": value.get("label") or key,
            "collection": value.get("collection") or "new",
            "source_org": value.get("source_org") or "",
            "description": value.get("description") or "",
            "table_count": len(value.get("tables") or []),
        }
        for key, value in macro.items()
    ]
    topics.sort(key=lambda item: (item["collection"] == "complementary", item["label"]))
    direct = {
        key: payload.get(key) or {}
        for key in ("labour_force", "youth_unemployment", "gdp_quarterly", "gdp_annual", "population")
    }
    result = {
        "available": True,
        "generated_at": snapshot.collected_at.isoformat(),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "is_stale": age.total_seconds() > 7 * 24 * 3600,
        "server_version": snapshot.server_version,
        "source": source,
        "summary": {
            "topics": len(topics),
            "tables": sum(item["table_count"] for item in topics),
            "new_topics": sum(item["collection"] == "new" for item in topics),
            "complementary_topics": sum(item["collection"] == "complementary" for item in topics),
        },
        "direct": direct,
        "topics": topics,
        "calendar": {
            "year": (payload.get("calendar") or {}).get("year"),
            "count": (payload.get("calendar") or {}).get("count", 0),
            "items": _calendar_items(payload),
        },
        "releases": payload.get("releases") or {},
        "errors": snapshot.errors or {},
    }
    if topic:
        selected = macro[topic]
        result["selected_topic"] = {
            "id": topic,
            "label": selected.get("label") or topic,
            "collection": selected.get("collection") or "new",
            "source_org": selected.get("source_org") or "",
            "description": selected.get("description") or "",
            "source": selected.get("source") or {},
            "tables": selected.get("tables") or [],
        }
    return result


def _quarter_date(period: str) -> str | None:
    text = str(period or "").strip()
    match = re.fullmatch(r"(\d{4})-Q([1-4])", text)
    if match:
        year, quarter = map(int, match.groups())
    else:
        match = re.fullmatch(r"(بهار|تابستان|پاییز|زمستان)\s+(\d{4})", text)
        if not match:
            return None
        quarter, year = SEASONS[match.group(1)], int(match.group(2))
    month = (quarter - 1) * 3 + 1
    return date(*jalali_to_gregorian(year, month, 1)).isoformat()


def _jalali_year(value: Any) -> int | None:
    text = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).strip()
    match = re.fullmatch(r"(13\d{2}|14\d{2})", text)
    return int(match.group(1)) if match else None


def _numeric_cell(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _series_changes(points: list[dict], *, frequency: str, unit: str) -> list[dict]:
    year_lag = {"annual": 1, "quarterly": 4, "monthly": 12}.get(frequency, 1)
    def ordinal(point: dict) -> int | None:
        if frequency == "annual":
            return _jalali_year(point.get("period_date_jalali"))
        try:
            period = date.fromisoformat(str(point.get("period_date") or ""))
        except ValueError:
            return None
        if frequency == "quarterly":
            return period.year * 4 + (period.month - 1) // 3
        if frequency == "monthly":
            return period.year * 12 + period.month - 1
        return None

    enriched = []
    for index, point in enumerate(points):
        value = _numeric_cell(point.get("value"))
        current_ordinal = ordinal(point)
        previous_point = points[index - 1] if index >= 1 else None
        previous_ordinal = ordinal(previous_point) if previous_point else None
        year_point = points[index - year_lag] if index >= year_lag else None
        year_ordinal = ordinal(year_point) if year_point else None
        previous = _numeric_cell(previous_point.get("value")) if previous_point and current_ordinal is not None and previous_ordinal == current_ordinal - 1 else None
        year_previous = _numeric_cell(year_point.get("value")) if year_point and current_ordinal is not None and year_ordinal == current_ordinal - year_lag else None
        period_delta = value - previous if value is not None and previous is not None else None
        year_delta = value - year_previous if value is not None and year_previous is not None else None
        enriched.append({
            **point,
            "period_change_percent": period_delta / abs(previous) * 100 if period_delta is not None and previous else None,
            "yearly_change_percent": year_delta / abs(year_previous) * 100 if year_delta is not None and year_previous else None,
            "period_change_percentage_points": period_delta if unit == "درصد" else None,
            "yearly_change_percentage_points": year_delta if unit == "درصد" else None,
            "period_change_coefficient": period_delta if unit == "ضریب" else None,
            "yearly_change_coefficient": year_delta if unit == "ضریب" else None,
        })
    return enriched


def _annual_table_series(payload: dict) -> list[dict]:
    """Extract yearly, numeric MCP tables (for example household Gini) as series."""
    result = []
    for topic_key, topic in (payload.get("macro") or {}).items():
        for table in topic.get("tables") or []:
            rows = table.get("rows") or []
            columns = table.get("columns") or []
            table_title = str(table.get("title") or "").strip()
            parsed_rows = []
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                year = _jalali_year(row[0])
                if year is None:
                    continue
                parsed_rows.append((year, row))
            if len({year for year, _ in parsed_rows}) < 2:
                continue
            for column_index in range(1, max(len(row) for _, row in parsed_rows)):
                points = []
                for year, row in sorted(parsed_rows, key=lambda item: item[0]):
                    if column_index >= len(row):
                        continue
                    value = _numeric_cell(row[column_index])
                    if value is None:
                        continue
                    points.append({
                        "period_date": date(*jalali_to_gregorian(year, 1, 1)).isoformat(),
                        "period_date_jalali": str(year),
                        "value": value,
                    })
                if len(points) < 2:
                    continue
                column_title = str(columns[column_index - 1] if column_index - 1 < len(columns) else "").strip()
                title = " — ".join(part for part in (table_title, column_title) if part)
                if not title:
                    title = f"جدول {table.get('n') or ''} · {column_title or f'ستون {column_index}'}"
                normalized_title = title.casefold()
                if "جینی" in normalized_title:
                    unit = "ضریب"
                elif "درصد" in normalized_title or "%" in normalized_title:
                    unit = "درصد"
                elif "هزار ریال" in normalized_title:
                    unit = "هزار ریال"
                else:
                    unit = "شاخص"
                points = _series_changes(points, frequency="annual", unit=unit)
                result.append({
                    "code": f"AMAR:{topic_key.upper()}_TABLE_{table.get('n') or 0}_COL_{column_index}",
                    "name_fa": title,
                    "name_en": "",
                    "kind": "official",
                    "category": "macro",
                    "frequency": "annual",
                    "unit": unit,
                    "classification": "اصلی",
                    "economic_group": topic.get("label") or topic_key,
                    "comparison_source": "amar_mcp",
                    "comparison_source_label": "مرکز آمار ایران · amar-mcp",
                    "is_primary": True,
                    "current": {"value": points[-1]["value"], "period_date": points[-1]["period_date"]},
                    "source": {"name": "amar-mcp", "organization": "مرکز آمار ایران"},
                    "series": points,
                })
    return result


def _travel_table_series(payload: dict) -> list[dict]:
    result = []
    for saved in payload.get("travel_tables") or []:
        table = saved.get("table") or {}
        rows = table.get("rows") or []
        year_row_index = max(
            range(len(rows)),
            key=lambda index: sum(_jalali_year(value) is not None for value in (rows[index][2:] if len(rows[index]) > 2 else [])),
            default=-1,
        )
        if year_row_index < 0:
            continue
        year_row = rows[year_row_index]
        season_row = next(
            (row for row in rows[year_row_index + 1:] if any(str(value or "").strip() in SEASONS for value in row)),
            [],
        )
        max_columns = max((len(row) for row in rows), default=0)
        years, current_year = {}, None
        for column in range(2, max_columns):
            parsed_year = _jalali_year(year_row[column]) if column < len(year_row) else None
            if parsed_year is not None:
                current_year = parsed_year
            years[column] = current_year
        periods = {}
        has_seasons = False
        for column, year in years.items():
            if year is None:
                continue
            season = str(season_row[column] or "").strip() if column < len(season_row) else ""
            if season in SEASONS:
                has_seasons = True
                period = f"{season} {year}"
                period_date = _quarter_date(period)
            else:
                period = str(year)
                period_date = date(*jalali_to_gregorian(year, 1, 1)).isoformat()
            if period_date:
                periods[column] = (period_date, period)
        frequency = "quarterly" if has_seasons else "annual"
        title = str(saved.get("title") or table.get("release") or "سفر").strip()
        for row in rows[year_row_index + 1:]:
            label = str(row[1] or "").strip() if len(row) > 1 else ""
            if not label or label.startswith(("مأخذ", "ماخذ", "منبع", "یادداشت")):
                continue
            points = []
            for column, (period_date, period) in periods.items():
                if column >= len(row):
                    continue
                value = _numeric_cell(row[column])
                if value is not None:
                    points.append({"period_date": period_date, "period_date_jalali": period, "value": value})
            points.sort(key=lambda point: point["period_date"])
            if len(points) < 2:
                continue
            full_title = f"{title} — {label}"
            title_text = full_title.casefold()
            if "هزینه" in title_text and "هزار ریال" in title_text:
                unit = "هزار ریال"
            elif "خانوار" in title_text:
                unit = "خانوار"
            elif "نفر شب" in title_text or "نفرشب" in title_text:
                unit = "نفرشب"
            elif "سفر" in title_text:
                unit = "سفر"
            else:
                unit = "شاخص"
            points = _series_changes(points, frequency=frequency, unit=unit)
            result.append({
                "code": f"AMAR:TRAVEL_{saved.get('id')}_ROW_{row[0] if row else len(result)}",
                "name_fa": full_title,
                "name_en": "",
                "kind": "official",
                "category": "macro",
                "frequency": frequency,
                "unit": unit,
                "classification": "اصلی",
                "economic_group": "گردشگری و سفر",
                "comparison_source": "amar_mcp",
                "comparison_source_label": "مرکز آمار ایران · amar-mcp",
                "is_primary": True,
                "current": {"value": points[-1]["value"], "period_date": points[-1]["period_date"]},
                "source": {"name": "amar-mcp", "organization": "مرکز آمار ایران"},
                "series": points,
            })
    return result


def _comparison_item(code: str, title: str, points: list[dict], field: str, *, group: str) -> dict | None:
    series = []
    for point in reversed(points):
        period_date = _quarter_date(point.get("period"))
        value = point.get(field)
        if not period_date or value is None:
            continue
        series.append({"period_date": period_date, "period_date_jalali": point.get("period"), "value": value})
    if not series:
        return None
    series = _series_changes(series, frequency="quarterly", unit="درصد")
    return {
        "code": f"AMAR:{code}",
        "name_fa": title,
        "name_en": "",
        "kind": "official",
        "category": "macro",
        "frequency": "quarterly",
        "unit": "درصد",
        "classification": "اصلی",
        "economic_group": group,
        "comparison_source": "amar_mcp",
        "comparison_source_label": "مرکز آمار ایران · amar-mcp",
        "is_primary": True,
        "current": {"value": series[-1]["value"], "period_date": series[-1]["period_date"]},
        "source": {"name": "amar-mcp", "organization": "مرکز آمار ایران"},
        "series": series,
    }


def amar_comparison_catalog() -> list[dict]:
    snapshot = _snapshot()
    if snapshot is None:
        return []
    payload = snapshot.payload or {}
    labour = payload.get("labour_force") or {}
    youth = payload.get("youth_unemployment") or {}
    gdp = payload.get("gdp_quarterly") or {}
    specs = [
        ("UNEMPLOYMENT", "نرخ بیکاری کشور", labour.get("unemployment") or [], "country", "بازار کار"),
        ("UNEMPLOYMENT_URBAN", "نرخ بیکاری نقاط شهری", labour.get("unemployment") or [], "urban", "بازار کار"),
        ("UNEMPLOYMENT_RURAL", "نرخ بیکاری نقاط روستایی", labour.get("unemployment") or [], "rural", "بازار کار"),
        ("PARTICIPATION", "نرخ مشارکت اقتصادی کشور", labour.get("participation") or [], "country", "بازار کار"),
        ("YOUTH_UNEMPLOYMENT", "نرخ بیکاری جوانان ۱۵ تا ۲۴ سال", youth.get("youth_unemployment") or [], "country", "بازار کار"),
        ("GDP_GROWTH", "رشد تولید ناخالص داخلی", gdp.get("series") or [], "growth_pct", "حساب‌های ملی"),
        ("GDP_EX_OIL", "رشد تولید ناخالص داخلی بدون نفت", gdp.get("series") or [], "gdp_ex_oil_pct", "حساب‌های ملی"),
        ("GDP_AGRICULTURE", "رشد ارزش افزوده کشاورزی", gdp.get("series") or [], "agriculture_pct", "حساب‌های ملی"),
        ("GDP_INDUSTRY", "رشد ارزش افزوده صنعت", gdp.get("series") or [], "industry_pct", "حساب‌های ملی"),
        ("GDP_SERVICES", "رشد ارزش افزوده خدمات", gdp.get("series") or [], "services_pct", "حساب‌های ملی"),
    ]
    direct_series = [item for spec in specs if (item := _comparison_item(*spec[:-1], group=spec[-1]))]
    items = direct_series + _annual_table_series(payload) + _travel_table_series(payload)
    descriptions = statistical_center_definitions()
    for item in items:
        item["description_fa"] = descriptions.get(item["code"], "")
    return items
