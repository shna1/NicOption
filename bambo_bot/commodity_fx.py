from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from .client import BamboClient
from .config import Settings
from .dates import format_jalali_datetime
from .forecast import fetch_chartix_history


TEHRAN = ZoneInfo("Asia/Tehran")
TROY_OUNCE_GRAMS = 31.1034768
POUNDS_PER_KILOGRAM = 2.20462262185
GOLD_BAR_GRAMS = 0.1
GOLD_BAR_PURITY = 0.995
SILVER_BAR_GRAMS = 1.0
SILVER_BAR_PURITY = 0.9999
FULL_COIN_FINE_GOLD_GRAMS = 8.13598 * 0.9


ASSET_SPECS = (
    ("silver", "شمش نقره", "SilverBar", "si", "یک گرم نقره با عیار ۹۹۹٫۹"),
    ("copper", "کاتد مس", "CopperCthd", "hg", "یک کیلوگرم کاتد مس"),
    ("gold", "شمش طلا (طلای ۲۴ عیار)", "GoldBar", "gc", "۰٫۱ گرم شمش طلا با حداقل عیار ۹۹۵"),
    ("coin", "گواهی سکه تمام", "GoldCoin", "gc", "یک سکه تمام طرح جدید با حدود ۷٫۳۲۲ گرم طلای خالص"),
)


def _last_close(symbol: str, settings: Settings, session=None) -> tuple[float, str]:
    start = (datetime.now(TEHRAN) - timedelta(days=20)).strftime("%Y-%m-%d")
    frame = fetch_chartix_history(
        symbol, date_from=start, timeout=settings.http_timeout_seconds, session=session
    )
    row = frame.iloc[-1]
    return float(row["close"]), row["date"].date().isoformat()


def _usd_content(asset_id: str, benchmarks: dict[str, float]) -> float:
    if asset_id == "gold":
        return benchmarks["gc"] * GOLD_BAR_GRAMS * GOLD_BAR_PURITY / TROY_OUNCE_GRAMS
    if asset_id == "silver":
        return benchmarks["si"] * SILVER_BAR_GRAMS * SILVER_BAR_PURITY / TROY_OUNCE_GRAMS
    if asset_id == "copper":
        return benchmarks["hg"] * POUNDS_PER_KILOGRAM
    if asset_id == "coin":
        return benchmarks["gc"] * FULL_COIN_FINE_GOLD_GRAMS / TROY_OUNCE_GRAMS
    raise ValueError("دارایی برای محاسبه دلار ضمنی شناخته نشد")


def _conversion_details(asset_id: str, benchmarks: dict[str, float], usd_content: float) -> dict:
    if asset_id == "copper":
        return {
            "formula": "قیمت جهانی مس × ۲٫۲۰۴۶۲ پوند در هر کیلوگرم",
            "calculation": f"{benchmarks['hg']:.4f} × {POUNDS_PER_KILOGRAM:.5f} = {usd_content:.4f}",
            "result_unit": "دلار برای هر کیلوگرم کاتد مس",
            "note": "هر گواهی CopperCthd معادل یک کیلوگرم است؛ مالیات تحویل فیزیکی در این نرخ معاملاتی منظور نشده است.",
        }
    if asset_id == "silver":
        return {
            "formula": "قیمت جهانی نقره × ۰٫۹۹۹۹ گرم ÷ ۳۱٫۱۰۳۴۸",
            "calculation": f"{benchmarks['si']:.4f} × {SILVER_BAR_PURITY:.4f} ÷ {TROY_OUNCE_GRAMS:.5f} = {usd_content:.4f}",
            "result_unit": "دلار برای هر گواهی یک‌گرمی",
        }
    if asset_id == "gold":
        return {
            "formula": "قیمت جهانی طلا × ۰٫۱ گرم × عیار ۰٫۹۹۵ ÷ ۳۱٫۱۰۳۴۸",
            "calculation": f"{benchmarks['gc']:.4f} × {GOLD_BAR_GRAMS:.1f} × {GOLD_BAR_PURITY:.3f} ÷ {TROY_OUNCE_GRAMS:.5f} = {usd_content:.4f}",
            "result_unit": "دلار برای هر گواهی ۰٫۱ گرمی",
        }
    return {
        "formula": "قیمت جهانی طلا × ۷٫۳۲۲۳۸ گرم طلای خالص ÷ ۳۱٫۱۰۳۴۸",
        "calculation": f"{benchmarks['gc']:.4f} × {FULL_COIN_FINE_GOLD_GRAMS:.5f} ÷ {TROY_OUNCE_GRAMS:.5f} = {usd_content:.4f}",
        "result_unit": "دلار برای هر سکه تمام",
    }


def build_commodity_fx_payload(
    continuous_rows: list[dict],
    benchmarks: dict[str, float],
    benchmark_dates: dict[str, str],
    free_market_rial: float,
    free_market_date: str,
    *,
    generated_at: datetime | None = None,
) -> dict:
    rows = {str(row.get("ContractCode") or ""): row for row in continuous_rows}
    free_market_toman = free_market_rial / 10
    assets = []
    for asset_id, label, contract_code, benchmark_key, unit_label in ASSET_SPECS:
        row = rows.get(contract_code)
        if not row:
            continue
        usd_content = _usd_content(asset_id, benchmarks)
        conversion = _conversion_details(asset_id, benchmarks, usd_content)
        quotes = []
        for quote_id, quote_label, field in (
            ("bid", "بهترین خرید", "BidPrice1"),
            ("last", "آخرین معامله", "LastTradedPrice"),
            ("ask", "بهترین فروش", "AskPrice1"),
        ):
            raw_price = row.get(field)
            if raw_price is None or float(raw_price) <= 0:
                continue
            price_rial = float(raw_price)
            implied_toman = (price_rial / 10) / usd_content
            difference = implied_toman - free_market_toman
            quotes.append({
                "id": quote_id,
                "label": quote_label,
                "certificate_price_rial": price_rial,
                "implied_usd_toman": implied_toman,
                "difference_toman": difference,
                "difference_percent": difference / free_market_toman * 100,
            })
        assets.append({
            "id": asset_id,
            "label": label,
            "contract_code": contract_code,
            "contract_description": row.get("ContractDescription"),
            "unit_label": unit_label,
            "benchmark_key": benchmark_key,
            "benchmark_price": benchmarks[benchmark_key],
            "benchmark_date": benchmark_dates[benchmark_key],
            "usd_value_per_certificate": usd_content,
            "conversion": conversion,
            "market_updated_at": row.get("LastUpdate"),
            "quotes": quotes,
        })
    now = generated_at or datetime.now(TEHRAN)
    return {
        "generated_at": now.isoformat(),
        "generated_at_display": format_jalali_datetime(now),
        "free_market": {
            "price_toman": free_market_toman,
            "price_rial": free_market_rial,
            "date": free_market_date,
            "symbol": "TDT",
        },
        "benchmarks": {
            "gold": {"price": benchmarks["gc"], "unit": "دلار/اونس", "date": benchmark_dates["gc"]},
            "silver": {"price": benchmarks["si"], "unit": "دلار/اونس", "date": benchmark_dates["si"]},
            "copper": {"price": benchmarks["hg"], "unit": "دلار/پوند", "date": benchmark_dates["hg"]},
        },
        "assets": assets,
        "sources": {
            "domestic": {"name": "بورس کالای ایران", "url": "https://cdn.ime.co.ir/"},
            "benchmarks": {"name": "Chartix", "url": "https://max.chartix.ir/"},
        },
        "methodology": (
            "دلار ضمنی از تقسیم قیمت تومانی هر گواهی بر ارزش دلاری مقدار فلز متناظر محاسبه می‌شود. "
            "کارمزد، مالیات، هزینه انبارداری و حباب سکه در این عدد تعدیل نشده‌اند."
        ),
    }


def collect_commodity_fx(settings: Settings, *, session=None) -> dict:
    http = session or requests.Session()
    client = BamboClient(settings)
    snapshot = client._fetch_ime_snapshot()
    symbols = {"gc": "COMEX_GC1!", "si": "COMEX_SI1!", "hg": "COMEX_HG1!"}
    benchmarks: dict[str, float] = {}
    dates: dict[str, str] = {}
    for key, symbol in symbols.items():
        benchmarks[key], dates[key] = _last_close(symbol, settings, http)
    free_market_rial, free_market_date = _last_close("TDT", settings, http)
    return build_commodity_fx_payload(
        snapshot.get("continuous") or [], benchmarks, dates,
        free_market_rial, free_market_date,
    )


class CommodityFxCache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._payload: dict | None = None
        self._loaded_at = 0.0

    def get(self, *, force: bool = False) -> dict:
        max_age = max(1, self.settings.interval_minutes) * 60
        with self._lock:
            if force or self._payload is None or time.monotonic() - self._loaded_at >= max_age:
                self._payload = collect_commodity_fx(self.settings)
                self._loaded_at = time.monotonic()
            return self._payload
