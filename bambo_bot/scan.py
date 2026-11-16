from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from zoneinfo import ZoneInfo

from .assets import canonical_tehran_asset
from .client import BamboClient
from .config import Settings
from .long_underlying import (
    LongUnderlyingOpportunity,
    build_option_last_price_map,
    build_volume_map,
    select_positive_opportunities,
)
from .models import Contract, Pick, reprice_covered_contract
from .selector import select_picks


TEHRAN = ZoneInfo("Asia/Tehran")


@dataclass(frozen=True)
class ScanResult:
    generated_at: datetime
    contracts: list[Contract]
    covered_call: dict[tuple[str, str], list[Pick]]
    long_underlying: dict[tuple[str, str], list[LongUnderlyingOpportunity]]
    tehran_contracts: list[Contract] = field(default_factory=list)
    tehran_covered_call: dict[tuple[str, str], list[Pick]] = field(default_factory=dict)
    tehran_long_underlying: dict[
        tuple[str, str], list[LongUnderlyingOpportunity]
    ] = field(default_factory=dict)
    covered_call_last: dict[tuple[str, str], list[Pick]] = field(default_factory=dict)
    long_underlying_last: dict[tuple[str, str], list[LongUnderlyingOpportunity]] = field(default_factory=dict)
    long_underlying_ask: dict[tuple[str, str], list[LongUnderlyingOpportunity]] = field(default_factory=dict)
    tehran_covered_call_last: dict[tuple[str, str], list[Pick]] = field(default_factory=dict)
    tehran_long_underlying_last: dict[
        tuple[str, str], list[LongUnderlyingOpportunity]
    ] = field(default_factory=dict)
    tehran_long_underlying_ask: dict[
        tuple[str, str], list[LongUnderlyingOpportunity]
    ] = field(default_factory=dict)
    goods_trade_rows: list[dict] = field(default_factory=list)
    tehran_trade_rows: list[dict] = field(default_factory=list)


def collect_scan(settings: Settings) -> ScanResult:
    client = BamboClient(settings)
    try:
        option_goods_rows = client.fetch_option_goods()
    except Exception:
        # Strategy rows remain usable when Bambo's auxiliary quote endpoint is
        # temporarily unavailable. Last-trade variants will simply be empty.
        option_goods_rows = []
    option_last_by_symbol = build_option_last_price_map(option_goods_rows)
    contracts = client.fetch_contracts()
    contracts = [
        replace(
            contract,
            option_last=option_last_by_symbol.get(contract.symbol, contract.option_last),
        )
        for contract in contracts
    ]
    long_rows = client.fetch_rows("long_underlying")
    volume_by_symbol = build_volume_map(option_goods_rows)
    long_underlying = select_positive_opportunities(
        long_rows,
        settings.long_underlying_interest_rate,
        volume_by_symbol,
        option_last_by_symbol=option_last_by_symbol,
    )
    long_underlying_last = select_positive_opportunities(
        long_rows,
        settings.long_underlying_interest_rate,
        volume_by_symbol,
        option_last_by_symbol=option_last_by_symbol,
        price_basis="last",
    )
    long_underlying_ask = select_positive_opportunities(
        long_rows,
        settings.long_underlying_interest_rate,
        volume_by_symbol,
        option_last_by_symbol=option_last_by_symbol,
        price_basis="ask",
    )
    covered_call = select_picks(
        contracts,
        min_annual_return=settings.covered_call_min_annual_return,
    )
    covered_call_last = select_picks(
        [reprice_covered_contract(contract, "last") for contract in contracts],
        min_annual_return=settings.covered_call_min_annual_return,
    )
    try:
        # TSETMC market watch is the complete official call-option universe.
        tehran_trade_rows = client.fetch_tehran_market_watch()
    except Exception:
        tehran_trade_rows = []
    tehran_contracts = client.fetch_tehran_contracts(
        tehran_trade_rows if tehran_trade_rows else None
    )
    tehran_long_rows = client.fetch_tehran_rows("long_underlying")
    if not tehran_trade_rows:
        # Keep tracking usable if the broader market-watch endpoint is briefly
        # unavailable; the strategy rows are a smaller but valid fallback.
        tehran_trade_rows = tehran_long_rows
    tehran_volume_by_symbol = {
        str(row.get("symbolOption") or ""): float(row.get("volume") or 0)
        for row in tehran_long_rows
        if row.get("symbolOption")
    }
    tehran_long_underlying = select_positive_opportunities(
        tehran_long_rows,
        settings.long_underlying_interest_rate,
        tehran_volume_by_symbol,
        asset_resolver=lambda row, symbol: canonical_tehran_asset(
            str(row.get("baseSymbol") or ""), symbol
        ),
        volume_is_proxy=False,
    )
    tehran_long_underlying_last = select_positive_opportunities(
        tehran_long_rows,
        settings.long_underlying_interest_rate,
        tehran_volume_by_symbol,
        asset_resolver=lambda row, symbol: canonical_tehran_asset(
            str(row.get("baseSymbol") or ""), symbol
        ),
        volume_is_proxy=False,
        price_basis="last",
    )
    tehran_long_underlying_ask = select_positive_opportunities(
        tehran_long_rows,
        settings.long_underlying_interest_rate,
        tehran_volume_by_symbol,
        asset_resolver=lambda row, symbol: canonical_tehran_asset(
            str(row.get("baseSymbol") or ""), symbol
        ),
        volume_is_proxy=False,
        price_basis="ask",
    )
    tehran_covered_call = select_picks(
        tehran_contracts,
        min_annual_return=settings.covered_call_min_annual_return,
    )
    tehran_covered_call_last = select_picks(
        [reprice_covered_contract(contract, "last") for contract in tehran_contracts],
        min_annual_return=settings.covered_call_min_annual_return,
    )
    return ScanResult(
        generated_at=datetime.now(TEHRAN),
        contracts=contracts,
        covered_call=covered_call,
        long_underlying=long_underlying,
        tehran_contracts=tehran_contracts,
        tehran_covered_call=tehran_covered_call,
        tehran_long_underlying=tehran_long_underlying,
        covered_call_last=covered_call_last,
        long_underlying_last=long_underlying_last,
        long_underlying_ask=long_underlying_ask,
        tehran_covered_call_last=tehran_covered_call_last,
        tehran_long_underlying_last=tehran_long_underlying_last,
        tehran_long_underlying_ask=tehran_long_underlying_ask,
        goods_trade_rows=long_rows,
        tehran_trade_rows=tehran_trade_rows,
    )
