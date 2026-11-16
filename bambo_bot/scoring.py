from __future__ import annotations

from bisect import bisect_right


def liquidity_percentile(value: float | None, universe: list[float]) -> float:
    positives = sorted(float(item) for item in universe if item is not None and item > 0)
    if value is None or value <= 0 or not positives:
        return 0.0
    return bisect_right(positives, float(value)) / len(positives)


def covered_call_score(
    *, annual_return, premium, base_price, option_delta, delta_estimated,
    transaction_value, liquidity_universe, days, quote_gap_percent,
) -> dict:
    annual = max(0.0, float(annual_return or 0.0))
    return_points = min(annual / 100.0, 1.0) * 30.0

    protection = 0.0
    if base_price and base_price > 0 and premium is not None:
        protection = max(0.0, float(premium) / float(base_price) * 100.0)
    protection_points = min(protection / 20.0, 1.0) * 20.0
    liquidity_points = liquidity_percentile(transaction_value, liquidity_universe) * 20.0

    if option_delta is None:
        delta_points = 0.0
    else:
        quality = max(0.0, 1.0 - abs(float(option_delta) - 0.75) / 0.50)
        delta_points = quality * 15.0 * (0.85 if delta_estimated else 1.0)

    remaining = max(0.0, float(days or 0.0))
    if remaining < 5:
        time_points = 2.0
    elif remaining <= 90:
        time_points = 10.0
    elif remaining <= 180:
        time_points = 10.0 - (remaining - 90.0) / 90.0 * 4.0
    else:
        time_points = 5.0

    if quote_gap_percent is None:
        quote_points = 2.5
    else:
        gap = abs(float(quote_gap_percent))
        quote_points = 5.0 if gap <= 2 else 4.0 if gap <= 5 else 3.0 if gap <= 10 else 1.5 if gap <= 20 else 0.5

    components = {
        "return": round(return_points, 1), "protection": round(protection_points, 1),
        "liquidity": round(liquidity_points, 1), "delta": round(delta_points, 1),
        "time": round(time_points, 1), "quote": round(quote_points, 1),
    }
    total = round(sum(components.values()), 1)
    label = "عالی" if total >= 80 else "خوب" if total >= 65 else "متوسط" if total >= 50 else "ضعیف"
    return {"score": total, "label": label, "components": components, "downside_protection_percent": round(protection, 2)}
