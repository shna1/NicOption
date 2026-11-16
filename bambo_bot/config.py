from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_url: str = field(
        default_factory=lambda: os.getenv(
            "BAMBO_API_URL",
            "https://server.bambo.fund/api/options/option-gold-strategy",
        )
    )
    option_goods_url: str = field(
        default_factory=lambda: os.getenv(
            "BAMBO_OPTION_GOODS_URL",
            "https://server.bambo.fund/api/options/option-goods",
        )
    )
    ime_cdn_url: str = field(
        default_factory=lambda: os.getenv(
            "IME_CDN_URL", "https://cdn.ime.co.ir"
        ).rstrip("/")
    )
    tehran_strategy_url: str = field(
        default_factory=lambda: os.getenv(
            "BAMBO_TEHRAN_STRATEGY_URL",
            "https://server.bambo.fund/api/options/strategies/{strategy}",
        )
    )
    tehran_market_watch_url: str = field(
        default_factory=lambda: os.getenv(
            "BAMBO_TEHRAN_MARKET_WATCH_URL",
            "https://server.bambo.fund/api/options/market-watch",
        )
    )
    tsetmc_option_market_watch_url: str = field(
        default_factory=lambda: os.getenv(
            "TSETMC_OPTION_MARKET_WATCH_URL",
            "https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0",
        )
    )
    bambo_session_cookie: str = field(
        default_factory=lambda: os.getenv("BAMBO_SESSION_COOKIE", "").strip()
    )
    interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("INTERVAL_MINUTES", "10"))
    )
    long_underlying_interest_rate: float = field(
        default_factory=lambda: float(os.getenv("LONG_UNDERLYING_INTEREST_RATE", "40"))
    )
    covered_call_warning_return: float = field(
        default_factory=lambda: float(os.getenv("COVERED_CALL_WARNING_RETURN", "40"))
    )
    covered_call_min_annual_return: float = field(
        default_factory=lambda: float(os.getenv("COVERED_CALL_MIN_ANNUAL_RETURN", "40"))
    )
    tehran_daily_limit_percent: float = field(
        default_factory=lambda: float(os.getenv("TEHRAN_DAILY_LIMIT_PERCENT", "3"))
    )
    leveraged_daily_limit_percent: float = field(
        default_factory=lambda: float(os.getenv("LEVERAGED_DAILY_LIMIT_PERCENT", "4"))
    )
    goods_daily_limit_percent: float = field(
        default_factory=lambda: float(os.getenv("GOODS_DAILY_LIMIT_PERCENT", "10"))
    )
    trades_file: Path = field(
        default_factory=lambda: Path(os.getenv("TRADES_FILE", "trades.json"))
    )
    http_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("HTTP_TIMEOUT_SECONDS", "25"))
    )
    http_retries: int = field(
        default_factory=lambda: int(os.getenv("HTTP_RETRIES", "3"))
    )
    forecast_cache_minutes: int = field(
        default_factory=lambda: int(os.getenv("FORECAST_CACHE_MINUTES", "10"))
    )

    def validate(self) -> None:
        if self.interval_minutes <= 0:
            raise ValueError("INTERVAL_MINUTES must be positive")
        if self.long_underlying_interest_rate < 0:
            raise ValueError("LONG_UNDERLYING_INTEREST_RATE cannot be negative")
        if self.covered_call_warning_return < 0:
            raise ValueError("COVERED_CALL_WARNING_RETURN cannot be negative")
        if self.covered_call_min_annual_return < 0:
            raise ValueError("COVERED_CALL_MIN_ANNUAL_RETURN cannot be negative")
        if min(
            self.tehran_daily_limit_percent,
            self.leveraged_daily_limit_percent,
            self.goods_daily_limit_percent,
        ) < 0:
            raise ValueError("Daily price limits cannot be negative")
        if not self.tsetmc_option_market_watch_url:
            raise ValueError("TSETMC_OPTION_MARKET_WATCH_URL cannot be empty")
        if not self.ime_cdn_url:
            raise ValueError("IME_CDN_URL cannot be empty")
        if self.forecast_cache_minutes <= 0:
            raise ValueError("FORECAST_CACHE_MINUTES must be positive")
