from __future__ import annotations

import json
import math
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from .assets import canonical_asset, canonical_tehran_asset, normalize_fa
from .dates import format_jalali_date, parse_user_date
from .financial_contract import (
    CANONICAL_CALCULATION_VERSION,
    CURRENCY_RIAL,
    LEGACY_CALCULATION_VERSION,
    QUANTITY_CONTRACT,
    QUANTITY_UNIT,
    decimal_text,
    exact_decimal,
    normalize_exposure,
    validate_currency_contract,
)
from .financial_rates import (
    calculate_commission,
    resolve_commission_rate,
    resolve_risk_free_rate,
)
from .option_math import call_greeks_from_price, call_greeks_from_volatility


TEHRAN = ZoneInfo("Asia/Tehran")
ENTRY_DATE_GRACE_DAYS = 1
def _estimated_commission(
    market: str, kind: str, price: float, quantity: float, *, as_of: date | None = None,
) -> float:
    amount, _ = calculate_commission(
        market=str(market or "tehran"),
        kind=kind,
        as_of=as_of or tehran_today(),
        price=max(0.0, price),
        quantity=max(0.0, quantity),
    )
    return float(amount)


def _exact_product(*values) -> float:
    """Multiply financial factors through Decimal and expose JSON-safe float."""
    result = exact_decimal(1, name="factor")
    for value in values:
        result *= exact_decimal(value, name="factor")
    return float(result)


def _captured_money_values(source: dict, resolved: dict[str, object]) -> dict[str, str]:
    """Capture authoritative v8 monetary inputs as exact decimal text."""
    captured: dict[str, str] = {}
    existing = source.get("money_values")
    if isinstance(existing, dict):
        for key, value in existing.items():
            try:
                captured[str(key)] = decimal_text(value, name=str(key))
            except ValueError:
                continue
    for key, fallback in resolved.items():
        value = source.get(key) if source.get(key) not in (None, "") else fallback
        if value not in (None, ""):
            captured[key] = decimal_text(value, name=key)
    return captured


def _money_decimal(record: dict, key: str, fallback=0):
    values = record.get("money_values")
    value = values.get(key) if isinstance(values, dict) else None
    if value in (None, ""):
        value = record.get(key, fallback)
    return exact_decimal(value, name=key)


def _attach_v8_trade_money_values(
    snapshot: dict, trade: dict, quote: dict | None = None,
) -> dict:
    """Attach Decimal-native monetary results to a v8 compatibility snapshot.

    The numeric fields in ``snapshot`` remain JSON numbers for the current API,
    while ``money_values`` is the authoritative exact representation.  Every
    derived amount below is recalculated from captured input lexemes (or a raw
    quote at the market-data boundary), never from an already-computed float.
    """
    if int(trade.get("calculation_version") or LEGACY_CALCULATION_VERSION) < 8:
        return snapshot
    money = dict(trade.get("money_values") or {})
    zero = Decimal("0")
    one_hundred = Decimal("100")
    quantity = exact_decimal(snapshot.get("quantity"), name="quantity")
    contract_size = exact_decimal(
        snapshot.get("contract_size"), name="contract_size"
    )
    units = quantity * contract_size
    exercise_quantity = exact_decimal(
        snapshot.get("exercise_quantity", 0), name="exercise_quantity"
    )
    premium_quantity = exact_decimal(
        snapshot.get("premium_trade_quantity", 0),
        name="premium_trade_quantity",
    )
    exercise_units = exercise_quantity * contract_size
    premium_units = premium_quantity * contract_size
    entry_base = _money_decimal(trade, "entry_base_price")
    entry_premium = _money_decimal(trade, "entry_premium")
    strike = _money_decimal(trade, "strike", snapshot.get("strike"))
    commission = _money_decimal(trade, "commission", snapshot.get("commission", 0))
    exit_commission = _money_decimal(
        trade, "exit_commission", snapshot.get("exit_commission", 0) or 0
    )
    option_exit_commission = _money_decimal(
        trade,
        "option_exit_commission_estimate",
        snapshot.get("option_exit_commission_estimate", 0),
    )
    exercise_commission = _money_decimal(
        trade,
        "exercise_commission_estimate",
        snapshot.get("exercise_commission_estimate", 0),
    )
    underlying_exit_commission = _money_decimal(
        trade,
        "underlying_exit_commission_estimate",
        snapshot.get("underlying_exit_commission_estimate", 0),
    )
    is_closed = trade.get("status") == "closed"
    is_long = str(trade.get("strategy_type") or "covered_call") == "long_call"
    net_entry = entry_premium if is_long else entry_base - entry_premium
    invested = net_entry * units + commission

    exact_results: dict[str, Decimal] = {
        "net_entry": net_entry,
        "invested_capital": invested,
        "commission": commission,
        "exit_commission": exit_commission,
        "realized_commission": commission + exit_commission,
    }

    def current_money(trade_key: str, quote_key: str, snapshot_key: str):
        if snapshot.get(snapshot_key) is None:
            return None
        if is_closed:
            return _money_decimal(trade, trade_key, snapshot[snapshot_key])
        raw = (quote or {}).get(quote_key)
        return exact_decimal(
            raw if raw is not None else snapshot[snapshot_key], name=snapshot_key
        )

    current_base = current_money(
        "exit_base_price", "base_last", "current_base_price"
    )
    current_option = current_money(
        "exit_option_price", "option_last", "current_option_exit_price"
    )
    realized_commission = commission + exit_commission
    option_offset_total = (
        realized_commission if is_closed else commission + option_exit_commission
    )
    exercise_total = (
        realized_commission if is_closed else commission + exercise_commission
    )
    exercise_and_sell_total = (
        realized_commission
        if is_closed
        else commission + exercise_commission + underlying_exit_commission
    )
    offset_and_sell_total = (
        realized_commission
        if is_closed
        else commission + option_exit_commission + underlying_exit_commission
    )
    exact_results.update({
        "option_offset_total_commission": option_offset_total,
        "exercise_total_commission": exercise_total,
        "exercise_and_sell_total_commission": exercise_and_sell_total,
        "offset_and_sell_total_commission": offset_and_sell_total,
    })
    if current_base is not None:
        exact_results["current_base_price"] = current_base
    if current_option is not None:
        exact_results["current_option_exit_price"] = current_option

    risk_free_rate = exact_decimal(
        snapshot.get("risk_free_annual_rate", 0), name="risk_free_annual_rate"
    )
    risk_free_days = exact_decimal(
        snapshot.get("risk_free_days", 0), name="risk_free_days"
    )
    exact_results["risk_free_profit"] = (
        invested * risk_free_rate * risk_free_days / one_hundred / Decimal("365")
    )

    if is_long:
        exact_results.update({
            "long_exercise_required_cash": strike * units,
            "exercise_allocation_required_cash": strike * exercise_units,
            "exercise_plus_premium": strike + entry_premium,
            "long_max_loss": invested,
        })
        annual_rate = exact_decimal(
            snapshot.get("annual_interest_rate", 0), name="annual_interest_rate"
        )
        entry_days = exact_decimal(snapshot.get("entry_days", 0), name="entry_days")
        interest_cost = strike * annual_rate * entry_days / one_hundred / Decimal("365")
        exact_results["exercise_interest_cost"] = interest_cost
        exact_results["interest_adjusted_exercise_plus_premium"] = (
            strike + entry_premium - interest_cost
        )
        if current_base is not None:
            gap_per_unit = strike + entry_premium - current_base
            exercise_allocation_commission = (
                exercise_and_sell_total * exercise_quantity / quantity
                if quantity > zero else zero
            )
            exact_results.update({
                "exercise_today_cost_gap": gap_per_unit * units,
                "exercise_today_profit": -gap_per_unit * units - exercise_and_sell_total,
                "exercise_allocation_cost_gap": gap_per_unit * exercise_units,
                "exercise_allocation_profit": (
                    -gap_per_unit * exercise_units - exercise_allocation_commission
                ),
                "long_exercise_profit": (
                    (current_base - strike - entry_premium) * units
                    - exercise_and_sell_total
                ),
                "long_exercise_breakeven": (
                    strike + entry_premium + exercise_and_sell_total / units
                ),
                "long_exercise_capital": (
                    (strike + entry_premium) * units + exercise_and_sell_total
                ),
                "long_expiration_profit": (
                    max(current_base - strike, zero) - entry_premium
                ) * units - commission,
            })
        if current_option is not None:
            premium_commission = (
                option_offset_total * premium_quantity / quantity
                if quantity > zero else zero
            )
            premium_profit = (
                (current_option - entry_premium) * premium_units
                - premium_commission
            )
            offset_profit = (
                (current_option - entry_premium) * units - option_offset_total
            )
            exact_results["premium_profit"] = premium_profit
            exact_results["long_offset_profit"] = offset_profit
            if "exercise_allocation_profit" in exact_results:
                exact_results["long_combined_profit"] = (
                    premium_profit + exact_results["exercise_allocation_profit"]
                )
            if is_closed:
                method = str(trade.get("exit_method") or "offset")
                realized = premium_profit
                if method == "exercise" and current_base is not None:
                    realized = (
                        (current_base - strike - entry_premium) * units
                        - realized_commission
                    )
                    exact_results["exercise_settlement_profit"] = realized
                elif method == "mixed":
                    realized = exact_results.get("long_combined_profit", premium_profit)
                exact_results["realized_profit"] = realized
                exact_results["long_combined_profit"] = realized
        elif snapshot.get("long_combined_profit") is not None:
            exact_results["long_combined_profit"] = exact_results[
                "exercise_allocation_profit"
            ]
        if snapshot.get("exercise_acquisition_price") is not None:
            acquired_units = exercise_units if exercise_units > zero else units
            exact_results["exercise_acquisition_price"] = (
                strike + entry_premium + realized_commission / acquired_units
            )
            if current_base is not None:
                exact_results["exercise_market_value_at_acquisition"] = current_base
        if snapshot.get("post_exercise_base_profit") is not None and quote:
            tracked = exact_decimal(
                quote.get("base_last"), name="tracked_base_price"
            )
            acquisition = _money_decimal(
                trade, "exit_base_price", snapshot.get("exercise_market_value_at_acquisition")
            )
            exact_results["post_exercise_base_profit"] = (
                tracked - acquisition
            ) * units
    else:
        net_premium = entry_premium * units - commission
        reference_base = current_base if current_base is not None else entry_base
        hold_net_benefit = entry_premium * units - exercise_total
        hold_per_unit = hold_net_benefit / units
        expected = (
            strike - entry_base + entry_premium
        ) * units - exercise_total
        base_change = (reference_base - entry_base) * units
        exact_results.update({
            "expected_profit": expected,
            "covered_hold_profit": expected,
            "covered_hold_base_price": entry_base,
            "covered_exercise_profit_per_unit": strike - entry_base,
            "covered_hold_premium_per_unit": entry_premium,
            "covered_net_premium_received": net_premium,
            "covered_net_premium_per_unit": net_premium / units,
            "covered_breakeven": entry_base - hold_per_unit,
            "covered_max_profit": expected,
            "covered_max_loss": invested,
            "covered_expiration_profit": (
                min(reference_base, strike) - entry_base + entry_premium
            ) * units - commission,
            "covered_base_change_profit": base_change,
            "covered_reference_base_price": reference_base,
        })
        if current_option is not None:
            option_change = (
                (entry_premium - current_option) * units - option_offset_total
            )
            combined = base_change + option_change
            exact_results.update({
                "covered_option_change_profit": option_change,
                "covered_combined_change_profit": combined,
                "covered_foregone_upside": (
                    max(zero, base_change - combined)
                    if reference_base > strike else zero
                ),
            })
            exercised = is_closed and trade.get("exit_method") == "exercise"
            settlement_base = strike if exercised else current_base
            settlement_option = zero if exercised else current_option
            option_profit = (
                (entry_premium - settlement_option) * units - option_offset_total
            )
            total_profit = (
                (entry_premium - settlement_option + settlement_base - entry_base)
                * units
                - offset_and_sell_total
            )
            kept = (
                is_closed
                and trade.get("exit_method") == "offset"
                and trade.get("underlying_disposition") == "keep"
            )
            if kept:
                total_profit = option_profit
            exact_results.update({
                "covered_liquidation_profit": total_profit,
                "covered_option_only_profit": option_profit,
                "option_profit": option_profit,
                "base_profit": (
                    zero if kept else (settlement_base - entry_base) * units
                ),
                "settlement_base_price": settlement_base,
                "total_profit": total_profit,
            })
            if is_closed:
                exact_results["realized_profit"] = total_profit
            candidates = (total_profit, expected, option_profit)
            exact_results["covered_best_profit"] = max(candidates)

        if snapshot.get("all_offset_and_sell_profit") is not None:
            raw_option = (
                (quote or {}).get("option_exit_ask")
                or (quote or {}).get("option_last")
                or snapshot.get("all_offset_option_price")
            )
            raw_base = (
                (quote or {}).get("base_bid")
                or (quote or {}).get("base_last")
                or snapshot.get("all_offset_base_price")
            )
            liquidation_option = exact_decimal(
                raw_option, name="all_offset_option_price"
            )
            liquidation_base = exact_decimal(raw_base, name="all_offset_base_price")
            exact_results["all_offset_option_price"] = liquidation_option
            exact_results["all_offset_base_price"] = liquidation_base
            exact_results["all_offset_and_sell_profit"] = (
                entry_premium - liquidation_option + liquidation_base - entry_base
            ) * units - offset_and_sell_total

    if snapshot.get("strategy_profit_for_risk_free") is not None:
        strategy_key = (
            "realized_profit"
            if is_closed
            else "long_combined_profit"
            if is_long and exact_results.get("long_combined_profit") is not None
            else "long_offset_profit"
            if is_long
            else "covered_liquidation_profit"
        )
        if exact_results.get(strategy_key) is not None:
            exact_results["strategy_profit_for_risk_free"] = exact_results[
                strategy_key
            ]

    for key, value in exact_results.items():
        if key in {"net_entry", "invested_capital", "commission"} or snapshot.get(key) is not None:
            snapshot[key] = float(value)
            money[key] = decimal_text(value, name=key)
    snapshot["money_schema_version"] = 1
    snapshot["money_values"] = money
    return snapshot


def _commission_value(value, *, estimate) -> tuple[float, str]:
    """Preserve explicit zero; estimate only an absent/null commission."""
    if value in (None, ""):
        return float(estimate()), "estimated"
    return _number(value, minimum=0), "actual"


def tehran_today() -> date:
    """Return the business calendar date used by the dashboard."""
    return datetime.now(TEHRAN).date()


def _number(value, *, minimum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("مقادیر عددی معامله معتبر نیستند") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError("مقادیر عددی معامله معتبر نیستند")
    return number


def trade_underlying_units(
    trade: dict, quantity=None, *, contract_size=None
) -> float:
    """Return economic underlying units without reinterpreting v7 records.

    Version 8 is the first canonical contract-count schema.  Missing metadata
    and every version below 8 retain the historical meaning where ``quantity``
    was already the final unit count.
    """
    source_quantity = trade.get("quantity", 1) if quantity is None else quantity
    try:
        version = int(
            trade.get("calculation_version") or LEGACY_CALCULATION_VERSION
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("نسخه محاسبه معامله معتبر نیست") from exc
    canonical = version >= CANONICAL_CALCULATION_VERSION
    exposure = normalize_exposure(
        quantity=source_quantity,
        quantity_kind=(
            trade.get("quantity_kind") if canonical else QUANTITY_UNIT
        ),
        contract_size=(
            contract_size
            if contract_size is not None
            else trade.get("contract_size", 1)
        ),
        calculation_version=version,
    )
    if canonical and exposure.quantity_kind != QUANTITY_CONTRACT:
        raise ValueError("در نسخه ۸، مقدار quantity باید تعداد قرارداد باشد")
    return float(exposure.underlying_units)


def quote_key(market: str, symbol: str) -> str:
    """Build a stable key across Persian/Arabic Yeh and Kaf variants."""
    return f"{str(market or '').strip()}|{normalize_fa(str(symbol or ''))}"


def resolve_trade_quote(payload: dict, live_quote: dict | None) -> dict:
    """Resolve a live quote or an explicitly entered expired contract.

    Manual contract metadata is accepted only for contracts whose expiry is not
    after Tehran's current business date. This keeps the normal workflow tied
    to the market feed while allowing historical positions to be reconstructed.
    """
    mode = str(payload.get("contract_entry_mode") or "live").strip()
    if mode != "manual_expired":
        if live_quote:
            return live_quote
        raise ValueError("نماد اختیار در اطلاعات جاری بازار پیدا نشد")

    symbol = normalize_fa(
        str(payload.get("manual_option_symbol") or payload.get("option_symbol") or "")
    ).strip()
    asset = normalize_fa(str(payload.get("asset") or "")).strip()
    market = str(payload.get("market") or "").strip()
    if market not in {"goods", "tehran"} or not symbol or not asset:
        raise ValueError("بازار، دارایی پایه و نماد قرارداد منقضی‌شده الزامی هستند")
    try:
        expiry = parse_user_date(str(payload.get("manual_expiry") or ""))
    except ValueError as exc:
        raise ValueError("تاریخ سررسید قرارداد منقضی‌شده معتبر نیست") from exc
    if expiry > tehran_today():
        raise ValueError("ورود دستی فقط برای قراردادی مجاز است که سررسید آن گذشته یا امروز باشد")
    result = {
        "market": market,
        "asset": asset,
        "symbol": symbol,
        "strike": _number(payload.get("manual_strike"), minimum=0.0000001),
        "expiry": expiry.isoformat(),
        "expiry_display": format_jalali_date(expiry),
        "contract_size": _number(payload.get("manual_contract_size"), minimum=0.0000001),
        "base_last": None,
        "option_last": None,
        "manual_expired": True,
    }
    return result


def underlying_quote_key(market: str, asset: str) -> str:
    market_name = str(market or "").strip()
    raw_asset = str(asset or "")
    goods_asset = canonical_asset(raw_asset, "")
    if goods_asset:
        # Physical commodities and commodity funds are priced by the IME
        # feed even when an older/manual position was mistakenly saved as TSE.
        market_name = "goods"
        canonical = goods_asset
    else:
        canonical = canonical_tehran_asset(raw_asset, "") or normalize_fa(raw_asset)
    # User-entered labels may use spaces, underscores or a zero-width joiner
    # for the same exchange symbol (for example هم تراز / هم‌تراز).
    normalized = normalize_fa(canonical).replace("\u200c", " ").replace("_", " ")
    normalized = " ".join(normalized.split())
    return f"{market_name}|{normalized}"


def build_underlying_quote_map(option_quotes: dict[str, dict]) -> dict[str, dict]:
    """Collapse option-chain quotes into one current quote per base asset."""
    result: dict[str, dict] = {}
    for quote in option_quotes.values():
        key = underlying_quote_key(quote.get("market"), quote.get("asset"))
        candidate = {
            "market": quote.get("market"), "asset": quote.get("asset"),
            "last": quote.get("base_last"), "bid": quote.get("base_bid"),
            "ask": quote.get("base_ask"),
            "last_is_previous_day": bool(quote.get("base_last_is_previous_day")),
            "previous_date": quote.get("base_previous_date"),
        }
        current = result.get(key)
        # Prefer a real trade from today over a complete quote assembled from
        # the previous close.  Multiple option rows can describe the same base
        # asset, and the first one is not necessarily the freshest one.
        score = (
            int(candidate.get("last") is not None and not candidate["last_is_previous_day"]),
            sum(candidate.get(name) is not None for name in ("last", "bid", "ask")),
            int(candidate.get("last") is not None),
        )
        current_score = (-1, -1, -1) if current is None else (
            int(current.get("last") is not None and not current.get("last_is_previous_day")),
            sum(current.get(name) is not None for name in ("last", "bid", "ask")),
            int(current.get("last") is not None),
        )
        if score > current_score:
            result[key] = candidate
    return result


def _analytics_snapshot(
    *, base_price: float, strike: float, option_price: float | None,
    days: int, interest_rate: float, covered: bool, prefix: str,
) -> dict:
    itm_percent = (
        (base_price - strike) / base_price * 100.0
        if base_price > 0 else None
    )
    greeks = None
    if base_price > 0 and option_price is not None and option_price >= 0 and days > 0:
        greeks = call_greeks_from_price(
            base_price, strike, days, option_price, interest_rate
        )
    estimated = greeks is None
    if estimated and base_price > 0:
        greeks = call_greeks_from_volatility(
            base_price, strike, max(1, days), interest_rate, volatility=0.35
        )
    option_delta = None if greeks is None else round(greeks.delta, 4)
    strategy_delta = (
        None if option_delta is None
        else round(1.0 - option_delta, 4) if covered else option_delta
    )
    return {
        f"{prefix}_base_price_snapshot": base_price,
        f"{prefix}_option_price_snapshot": option_price,
        f"{prefix}_days_to_expiry": max(0, days),
        f"{prefix}_itm_percent": (
            round(itm_percent, 2) if itm_percent is not None else None
        ),
        f"{prefix}_moneyness": (
            "ITM" if base_price > strike else "OTM" if base_price < strike else "ATM"
        ),
        f"{prefix}_option_delta": option_delta,
        f"{prefix}_strategy_delta": strategy_delta,
        f"{prefix}_implied_volatility": (
            None if greeks is None else round(greeks.implied_volatility * 100.0, 2)
        ),
        f"{prefix}_delta_estimated": estimated if greeks is not None else False,
    }


def _risk_neutral_call_itm_probability(
    *, spot: float, strike: float, days: int, interest_rate: float,
    volatility_percent: float | None,
) -> float | None:
    """Return the Black–Scholes risk-neutral probability N(d2).

    The project does not currently store a continuous dividend yield, so the
    disclosed model uses q=0.  This is a scenario indicator, not a forecast of
    the real-world exercise rate.
    """
    if spot <= 0 or strike <= 0 or volatility_percent is None:
        return None
    if days <= 0:
        return 100.0 if spot > strike else 0.0 if spot < strike else 50.0
    sigma = volatility_percent / 100.0
    if sigma <= 0:
        return None
    years = days / 365.0
    rate = interest_rate / 100.0
    d2 = (
        math.log(spot / strike) + (rate - 0.5 * sigma * sigma) * years
    ) / (sigma * math.sqrt(years))
    return max(0.0, min(100.0, 100.0 * 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))))


def build_quote_map(goods_rows: list[dict], tehran_rows: list[dict]) -> dict[str, dict]:
    def positive(value) -> float | None:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None

    quotes: dict[str, dict] = {}
    for market, rows in (("goods", goods_rows), ("tehran", tehran_rows)):
        for row in rows:
            symbol = normalize_fa(str(row.get("symbolOption") or ""))
            if not symbol:
                continue
            resolver = canonical_asset if market == "goods" else canonical_tehran_asset
            asset = resolver(str(row.get("baseSymbol") or ""), symbol)
            base_ask = positive(
                row.get("bestAskBase") if "bestAskBase" in row else row.get("askPrice1Base")
            )
            base_bid = positive(
                row.get("bestBidBase") if "bestBidBase" in row else row.get("bidPrice1Base")
            )
            base_last_raw = positive(row.get("lastTradeBase"))
            base_previous = positive(row.get("previousPriceBase"))
            option_ask = positive(row.get("askPrice1Option"))
            option_bid = positive(row.get("bidPrice1Option"))
            option_last_raw = positive(row.get("optionPrice") or row.get("lastTradeOption"))
            option_previous = positive(row.get("previousPriceOption"))
            base_last = base_last_raw or base_previous
            option_last = option_last_raw or option_previous
            base_price = base_ask or base_last or positive(row.get("closingPriceBase"))
            strike = positive(row.get("dueDatePrice"))
            if base_price is None or strike is None:
                continue
            expiry_raw = str(row.get("expiration_date") or "").split("T", 1)[0]
            try:
                expiry_date = parse_user_date(expiry_raw)
            except ValueError:
                continue
            expiry = expiry_date.isoformat()
            if not asset or not expiry:
                continue
            quotes[quote_key(market, symbol)] = {
                "market": market,
                "asset": asset,
                "symbol": symbol,
                "base_price": base_price,
                "base_ask": base_ask,
                # Closing a recorded strategy is based on the latest traded
                # underlying price, not the current order-book ask.
                "base_last": base_last,
                "base_last_raw": base_last_raw,
                "base_previous": base_previous,
                "base_last_is_previous_day": base_last_raw is None and base_previous is not None,
                "base_previous_date": row.get("previousPriceBaseDate"),
                "base_bid": base_bid,
                "base_queue_status": row.get("baseQueueStatus") or "نامشخص",
                "base_market_status": row.get("baseTradingStatus") or "نامشخص",
                "base_market_status_code": row.get("baseTradingStatusCode"),
                "base_market_status_date": row.get("baseTradingStatusDate"),
                "base_is_closed": bool(row.get("baseIsClosed")),
                "option_queue_status": row.get("optionQueueStatus") or "نامشخص",
                "quote_quality_valid": bool(row.get("quoteQualityValid", True)),
                "quote_quality_warnings": dict(row.get("quoteQualityWarnings") or {}),
                # A short call is closed by buying at the best sell/ask quote.
                "option_exit_ask": option_ask,
                # A purchased call is closed by selling at the best bid quote.
                "option_exit_bid": option_bid,
                # Open long-call P/L is marked to the latest traded premium.
                "option_last": option_last,
                "option_last_raw": option_last_raw,
                "option_previous": option_previous,
                "option_last_is_previous_day": option_last_raw is None and option_previous is not None,
                "option_previous_date": row.get("previousPriceOptionDate"),
                "strike": strike,
                "contract_size": positive(row.get("contractSize")) or 1.0,
                "expiry": expiry,
                "days": int(float(row.get("days") or 0)),
                "ins_code_option": str(row.get("insCodeOption") or ""),
                "ins_code_base": str(row.get("insCodeBase") or ""),
            }
    return quotes


def select_trade_valuation_quote(
    quote: dict | None,
    strategy_type: str,
    *,
    covered_option_basis: str = "last",
    covered_base_basis: str = "last",
    long_option_basis: str = "last",
    long_base_basis: str = "last",
) -> dict | None:
    """Select the user-requested marks without changing the raw market quote."""
    if quote is None:
        return None
    selected = dict(quote)
    option_basis = long_option_basis if strategy_type == "long_call" else covered_option_basis
    base_basis = long_base_basis if strategy_type == "long_call" else covered_base_basis
    option_key = {"bid": "option_exit_bid", "ask": "option_exit_ask", "last": "option_last"}.get(option_basis, "option_last")
    base_key = {"bid": "base_bid", "ask": "base_ask", "last": "base_last"}.get(base_basis, "base_last")
    option_value = quote.get(option_key)
    base_value = quote.get(base_key)
    warnings = quote.get("quote_quality_warnings") or {}
    option_blocked = (
        (option_basis == "ask" and quote.get("option_queue_status") == "صف خرید")
        or (option_basis == "bid" and quote.get("option_queue_status") == "صف فروش")
        or (option_basis == "ask" and "askPrice1Option" in warnings)
        or (option_basis == "bid" and "bidPrice1Option" in warnings)
    )
    base_blocked = (
        (base_basis == "ask" and quote.get("base_queue_status") == "صف خرید")
        or (base_basis == "bid" and quote.get("base_queue_status") == "صف فروش")
        or (base_basis == "ask" and "bestAskBase" in warnings)
        or (base_basis == "bid" and "bestBidBase" in warnings)
    )
    option_fallback = option_basis != "last" and option_value is None and not option_blocked
    base_fallback = base_basis != "last" and base_value is None and not base_blocked
    if option_fallback:
        option_value = quote.get("option_last")
    if base_fallback:
        base_value = quote.get("base_last")
    selected["option_last"] = option_value
    selected["base_last"] = base_value
    selected["selected_option_is_previous_day"] = bool(
        (option_basis == "last" or option_fallback) and quote.get("option_last_is_previous_day")
    )
    selected["selected_base_is_previous_day"] = bool(
        (base_basis == "last" or base_fallback) and quote.get("base_last_is_previous_day")
    )
    selected["valuation_option_label"] = (
        "آخرین قیمت روز معاملاتی قبل" if selected["selected_option_is_previous_day"]
        else "آخرین معامله" if option_fallback
        else "بهترین پیشنهاد خرید" if option_basis == "bid"
        else "بهترین پیشنهاد فروش" if option_basis == "ask"
        else "آخرین معامله"
    )
    selected["valuation_base_label"] = (
        "آخرین قیمت روز معاملاتی قبل" if selected["selected_base_is_previous_day"]
        else "آخرین معامله" if base_fallback
        else "بهترین پیشنهاد خرید" if base_basis == "bid"
        else "بهترین پیشنهاد فروش" if base_basis == "ask"
        else "آخرین معامله"
    )
    return selected


def calculate_trade_snapshot(
    trade: dict, quote: dict | None, *, as_of: date
) -> dict:
    entry_date = parse_user_date(trade["entry_date"])
    entry_base = _number(trade["entry_base_price"], minimum=0.0000001)
    entry_premium = _number(trade["entry_premium"], minimum=0)
    quantity = _number(trade.get("quantity", 1), minimum=0.0000001)
    contract_size = _number(trade.get("contract_size", 1), minimum=0.0000001)
    calculation_version = int(
        trade.get("calculation_version") or LEGACY_CALCULATION_VERSION
    )
    validate_currency_contract(
        currency_unit=trade.get("currency_unit") or CURRENCY_RIAL,
        calculation_version=calculation_version,
    )
    commission = _number(trade.get("commission", 0), minimum=0)
    option_exit_commission_estimate = _number(
        trade.get("option_exit_commission_estimate", 0), minimum=0
    )
    exercise_commission_estimate = _number(
        trade.get("exercise_commission_estimate", 0), minimum=0
    )
    underlying_exit_commission_estimate = _number(
        trade.get("underlying_exit_commission_estimate", 0), minimum=0
    )
    exit_commission = (
        _number(trade.get("exit_commission", 0), minimum=0)
        if trade.get("status") == "closed"
        else 0.0
    )
    realized_commission = commission + exit_commission
    is_closed = trade.get("status") == "closed"
    option_offset_total_commission = (
        realized_commission
        if is_closed
        else commission + option_exit_commission_estimate
    )
    exercise_total_commission = (
        realized_commission
        if is_closed
        else commission + exercise_commission_estimate
    )
    exercise_and_sell_total_commission = (
        realized_commission
        if is_closed
        else commission
        + exercise_commission_estimate
        + underlying_exit_commission_estimate
    )
    offset_and_sell_total_commission = (
        realized_commission
        if is_closed
        else commission
        + option_exit_commission_estimate
        + underlying_exit_commission_estimate
    )
    strategy_type = str(trade.get("strategy_type") or "covered_call")
    is_long_call = strategy_type == "long_call"
    if is_long_call:
        exercise_quantity = _number(trade.get("exercise_quantity", 0), minimum=0)
        premium_trade_quantity = _number(
            trade.get("premium_trade_quantity", quantity), minimum=0
        )
        allocation_total = exercise_quantity + premium_trade_quantity
        # Legacy records predate allocation fields and belong to the premium
        # trading bucket. New records are kept reconciled by TradeStore.
        if allocation_total <= 0:
            premium_trade_quantity = quantity
            allocation_total = quantity
        quantity = allocation_total
    else:
        exercise_quantity = 0.0
        premium_trade_quantity = 0.0
    units = trade_underlying_units(trade, quantity)
    exercise_units = (
        trade_underlying_units(trade, exercise_quantity)
        if is_long_call and exercise_quantity > 0 else 0.0
    )
    premium_trade_units = (
        trade_underlying_units(trade, premium_trade_quantity)
        if is_long_call and premium_trade_quantity > 0 else 0.0
    )
    base_is_closed = bool(
        trade.get("status") != "closed"
        and quote
        and quote.get("base_is_closed") is True
    )

    if trade.get("status") == "closed":
        current_base = _number(trade["exit_base_price"], minimum=0)
        current_option = _number(trade["exit_option_price"], minimum=0)
        valuation_date = parse_user_date(trade["exit_date"])
        data_status = "closed"
    elif base_is_closed:
        current_base = current_option = None
        valuation_date = as_of
        data_status = "base_closed"
    elif quote and quote.get("base_last") is not None and quote.get("option_last") is not None:
        # Open-position profit on the personal trades page is marked to the
        # latest trades of both legs. Order-book prices remain available for
        # market screening, but do not drive these two P/L figures.
        current_base = _number(quote["base_last"], minimum=0)
        current_option = _number(quote["option_last"], minimum=0)
        valuation_date = as_of
        data_status = "live"
    else:
        current_base = current_option = None
        valuation_date = as_of
        data_status = "quote_unavailable"

    strike_value = trade.get("strike") or (quote or {}).get("strike")
    expiry_value = trade.get("expiry") or (quote or {}).get("expiry")
    strike = _number(strike_value, minimum=0.0000001)
    expiry = datetime.strptime(str(expiry_value), "%Y-%m-%d").date()
    entry_days = max(1, (expiry - entry_date).days)
    elapsed_days = max(0, (valuation_date - entry_date).days)
    invested_days = max(1, (valuation_date - entry_date).days)
    net_entry = entry_premium if is_long_call else entry_base - entry_premium
    if net_entry <= 0:
        raise ValueError(
            "پرمیوم پرداختی باید مثبت باشد"
            if is_long_call
            else "قیمت پایه در ورود باید بیشتر از پرمیوم دریافتی باشد"
        )

    market = str(trade.get("market") or "tehran")
    # New/open forms already persist their live estimate.  The fallback is
    # intentionally limited to historical closed records so a zero estimate
    # never changes the live scenarios while market prices are moving.
    commission_source = str(trade.get("commission_source") or "").strip()
    if commission_source not in {"actual", "estimated"}:
        commission_source = (
            "estimated"
            if is_closed
            and calculation_version < CANONICAL_CALCULATION_VERSION
            and commission <= 0
            else "actual"
        )
    commission_was_estimated = commission_source == "estimated"
    if commission_was_estimated:
        commission = _estimated_commission(
            market, "option_buy" if is_long_call else "option_sell", entry_premium, units
        )
        if not is_long_call and not trade.get("underlying_position_id"):
            commission += _estimated_commission(market, "underlying_buy", entry_base, units)

    if is_closed and option_exit_commission_estimate <= 0 and current_option is not None:
        option_exit_commission_estimate = _estimated_commission(
            market, "option_sell" if is_long_call else "option_buy", current_option, units
        )
    if is_closed and exercise_commission_estimate <= 0:
        exercise_commission_estimate = _estimated_commission(
            market, "option_exercise", strike, exercise_units if is_long_call else units
        )
    if is_closed and underlying_exit_commission_estimate <= 0 and current_base is not None:
        underlying_exit_commission_estimate = _estimated_commission(
            market, "underlying_sell", current_base, units
        )

    exit_commission_source = str(trade.get("exit_commission_source") or "").strip()
    if exit_commission_source not in {"actual", "estimated"}:
        exit_commission_source = (
            "estimated"
            if is_closed
            and calculation_version < CANONICAL_CALCULATION_VERSION
            and exit_commission <= 0
            else "actual"
        )
    exit_commission_was_estimated = bool(
        is_closed and exit_commission_source == "estimated"
    )
    if exit_commission_was_estimated:
        exit_commission = 0.0
        method = str(trade.get("exit_method") or "offset")
        if is_long_call:
            if method in {"exercise", "mixed"}:
                exit_commission += _estimated_commission(market, "option_exercise", strike, exercise_units)
                exit_commission += _estimated_commission(market, "underlying_buy", strike, exercise_units)
            if method in {"offset", "mixed", "roll"}:
                offset_units = premium_trade_units if method == "mixed" else units
                exit_commission += _estimated_commission(market, "option_sell", current_option or 0, offset_units)
        else:
            if method == "exercise":
                exit_commission += _estimated_commission(market, "option_exercise", strike, units)
            else:
                exit_commission += _estimated_commission(market, "option_buy", current_option or 0, units)
            if str(trade.get("underlying_disposition") or "sell") == "sell":
                exit_commission += _estimated_commission(market, "underlying_sell", current_base or 0, units)

    realized_commission = commission + exit_commission
    option_offset_total_commission = realized_commission if is_closed else commission + option_exit_commission_estimate
    exercise_total_commission = realized_commission if is_closed else commission + exercise_commission_estimate
    exercise_and_sell_total_commission = realized_commission if is_closed else commission + exercise_commission_estimate + underlying_exit_commission_estimate
    offset_and_sell_total_commission = realized_commission if is_closed else commission + option_exit_commission_estimate + underlying_exit_commission_estimate

    invested_capital = _exact_product(net_entry, units) + commission
    risk_free_days = max(0, (valuation_date - entry_date).days)
    risk_free_annual_rate = (
        _number(trade.get("annual_interest_rate", 40), minimum=0)
        if calculation_version >= CANONICAL_CALCULATION_VERSION
        else 40.0
    )
    risk_free_profit = (
        invested_capital * (risk_free_annual_rate / 100.0) * risk_free_days / 365.0
    )

    def with_risk_free_comparison(snapshot: dict) -> dict:
        """Attach a like-for-like 40% annual risk-free benchmark."""
        if trade.get("status") == "closed":
            strategy_profit = snapshot.get("realized_profit")
            strategy_basis = "سود یا زیان قطعی معامله"
        elif is_long_call:
            strategy_profit = snapshot.get("long_combined_profit")
            if strategy_profit is None:
                strategy_profit = snapshot.get("long_offset_profit")
            strategy_basis = "نتیجه فعلی خرید اختیار بر اساس تخصیص ثبت‌شده"
        else:
            strategy_profit = snapshot.get("covered_liquidation_profit")
            strategy_basis = "آفست اختیار و فروش دارایی پایه در امروز"
        strategy_profit = (
            float(strategy_profit)
            if strategy_profit is not None and math.isfinite(float(strategy_profit))
            else None
        )
        snapshot.update({
            "risk_free_annual_rate": risk_free_annual_rate,
            "risk_free_days": risk_free_days,
            "risk_free_profit": risk_free_profit,
            "risk_free_return_percent": (
                risk_free_annual_rate * risk_free_days / 365.0
            ),
            "strategy_profit_for_risk_free": strategy_profit,
            "strategy_profit_for_risk_free_percent": (
                strategy_profit / invested_capital * 100.0
                if strategy_profit is not None and invested_capital > 0 else None
            ),
            "strategy_to_risk_free_multiple": (
                strategy_profit / risk_free_profit
                if strategy_profit is not None and risk_free_profit > 0 else None
            ),
            "strategy_profit_for_risk_free_basis": strategy_basis,
        })
        return _attach_v8_trade_money_values(snapshot, trade, quote)
    # Covered-call hold/assignment metric requested by the user:
    #   strike - base entry price + received premium
    # multiplied by the final quantity entered by the user. Current market
    # marks belong only to today's exit scenarios and must not change this
    # expiry target. An explicitly closed underlying suppresses all open P/L.
    covered_exercise_profit_per_unit = (
        None if is_long_call else strike - entry_base
    )
    expected_profit = (
        None
        if is_long_call or base_is_closed
        else _exact_product(covered_exercise_profit_per_unit + entry_premium, units)
        - exercise_total_commission
    )
    expected_percent = (
        None if expected_profit is None else expected_profit / invested_capital * 100
    )
    result = {
        **trade,
        "entry_date_display": format_jalali_date(entry_date),
        "expiry": expiry.isoformat(),
        "expiry_display": format_jalali_date(expiry),
        "strike": strike,
        "entry_days": entry_days,
        "elapsed_days": elapsed_days,
        "invested_days": invested_days,
        "strategy_progress_percent": min(100.0, elapsed_days / entry_days * 100),
        "remaining_days": max(0, (expiry - valuation_date).days),
        "net_entry": net_entry,
        "quantity": quantity,
        "contract_size": contract_size,
        "underlying_units": units,
        "invested_capital": invested_capital,
        "commission": commission,
        "commission_source": commission_source,
        "exit_commission": exit_commission if is_closed else trade.get("exit_commission"),
        "exit_commission_source": exit_commission_source if is_closed else trade.get("exit_commission_source"),
        "exercise_quantity": exercise_quantity,
        "premium_trade_quantity": premium_trade_quantity,
        "expected_profit": expected_profit,
        "expected_profit_percent": expected_percent,
        "expected_profit_yoy": (
            None if expected_percent is None else expected_percent * 365 / entry_days
        ),
        "current_base_price": current_base,
        "current_option_exit_price": current_option,
        "current_option_exit_ask": current_option,
        "covered_hold_base_price": entry_base if not is_long_call else None,
        "covered_exercise_profit_per_unit": covered_exercise_profit_per_unit,
        "covered_hold_premium_per_unit": entry_premium if not is_long_call else None,
        "base_price_change_percent": (
            None
            if current_base is None
            else (current_base - entry_base) / entry_base * 100
        ),
        "premium_price_change_percent": (
            None
            if current_option is None or entry_premium <= 0
            else (current_option - entry_premium) / entry_premium * 100
        ),
        "option_valuation_basis": (
            "ثبت خروج"
            if trade.get("status") == "closed"
            else str((quote or {}).get("valuation_option_label") or "آخرین معامله")
            if data_status == "live"
            else "ناموجود"
        ),
        "base_valuation_basis": (
            "ثبت خروج"
            if trade.get("status") == "closed"
            else str((quote or {}).get("valuation_base_label") or "آخرین معامله")
            if data_status == "live"
            else "ناموجود"
        ),
        "base_best_bid": (quote or {}).get("base_bid"),
        "base_best_ask": (quote or {}).get("base_ask"),
        "base_last_trade": (
            (quote or {}).get("base_last_raw")
            or (quote or {}).get("base_previous")
            or (quote or {}).get("base_last")
        ),
        "base_last_is_previous_day": bool(
            (quote or {}).get("base_last_is_previous_day")
        ),
        "option_best_bid": (quote or {}).get("option_exit_bid"),
        "option_best_ask": (quote or {}).get("option_exit_ask"),
        "option_last_trade": (
            (quote or {}).get("option_last_raw")
            or (quote or {}).get("option_previous")
            or (quote or {}).get("option_last")
        ),
        "option_last_is_previous_day": bool(
            (quote or {}).get("option_last_is_previous_day")
        ),
        "selected_base_is_previous_day": bool(
            (quote or {}).get("selected_base_is_previous_day")
        ),
        "selected_option_is_previous_day": bool(
            (quote or {}).get("selected_option_is_previous_day")
        ),
        "base_is_closed": base_is_closed,
        "base_market_status": (
            str((quote or {}).get("base_market_status") or "نامشخص")
        ),
        "base_market_status_code": (quote or {}).get("base_market_status_code"),
        "data_status": data_status,
        "valuation_date_display": format_jalali_date(valuation_date),
        "exit_date_display": (
            format_jalali_date(valuation_date)
            if trade.get("status") == "closed"
            else None
        ),
        "exit_commission": exit_commission,
        "realized_commission": realized_commission,
        "commission_auto_calculated": commission_was_estimated,
        "exit_commission_auto_calculated": exit_commission_was_estimated,
        "option_exit_commission_estimate": option_exit_commission_estimate,
        "exercise_commission_estimate": exercise_commission_estimate,
        "underlying_exit_commission_estimate": underlying_exit_commission_estimate,
        "option_offset_total_commission": option_offset_total_commission,
        "exercise_total_commission": exercise_total_commission,
        "exercise_and_sell_total_commission": exercise_and_sell_total_commission,
        "offset_and_sell_total_commission": offset_and_sell_total_commission,
        "exit_method": trade.get("exit_method") if trade.get("status") == "closed" else None,
        "exit_method_label": (
            "اعمال/تخصیص" if trade.get("exit_method") == "exercise"
            else "خروج ترکیبی" if trade.get("exit_method") == "mixed"
            else "آفست" if trade.get("status") == "closed" else None
        ),
    }
    if not is_long_call:
        result.update({
            "covered_hold_profit": expected_profit,
            "covered_hold_percent": expected_percent,
        })
    annual_interest_rate = _number(trade.get("annual_interest_rate", 40), minimum=0)
    if result.get("entry_itm_percent") is None:
        result.update(_analytics_snapshot(
            base_price=entry_base, strike=strike, option_price=entry_premium,
            days=entry_days, interest_rate=annual_interest_rate,
            covered=not is_long_call, prefix="entry",
        ))
    if trade.get("status") != "closed" and current_base is not None:
        result.update(_analytics_snapshot(
            base_price=current_base, strike=strike, option_price=current_option,
            days=max(0, (expiry - valuation_date).days),
            interest_rate=annual_interest_rate,
            covered=not is_long_call, prefix="current",
        ))
    if trade.get("status") == "closed" and result.get("exit_itm_percent") is None:
        result.update(_analytics_snapshot(
            base_price=current_base, strike=strike, option_price=current_option,
            days=max(0, (expiry - valuation_date).days),
            interest_rate=annual_interest_rate,
            covered=not is_long_call, prefix="exit",
        ))
    if not is_long_call:
        probability_prefix = "exit" if trade.get("status") == "closed" else "current"
        probability_volatility = result.get(f"{probability_prefix}_implied_volatility")
        probability_estimated = bool(result.get(f"{probability_prefix}_delta_estimated"))
        reference_base = current_base if current_base is not None else entry_base
        probability_days = max(0, (expiry - valuation_date).days)
        net_premium_received = _exact_product(entry_premium, units) - commission
        premium_per_unit_net = net_premium_received / units
        hold_net_benefit = (
            _exact_product(entry_premium, units) - exercise_total_commission
        )
        hold_net_benefit_per_unit = hold_net_benefit / units
        breakeven = entry_base - hold_net_benefit_per_unit
        base_change_profit = _exact_product(reference_base - entry_base, units)
        option_change_profit = (
            _exact_product(entry_premium - float(current_option), units)
            - option_offset_total_commission
            if current_option is not None else None
        )
        combined_change_profit = (
            base_change_profit + option_change_profit
            if option_change_profit is not None else None
        )
        foregone_upside = (
            max(0.0, base_change_profit - combined_change_profit)
            if combined_change_profit is not None and reference_base > strike
            else 0.0
        )
        premium_return_percent = (
            net_premium_received / invested_capital * 100.0
            if invested_capital > 0 else None
        )
        exit_method = str(trade.get("exit_method") or "")
        rolled = exit_method == "roll" or bool(
            trade.get("rolled_to_trade_id") or trade.get("roll_to_trade_id")
        )
        position_status = (
            "rolled" if rolled
            else "exercised" if trade.get("status") == "closed" and exit_method == "exercise"
            else "closed" if trade.get("status") == "closed"
            else "open"
        )
        result.update({
            "covered_position_status": position_status,
            "covered_net_premium_received": net_premium_received,
            "covered_net_premium_per_unit": premium_per_unit_net,
            "covered_premium_return_percent": premium_return_percent,
            "covered_premium_return_yoy": (
                premium_return_percent * 365.0 / entry_days
                if premium_return_percent is not None else None
            ),
            "covered_strike_distance": strike - reference_base,
            "covered_strike_distance_percent": (
                (strike - reference_base) / reference_base * 100.0
                if reference_base > 0 else None
            ),
            "covered_breakeven": breakeven,
            "covered_max_profit": (
                _exact_product(strike - entry_base + entry_premium, units)
                - exercise_total_commission
            ),
            "covered_max_loss": invested_capital,
            "covered_expiration_profit": _exact_product(
                min(reference_base, strike) - entry_base + entry_premium,
                units,
            ) - commission,
            "covered_assigned": reference_base > strike,
            "covered_downside_protection_percent": (
                hold_net_benefit_per_unit / entry_base * 100.0
                if entry_base > 0 else None
            ),
            "covered_base_change_profit": base_change_profit,
            "covered_option_change_profit": option_change_profit,
            "covered_combined_change_profit": combined_change_profit,
            "covered_foregone_upside": foregone_upside,
            "covered_assignment_probability": _risk_neutral_call_itm_probability(
                spot=reference_base, strike=strike, days=probability_days,
                interest_rate=annual_interest_rate,
                volatility_percent=probability_volatility,
            ),
            "covered_assignment_probability_model": "Black–Scholes N(d2), q=0",
            "covered_assignment_probability_estimated": probability_estimated,
            "covered_assignment_probability_volatility": probability_volatility,
            "covered_reference_base_price": reference_base,
        })
    if is_long_call:
        annual_rate = annual_interest_rate
        period_interest_rate = annual_rate / 100 * entry_days / 365
        exercise_plus_premium = strike + entry_premium
        exercise_interest_cost = strike * period_interest_rate
        interest_adjusted_exercise_plus_premium = (
            exercise_plus_premium - exercise_interest_cost
        )
        exercise_premium_vs_base_percent = (
            (interest_adjusted_exercise_plus_premium - entry_base)
            / entry_base
            * 100
        )
        exercise_profit_percent = (
            (((period_interest_rate - 1) * strike) + entry_premium)
            / entry_base
            * 100
        )
        result.update({
            "annual_interest_rate": annual_rate,
            "period_interest_rate": period_interest_rate,
            "long_exercise_required_cash": _exact_product(strike, units),
            "exercise_allocation_required_cash": _exact_product(strike, exercise_units),
            "exercise_profit_percent": exercise_profit_percent,
            "exercise_plus_premium": exercise_plus_premium,
            "exercise_interest_cost": exercise_interest_cost,
            "interest_adjusted_exercise_plus_premium": (
                interest_adjusted_exercise_plus_premium
            ),
            "exercise_premium_vs_base_percent": (
                exercise_premium_vs_base_percent
            ),
        })
        if current_base is not None:
            expiration_profit = (
                _exact_product(max(current_base - strike, 0.0) - entry_premium, units)
                - commission
            )
            exercise_cost_gap = _exact_product(strike + entry_premium - current_base, units)
            allocated_exercise_cost_gap = (
                _exact_product(strike + entry_premium - current_base, exercise_units)
            )
            exercise_commission = (
                exercise_and_sell_total_commission * exercise_quantity / quantity
                if quantity > 0 else 0.0
            )
            result.update({
                # The cost gap follows the user's requested expression:
                # strike + paid premium - today's underlying price.  Its
                # negative is the standard exercise P/L.
                "exercise_today_cost_gap": exercise_cost_gap,
                "exercise_today_profit": (
                    -exercise_cost_gap - exercise_and_sell_total_commission
                ),
                "exercise_allocation_cost_gap": allocated_exercise_cost_gap,
                "exercise_allocation_profit": (
                    -allocated_exercise_cost_gap - exercise_commission
                ),
                "exercise_allocation_profit_percent": (
                    (-allocated_exercise_cost_gap - exercise_commission)
                    / invested_capital * 100
                ),
                "long_exercise_profit": (
                    _exact_product(current_base - (strike + entry_premium), units)
                    - exercise_and_sell_total_commission
                ),
                "long_exercise_profit_percent": (
                    (_exact_product(current_base - (strike + entry_premium), units)
                    - exercise_and_sell_total_commission)
                    / (_exact_product(strike + entry_premium, units)
                       + exercise_and_sell_total_commission)
                    * 100
                ),
                "long_exercise_breakeven": (
                    strike + entry_premium
                    + exercise_and_sell_total_commission / units
                ),
                "long_exercise_capital": (
                    _exact_product(strike + entry_premium, units)
                    + exercise_and_sell_total_commission
                ),
                "long_expiration_profit": expiration_profit,
                "long_max_loss": invested_capital,
            })
        if (
            trade.get("status") == "closed"
            and trade.get("exit_method") == "exercise"
            and quote
            and quote.get("base_last") is not None
        ):
            tracked_base = _number(quote["base_last"], minimum=0)
            exercised_units = max(1.0, exercise_units or units)
            acquisition_break_even = (
                strike + entry_premium + realized_commission / exercised_units
            )
            result.update({
                "exercise_acquisition_price": acquisition_break_even,
                "exercise_acquisition_units": exercised_units,
                "exercise_market_value_at_acquisition": current_base,
                "tracked_base_price": tracked_base,
                # The option result already includes intrinsic value through
                # the exercise date, so only the subsequent base movement is
                # additive in the combined portfolio view.
                "post_exercise_base_profit": (
                    _exact_product(tracked_base - current_base, units)
                ),
            })
        if current_option is None:
            exercise_result = result.get("exercise_allocation_profit")
            combined = (
                exercise_result
                if premium_trade_quantity == 0 and exercise_result is not None
                else None
            )
            result.update({
                "long_offset_profit": None,
                "long_offset_profit_percent": None,
                "premium_profit": None,
                "premium_growth_percent": None,
                "premium_profit_yoy": None,
                "long_combined_profit": combined,
                "long_combined_profit_percent": (
                    combined / invested_capital * 100 if combined is not None else None
                ),
            })
            return with_risk_free_comparison(result)
        premium_commission = (
            option_offset_total_commission * premium_trade_quantity / quantity
            if quantity > 0 else 0.0
        )
        premium_profit = (
            _exact_product(current_option - entry_premium, premium_trade_units)
            - premium_commission
        )
        long_offset_profit = (
            _exact_product(current_option - entry_premium, units)
            - option_offset_total_commission
        )
        premium_growth_percent = (current_option - entry_premium) / entry_premium * 100
        exercise_allocation_profit = result.get("exercise_allocation_profit")
        long_combined_profit = (
            premium_profit + exercise_allocation_profit
            if exercise_allocation_profit is not None else None
        )
        result.update({
            "long_offset_profit": long_offset_profit,
            "long_offset_profit_percent": (
                long_offset_profit / invested_capital * 100
            ),
            "premium_profit": premium_profit,
            "premium_growth_percent": premium_growth_percent,
            "premium_profit_yoy": premium_growth_percent * 365 / invested_days,
            "long_combined_profit": long_combined_profit,
            "long_combined_profit_percent": (
                long_combined_profit / invested_capital * 100
                if long_combined_profit is not None else None
            ),
            "long_combined_profit_yoy": (
                long_combined_profit / invested_capital * 100 * 365 / invested_days
                if long_combined_profit is not None else None
            ),
        })
        if trade.get("status") == "closed":
            realized_profit = premium_profit
            if trade.get("exit_method") == "exercise":
                realized_profit = (
                    _exact_product(current_base - strike - entry_premium, units)
                    - realized_commission
                )
                result["exercise_settlement_profit"] = realized_profit
            elif trade.get("exit_method") == "mixed":
                realized_profit = long_combined_profit
            realized_percent = realized_profit / invested_capital * 100
            result.update({
                "realized_profit": realized_profit,
                "realized_profit_percent": realized_percent,
                "realized_profit_yoy": realized_percent * 365 / invested_days,
            })
            result["long_combined_profit"] = realized_profit
            result["long_combined_profit_percent"] = realized_percent
            result["long_combined_profit_yoy"] = realized_percent * 365 / invested_days
        return with_risk_free_comparison(result)

    # A portfolio-wide liquidation is executable only by buying back every
    # short call at the best ask and selling every underlying at the best bid.
    # If either order book side is unavailable, the last reliable trade is
    # used; build_quote_map marks it when that value came from the prior day.
    liquidation_option = None if base_is_closed else (
        (quote or {}).get("option_exit_ask") or (quote or {}).get("option_last")
    )
    liquidation_base = None if base_is_closed else (
        (quote or {}).get("base_bid") or (quote or {}).get("base_last")
    )
    result.update({
        "all_offset_option_price": liquidation_option,
        "all_offset_option_basis": (
            "بهترین پیشنهاد فروش"
            if (quote or {}).get("option_exit_ask") is not None
            else "آخرین قیمت روز معاملاتی قبل"
            if (quote or {}).get("option_last_is_previous_day")
            else "آخرین معامله"
            if liquidation_option is not None else "ناموجود"
        ),
        "all_offset_option_is_previous_day": bool(
            (quote or {}).get("option_exit_ask") is None
            and (quote or {}).get("option_last_is_previous_day")
        ),
        "all_offset_base_price": liquidation_base,
        "all_offset_base_basis": (
            "بهترین پیشنهاد خرید"
            if (quote or {}).get("base_bid") is not None
            else "آخرین قیمت روز معاملاتی قبل"
            if (quote or {}).get("base_last_is_previous_day")
            else "آخرین معامله"
            if liquidation_base is not None else "ناموجود"
        ),
        "all_offset_base_is_previous_day": bool(
            (quote or {}).get("base_bid") is None
            and (quote or {}).get("base_last_is_previous_day")
        ),
    })
    if liquidation_option is not None and liquidation_base is not None:
        liquidation_profit = _exact_product(
            (entry_premium - float(liquidation_option))
            + (float(liquidation_base) - entry_base),
            units,
        ) - offset_and_sell_total_commission
        result.update({
            "all_offset_and_sell_profit": liquidation_profit,
            "all_offset_and_sell_percent": liquidation_profit / invested_capital * 100,
        })
    else:
        result.update({
            "all_offset_and_sell_profit": None,
            "all_offset_and_sell_percent": None,
        })

    if current_base is None or current_option is None:
        result.update({
            "covered_liquidation_profit": None,
            "covered_liquidation_percent": None,
            "covered_option_only_profit": None,
            "covered_option_only_percent": None,
            "covered_best_profit": expected_profit,
            "covered_best_percent": expected_percent,
            "covered_best_decision": "نگهداری پوزیشن کاوردکال",
            "option_profit": None,
            "option_profit_percent": None,
            "option_profit_yoy": None,
            "option_profit_fulfillment_percent": None,
            "total_profit": None,
            "total_profit_percent": None,
            "total_profit_yoy": None,
            "total_profit_fulfillment_percent": None,
            "base_profit": None,
        })
        return with_risk_free_comparison(result)

    exercised = trade.get("status") == "closed" and trade.get("exit_method") == "exercise"
    settlement_base = strike if exercised else current_base
    settlement_option = 0.0 if exercised else current_option
    option_profit_per_unit = entry_premium - settlement_option
    base_profit_per_unit = settlement_base - entry_base
    total_profit_per_unit = option_profit_per_unit + base_profit_per_unit
    option_profit = _exact_product(option_profit_per_unit, units) - option_offset_total_commission
    total_profit = _exact_product(total_profit_per_unit, units) - offset_and_sell_total_commission
    kept_underlying = (
        trade.get("status") == "closed"
        and trade.get("exit_method") == "offset"
        and trade.get("underlying_disposition") == "keep"
    )
    if kept_underlying:
        # Only the option leg is realized here. The released base lot resumes
        # independent mark-to-market tracking at its original acquisition cost.
        total_profit = option_profit
        base_profit_per_unit = 0.0
    result.update({
        "covered_liquidation_profit": total_profit,
        "covered_liquidation_percent": total_profit / invested_capital * 100,
        "covered_option_only_profit": option_profit,
        "covered_option_only_percent": option_profit / invested_capital * 100,
        "option_profit": option_profit,
        "option_profit_percent": option_profit / invested_capital * 100,
        "option_profit_yoy": option_profit / invested_capital * 100 * 365 / invested_days,
        "option_profit_fulfillment_percent": (
            option_profit / expected_profit * 100 if expected_profit != 0 else None
        ),
        "base_profit": _exact_product(base_profit_per_unit, units),
        "underlying_kept": kept_underlying,
        "settlement_base_price": settlement_base,
        "total_profit": total_profit,
        "total_profit_percent": total_profit / invested_capital * 100,
        "total_profit_yoy": total_profit / invested_capital * 100 * 365 / invested_days,
        "total_profit_fulfillment_percent": (
            total_profit / expected_profit * 100 if expected_profit != 0 else None
        ),
    })
    decision_candidates = [
        ("آفست اختیار و فروش دارایی پایه", total_profit),
        ("نگهداری پوزیشن کاوردکال", expected_profit),
        ("آفست اختیار و نگهداری دارایی پایه", option_profit),
    ]
    best_label, best_profit = max(decision_candidates, key=lambda item: item[1])
    result.update({
        "covered_best_profit": best_profit,
        "covered_best_percent": best_profit / invested_capital * 100,
        "covered_best_decision": best_label,
    })
    if trade.get("status") == "closed":
        result.update({
            "realized_profit": total_profit,
            "realized_profit_percent": total_profit / invested_capital * 100,
            "realized_profit_yoy": (
                total_profit / invested_capital * 100 * 365 / invested_days
            ),
        })
    return with_risk_free_comparison(result)


def summarize_open_trades(
    trades: list[dict], underlying_positions: list[dict] | None = None,
) -> dict:
    """Reconcile the open-trade portfolio metrics shown on the trades page."""
    open_trades = [item for item in trades if item.get("status") != "closed"]
    covered = [
        item
        for item in open_trades
        if str(item.get("strategy_type") or "covered_call") == "covered_call"
    ]
    long_calls = [
        item for item in open_trades if item.get("strategy_type") == "long_call"
    ]

    def total(items: list[dict], key: str) -> float:
        return sum(
            float(item[key])
            for item in items
            if item.get(key) is not None and math.isfinite(float(item[key]))
        )

    def annualized_percent(
        items: list[dict], profit_keys: tuple[str, ...], *,
        days_key: str = "invested_days", capital_key: str = "invested_capital",
    ) -> float | None:
        profit_total = 0.0
        capital_total = 0.0
        capital_days = 0.0
        for item in items:
            profit = next(
                (
                    float(item[key]) for key in profit_keys
                    if item.get(key) is not None
                    and math.isfinite(float(item[key]))
                ),
                None,
            )
            if profit is None:
                continue
            capital = float(item.get(capital_key) or 0)
            if capital <= 0 or not math.isfinite(capital):
                continue
            days = max(1.0, float(item.get(days_key) or 1))
            profit_total += profit
            capital_total += capital
            capital_days += capital * days
        if capital_total <= 0 or capital_days <= 0:
            return None
        average_days = capital_days / capital_total
        return profit_total / capital_total * 100 * 365 / average_days

    covered_best_profit = 0.0
    covered_best_capital = 0.0
    covered_best_capital_days = 0.0
    covered_valued_count = 0
    for item in covered:
        candidates = [
            (key, float(item[key]))
            for key in (
                "covered_hold_profit",
                "covered_option_only_profit",
                "covered_liquidation_profit",
                "expected_profit",
                "option_profit",
                "total_profit",
            )
            if item.get(key) is not None and math.isfinite(float(item[key]))
        ]
        if candidates:
            best_key, best_profit = max(candidates, key=lambda candidate: candidate[1])
            covered_best_profit += best_profit
            best_days_key = (
                "entry_days"
                if best_key in {"covered_hold_profit", "expected_profit"}
                else "invested_days"
            )
            item_capital = float(item.get("invested_capital") or 0)
            if item_capital > 0 and math.isfinite(item_capital):
                covered_best_capital += item_capital
                covered_best_capital_days += item_capital * max(
                    1.0, float(item.get(best_days_key) or 1)
                )
            covered_valued_count += 1

    long_premium_profit = total(long_calls, "premium_profit")
    long_exercise_profit = total(long_calls, "exercise_allocation_profit")
    long_combined_profit = sum(
        float(
            item.get("long_combined_profit")
            if item.get("long_combined_profit") is not None
            else item.get("premium_profit") or 0
        )
        for item in long_calls
    )
    long_valued_count = sum(
        1
        for item in long_calls
        if (
            item.get("long_combined_profit") is not None
            or item.get("premium_profit") is not None
        )
    )
    long_combined_capital = sum(
        float(item.get("invested_capital") or 0)
        for item in long_calls
        if item.get("long_combined_profit") is not None
        or item.get("premium_profit") is not None
    )
    long_combined_capital_days = sum(
        float(item.get("invested_capital") or 0)
        * max(1.0, float(item.get("invested_days") or 1))
        for item in long_calls
        if item.get("long_combined_profit") is not None
        or item.get("premium_profit") is not None
    )

    def current_fluctuation(
        items: list[dict], profit_keys: tuple[str, ...]
    ) -> tuple[float, int, float, float]:
        """Aggregate the current marked fluctuation without scenario mixing."""
        profit_total = 0.0
        valued_count = 0
        capital_total = 0.0
        capital_days = 0.0
        for item in items:
            profit = next(
                (
                    float(item[key]) for key in profit_keys
                    if item.get(key) is not None
                    and math.isfinite(float(item[key]))
                ),
                None,
            )
            if profit is None:
                continue
            profit_total += profit
            valued_count += 1
            capital = float(item.get("invested_capital") or 0)
            if capital > 0 and math.isfinite(capital):
                capital_total += capital
                capital_days += capital * max(
                    1.0, float(item.get("invested_days") or 1)
                )
        return profit_total, valued_count, capital_total, capital_days

    (
        covered_fluctuation_profit,
        covered_fluctuation_count,
        covered_fluctuation_capital,
        covered_fluctuation_capital_days,
    ) = current_fluctuation(
        covered, ("covered_liquidation_profit", "total_profit")
    )
    (
        long_fluctuation_profit,
        long_fluctuation_count,
        long_fluctuation_capital,
        long_fluctuation_capital_days,
    ) = current_fluctuation(
        long_calls, ("long_offset_profit", "premium_profit")
    )
    covered_capital = total(covered, "invested_capital")
    covered_hold_profit = total(covered, "covered_hold_profit")
    covered_option_only_profit = total(covered, "covered_option_only_profit")
    covered_selected_liquidation_profit = total(
        covered, "covered_liquidation_profit"
    )
    covered_liquidation_profit = total(covered, "all_offset_and_sell_profit")
    covered_liquidation_count = sum(
        1 for item in covered
        if item.get("all_offset_and_sell_profit") is not None
        and math.isfinite(float(item["all_offset_and_sell_profit"]))
    )
    long_capital = total(long_calls, "invested_capital")
    long_offset_profit = total(long_calls, "long_offset_profit")
    long_exercise_decision_profit = total(long_calls, "long_exercise_profit")
    long_exercise_capital = total(long_calls, "long_exercise_capital")
    long_exercise_required_cash = total(
        long_calls, "long_exercise_required_cash"
    )
    long_exercise_allocation_required_cash = total(
        long_calls, "exercise_allocation_required_cash"
    )

    by_asset: list[dict] = []
    strategy_trades = covered + long_calls
    asset_names = sorted(
        {str(item.get("asset") or "نامشخص").strip() or "نامشخص" for item in strategy_trades},
        key=normalize_fa,
    )
    for asset in asset_names:
        items = [
            item for item in strategy_trades
            if (str(item.get("asset") or "نامشخص").strip() or "نامشخص") == asset
        ]
        asset_capital = total(items, "invested_capital")
        asset_profit = 0.0
        valued_count = 0
        for item in items:
            strategy = str(item.get("strategy_type") or "covered_call")
            if strategy == "long_call":
                value = (
                    item.get("long_offset_profit")
                    if item.get("long_offset_profit") is not None
                    else item.get("premium_profit")
                )
                candidates = [] if value is None else [float(value)]
            else:
                value = (
                    item.get("covered_liquidation_profit")
                    if item.get("covered_liquidation_profit") is not None
                    else item.get("total_profit")
                )
                candidates = [] if value is None else [float(value)]
            candidates = [value for value in candidates if math.isfinite(value)]
            if candidates:
                asset_profit += candidates[0]
                valued_count += 1
        by_asset.append({
            "asset": asset,
            "count": len(items),
            "covered_count": sum(
                1 for item in items
                if str(item.get("strategy_type") or "covered_call") == "covered_call"
            ),
            "long_call_count": sum(
                1 for item in items if item.get("strategy_type") == "long_call"
            ),
            "underlying_count": 0,
            "valued_count": valued_count,
            "invested_capital": asset_capital,
            "selected_profit": asset_profit,
            "selected_profit_percent": (
                asset_profit / asset_capital * 100 if asset_capital > 0 else None
            ),
        })
    by_asset.sort(
        key=lambda item: (-float(item["invested_capital"]), normalize_fa(item["asset"]))
    )
    standalone_underlyings = [
        item for item in (underlying_positions or [])
        if item.get("status") != "closed"
        and not item.get("portfolio_excluded")
        and float(item.get("available_quantity") or 0) > 0
    ]
    underlying_capital = total(standalone_underlyings, "invested_capital")
    underlying_profit = total(standalone_underlyings, "profit")
    portfolio_capital = covered_capital + long_capital
    portfolio_profit = covered_fluctuation_profit + long_fluctuation_profit
    annualized_capital = covered_fluctuation_capital + long_fluctuation_capital
    annualized_capital_days = (
        covered_fluctuation_capital_days + long_fluctuation_capital_days
    )
    by_asset.sort(
        key=lambda item: (-float(item["invested_capital"]), normalize_fa(item["asset"]))
    )
    for item in by_asset:
        item["liquidity_share_percent"] = (
            float(item["invested_capital"]) / portfolio_capital * 100
            if portfolio_capital > 0 else None
        )

    return {
        "covered_call": {
            "count": len(covered),
            "invested_capital": covered_capital,
            "expected_profit": total(covered, "expected_profit"),
            "hold_profit": covered_hold_profit,
            "hold_percent": (
                covered_hold_profit / covered_capital * 100
                if covered_capital > 0 else None
            ),
            "hold_yoy": annualized_percent(
                covered, ("covered_hold_profit", "expected_profit"),
                days_key="entry_days",
            ),
            "option_only_profit": covered_option_only_profit,
            "option_only_percent": (
                covered_option_only_profit / covered_capital * 100
                if covered_capital > 0 else None
            ),
            "option_only_yoy": annualized_percent(
                covered, ("covered_option_only_profit", "option_profit")
            ),
            "selected_liquidation_profit": covered_selected_liquidation_profit,
            "selected_liquidation_percent": (
                covered_selected_liquidation_profit / covered_capital * 100
                if covered_capital > 0 else None
            ),
            "selected_liquidation_yoy": annualized_percent(
                covered, ("covered_liquidation_profit", "total_profit")
            ),
            "best_decision_profit": covered_best_profit,
            "best_decision_percent": (
                covered_best_profit / covered_capital * 100
                if covered_capital > 0 else None
            ),
            "all_offset_and_sell_profit": covered_liquidation_profit,
            "all_offset_and_sell_percent": (
                covered_liquidation_profit / covered_capital * 100
                if covered_capital > 0 else None
            ),
            "all_offset_and_sell_valued_count": covered_liquidation_count,
            "valued_count": covered_valued_count,
            "fluctuation_profit": covered_fluctuation_profit,
            "fluctuation_percent": (
                covered_fluctuation_profit / covered_capital * 100
                if covered_capital > 0 else None
            ),
            "fluctuation_yoy": annualized_percent(
                covered, ("covered_liquidation_profit", "total_profit")
            ),
            "fluctuation_valued_count": covered_fluctuation_count,
        },
        "long_call": {
            "count": len(long_calls),
            "invested_capital": long_capital,
            "premium_profit": long_premium_profit,
            "exercise_profit": long_exercise_profit,
            "offset_profit": long_offset_profit,
            "offset_percent": (
                long_offset_profit / long_capital * 100
                if long_capital > 0 else None
            ),
            "offset_yoy": annualized_percent(
                long_calls, ("long_offset_profit", "premium_profit")
            ),
            "exercise_decision_profit": long_exercise_decision_profit,
            "exercise_decision_percent": (
                long_exercise_decision_profit / long_exercise_capital * 100
                if long_exercise_capital > 0 else None
            ),
            "exercise_decision_yoy": annualized_percent(
                long_calls, ("long_exercise_profit",),
                capital_key="long_exercise_capital",
            ),
            "exercise_required_cash": long_exercise_required_cash,
            "exercise_allocation_required_cash": (
                long_exercise_allocation_required_cash
            ),
            "combined_profit": long_combined_profit,
            "combined_yoy": (
                long_combined_profit / long_combined_capital * 100 * 365
                / (long_combined_capital_days / long_combined_capital)
                if long_combined_capital > 0
                and long_combined_capital_days > 0 else None
            ),
            "valued_count": long_valued_count,
            "fluctuation_profit": long_fluctuation_profit,
            "fluctuation_percent": (
                long_fluctuation_profit / long_capital * 100
                if long_capital > 0 else None
            ),
            "fluctuation_yoy": annualized_percent(
                long_calls, ("long_offset_profit", "premium_profit")
            ),
            "fluctuation_valued_count": long_fluctuation_count,
        },
        "total": {
            "count": len(strategy_trades),
            "invested_capital": portfolio_capital,
            "selected_profit": portfolio_profit,
            "selected_profit_percent": (
                portfolio_profit / portfolio_capital * 100
                if portfolio_capital > 0 else None
            ),
            "selected_profit_yoy": (
                portfolio_profit / annualized_capital * 100 * 365
                / (annualized_capital_days / annualized_capital)
                if annualized_capital > 0 and annualized_capital_days > 0
                else None
            ),
            "valued_count": covered_fluctuation_count + long_fluctuation_count,
        },
        "underlying": summarize_underlying_positions(standalone_underlyings),
        "by_asset": by_asset,
    }


def summarize_closed_trades(
    trades: list[dict], underlying_positions: list[dict] | None = None,
) -> dict:
    """Aggregate realized results using capital-day weighted annualization."""
    closed = [item for item in trades if item.get("status") == "closed"]
    closed_underlyings = [
        {
            **item,
            "strategy_type": "underlying",
            "realized_profit": item.get("profit"),
        }
        for item in (underlying_positions or [])
        if item.get("status") == "closed" and not item.get("portfolio_excluded")
    ]
    closed = closed + closed_underlyings
    valued: list[tuple[float, float, float]] = []
    for item in closed:
        try:
            profit = float(item.get("realized_profit"))
            capital = float(item.get("invested_capital"))
            days = max(1.0, float(item.get("invested_days") or 1))
        except (TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in (profit, capital, days)):
            continue
        if capital <= 0:
            continue
        valued.append((profit, capital, days))

    net_profit = sum(profit for profit, _, _ in valued)
    invested_capital = sum(capital for _, capital, _ in valued)
    capital_days = sum(capital * days for _, capital, days in valued)
    by_asset = []
    asset_names = sorted(
        {str(item.get("asset") or "نامشخص").strip() or "نامشخص" for item in closed},
        key=normalize_fa,
    )
    for asset in asset_names:
        items = [
            item for item in closed
            if (str(item.get("asset") or "نامشخص").strip() or "نامشخص") == asset
        ]
        asset_valued = []
        for item in items:
            try:
                profit = float(item.get("realized_profit"))
                capital = float(item.get("invested_capital"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(profit) or not math.isfinite(capital) or capital <= 0:
                continue
            asset_valued.append((profit, capital))
        asset_profit = sum(profit for profit, _ in asset_valued)
        asset_capital = sum(capital for _, capital in asset_valued)
        by_asset.append({
            "asset": asset,
            "count": len(items),
            "valued_count": len(asset_valued),
            "covered_count": sum(
                1 for item in items
                if str(item.get("strategy_type") or "covered_call") == "covered_call"
            ),
            "long_call_count": sum(
                1 for item in items if item.get("strategy_type") == "long_call"
            ),
            "underlying_count": sum(
                1 for item in items if item.get("strategy_type") == "underlying"
            ),
            "invested_capital": asset_capital,
            "net_profit": asset_profit,
            "profit_percent": (
                asset_profit / asset_capital * 100 if asset_capital > 0 else None
            ),
        })
    by_asset.sort(
        key=lambda item: (-float(item["invested_capital"]), normalize_fa(item["asset"]))
    )
    for item in by_asset:
        item["liquidity_share_percent"] = (
            float(item["invested_capital"]) / invested_capital * 100
            if invested_capital > 0 else None
        )
    covered = [
        item for item in closed
        if str(item.get("strategy_type") or "covered_call") == "covered_call"
    ]

    def finite(value, default=0.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    gross_premium = sum(
        finite(item.get("entry_premium")) * finite(item.get("underlying_units") or item.get("quantity"))
        for item in covered
    )
    option_income = sum(finite(item.get("option_profit")) for item in covered)
    share_return = sum(
        (finite(item.get("exit_base_price"), finite(item.get("current_base_price")))
         - finite(item.get("entry_base_price")))
        * finite(item.get("underlying_units") or item.get("quantity"))
        for item in covered
    )
    foregone_upside = sum(
        max(0.0, finite(item.get("exit_base_price")) - finite(item.get("strike")))
        * finite(item.get("underlying_units") or item.get("quantity"))
        for item in covered
        if item.get("exit_method") == "exercise"
    )
    covered_profit = sum(finite(item.get("realized_profit")) for item in covered)
    holding_profit = share_return
    covered_returns = [
        finite(item.get("realized_profit_percent"), None)
        for item in covered
    ]
    covered_returns = [value for value in covered_returns if value is not None]
    covered_days = [max(1.0, finite(item.get("invested_days"), 1.0)) for item in covered]
    holding_downside_loss = sum(
        max(0.0, -(
            (finite(item.get("exit_base_price"), finite(item.get("current_base_price")))
             - finite(item.get("entry_base_price")))
            * finite(item.get("underlying_units") or item.get("quantity"))
        ))
        for item in covered
    )
    covered_downside_loss = sum(
        max(0.0, -finite(item.get("realized_profit"))) for item in covered
    )
    drawdown_reduction = holding_downside_loss - covered_downside_loss
    covered_evaluation = {
        "count": len(covered),
        "total_premium_received": gross_premium,
        "premium_income_net": option_income,
        "premium_retained_percent": (
            option_income / gross_premium * 100.0 if gross_premium > 0 else None
        ),
        "assignment_rate_percent": (
            sum(1 for item in covered if item.get("exit_method") == "exercise")
            / len(covered) * 100.0 if covered else None
        ),
        "rolled_rate_percent": (
            sum(1 for item in covered if (
                item.get("exit_method") == "roll"
                or item.get("rolled_to_trade_id")
                or item.get("roll_to_trade_id")
            )) / len(covered) * 100.0 if covered else None
        ),
        "average_period_return_percent": (
            sum(covered_returns) / len(covered_returns) if covered_returns else None
        ),
        "average_holding_days": (
            sum(covered_days) / len(covered_days) if covered_days else None
        ),
        "covered_return": covered_profit,
        "holding_return": holding_profit,
        "covered_vs_holding": covered_profit - holding_profit,
        "share_return": share_return,
        "option_income": option_income,
        "foregone_upside": foregone_upside,
        "reconstructed_return": share_return + option_income - foregone_upside,
        "holding_downside_loss": holding_downside_loss,
        "covered_downside_loss": covered_downside_loss,
        "drawdown_reduction": drawdown_reduction,
        "drawdown_reduction_percent": (
            drawdown_reduction / holding_downside_loss * 100.0
            if holding_downside_loss > 0 else None
        ),
        "drawdown_metric_note": "proxy_from_closed_downside_periods",
    }
    return {
        "count": len(closed),
        "valued_count": len(valued),
        "wins": sum(1 for profit, _, _ in valued if profit > 0),
        "losses": sum(1 for profit, _, _ in valued if profit < 0),
        "net_profit": net_profit,
        "invested_capital": invested_capital,
        "profit_percent": (
            net_profit / invested_capital * 100 if invested_capital > 0 else None
        ),
        "average_holding_days": (
            sum(days for _, _, days in valued) / len(valued) if valued else None
        ),
        "by_asset": by_asset,
        "annualized_return_percent": (
            net_profit / capital_days * 365 * 100 if capital_days > 0 else None
        ),
        "covered_call": covered_evaluation,
    }


def build_covered_profit_recognition(
    trades: list[dict], *, as_of: date, initial_capital: float | None
) -> dict:
    """Build reconciled option and underlying-aware profit views.

    The legacy function name is retained for API compatibility.  Covered calls
    expose option-only and option-plus-underlying marks.  Long calls expose the
    premium mark and the exercise-today result.  Closed trades are counted once;
    exercised long calls can then add only the base movement after exercise.
    """
    covered = [
        item for item in trades
        if str(item.get("strategy_type") or "covered_call") == "covered_call"
    ]
    long_calls = [item for item in trades if item.get("strategy_type") == "long_call"]
    open_items = [item for item in covered if item.get("status") != "closed"]
    closed_items = [item for item in covered if item.get("status") == "closed"]
    open_long = [item for item in long_calls if item.get("status") != "closed"]
    closed_long = [item for item in long_calls if item.get("status") == "closed"]

    def finite(value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def sum_present(items: list[dict], key: str) -> tuple[float, int]:
        values = [finite(item.get(key)) for item in items]
        present = [value for value in values if value is not None]
        return sum(present), len(present)

    closed_profit, closed_valued_count = sum_present(closed_items, "realized_profit")
    open_option_profit, open_option_count = sum_present(open_items, "option_profit")
    open_current_profit, open_current_count = sum_present(open_items, "total_profit")
    open_liquidation_profit, open_liquidation_count = sum_present(
        open_items, "all_offset_and_sell_profit"
    )
    open_expected_profit, open_expected_count = sum_present(open_items, "expected_profit")
    current_profit = closed_profit + open_current_profit
    all_offset_and_sell_profit = closed_profit + open_liquidation_profit
    final_profit = closed_profit + open_expected_profit

    closed_long_profit, closed_long_count = sum_present(closed_long, "realized_profit")
    open_long_offset_items = [
        {
            **item,
            "_long_offset_profit": (
                item.get("long_offset_profit")
                if item.get("long_offset_profit") is not None
                else item.get("premium_profit")
            ),
        }
        for item in open_long
    ]
    open_long_premium, open_long_premium_count = sum_present(
        open_long_offset_items, "_long_offset_profit"
    )
    open_long_combined_items = [
        {
            **item,
            "_combined_long_profit": (
                item.get("long_exercise_profit")
                if item.get("long_exercise_profit") is not None
                else item.get("long_combined_profit")
                if item.get("long_combined_profit") is not None
                else item.get("exercise_today_profit")
            ),
        }
        for item in open_long
    ]
    open_long_exercise, open_long_exercise_count = sum_present(
        open_long_combined_items, "_combined_long_profit"
    )
    post_exercise_profit, post_exercise_count = sum_present(
        [item for item in closed_long if item.get("exit_method") == "exercise"],
        "post_exercise_base_profit",
    )
    option_only_profit = (
        closed_profit + open_option_profit + closed_long_profit + open_long_premium
    )
    with_underlying_profit = (
        current_profit + closed_long_profit + open_long_exercise + post_exercise_profit
    )

    entry_dates = []
    for item in covered + long_calls:
        try:
            entry_dates.append(date.fromisoformat(str(item.get("entry_date") or "")))
        except ValueError:
            pass
    start_date = min(entry_dates) if entry_dates else as_of

    open_expiries = []
    for item in open_items:
        try:
            open_expiries.append(date.fromisoformat(str(item.get("expiry") or "")))
        except ValueError:
            pass
    if open_expiries:
        final_date = max(open_expiries)
    else:
        exit_dates = []
        for item in closed_items:
            try:
                exit_dates.append(date.fromisoformat(str(item.get("exit_date") or "")))
            except ValueError:
                pass
        final_date = max(exit_dates) if exit_dates else as_of

    elapsed_days = max(1, (as_of - start_date).days)
    horizon_days = max(1, (final_date - start_date).days)
    remaining_days = max(0, (final_date - as_of).days) if open_expiries else 0
    capital = finite(initial_capital) or 0.0

    def scaled(profit: float, days: int) -> dict:
        if capital <= 0:
            return {
                "return_percent": None,
                "monthly_return_percent": None,
                "annual_return_percent": None,
            }
        period_return = profit / capital * 100.0
        return {
            "return_percent": period_return,
            "monthly_return_percent": period_return * 30.0 / days,
            "annual_return_percent": period_return * 365.0 / days,
        }

    details = []
    for item in covered + long_calls:
        closed = item.get("status") == "closed"
        is_long = item.get("strategy_type") == "long_call"
        option_value = finite(
            item.get("realized_profit") if closed else
            (
                item.get("long_offset_profit")
                if item.get("long_offset_profit") is not None
                else item.get("premium_profit")
            ) if is_long else item.get("option_profit")
        )
        underlying_value = finite(
            item.get("realized_profit") if closed else
            (
                item.get("long_exercise_profit")
                if item.get("long_exercise_profit") is not None
                else item.get("long_combined_profit")
                if item.get("long_combined_profit") is not None
                else item.get("exercise_today_profit")
            ) if is_long else item.get("total_profit")
        )
        if is_long and closed and item.get("exit_method") == "exercise":
            underlying_value = (underlying_value or 0.0) + (
                finite(item.get("post_exercise_base_profit")) or 0.0
            )
        final_value = finite(
            item.get("realized_profit") if closed else
            (
                item.get("long_exercise_profit")
                if item.get("long_exercise_profit") is not None
                else item.get("long_combined_profit")
                if item.get("long_combined_profit") is not None
                else item.get("exercise_today_profit")
            ) if is_long else item.get("expected_profit")
        )
        details.append({
            "id": item.get("id"),
            "market": item.get("market"),
            "asset": item.get("asset"),
            "option_symbol": item.get("option_symbol"),
            "strategy_type": "long_call" if is_long else "covered_call",
            "status": "closed" if closed else "open",
            "expiry": item.get("expiry"),
            "expiry_display": item.get("expiry_display"),
            "remaining_days": 0 if closed else item.get("remaining_days"),
            "option_only_profit": option_value,
            "with_underlying_profit": underlying_value,
            "all_offset_and_sell_profit": finite(
                item.get("realized_profit") if closed
                else item.get("all_offset_and_sell_profit") if not is_long else None
            ),
            "all_offset_and_sell_percent": finite(
                item.get("realized_profit_percent") if closed
                else item.get("all_offset_and_sell_percent") if not is_long else None
            ),
            "invested_capital": finite(item.get("invested_capital")),
            "quantity": finite(item.get("quantity")),
            "exercise_quantity": finite(item.get("exercise_quantity")),
            "premium_trade_quantity": finite(item.get("premium_trade_quantity")),
            "base_best_bid": finite(item.get("base_best_bid")),
            "base_best_ask": finite(item.get("base_best_ask")),
            "base_last_trade": finite(item.get("base_last_trade")),
            "base_last_is_previous_day": bool(item.get("base_last_is_previous_day")),
            "option_best_bid": finite(item.get("option_best_bid")),
            "option_best_ask": finite(item.get("option_best_ask")),
            "option_last_trade": finite(item.get("option_last_trade")),
            "option_last_is_previous_day": bool(item.get("option_last_is_previous_day")),
            "current_profit": underlying_value,
            "exercise_cost_gap": finite(item.get("exercise_today_cost_gap")),
            "final_profit": final_value,
            "option_basis": "سود قطعی" if closed else (
                "فروش اختیار با مبنای انتخابی" if is_long else "آفست اختیار"
            ),
            "underlying_basis": "سود قطعی" if closed and not (
                is_long and item.get("exit_method") == "exercise"
            ) else "اعمال اختیار + تغییرات بعدی پایه" if closed else (
                "اعمال امروز: پایه − سربه‌سر (اعمال + پرمیوم)" if is_long
                else "آفست اختیار و فروش پایه"
            ),
            "current_basis": "سود قطعی" if closed else (
                "اعمال امروز بر اساس سربه‌سر" if is_long else "آفست اختیار و فروش پایه"
            ),
            "final_basis": "سود قطعی" if closed else (
                "اعمال بر اساس سربه‌سر امروز" if is_long else "سود انتظاری تا سررسید"
            ),
        })
    details.sort(key=lambda item: (
        item["status"] == "closed",
        str(item.get("expiry") or ""),
        str(item.get("option_symbol") or ""),
    ))

    underlying_positions = []
    for item in open_items:
        underlying_positions.append({
            "id": item.get("id"), "market": item.get("market"),
            "asset": item.get("asset"), "source": "covered_call",
            "source_label": "خرید پایه برای کاوردکال",
            "entry_date": item.get("entry_date"),
            "entry_price": finite(item.get("entry_base_price")),
            "current_price": finite(item.get("current_base_price")),
            "quantity": finite(item.get("quantity")),
            "profit": finite(item.get("base_profit")),
        })
    for item in closed_long:
        if item.get("exit_method") != "exercise":
            continue
        underlying_positions.append({
            "id": item.get("id"), "market": item.get("market"),
            "asset": item.get("asset"), "source": "exercise",
            "source_label": "دریافت پایه از اعمال اختیار",
            "entry_date": item.get("exit_date"),
            "entry_price": finite(item.get("exercise_acquisition_price")),
            "mark_price_at_acquisition": finite(item.get("exit_base_price")),
            "current_price": finite(item.get("tracked_base_price")),
            "quantity": finite(item.get("quantity")),
            "profit": finite(item.get("post_exercise_base_profit")),
        })

    return {
        "trade_count": len(covered) + len(long_calls),
        "covered_trade_count": len(covered),
        "long_trade_count": len(long_calls),
        "open_count": len(open_items) + len(open_long),
        "closed_count": len(closed_items) + len(closed_long),
        "capital": capital,
        "start_date": start_date.isoformat(),
        "as_of": as_of.isoformat(),
        "elapsed_days": elapsed_days,
        "final_date": final_date.isoformat(),
        "remaining_days_to_last": remaining_days,
        "horizon_days": horizon_days,
        "closed_realized_profit": closed_profit,
        "closed_valued_count": closed_valued_count,
        "open_current_profit": open_current_profit,
        "open_current_count": open_current_count,
        "open_expected_profit": open_expected_profit,
        "open_expected_count": open_expected_count,
        "current_profit": current_profit,
        "all_offset_and_sell_profit": all_offset_and_sell_profit,
        "all_offset_and_sell_percent": (
            all_offset_and_sell_profit / capital * 100 if capital > 0 else None
        ),
        "all_offset_and_sell_scaled": scaled(
            all_offset_and_sell_profit, elapsed_days
        ),
        "open_all_offset_and_sell_profit": open_liquidation_profit,
        "open_all_offset_and_sell_count": open_liquidation_count,
        "all_offset_and_sell_unavailable_count": (
            len(open_items) - open_liquidation_count
        ),
        "final_profit": final_profit,
        "current_unavailable_count": len(open_items) - open_current_count,
        "expected_unavailable_count": len(open_items) - open_expected_count,
        "recognized_to_final_percent": (
            current_profit / final_profit * 100.0 if final_profit != 0 else None
        ),
        "current_scaled": scaled(current_profit, elapsed_days),
        "final_scaled": scaled(final_profit, horizon_days),
        "covered_call": {
            "option_only_profit": closed_profit + open_option_profit,
            "with_underlying_profit": current_profit,
            "all_offset_and_sell_profit": all_offset_and_sell_profit,
            "all_offset_and_sell_scaled": scaled(
                all_offset_and_sell_profit, elapsed_days
            ),
            "closed_profit": closed_profit,
            "open_option_profit": open_option_profit,
            "open_with_underlying_profit": open_current_profit,
            "option_only_scaled": scaled(closed_profit + open_option_profit, elapsed_days),
            "with_underlying_scaled": scaled(current_profit, elapsed_days),
        },
        "long_call": {
            "option_only_profit": closed_long_profit + open_long_premium,
            "with_underlying_profit": (
                closed_long_profit + open_long_exercise + post_exercise_profit
            ),
            "closed_profit": closed_long_profit,
            "open_premium_profit": open_long_premium,
            "open_exercise_profit": open_long_exercise,
            "post_exercise_base_profit": post_exercise_profit,
            "option_only_scaled": scaled(closed_long_profit + open_long_premium, elapsed_days),
            "with_underlying_scaled": scaled(
                closed_long_profit + open_long_exercise + post_exercise_profit,
                elapsed_days,
            ),
            "open_premium_valued_count": open_long_premium_count,
            "open_exercise_valued_count": open_long_exercise_count,
            "closed_valued_count": closed_long_count,
            "post_exercise_valued_count": post_exercise_count,
        },
        "combined": {
            "option_only_profit": option_only_profit,
            "with_underlying_profit": with_underlying_profit,
            "option_only_scaled": scaled(option_only_profit, elapsed_days),
            "with_underlying_scaled": scaled(with_underlying_profit, elapsed_days),
        },
        "underlying_positions": underlying_positions,
        "details": details,
    }


def build_account_growth(
    trades: list[dict], *, as_of: date, initial_capital: float | None = None,
    underlying_positions: list[dict] | None = None,
) -> dict:
    """Build an event-based cumulative P/L series for the trades dashboard.

    Closed trades affect the curve on their exit date. Open trades are marked
    to market only at the current point because historical daily valuations are
    not stored. Entry dates are retained as zero-delta events so the chart shows
    the actual account activity timeline without inventing daily observations.
    """
    events: dict[str, dict[str, float | int]] = {}

    def finite(value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def event(day_value: str) -> dict[str, float | int]:
        return events.setdefault(
            day_value, {"entries": 0, "exits": 0, "realized_delta": 0.0}
        )

    invested_capital = 0.0
    open_mark_profit = 0.0
    valued_open_count = 0
    capital_events: dict[str, dict[str, float]] = {}
    holding_days = {"all": [], "covered_call": [], "long_call": [], "underlying": []}
    base_items = []
    for position in underlying_positions or []:
        if position.get("portfolio_excluded"):
            continue
        if position.get("status") != "closed" and float(position.get("available_quantity") or 0) <= 0:
            continue
        base_items.append({
            **position, "strategy_type":"underlying",
            "realized_profit": position.get("profit") if position.get("status") == "closed" else None,
            "total_profit": position.get("profit") if position.get("status") != "closed" else None,
        })
    portfolio_items = list(trades) + base_items
    for item in portfolio_items:
        capital = finite(item.get("invested_capital"))
        if capital is not None and capital > 0:
            invested_capital += capital
        entry_date = str(item.get("entry_date") or "")
        try:
            date.fromisoformat(entry_date)
        except ValueError:
            entry_date = ""
        if entry_date:
            event(entry_date)["entries"] += 1
            if capital is not None and capital > 0:
                capital_event = capital_events.setdefault(entry_date, {"in": 0.0, "out": 0.0})
                capital_event["in"] += capital

        holding_end = as_of
        if item.get("status") == "closed":
            try:
                holding_end = date.fromisoformat(str(item.get("exit_date") or ""))
            except ValueError:
                holding_end = as_of
        try:
            holding_start = date.fromisoformat(entry_date)
            duration = max(0, (holding_end - holding_start).days)
            strategy_key = "long_call" if item.get("strategy_type") == "long_call" else "underlying" if item.get("strategy_type") == "underlying" else "covered_call"
            holding_days["all"].append(duration)
            holding_days[strategy_key].append(duration)
        except ValueError:
            pass

        if item.get("status") == "closed":
            exit_date = str(item.get("exit_date") or "")
            realized = finite(item.get("realized_profit"))
            try:
                date.fromisoformat(exit_date)
            except ValueError:
                exit_date = ""
            if exit_date and realized is not None:
                target = event(exit_date)
                target["exits"] += 1
                target["realized_delta"] += realized
            if exit_date and capital is not None and capital > 0:
                capital_event = capital_events.setdefault(exit_date, {"in": 0.0, "out": 0.0})
                capital_event["out"] += capital
            continue

        if item.get("strategy_type") == "long_call":
            mark_profit = finite(item.get("long_combined_profit"))
            if mark_profit is None:
                mark_profit = finite(item.get("premium_profit"))
        else:
            mark_profit = finite(item.get("total_profit"))
        if mark_profit is not None:
            open_mark_profit += mark_profit
            valued_open_count += 1

    deployed = 0.0
    inferred_initial_capital = 0.0
    for day_value in sorted(capital_events):
        deployed += capital_events[day_value]["in"]
        inferred_initial_capital = max(inferred_initial_capital, deployed)
        deployed -= capital_events[day_value]["out"]

    explicit_initial = finite(initial_capital)
    if explicit_initial is not None and explicit_initial <= 0:
        explicit_initial = None
    account_initial = explicit_initial or inferred_initial_capital
    capital_source = "user" if explicit_initial is not None else "estimated"

    cumulative = 0.0
    points = []
    for day_value in sorted(events):
        item = events[day_value]
        cumulative += float(item["realized_delta"])
        points.append({
            "date": day_value,
            "value": cumulative,
            "equity": account_initial + cumulative,
            **item,
        })

    current_date = as_of.isoformat()
    total_profit = cumulative + open_mark_profit
    if points and points[-1]["date"] == current_date:
        points[-1]["value"] = total_profit
        points[-1]["equity"] = account_initial + total_profit
        points[-1]["open_mark"] = open_mark_profit
        points[-1]["is_current"] = True
    else:
        points.append({
            "date": current_date,
            "value": total_profit,
            "equity": account_initial + total_profit,
            "entries": 0,
            "exits": 0,
            "realized_delta": 0.0,
            "open_mark": open_mark_profit,
            "is_current": True,
        })

    equity_values = [float(point["equity"]) for point in points]
    peak = None
    peak_date = None
    max_drawdown_percent = 0.0
    max_drawdown_amount = 0.0
    drawdown_peak_date = None
    drawdown_trough_date = None
    for point, equity in zip(points, equity_values):
        if peak is None or equity > peak:
            peak = equity
            peak_date = point["date"]
        if peak and peak > 0:
            amount = peak - equity
            percent = amount / peak * 100.0
            if percent > max_drawdown_percent:
                max_drawdown_percent = percent
                max_drawdown_amount = amount
                drawdown_peak_date = peak_date
                drawdown_trough_date = point["date"]

    valid_entry_dates = []
    for item in portfolio_items:
        try:
            valid_entry_dates.append(date.fromisoformat(str(item.get("entry_date") or "")))
        except ValueError:
            pass
    tracking_days = max(1, (as_of - min(valid_entry_dates)).days) if valid_entry_dates else 0
    return_percent = total_profit / account_initial * 100.0 if account_initial > 0 else None
    average_monthly_return = average_annual_return = None
    if return_percent is not None and tracking_days > 0 and 1 + return_percent / 100.0 > 0:
        growth_factor = 1 + return_percent / 100.0
        average_monthly_return = (growth_factor ** (365.0 / tracking_days / 12.0) - 1) * 100.0
        average_annual_return = (growth_factor ** (365.0 / tracking_days) - 1) * 100.0

    def average(values: list[int]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "points": points,
        "realized_profit": cumulative,
        "open_mark_profit": open_mark_profit,
        "total_profit": total_profit,
        "invested_capital": invested_capital,
        "initial_capital": account_initial,
        "initial_capital_source": capital_source,
        "inferred_initial_capital": inferred_initial_capital,
        "current_equity": account_initial + total_profit,
        "return_percent": return_percent,
        "average_monthly_return_percent": average_monthly_return,
        "average_annual_return_percent": average_annual_return,
        "tracking_days": tracking_days,
        "max_drawdown_percent": max_drawdown_percent,
        "max_drawdown_amount": max_drawdown_amount,
        "max_drawdown_peak_date": drawdown_peak_date,
        "max_drawdown_trough_date": drawdown_trough_date,
        # This curve contains recorded trade/cash-flow events plus the current
        # mark.  It is intentionally not described as daily MDD: no daily mark
        # series exists from which an intra-event drawdown could be observed.
        "drawdown_method": "observed_event_points",
        "drawdown_scope_label": "افت سرمایه در نقاط ثبت‑شده",
        "drawdown_is_daily": False,
        "drawdown_observation_count": len(points),
        "drawdown_limitation": (
            "این شاخص فقط از نقاط ثبت‑شده ورود، خروج و ارزش‌گذاری جاری "
            "محاسبه می‌شود و افت روزانه بین این نقاط را نشان نمی‌دهد."
        ),
        "average_holding_days": average(holding_days["all"]),
        "average_holding_days_covered_call": average(holding_days["covered_call"]),
        "average_holding_days_long_call": average(holding_days["long_call"]),
        "average_holding_days_underlying": average(holding_days["underlying"]),
        "valued_open_count": valued_open_count,
        "open_count": sum(1 for item in trades if item.get("status") != "closed"),
        "closed_count": sum(1 for item in trades if item.get("status") == "closed"),
    }


class AccountStore:
    """Persist user-entered portfolio settings beside the trades file."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def read(self) -> dict:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {"initial_capital": None, "cash_balance": None}
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("تنظیمات حساب قابل خواندن نیست") from exc
            return payload if isinstance(payload, dict) else {
                "initial_capital": None, "cash_balance": None,
            }

    def save(self, initial_capital, cash_balance=None) -> dict:
        value = None
        if initial_capital not in (None, ""):
            value = _number(initial_capital, minimum=0.0000001)
        cash = None
        if cash_balance not in (None, ""):
            cash = _number(cash_balance, minimum=0)
        payload = {"initial_capital": value, "cash_balance": cash}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
        return payload


def calculate_underlying_snapshot(
    position: dict, quote: dict | None, *, as_of: date, allocated_quantity: float = 0,
) -> dict:
    entry_date = parse_user_date(position["entry_date"])
    quantity = _number(position.get("quantity"), minimum=0.0000001)
    entry_price = _number(position.get("entry_price"), minimum=0.0000001)
    market = str(position.get("market") or (quote or {}).get("market") or "tehran")
    commission = _number(position.get("commission", 0), minimum=0)
    commission_source = str(position.get("commission_source") or "").strip()
    if commission_source not in {"actual", "estimated"}:
        # Preserve the historical fallback only for legacy closed rows that
        # predate provenance metadata. New records always persist a source.
        commission_source = (
            "estimated"
            if position.get("status") == "closed" and commission <= 0
            else "actual"
        )
    commission_was_estimated = commission_source == "estimated"
    if commission_was_estimated and commission <= 0:
        commission = _estimated_commission(market, "underlying_buy", entry_price, quantity)
    allocated = max(0.0, min(quantity, float(allocated_quantity or 0)))
    available = max(0.0, quantity - allocated)
    closed = position.get("status") == "closed"
    current_price = (
        _number(position.get("exit_price"), minimum=0.0000001)
        if closed else _number((quote or {}).get("last"), minimum=0.0000001)
        if (quote or {}).get("last") is not None else None
    )
    valuation_date = parse_user_date(position["exit_date"]) if closed else as_of
    valued_quantity = quantity if closed else available
    allocated_commission = commission * valued_quantity / quantity if quantity > 0 else 0
    invested_capital = entry_price * valued_quantity + allocated_commission
    exit_commission = _number(position.get("exit_commission", 0), minimum=0) if closed else 0
    exit_commission_source = str(position.get("exit_commission_source") or "").strip()
    if exit_commission_source not in {"actual", "estimated"}:
        exit_commission_source = "estimated" if closed and exit_commission <= 0 else "actual"
    exit_commission_was_estimated = bool(closed and exit_commission_source == "estimated")
    if exit_commission_was_estimated and exit_commission <= 0 and current_price is not None:
        exit_commission = _estimated_commission(market, "underlying_sell", current_price, quantity)
    profit = (
        (current_price - entry_price) * valued_quantity
        - allocated_commission
        - exit_commission
        if current_price is not None else None
    )
    days = max(1,(valuation_date-entry_date).days)
    percent = profit / invested_capital * 100 if profit is not None and invested_capital > 0 else None
    result = {
        **position,
        "market": (
            (quote or {}).get("market")
            if not closed and (quote or {}).get("market")
            else position.get("market")
        ),
        "entry_date_display": format_jalali_date(entry_date),
        "exit_date_display": format_jalali_date(valuation_date) if closed else None,
        "valuation_date_display": format_jalali_date(valuation_date),
        "current_price": current_price,
        "best_bid": (quote or {}).get("bid"), "best_ask": (quote or {}).get("ask"),
        "last_is_previous_day": bool((quote or {}).get("last_is_previous_day")),
        "allocated_quantity": allocated, "available_quantity": available,
        "valued_quantity": valued_quantity, "invested_capital": invested_capital,
        "commission": commission, "commission_source": commission_source,
        "exit_commission": exit_commission,
        "exit_commission_source": exit_commission_source if closed else position.get("exit_commission_source"),
        "realized_commission": commission + exit_commission if closed else None,
        "commission_auto_calculated": commission_was_estimated,
        "exit_commission_auto_calculated": exit_commission_was_estimated,
        "profit": profit, "profit_percent": percent,
        "profit_yoy": percent * 365 / days if percent is not None else None,
        "holding_days": days,
        "data_status": "closed" if closed else "live" if current_price is not None else "quote_unavailable",
    }
    if int(position.get("calculation_version") or LEGACY_CALCULATION_VERSION) >= 8:
        money = dict(position.get("money_values") or {})
        entry_exact = _money_decimal(position, "entry_price")
        commission_exact = _money_decimal(
            position, "commission", commission
        )
        quantity_exact = exact_decimal(
            position.get("quantity"), name="quantity"
        )
        allocated_exact = min(
            quantity_exact,
            max(
                Decimal("0"),
                exact_decimal(allocated_quantity or 0, name="allocated_quantity"),
            ),
        )
        valued_exact = quantity_exact if closed else quantity_exact - allocated_exact
        allocated_commission_exact = (
            commission_exact * valued_exact / quantity_exact
        )
        invested_exact = entry_exact * valued_exact + allocated_commission_exact
        result["invested_capital"] = float(invested_exact)
        money["entry_price"] = decimal_text(entry_exact)
        money["commission"] = decimal_text(commission_exact)
        money["invested_capital"] = decimal_text(invested_exact)
        exit_commission_exact = _money_decimal(
            position, "exit_commission", exit_commission
        )
        if result.get("exit_commission") is not None:
            result["exit_commission"] = float(exit_commission_exact)
            money["exit_commission"] = decimal_text(exit_commission_exact)
        if result.get("realized_commission") is not None:
            realized_exact = commission_exact + exit_commission_exact
            result["realized_commission"] = float(realized_exact)
            money["realized_commission"] = decimal_text(realized_exact)
        if current_price is not None:
            raw_current_price = (
                position.get("money_values", {}).get("exit_price")
                if closed and isinstance(position.get("money_values"), dict)
                else position.get("exit_price") if closed
                else (quote or {}).get("last")
            )
            current_exact = exact_decimal(
                raw_current_price
                if raw_current_price not in (None, "")
                else current_price,
                name="current_price",
            )
            profit_exact = (
                (current_exact - entry_exact) * valued_exact
                - allocated_commission_exact
                - exit_commission_exact
            )
            result["profit"] = float(profit_exact)
            money["profit"] = decimal_text(profit_exact)
        result["money_schema_version"] = 1
        result["money_values"] = money
    return result


def summarize_underlying_positions(positions: list[dict], *, closed: bool = False) -> dict:
    items = [
        item for item in positions
        if (item.get("status") == "closed") == closed
        and not item.get("portfolio_excluded")
    ]
    if not closed:
        items = [item for item in items if float(item.get("available_quantity") or 0) > 0]
    capital = sum(float(item.get("invested_capital") or 0) for item in items)
    profit = sum(float(item.get("profit") or 0) for item in items if item.get("profit") is not None)
    return {
        "count": len(items), "invested_capital": capital, "profit": profit,
        "profit_percent": profit / capital * 100 if capital > 0 else None,
        "valued_count": sum(1 for item in items if item.get("profit") is not None),
    }


def underlying_allocations(trades: list[dict]) -> dict[str,float]:
    allocations: dict[str,float] = {}
    for trade in trades:
        position_id = str(trade.get("underlying_position_id") or "")
        if not position_id or trade.get("status") == "closed" or trade.get("strategy_type") != "covered_call":
            continue
        units = trade_underlying_units(trade)
        allocations[position_id] = allocations.get(position_id,0.0) + units
    return allocations


def build_portfolio_asset_ledger(
    trades: list[dict], underlying_positions: list[dict] | None = None, *,
    cash_balance: float | None = None,
) -> dict:
    """Build a read-only allocation view without changing portfolio profit.

    Linked covered calls receive their collateral from the underlying-position
    allocation.  Older imported covered calls have no position link, so their
    own confirmed base entry price and quantity are used as a display-only
    collateral lot.  The returned base-price P/L is explanatory and must not
    be added to ``summarize_open_trades`` because covered-call P/L already
    contains the same underlying movement.
    """

    def finite(value, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    rows_by_key: dict[str, dict] = {}

    def ensure_row(market, asset) -> dict:
        key = underlying_quote_key(market, asset)
        if key not in rows_by_key:
            rows_by_key[key] = {
                "key": key,
                "market": str(market or "tehran"),
                "asset": str(asset or "نامشخص"),
                "base_lot_count": 0,
                "covered_call_count": 0,
                "legacy_collateral_trade_count": 0,
                "long_call_count": 0,
                "long_call_quantity": 0.0,
                "long_call_cost": 0.0,
                "free_quantity": 0.0,
                "collateral_quantity": 0.0,
                "free_cost": 0.0,
                "collateral_cost": 0.0,
                "free_current_value": 0.0,
                "collateral_current_value": 0.0,
                "free_price_profit": 0.0,
                "collateral_price_profit": 0.0,
                "valued_free_cost": 0.0,
                "valued_collateral_cost": 0.0,
                "valued_free_quantity": 0.0,
                "valued_collateral_quantity": 0.0,
            }
        return rows_by_key[key]

    for position in underlying_positions or []:
        if position.get("status") == "closed" or position.get("portfolio_excluded"):
            continue
        free_quantity = max(0.0, finite(position.get("available_quantity")))
        collateral_quantity = max(0.0, finite(position.get("allocated_quantity")))
        active_quantity = free_quantity + collateral_quantity
        if active_quantity <= 0:
            continue
        quantity = max(active_quantity, finite(position.get("quantity")), 1.0)
        entry_price = max(0.0, finite(position.get("entry_price")))
        commission_per_unit = max(0.0, finite(position.get("commission"))) / quantity
        row = ensure_row(position.get("market"), position.get("asset"))
        row["base_lot_count"] += 1
        row["free_quantity"] += free_quantity
        row["collateral_quantity"] += collateral_quantity
        row["free_cost"] += free_quantity * (entry_price + commission_per_unit)
        row["collateral_cost"] += collateral_quantity * (
            entry_price + commission_per_unit
        )
        current_raw = position.get("current_price")
        current_price = finite(current_raw) if current_raw is not None else None
        if current_price is not None:
            row["free_current_value"] += free_quantity * current_price
            row["collateral_current_value"] += collateral_quantity * current_price
            row["free_price_profit"] += (current_price - entry_price) * free_quantity
            row["collateral_price_profit"] += (
                current_price - entry_price
            ) * collateral_quantity
            row["valued_free_cost"] += entry_price * free_quantity
            row["valued_collateral_cost"] += entry_price * collateral_quantity
            row["valued_free_quantity"] += free_quantity
            row["valued_collateral_quantity"] += collateral_quantity

    open_trades = [item for item in trades if item.get("status") != "closed"]
    for trade in open_trades:
        strategy = str(trade.get("strategy_type") or "covered_call")
        row = ensure_row(trade.get("market"), trade.get("asset"))
        if strategy == "long_call":
            row["long_call_count"] += 1
            row["long_call_quantity"] += max(0.0, finite(trade.get("quantity")))
            row["long_call_cost"] += max(0.0, finite(trade.get("invested_capital")))
            continue
        if strategy != "covered_call":
            continue
        row["covered_call_count"] += 1
        if str(trade.get("underlying_position_id") or "").strip():
            continue
        quantity = max(0.0, trade_underlying_units(trade))
        entry_price = max(0.0, finite(trade.get("entry_base_price")))
        if quantity <= 0 or entry_price <= 0:
            continue
        # Legacy imports predate the base-position link.  Their confirmed
        # trade inputs are still the authoritative collateral source.
        cost = quantity * entry_price
        row["legacy_collateral_trade_count"] += 1
        row["collateral_quantity"] += quantity
        row["collateral_cost"] += cost
        current_raw = trade.get("current_base_price")
        current_price = finite(current_raw) if current_raw is not None else None
        if current_price is not None:
            row["collateral_current_value"] += quantity * current_price
            row["collateral_price_profit"] += (
                current_price - entry_price
            ) * quantity
            row["valued_collateral_cost"] += cost
            row["valued_collateral_quantity"] += quantity

    rows = []
    for row in rows_by_key.values():
        base_quantity = row["free_quantity"] + row["collateral_quantity"]
        base_cost = row["free_cost"] + row["collateral_cost"]
        row.update({
            "base_quantity": base_quantity,
            "base_cost": base_cost,
            "base_current_value": (
                row["free_current_value"] + row["collateral_current_value"]
            ),
            "free_average_cost": (
                row["free_cost"] / row["free_quantity"]
                if row["free_quantity"] > 0 else None
            ),
            "collateral_average_cost": (
                row["collateral_cost"] / row["collateral_quantity"]
                if row["collateral_quantity"] > 0 else None
            ),
            "free_price_profit_percent": (
                row["free_price_profit"] / row["valued_free_cost"] * 100
                if row["valued_free_cost"] > 0 else None
            ),
            "collateral_price_profit_percent": (
                row["collateral_price_profit"]
                / row["valued_collateral_cost"] * 100
                if row["valued_collateral_cost"] > 0 else None
            ),
        })
        rows.append(row)
    rows.sort(
        key=lambda item: (
            -float(item["base_cost"] + item["long_call_cost"]),
            normalize_fa(item["asset"]),
        )
    )

    free_cost = sum(float(item["free_cost"]) for item in rows)
    collateral_cost = sum(float(item["collateral_cost"]) for item in rows)
    base_cost = free_cost + collateral_cost
    free_price_profit = sum(float(item["free_price_profit"]) for item in rows)
    collateral_price_profit = sum(
        float(item["collateral_price_profit"]) for item in rows
    )
    valued_free_cost = sum(float(item["valued_free_cost"]) for item in rows)
    valued_collateral_cost = sum(
        float(item["valued_collateral_cost"]) for item in rows
    )
    long_call_cost = sum(float(item["long_call_cost"]) for item in rows)
    cash = max(0.0, finite(cash_balance))
    return {
        "cash": cash,
        "base": {
            "cost": base_cost,
            "current_value": sum(float(item["base_current_value"]) for item in rows),
            "quantity": sum(float(item["base_quantity"]) for item in rows),
            "asset_count": sum(1 for item in rows if item["base_quantity"] > 0),
            "free_share_percent": free_cost / base_cost * 100 if base_cost > 0 else 0.0,
            "collateral_share_percent": (
                collateral_cost / base_cost * 100 if base_cost > 0 else 0.0
            ),
        },
        "free": {
            "cost": free_cost,
            "quantity": sum(float(item["free_quantity"]) for item in rows),
            "asset_count": sum(1 for item in rows if item["free_quantity"] > 0),
            "current_value": sum(float(item["free_current_value"]) for item in rows),
            "price_profit": free_price_profit,
            "price_profit_percent": (
                free_price_profit / valued_free_cost * 100
                if valued_free_cost > 0 else None
            ),
        },
        "collateral": {
            "cost": collateral_cost,
            "quantity": sum(float(item["collateral_quantity"]) for item in rows),
            "asset_count": sum(
                1 for item in rows if item["collateral_quantity"] > 0
            ),
            "current_value": sum(
                float(item["collateral_current_value"]) for item in rows
            ),
            "price_profit": collateral_price_profit,
            "price_profit_percent": (
                collateral_price_profit / valued_collateral_cost * 100
                if valued_collateral_cost > 0 else None
            ),
            "covered_call_count": sum(
                int(item["covered_call_count"]) for item in rows
            ),
            "legacy_trade_count": sum(
                int(item["legacy_collateral_trade_count"]) for item in rows
            ),
        },
        "long_calls": {
            "cost": long_call_cost,
            "quantity": sum(float(item["long_call_quantity"]) for item in rows),
            "trade_count": sum(int(item["long_call_count"]) for item in rows),
        },
        "tracked_total_cost": cash + base_cost + long_call_cost,
        "profit_policy": "collateral_base_profit_is_informational_only",
        "rows": rows,
    }


def validate_underlying_link(payload: dict, positions: list[dict], trades: list[dict], quote: dict, *, editing_trade_id: str | None = None) -> None:
    if str(payload.get("strategy_type") or "covered_call") != "covered_call":
        return
    position_id = str(payload.get("underlying_position_id") or "").strip()
    if not position_id:
        return  # Backward-compatible imports remain valid; the UI requires a link.
    position = next((item for item in positions if item.get("id") == position_id and item.get("status") != "closed"),None)
    if position is None: raise ValueError("دارایی پایه انتخاب‌شده پیدا نشد")
    if underlying_quote_key(position.get("market"),position.get("asset")) != underlying_quote_key(payload.get("market"),payload.get("asset") or quote.get("asset")):
        raise ValueError("دارایی پایه انتخاب‌شده با قرارداد کاوردکال یکسان نیست")
    relevant = [item for item in trades if item.get("id") != editing_trade_id]
    allocated = underlying_allocations(relevant).get(position_id,0.0)
    required = trade_underlying_units(
        payload, contract_size=quote.get("contract_size", 1)
    )
    available = _number(position.get("quantity"),minimum=0.0000001) - allocated
    if required > available + 1e-9:
        raise ValueError(f"موجودی آزاد دارایی پایه کافی نیست؛ موجودی آزاد {available:g} واحد است")


def validate_underlying_position_change(
    position_id: str, payload: dict | None, positions: list[dict],
    trades: list[dict], *, deleting: bool = False,
) -> None:
    """Protect base lots that are currently collateral for covered calls."""
    allocated = underlying_allocations(trades).get(str(position_id), 0.0)
    if deleting and allocated > 0:
        raise ValueError("این دارایی پایه به کاوردکال باز متصل است و فعلاً قابل حذف نیست")
    if not deleting and allocated > 0:
        current = next((item for item in positions if item.get("id") == position_id), None)
        if current is None:
            raise KeyError("دارایی پایه پیدا نشد")
        new_quantity = _number(
            (payload or {}).get("quantity", current.get("quantity")),
            minimum=0.0000001,
        )
        if new_quantity + 1e-9 < allocated:
            raise ValueError(
                f"تعداد دارایی پایه نمی‌تواند کمتر از {allocated:g} واحد تخصیص‌یافته باشد"
            )


def exercise_underlying_terms(trade: dict) -> dict:
    """Build an underlying cost basis from a long-call trade.

    The strike is discounted over the actual purchase-to-exercise interval,
    then the paid premium is added to produce the acquired asset cost basis.
    """
    if trade.get("strategy_type") != "long_call":
        raise ValueError("معامله انتخابی باید از نوع خرید اختیار خرید باشد")
    quantity = _number(trade.get("quantity"), minimum=0.0000001)
    exercise_quantity = float(trade.get("exercise_quantity") or 0)
    if trade.get("status") != "closed" or trade.get("exit_method") not in {
        "exercise", "mixed",
    }:
        raise ValueError("فقط معامله بسته‌شده‌ای که تمام یا بخشی از آن اعمال شده قابل تبدیل است")
    contracts = exercise_quantity or quantity
    contract_size = _number(trade.get("contract_size", 1), minimum=0.0000001)
    units = trade_underlying_units(trade, contracts)
    strike = _number(trade.get("strike"), minimum=0.0000001)
    premium = _number(trade.get("entry_premium"), minimum=0)
    annual_rate = _number(trade.get("annual_interest_rate", 40), minimum=0)
    try:
        entry_date = parse_user_date(str(trade.get("entry_date") or ""))
        exercise_date = parse_user_date(str(trade.get("exit_date") or ""))
        days = max(0, (exercise_date - entry_date).days)
    except (TypeError, ValueError):
        raise ValueError("تاریخ خرید و تاریخ اعمال معامله باید معتبر باشند")
    annual_rate_decimal = annual_rate / 100
    calculation_version = int(
        trade.get("calculation_version") or LEGACY_CALCULATION_VERSION
    )
    if calculation_version >= CANONICAL_CALCULATION_VERSION:
        period_rate = annual_rate_decimal * days / 365
        interest_adjustment = strike * period_rate
        adjusted_strike = strike - interest_adjustment
        discount_factor = 1 + period_rate
        interest_convention = "simple"
        interest_day_count = "ACT/365"
    else:
        discount_factor = (1 + annual_rate_decimal) ** (days / 365)
        adjusted_strike = strike / discount_factor
        period_rate = discount_factor - 1
        interest_adjustment = strike - adjusted_strike
        interest_convention = "compound_legacy"
        interest_day_count = "ACT/365"
    adjusted_entry_price = adjusted_strike + premium
    if adjusted_entry_price <= 0:
        raise ValueError("قیمت ورود تعدیل‌شده حاصل از معامله معتبر نیست")
    entry_base = _number(trade.get("entry_base_price"), minimum=0.0000001)
    relative_advantage = (entry_base - adjusted_entry_price) / entry_base * 100
    return {
        "market": str(trade.get("market") or ""),
        "asset": str(trade.get("asset") or ""),
        "quantity": units,
        "entry_price": adjusted_entry_price,
        "source_option_symbol": str(trade.get("option_symbol") or ""),
        "source_contracts": contracts,
        "source_contract_size": contract_size,
        "annual_interest_rate": annual_rate,
        "interest_period_days": days,
        "period_interest_rate": period_rate,
        "interest_convention": interest_convention,
        "interest_day_count": interest_day_count,
        "adjusted_strike": adjusted_strike,
        "risk_free_interest_adjustment": interest_adjustment,
        "relative_advantage_percent": relative_advantage,
    }


def prepare_underlying_payload(payload: dict, trades: list[dict]) -> dict:
    """Validate and enrich exercise-based underlying form submissions."""
    prepared = dict(payload)
    method = str(prepared.get("acquisition_method") or "direct").strip()
    mode = str(prepared.get("exercise_entry_mode") or "manual").strip()
    if method != "exercise":
        prepared["exercise_entry_mode"] = "manual"
        prepared["source_trade_id"] = None
        return prepared
    if mode not in {"trade", "manual"}:
        raise ValueError("روش ورود اطلاعات اعمال معتبر نیست")
    prepared["exercise_entry_mode"] = mode
    if mode == "manual":
        prepared["source_trade_id"] = None
        return prepared
    source_id = str(prepared.get("source_trade_id") or "").strip()
    source = next((item for item in trades if str(item.get("id")) == source_id), None)
    if not source:
        raise ValueError("معامله اختیار خرید انتخابی پیدا نشد")
    if source.get("status") != "closed" or source.get("exit_method") not in {
        "exercise", "mixed",
    } or float(source.get("exercise_quantity") or 0) <= 0:
        raise ValueError("معامله انتخابی باید بسته شده و دارای تعداد اعمال‌شده باشد")
    prepared.update(exercise_underlying_terms(source))
    prepared["source_trade_id"] = source_id
    return prepared


class UnderlyingPositionStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()

    def _read(self) -> list[dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError,json.JSONDecodeError) as exc:
            raise RuntimeError("فایل دارایی‌های پایه قابل خواندن نیست") from exc
        return payload if isinstance(payload,list) else []

    def _write(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix+".tmp")
        temporary.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")
        temporary.replace(self.path)

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._read()]

    def create(self, payload: dict) -> dict:
        market = str(payload.get("market") or "").strip()
        asset = str(payload.get("asset") or "").strip()
        if canonical_asset(asset, ""):
            market = "goods"
        method = str(payload.get("acquisition_method") or "direct").strip()
        if market not in {"tehran","goods"} or not asset or method not in {"direct","exercise"}:
            raise ValueError("بازار، دارایی پایه و روش خرید معتبر نیست")
        entry_date = parse_user_date(str(payload.get("entry_date") or ""))
        if entry_date > tehran_today() + timedelta(days=ENTRY_DATE_GRACE_DAYS):
            raise ValueError("تاریخ خرید دارایی پایه نمی‌تواند بعد از امروز باشد")
        entry_price = _number(payload.get("entry_price"),minimum=0.0000001)
        quantity = _number(payload.get("quantity"),minimum=0.0000001)
        commission, commission_source = _commission_value(
            payload.get("commission"),
            estimate=lambda: _estimated_commission(
                market,
                "underlying_buy",
                entry_price,
                quantity,
                as_of=entry_date,
            ),
        )
        if payload.get("commission_source") in {"actual", "estimated"}:
            commission_source = str(payload["commission_source"])
        item = {
            "id":uuid4().hex,"status":"open","market":market,"asset":asset,
            "acquisition_method":method,"entry_date":entry_date.isoformat(),
            "entry_price":entry_price,
            "quantity":quantity,
            "commission":commission,
            "commission_source":commission_source,
            "source_trade_id":str(payload.get("source_trade_id") or "").strip() or None,
            "exercise_entry_mode":str(payload.get("exercise_entry_mode") or "manual"),
        }
        if payload.get("quantity_kind") == "unit":
            item["quantity_kind"] = "unit"
        if payload.get("currency_unit") in {"rial", "toman"}:
            item["currency_unit"] = payload["currency_unit"]
        if payload.get("calculation_version") not in (None, ""):
            item["calculation_version"] = int(payload["calculation_version"])
        if int(item.get("calculation_version") or LEGACY_CALCULATION_VERSION) >= 8:
            item["currency_unit"] = validate_currency_contract(
                currency_unit=item.get("currency_unit") or CURRENCY_RIAL,
                calculation_version=item["calculation_version"],
            )
            commission_schedule = resolve_commission_rate(
                market=market,
                kind="underlying_buy",
                as_of=entry_date,
            )
            item["quantity_kind"] = QUANTITY_UNIT
            item["money_schema_version"] = 1
            item["commission_schedule_source"] = commission_schedule.source
            item["commission_schedule_version"] = commission_schedule.version
            item["commission_schedule_effective_from"] = (
                commission_schedule.effective_from.isoformat()
            )
            item["commission_rounding_mode"] = commission_schedule.rounding_mode
            item["commission_rounding_increment"] = decimal_text(
                commission_schedule.rounding_increment
            )
            item["commission_rounding_version"] = (
                commission_schedule.rounding_version
            )
            item["money_values"] = _captured_money_values(payload, {
                "entry_price": entry_price,
                "commission": commission,
            })
        for key in ("source_option_symbol","source_contracts","source_contract_size",
                    "annual_interest_rate","interest_period_days","period_interest_rate",
                    "adjusted_strike","risk_free_interest_adjustment","relative_advantage_percent",
                    "suggested_price","suggested_price_fetched_at","confirmed_price",
                    "price_confirmed_at"):
            if payload.get(key) not in (None, ""):
                item[key] = payload.get(key)
        with self._lock:
            items=self._read()
            if item.get("source_trade_id") and any(
                existing.get("source_trade_id") == item["source_trade_id"]
                and existing.get("acquisition_method") == "exercise"
                for existing in items
            ):
                raise ValueError("دارایی حاصل از این معامله اختیار خرید قبلاً ثبت شده است")
            items.append(item); self._write(items)
        return dict(item)

    def update(self, position_id: str, payload: dict) -> dict:
        with self._lock:
            items=self._read()
            existing=next((item for item in items if item.get("id")==position_id),None)
        if existing is None: raise KeyError("دارایی پایه پیدا نشد")
        # Validate through a temporary in-memory record without writing it.
        market=str(payload.get("market") or existing.get("market") or "").strip()
        asset=str(payload.get("asset") or existing.get("asset") or "").strip()
        if canonical_asset(asset, ""):
            market="goods"
        method=str(payload.get("acquisition_method") or existing.get("acquisition_method") or "direct").strip()
        entry_date=parse_user_date(str(payload.get("entry_date") or existing.get("entry_date") or ""))
        entry_price = _number(payload.get("entry_price",existing.get("entry_price")),minimum=0.0000001)
        quantity = _number(payload.get("quantity",existing.get("quantity")),minimum=0.0000001)
        if "commission" in payload:
            commission, commission_source = _commission_value(
                payload.get("commission"),
                estimate=lambda: _estimated_commission(
                    market, "underlying_buy", entry_price, quantity
                ),
            )
            if payload.get("commission_source") in {"actual", "estimated"}:
                commission_source = str(payload["commission_source"])
        else:
            commission = _number(existing.get("commission", 0), minimum=0)
            commission_source = str(existing.get("commission_source") or "actual")
        updated={**existing,"market":market,"asset":asset,"acquisition_method":method,
            "entry_date":entry_date.isoformat(),"entry_price":entry_price,
            "quantity":quantity,"commission":commission,
            "commission_source":commission_source}
        if int(updated.get("calculation_version") or LEGACY_CALCULATION_VERSION) >= 8:
            updated["money_schema_version"] = 1
            updated["money_values"] = _captured_money_values(
                {**existing, **payload},
                {"entry_price": entry_price, "commission": commission},
            )
        updated["source_trade_id"] = str(payload.get("source_trade_id") or "").strip() or None
        updated["exercise_entry_mode"] = str(payload.get("exercise_entry_mode") or existing.get("exercise_entry_mode") or "manual")
        for key in ("source_option_symbol","source_contracts","source_contract_size",
                    "annual_interest_rate","interest_period_days","period_interest_rate",
                    "adjusted_strike","risk_free_interest_adjustment","relative_advantage_percent",
                    "suggested_price","suggested_price_fetched_at","confirmed_price",
                    "price_confirmed_at"):
            if payload.get(key) not in (None, ""):
                updated[key] = payload.get(key)
        if market not in {"tehran","goods"} or not asset or method not in {"direct","exercise"}:
            raise ValueError("اطلاعات دارایی پایه معتبر نیست")
        with self._lock:
            items=self._read()
            for index,item in enumerate(items):
                if item.get("id")==position_id:
                    items[index]=updated; self._write(items); return dict(updated)
        raise KeyError("دارایی پایه پیدا نشد")

    def create_from_exercise(self, trade: dict) -> dict | None:
        if trade.get("strategy_type") != "long_call" or trade.get("exit_method") not in {"exercise","mixed"}:
            return None
        contracts=float(trade.get("exercise_quantity") or trade.get("quantity") or 0)
        if contracts <= 0: return None
        terms = exercise_underlying_terms(trade)
        units=terms["quantity"]
        source_id=str(trade.get("id") or "")
        with self._lock:
            items=self._read()
            existing=next((item for item in items if item.get("source_trade_id")==source_id and item.get("acquisition_method")=="exercise"),None)
            payload={"status":"open","market":trade.get("market"),"asset":trade.get("asset"),
                "acquisition_method":"exercise","entry_date":trade.get("exit_date"),
                "entry_price":terms["entry_price"],"quantity":units,"commission":0.0,
                "commission_source":"actual",
                "source_trade_id":source_id,"exercise_entry_mode":"trade",
                "quantity_kind":"unit",
                "currency_unit":str(trade.get("currency_unit") or "rial"),
                "calculation_version":int(trade.get("calculation_version") or 7), **{
                    key:value for key,value in terms.items() if key not in {"market","asset","quantity","entry_price"}
                }}
            if existing:
                existing.update(payload); self._write(items); return dict(existing)
            payload["id"]=uuid4().hex; items.append(payload); self._write(items); return dict(payload)

    def sell_quantity(
        self, position_id: str, quantity: float, *, exit_date: date,
        exit_price: float, exit_commission=None, exit_commission_source=None,
        source_trade_id=None,
        exclude_from_portfolio: bool = False, suggested_exit_price=None,
        suggested_price_fetched_at=None, price_confirmed_at=None,
    ) -> dict:
        quantity=_number(quantity,minimum=0.0000001)
        with self._lock:
            items=self._read()
            for item in items:
                if item.get("id")!=position_id or item.get("status")=="closed": continue
                entry_date = parse_user_date(str(item.get("entry_date") or ""))
                if exit_date < entry_date or exit_date > tehran_today():
                    raise ValueError("تاریخ فروش باید از تاریخ خرید تا امروز باشد")
                available=_number(item.get("quantity"),minimum=0.0000001)
                if quantity>available+1e-9: raise ValueError("تعداد دارایی فروخته‌شده بیشتر از موجودی است")
                ratio=quantity/available
                resolved_exit_price = _number(exit_price,minimum=0.0000001)
                resolved_exit_commission, inferred_exit_source = _commission_value(
                    exit_commission,
                    estimate=lambda: _estimated_commission(
                        str(item.get("market") or "tehran"),
                        "underlying_sell", resolved_exit_price, quantity,
                    ),
                )
                resolved_exit_source = (
                    str(exit_commission_source)
                    if exit_commission_source in {"actual", "estimated"}
                    else inferred_exit_source
                )
                closed=dict(item); closed.update({"id":uuid4().hex,"status":"closed","quantity":quantity,
                    "commission":float(item.get("commission") or 0)*ratio,"exit_date":exit_date.isoformat(),
                    "exit_price":resolved_exit_price,"exit_commission":resolved_exit_commission,
                    "exit_commission_source":resolved_exit_source,
                    "source_trade_id":source_trade_id or item.get("source_trade_id"),"parent_position_id":position_id,
                    "portfolio_excluded":bool(exclude_from_portfolio),
                    "suggested_exit_price":suggested_exit_price,
                    "suggested_exit_price_fetched_at":suggested_price_fetched_at,
                    "confirmed_exit_price":_number(exit_price,minimum=0.0000001),
                    "exit_price_confirmed_at":price_confirmed_at or datetime.now().isoformat()})
                if int(item.get("calculation_version") or 7) >= 8:
                    original_commission = _money_decimal(
                        item, "commission", item.get("commission", 0)
                    )
                    ratio_exact = (
                        exact_decimal(quantity, name="quantity")
                        / exact_decimal(available, name="available")
                    )
                    closed["money_schema_version"] = 1
                    closed["money_values"] = _captured_money_values(
                        {
                            **closed,
                            "commission": original_commission * ratio_exact,
                            "exit_price": exit_price,
                            "exit_commission": (
                                exit_commission
                                if exit_commission not in (None, "")
                                else resolved_exit_commission
                            ),
                        },
                        {
                            "commission": original_commission * ratio_exact,
                            "exit_price": resolved_exit_price,
                            "exit_commission": resolved_exit_commission,
                        },
                    )
                if quantity>=available-1e-9:
                    item.update(closed); item["id"]=position_id
                else:
                    item["quantity"]=available-quantity; item["commission"]=float(item.get("commission") or 0)*(1-ratio)
                    if int(item.get("calculation_version") or 7) >= 8:
                        remaining_money = dict(item.get("money_values") or {})
                        remaining_money["commission"] = decimal_text(
                            original_commission
                            * (exact_decimal(1, name="one") - ratio_exact)
                        )
                        item["money_values"] = remaining_money
                    items.append(closed)
                self._write(items); return dict(closed)
        raise KeyError("دارایی پایه پیدا نشد")

    def rebase_released_quantity(
        self,
        position_id: str,
        quantity: float,
        *,
        release_date: date,
        release_price: float,
        other_allocated_quantity: float = 0,
        source_trade_id: str | None = None,
    ) -> dict:
        """Return covered-call collateral to the free pool at release price.

        Only the released portion is repriced. Any already-free quantity keeps
        its prior basis and the resulting free pool receives a weighted basis.
        Remaining collateral is excluded from that weighting.
        """
        released = _number(quantity, minimum=0.0000001)
        price = _number(release_price, minimum=0.0000001)
        allocated = _number(other_allocated_quantity or 0, minimum=0)
        with self._lock:
            items = self._read()
            for item in items:
                if item.get("id") != position_id or item.get("status") == "closed":
                    continue
                total = _number(item.get("quantity"), minimum=0.0000001)
                free_after = max(0.0, total - allocated)
                if released > free_after + 1e-9:
                    raise ValueError("تعداد آزادشده بیشتر از موجودی قابل آزادسازی است")
                free_before = max(0.0, free_after - released)
                prior_basis = _number(item.get("entry_price"), minimum=0.0000001)
                resulting_basis = (
                    (free_before * prior_basis + released * price) / free_after
                    if free_after > 0 else prior_basis
                )
                item.setdefault("original_entry_price", prior_basis)
                item.setdefault("original_entry_date", item.get("entry_date"))
                events = list(item.get("cost_basis_events") or [])
                events.append({
                    "kind": "covered_call_release",
                    "source_trade_id": source_trade_id,
                    "date": release_date.isoformat(),
                    "quantity": released,
                    "prior_free_quantity": free_before,
                    "remaining_allocated_quantity": allocated,
                    "prior_basis": prior_basis,
                    "release_price": price,
                    "resulting_basis": resulting_basis,
                })
                item["entry_price"] = resulting_basis
                item["basis_updated_at"] = release_date.isoformat()
                item["cost_basis_events"] = events
                self._write(items)
                return dict(item)
        raise KeyError("دارایی پایه پیدا نشد")

    def delete(self, position_id: str) -> None:
        with self._lock:
            items=self._read(); remaining=[item for item in items if item.get("id")!=position_id]
            if len(items)==len(remaining): raise KeyError("دارایی پایه پیدا نشد")
            self._write(remaining)


class TradeStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("فایل معاملات قابل خواندن نیست") from exc
        return payload if isinstance(payload, list) else []

    def _write(self, trades: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(trades, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(item) for item in self._read()]

    def create(self, payload: dict, quote: dict) -> dict:
        trade = self._validated(payload, quote)
        trade.update({"id": uuid4().hex, "status": "open", "mutation_version": 1})
        with self._lock:
            trades = self._read()
            request_id = str(payload.get("client_request_id") or "").strip()
            if request_id:
                existing = next(
                    (item for item in trades if item.get("client_request_id") == request_id),
                    None,
                )
                if existing:
                    return dict(existing)
                trade["client_request_id"] = request_id
            trades.append(trade)
            self._write(trades)
        return trade

    def update(self, trade_id: str, payload: dict, quote: dict) -> dict:
        updated = self._validated(payload, quote)
        expected_version = payload.get("mutation_version")
        with self._lock:
            trades = self._read()
            for index, existing in enumerate(trades):
                if existing.get("id") == trade_id:
                    current_version = int(existing.get("mutation_version") or 1)
                    if expected_version not in (None, "") and int(expected_version) != current_version:
                        raise ValueError("معامله همزمان تغییر کرده است؛ اطلاعات را تازه‌سازی کنید")
                    updated.update({"id": trade_id, "status": existing.get("status", "open")})
                    updated["mutation_version"] = current_version + 1
                    for key in (
                        "exit_date",
                        "exit_base_price",
                        "exit_option_price",
                        "exit_commission",
                        "exit_note",
                        "quantity_kind",
                        "currency_unit",
                        "calculation_version",
                        "interest_convention",
                        "interest_day_count",
                    ):
                        if key in existing:
                            updated[key] = existing[key]
                    trades[index] = updated
                    self._write(trades)
                    return updated
        raise KeyError("معامله پیدا نشد")

    def close(
        self,
        trade_id: str,
        quote: dict | None,
        *,
        exit_date: date,
        exit_method="offset",
        exit_base_price=None,
        exit_option_price=None,
        exit_commission=None,
        exit_commission_source=None,
        exit_note="",
        price_confirmed=False,
        close_quantity=None,
        close_exercise_quantity=None,
        close_premium_trade_quantity=None,
        underlying_disposition="sell",
        underlying_keep_basis="entry",
        expected_version=None,
    ) -> dict:
        if price_confirmed is not True:
            raise ValueError("برای ثبت خروج باید بررسی قیمت‌های آخرین معامله را تأیید کنید")
        with self._lock:
            trades = self._read()
            for item in trades:
                if item.get("id") == trade_id:
                    current_version = int(item.get("mutation_version") or 1)
                    if expected_version not in (None, "") and int(expected_version) != current_version:
                        raise ValueError("معامله همزمان تغییر کرده است؛ اطلاعات را تازه‌سازی کنید")
                    is_long_call = item.get("strategy_type") == "long_call"
                    method = str(exit_method or item.get("exit_method") or "offset").strip()
                    if method not in {"offset", "exercise", "mixed"}:
                        raise ValueError("روش خروج معتبر نیست")
                    if method == "mixed" and not is_long_call:
                        raise ValueError("خروج ترکیبی فقط برای خرید اختیار خرید معتبر است")
                    disposition = str(underlying_disposition or "sell").strip()
                    if disposition not in {"sell", "keep"}:
                        raise ValueError("وضعیت دارایی پایه پس از خروج معتبر نیست")
                    keep_basis = str(underlying_keep_basis or "entry").strip()
                    if keep_basis not in {"entry", "exit"}:
                        raise ValueError("مبنای قیمت ورود دارایی پایه معتبر نیست")
                    if is_long_call:
                        disposition = "keep" if method in {"exercise", "mixed"} else "sell"
                    original_quantity = _number(
                        item.get("quantity", 1), minimum=0.0000001
                    )
                    is_already_closed = item.get("status") == "closed"
                    if is_long_call:
                        available_exercise = _number(
                            item.get("exercise_quantity", 0), minimum=0
                        )
                        available_premium = _number(
                            item.get("premium_trade_quantity", original_quantity),
                            minimum=0,
                        )
                        has_partial_request = (
                            close_exercise_quantity not in (None, "")
                            or close_premium_trade_quantity not in (None, "")
                        ) and not is_already_closed
                        if has_partial_request:
                            closing_exercise = _number(
                                close_exercise_quantity or 0, minimum=0
                            )
                            closing_premium = _number(
                                close_premium_trade_quantity or 0, minimum=0
                            )
                            closing_quantity = closing_exercise + closing_premium
                            if closing_quantity <= 0:
                                raise ValueError("تعداد بسته‌شونده باید بیشتر از صفر باشد")
                            if closing_quantity > original_quantity + 1e-9:
                                raise ValueError(
                                    "جمع تعداد قراردادهای اعمال و آفست بیشتر از مانده معامله است"
                                )
                            method = (
                                "mixed" if closing_exercise > 0 and closing_premium > 0
                                else "exercise" if closing_exercise > 0 else "offset"
                            )
                        else:
                            closing_quantity = original_quantity
                            closing_exercise = available_exercise
                            closing_premium = available_premium
                    else:
                        closing_quantity = (
                            original_quantity
                            if close_quantity in (None, "") or is_already_closed
                            else _number(close_quantity, minimum=0.0000001)
                        )
                        if closing_quantity > original_quantity + 1e-9:
                            raise ValueError("تعداد بسته‌شونده بیشتر از مانده معامله است")
                        closing_exercise = closing_premium = 0.0

                    if int(item.get("calculation_version") or 7) >= 8:
                        trade_underlying_units(item, closing_quantity)
                        if is_long_call:
                            if closing_exercise > 0:
                                trade_underlying_units(item, closing_exercise)
                            if closing_premium > 0:
                                trade_underlying_units(item, closing_premium)

                    partial_close = (
                        not is_already_closed
                        and closing_quantity < original_quantity - 1e-9
                    )
                    if partial_close:
                        entry_commission = _number(item.get("commission", 0), minimum=0)
                        commission_ratio = closing_quantity / original_quantity
                        entry_commission_exact = _money_decimal(
                            item, "commission", entry_commission
                        )
                        commission_ratio_exact = (
                            exact_decimal(closing_quantity, name="closing_quantity")
                            / exact_decimal(original_quantity, name="original_quantity")
                        )
                        closed_record = dict(item)
                        closed_record.update({
                            "id": uuid4().hex,
                            "parent_trade_id": item.get("parent_trade_id") or item["id"],
                            "source_trade_id": item["id"],
                            "quantity": closing_quantity,
                            "commission": entry_commission * commission_ratio,
                            "partial_close": True,
                            "mutation_version": 1,
                            "remaining_quantity_after_close": (
                                original_quantity - closing_quantity
                            ),
                        })
                        item["quantity"] = original_quantity - closing_quantity
                        item["commission"] = entry_commission * (1 - commission_ratio)
                        if int(item.get("calculation_version") or 7) >= 8:
                            closed_money = dict(item.get("money_values") or {})
                            open_money = dict(closed_money)
                            closed_money["commission"] = decimal_text(
                                entry_commission_exact * commission_ratio_exact
                            )
                            open_money["commission"] = decimal_text(
                                entry_commission_exact
                                * (exact_decimal(1, name="one") - commission_ratio_exact)
                            )
                            closed_record["money_values"] = closed_money
                            item["money_values"] = open_money
                        item["partial_close_count"] = int(
                            item.get("partial_close_count", 0)
                        ) + 1
                        item["mutation_version"] = current_version + 1
                        if is_long_call:
                            closed_record["exercise_quantity"] = closing_exercise
                            closed_record["premium_trade_quantity"] = closing_premium
                            remaining_quantity = original_quantity - closing_quantity
                            # Entry allocation records the initial intent, not a
                            # restriction on the eventual exit.  Preserve as much
                            # of the unconsumed exercise allocation as possible and
                            # reconcile the rest to premium trading so the remaining
                            # buckets always equal the open quantity.
                            item["exercise_quantity"] = min(
                                max(0.0, available_exercise - closing_exercise),
                                remaining_quantity,
                            )
                            item["premium_trade_quantity"] = (
                                remaining_quantity - item["exercise_quantity"]
                            )
                    else:
                        closed_record = item
                        closed_record["mutation_version"] = current_version + 1
                        if is_long_call:
                            closed_record["exercise_quantity"] = closing_exercise
                            closed_record["premium_trade_quantity"] = closing_premium
                            closed_record["quantity"] = closing_quantity
                    market_base = (quote or {}).get("base_last")
                    market_option = (quote or {}).get("option_last")
                    base_price = _number(
                        exit_base_price if exit_base_price not in (None, "") else market_base,
                        minimum=0.0000001,
                    )
                    option_price = (
                        _number(
                            exit_option_price
                            if exit_option_price not in (None, "")
                            else (quote or {}).get("option_last") or 0,
                            minimum=0,
                        )
                        if method == "exercise" and is_long_call
                        else 0.0 if method == "exercise" else _number(
                            exit_option_price if exit_option_price not in (None, "") else market_option,
                            minimum=0,
                        )
                    )
                    if method == "offset" and market_option is None and exit_option_price in (None, ""):
                        raise ValueError("آخرین معامله اختیار در دسترس نیست؛ قیمت را دستی وارد کنید")
                    if market_base is None and exit_base_price in (None, ""):
                        raise ValueError("آخرین معامله دارایی پایه در دسترس نیست؛ قیمت را دستی وارد کنید")
                    entry_date = parse_user_date(item["entry_date"])
                    if exit_date < entry_date or exit_date > tehran_today():
                        raise ValueError(
                            "تاریخ خروج باید از تاریخ ورود تا امروز باشد"
                        )
                    note = str(exit_note or "").strip()
                    if len(note) > 500:
                        raise ValueError("توضیحات خروج حداکثر ۵۰۰ نویسه است")
                    expiry = datetime.strptime(str(closed_record["expiry"]), "%Y-%m-%d").date()
                    market_snapshot_option = (
                        (quote or {}).get("option_last")
                        if method == "exercise" and not is_long_call
                        else option_price
                    )
                    exit_analytics = _analytics_snapshot(
                        base_price=base_price,
                        strike=_number(closed_record["strike"], minimum=0.0000001),
                        option_price=(
                            _number(market_snapshot_option, minimum=0)
                            if market_snapshot_option is not None else None
                        ),
                        days=max(0, (expiry - exit_date).days),
                        interest_rate=_number(closed_record.get("annual_interest_rate", 40), minimum=0),
                        covered=not is_long_call,
                        prefix="exit",
                    )
                    resolved_exit_commission, inferred_exit_commission_source = _commission_value(
                        exit_commission,
                        estimate=lambda: 0.0,
                    )
                    exit_commission_source = (
                        str(exit_commission_source)
                        if exit_commission_source in {"actual", "estimated"}
                        else inferred_exit_commission_source
                    )
                    closed_record.update({
                        "status": "closed",
                        "exit_method": method,
                        "exit_date": exit_date.isoformat(),
                        "exit_base_price": base_price,
                        "exit_option_price": option_price,
                        "exit_commission": resolved_exit_commission,
                        "exit_commission_source": exit_commission_source,
                        "exit_note": note,
                        "exit_price_basis": "last_trade",
                        "exit_price_confirmed": True,
                        "suggested_exit_base_price": market_base,
                        "suggested_exit_option_price": market_option,
                        "confirmed_exit_base_price": base_price,
                        "confirmed_exit_option_price": option_price,
                        "exit_price_confirmed_at": datetime.now().isoformat(),
                        "underlying_disposition": disposition,
                        "underlying_keep_basis": keep_basis,
                        **exit_analytics,
                    })
                    if int(closed_record.get("calculation_version") or 7) >= 8:
                        money_source = dict(closed_record)
                        if exit_base_price not in (None, ""):
                            money_source["exit_base_price"] = exit_base_price
                        if exit_option_price not in (None, ""):
                            money_source["exit_option_price"] = exit_option_price
                        if exit_commission not in (None, ""):
                            money_source["exit_commission"] = exit_commission
                        closed_record["money_schema_version"] = 1
                        closed_record["money_values"] = _captured_money_values(
                            money_source,
                            {
                                "exit_base_price": base_price,
                                "exit_option_price": option_price,
                                "exit_commission": resolved_exit_commission,
                            },
                        )
                    if partial_close:
                        trades.append(closed_record)
                    self._write(trades)
                    return dict(closed_record)
        raise KeyError("معامله پیدا نشد")

    def delete(self, trade_id: str) -> None:
        with self._lock:
            trades = self._read()
            remaining = [item for item in trades if item.get("id") != trade_id]
            if len(remaining) == len(trades):
                raise KeyError("معامله پیدا نشد")
            self._write(remaining)

    @staticmethod
    def _validated(payload: dict, quote: dict) -> dict:
        market = str(payload.get("market") or "").strip()
        strategy_type = str(payload.get("strategy_type") or "covered_call").strip()
        symbol = normalize_fa(str(
            payload.get("option_symbol")
            or payload.get("manual_option_symbol")
            or ""
        ))
        asset = str(payload.get("asset") or quote.get("asset") or "").strip()
        if (
            market not in {"goods", "tehran"}
            or strategy_type not in {"covered_call", "long_call"}
            or not symbol
            or not asset
        ):
            raise ValueError("بازار، دارایی پایه و نماد اختیار الزامی هستند")
        entry_date = parse_user_date(str(payload.get("entry_date") or ""))
        expiry = datetime.strptime(str(quote["expiry"]), "%Y-%m-%d").date()
        latest_entry_date = tehran_today() + timedelta(days=ENTRY_DATE_GRACE_DAYS)
        if entry_date > latest_entry_date or entry_date >= expiry:
            raise ValueError(
                "تاریخ ورود باید قبل از سررسید و حداکثر یک روز بعد از امروز تهران باشد"
            )
        entry_base_price = _number(payload.get("entry_base_price"), minimum=0.0000001)
        entry_premium = _number(payload.get("entry_premium"), minimum=0)
        if strategy_type == "covered_call" and entry_base_price <= entry_premium:
            raise ValueError("قیمت پایه در ورود باید بیشتر از پرمیوم دریافتی باشد")
        if strategy_type == "long_call" and entry_premium <= 0:
            raise ValueError("پرمیوم پرداختی باید مثبت باشد")
        risk_free_snapshot = resolve_risk_free_rate(
            as_of=entry_date,
            override=(
                payload.get("annual_interest_rate")
                if "annual_interest_rate" in payload
                else None
            ),
        )
        annual_interest_rate = float(risk_free_snapshot.rate_percent)
        if strategy_type == "long_call":
            has_allocations = (
                "exercise_quantity" in payload or "premium_trade_quantity" in payload
            )
            if has_allocations:
                exercise_quantity = _number(
                    payload.get("exercise_quantity") or 0, minimum=0
                )
                premium_trade_quantity = _number(
                    payload.get("premium_trade_quantity") or 0, minimum=0
                )
                quantity = exercise_quantity + premium_trade_quantity
                if quantity <= 0:
                    raise ValueError(
                        "حداقل یکی از تعدادهای اعمال یا نوسان‌گیری باید بیشتر از صفر باشد"
                    )
            else:
                # Backward compatibility for old clients and saved trades.
                quantity = _number(payload.get("quantity", 1), minimum=0.0000001)
                exercise_quantity = 0.0
                premium_trade_quantity = quantity
        else:
            quantity = _number(payload.get("quantity", 1), minimum=0.0000001)
            exercise_quantity = 0.0
            premium_trade_quantity = 0.0
        contract_size = _number(
            quote.get("contract_size", 1), minimum=0.0000001
        )
        calculation_version = int(
            payload.get("calculation_version") or LEGACY_CALCULATION_VERSION
        )
        quantity_kind = str(
            payload.get("quantity_kind")
            or (QUANTITY_CONTRACT if calculation_version >= CANONICAL_CALCULATION_VERSION else QUANTITY_UNIT)
        )
        currency_unit = str(payload.get("currency_unit") or CURRENCY_RIAL)
        validate_currency_contract(
            currency_unit=currency_unit,
            calculation_version=calculation_version,
        )
        validation_record = {
            "quantity": quantity,
            "quantity_kind": quantity_kind,
            "contract_size": contract_size,
            "calculation_version": calculation_version,
        }
        trade_underlying_units(validation_record)
        if strategy_type == "long_call":
            for allocation in (exercise_quantity, premium_trade_quantity):
                if allocation > 0:
                    trade_underlying_units(validation_record, allocation)
        units = trade_underlying_units(validation_record)
        entry_commission_kind = (
            "option_buy" if strategy_type == "long_call" else "option_sell"
        )
        commission_schedule = resolve_commission_rate(
            market=market,
            kind=entry_commission_kind,
            as_of=entry_date,
        )
        commission, commission_source = _commission_value(
            payload.get("commission") if "commission" in payload else None,
            estimate=lambda: _estimated_commission(
                market,
                entry_commission_kind,
                entry_premium,
                units,
                as_of=entry_date,
            ),
        )
        trade = {
            "market": market,
            "strategy_type": strategy_type,
            "asset": asset,
            "option_symbol": symbol,
            "entry_date": entry_date.isoformat(),
            "entry_base_price": entry_base_price,
            "entry_premium": entry_premium,
            "quantity": quantity,
            "contract_size": contract_size,
            "quantity_kind": quantity_kind,
            "currency_unit": currency_unit,
            "calculation_version": calculation_version,
            "exercise_quantity": exercise_quantity,
            "premium_trade_quantity": premium_trade_quantity,
            "commission": commission,
            "commission_source": str(
                payload.get("commission_source") or commission_source
            ) if payload.get("commission_source") in {"actual", "estimated"} else commission_source,
            "option_exit_commission_estimate": _number(
                payload.get("option_exit_commission_estimate", 0), minimum=0
            ),
            "exercise_commission_estimate": _number(
                payload.get("exercise_commission_estimate", 0), minimum=0
            ),
            "underlying_exit_commission_estimate": _number(
                payload.get("underlying_exit_commission_estimate", 0), minimum=0
            ),
            "annual_interest_rate": annual_interest_rate,
            "risk_free_rate_source": risk_free_snapshot.source,
            "risk_free_rate_version": risk_free_snapshot.version,
            "risk_free_rate_effective_from": (
                risk_free_snapshot.effective_from.isoformat()
            ),
            "commission_schedule_source": commission_schedule.source,
            "commission_schedule_version": commission_schedule.version,
            "commission_schedule_effective_from": (
                commission_schedule.effective_from.isoformat()
            ),
            "commission_rounding_mode": commission_schedule.rounding_mode,
            "commission_rounding_increment": decimal_text(
                commission_schedule.rounding_increment
            ),
            "commission_rounding_version": commission_schedule.rounding_version,
            "interest_convention": (
                "simple"
                if calculation_version >= CANONICAL_CALCULATION_VERSION
                else str(payload.get("interest_convention") or "compound_legacy")
            ),
            "interest_day_count": "ACT/365",
            "strike": _number(quote["strike"], minimum=0.0000001),
            "expiry": quote["expiry"],
            "contract_entry_mode": (
                "manual_expired" if quote.get("manual_expired") else "live"
            ),
        }
        if calculation_version >= CANONICAL_CALCULATION_VERSION:
            trade["money_schema_version"] = 1
            trade["money_values"] = _captured_money_values(payload, {
                "entry_base_price": entry_base_price,
                "entry_premium": entry_premium,
                "commission": commission,
                "option_exit_commission_estimate": trade[
                    "option_exit_commission_estimate"
                ],
                "exercise_commission_estimate": trade[
                    "exercise_commission_estimate"
                ],
                "underlying_exit_commission_estimate": trade[
                    "underlying_exit_commission_estimate"
                ],
                "strike": trade["strike"],
            })
        for key in (
            "suggested_base_price", "suggested_option_price",
            "suggested_price_fetched_at", "confirmed_base_price",
            "confirmed_option_price", "price_confirmed_at",
        ):
            if payload.get(key) not in (None, ""):
                trade[key] = payload.get(key)
        if strategy_type == "covered_call" and payload.get("underlying_position_id"):
            trade["underlying_position_id"] = str(payload["underlying_position_id"]).strip()
        trade.update(_analytics_snapshot(
            base_price=entry_base_price,
            strike=trade["strike"],
            option_price=entry_premium,
            days=max(0, (expiry - entry_date).days),
            interest_rate=annual_interest_rate,
            covered=strategy_type == "covered_call",
            prefix="entry",
        ))
        return trade
