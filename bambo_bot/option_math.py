from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, sqrt


@dataclass(frozen=True)
class CallGreeks:
    delta: float
    implied_volatility: float


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _call_price(spot: float, strike: float, years: float, rate: float, volatility: float) -> float:
    if volatility <= 0 or years <= 0:
        return max(spot - strike * exp(-rate * years), 0.0)
    scale = volatility * sqrt(years)
    d1 = (log(spot / strike) + (rate + 0.5 * volatility**2) * years) / scale
    d2 = d1 - scale
    return spot * _normal_cdf(d1) - strike * exp(-rate * years) * _normal_cdf(d2)


def call_greeks_from_volatility(
    spot: float | None,
    strike: float | None,
    days: int | float | None,
    annual_rate_percent: float = 40,
    volatility: float = 0.35,
) -> CallGreeks | None:
    if None in (spot, strike, days):
        return None
    spot = float(spot)
    strike = float(strike)
    years = float(days) / 365.0
    rate = max(0.0, float(annual_rate_percent)) / 100.0
    volatility = float(volatility)
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        return None
    scale = volatility * sqrt(years)
    d1 = (log(spot / strike) + (rate + 0.5 * volatility**2) * years) / scale
    return CallGreeks(delta=_normal_cdf(d1), implied_volatility=volatility)


def call_greeks_from_price(
    spot: float | None,
    strike: float | None,
    days: int | float | None,
    option_price: float | None,
    annual_rate_percent: float = 40,
) -> CallGreeks | None:
    """Infer call IV from its quote and return Black–Scholes delta.

    The risk-free rate is treated as a continuously compounded annual rate. Quotes
    outside no-arbitrage bounds return ``None`` instead of producing a misleading
    delta.
    """
    if None in (spot, strike, days, option_price):
        return None
    spot = float(spot)
    strike = float(strike)
    years = float(days) / 365.0
    quote = float(option_price)
    rate = max(0.0, float(annual_rate_percent)) / 100.0
    if spot <= 0 or strike <= 0 or years <= 0 or quote < 0:
        return None

    lower = max(spot - strike * exp(-rate * years), 0.0)
    upper = spot
    tolerance = max(1e-7, spot * 1e-8)
    if quote < lower - tolerance or quote > upper + tolerance:
        return None
    quote = min(max(quote, lower), upper)
    if quote <= lower + tolerance:
        forward_moneyness = spot - strike * exp(-rate * years)
        delta = 1.0 if forward_moneyness > 0 else 0.0
        return CallGreeks(delta=delta, implied_volatility=0.0)

    low_vol, high_vol = 1e-8, 1.0
    while high_vol < 20.0 and _call_price(spot, strike, years, rate, high_vol) < quote:
        high_vol *= 2.0
    if _call_price(spot, strike, years, rate, high_vol) < quote - tolerance:
        return None

    for _ in range(100):
        mid = (low_vol + high_vol) / 2.0
        if _call_price(spot, strike, years, rate, mid) < quote:
            low_vol = mid
        else:
            high_vol = mid
    volatility = (low_vol + high_vol) / 2.0
    scale = volatility * sqrt(years)
    d1 = (log(spot / strike) + (rate + 0.5 * volatility**2) * years) / scale
    return CallGreeks(delta=_normal_cdf(d1), implied_volatility=volatility)
