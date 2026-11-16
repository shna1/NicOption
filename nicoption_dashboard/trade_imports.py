from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction

from bambo_bot.dates import parse_user_date
from bambo_bot.trades import TradeStore, _analytics_snapshot, _number

from .models import TradeRecord, UnderlyingPositionRecord


MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 1000

COMMON_HEADERS = {
    "بازار", "دارایی پایه", "نماد اختیار", "تاریخ ورود",
    "تعداد کل", "تعداد با هدف اعمال", "تعداد نوسان‌گیری پرمیوم",
    "قیمت پایه ورود", "پرمیوم ورود", "قیمت اعمال", "کارمزد ورود",
}
OPEN_HEADERS = COMMON_HEADERS | {"تاریخ سررسید"}
CLOSED_HEADERS = COMMON_HEADERS | {
    "تاریخ خروج", "روش خروج", "قیمت پایه خروج", "قیمت اختیار خروج",
    "روز تا سررسید در ورود", "کارمزد خروج", "یادداشت",
}

STRATEGIES = {"کاوردکال": "covered_call", "خرید اختیار خرید": "long_call"}
POSITION_TYPES = {**STRATEGIES, "خرید دارایی پایه": "underlying"}
MARKETS = {"بورس تهران": "tehran", "بورس کالا": "goods"}
ACQUISITION_METHODS = {
    "خرید مستقیم دارایی پایه": "direct",
    "خرید مستقیم": "direct",
    "خرید از طریق اعمال اختیار خرید": "exercise",
    "خرید از طریق اعمال": "exercise",
}
EXIT_METHODS = {
    "آفست": "offset",
    "اعمال": "exercise",
    "اعمال/تخصیص": "exercise",
    "خروج ترکیبی": "mixed",
}


@dataclass(frozen=True)
class ParsedTradeImport:
    records: list[dict]
    errors: list[dict]


def _required_text(row: dict, column: str) -> str:
    value = str(row.get(column) or "").strip()
    if not value:
        raise ValueError(f"ستون «{column}» خالی است")
    return value


def _optional_number(row: dict, column: str, default=0) -> float:
    value = str(row.get(column) or "").strip()
    return float(default) if not value else _number(value, minimum=0)


def _position_label(row: dict) -> str:
    value = str(row.get("نوع موقعیت") or row.get("استراتژی") or "").strip()
    if not value:
        raise ValueError("ستون «نوع موقعیت» خالی است")
    if value not in POSITION_TYPES:
        raise ValueError(f"نوع موقعیت «{value}» پشتیبانی نمی‌شود")
    return value


def _fingerprint(owner_id: int, status: str, record: dict) -> str:
    keys = (
        "_record_type", "strategy_type", "market", "asset", "option_symbol",
        "acquisition_method", "source_option_symbol", "entry_date",
        "expiry", "quantity", "entry_base_price", "entry_premium", "strike",
        "entry_price", "exit_date", "exit_method", "exit_base_price",
        "exit_option_price", "exit_price",
    )
    raw = "\x1f".join(str(record.get(key) or "") for key in keys)
    return hashlib.sha256(f"{owner_id}\x1e{status}\x1e{raw}".encode()).hexdigest()


def _identity_key(record: dict, *, model_type: str | None = None) -> tuple:
    """Return a stable business identity independent of database/import IDs."""
    record_type = model_type or record.get("_record_type")
    if not record_type:
        record_type = "trade" if record.get("strategy_type") else "underlying"
    status = str(record.get("status") or "open")
    if record_type == "trade":
        keys = (
            "strategy_type", "market", "asset", "option_symbol", "entry_date",
            "expiry", "quantity", "entry_base_price", "entry_premium", "strike",
            "exit_date", "exit_method", "exit_base_price", "exit_option_price",
        )
    else:
        keys = (
            "market", "asset", "acquisition_method", "source_option_symbol",
            "entry_date", "import_initial_quantity", "entry_price", "exit_date",
            "exit_price",
        )
    values = []
    for key in keys:
        value = record.get(key)
        if key == "import_initial_quantity" and value in (None, ""):
            value = record.get("quantity")
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        values.append(str(value or "").strip())
    return (record_type, status, *values)


def _base_trade(row: dict, *, status: str) -> dict:
    strategy_label = _position_label(row)
    market_label = _required_text(row, "بازار")
    try:
        strategy = STRATEGIES[strategy_label]
    except KeyError as exc:
        raise ValueError(f"استراتژی «{strategy_label}» پشتیبانی نمی‌شود") from exc
    try:
        market = MARKETS[market_label]
    except KeyError as exc:
        raise ValueError(f"بازار «{market_label}» پشتیبانی نمی‌شود") from exc

    entry_date = parse_user_date(_required_text(row, "تاریخ ورود"))
    if status == "open":
        expiry = parse_user_date(_required_text(row, "تاریخ سررسید"))
    else:
        entry_days = int(_number(
            _required_text(row, "روز تا سررسید در ورود"), minimum=0
        ))
        expiry = entry_date + timedelta(days=entry_days)

    quantity = _number(_required_text(row, "تعداد کل"), minimum=0.0000001)
    exercise_quantity = _optional_number(row, "تعداد با هدف اعمال")
    premium_quantity = _optional_number(row, "تعداد نوسان‌گیری پرمیوم")
    if strategy == "long_call" and abs(
        quantity - exercise_quantity - premium_quantity
    ) > 1e-6:
        raise ValueError("جمع تعداد اعمال و نوسان‌گیری با تعداد کل برابر نیست")

    quote = {
        "asset": _required_text(row, "دارایی پایه"),
        "expiry": expiry.isoformat(),
        "strike": _number(_required_text(row, "قیمت اعمال"), minimum=0.0000001),
        "contract_size": 1,
    }
    payload = {
        "strategy_type": strategy,
        "market": market,
        "asset": quote["asset"],
        "option_symbol": _required_text(row, "نماد اختیار"),
        "entry_date": entry_date.isoformat(),
        "entry_base_price": _required_text(row, "قیمت پایه ورود"),
        "entry_premium": _required_text(row, "پرمیوم ورود"),
        "quantity": quantity,
        "exercise_quantity": exercise_quantity,
        "premium_trade_quantity": premium_quantity,
        "commission": _optional_number(row, "کارمزد ورود"),
    }
    return {"_record_type": "trade", **TradeStore._validated(payload, quote)}


def _underlying_position(row: dict, *, status: str) -> dict:
    market_label = _required_text(row, "بازار")
    try:
        market = MARKETS[market_label]
    except KeyError as exc:
        raise ValueError(f"بازار «{market_label}» پشتیبانی نمی‌شود") from exc
    method_label = _required_text(row, "روش خرید دارایی پایه")
    try:
        method = ACQUISITION_METHODS[method_label]
    except KeyError as exc:
        raise ValueError(f"روش خرید «{method_label}» پشتیبانی نمی‌شود") from exc

    entry_date = parse_user_date(_required_text(row, "تاریخ ورود"))
    initial_quantity = _optional_number(
        row, "تعداد اولیه دارایی پایه",
        default=_number(_required_text(row, "تعداد کل"), minimum=0.0000001),
    )
    if initial_quantity <= 0:
        raise ValueError("تعداد اولیه دارایی پایه باید بزرگ‌تر از صفر باشد")
    available_quantity = _optional_number(
        row, "تعداد آزاد دارایی پایه", default=initial_quantity
    )
    allocated_quantity = _optional_number(
        row, "تعداد تخصیص‌یافته به کاوردکال", default=0
    )
    if available_quantity <= 0:
        raise ValueError("تعداد آزاد دارایی پایه باید بزرگ‌تر از صفر باشد")
    if available_quantity + allocated_quantity > initial_quantity + 1e-6:
        raise ValueError("جمع تعداد آزاد و تخصیص‌یافته از تعداد اولیه بیشتر است")

    item = {
        "_record_type": "underlying",
        "status": status,
        "market": market,
        "asset": _required_text(row, "دارایی پایه"),
        "acquisition_method": method,
        "entry_date": entry_date.isoformat(),
        # Exported standalone rows represent the unallocated inventory. Keeping
        # only that amount in the domain record prevents covered-call collateral
        # from being counted twice.
        "quantity": available_quantity if status == "open" else initial_quantity,
        "entry_price": _number(
            _required_text(row, "قیمت پایه ورود"), minimum=0.0000001
        ),
        "commission": _optional_number(row, "کارمزد ورود"),
        "source_trade_id": None,
        "source_option_symbol": str(row.get("قرارداد منبع اعمال") or "").strip(),
        "exercise_entry_mode": "manual",
        "import_initial_quantity": initial_quantity,
        "import_available_quantity": available_quantity,
        "import_allocated_quantity": allocated_quantity,
    }
    if method == "exercise" and not item["source_option_symbol"]:
        raise ValueError("ستون «قرارداد منبع اعمال» برای خرید از طریق اعمال خالی است")
    current_price = str(row.get("قیمت پایه جاری") or "").strip()
    if current_price:
        item["import_current_price"] = _number(current_price, minimum=0.0000001)
    if status == "closed":
        exit_date = parse_user_date(_required_text(row, "تاریخ خروج"))
        if exit_date < entry_date:
            raise ValueError("تاریخ خروج نمی‌تواند قبل از تاریخ ورود باشد")
        item.update({
            "exit_date": exit_date.isoformat(),
            "exit_price": _number(
                _required_text(row, "قیمت پایه خروج"), minimum=0.0000001
            ),
            "exit_commission": _optional_number(row, "کارمزد خروج"),
            "exit_note": str(row.get("یادداشت") or "").strip(),
        })
        if len(item["exit_note"]) > 500:
            raise ValueError("یادداشت خروج حداکثر ۵۰۰ نویسه است")
        for column, key in (
            ("سود یا زیان قطعی", "import_realized_profit"),
            ("بازده قطعی (درصد)", "import_realized_return_percent"),
            ("بازده سالانه‌شده (درصد)", "import_annualized_return_percent"),
            ("روز نگهداری", "import_holding_days"),
        ):
            value = str(row.get(column) or "").strip()
            if value:
                item[key] = _number(value)
    return item


def _closed_fields(row: dict, trade: dict) -> dict:
    exit_date = parse_user_date(_required_text(row, "تاریخ خروج"))
    if exit_date < parse_user_date(trade["entry_date"]):
        raise ValueError("تاریخ خروج نمی‌تواند قبل از تاریخ ورود باشد")
    method_label = _required_text(row, "روش خروج")
    try:
        method = EXIT_METHODS[method_label]
    except KeyError as exc:
        raise ValueError(f"روش خروج «{method_label}» پشتیبانی نمی‌شود") from exc
    if method == "mixed" and trade["strategy_type"] != "long_call":
        raise ValueError("خروج ترکیبی فقط برای خرید اختیار خرید معتبر است")
    base_price = _number(
        _required_text(row, "قیمت پایه خروج"), minimum=0.0000001
    )
    option_price = _number(
        _required_text(row, "قیمت اختیار خروج"), minimum=0
    )
    note = str(row.get("یادداشت") or "").strip()
    if len(note) > 500:
        raise ValueError("یادداشت خروج حداکثر ۵۰۰ نویسه است")
    expiry = parse_user_date(trade["expiry"])
    return {
        "status": "closed",
        "exit_date": exit_date.isoformat(),
        "exit_method": method,
        "exit_base_price": base_price,
        "exit_option_price": option_price,
        "exit_commission": _optional_number(row, "کارمزد خروج"),
        "exit_note": note,
        "exit_price_basis": "imported_csv",
        "exit_price_confirmed": True,
        **_analytics_snapshot(
            base_price=base_price,
            strike=trade["strike"],
            option_price=option_price,
            days=max(0, (expiry - exit_date).days),
            interest_rate=trade.get("annual_interest_rate", 40),
            covered=trade["strategy_type"] == "covered_call",
            prefix="exit",
        ),
    }


def parse_trade_csv(upload, *, owner_id: int, status: str) -> ParsedTradeImport:
    if status not in {"open", "closed"}:
        raise ValueError("نوع فایل معاملات معتبر نیست")
    if not str(getattr(upload, "name", "")).lower().endswith(".csv"):
        raise ValueError("فایل باید با پسوند CSV باشد")
    content = upload.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise ValueError("حجم فایل CSV نباید بیشتر از ۲ مگابایت باشد")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("فایل CSV باید با UTF-8 ذخیره شده باشد") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = {str(value or "").strip() for value in (reader.fieldnames or [])}
    if not ({"نوع موقعیت", "استراتژی"} & headers):
        raise ValueError("ستون الزامی «نوع موقعیت» موجود نیست")
    missing = (OPEN_HEADERS if status == "open" else CLOSED_HEADERS) - headers
    if missing:
        raise ValueError("ستون‌های الزامی موجود نیستند: " + "، ".join(sorted(missing)))

    records: list[dict] = []
    errors: list[dict] = []
    for index, row in enumerate(reader, start=2):
        if index > MAX_CSV_ROWS + 1:
            raise ValueError("فایل CSV حداکثر می‌تواند ۱۰۰۰ ردیف داشته باشد")
        try:
            position_label = _position_label(row)
            record = (
                _underlying_position(row, status=status)
                if position_label == "خرید دارایی پایه"
                else _base_trade(row, status=status)
            )
            record["status"] = status
            if status == "closed" and record["_record_type"] == "trade":
                record.update(_closed_fields(row, record))
            fingerprint = _fingerprint(owner_id, status, record)
            prefix = "impu_" if record["_record_type"] == "underlying" else "imp_"
            record.update({
                "id": prefix + fingerprint[:27],
                "import_fingerprint": fingerprint,
                "import_source": "csv",
            })
            records.append(record)
        except (ValueError, TypeError) as exc:
            errors.append({"row": index, "detail": str(exc)})
    if not records and not errors:
        raise ValueError("فایل CSV هیچ ردیف معامله‌ای ندارد")
    return ParsedTradeImport(records=records, errors=errors)


def import_trade_records(parsed: ParsedTradeImport, *, owner_id: int) -> dict:
    if parsed.errors:
        raise ValueError("فایل دارای ردیف نامعتبر است و قابل ثبت نیست")
    unique_records = {
        _identity_key(item): item for item in parsed.records
    }
    duplicate_rows = len(parsed.records) - len(unique_records)
    existing = {
        _identity_key(
            {**payload, "status": payload.get("status") or record_status},
            model_type="trade",
        )
        for record_status, payload in TradeRecord.objects.filter(
            owner_id=owner_id
        ).values_list("status", "payload")
    } | {
        _identity_key(
            {**payload, "status": payload.get("status") or record_status},
            model_type="underlying",
        )
        for record_status, payload in UnderlyingPositionRecord.objects.filter(
            owner_id=owner_id
        ).values_list("status", "payload")
    }
    new_records = [
        item for identity, item in unique_records.items() if identity not in existing
    ]
    existing_records = len(unique_records) - len(new_records)
    with transaction.atomic():
        TradeRecord.objects.bulk_create([
            TradeRecord(
                id=item["id"], owner_id=owner_id,
                status=item["status"], payload=item,
            )
            for item in new_records if item["_record_type"] == "trade"
        ])
        UnderlyingPositionRecord.objects.bulk_create([
            UnderlyingPositionRecord(
                id=item["id"], owner_id=owner_id,
                status=item["status"], payload=item,
            )
            for item in new_records if item["_record_type"] == "underlying"
        ])
    imported_trades = sum(
        item["_record_type"] == "trade" for item in new_records
    )
    imported_underlyings = len(new_records) - imported_trades
    return {
        "total": len(parsed.records),
        "imported": len(new_records),
        "skipped": existing_records + duplicate_rows,
        "imported_trades": imported_trades,
        "imported_underlyings": imported_underlyings,
    }
