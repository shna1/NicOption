from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from bambo_bot.config import Settings
from bambo_bot.dates import format_jalali_date
from bambo_bot.history import PriceHistoryClient
from bambo_bot.forecast import ForecastCache
from bambo_bot.financial_contract import financial_capabilities
from bambo_bot.commodity_fx import CommodityFxCache
from bambo_bot.trades import (
    build_account_growth,
    build_covered_profit_recognition,
    build_portfolio_asset_ledger,
    build_underlying_quote_map,
    calculate_trade_snapshot,
    calculate_underlying_snapshot,
    quote_key,
    select_trade_valuation_quote,
    summarize_closed_trades,
    summarize_open_trades,
    summarize_underlying_positions,
    underlying_allocations,
    underlying_quote_key,
)
from bambo_bot.web import DashboardCache

from .stores import DjangoAccountStore, DjangoTradeStore, DjangoUnderlyingPositionStore


class DashboardRuntime:
    def __init__(self, owner_id: int | None = None) -> None:
        self.settings = Settings()
        self.cache = DashboardCache(self.settings)
        self.history = PriceHistoryClient(self.settings)
        self.forecast = ForecastCache(self.settings)
        self.commodity_fx = CommodityFxCache(self.settings)
        self.trades = DjangoTradeStore(owner_id)
        self.underlyings = DjangoUnderlyingPositionStore(owner_id)
        self.account = DjangoAccountStore(owner_id)

    def trade_payload(
        self,
        *,
        covered_option_basis: str = "last",
        covered_base_basis: str = "last",
        long_option_basis: str = "last",
        long_base_basis: str = "last",
    ) -> dict:
        basis_label = {
            "bid": "بهترین پیشنهاد خرید",
            "ask": "بهترین پیشنهاد فروش",
            "last": "آخرین معامله",
        }
        dashboard = self.cache.get()
        as_of = datetime.fromisoformat(dashboard["generated_at"]).date()
        quotes = self.cache.trade_quotes()
        contracts = []
        for quote in sorted(
            quotes.values(),
            key=lambda item: (
                item["market"], item["asset"], item["expiry"], item["symbol"]
            ),
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
        raw_trades = self.trades.list()
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
            ) for item in self.underlyings.list()
        ]
        account = self.account.read()
        account_growth = build_account_growth(
            trades, as_of=as_of, initial_capital=account.get("initial_capital"),
            underlying_positions=underlyings,
        )
        underlying_summary = summarize_underlying_positions(underlyings)
        closed_underlying_summary = summarize_underlying_positions(underlyings,closed=True)
        open_summary = summarize_open_trades(trades, underlyings)
        closed_summary = summarize_closed_trades(trades, underlyings)
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
            "underlying_summary": underlying_summary,
            "closed_underlying_summary": closed_underlying_summary,
            "trades": trades,
            "summary": open_summary,
            "closed_summary": closed_summary,
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


@lru_cache(maxsize=16)
def get_runtime(owner_id: int | None = None) -> DashboardRuntime:
    return DashboardRuntime(owner_id)
