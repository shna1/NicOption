from __future__ import annotations

from django.utils import timezone
import re
from datetime import date
import hashlib

from bambo_bot.dates import jalali_to_gregorian
from .cbi_series import canonical_name, merge_series_items

from .models import CentralBankSnapshot

_MONTHS = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
_SEASONS = {"بهار": 1, "تابستان": 2, "پاییز": 3, "زمستان": 4}
SOURCE = {"name": "cbi-mcp", "organization": "بانک مرکزی جمهوری اسلامی ایران", "adapter": "غیررسمی و فقط‌خواندنی", "author": "سپهر رادمرد", "repository": "https://github.com/sepehr071/cbi-mcp"}


def _catalog_series(payload: dict) -> list[dict]:
    """Normalize stored cbi-mcp history into the shared indicator shape."""
    result = []
    inflation = payload.get("inflation") or {}
    inflation_series = []
    annual_points = [{"period": str(item.get("year")), "value": item.get("rate_pct")} for item in inflation.get("annual") or []]
    if len(annual_points) > 1:
        inflation_series.append({"name": "تورم سالانه بانک مرکزی", "unit": "درصد", "points": annual_points})
    year = inflation.get("year")
    monthly_points = [{"period": f"{year} {item.get('month')}", "value": item.get("rate_pct")} for item in inflation.get("monthly") or [] if year and item.get("month")]
    if len(monthly_points) > 1:
        inflation_series.append({"name": "تورم ماهانه بانک مرکزی", "unit": "درصد", "points": monthly_points})
    if inflation_series:
        result.extend(_catalog_series({"statistics_time_series": {"sections": [{"key": "inflation", "label": "تورم و قیمت‌ها", "series": inflation_series}]}}))
    sections = [section for section in (payload.get("statistics_time_series") or {}).get("sections") or []
                if section.get("key") != "balance_of_payments"]
    sections.extend(_dated_mcp_sections(payload))
    for section in sections:
        merged_items = merge_series_items(section.get("series") or [])
        for item in merged_items:
            parsed = []
            for point in item.get("points") or []:
                label = str(point.get("period") or "").strip()
                period_info = _series_period(label, item.get("frequency"))
                if not period_info:
                    continue
                frequency, ordinal, date_value, jalali_date = period_info
                year, month = map(int, jalali_date.split("/")[:2])
                try:
                    value = float(point.get("value"))
                    if value != value or abs(value) == float("inf"):
                        continue
                except (TypeError, ValueError, OverflowError):
                    continue
                parsed.append({"period": label, "period_date": date_value, "period_date_jalali": label,
                               "jalali_date": jalali_date, "value": value, "_ordinal": ordinal})
            parsed.sort(key=lambda point: point["_ordinal"])
            if not parsed:
                continue
            frequency = item.get("frequency") or ("monthly" if any(p["period"].split()[-1] in _MONTHS for p in parsed if p["period"].split()) else (
                "quarterly" if any(p["period"].split()[-1] in _SEASONS for p in parsed if p["period"].split()) else "annual"))
            step, year_lag = {"monthly": (1, 12), "quarterly": (1, 4), "annual": (1, 1), "weekly": (7, 364), "daily": (1, 365)}[frequency]
            by_ordinal = {point["_ordinal"]: point for point in parsed}
            for pos, point in enumerate(parsed):
                prev = by_ordinal.get(point["_ordinal"] - step)
                year_prev = by_ordinal.get(point["_ordinal"] - year_lag)
                for prefix, other in (("period", prev), ("yearly", year_prev)):
                    delta = point["value"] - other["value"] if other else None
                    point[f"{prefix}_change_percent"] = delta / abs(other["value"]) * 100 if delta is not None and other["value"] else None
                    point[f"{prefix}_change_percentage_points"] = delta if delta is not None and item.get("unit") == "درصد" else None
                    point[f"{prefix}_change_coefficient"] = delta if delta is not None and item.get("unit") == "ضریب" else None
                    point[f"{prefix}_change_value"] = delta if delta is not None else None
            name = str(item.get("name") or "سری بدون نام").strip()
            digest = hashlib.sha256(canonical_name(item.get("name")).encode("utf-8")).hexdigest()[:12]
            code = f"CBI:{section.get('key', 'statistics')}:{digest}"
            group = "عملیات بازار باز" if canonical_name(name) == "مانده اجرای عملیات سیاست پولی" else (section.get("label") or "آمار بانک مرکزی")
            result.append({"technical_id": code, "title_fa": name, "unit": item.get("unit") or "—",
                "frequency": frequency, "economic_group": group,
                "metric_type": "سری زمانی", "source": SOURCE, "comparison_source": "cbi_mcp", "merged_from": item.get("merged_from", []),
                "current": parsed[-1], "series": [{k: v for k, v in p.items() if k != "_ordinal"} for p in parsed]})
    # Some cb_statistics workbooks are wide: period labels are columns and
    # indicators are rows. Recover those from the raw stored tool response too.
    known = {(item["economic_group"], item["title_fa"]) for item in result}
    for section_key in ("monetary", "fiscal", "capital_market"):
        raw = payload.get(f"statistics_{section_key}") or {}
        rows = raw.get("rows") or []
        header_index = next((i for i, row in enumerate(rows) if isinstance(row, list) and sum(bool(_period_key(cell)) for cell in row) >= 2), None)
        header = rows[header_index] if header_index is not None else None
        if not header:
            continue
        # Workbooks with split multi-row headings need their column hierarchy
        # resolved first; treating bare year headings as full periods mislabels
        # partial-year columns as annual observations.
        nested_header = rows[header_index + 1:header_index + 3]
        nested_text = " ".join(str(cell) for row in nested_header if isinstance(row, list) for cell in row)
        if any(month in nested_text for month in _MONTHS) or any(season in nested_text for season in _SEASONS):
            continue
        period_columns = [(i, _period_key(cell)) for i, cell in enumerate(header) if _period_key(cell)]
        for row in rows:
            if not isinstance(row, list):
                continue
            labels = [str(value).strip() for value in row[:min(i for i, _ in period_columns)] if isinstance(value, str) and value.strip()]
            if not labels:
                continue
            name = " · ".join(labels)
            if name in {"عنوان", "نام شاخص", "شاخص"}:
                continue
            group = section_key
            if (group, name) in known:
                continue
            points = []
            for column, (frequency, ordinal, date_value, period_label, jalali_date) in period_columns:
                if column >= len(row):
                    continue
                try:
                    value = float(row[column])
                    if value != value or abs(value) == float("inf"):
                        continue
                except (TypeError, ValueError):
                    continue
                points.append({"period": period_label, "period_date": date_value, "period_date_jalali": period_label,
                    "jalali_date": jalali_date, "value": value, "_ordinal": ordinal, "_frequency": frequency})
            points.sort(key=lambda point: point["_ordinal"])
            if len(points) < 2:
                continue
            frequency = points[0]["_frequency"]
            lag = {"monthly": 12, "quarterly": 4, "annual": 1}[frequency]
            by_ordinal = {point["_ordinal"]: point for point in points}
            for pos, point in enumerate(points):
                prior = by_ordinal.get(point["_ordinal"] - 1)
                yearly = by_ordinal.get(point["_ordinal"] - lag)
                point["period_change_value"] = point["value"] - prior["value"] if prior else None
                point["yearly_change_value"] = point["value"] - yearly["value"] if yearly else None
            unit = "شاخص" if "شاخص" in name else "هزار میلیارد ریال"
            code = f"CBI:{section_key}:wide:{len(result)}"
            result.append({"technical_id": code, "title_fa": name, "unit": unit, "frequency": frequency,
                "economic_group": {"monetary":"پول و اعتبار", "balance_of_payments":"تراز پرداخت‌ها", "fiscal":"مالی دولت", "capital_market":"بازار سرمایه"}.get(section_key, section_key), "metric_type": "سری زمانی", "source": SOURCE,
                "comparison_source": "cbi_mcp", "current": {k: v for k, v in points[-1].items() if not k.startswith("_")},
                "series": [{k: v for k, v in point.items() if not k.startswith("_")} for point in points]})
            known.add((group, name))
    combined: dict[tuple[str, str, str], dict] = {}
    for indicator in result:
        key = (canonical_name(indicator.get("title_fa")), str(indicator.get("unit") or ""), str(indicator.get("frequency") or ""))
        current = combined.get(key)
        if current is None:
            current = {**indicator, "series": [], "merged_from": []}
            combined[key] = current
        current["merged_from"].extend(indicator.get("merged_from") or [indicator.get("title_fa")])
        points = {point.get("period_date"): point for point in current["series"] if point.get("period_date")}
        for point in indicator.get("series") or []:
            key_date = point.get("period_date") or point.get("period_date_jalali")
            if key_date not in points:
                points[key_date] = point
        current["series"] = sorted(points.values(), key=lambda point: (point.get("period_date") or "", point.get("period_date_jalali") or ""))
        current["current"] = current["series"][-1] if current["series"] else current.get("current")
        digest = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:12]
        current["technical_id"] = f"CBI:{digest}"
    for item in combined.values():
        item["merged_from"] = sorted(set(item["merged_from"]))
    return list(combined.values())


def _period_key(value):
    text = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).strip()
    match = re.fullmatch(r"(13\d{2}|14\d{2})(?:\s+(.+))?", text)
    if not match:
        return None
    year, part = int(match.group(1)), (match.group(2) or "").strip()
    if part in _MONTHS:
        month, frequency = _MONTHS.index(part) + 1, "monthly"
        ordinal = year * 12 + month - 1
    elif part in _SEASONS:
        month, frequency = (_SEASONS[part] - 1) * 3 + 1, "quarterly"
        ordinal = year * 4 + _SEASONS[part] - 1
    elif not part or part in {"سال", "سالانه"}:
        month, frequency, ordinal = 1, "annual", year
    else:
        return None
    date_value = date(*jalali_to_gregorian(year, month, 1)).isoformat()
    return frequency, ordinal, date_value, text, f"{year:04d}/{month:02d}/01"


def _series_period(value: str, frequency: str | None = None):
    text = str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).strip()
    match = re.fullmatch(r"(13\d{2}|14\d{2})(?:\s+(.+))?", text)
    if match:
        year, part = int(match.group(1)), (match.group(2) or "").strip()
        if part in _MONTHS:
            month, freq, ordinal = _MONTHS.index(part) + 1, "monthly", year * 12 + _MONTHS.index(part)
        elif part in _SEASONS:
            month, freq, ordinal = (_SEASONS[part] - 1) * 3 + 1, "quarterly", year * 4 + _SEASONS[part] - 1
        elif not part or part in {"سال", "سالانه"}:
            month, freq, ordinal = 1, "annual", year
        else:
            return None
        date_value = date(*jalali_to_gregorian(year, month, 1)).isoformat()
        return freq, ordinal, date_value, f"{year:04d}/{month:02d}/01"
    # MCP rate tools use Jalali slash dates; auctions use '9 آبان 1405'.
    match = re.fullmatch(r"(13\d{2}|14\d{2})/(\d{1,2})/(\d{1,2})", text)
    if match:
        year, month, day = map(int, match.groups())
        try:
            gregorian = date(*jalali_to_gregorian(year, month, day))
        except ValueError:
            return None
        freq = frequency or "daily"
        return freq, gregorian.toordinal(), gregorian.isoformat(), f"{year:04d}/{month:02d}/{day:02d}"
    match = re.fullmatch(r"(\d{1,2})\s+([^\s]+)\s+(13\d{2}|14\d{2})", text)
    if match and match.group(2) in _MONTHS:
        day, month_name, year = match.groups()
        year, month, day = int(year), _MONTHS.index(month_name) + 1, int(day)
        try:
            gregorian = date(*jalali_to_gregorian(year, month, day))
        except ValueError:
            return None
        freq = frequency or "weekly"
        return freq, gregorian.toordinal(), gregorian.isoformat(), f"{year:04d}/{month:02d}/{day:02d}"
    return None


def _dated_mcp_sections(payload: dict) -> list[dict]:
    sections = []

    def add(key, label, items):
        if items:
            sections.append({"key": key, "label": label, "series": items})

    policy_rows = payload.get("policy_rates", {}).get("rows") or []
    if policy_rows:
        metrics = (("interbank_pct", "نرخ بین‌بانکی"), ("repo_min_pct", "حداقل نرخ ریپو"),
                   ("standing_lending_pct", "نرخ اعتبارگیری قاعده‌مند"), ("standing_deposit_pct", "نرخ سپرده‌گذاری قاعده‌مند"))
        add("policy_rates", "بازار پول و نرخ‌های سیاستی", [
            {"name": title, "unit": "درصد", "frequency": "weekly",
             "points": [{"period": row.get("date"), "value": row.get(field)} for row in policy_rows if row.get("date") and row.get(field) is not None]}
            for field, title in metrics
        ])
    auctions = payload.get("bond_auctions", {}).get("auctions") or []
    if auctions:
        add("bond_auctions", "حراج اوراق دولتی", [{"name": "فروش اوراق در هر حراج", "unit": "هزار میلیارد ریال", "frequency": "weekly",
             "points": [{"period": item.get("date"), "value": item.get("total_sold_this_auction")} for item in auctions if item.get("date") and item.get("total_sold_this_auction") is not None]}])
    return sections


def central_bank_snapshot_payload() -> dict:
    snapshot = CentralBankSnapshot.objects.order_by("-collected_at", "-pk").first()
    source = {
        "name": "cbi-mcp",
        "organization": "بانک مرکزی جمهوری اسلامی ایران",
        "adapter": "غیررسمی و فقط‌خواندنی",
        "author": "سپهر رادمرد",
        "repository": "https://github.com/sepehr071/cbi-mcp",
    }
    if snapshot is None:
        return {"available": False, "generated_at": None, "source": source, "data": {}, "errors": {}}
    age = timezone.now() - snapshot.collected_at
    source["name"] = snapshot.server_name
    data = dict(snapshot.payload or {})
    data.pop("exchange_rates", None)
    data.pop("rate_history", None)
    data.pop("statistics_balance_of_payments", None)
    time_series = data.get("statistics_time_series") or {}
    data["statistics_time_series"] = {**time_series, "sections": [
        section for section in time_series.get("sections") or [] if section.get("key") != "balance_of_payments"
    ]}
    return {
        "available": True,
        "generated_at": snapshot.collected_at.isoformat(),
        "age_hours": round(age.total_seconds() / 3600, 1),
        "is_stale": age.total_seconds() > 36 * 3600,
        "server_version": snapshot.server_version,
        "source": source,
        "data": data,
        "series_catalog": _catalog_series(data),
        "errors": snapshot.errors,
    }
