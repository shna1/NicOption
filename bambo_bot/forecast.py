from __future__ import annotations

import base64
import json
import math
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from Crypto.Cipher import AES
from Crypto.Hash import MD5

from .config import Settings
from .dates import format_jalali_date, format_jalali_datetime


TEHRAN = ZoneInfo("Asia/Tehran")
CHARTIX_HISTORY_URL = "https://datafeed.chartix.ir/api/v1/history"
CHARTIX_PASSPHRASE = "e122cac15bb1f7c2dff422aa73674580"
START_DATE = "2020-01-01"
MODEL_START_DATE = "2025-10-21"
INITIAL_CAPITAL = 100_000_000.0


def _decrypt_cryptojs(ciphertext_b64: str, passphrase: str) -> str:
    raw = base64.b64decode(ciphertext_b64)
    if len(raw) < 17 or raw[:8] != b"Salted__":
        raise ValueError("پاسخ رمزگذاری‌شده Chartix معتبر نیست")
    salt, ciphertext = raw[8:16], raw[16:]
    key_iv, previous = b"", b""
    while len(key_iv) < 48:
        previous = MD5.new(previous + passphrase.encode("utf-8") + salt).digest()
        key_iv += previous
    decrypted = AES.new(key_iv[:32], AES.MODE_CBC, key_iv[32:48]).decrypt(ciphertext)
    padding = decrypted[-1]
    if padding < 1 or padding > 16:
        raise ValueError("رمزگشایی داده Chartix ناموفق بود")
    return decrypted[:-padding].decode("utf-8")


def fetch_chartix_history(
    symbol: str,
    *,
    date_from: str = START_DATE,
    date_to: str | None = None,
    timeout: int = 25,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    date_to = date_to or (datetime.now(TEHRAN) + timedelta(days=1)).strftime("%Y-%m-%d")
    start_ts = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
    end_ts = int(datetime.strptime(date_to, "%Y-%m-%d").timestamp())
    client = session or requests
    response = client.get(
        CHARTIX_HISTORY_URL,
        params={
            "symbol": symbol,
            "resolution": "1D",
            "from": start_ts,
            "to": end_ts,
            "countback": 10000,
            "id": "null",
            "adj": 0,
        },
        headers={"user-agent": "Mozilla/5.0", "referer": "https://max.chartix.ir/"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = json.loads(_decrypt_cryptojs(response.text, CHARTIX_PASSPHRASE))
    required = ("t", "o", "h", "l", "c")
    if not all(key in payload for key in required):
        raise ValueError(f"داده کافی برای نماد {symbol} دریافت نشد")
    size = len(payload["t"])
    volume = payload.get("v") or [0] * size
    frame = pd.DataFrame({
        "date": pd.to_datetime(payload["t"], unit="s"),
        "open": payload["o"], "high": payload["h"], "low": payload["l"],
        "close": payload["c"], "volume": volume,
    })
    if frame.empty:
        raise ValueError(f"تاریخچه نماد {symbol} خالی است")
    return frame


def _prepare_history(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    result = frame.copy().set_index("date")
    result.columns = [f"o_{symbol}", f"h_{symbol}", f"l_{symbol}", f"c_{symbol}", f"v_{symbol}"]
    result.index = pd.to_datetime(result.index)
    return result[~result.index.duplicated(keep="first")]


def _prepare_model(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = ["price", "volume", "intrinsic_price", "bubble_pct"]
    rolling_bubble = result["bubble_pct"].rolling(30)
    result["bubble_zscore"] = (result["bubble_pct"] - rolling_bubble.mean()) / rolling_bubble.std()
    with np.errstate(invalid="ignore"):
        log_volume = np.log1p(result["volume"])
    result["volume_zscore"] = (
        log_volume - log_volume.rolling(30).mean()
    ) / log_volume.rolling(30).std()
    result["bubble_acceleration"] = result["bubble_pct"].diff().diff()
    result["date"] = result.index
    return result.dropna().reset_index(drop=True)


def build_model_inputs(histories: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    prepared = [_prepare_history(histories[key], key) for key in (
        "usdirr", "usdt", "goldbar", "gc1", "si1", "hg1", "copper_c", "silverbar"
    )]
    all_data = pd.concat(prepared, axis=1)
    all_data["c_usdirr"] = all_data["c_usdirr"] / 10
    all_data["c_goldbar"] = all_data["c_goldbar"] * 1000
    all_data = all_data.loc[all_data.index > MODEL_START_DATE].ffill()

    all_data["gold_intrinsic"] = (((all_data["c_gc1"] * all_data["c_usdt"]) / 31.103) * 995 * 1000) / 1000
    all_data["gold_bubble"] = ((all_data["c_goldbar"] / all_data["gold_intrinsic"]) - 1).round(2) * 100
    gold = _prepare_model(all_data[["c_goldbar", "v_goldbar", "gold_intrinsic", "gold_bubble"]])

    all_data["c_copper_c"] = all_data["c_copper_c"] / 10
    all_data["copper_intrinsic"] = (all_data["c_hg1"] * 2204.62 * all_data["c_usdt"]) / 1000
    all_data["copper_bubble"] = ((all_data["c_copper_c"] / all_data["copper_intrinsic"]) - 1).round(2) * 100
    copper = _prepare_model(all_data[["c_copper_c", "v_copper_c", "copper_intrinsic", "copper_bubble"]])
    copper["volume_zscore_bucket"] = pd.qcut(
        copper["volume_zscore"], 10, labels=False, duplicates="drop"
    ).astype(int)

    all_data["c_silverbar"] = all_data["c_silverbar"] / 10
    all_data["silver_intrinsic"] = (((all_data["c_si1"] * all_data["c_usdt"]) / 31.103) * 999.9) / 1000
    all_data["silver_bubble"] = ((all_data["c_silverbar"] / all_data["silver_intrinsic"]) - 1).round(2) * 100
    silver = _prepare_model(all_data[["c_silverbar", "v_silverbar", "silver_intrinsic", "silver_bubble"]])
    silver["bubble_zscore_bucket"] = pd.qcut(
        silver["bubble_zscore"], 10, labels=False, duplicates="drop"
    ).astype(int)
    silver["volume_zscore_bucket"] = pd.qcut(
        silver["volume_zscore"], 10, labels=False, duplicates="drop"
    ).astype(int)
    return {"goldbar": gold, "copper": copper, "silverbar": silver}


def _finish_backtest(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["position"] = result["raw_position"].shift(1).fillna(0)
    result["daily_return"] = result["price"].pct_change().fillna(0)
    result["strategy_return"] = result["position"] * result["daily_return"]
    result["equity"] = (1 + result["strategy_return"]).cumprod() * INITIAL_CAPITAL
    result["bh_equity"] = (1 + result["daily_return"]).cumprod() * INITIAL_CAPITAL
    result["strategy_drawdown"] = result["equity"] / result["equity"].cummax() - 1
    result["bh_drawdown"] = result["bh_equity"] / result["bh_equity"].cummax() - 1
    return result


def backtest_gold(frame: pd.DataFrame, entry: float = -0.55, exit_: float = 0.0) -> pd.DataFrame:
    position, positions, signals = 0, [], []
    for value in frame["bubble_zscore"]:
        signal = "hold"
        if position == 0 and value <= entry:
            position, signal = 1, "buy"
        elif position == 1 and value >= exit_:
            position, signal = 0, "sell"
        positions.append(position); signals.append(signal)
    result = frame.copy()
    result["raw_position"], result["signal"] = positions, signals
    return _finish_backtest(result)


def backtest_copper(frame: pd.DataFrame, entry_bucket: int = 8, holding_days: int = 10) -> pd.DataFrame:
    position = days_in_trade = 0
    positions, signals = [], []
    for bucket in frame["volume_zscore_bucket"]:
        signal = "hold"
        if position == 0 and bucket >= entry_bucket:
            position, days_in_trade, signal = 1, 0, "buy"
        elif position == 1:
            days_in_trade += 1
            if days_in_trade >= holding_days:
                position, days_in_trade, signal = 0, 0, "sell"
        positions.append(position); signals.append(signal)
    result = frame.copy()
    result["raw_position"], result["signal"] = positions, signals
    return _finish_backtest(result)


def backtest_silver(
    frame: pd.DataFrame,
    entry_bubble: int = 4,
    entry_volume: int = 6,
    exit_bubble: int = 7,
    holding_days: int = 15,
) -> pd.DataFrame:
    position = days_in_trade = 0
    positions, signals = [], []
    for _, row in frame.iterrows():
        signal = "hold"
        if position == 0 and row["bubble_zscore_bucket"] <= entry_bubble and row["volume_zscore_bucket"] >= entry_volume:
            position, days_in_trade, signal = 1, 0, "buy"
        elif position == 1:
            days_in_trade += 1
            if days_in_trade >= holding_days or row["bubble_zscore_bucket"] >= exit_bubble:
                position, days_in_trade, signal = 0, 0, "sell"
        positions.append(position); signals.append(signal)
    result = frame.copy()
    result["raw_position"], result["signal"] = positions, signals
    return _finish_backtest(result)


def _finite(value, digits: int = 4):
    value = float(value)
    return round(value, digits) if math.isfinite(value) else None


def _series(frame: pd.DataFrame, column: str, *, multiplier: float = 1.0) -> list[float | None]:
    return [_finite(value * multiplier, 4) if pd.notna(value) else None for value in frame[column]]


def _asset_payload(
    asset_id: str,
    label: str,
    frame: pd.DataFrame,
    *,
    indicator_series: list[tuple[str, str]],
    thresholds: list[dict],
    rule: str,
    price_divisor: float = 1.0,
) -> dict:
    active_signals = frame[frame["signal"] != "hold"]
    last_signal = active_signals.iloc[-1] if not active_signals.empty else None
    std = frame["strategy_return"].std()
    dates = [value.strftime("%Y-%m-%d") for value in pd.to_datetime(frame["date"])]
    buys = frame[frame["signal"] == "buy"]
    sells = frame[frame["signal"] == "sell"]
    point = lambda row: {"date": row["date"].strftime("%Y-%m-%d"), "value": _finite(row["price"] / price_divisor, 2)}
    return {
        "id": asset_id,
        "label": label,
        "rule": rule,
        "latest_signal": None if last_signal is None else last_signal["signal"],
        "latest_signal_label": "بدون سیگنال" if last_signal is None else ("خرید" if last_signal["signal"] == "buy" else "فروش"),
        "signal_date": None if last_signal is None else last_signal["date"].strftime("%Y-%m-%d"),
        "signal_date_display": None if last_signal is None else format_jalali_date(last_signal["date"].date()),
        "signal_price": None if last_signal is None else _finite(last_signal["price"] / price_divisor, 2),
        "current_price": _finite(frame["price"].iloc[-1] / price_divisor, 2),
        "current_date": dates[-1],
        "current_date_display": format_jalali_date(frame["date"].iloc[-1].date()),
        "current_position": bool(frame["raw_position"].iloc[-1]),
        "metrics": {
            "strategy_return_percent": _finite((frame["equity"].iloc[-1] / INITIAL_CAPITAL - 1) * 100, 2),
            "buy_hold_return_percent": _finite((frame["bh_equity"].iloc[-1] / INITIAL_CAPITAL - 1) * 100, 2),
            "strategy_mdd_percent": _finite(frame["strategy_drawdown"].min() * 100, 2),
            "buy_hold_mdd_percent": _finite(frame["bh_drawdown"].min() * 100, 2),
            "sharpe": None if not std or pd.isna(std) else _finite(frame["strategy_return"].mean() / std * np.sqrt(252), 2),
            "trades": int((frame["signal"] == "buy").sum()),
            "exposure_percent": _finite(frame["position"].mean() * 100, 2),
        },
        "charts": {
            "price": {
                "dates": dates,
                "series": [{"name": "قیمت", "values": _series(frame, "price", multiplier=1 / price_divisor)}],
                "buy_points": [point(row) for _, row in buys.iterrows()],
                "sell_points": [point(row) for _, row in sells.iterrows()],
            },
            "indicator": {
                "dates": dates,
                "series": [{"name": name, "values": _series(frame, column)} for name, column in indicator_series],
                "thresholds": thresholds,
            },
            "equity": {
                "dates": dates,
                "series": [
                    {"name": "استراتژی", "values": _series(frame, "equity")},
                    {"name": "خرید و نگهداری", "values": _series(frame, "bh_equity")},
                ],
            },
            "drawdown": {
                "dates": dates,
                "series": [
                    {"name": "استراتژی", "values": _series(frame, "strategy_drawdown", multiplier=100)},
                    {"name": "خرید و نگهداری", "values": _series(frame, "bh_drawdown", multiplier=100)},
                ],
            },
        },
    }


def collect_forecast(settings: Settings, *, session: requests.Session | None = None) -> dict:
    symbols = {
        "gc1": "COMEX_GC1!", "hg1": "COMEX_HG1!", "si1": "COMEX_SI1!",
        "copper_c": "COPPERCTHD", "usdirr": "TDT", "usdt": "USDTIRT",
        "goldbar": "GOLDBAR", "silverbar": "SILVERBAR",
    }
    histories = {
        key: fetch_chartix_history(
            symbol, timeout=settings.http_timeout_seconds, session=session
        ) for key, symbol in symbols.items()
    }
    inputs = build_model_inputs(histories)
    results = {
        "goldbar": backtest_gold(inputs["goldbar"]),
        "copper": backtest_copper(inputs["copper"]),
        "silverbar": backtest_silver(inputs["silverbar"]),
    }
    now = datetime.now(TEHRAN)
    assets = [
        _asset_payload(
            "goldbar", "شمش طلا", results["goldbar"],
            indicator_series=[("Z-Score حباب", "bubble_zscore")],
            thresholds=[{"label": "ورود", "value": -0.55}, {"label": "خروج", "value": 0}],
            rule="خرید در Z-Score حباب ≤ ‎−۰٫۵۵ و فروش در Z-Score ≥ ۰",
            price_divisor=10000,
        ),
        _asset_payload(
            "silverbar", "شمش نقره", results["silverbar"],
            indicator_series=[("دهک حباب", "bubble_zscore_bucket"), ("دهک حجم", "volume_zscore_bucket")],
            thresholds=[{"label": "حداکثر دهک حباب ورود", "value": 4}, {"label": "حداقل دهک حجم ورود", "value": 6}, {"label": "دهک حباب خروج", "value": 7}],
            rule="ورود با دهک حباب ≤ ۴ و دهک حجم ≥ ۶؛ خروج پس از ۱۵ روز یا دهک حباب ≥ ۷",
        ),
        _asset_payload(
            "copper", "مس کاتد", results["copper"],
            indicator_series=[("دهک حجم", "volume_zscore_bucket")],
            thresholds=[{"label": "حداقل دهک ورود", "value": 8}],
            rule="خرید در دهک حجم ≥ ۸ و خروج پس از ۱۰ روز معاملاتی",
        ),
    ]
    return {
        "generated_at": now.isoformat(),
        "generated_at_display": format_jalali_datetime(now),
        "source": {
            "name": "Chartix",
            "url": "https://max.chartix.ir/",
            "grain": "کندل روزانه",
            "model_start_date": MODEL_START_DATE,
            "model_start_date_display": format_jalali_date(datetime.strptime(MODEL_START_DATE, "%Y-%m-%d").date()),
        },
        "methodology": {
            "initial_capital": INITIAL_CAPITAL,
            "execution": "سیگنال در پایان روز ساخته و بازده از روز معاملاتی بعد محاسبه می‌شود.",
            "warning": "این خروجی نتیجه یک مدل و بک‌تست تاریخی است و تضمین‌کننده بازده آینده یا توصیه سرمایه‌گذاری نیست.",
        },
        "assets": assets,
    }


class ForecastCache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._payload: dict | None = None
        self._loaded_at = 0.0

    def get(self, *, force: bool = False) -> dict:
        max_age = max(60, self.settings.forecast_cache_minutes * 60)
        with self._lock:
            if force or self._payload is None or time.monotonic() - self._loaded_at >= max_age:
                self._payload = collect_forecast(self.settings)
                self._loaded_at = time.monotonic()
            return self._payload
