from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def option_quote_gap_percent(best_bid: float | None, last_trade: float | None) -> float | None:
    """Return the signed best-bid discount relative to the last trade."""
    if best_bid is None or best_bid <= 0 or last_trade is None or last_trade <= 0:
        return None
    gap = round((last_trade - best_bid) / last_trade * 100, 2)
    return 0.0 if gap == 0 else gap


def option_ask_gap_percent(best_ask: float | None, last_trade: float | None) -> float | None:
    """Return the signed best-ask premium relative to the last trade."""
    if best_ask is None or best_ask <= 0 or last_trade is None or last_trade <= 0:
        return None
    gap = round((best_ask - last_trade) / last_trade * 100, 2)
    return 0.0 if gap == 0 else gap


@dataclass(frozen=True)
class Contract:
    asset: str
    source_asset: str
    symbol: str
    expiry: str
    days: int
    state: str
    transaction_value: float
    annual_return: float | None
    expiry_return: float | None
    base_price: float | None
    option_bid: float | None
    strike: float | None
    breakeven: float | None
    itm_percent: float | None
    option_last: float | None = None

    @classmethod
    def from_api(cls, row: dict[str, Any], asset: str) -> "Contract":
        days = int(_number(row.get("days")) or 0)
        expiry_return = _number(row.get("simpleInterestRate"))
        annual_return = _number(row.get("interestRate"))
        if annual_return is None and expiry_return is not None and days > 0:
            annual_return = expiry_return * 365 / days
        return cls(
            asset=asset,
            source_asset=str(row.get("baseSymbol") or ""),
            symbol=str(row.get("symbolOption") or ""),
            expiry=str(row.get("expiration_date") or "").split("T", 1)[0],
            days=days,
            state=str(row.get("state") or "").upper(),
            transaction_value=_number(row.get("value")) or 0.0,
            annual_return=annual_return,
            expiry_return=expiry_return,
            base_price=_number(row.get("askPrice1Base")),
            option_bid=_number(row.get("bidPrice1Option")),
            strike=_number(row.get("dueDatePrice")),
            breakeven=_number(row.get("bep")),
            itm_percent=_number(row.get("itmPercent")),
            option_last=_number(row.get("optionPrice")),
        )

    @property
    def option_gap_percent(self) -> float | None:
        return option_quote_gap_percent(self.option_bid, self.option_last)


@dataclass(frozen=True)
class Pick:
    category: str
    metric_name: str
    contract: Contract


def reprice_covered_contract(contract: Contract, basis: str) -> Contract:
    """Recalculate covered-call returns from the selected executable quote."""
    premium = contract.option_last if basis == "last" else contract.option_bid
    base = contract.base_price
    strike = contract.strike
    if premium is None or base is None or base <= 0 or strike is None or contract.days <= 0:
        return replace(contract, annual_return=None, expiry_return=None, breakeven=None)
    expiry_return = (premium - max(base - strike, 0)) / base * 100
    annual_return = expiry_return * 365 / contract.days
    return replace(
        contract,
        annual_return=annual_return,
        expiry_return=expiry_return,
        breakeven=base - premium,
    )
