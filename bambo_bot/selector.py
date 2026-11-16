from __future__ import annotations

from collections import defaultdict

from .models import Contract, Pick


CATEGORIES = (
    ("ITM · بیشترین سود سالانه", "ITM", "annual_return", "سود سالانه"),
    ("ITM · بیشترین سود تا سررسید", "ITM", "expiry_return", "سود تا سررسید"),
)


def _best(candidates: list[Contract], metric: str) -> Contract | None:
    eligible = [item for item in candidates if getattr(item, metric) is not None]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda item: (
            -(getattr(item, metric) or 0),
            -item.transaction_value,
            item.symbol,
        ),
    )[0]


def select_picks(
    contracts: list[Contract], min_annual_return: float = 40
) -> dict[tuple[str, str], list[Pick]]:
    groups: dict[tuple[str, str], list[Contract]] = defaultdict(list)
    for contract in contracts:
        if contract.expiry and contract.symbol:
            groups[(contract.asset, contract.expiry)].append(contract)

    selections: dict[tuple[str, str], list[Pick]] = {}
    for key, chain in groups.items():
        eligible_chain = [
            item
            for item in chain
            if item.annual_return is not None
            and item.annual_return >= min_annual_return
        ]
        picks: list[Pick] = []
        for category, state, metric, metric_name in CATEGORIES:
            winner = _best([item for item in eligible_chain if item.state == state], metric)
            if winner:
                picks.append(Pick(category, metric_name, winner))
        selections[key] = picks
    return selections


def top_unique_contracts(
    selections: dict[tuple[str, str], list[Pick]], limit: int = 5
) -> list[Contract]:
    unique: dict[str, Contract] = {}
    for picks in selections.values():
        for pick in picks:
            item = pick.contract
            if item.transaction_value <= 0:
                continue
            current = unique.get(item.symbol)
            if current is None or (item.annual_return or 0) > (current.annual_return or 0):
                unique[item.symbol] = item
    return sorted(
        unique.values(),
        key=lambda item: (-(item.annual_return or 0), -item.transaction_value, item.symbol),
    )[:limit]
