from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from .assets import canonical_asset
from .models import option_ask_gap_percent


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class LongUnderlyingOpportunity:
    asset: str
    symbol: str
    expiry: str
    days: int
    state: str
    profit_percent: float
    base_price: float
    option_bid: float
    strike: float
    breakeven: float | None
    transaction_value: float
    volume: float
    option_ask: float | None = None
    volume_is_proxy: bool = False
    source_asset: str = ""
    option_last: float | None = None
    itm_percent: float | None = None

    @property
    def option_gap_percent(self) -> float | None:
        return option_ask_gap_percent(self.option_ask, self.option_last)


def calculate_profit_percent(
    row: dict[str, Any],
    interest_rate: float,
    *,
    price_basis: str = "bid",
    option_last: float | None = None,
) -> float | None:
    """Return how much the interest-adjusted option cost is below the base."""
    base_price = _number(row.get("askPrice1Base"))
    option_price = (
        option_last if price_basis == "last"
        else _number(row.get("askPrice1Option")) if price_basis == "ask"
        else _number(row.get("bidPrice1Option"))
    )
    strike = _number(row.get("dueDatePrice"))
    days = _number(row.get("days"))
    if (
        base_price is None
        or option_price is None
        or strike is None
        or base_price == 0
        or days is None
    ):
        return None
    period_rate = max(0.0, interest_rate) / 100 * days / 365
    adjusted_cost = strike + option_price - strike * period_rate
    return round((base_price - adjusted_cost) / base_price * 100, 2)


def select_positive_opportunities(
    rows: list[dict[str, Any]],
    interest_rate: float,
    volume_by_symbol: dict[str, float] | None = None,
    asset_resolver: Callable[[dict[str, Any], str], str | None] | None = None,
    volume_is_proxy: bool = False,
    option_last_by_symbol: dict[str, float] | None = None,
    price_basis: str = "bid",
) -> dict[tuple[str, str], list[LongUnderlyingOpportunity]]:
    groups: dict[tuple[str, str], list[LongUnderlyingOpportunity]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbolOption") or "")
        asset = (
            asset_resolver(row, symbol)
            if asset_resolver
            else canonical_asset(str(row.get("baseSymbol") or ""), symbol)
        )
        expiry = str(row.get("expiration_date") or "").split("T", 1)[0]
        volume = (
            (volume_by_symbol or {}).get(symbol)
            if volume_by_symbol is not None
            else _number(row.get("volume"))
        )
        volume = volume or 0.0
        base_price = _number(row.get("askPrice1Base"))
        option_bid = _number(row.get("bidPrice1Option"))
        option_ask = _number(row.get("askPrice1Option"))
        option_last = (
            option_last_by_symbol.get(symbol)
            if option_last_by_symbol and symbol in option_last_by_symbol
            else _number(row.get("optionPrice"))
        )
        calculation_price = (
            option_last if price_basis == "last"
            else option_ask if price_basis == "ask"
            else option_bid
        )
        profit_percent = calculate_profit_percent(
            row,
            interest_rate,
            price_basis=price_basis,
            option_last=option_last,
        )
        strike = _number(row.get("dueDatePrice"))
        if (
            not asset
            or not symbol
            or not expiry
            or profit_percent is None
            or profit_percent <= 0
            or base_price is None
            or option_bid is None
            or calculation_price is None
            or strike is None
            or volume <= 0
        ):
            continue
        opportunity = LongUnderlyingOpportunity(
            asset=asset,
            source_asset=str(row.get("baseSymbol") or asset),
            symbol=symbol,
            expiry=expiry,
            days=int(_number(row.get("days")) or 0),
            state=str(row.get("state") or "").upper(),
            profit_percent=profit_percent,
            base_price=base_price,
            option_bid=option_bid,
            option_ask=option_ask,
            strike=strike,
            breakeven=strike + calculation_price,
            transaction_value=_number(row.get("value")) or 0.0,
            volume=volume,
            volume_is_proxy=volume_is_proxy,
            option_last=option_last,
            itm_percent=_number(row.get("itmPercent")),
        )
        groups[(asset, expiry)].append(opportunity)

    for opportunities in groups.values():
        opportunities.sort(
            key=lambda item: (-item.profit_percent, -item.transaction_value, item.symbol)
        )
    return dict(groups)


def build_volume_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows:
        symbol = str(row.get("code_id") or row.get("symbol") or "")
        if symbol:
            result[symbol] = _number(row.get("vol_transaction")) or 0.0
    return result


def build_option_last_price_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows:
        symbol = str(row.get("code_id") or row.get("symbol") or "")
        price = _number(row.get("close_price"))
        if symbol and price is not None and price > 0:
            result[symbol] = price
    return result
