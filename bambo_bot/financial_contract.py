"""Versioned, exact quantity semantics for financial records.

This module deliberately contains no pricing or portfolio logic.  It is the
single boundary that converts an explicitly typed quantity into option
contracts and underlying units.  Legacy callers must provide their known
quantity kind; missing historical semantics are never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


LEGACY_CALCULATION_VERSION = 7
CANONICAL_CALCULATION_VERSION = 8
QUANTITY_CONTRACT = "contract"
QUANTITY_UNIT = "unit"
QUANTITY_KINDS = frozenset({QUANTITY_CONTRACT, QUANTITY_UNIT})
CURRENCY_RIAL = "rial"
CURRENCY_TOMAN = "toman"
CURRENCY_UNITS = frozenset({CURRENCY_RIAL, CURRENCY_TOMAN})
CURRENCY_FACTORS_IN_RIAL = {
    CURRENCY_RIAL: Decimal("1"),
    CURRENCY_TOMAN: Decimal("10"),
}


def financial_capabilities() -> dict[str, Any]:
    """Return auditable calculation coverage without inventing market rules.

    Corporate-action processing remains deliberately disabled until an
    authoritative Iran-market rule set and a product workflow are approved.
    Exposing the gap in the payload prevents clients from assuming that a
    displayed return has already incorporated those events.
    """
    return {
        "calculation_version": CANONICAL_CALCULATION_VERSION,
        "currency_unit": CURRENCY_RIAL,
        "corporate_actions": {
            "status": "not_supported",
            "automatic_adjustment": False,
            "supported_events": [],
            "excluded_events": [
                "cash_dividend",
                "stock_split_or_capital_increase",
                "adjusted_contract_multiplier",
            ],
            "reason": "official_market_rules_and_product_scope_unverified",
        },
    }


class AmbiguousQuantityError(ValueError):
    """Raised when a legacy quantity cannot be interpreted safely."""


def exact_decimal(value: Any, *, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{name} must be finite")
    return number


def decimal_text(value: Any, *, name: str = "money") -> str:
    """Return a stable non-exponent Decimal representation."""
    number = exact_decimal(value, name=name)
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def normalize_currency(
    value: Any, *, from_unit: str, to_unit: str
) -> Decimal:
    """Convert rial/toman amounts exactly, without a float round trip."""
    if from_unit not in CURRENCY_UNITS or to_unit not in CURRENCY_UNITS:
        raise ValueError("currency unit must be rial or toman")
    amount = exact_decimal(value, name="money")
    return (
        amount
        * CURRENCY_FACTORS_IN_RIAL[from_unit]
        / CURRENCY_FACTORS_IN_RIAL[to_unit]
    )


def validate_currency_contract(
    *, currency_unit: str | None, calculation_version: int | None
) -> str:
    """Validate currency metadata while preserving legacy interpretation.

    Version 8 has one storage/calculation unit: rial. A toman-labelled v8
    payload is rejected instead of being silently treated as rial or converted
    at an undocumented boundary. Legacy rows retain their declared unit.
    """
    unit = str(currency_unit or "").strip()
    if unit not in CURRENCY_UNITS:
        raise ValueError("currency unit must be rial or toman")
    if isinstance(calculation_version, bool):
        raise ValueError("calculation_version must be a positive integer")
    try:
        version = int(calculation_version)
    except (TypeError, ValueError) as exc:
        raise ValueError("calculation_version must be a positive integer") from exc
    if version <= 0:
        raise ValueError("calculation_version must be a positive integer")
    if version >= CANONICAL_CALCULATION_VERSION and unit != CURRENCY_RIAL:
        raise ValueError("version 8 canonical currency unit must be rial")
    return unit


@dataclass(frozen=True)
class NormalizedExposure:
    source_quantity: Decimal
    quantity_kind: str
    contract_size: Decimal
    contract_quantity: Decimal
    underlying_units: Decimal
    calculation_version: int


def normalize_exposure(
    *,
    quantity: Any,
    quantity_kind: str | None,
    contract_size: Any,
    calculation_version: int | None,
) -> NormalizedExposure:
    """Normalize an explicitly typed quantity without double multiplication.

    ``contract`` means ``underlying_units = quantity * contract_size``.
    ``unit`` means quantity is already the final underlying-unit count.  The
    latter rule preserves known legacy records and underlying positions.
    """
    if quantity_kind not in QUANTITY_KINDS:
        raise AmbiguousQuantityError(
            "quantity_kind must be explicit for legacy financial records"
        )
    if isinstance(calculation_version, bool):
        raise AmbiguousQuantityError(
            "calculation_version must be explicit for financial records"
        )
    try:
        version = int(calculation_version)
    except (TypeError, ValueError) as exc:
        raise AmbiguousQuantityError(
            "calculation_version must be explicit for financial records"
        ) from exc
    if version <= 0:
        raise ValueError("calculation_version must be positive")

    source_quantity = exact_decimal(quantity, name="quantity")
    multiplier = exact_decimal(contract_size, name="contract_size")
    if source_quantity <= 0:
        raise ValueError("quantity must be positive")
    if multiplier <= 0:
        raise ValueError("contract_size must be positive")

    if quantity_kind == QUANTITY_CONTRACT:
        if source_quantity != source_quantity.to_integral_value():
            raise ValueError("contract quantity must be a positive whole number")
        contract_quantity = source_quantity
        underlying_units = source_quantity * multiplier
    else:
        underlying_units = source_quantity
        contract_quantity = source_quantity / multiplier

    return NormalizedExposure(
        source_quantity=source_quantity,
        quantity_kind=quantity_kind,
        contract_size=multiplier,
        contract_quantity=contract_quantity,
        underlying_units=underlying_units,
        calculation_version=version,
    )
