from __future__ import annotations

import threading
import time
from datetime import datetime
from urllib.parse import quote

from .assets import normalize_fa
from .config import Settings
from .http import make_session


ALIASES = {
    # The covered-call underlying shown by Bambo is the gold certificate
    # represented by TSETMC symbol «طلا», not Lotus ETF's own price series.
    "صندوق طلای لوتوس": ("طلا",),
    "صندوق طلای دنا زاگرس": ("جواهر",),
    "صندوق طلای درخشان": ("درخشان",),
    "صندوق طلای کارآمد": ("کارآمد",),
    "هم‌تراز": ("هم تراز",),
}


COMMODITY_HISTORIES = {
    # Each gold-bar deposit certificate represents 0.1 gram of 24K gold.
    "طلای 24 عیار": {
        "slug": "geram24",
        "symbol": "شمش طلا",
        "title": "طلای ۲۴ عیار · معادل ۰.۱ گرم",
        "scale": 0.1,
        "note": "قیمت فلز پایه با مقیاس ۰.۱ گرم (معادل هر گواهی شمش طلا)؛ نرخ گواهی بورس کالا ممکن است اندکی اختلاف داشته باشد.",
    },
    "شمش نقره": {
        "slug": "silver_999",
        "symbol": "شمش نقره",
        "title": "نقره ۹۹۹ · هر گرم",
        "scale": 1.0,
        "note": "قیمت هر گرم نقره ۹۹۹ به‌عنوان فلز پایه؛ نرخ گواهی بورس کالا ممکن است اندکی اختلاف داشته باشد.",
    },
}


class PriceHistoryClient:
    """Resolve a Bambo underlying symbol and fetch daily TSETMC closing prices."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = make_session(settings.http_retries)
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], tuple[float, dict]] = {}

    def fetch(self, asset: str, source_asset: str = "") -> dict:
        key = (normalize_fa(asset), normalize_fa(source_asset))
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < 600:
                return cached[1]

        commodity = COMMODITY_HISTORIES.get(normalize_fa(asset))
        if commodity:
            result = self._fetch_commodity_history(asset, commodity)
        else:
            instrument = self._resolve(asset, source_asset)
            result = self._fetch_tsetmc_history(asset, source_asset, instrument)

        with self._lock:
            self._cache[key] = (time.monotonic(), result)
        return result

    def fetch_current_purchase_price(
        self, asset: str, source_asset: str = ""
    ) -> float | None:
        """Return best ask, falling back to the latest traded price."""
        instrument = self._resolve(asset, source_asset)
        if not instrument:
            return None
        ins_code = str(instrument.get("insCode") or "")
        if not ins_code:
            return None

        response = self.session.get(
            f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}",
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        limits = response.json().get("bestLimits", [])
        first_level = next(
            (row for row in limits if int(row.get("number") or 0) == 1),
            None,
        )
        if first_level:
            try:
                best_ask = float(first_level.get("pMeOf") or 0)
            except (TypeError, ValueError):
                best_ask = 0.0
            if best_ask > 0:
                return best_ask

        response = self.session.get(
            f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{ins_code}",
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        info = response.json().get("closingPriceInfo", {})
        for field in ("pDrCotVal", "pClosing", "priceYesterday"):
            try:
                price = float(info.get(field) or 0)
            except (TypeError, ValueError):
                continue
            if price > 0:
                return price
        return None

    def _fetch_commodity_history(self, asset: str, commodity: dict) -> dict:
        response = self.session.get(
            "https://api.tgju.org/v1/market/indicator/summary-table-data/"
            + commodity["slug"],
            params={
                "lang": "fa",
                "order_dir": "desc",
                "draw": 1,
                "start": 0,
                "length": 180,
            },
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json().get("data", [])
        points = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 7:
                continue
            try:
                price = float(str(row[3]).replace(",", "")) * commodity["scale"]
                low = float(str(row[1] or row[3]).replace(",", "")) * commodity["scale"]
                high = float(str(row[2] or row[3]).replace(",", "")) * commodity["scale"]
                date = datetime.strptime(str(row[6]), "%Y/%m/%d").date().isoformat()
                points.append({"date": date, "price": price, "low": low, "high": high})
            except (TypeError, ValueError):
                continue
        points.sort(key=lambda item: item["date"])
        return {
            "asset": asset,
            "symbol": commodity["symbol"],
            "title": commodity["title"],
            "source": "TGJU",
            "note": commodity["note"],
            "points": points[-180:],
        }

    def _fetch_tsetmc_history(
        self, asset: str, source_asset: str, instrument: dict | None
    ) -> dict:
        if not instrument:
            result = {
                "asset": asset,
                "symbol": source_asset or asset,
                "source": "TSETMC",
                "points": [],
                "message": "برای این دارایی تاریخچه قیمت قابل اتکایی در TSETMC پیدا نشد.",
            }
            return result
        ins_code = str(instrument.get("insCode") or "")
        response = self.session.get(
            f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{ins_code}/0",
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        rows = response.json().get("closingPriceDaily", [])
        points = []
        for row in rows:
            date_raw = str(row.get("dEven") or "")
            price = row.get("pClosing")
            if len(date_raw) != 8 or price is None:
                continue
            try:
                date = datetime.strptime(date_raw, "%Y%m%d").date().isoformat()
                points.append(
                    {
                        "date": date,
                        "price": float(price),
                        "low": float(row.get("priceMin") or price),
                        "high": float(row.get("priceMax") or price),
                    }
                )
            except (TypeError, ValueError):
                continue
        points.sort(key=lambda item: item["date"])
        return {
            "asset": asset,
            "symbol": instrument.get("lVal18AFC") or source_asset or asset,
            "title": instrument.get("lVal30") or asset,
            "source": "TSETMC",
            "points": points[-180:],
        }

    def _resolve(self, asset: str, source_asset: str) -> dict | None:
        candidates = []
        # Explicit canonical mappings take precedence over Bambo's display label.
        for value in (*ALIASES.get(asset, ()), source_asset, asset):
            value = normalize_fa(value)
            if value and value not in candidates and value != "دارایی پایه":
                candidates.append(value)
        for candidate in candidates:
            response = self.session.get(
                "https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/" + quote(candidate),
                timeout=self.settings.http_timeout_seconds,
            )
            response.raise_for_status()
            rows = response.json().get("instrumentSearch", [])
            exact = [
                row for row in rows
                if normalize_fa(str(row.get("lVal18AFC") or "")) == candidate
                and str(row.get("insCode") or "")
            ]
            if exact:
                exact.sort(key=lambda row: (int(row.get("lastDate") or 0) != 1, int(row.get("flow") or 9)))
                return exact[0]
        return None
