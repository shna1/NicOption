from __future__ import annotations

import csv
import hashlib
import json
import re
import threading
import time
from bisect import bisect_left
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Iterator, Mapping
from urllib.parse import quote, urlparse

import requests
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from bambo_bot.dates import gregorian_to_jalali, jalali_to_gregorian

from .models import (
    DataIssue,
    DataSource,
    EconomicIndicator,
    IndicatorObservation,
    IndicatorSource,
    IngestionRun,
)


REQUIRED_COLUMNS = {"indicator_code", "period_date", "value", "unit", "original_source"}
CANONICAL_COLUMNS = REQUIRED_COLUMNS | {
    "published_at", "source_url", "status", "revision", "notes", "external_id"
}
ALLOWED_STATUSES = {choice for choice, _ in IndicatorObservation.Status.choices}
FREQUENCY_DAYS = {"daily": 1, "monthly": 31, "quarterly": 92, "annual": 366}
_DIGIT_TABLE = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩−٫٬", "01234567890123456789-. ,".replace(" ", ""))
_PROCESS_LOCK = threading.Lock()
_ADVISORY_LOCK_ID = 708_214_511


class ImportConfigurationError(RuntimeError):
    pass


class ConcurrentImportError(RuntimeError):
    pass


def freshness_deadline(indicator: EconomicIndicator, period: date) -> date:
    return period + timedelta(days=FREQUENCY_DAYS[indicator.frequency] + indicator.expected_release_lag_days + indicator.stale_after_days)


@dataclass(frozen=True)
class RowIssue:
    row_number: int | None
    severity: str
    code: str
    message: str
    indicator_code: str = ""
    source_name: str = ""
    external_id: str = ""
    safe_payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRow:
    row_number: int
    indicator: EconomicIndicator
    source: DataSource
    period_date: date
    value: Decimal
    unit: str
    published_at: datetime | None
    status: str
    source_url: str
    external_id: str
    requested_revision: int | None
    notes: str
    content_hash: str


@dataclass
class ImportSummary:
    seen: int = 0
    inserted: int = 0
    revised: int = 0
    unchanged: int = 0
    rejected: int = 0
    issues: list[RowIssue] = field(default_factory=list)
    run: IngestionRun | None = None

    def as_dict(self) -> dict:
        return {
            "seen": self.seen,
            "inserted": self.inserted,
            "revised": self.revised,
            "unchanged": self.unchanged,
            "rejected": self.rejected,
        }


def normalize_headers(row: Mapping) -> dict[str, object]:
    return {str(key or "").strip().lower(): value for key, value in row.items()}


def blank_to_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_decimal(value) -> Decimal | None:
    text = blank_to_none(value)
    if text is None:
        return None
    normalized = text.translate(_DIGIT_TABLE).replace(",", "").replace("٬", "").replace(" ", "")
    try:
        parsed = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("value must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError("value must be a finite decimal")
    return parsed


def parse_period_date(value) -> date:
    text = blank_to_none(value)
    if text is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("period_date must be an unambiguous ISO Gregorian date")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("period_date is invalid") from exc


def parse_published_at(value) -> datetime | None:
    text = blank_to_none(value)
    if text is None:
        return None
    parsed = parse_datetime(text)
    if parsed is None:
        raise ValueError("published_at must be an ISO-8601 datetime")
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def parse_url(value) -> str:
    text = blank_to_none(value)
    if text is None:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an http(s) URL")
    return text


def parse_revision(value) -> int | None:
    text = blank_to_none(value)
    if text is None:
        return None
    normalized = text.translate(_DIGIT_TABLE)
    if not normalized.isdigit():
        raise ValueError("revision must be a non-negative integer")
    return int(normalized)


def _content_hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_payload(row: Mapping) -> dict:
    safe_keys = ("indicator_code", "period_date", "unit", "original_source", "status", "external_id")
    return {key: str(row.get(key))[:180] for key in safe_keys if blank_to_none(row.get(key)) is not None}


def _source_link_is_valid(links: list[tuple], indicator_id: int, source_id: int, period: date | None) -> bool:
    if period is None:
        return False
    return any(
        linked_indicator == indicator_id
        and linked_source == source_id
        and (valid_from is None or valid_from <= period)
        and (valid_to is None or valid_to >= period)
        for linked_indicator, linked_source, valid_from, valid_to in links
    )


def normalize_and_validate_rows(rows: Iterable[Mapping], *, indicator_code: str = "") -> tuple[list[NormalizedRow], ImportSummary]:
    summary = ImportSummary()
    indicators = {item.code: item for item in EconomicIndicator.objects.filter(is_active=True)}
    sources = {item.name.casefold(): item for item in DataSource.objects.filter(is_active=True)}
    links = list(IndicatorSource.objects.filter(source__is_active=True).values_list("indicator_id", "source_id", "valid_from", "valid_to"))
    normalized_rows: list[NormalizedRow] = []
    seen: dict[tuple, str] = {}
    future_limit = timezone.localdate() + timedelta(days=int(getattr(settings, "ECONOMIC_MAX_FUTURE_DAYS", 7)))

    for row_number, raw in enumerate(rows, start=2):
        summary.seen += 1
        row = normalize_headers(raw)
        missing_columns = REQUIRED_COLUMNS - set(row)
        if missing_columns:
            summary.rejected += 1
            summary.issues.append(RowIssue(row_number, "error", "missing_columns", f"Missing columns: {', '.join(sorted(missing_columns))}", safe_payload=_safe_payload(row)))
            continue
        code = str(blank_to_none(row.get("indicator_code")) or "").upper()
        source_name = str(blank_to_none(row.get("original_source")) or "")
        external_id = str(blank_to_none(row.get("external_id")) or "")[:180]
        if indicator_code and code != indicator_code.upper():
            continue
        indicator = indicators.get(code)
        source = sources.get(source_name.casefold())
        errors: list[tuple[str, str]] = []
        if not indicator:
            errors.append(("unknown_indicator", "indicator_code is not an active catalog entry"))
        if not source_name:
            errors.append(("blank_source", "original_source is required and cannot be Google Sheets implicitly"))
        elif not source:
            errors.append(("unknown_source", "original_source must be configured as an active DataSource"))
        try:
            period = parse_period_date(row.get("period_date"))
            if period > future_limit:
                errors.append(("future_period", "period_date is unreasonably far in the future"))
        except ValueError as exc:
            period = None
            errors.append(("invalid_period_date", str(exc)))
        try:
            value = parse_decimal(row.get("value"))
            if value is None:
                errors.append(("missing_value", "value is required; blank is not zero"))
        except ValueError as exc:
            value = None
            errors.append(("invalid_decimal", str(exc)))
        unit = str(blank_to_none(row.get("unit")) or "")
        if not unit:
            errors.append(("missing_unit", "unit is required"))
        elif indicator and not indicator.unit:
            errors.append(("indicator_unit_unconfigured", "indicator unit must be configured before import"))
        elif indicator and unit != indicator.unit:
            errors.append(("unit_mismatch", "row unit does not match indicator metadata"))
        status = str(blank_to_none(row.get("status")) or IndicatorObservation.Status.PUBLISHED).lower()
        if status not in ALLOWED_STATUSES:
            errors.append(("invalid_status", "status is not allowed"))
        try:
            published_at = parse_published_at(row.get("published_at"))
        except ValueError as exc:
            published_at = None
            errors.append(("invalid_published_at", str(exc)))
        try:
            source_url = parse_url(row.get("source_url"))
        except ValueError as exc:
            source_url = ""
            errors.append(("invalid_url", str(exc)))
        try:
            requested_revision = parse_revision(row.get("revision"))
        except ValueError as exc:
            requested_revision = None
            errors.append(("invalid_revision", str(exc)))
        if indicator and source and not _source_link_is_valid(links, indicator.pk, source.pk, period):
            errors.append(("source_not_linked", "source is not linked to this indicator"))
        if indicator and source and indicator.kind == EconomicIndicator.Kind.OFFICIAL and source.source_type != DataSource.SourceType.OFFICIAL:
            errors.append(("source_kind_mismatch", "an official indicator requires an official original source"))
        if errors:
            summary.rejected += 1
            summary.issues.extend(RowIssue(row_number, "error", issue_code, message, code, source_name, external_id, _safe_payload(row)) for issue_code, message in errors)
            continue
        notes = str(blank_to_none(row.get("notes")) or "")[:1000]
        hash_payload = {
            "value": str(value), "unit": unit,
            "published_at": published_at.isoformat() if published_at else None,
            "status": status, "source_url": source_url,
            "external_id": external_id, "notes": notes,
        }
        content_hash = _content_hash(hash_payload)
        grain = (indicator.pk, source.pk, period)
        previous_hash = seen.get(grain)
        if previous_hash is not None:
            severity = "warning" if previous_hash == content_hash else "error"
            issue_code = "duplicate_exact" if previous_hash == content_hash else "duplicate_conflict"
            summary.issues.append(RowIssue(row_number, severity, issue_code, "duplicate row in the same input", code, source_name, external_id, _safe_payload(row)))
            if severity == "error":
                summary.rejected += 1
            else:
                summary.unchanged += 1
            continue
        seen[grain] = content_hash
        if published_at is None:
            summary.issues.append(RowIssue(row_number, "warning", "missing_published_at", "published_at is missing", code, source_name, external_id, _safe_payload(row)))
        elif published_at.date() < period:
            summary.issues.append(RowIssue(row_number, "warning", "chronology", "published_at is before period_date", code, source_name, external_id, _safe_payload(row)))
        normalized_rows.append(NormalizedRow(row_number, indicator, source, period, value, unit, published_at, status, source_url, external_id, requested_revision, notes, content_hash))
    return normalized_rows, summary


def _persist_issues(run: IngestionRun, issues: list[RowIssue]) -> None:
    indicator_map = {item.code: item for item in EconomicIndicator.objects.filter(code__in={issue.indicator_code for issue in issues if issue.indicator_code})}
    source_map = {item.name: item for item in DataSource.objects.filter(name__in={issue.source_name for issue in issues if issue.source_name})}
    DataIssue.objects.bulk_create([
        DataIssue(
            ingestion_run=run,
            indicator=indicator_map.get(issue.indicator_code),
            source=source_map.get(issue.source_name),
            row_number=issue.row_number,
            external_row_id=issue.external_id,
            severity=issue.severity,
            issue_code=issue.code,
            message=issue.message,
            safe_payload=issue.safe_payload,
        ) for issue in issues
    ], batch_size=500)


def _apply_rows(rows: list[NormalizedRow], summary: ImportSummary) -> None:
    if not rows:
        return
    indicator_ids = {row.indicator.pk for row in rows}
    source_ids = {row.source.pk for row in rows}
    dates = {row.period_date for row in rows}
    locked_versions = list(IndicatorObservation.objects.select_for_update().filter(
        indicator_id__in=indicator_ids, source_id__in=source_ids, period_date__in=dates,
    ))
    current_by_key = {
        (item.indicator_id, item.source_id, item.period_date): item
        for item in locked_versions if item.is_current_revision
    }
    max_revision_by_key: dict[tuple, int] = {}
    for item in locked_versions:
        key = (item.indicator_id, item.source_id, item.period_date)
        max_revision_by_key[key] = max(item.revision, max_revision_by_key.get(key, -1))

    min_period = min(row.period_date for row in rows) - timedelta(days=400)
    histories: dict[tuple[int, int], list[IndicatorObservation]] = {}
    for item in IndicatorObservation.objects.filter(
        indicator_id__in=indicator_ids, source_id__in=source_ids,
        is_current_revision=True, period_date__gte=min_period,
    ).order_by("period_date"):
        histories.setdefault((item.indicator_id, item.source_id), []).append(item)

    now = timezone.now()
    to_retire: list[IndicatorObservation] = []
    to_create: list[IndicatorObservation] = []
    threshold = Decimal(str(getattr(settings, "ECONOMIC_OUTLIER_PERCENT", "200")))
    for row in rows:
        key = (row.indicator.pk, row.source.pk, row.period_date)
        current = current_by_key.get(key)
        if current and current.content_hash == row.content_hash:
            summary.unchanged += 1
            continue
        revision = max_revision_by_key.get(key, -1) + 1
        if row.requested_revision is not None:
            revision = max(revision, row.requested_revision)
        if current:
            current.is_current_revision = False
            to_retire.append(current)
            summary.revised += 1
        else:
            summary.inserted += 1
        observation = IndicatorObservation(
            indicator=row.indicator, source=row.source, period_date=row.period_date,
            value=row.value, unit=row.unit, published_at=row.published_at,
            collected_at=now, revision=revision, status=row.status,
            source_url=row.source_url, external_id=row.external_id,
            content_hash=row.content_hash, supersedes=current,
            is_current_revision=True, raw_metadata={"notes": row.notes} if row.notes else {},
        )
        to_create.append(observation)
        history = histories.get((row.indicator.pk, row.source.pk), [])
        prior_dates = [item.period_date for item in history]
        position = bisect_left(prior_dates, row.period_date)
        previous = history[position - 1] if position else None
        if previous and previous.value != 0:
            percent = abs((observation.value - previous.value) / previous.value * Decimal("100"))
            if percent > threshold:
                summary.issues.append(RowIssue(row.row_number, "warning", "unusual_change", f"Change exceeds configured {threshold}% threshold", row.indicator.code, row.source.name, row.external_id, {"indicator_code": row.indicator.code, "period_date": row.period_date.isoformat()}))
    if to_retire:
        IndicatorObservation.objects.bulk_update(to_retire, ("is_current_revision",), batch_size=500)
    if to_create:
        IndicatorObservation.objects.bulk_create(to_create, batch_size=500)


def import_rows(
    rows: Iterable[Mapping], *, channel: str, dry_run: bool = False,
    strict: bool = False, indicator_code: str = "", metadata: dict | None = None,
    created_by=None,
) -> ImportSummary:
    normalized, summary = normalize_and_validate_rows(rows, indicator_code=indicator_code)
    has_errors = any(issue.severity in {"error", "critical"} for issue in summary.issues)
    if dry_run:
        current_hashes = {(o.indicator_id, o.source_id, o.period_date): o.content_hash for o in IndicatorObservation.objects.filter(is_current_revision=True, indicator_id__in={row.indicator.pk for row in normalized})}
        for row in normalized:
            existing = current_hashes.get((row.indicator.pk, row.source.pk, row.period_date))
            if existing == row.content_hash:
                summary.unchanged += 1
            elif existing:
                summary.revised += 1
            else:
                summary.inserted += 1
        return summary

    with transaction.atomic():
        run = IngestionRun.objects.create(
            channel=channel,
            metadata=metadata or {},
            created_by=created_by,
        )
        summary.run = run
        if strict and has_errors:
            run.status = IngestionRun.Status.FAILED
        else:
            _apply_rows(normalized, summary)
            run.status = IngestionRun.Status.PARTIAL if has_errors else IngestionRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.rows_seen = summary.seen
        run.rows_inserted = summary.inserted
        run.rows_revised = summary.revised
        run.rows_unchanged = summary.unchanged
        run.rows_rejected = summary.rejected
        run.error_summary = f"{summary.rejected} rejected row(s)" if summary.rejected else ""
        run.save()
        _persist_issues(run, summary.issues)
    return summary


def iter_csv_rows(path: str | Path) -> Iterator[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ImportConfigurationError("CSV header is missing")
        yield from reader


class GoogleSheetsClient:
    READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

    def __init__(self, credential_file: str, *, timeout: int = 20, retries: int = 2):
        if not credential_file or not Path(credential_file).is_file():
            raise ImportConfigurationError("GOOGLE_SERVICE_ACCOUNT_FILE does not exist")
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
        except ImportError as exc:
            raise ImportConfigurationError("google-auth must be installed") from exc
        credentials = service_account.Credentials.from_service_account_file(credential_file, scopes=[self.READONLY_SCOPE])
        self.session = AuthorizedSession(credentials)
        self.timeout = timeout
        self.retries = retries

    def rows(self, spreadsheet_id: str, sheet_range: str) -> Iterator[dict]:
        if not spreadsheet_id or not sheet_range:
            raise ImportConfigurationError("ECONOMIC_GOOGLE_SHEET_ID and ECONOMIC_GOOGLE_SHEET_RANGE are required")
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values/{quote(sheet_range, safe='')}"
        response = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt >= self.retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        values = response.json().get("values", [])
        if not values:
            return
        headers = [str(item).strip() for item in values[0]]
        for values_row in values[1:]:
            yield dict(zip(headers, values_row + [""] * (len(headers) - len(values_row))))


class PriceTodayClient:
    BASE_URL = "https://api.priceto.day/v1/history/irr"

    def __init__(self, *, timeout: int = 20, retries: int = 2, session=None):
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()

    def monthly_rows(self, *, slug: str, indicator_code: str, source_name: str,
                     unit: str, from_date: date, to_date: date | None = None) -> tuple[list[dict], dict]:
        url = f"{self.BASE_URL}/{quote(slug, safe='')}"
        params = {"from": from_date.isoformat()}
        if to_date:
            params["to"] = to_date.isoformat()
        response = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "nicoption-economic-data/1.0 (+https://nicoption.ir)",
                    },
                )
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt >= self.retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        payload = response.json()
        if payload.get("success") is not True or not isinstance(payload.get("result"), list):
            raise ValueError("PriceToDay response does not contain a successful result list")

        daily: dict[date, tuple[datetime, Decimal]] = {}
        duplicates = 0
        for item in payload["result"]:
            if not isinstance(item, Mapping):
                raise ValueError("PriceToDay result item must be an object")
            try:
                timestamp = datetime.fromisoformat(str(item["time"]).replace("Z", "+00:00"))
                price = Decimal(str(item["price"]))
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                raise ValueError("PriceToDay result contains an invalid time or price") from exc
            if timezone.is_naive(timestamp) or not price.is_finite() or price <= 0:
                raise ValueError("PriceToDay time must be timezone-aware and price must be positive")
            market_day = timezone.localtime(timestamp).date()
            duplicates += int(market_day in daily)
            daily[market_day] = (timestamp, price)

        monthly: dict[tuple[int, int], tuple[date, datetime, Decimal]] = {}
        for day, (timestamp, price) in daily.items():
            jalali_year, jalali_month, _ = gregorian_to_jalali(day.year, day.month, day.day)
            key = (jalali_year, jalali_month)
            if key not in monthly or day >= monthly[key][0]:
                monthly[key] = (day, timestamp, price)

        today = timezone.localdate()
        current_jalali_year, current_jalali_month, _ = gregorian_to_jalali(
            today.year, today.month, today.day
        )
        rows = []
        for (jalali_year, jalali_month), (observed_day, timestamp, price) in sorted(monthly.items()):
            period_date = date(*jalali_to_gregorian(jalali_year, jalali_month, 1))
            observed_jalali = gregorian_to_jalali(
                observed_day.year, observed_day.month, observed_day.day
            )
            rows.append({
                "indicator_code": indicator_code,
                # The database stays Gregorian-compatible, but this date is the
                # Gregorian representation of day one of the Solar Hijri month.
                "period_date": period_date.isoformat(),
                "value": format(price, "f"),
                "unit": unit,
                "published_at": timestamp.isoformat(),
                "original_source": source_name,
                "source_url": f"{url}?from={from_date.isoformat()}",
                "status": "preliminary" if (jalali_year, jalali_month) == (
                    current_jalali_year, current_jalali_month
                ) else "published",
                "revision": "",
                "notes": (
                    "آخرین قیمت معتبر ماه شمسی؛ "
                    f"دوره {jalali_year:04d}/{jalali_month:02d}؛ "
                    f"تاریخ مشاهده {observed_jalali[0]:04d}/{observed_jalali[1]:02d}/{observed_jalali[2]:02d}"
                ),
                "external_id": f"pricetoday:{slug}:jalali:{jalali_year:04d}-{jalali_month:02d}",
            })
        return rows, {
            "raw_rows": len(payload["result"]),
            "unique_days": len(daily),
            "duplicate_days": duplicates,
            "monthly_rows": len(rows),
        }


class FinpyTSEClient:
    """Adapt FinPy-TSE's daily TEDPIX frame to canonical monthly observations."""

    SOURCE_URL = "https://cdn.tsetmc.com/api/Index/GetIndexB2History/32097828799138957"

    def __init__(self, *, retries: int = 2, history_loader=None):
        self.retries = retries
        self._history_loader = history_loader

    def _load_history(self, **kwargs):
        if self._history_loader is None:
            try:
                import finpy_tse
            except ImportError as exc:
                raise ImportConfigurationError("finpy-tse must be installed") from exc
            self._history_loader = finpy_tse.Get_CWI_History
        for attempt in range(self.retries + 1):
            try:
                return self._history_loader(**kwargs)
            except Exception as exc:
                if attempt >= self.retries:
                    raise ValueError("FinPy-TSE history fetch failed") from exc
                time.sleep(min(2 ** attempt, 4))

    def monthly_rows(self, *, from_date: date, to_date: date,
                     indicator_code: str = "IR_TEDPIX",
                     source_name: str = "TSETMC via FinPy-TSE",
                     unit: str = "واحد") -> tuple[list[dict], dict]:
        from_jalali = gregorian_to_jalali(from_date.year, from_date.month, from_date.day)
        to_jalali = gregorian_to_jalali(to_date.year, to_date.month, to_date.day)
        frame = self._load_history(
            start_date=f"{from_jalali[0]:04d}-{from_jalali[1]:02d}-{from_jalali[2]:02d}",
            end_date=f"{to_jalali[0]:04d}-{to_jalali[1]:02d}-{to_jalali[2]:02d}",
            ignore_date=False,
            just_adj_close=True,
            show_weekday=False,
            double_date=True,
        )
        if frame is None or not hasattr(frame, "columns"):
            raise ValueError("FinPy-TSE did not return a data frame")
        required = {"Date", "Adj Close"}
        if not required.issubset(set(frame.columns)):
            raise ValueError("FinPy-TSE TEDPIX data frame is missing Date or Adj Close")

        daily: dict[date, Decimal] = {}
        duplicates = 0
        for _, item in frame.iterrows():
            raw_day = item["Date"]
            if hasattr(raw_day, "date"):
                market_day = raw_day.date()
            else:
                market_day = date.fromisoformat(str(raw_day)[:10])
            try:
                value = Decimal(str(item["Adj Close"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError("FinPy-TSE TEDPIX data contains an invalid value") from exc
            if not value.is_finite() or value <= 0:
                raise ValueError("FinPy-TSE TEDPIX values must be positive finite decimals")
            if market_day < from_date or market_day > to_date:
                continue
            duplicates += int(market_day in daily)
            daily[market_day] = value

        monthly: dict[tuple[int, int], tuple[date, Decimal]] = {}
        for market_day, value in daily.items():
            jalali_year, jalali_month, _ = gregorian_to_jalali(
                market_day.year, market_day.month, market_day.day
            )
            key = (jalali_year, jalali_month)
            if key not in monthly or market_day >= monthly[key][0]:
                monthly[key] = (market_day, value)

        today = timezone.localdate()
        current_jalali = gregorian_to_jalali(today.year, today.month, today.day)[:2]
        rows = []
        for (jalali_year, jalali_month), (observed_day, value) in sorted(monthly.items()):
            period_date = date(*jalali_to_gregorian(jalali_year, jalali_month, 1))
            observed_jalali = gregorian_to_jalali(
                observed_day.year, observed_day.month, observed_day.day
            )
            rows.append({
                "indicator_code": indicator_code,
                "period_date": period_date.isoformat(),
                "value": format(value, "f"),
                "unit": unit,
                "published_at": datetime.combine(
                    observed_day,
                    datetime.min.time(),
                    tzinfo=timezone.get_current_timezone(),
                ).isoformat(),
                "original_source": source_name,
                "source_url": self.SOURCE_URL,
                "status": "preliminary" if (jalali_year, jalali_month) == current_jalali else "published",
                "revision": "",
                "notes": (
                    "آخرین مقدار معتبر شاخص کل در ماه شمسی از FinPy-TSE؛ "
                    f"دوره {jalali_year:04d}/{jalali_month:02d}؛ "
                    f"تاریخ مشاهده {observed_jalali[0]:04d}/{observed_jalali[1]:02d}/{observed_jalali[2]:02d}"
                ),
                "external_id": f"finpy-tse:tedpix:jalali:{jalali_year:04d}-{jalali_month:02d}",
            })
        if not rows:
            raise ValueError("FinPy-TSE returned no TEDPIX observations in the requested range")
        return rows, {
            "raw_rows": len(frame),
            "unique_days": len(daily),
            "duplicate_days": duplicates,
            "monthly_rows": len(rows),
        }


@contextmanager
def ingestion_lock():
    acquired = False
    postgres_lock = connection.vendor == "postgresql"
    if postgres_lock:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [_ADVISORY_LOCK_ID])
            acquired = bool(cursor.fetchone()[0])
    else:
        acquired = _PROCESS_LOCK.acquire(blocking=False)
    if not acquired:
        raise ConcurrentImportError("another economic-data import is already running")
    try:
        yield
    finally:
        if postgres_lock:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [_ADVISORY_LOCK_ID])
        else:
            _PROCESS_LOCK.release()
