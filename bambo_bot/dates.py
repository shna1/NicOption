from __future__ import annotations

from datetime import date, datetime
import re


def gregorian_to_jalali(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert a Gregorian date to the Solar Hijri (Jalali) calendar."""
    month_days = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if year > 1600:
        jalali_year = 979
        year -= 1600
    else:
        jalali_year = 0
        year -= 621
    adjusted_year = year + 1 if month > 2 else year
    days = (
        365 * year
        + (adjusted_year + 3) // 4
        - (adjusted_year + 99) // 100
        + (adjusted_year + 399) // 400
        - 80
        + day
        + month_days[month - 1]
    )
    jalali_year += 33 * (days // 12053)
    days %= 12053
    jalali_year += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jalali_year += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jalali_month = 1 + days // 31
        jalali_day = 1 + days % 31
    else:
        jalali_month = 7 + (days - 186) // 30
        jalali_day = 1 + (days - 186) % 30
    return jalali_year, jalali_month, jalali_day


def jalali_to_gregorian(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert a Solar Hijri date to the Gregorian calendar."""
    year -= 979
    month -= 1
    day -= 1
    days = 365 * year + (year // 33) * 8 + ((year % 33) + 3) // 4
    days += sum((31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30)[:month]) + day
    days += 79
    gregorian_year = 1600 + 400 * (days // 146097)
    days %= 146097
    leap = True
    if days >= 36525:
        days -= 1
        gregorian_year += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
        else:
            leap = False
    gregorian_year += 4 * (days // 1461)
    days %= 1461
    if days >= 366:
        leap = False
        days -= 1
        gregorian_year += days // 365
        days %= 365
    month_days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gregorian_month = 1
    for length in month_days:
        if days < length:
            break
        days -= length
        gregorian_month += 1
    return gregorian_year, gregorian_month, days + 1


def parse_user_date(value: str) -> date:
    """Parse Gregorian or Solar Hijri dates regardless of slash/dash separator.

    Market feeds are not consistent about separators: IME may provide a Solar
    Hijri date with slashes while normalized rows use Gregorian ISO dates.  The
    year therefore determines the calendar instead of the punctuation.
    """
    normalized = str(value or "").strip().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    normalized = normalized.split("T", 1)[0].strip()
    parts = re.split(r"[-/]", normalized)
    if len(parts) != 3:
        raise ValueError("تاریخ باید به صورت ۱۴۰۵/۰۵/۱۲ وارد شود")
    year, month, day = (int(part) for part in parts)
    if year < 1700:
        year, month, day = jalali_to_gregorian(year, month, day)
    return date(year, month, day)


def format_jalali_date(value: date) -> str:
    year, month, day = gregorian_to_jalali(value.year, value.month, value.day)
    return f"{year:04d}/{month:02d}/{day:02d}"


def format_market_expiry(expiry: str, market: str) -> str:
    """Render every market expiry in a consistent Solar Hijri format."""
    try:
        parsed = parse_user_date(expiry)
    except (TypeError, ValueError):
        return str(expiry or "").replace("-", "/")
    return format_jalali_date(parsed)


def format_jalali_datetime(value: datetime) -> str:
    """Format a timezone-aware datetime with a Solar Hijri calendar date."""
    year, month, day = gregorian_to_jalali(value.year, value.month, value.day)
    return f"{year:04d}/{month:02d}/{day:02d} {value:%H:%M}"
