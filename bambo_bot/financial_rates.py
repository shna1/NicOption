"""Versioned financial assumptions used by calculation version 8.

The initial schedules preserve the historical application constants and their
historical nearest-rial rounding behavior. Their source and rounding rule stay
explicitly unverified until an authoritative market document is attached;
versioning prevents later changes from rewriting old results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN

from .financial_contract import exact_decimal


LEGACY_EFFECTIVE_FROM = date(2020, 1, 1)
LEGACY_SOURCE = "legacy-static-unverified"
LEGACY_COMMISSION_ROUNDING = ROUND_HALF_EVEN
LEGACY_COMMISSION_INCREMENT = Decimal("1")
LEGACY_COMMISSION_ROUNDING_VERSION = "nearest-rial-half-even-legacy-v1"


@dataclass(frozen=True)
class RiskFreeRateSnapshot:
    rate_percent: Decimal
    version: str
    effective_from: date
    source: str


@dataclass(frozen=True)
class CommissionRateSnapshot:
    rate: Decimal
    version: str
    effective_from: date
    source: str
    rounding_mode: str
    rounding_increment: Decimal
    rounding_version: str


_RISK_FREE = RiskFreeRateSnapshot(
    rate_percent=Decimal("40"),
    version="ir-risk-free-legacy-v1",
    effective_from=LEGACY_EFFECTIVE_FROM,
    source=LEGACY_SOURCE,
)

_COMMISSION_RATES = {
    "tehran": {
        "underlying_buy": Decimal("0.003712"),
        "underlying_sell": Decimal("0.0088"),
        "option_buy": Decimal("0.00103"),
        "option_sell": Decimal("0.00103"),
        "option_exercise": Decimal("0.0005"),
    },
    "goods": {
        "underlying_buy": Decimal("0.003712"),
        "underlying_sell": Decimal("0.0088"),
        "option_buy": Decimal("0.0012"),
        "option_sell": Decimal("0.0012"),
        "option_exercise": Decimal("0.0012"),
    },
}


def resolve_risk_free_rate(
    *, as_of: date, override=None
) -> RiskFreeRateSnapshot:
    if as_of < _RISK_FREE.effective_from:
        raise ValueError("no risk-free rate schedule exists for this date")
    if override not in (None, ""):
        rate = exact_decimal(override, name="risk_free_rate")
        if rate < 0:
            raise ValueError("risk-free rate must be nonnegative")
        return RiskFreeRateSnapshot(
            rate_percent=rate,
            version=f"user-override:{as_of.isoformat()}",
            effective_from=as_of,
            source="user_override",
        )
    return _RISK_FREE


def resolve_commission_rate(
    *, market: str, kind: str, as_of: date
) -> CommissionRateSnapshot:
    market_rates = _COMMISSION_RATES.get(str(market or "tehran"))
    if market_rates is None or kind not in market_rates:
        raise ValueError("commission market or kind is unsupported")
    if as_of < LEGACY_EFFECTIVE_FROM:
        raise ValueError("no commission schedule exists for this date")
    return CommissionRateSnapshot(
        rate=market_rates[kind],
        version="ir-fees-legacy-v1",
        effective_from=LEGACY_EFFECTIVE_FROM,
        source=LEGACY_SOURCE,
        rounding_mode=LEGACY_COMMISSION_ROUNDING,
        rounding_increment=LEGACY_COMMISSION_INCREMENT,
        rounding_version=LEGACY_COMMISSION_ROUNDING_VERSION,
    )


def calculate_commission(
    *, market: str, kind: str, as_of: date, price, quantity
) -> tuple[Decimal, CommissionRateSnapshot]:
    """Calculate a fee with an explicit, reproducible compatibility policy.

    The current rounding rule preserves the application's historical nearest-
    rial, ties-to-even behavior.  It is deliberately labeled legacy and must
    not be presented as an exchange rule until an authoritative circular is
    attached to a future schedule version.
    """
    snapshot = resolve_commission_rate(market=market, kind=kind, as_of=as_of)
    notional = (
        exact_decimal(price, name="price")
        * exact_decimal(quantity, name="quantity")
    )
    if notional < 0:
        raise ValueError("commission notional must be nonnegative")
    amount = (notional * snapshot.rate).quantize(
        snapshot.rounding_increment,
        rounding=snapshot.rounding_mode,
    )
    return amount, snapshot
