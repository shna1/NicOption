from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import OrderedDict, defaultdict, deque
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from statistics import median

from .assets import TARGET_ASSETS, canonical_asset, canonical_tehran_asset
from .config import Settings
from .dates import format_jalali_date, format_market_expiry, parse_user_date
from .scan import ScanResult, collect_scan
from .selector import top_unique_contracts
from .history import PriceHistoryClient
from .forecast import ForecastCache
from .financial_contract import financial_capabilities
from .commodity_fx import CommodityFxCache
from .client import BamboClient
from .option_math import call_greeks_from_price, call_greeks_from_volatility
from .models import option_ask_gap_percent, option_quote_gap_percent
from .scoring import covered_call_score
from .trades import (
    AccountStore,
    TradeStore,
    UnderlyingPositionStore,
    build_covered_profit_recognition,
    build_portfolio_asset_ledger,
    build_quote_map,
    build_underlying_quote_map,
    build_account_growth,
    calculate_trade_snapshot,
    calculate_underlying_snapshot,
    quote_key,
    resolve_trade_quote,
    select_trade_valuation_quote,
    summarize_closed_trades,
    summarize_open_trades,
    summarize_underlying_positions,
    underlying_allocations,
    underlying_quote_key,
    validate_underlying_link,
    validate_underlying_position_change,
    prepare_underlying_payload,
    trade_underlying_units,
)


LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("web_static")
ASSET_ORDER = {name: index for index, name in enumerate(TARGET_ASSETS)}


def _number(value):
    return None if value is None else float(value)


def _monthly_return(annual_return: float | None) -> float | None:
    return None if annual_return is None else annual_return / 12.0


def _buyback_fields(
    *, base_price: float | None, premium: float | None, days: int
) -> dict:
    """Return premium-funded buyback ratios for a covered call.

    The period ratio is premium divided by the underlying price. Annual and
    monthly figures use the same simple annualization convention as the
    dashboard's covered-call return, so the two metrics remain comparable.
    """
    if base_price is None or premium is None or base_price <= 0:
        return {
            "buyback_percent": None,
            "buyback_annual_percent": None,
            "buyback_monthly_percent": None,
        }
    period = premium / base_price * 100.0
    annual = period * 365.0 / days if days > 0 else None
    return {
        "buyback_percent": period,
        "buyback_annual_percent": annual,
        "buyback_monthly_percent": _monthly_return(annual),
    }


def _long_cost_fields(
    *,
    base_price: float,
    strike: float,
    premium: float | None,
    days: int,
    interest_rate: float,
) -> dict:
    if premium is None or base_price <= 0:
        return {
            "period_interest_rate_percent": None,
            "risk_free_adjusted_strike": None,
            "exercise_discount_percent": None,
            "exercise_interest_cost": None,
            "adjusted_exercise_plus_premium": None,
            "adjusted_cost_to_base_percent": None,
            "adjusted_cost_vs_base_percent": None,
            "advantage_percent": None,
        }
    period_rate = max(0.0, interest_rate) / 100.0 * max(0, days) / 365.0
    interest_cost = strike * period_rate
    adjusted_strike = strike - interest_cost
    adjusted_cost = strike + premium - interest_cost
    cost_to_base_percent = adjusted_cost / base_price * 100.0 - 100.0
    difference_percent = (adjusted_cost - base_price) / base_price * 100.0
    return {
        "period_interest_rate_percent": period_rate * 100.0,
        "risk_free_adjusted_strike": adjusted_strike,
        "exercise_discount_percent": period_rate * 100.0,
        "exercise_interest_cost": interest_cost,
        "adjusted_exercise_plus_premium": adjusted_cost,
        "adjusted_cost_to_base_percent": cost_to_base_percent,
        "adjusted_cost_vs_base_percent": difference_percent,
        "advantage_percent": -difference_percent,
    }


def _sort_key(market: str, asset: str, expiry: str) -> tuple:
    if market == "goods":
        return (0, ASSET_ORDER.get(asset, 999), expiry)
    return (1, asset, expiry)


def _greek_fields(base_price, strike, days, option_price, interest_rate, *, covered=True) -> dict:
    greeks = call_greeks_from_price(
        base_price, strike, days, option_price, interest_rate
    )
    estimated = greeks is None
    if estimated:
        greeks = call_greeks_from_volatility(
            base_price, strike, days, interest_rate, volatility=0.35
        )
    if greeks is None:
        return {"option_delta": None, "strategy_delta": None, "implied_volatility": None, "delta_estimated": False}
    option_delta = round(greeks.delta, 4)
    return {
        "option_delta": option_delta,
        "strategy_delta": round(1.0 - option_delta, 4) if covered else option_delta,
        "implied_volatility": round(greeks.implied_volatility * 100.0, 2),
        "delta_estimated": estimated,
    }


def _score_fields(item, calculation_price, greeks, liquidity_values) -> dict:
    result = covered_call_score(
        annual_return=item.annual_return, premium=calculation_price,
        base_price=item.base_price, option_delta=greeks["option_delta"],
        delta_estimated=greeks["delta_estimated"],
        transaction_value=item.transaction_value, liquidity_universe=liquidity_values,
        days=item.days, quote_gap_percent=item.option_gap_percent,
    )
    return {"covered_score": result["score"], "covered_score_label": result["label"],
            "covered_score_components": result["components"],
            "downside_protection_percent": result["downside_protection_percent"]}


def calculate_custom_covered_call(payload: dict, liquidity_values: list[float], interest_rate: float = 40) -> dict:
    def number(name: str, *, required: bool = True) -> float | None:
        raw = payload.get(name)
        if raw in (None, ""):
            if required:
                raise ValueError(f"فیلد {name} الزامی است")
            return None
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"مقدار {name} معتبر نیست") from exc

    base = number("base_price")
    premium = number("premium")
    strike = number("strike")
    days = number("days")
    transaction_value = number("transaction_value", required=False)
    option_last = number("option_last", required=False)
    if base <= 0 or premium < 0 or strike <= 0 or days <= 0:
        raise ValueError("قیمت پایه، اعمال و روز تا سررسید باید مثبت باشند")

    positives = [float(value) for value in liquidity_values if value and value > 0]
    liquidity_assumed = transaction_value is None
    if transaction_value is None:
        transaction_value = median(positives) if positives else 0.0
    quote_gap = None if option_last in (None, 0) else round((option_last - premium) / option_last * 100, 2)
    expiry_return = (premium - max(base - strike, 0.0)) / base * 100.0
    annual_return = expiry_return * 365.0 / days
    itm_percent = (base - strike) / base * 100.0
    greeks = _greek_fields(base, strike, days, premium, interest_rate)
    score = covered_call_score(
        annual_return=annual_return, premium=premium, base_price=base,
        option_delta=greeks["option_delta"], delta_estimated=greeks["delta_estimated"],
        transaction_value=transaction_value, liquidity_universe=liquidity_values,
        days=days, quote_gap_percent=quote_gap,
    )
    return {
        "asset": str(payload.get("asset") or "").strip(),
        "symbol": str(payload.get("symbol") or "").strip(),
        "market": str(payload.get("market") or "tehran"),
        "state": "ITM" if base > strike else "ATM" if base == strike else "OTM",
        "base_price": base, "premium": premium, "strike": strike, "days": int(days),
        "breakeven": base - premium, "expiry_return": round(expiry_return, 2),
        "annual_return": round(annual_return, 2),
        "monthly_return": round(annual_return / 12.0, 2),
        "itm_percent": round(itm_percent, 2),
        **_buyback_fields(base_price=base, premium=premium, days=int(days)),
        "transaction_value": transaction_value, "liquidity_assumed": liquidity_assumed,
        "option_last": option_last, "quote_gap_percent": quote_gap,
        **greeks, "covered_score": score["score"], "covered_score_label": score["label"],
        "covered_score_components": score["components"],
        "downside_protection_percent": score["downside_protection_percent"],
        "passes_dashboard_rule": annual_return >= 40 and base > strike,
    }


def _covered_groups(
    selections, *, market: str, price_basis: str = "bid", interest_rate: float = 40
) -> list[dict]:
    covered_groups = []
    liquidity_values = list({pick.contract.symbol: pick.contract.transaction_value for picks in selections.values() for pick in picks}.values())
    for (asset, expiry), picks in sorted(selections.items(), key=lambda item: _sort_key(market, *item[0])):
        if not picks:
            continue
        merged: OrderedDict[str, dict] = OrderedDict()
        for pick in picks:
            item = pick.contract
            if item.symbol not in merged:
                calculation_price = item.option_last if price_basis == "last" else item.option_bid
                greeks = _greek_fields(item.base_price, item.strike, item.days, calculation_price, interest_rate)
                merged[item.symbol] = {
                    "symbol": item.symbol,
                    "source_asset": item.source_asset,
                    "state": item.state,
                    "labels": [],
                    "annual_return": _number(item.annual_return),
                    "monthly_return": _monthly_return(_number(item.annual_return)),
                    "expiry_return": _number(item.expiry_return),
                    "transaction_value": item.transaction_value,
                    "transaction_zero": item.transaction_value == 0,
                    "base_price": _number(item.base_price),
                    "option_bid": _number(item.option_bid),
                    "option_last": _number(item.option_last),
                    "option_gap_percent": _number(item.option_gap_percent),
                    "calculation_price": _number(calculation_price),
                    "price_basis": price_basis,
                    "strike": _number(item.strike),
                    "breakeven": _number(item.breakeven),
                    "itm_percent": _number(item.itm_percent),
                    **_buyback_fields(
                        base_price=_number(item.base_price),
                        premium=_number(calculation_price),
                        days=item.days,
                    ),
                    **greeks,
                    **_score_fields(item, calculation_price, greeks, liquidity_values),
                }
            merged[item.symbol]["labels"].append(pick.category)
        covered_groups.append(
            {
                "market": market,
                "asset": asset,
                "expiry": expiry,
                "expiry_display": format_market_expiry(expiry, market),
                "days": picks[0].contract.days,
                "items": list(merged.values()),
            }
        )
    return covered_groups


def _long_groups(groups, *, market: str, price_basis: str = "bid", interest_rate: float = 40) -> list[dict]:
    def premium(item):
        return (
            item.option_last if price_basis == "last"
            else item.option_ask if price_basis == "ask"
            else item.option_bid
        )

    long_groups = []
    for (asset, expiry), items in sorted(
        groups.items(),
        key=lambda item: _sort_key(market, *item[0]),
    ):
        if not items:
            continue
        long_groups.append(
            {
                "market": market,
                "asset": asset,
                "expiry": expiry,
                "expiry_display": format_market_expiry(expiry, market),
                "days": items[0].days,
                "items": [
                    {
                        "symbol": item.symbol,
                        "source_asset": item.source_asset,
                        "state": item.state,
                        "profit_percent": item.profit_percent,
                        "transaction_value": item.transaction_value,
                        "transaction_zero": item.transaction_value == 0,
                        "volume": item.volume,
                        "volume_is_proxy": item.volume_is_proxy,
                        "base_price": item.base_price,
                        "option_bid": item.option_bid,
                        "option_best_ask": item.option_ask,
                        "option_last": item.option_last,
                        "option_gap_percent": item.option_gap_percent,
                        "calculation_price": premium(item),
                        "price_basis": price_basis,
                        "strike": item.strike,
                        "breakeven": item.breakeven,
                        "itm_percent": item.itm_percent,
                        **_long_cost_fields(
                            base_price=item.base_price,
                            strike=item.strike,
                            premium=premium(item),
                            days=item.days,
                            interest_rate=interest_rate,
                        ),
                        **_greek_fields(
                            item.base_price,
                            item.strike,
                            item.days,
                            premium(item),
                            interest_rate,
                            covered=False,
                        ),
                    }
                    for item in items
                ],
            }
        )
    return long_groups


def _top_items(selections, market: str, price_basis: str = "bid", interest_rate: float = 40) -> list[dict]:
    liquidity_values = list({pick.contract.symbol: pick.contract.transaction_value for picks in selections.values() for pick in picks}.values())
    rows = []
    for item in top_unique_contracts(selections):
        calculation_price = item.option_last if price_basis == "last" else item.option_bid
        greeks = _greek_fields(item.base_price, item.strike, item.days, calculation_price, interest_rate)
        rows.append({
            "market": market,
            "asset": item.asset,
            "source_asset": item.source_asset,
            "symbol": item.symbol,
            "expiry": item.expiry,
            "expiry_display": format_market_expiry(item.expiry, market),
            "days": item.days,
            "state": item.state,
            "annual_return": _number(item.annual_return),
            "monthly_return": _monthly_return(_number(item.annual_return)),
            "expiry_return": _number(item.expiry_return),
            "transaction_value": item.transaction_value,
            "transaction_zero": item.transaction_value == 0,
            "base_price": _number(item.base_price),
            "option_bid": _number(item.option_bid),
            "option_last": _number(item.option_last),
            "option_gap_percent": _number(item.option_gap_percent),
            "calculation_price": _number(calculation_price),
            "price_basis": price_basis,
            "strike": _number(item.strike),
            "breakeven": _number(item.breakeven),
            "itm_percent": _number(item.itm_percent),
            **_buyback_fields(
                base_price=_number(item.base_price),
                premium=_number(calculation_price),
                days=item.days,
            ),
            **greeks,
            **_score_fields(item, calculation_price, greeks, liquidity_values),
        })
    return rows


def _top_long_items(
    groups, market: str, limit: int = 5, price_basis: str = "bid", interest_rate: float = 40
) -> list[dict]:
    def premium(item):
        return (
            item.option_last if price_basis == "last"
            else item.option_ask if price_basis == "ask"
            else item.option_bid
        )

    unique = {}
    for items in groups.values():
        for item in items:
            if item.transaction_value <= 0:
                continue
            current = unique.get(item.symbol)
            if current is None or item.profit_percent > current.profit_percent:
                unique[item.symbol] = item
    ranked = sorted(
        unique.values(),
        key=lambda item: (-item.profit_percent, -item.transaction_value, item.symbol),
    )[:limit]
    return [
        {
            "market": market,
            "asset": item.asset,
            "source_asset": item.source_asset,
            "symbol": item.symbol,
            "expiry": item.expiry,
            "expiry_display": format_market_expiry(item.expiry, market),
            "days": item.days,
            "state": item.state,
            "profit_percent": item.profit_percent,
            "transaction_value": item.transaction_value,
            "transaction_zero": item.transaction_value == 0,
            "base_price": item.base_price,
            "option_bid": item.option_bid,
            "option_best_ask": item.option_ask,
            "option_last": item.option_last,
            "option_gap_percent": item.option_gap_percent,
            "calculation_price": premium(item),
            "price_basis": price_basis,
            "strike": item.strike,
            "breakeven": item.breakeven,
            "itm_percent": item.itm_percent,
            **_long_cost_fields(
                base_price=item.base_price,
                strike=item.strike,
                premium=premium(item),
                days=item.days,
                interest_rate=interest_rate,
            ),
            **_greek_fields(
                item.base_price,
                item.strike,
                item.days,
                premium(item),
                interest_rate,
            ),
        }
        for item in ranked
    ]


def _option_strategy_table(
    rows: list[dict], *, market: str, strategy: str,
    top_symbols: set[str], interest_rate: float = 40,
    price_basis: str = "bid", base_basis: str = "ask",
) -> list[dict]:
    """Calculate the complete option universe for one market and strategy."""
    liquidity_values = [float(row.get("value") or 0) for row in rows]
    result = []
    for row in rows:
        symbol = str(row.get("symbolOption") or "").strip()
        resolver = canonical_tehran_asset if market == "tehran" else canonical_asset
        asset = resolver(str(row.get("baseSymbol") or ""), symbol)
        try:
            strike = float(row.get("dueDatePrice") or 0)
            days = int(float(row.get("days") or 0))
            premium = float(row.get("bidPrice1Option") or 0)
            transaction_value = float(row.get("value") or 0)
            volume = float(row.get("volume") or 0)
        except (TypeError, ValueError):
            continue
        base_best_ask = _number(
            row.get("bestAskBase") if "bestAskBase" in row else row.get("askPrice1Base")
        )
        base_best_bid = _number(
            row.get("bestBidBase") if "bestBidBase" in row else row.get("bidPrice1Base")
        )
        base_last = _number(
            row.get("lastTradeBase") or row.get("previousPriceBase")
            or row.get("closingPriceBase")
        )
        base_price = {
            "ask": base_best_ask,
            "bid": base_best_bid,
            "last": base_last,
        }.get(base_basis)
        if not symbol or not asset or base_price is None or base_price <= 0 or strike <= 0:
            continue
        option_last = _number(row.get("lastTradeOption"))
        option_close = _number(row.get("closingPriceOption"))
        option_best_ask = _number(row.get("askPrice1Option"))
        premium_value = {
            "bid": premium if premium > 0 else None,
            "ask": option_best_ask if option_best_ask and option_best_ask > 0 else None,
            "last": option_last or option_close,
        }.get(price_basis)
        expiry_return = annual_return = monthly_return = None
        if strategy == "covered_call" and premium_value is not None and days > 0:
            expiry_return = (premium_value - max(base_price - strike, 0.0)) / base_price * 100.0
            annual_return = expiry_return * 365.0 / days
            monthly_return = annual_return / 12.0
        greeks = _greek_fields(
            base_price, strike, days, premium_value or option_last,
            interest_rate, covered=strategy == "covered_call",
        )
        score = None
        score_label = None
        score_components = {}
        downside_protection = None
        if strategy == "covered_call" and premium_value is not None and annual_return is not None:
            scored = covered_call_score(
                annual_return=annual_return,
                premium=premium_value,
                base_price=base_price,
                option_delta=greeks["option_delta"],
                delta_estimated=greeks["delta_estimated"],
                transaction_value=transaction_value,
                liquidity_universe=liquidity_values,
                days=days,
                quote_gap_percent=option_quote_gap_percent(
                    premium if premium > 0 else None, option_last
                ),
            )
            score, score_label = scored["score"], scored["label"]
            score_components = scored["components"]
            downside_protection = scored["downside_protection_percent"]
        long_fields = _long_cost_fields(
            base_price=base_price,
            strike=strike,
            premium=premium_value,
            days=days,
            interest_rate=interest_rate,
        )
        itm_percent = (base_price - strike) / base_price * 100.0
        result.append({
            "asset": asset,
            "source_asset": str(row.get("baseSymbol") or asset),
            "market": market,
            "strategy": strategy,
            "base_price": base_price,
            "base_best_ask": base_best_ask,
            "base_best_bid": base_best_bid,
            "base_last": base_last,
            "base_close": _number(row.get("closingPriceBase")),
            "base_price_basis": base_basis,
            "base_queue_status": str(row.get("baseQueueStatus") or "نامشخص"),
            "option_queue_status": str(row.get("optionQueueStatus") or "نامشخص"),
            "quote_quality_valid": bool(row.get("quoteQualityValid", True)),
            "quote_quality_warnings": dict(row.get("quoteQualityWarnings") or {}),
            "base_price_min": _number(row.get("basePriceMin")),
            "base_price_max": _number(row.get("basePriceMax")),
            "option_price_min": _number(row.get("optionPriceMin")),
            "option_price_max": _number(row.get("optionPriceMax")),
            "symbol": symbol,
            "option_price": option_close or option_last,
            "option_best_ask": option_best_ask,
            "option_best_bid": premium if premium > 0 else None,
            "option_bid": premium if premium > 0 else None,
            "option_last": option_last,
            "option_gap_percent": (
                option_quote_gap_percent(premium if premium > 0 else None, option_last)
                if strategy == "covered_call"
                else option_ask_gap_percent(option_best_ask, option_last)
            ),
            "calculation_price": premium_value,
            "price_basis": price_basis,
            "option_volume": volume,
            "transaction_value": transaction_value,
            "transaction_zero": transaction_value <= 0,
            "strike": strike,
            "breakeven": (
                round(base_price - premium_value, 2)
                if strategy == "covered_call" and premium_value is not None
                else round(strike + premium_value, 2) if premium_value is not None else None
            ),
            "state": "ITM" if base_price > strike else "OTM" if base_price < strike else "ATM",
            "itm_percent": round(itm_percent, 2),
            "days": days,
            "expiry": str(row.get("expiration_date") or ""),
            "expiry_display": format_market_expiry(str(row.get("expiration_date") or ""), market),
            "expiry_return": None if expiry_return is None else round(expiry_return, 2),
            "annual_return": None if annual_return is None else round(annual_return, 2),
            "monthly_return": None if monthly_return is None else round(monthly_return, 2),
            "premium_to_base_percent": (
                None if premium_value is None
                else round(premium_value / base_price * 100.0, 2)
            ),
            "leverage": (
                None if premium_value is None or premium_value <= 0
                else round(base_price / premium_value, 2)
            ),
            **_buyback_fields(
                base_price=base_price,
                premium=premium_value if strategy == "covered_call" else None,
                days=days,
            ),
            "covered_score": score,
            "covered_score_label": score_label,
            "covered_score_components": score_components,
            "downside_protection_percent": downside_protection,
            "is_top_five": symbol in top_symbols,
            "recommendation": (
                "خرید اختیار" if (long_fields.get("advantage_percent") or 0) > 0
                else "خرید دارایی پایه"
            ),
            **long_fields,
            **greeks,
        })
    return sorted(
        result,
        key=lambda item: (
            -(
                item["covered_score"] if strategy == "covered_call" and item["covered_score"] is not None
                else item["advantage_percent"] if strategy != "covered_call" and item["advantage_percent"] is not None
                else -10_000
            ),
            item["symbol"],
        ),
    )


def build_dashboard_payload(scan: ScanResult, settings: Settings) -> dict:
    rate = settings.long_underlying_interest_rate
    covered_groups = _covered_groups(scan.covered_call, market="goods", interest_rate=rate)
    covered_groups += _covered_groups(scan.tehran_covered_call, market="tehran", interest_rate=rate)
    long_groups = _long_groups(scan.long_underlying, market="goods", interest_rate=rate)
    long_groups += _long_groups(scan.tehran_long_underlying, market="tehran", interest_rate=rate)
    covered_last_groups = _covered_groups(
        scan.covered_call_last, market="goods", price_basis="last", interest_rate=rate
    )
    covered_last_groups += _covered_groups(
        scan.tehran_covered_call_last, market="tehran", price_basis="last", interest_rate=rate
    )
    long_last_groups = _long_groups(
        scan.long_underlying_last, market="goods", price_basis="last", interest_rate=rate
    )
    long_last_groups += _long_groups(
        scan.tehran_long_underlying_last, market="tehran", price_basis="last", interest_rate=rate
    )
    long_ask_groups = _long_groups(
        scan.long_underlying_ask, market="goods", price_basis="ask", interest_rate=rate
    )
    long_ask_groups += _long_groups(
        scan.tehran_long_underlying_ask, market="tehran", price_basis="ask", interest_rate=rate
    )
    def ranked_symbols(groups, market, metric):
        ranked = sorted(
            (
                item for group in groups if group["market"] == market
                for item in group["items"] if not item["transaction_zero"]
            ),
            key=lambda item: (
                -float(item.get(metric) or 0),
                -float(item.get("transaction_value") or 0),
            ),
        )[:5]
        return {item["symbol"] for item in ranked}

    strategy_tables = {"covered_call": {}, "long_underlying": {}}
    all_price_bases = ("bid", "ask", "last")
    strategy_table_variants = {
        strategy: {
            option_basis: {base_basis: {} for base_basis in all_price_bases}
            for option_basis in all_price_bases
        }
        for strategy in ("covered_call", "long_underlying")
    }
    covered_overview_candidates = {"bid": {}, "last": {}}
    for market, rows in (
        ("tehran", scan.tehran_trade_rows), ("goods", scan.goods_trade_rows)
    ):
        for option_basis in all_price_bases:
            for base_basis in all_price_bases:
                table = _option_strategy_table(
                    rows, market=market, strategy="covered_call",
                    top_symbols=set(), interest_rate=rate,
                    price_basis=option_basis, base_basis=base_basis,
                )
                top = {
                    item["symbol"] for item in sorted(
                        (item for item in table if item["transaction_value"] > 0),
                        key=lambda item: (
                            -float(item.get("covered_score") or -1),
                            -float(item.get("annual_return") or -10_000),
                            -float(item.get("transaction_value") or 0),
                        ),
                    )[:5]
                }
                for item in table:
                    item["is_top_five"] = item["symbol"] in top
                strategy_table_variants["covered_call"][option_basis][base_basis][market] = table
        strategy_tables["covered_call"][market] = strategy_table_variants["covered_call"]["bid"]["ask"][market]
        covered_overview_candidates["bid"][market] = strategy_tables["covered_call"][market]
        covered_overview_candidates["last"][market] = strategy_table_variants["covered_call"]["last"]["ask"][market]
        for option_basis in all_price_bases:
            for base_basis in all_price_bases:
                table = _option_strategy_table(
                    rows, market=market, strategy="long_underlying",
                    top_symbols=set(), interest_rate=rate,
                    price_basis=option_basis, base_basis=base_basis,
                )
                top = {
                    item["symbol"] for item in sorted(
                        (
                            item for item in table
                            if item["transaction_value"] > 0
                            and (item.get("advantage_percent") or 0) > 0
                        ),
                        key=lambda item: (
                            -float(item.get("advantage_percent") or -10_000),
                            -float(item.get("transaction_value") or 0),
                        ),
                    )[:5]
                }
                for item in table:
                    item["is_top_five"] = item["symbol"] in top
                strategy_table_variants["long_underlying"][option_basis][base_basis][market] = table
        strategy_tables["long_underlying"][market] = strategy_table_variants["long_underlying"]["last"]["ask"][market]

    covered_items = [item for group in covered_groups for item in group["items"]]
    long_items = [item for group in long_groups for item in group["items"]]
    active_assets = sorted(
        {group["asset"] for group in covered_groups + long_groups},
        key=lambda asset: (ASSET_ORDER.get(asset, 999), asset),
    )
    market_summary = {}
    for market in ("goods", "tehran"):
        market_covered = [item for group in covered_groups if group["market"] == market for item in group["items"]]
        market_long = [item for group in long_groups if group["market"] == market for item in group["items"]]
        market_summary[market] = {
            "covered_contracts": len(market_covered),
            "positive_contracts": len(market_long),
        }
    return {
        "generated_at": scan.generated_at.isoformat(),
        "source": {
            "name": "TSETMC و بورس کالای ایران",
            "urls": {
                "goods": "https://cdn.ime.co.ir/",
                "tehran": "https://www.tsetmc.com/OptionMarketWatch/0",
            },
            "grain": "هر قرارداد اختیار × سررسید",
        },
        "rules": {
            "covered_min_annual_return": settings.covered_call_min_annual_return,
            "warning_return": settings.covered_call_warning_return,
            "long_interest_rate": settings.long_underlying_interest_rate,
            "refresh_minutes": settings.interval_minutes,
            "tehran_daily_limit_percent": settings.tehran_daily_limit_percent,
            "leveraged_daily_limit_percent": settings.leveraged_daily_limit_percent,
            "goods_daily_limit_percent": settings.goods_daily_limit_percent,
            "goods_data_policy": (
                "زنجیره اختیار، سفارش‌ها، معاملات و قیمت دارایی‌های پایه بورس کالا "
                "مستقیماً از تابلوی رسمی بورس کالای ایران دریافت می‌شوند."
            ),
        },
        "summary": {
            "covered_contracts": len(covered_items),
            "positive_contracts": len(long_items),
            "active_assets": len(active_assets),
            "zero_value_contracts": sum(
                1 for item in covered_items + long_items if item["transaction_zero"]
            ),
            "by_market": market_summary,
        },
        "markets": [
            {"id": "goods", "label": "بورس کالا"},
            {"id": "tehran", "label": "بورس تهران"},
        ],
        "assets": active_assets,
        "tehran_covered_call_table": strategy_tables["covered_call"]["tehran"],
        "strategy_tables": strategy_tables,
        "strategy_table_variants": strategy_table_variants,
        "covered_overview_candidates": covered_overview_candidates,
        "covered_call": covered_groups,
        "long_underlying": long_groups,
        "top_opportunities": {
            "covered_call": {
                "goods": _top_items(scan.covered_call, "goods", interest_rate=rate),
                "tehran": _top_items(scan.tehran_covered_call, "tehran", interest_rate=rate),
            },
            "long_underlying": {
                "goods": _top_long_items(scan.long_underlying, "goods", interest_rate=rate),
                "tehran": _top_long_items(scan.tehran_long_underlying, "tehran", interest_rate=rate),
            },
        },
        "price_variants": {
            "covered_call": {
                "bid": {
                    "groups": covered_groups,
                    "top": {
                        "goods": _top_items(scan.covered_call, "goods", interest_rate=rate),
                        "tehran": _top_items(scan.tehran_covered_call, "tehran", interest_rate=rate),
                    },
                },
                "last": {
                    "groups": covered_last_groups,
                    "top": {
                        "goods": _top_items(scan.covered_call_last, "goods", "last", rate),
                        "tehran": _top_items(
                            scan.tehran_covered_call_last, "tehran", "last", rate
                        ),
                    },
                },
            },
            "long_underlying": {
                "bid": {
                    "groups": long_groups,
                    "top": {
                        "goods": _top_long_items(scan.long_underlying, "goods", interest_rate=rate),
                        "tehran": _top_long_items(
                            scan.tehran_long_underlying, "tehran", interest_rate=rate
                        ),
                    },
                },
                "last": {
                    "groups": long_last_groups,
                    "top": {
                        "goods": _top_long_items(
                            scan.long_underlying_last, "goods", price_basis="last", interest_rate=rate
                        ),
                        "tehran": _top_long_items(
                            scan.tehran_long_underlying_last,
                            "tehran",
                            price_basis="last",
                            interest_rate=rate,
                        ),
                    },
                },
                "ask": {
                    "groups": long_ask_groups,
                    "top": {
                        "goods": _top_long_items(
                            scan.long_underlying_ask, "goods", price_basis="ask", interest_rate=rate
                        ),
                        "tehran": _top_long_items(
                            scan.tehran_long_underlying_ask,
                            "tehran",
                            price_basis="ask",
                            interest_rate=rate,
                        ),
                    },
                },
            },
        },
    }


class DashboardCache:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._payload: dict | None = None
        self._trade_quotes: dict[str, dict] = {}
        self._loaded_at = 0.0
        self._order_flow_lock = threading.Lock()
        self._order_flow_cache: dict[str, tuple[float, dict]] = {}
        self._order_flow_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=120))
        self._order_flow_candles: dict[str, OrderedDict] = defaultdict(OrderedDict)

    def get(self, *, force: bool = False) -> dict:
        max_age = max(60, self.settings.interval_minutes * 60)
        with self._lock:
            if force or self._payload is None or time.monotonic() - self._loaded_at >= max_age:
                scan = collect_scan(self.settings)
                self._payload = build_dashboard_payload(scan, self.settings)
                self._trade_quotes = build_quote_map(
                    scan.goods_trade_rows, scan.tehran_trade_rows
                )
                self._loaded_at = time.monotonic()
            return self._payload

    def trade_quotes(self) -> dict[str, dict]:
        self.get()
        with self._lock:
            return {key: dict(value) for key, value in self._trade_quotes.items()}

    def order_flow_catalog(self) -> dict:
        instruments: list[dict] = []
        bases: set[tuple[str, str, str]] = set()
        for quote in self.trade_quotes().values():
            market = quote["market"]
            instruments.append({
                "market": market, "instrument_type": "option",
                "symbol": quote["symbol"], "asset": quote["asset"],
                "ins_code": quote.get("ins_code_option") or "",
            })
            base_key = (market, quote["asset"], quote.get("ins_code_base") or "")
            if base_key not in bases:
                bases.add(base_key)
                instruments.append({
                    "market": market, "instrument_type": "base",
                    "symbol": quote["asset"], "asset": quote["asset"],
                    "ins_code": quote.get("ins_code_base") or "",
                })
        instruments.sort(key=lambda item: (
            item["market"], item["instrument_type"], item["asset"], item["symbol"]
        ))
        return {"instruments": instruments}

    def order_flow(self, *, market: str, instrument_type: str, symbol: str, force=False) -> dict:
        catalog = self.order_flow_catalog()["instruments"]
        item = next((entry for entry in catalog if entry["market"] == market
                     and entry["instrument_type"] == instrument_type
                     and entry["symbol"] == symbol), None)
        if not item:
            raise KeyError("نماد انتخاب‌شده در فهرست جاری بازار پیدا نشد")
        key = f"{market}:{instrument_type}:{symbol}"
        with self._order_flow_lock:
            cached = self._order_flow_cache.get(key)
            if not force and cached and time.monotonic() - cached[0] < 10:
                return cached[1]

        client = BamboClient(self.settings)
        if market == "tehran":
            ins_code = item.get("ins_code")
            if not ins_code:
                raise RuntimeError("شناسه TSETMC برای این نماد موجود نیست")
            book = client.fetch_tsetmc_order_book(ins_code)
            candles = client.fetch_tsetmc_intraday_candles(ins_code)
            candle_source = "کندل‌های ۱۵ دقیقه‌ای ساخته‌شده از مشاهدات درون‌روزی رسمی TSETMC"
        else:
            book = client.fetch_ime_order_book(
                symbol=symbol, asset=item["asset"], instrument_type=instrument_type
            )
            candles = []
            candle_source = "کندل زنده ۱۵ دقیقه‌ای از نمونه‌های ثبت‌شده در همین اجرای برنامه"
        levels = book["levels"]
        total_bid = sum(float(row.get("bid_volume") or 0) for row in levels)
        total_ask = sum(float(row.get("ask_volume") or 0) for row in levels)
        total = total_bid + total_ask
        imbalance = ((total_bid - total_ask) / total * 100) if total else 0.0
        best_bid = next((row.get("bid_price") for row in levels if row.get("bid_price")), None)
        best_ask = next((row.get("ask_price") for row in levels if row.get("ask_price")), None)
        spread = best_ask - best_bid if best_bid and best_ask else None
        midpoint = (best_ask + best_bid) / 2 if best_bid and best_ask else None
        spread_percent = spread / midpoint * 100 if spread is not None and midpoint else None
        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        point = {
            "timestamp": generated_at, "imbalance_percent": round(imbalance, 2),
            "bid_volume": total_bid, "ask_volume": total_ask,
            "spread_percent": None if spread_percent is None else round(spread_percent, 4),
        }
        with self._order_flow_lock:
            if market == "goods" and book.get("last_price"):
                now = datetime.fromisoformat(generated_at)
                bucket = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
                bucket_key = bucket.isoformat(timespec="minutes")
                price = float(book["last_price"])
                candle_map = self._order_flow_candles[key]
                candle = candle_map.get(bucket_key)
                if candle:
                    candle["high"] = max(candle["high"], price)
                    candle["low"] = min(candle["low"], price)
                    candle["close"] = price
                else:
                    candle_map[bucket_key] = {
                        "timestamp": bucket.isoformat(timespec="seconds"),
                        "open": price, "high": price, "low": price, "close": price,
                    }
                while len(candle_map) > 32:
                    candle_map.popitem(last=False)
                candles = list(candle_map.values())
            history = self._order_flow_history[key]
            if not history or history[-1]["timestamp"] != generated_at:
                history.append(point)
            payload = {
                **item, **book, "generated_at": generated_at,
                "best_bid": best_bid, "best_ask": best_ask,
                "spread": spread, "spread_percent": spread_percent,
                "total_bid_volume": total_bid, "total_ask_volume": total_ask,
                "imbalance_percent": imbalance, "history": list(history),
                "candles": candles, "candle_source": candle_source,
                "note": "عمق تجمیعی عمومی منبع رسمی؛ تعداد سفارش‌های منفرد و سمت آغازگر معامله منتشر نمی‌شود.",
            }
            self._order_flow_cache[key] = (time.monotonic(), payload)
            return payload


def _handler_factory(cache: DashboardCache):
    history_client = PriceHistoryClient(cache.settings)
    forecast_cache = ForecastCache(cache.settings)
    commodity_fx_cache = CommodityFxCache(cache.settings)
    trade_store = TradeStore(cache.settings.trades_file)
    underlying_store = UnderlyingPositionStore(
        cache.settings.trades_file.with_name("underlying_positions.json")
    )
    account_store = AccountStore(cache.settings.trades_file.with_name("account.json"))

    def trade_payload(
        *,
        covered_option_basis="last",
        covered_base_basis="last",
        long_option_basis="last",
        long_base_basis="last",
    ) -> dict:
        basis_label = {
            "bid": "بهترین پیشنهاد خرید",
            "ask": "بهترین پیشنهاد فروش",
            "last": "آخرین معامله",
        }
        dashboard = cache.get()
        as_of = datetime.fromisoformat(dashboard["generated_at"]).date()
        quotes = cache.trade_quotes()
        contracts = []
        for quote in sorted(
            quotes.values(),
            key=lambda item: (item["market"], item["asset"], item["expiry"], item["symbol"]),
        ):
            expiry = datetime.strptime(quote["expiry"], "%Y-%m-%d").date()
            contracts.append({
                **quote,
                "expiry_display": format_jalali_date(expiry),
                "exit_quote_available": quote.get("option_exit_ask") is not None,
                "long_exit_quote_available": quote.get("option_exit_bid") is not None,
                "long_last_available": quote.get("option_last") is not None,
                "base_last_available": quote.get("base_last") is not None,
            })
        raw_trades = trade_store.list()
        trades = [
            calculate_trade_snapshot(
                item,
                select_trade_valuation_quote(
                    quotes.get(quote_key(item.get("market"), item.get("option_symbol"))),
                    str(item.get("strategy_type") or "covered_call"),
                    covered_option_basis=covered_option_basis,
                    covered_base_basis=covered_base_basis,
                    long_option_basis=long_option_basis,
                    long_base_basis=long_base_basis,
                ),
                as_of=as_of,
            )
            for item in raw_trades
        ]
        base_quotes = build_underlying_quote_map(quotes)
        allocations = underlying_allocations(raw_trades)
        underlyings = [
            calculate_underlying_snapshot(
                item,
                base_quotes.get(underlying_quote_key(item.get("market"),item.get("asset"))),
                as_of=as_of,
                allocated_quantity=allocations.get(str(item.get("id")),0),
            ) for item in underlying_store.list()
        ]
        account = account_store.read()
        account_growth = build_account_growth(
            trades,
            as_of=as_of,
            initial_capital=account.get("initial_capital"),
            underlying_positions=underlyings,
        )
        return {
            "calculation_schema_version": 7,
            "financial_capabilities": financial_capabilities(),
            "generated_at": dashboard["generated_at"],
            "price_policy": {
                "covered_call_valuation": (
                    f"{basis_label[covered_option_basis]} اختیار و "
                    f"{basis_label[covered_base_basis]} دارایی پایه"
                ),
                "long_call_valuation": (
                    f"{basis_label[long_option_basis]} اختیار و "
                    f"{basis_label[long_base_basis]} دارایی پایه"
                ),
                "trade_close_default": "آخرین معامله اختیار و دارایی پایه؛ با تأیید کاربر",
                "long_call_exit": "آخرین معامله اختیار؛ با تأیید کاربر",
                "base_current": "آخرین معامله دارایی پایه در منبع بازار",
            },
            "contracts": contracts,
            "underlying_quotes": list(base_quotes.values()),
            "underlying_positions": underlyings,
            "underlying_summary": summarize_underlying_positions(underlyings),
            "closed_underlying_summary": summarize_underlying_positions(underlyings,closed=True),
            "trades": trades,
            "summary": summarize_open_trades(trades, underlyings),
            "closed_summary": summarize_closed_trades(trades, underlyings),
            "account": account,
            "asset_ledger": build_portfolio_asset_ledger(
                trades,
                underlyings,
                cash_balance=account.get("cash_balance"),
            ),
            "account_growth": account_growth,
            "profit_recognition": build_covered_profit_recognition(
                trades,
                as_of=as_of,
                initial_capital=account_growth.get("initial_capital"),
            ),
        }

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "BamboDashboard/1.0"

        def log_message(self, format, *args):
            LOGGER.info("%s - %s", self.address_string(), format % args)

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()

        def _send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
            self._headers(status, content_type, len(data))
            self.wfile.write(data)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send_bytes(data, "application/json; charset=utf-8", status)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 65536:
                raise ValueError("حجم درخواست معتبر نیست")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("ساختار درخواست معتبر نیست")
            return payload

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                if path == "/api/account":
                    payload = self._read_json()
                    account_store.save(payload.get("initial_capital"))
                    self._send_json(trade_payload())
                    return
                if path == "/api/trades":
                    payload = self._read_json()
                    payload.update({
                        "quantity_kind": "contract",
                        "currency_unit": "rial",
                        "calculation_version": 8,
                    })
                    quotes = cache.trade_quotes()
                    key = quote_key(payload.get("market"), payload.get("option_symbol"))
                    quote = resolve_trade_quote(payload, quotes.get(key))
                    payload["option_symbol"] = quote.get("symbol") or payload.get("option_symbol")
                    validate_underlying_link(payload,underlying_store.list(),trade_store.list(),quote)
                    trade_store.create(payload, quote)
                    self._send_json(trade_payload(), HTTPStatus.CREATED)
                    return
                if path == "/api/underlyings":
                    payload = prepare_underlying_payload(self._read_json(), trade_store.list())
                    underlying_store.create(payload)
                    self._send_json(trade_payload(),HTTPStatus.CREATED)
                    return
                underlying_close = re.fullmatch(
                    r"/api/underlyings/([a-f0-9]+)/close", path
                )
                if underlying_close:
                    payload = self._read_json()
                    position = next(
                        (item for item in underlying_store.list()
                         if item.get("id") == underlying_close.group(1)), None,
                    )
                    if not position:
                        raise KeyError("دارایی پایه پیدا نشد")
                    allocated = underlying_allocations(trade_store.list()).get(
                        underlying_close.group(1), 0.0
                    )
                    available = float(position.get("quantity") or 0) - allocated
                    quantity = float(payload.get("quantity") or 0)
                    if quantity > available + 1e-9:
                        raise ValueError("فقط موجودی آزاد دارایی پایه قابل فروش است")
                    underlying_store.sell_quantity(
                        underlying_close.group(1), quantity,
                        exit_date=parse_user_date(str(payload.get("exit_date") or "")),
                        exit_price=payload.get("exit_price"),
                        exit_commission=payload.get("exit_commission"),
                        exit_commission_source=payload.get("exit_commission_source"),
                    )
                    self._send_json(trade_payload())
                    return
                match = re.fullmatch(r"/api/trades/([a-f0-9]+)/close", path)
                if match:
                    payload = self._read_json()
                    current = next(
                        (item for item in trade_store.list() if item.get("id") == match.group(1)),
                        None,
                    )
                    if not current:
                        raise KeyError("معامله پیدا نشد")
                    dashboard = cache.get()
                    as_of = datetime.fromisoformat(dashboard["generated_at"]).date()
                    quote = cache.trade_quotes().get(
                        quote_key(current.get("market"), current.get("option_symbol"))
                    )
                    exit_date = parse_user_date(
                        str(payload.get("exit_date") or format_jalali_date(as_of))
                    )
                    confirmation = payload.get("price_confirmed")
                    was_closed = current.get("status") == "closed"
                    closed_trade = trade_store.close(
                        match.group(1),
                        quote,
                        exit_date=exit_date,
                        exit_method=payload.get("exit_method", current.get("exit_method", "offset")),
                        exit_base_price=payload.get("exit_base_price"),
                        exit_option_price=payload.get("exit_option_price"),
                        exit_commission=payload.get("exit_commission"),
                        exit_commission_source=payload.get("exit_commission_source"),
                        exit_note=payload.get("exit_note", ""),
                        price_confirmed=(
                            confirmation is True
                            or str(confirmation).strip().lower() in {"1", "true", "on"}
                        ),
                        close_quantity=payload.get("close_quantity"),
                        close_exercise_quantity=payload.get("close_exercise_quantity"),
                        close_premium_trade_quantity=payload.get("close_premium_trade_quantity"),
                        underlying_disposition=payload.get("underlying_disposition","sell"),
                        underlying_keep_basis=payload.get("underlying_keep_basis", "entry"),
                    )
                    if not was_closed:
                        if closed_trade.get("strategy_type") == "long_call" and closed_trade.get("exit_method") in {"exercise","mixed"}:
                            underlying_store.create_from_exercise(closed_trade)
                        elif closed_trade.get("strategy_type") == "covered_call" and closed_trade.get("underlying_position_id") and closed_trade.get("underlying_disposition") == "sell":
                            units=trade_underlying_units(closed_trade)
                            sale_price=float(closed_trade.get("strike") if closed_trade.get("exit_method")=="exercise" else closed_trade.get("exit_base_price"))
                            underlying_store.sell_quantity(
                                closed_trade["underlying_position_id"], units,
                                exit_date=exit_date, exit_price=sale_price,
                                source_trade_id=closed_trade.get("id"),
                                exclude_from_portfolio=True,
                            )
                        elif closed_trade.get("strategy_type") == "covered_call" and closed_trade.get("underlying_disposition") == "keep":
                            units=trade_underlying_units(closed_trade)
                            if not closed_trade.get("underlying_position_id"):
                                basis_price=(closed_trade.get("entry_base_price") if closed_trade.get("underlying_keep_basis")=="entry" else closed_trade.get("exit_base_price"))
                                underlying_store.create({
                                    "market":closed_trade.get("market"),"asset":closed_trade.get("asset"),
                                    "acquisition_method":"direct","entry_date":closed_trade.get("entry_date"),
                                    "entry_price":basis_price,"quantity":units,"commission":0,
                                    "commission_source":"actual","source_trade_id":closed_trade.get("id"),
                                    "currency_unit":closed_trade.get("currency_unit"),
                                    "calculation_version":closed_trade.get("calculation_version"),
                                })
                                self._send_json(trade_payload())
                                return
                            linked_position=next((position for position in underlying_store.list() if position.get("id")==closed_trade["underlying_position_id"]),None)
                            other_allocated= max(0.0, float((linked_position or {}).get("allocated_quantity") or 0) - units)
                            basis_price=(closed_trade.get("entry_base_price") if closed_trade.get("underlying_keep_basis")=="entry" else closed_trade.get("exit_base_price"))
                            underlying_store.rebase_released_quantity(
                                closed_trade["underlying_position_id"], units,
                                release_date=exit_date, release_price=float(basis_price),
                                other_allocated_quantity=other_allocated,
                                source_trade_id=closed_trade.get("id"),
                            )
                    self._send_json(trade_payload())
                    return
                if path != "/api/covered-score":
                    self._send_json({"error": "یافت نشد"}, HTTPStatus.NOT_FOUND)
                    return
                payload = self._read_json()
                market = str(payload.get("market") or "tehran")
                if market not in {"tehran", "goods"}:
                    raise ValueError("بازار معتبر نیست")
                dashboard = cache.get()
                values = [
                    item["transaction_value"]
                    for group in dashboard["covered_call"] if group["market"] == market
                    for item in group["items"]
                ]
                result = calculate_custom_covered_call(
                    payload, values, cache.settings.long_underlying_interest_rate
                )
                self._send_json(result)
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except KeyError as exc:
                self._send_json({"error": str(exc).strip("'")}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                LOGGER.exception("POST request failed")
                self._send_json({"error": "انجام عملیات ناموفق بود", "detail": str(exc)[:200]}, HTTPStatus.BAD_GATEWAY)

        def do_PUT(self):
            path = urlparse(self.path).path
            underlying_match = re.fullmatch(r"/api/underlyings/([a-f0-9]+)",path)
            if underlying_match:
                try:
                    payload = prepare_underlying_payload(self._read_json(), trade_store.list())
                    validate_underlying_position_change(
                        underlying_match.group(1), payload,
                        underlying_store.list(), trade_store.list(),
                    )
                    underlying_store.update(underlying_match.group(1),payload)
                    self._send_json(trade_payload())
                except ValueError as exc: self._send_json({"error":str(exc)},HTTPStatus.BAD_REQUEST)
                except KeyError as exc: self._send_json({"error":str(exc).strip("'")},HTTPStatus.NOT_FOUND)
                return
            match = re.fullmatch(r"/api/trades/([a-f0-9]+)", path)
            if not match:
                self._send_json({"error": "یافت نشد"}, HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json()
                existing = next(
                    (item for item in trade_store.list()
                     if item.get("id") == match.group(1)), None,
                )
                if existing is None:
                    raise KeyError("معامله پیدا نشد")
                for key in ("quantity_kind", "currency_unit", "calculation_version"):
                    if key in existing:
                        payload[key] = existing[key]
                live_quote = cache.trade_quotes().get(
                    quote_key(payload.get("market"), payload.get("option_symbol"))
                )
                quote = resolve_trade_quote(payload, live_quote)
                payload["option_symbol"] = quote.get("symbol") or payload.get("option_symbol")
                validate_underlying_link(payload,underlying_store.list(),trade_store.list(),quote,editing_trade_id=match.group(1))
                trade_store.update(match.group(1), payload, quote)
                self._send_json(trade_payload())
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except KeyError as exc:
                self._send_json({"error": str(exc).strip("'")}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                LOGGER.exception("Trade update failed")
                self._send_json({"error": "ویرایش معامله ناموفق بود", "detail": str(exc)[:200]}, HTTPStatus.BAD_GATEWAY)

        def do_DELETE(self):
            path = urlparse(self.path).path
            underlying_match = re.fullmatch(r"/api/underlyings/([a-f0-9]+)",path)
            if underlying_match:
                try:
                    validate_underlying_position_change(
                        underlying_match.group(1), None,
                        underlying_store.list(), trade_store.list(), deleting=True,
                    )
                    underlying_store.delete(underlying_match.group(1)); self._send_json(trade_payload())
                except ValueError as exc: self._send_json({"error":str(exc)},HTTPStatus.BAD_REQUEST)
                except KeyError as exc: self._send_json({"error":str(exc).strip("'")},HTTPStatus.NOT_FOUND)
                return
            match = re.fullmatch(r"/api/trades/([a-f0-9]+)", path)
            if not match:
                self._send_json({"error": "یافت نشد"}, HTTPStatus.NOT_FOUND)
                return
            try:
                trade_store.delete(match.group(1))
                self._send_json(trade_payload())
            except KeyError as exc:
                self._send_json({"error": str(exc).strip("'")}, HTTPStatus.NOT_FOUND)
            except Exception as exc:
                LOGGER.exception("Trade delete failed")
                self._send_json({"error": "حذف معامله ناموفق بود", "detail": str(exc)[:200]}, HTTPStatus.BAD_GATEWAY)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/order-book/catalog":
                try:
                    self._send_json(cache.order_flow_catalog())
                except Exception as exc:
                    LOGGER.exception("Order-flow catalog failed")
                    self._send_json({"error": "دریافت فهرست نمادها ناموفق بود", "detail": str(exc)[:200]}, HTTPStatus.BAD_GATEWAY)
                return
            if parsed.path == "/api/order-book":
                query = parse_qs(parsed.query)
                market = (query.get("market") or ["tehran"])[0]
                instrument_type = (query.get("instrument_type") or ["option"])[0]
                symbol = (query.get("symbol") or [""])[0].strip()
                if market not in {"tehran", "goods"} or instrument_type not in {"option", "base"} or not symbol:
                    self._send_json({"error": "بازار، نوع نماد یا نام نماد معتبر نیست"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    self._send_json(cache.order_flow(
                        market=market, instrument_type=instrument_type, symbol=symbol,
                        force=(query.get("refresh") == ["1"]),
                    ))
                except KeyError as exc:
                    self._send_json({"error": str(exc).strip("'")}, HTTPStatus.NOT_FOUND)
                except Exception as exc:
                    LOGGER.exception("Order-flow refresh failed")
                    self._send_json({"error": "دریافت عمق سفارش‌ها ناموفق بود", "detail": str(exc)[:200]}, HTTPStatus.BAD_GATEWAY)
                return
            if parsed.path == "/api/commodity-fx":
                try:
                    force = parse_qs(parsed.query).get("refresh") == ["1"]
                    self._send_json(commodity_fx_cache.get(force=force))
                except Exception as exc:
                    LOGGER.exception("Commodity implied FX refresh failed")
                    self._send_json(
                        {"error": "دریافت دلار ضمنی بورس کالا ناموفق بود", "detail": str(exc)[:200]},
                        HTTPStatus.BAD_GATEWAY,
                    )
                return
            if parsed.path == "/api/forecast":
                try:
                    force = parse_qs(parsed.query).get("refresh") == ["1"]
                    self._send_json(forecast_cache.get(force=force))
                except Exception as exc:
                    LOGGER.exception("Forecast refresh failed")
                    self._send_json(
                        {"error": "دریافت پیش‌بینی ناموفق بود", "detail": str(exc)[:200]},
                        HTTPStatus.BAD_GATEWAY,
                    )
                return
            if parsed.path == "/api/trades":
                try:
                    query = parse_qs(parsed.query)
                    covered_option_basis = (query.get("covered_option_basis") or ["last"])[0]
                    covered_base_basis = (query.get("covered_base_basis") or ["last"])[0]
                    long_option_basis = (query.get("long_option_basis") or ["last"])[0]
                    long_base_basis = (query.get("long_base_basis") or ["last"])[0]
                    if covered_option_basis not in {"last", "bid", "ask"}:
                        covered_option_basis = "last"
                    if covered_base_basis not in {"last", "bid", "ask"}:
                        covered_base_basis = "last"
                    if long_option_basis not in {"last", "bid", "ask"}:
                        long_option_basis = "last"
                    if long_base_basis not in {"last", "bid", "ask"}:
                        long_base_basis = "last"
                    self._send_json(trade_payload(
                        covered_option_basis=covered_option_basis,
                        covered_base_basis=covered_base_basis,
                        long_option_basis=long_option_basis,
                        long_base_basis=long_base_basis,
                    ))
                except Exception as exc:
                    LOGGER.exception("Trade tracking failed")
                    self._send_json(
                        {"error": "دریافت معاملات ناموفق بود", "detail": str(exc)[:200]},
                        HTTPStatus.BAD_GATEWAY,
                    )
                return
            if parsed.path == "/api/data":
                try:
                    force = parse_qs(parsed.query).get("refresh") == ["1"]
                    self._send_json(cache.get(force=force))
                except Exception as exc:
                    LOGGER.exception("Dashboard refresh failed")
                    self._send_json(
                        {"error": "دریافت اطلاعات بازار ناموفق بود", "detail": str(exc)[:200]},
                        HTTPStatus.BAD_GATEWAY,
                    )
                return
            if parsed.path == "/health":
                self._send_json({"ok": True})
                return
            if parsed.path == "/api/history":
                query = parse_qs(parsed.query)
                asset = (query.get("asset") or [""])[0].strip()
                source_asset = (query.get("source_asset") or [""])[0].strip()
                if not asset:
                    self._send_json({"error": "نام دارایی مشخص نشده است"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    self._send_json(history_client.fetch(asset, source_asset))
                except Exception as exc:
                    LOGGER.exception("Price history fetch failed")
                    self._send_json(
                        {"error": "دریافت تاریخچه قیمت ناموفق بود", "detail": str(exc)[:200]},
                        HTTPStatus.BAD_GATEWAY,
                    )
                return
            static_files = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/index.html": ("index.html", "text/html; charset=utf-8"),
                "/market": ("index.html", "text/html; charset=utf-8"),
                "/tehran-options": ("index.html", "text/html; charset=utf-8"),
                "/commodity-exchange": ("index.html", "text/html; charset=utf-8"),
                "/order-flow": ("index.html", "text/html; charset=utf-8"),
                "/trades": ("index.html", "text/html; charset=utf-8"),
                "/profit-recognition": ("index.html", "text/html; charset=utf-8"),
                "/closed-trades": ("index.html", "text/html; charset=utf-8"),
                "/calculator": ("index.html", "text/html; charset=utf-8"),
                "/settings": ("index.html", "text/html; charset=utf-8"),
                "/forecast": ("index.html", "text/html; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/financial-csv.js": (
                    "financial-csv.js",
                    "text/javascript; charset=utf-8",
                ),
                "/fonts/Vazirmatn.woff2": ("fonts/Vazirmatn.woff2", "font/woff2"),
                "/assets/tse-logo.jpeg": ("assets/tse-logo.jpeg", "image/jpeg"),
                "/assets/ime-logo.webp": ("assets/ime-logo.webp", "image/webp"),
            }
            target = static_files.get(parsed.path)
            if not target:
                self._send_json({"error": "یافت نشد"}, HTTPStatus.NOT_FOUND)
                return
            filename, content_type = target
            try:
                self._send_bytes((STATIC_DIR / filename).read_bytes(), content_type)
            except FileNotFoundError:
                self._send_json({"error": "فایل رابط کاربری موجود نیست"}, HTTPStatus.NOT_FOUND)

    return DashboardHandler


def create_dashboard_server(
    settings: Settings, host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(
        (host, port), _handler_factory(DashboardCache(settings))
    )


def serve_dashboard(settings: Settings, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = create_dashboard_server(settings, host=host, port=port)
    LOGGER.info("Dashboard available at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Dashboard stopped")
    finally:
        server.server_close()
