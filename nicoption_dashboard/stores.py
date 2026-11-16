from __future__ import annotations

import threading
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.contrib.auth import get_user_model

from bambo_bot.financial_contract import exact_decimal
from bambo_bot.trades import AccountStore, TradeStore, UnderlyingPositionStore, _number

from .models import AccountPreference, TradeRecord, UnderlyingPositionRecord


_UNSET = object()


class DjangoTradeStore(TradeStore):
    """TradeStore-compatible adapter backed by Django's database."""

    def __init__(self, owner_id: int | None = None) -> None:
        # Parent validation and lifecycle methods are reused. The path is never
        # read because persistence is implemented by the two methods below.
        self.path = Path("django://trades")
        self._lock = threading.RLock()
        self.owner_id = owner_id

    def _queryset(self):
        if self.owner_id is None:
            raise RuntimeError("Trade store requires an authenticated owner")
        return TradeRecord.objects.filter(owner_id=self.owner_id)

    def _read(self) -> list[dict]:
        queryset = self._queryset().order_by("created_at", "id")
        if transaction.get_connection().in_atomic_block:
            queryset = queryset.select_for_update()
        records = []
        for row in queryset.values(
            "payload",
            "quantity_kind",
            "contract_size",
            "currency_unit",
            "calculation_version",
            "mutation_version",
        ):
            payload = dict(row["payload"])
            for key in ("quantity_kind", "currency_unit", "calculation_version"):
                if row[key] not in (None, ""):
                    payload[key] = row[key]
            if row["contract_size"] is not None:
                payload["contract_size"] = str(row["contract_size"])
            payload["mutation_version"] = row["mutation_version"]
            records.append(payload)
        return records

    def _write(self, trades: list[dict]) -> None:
        ids = {str(item.get("id") or "") for item in trades if item.get("id")}
        self._queryset().exclude(id__in=ids).delete()
        for item in trades:
            trade_id = str(item.get("id") or "")
            if not trade_id:
                continue
            defaults = {
                "owner_id": self.owner_id,
                "status": str(item.get("status") or "open"),
                "payload": dict(item),
            }
            if item.get("quantity_kind") in {"contract", "unit"}:
                defaults["quantity_kind"] = item["quantity_kind"]
            if item.get("contract_size") not in (None, ""):
                defaults["contract_size"] = Decimal(str(item["contract_size"]))
            if item.get("currency_unit") in {"rial", "toman"}:
                defaults["currency_unit"] = item["currency_unit"]
            if item.get("calculation_version") not in (None, ""):
                defaults["calculation_version"] = int(item["calculation_version"])
            defaults["mutation_version"] = int(item.get("mutation_version") or 1)
            TradeRecord.objects.update_or_create(
                id=trade_id,
                defaults=defaults,
            )

    def create(self, payload: dict, quote: dict) -> dict:
        with transaction.atomic():
            self._lock_owner()
            return super().create(payload, quote)

    def update(self, trade_id: str, payload: dict, quote: dict) -> dict:
        with transaction.atomic():
            self._lock_owner()
            return super().update(trade_id, payload, quote)

    def close(self, trade_id: str, quote: dict | None, **kwargs) -> dict:
        with transaction.atomic():
            self._lock_owner()
            return super().close(trade_id, quote, **kwargs)

    def delete(self, trade_id: str) -> None:
        with transaction.atomic():
            self._lock_owner()
            super().delete(trade_id)

    def _lock_owner(self) -> None:
        """Serialize all trade mutations, including the first create."""
        if self.owner_id is None:
            raise RuntimeError("Trade store requires an authenticated owner")
        get_user_model().objects.select_for_update().only("pk").get(pk=self.owner_id)


class DjangoAccountStore(AccountStore):
    """AccountStore-compatible adapter backed by Django's database."""

    def __init__(self, owner_id: int | None = None) -> None:
        self.path = Path("django://account")
        self._lock = threading.RLock()
        self.owner_id = owner_id

    def _require_owner(self) -> int:
        if self.owner_id is None:
            raise RuntimeError("Account store requires an authenticated owner")
        return self.owner_id

    def read(self) -> dict:
        preference = AccountPreference.objects.filter(
            owner_id=self._require_owner()
        ).first()
        return {
            # Decimal is the persistence/calculation source.  The existing API
            # contract remains JSON numeric at this presentation boundary.
            "initial_capital": (
                None
                if preference is None or preference.initial_capital is None
                else float(preference.initial_capital)
            ),
            "cash_balance": (
                None
                if preference is None or preference.cash_balance is None
                else float(preference.cash_balance)
            ),
        }

    def save(self, initial_capital, cash_balance=_UNSET) -> dict:
        value = None
        if initial_capital not in (None, ""):
            value = exact_decimal(initial_capital, name="initial_capital")
            if value <= 0:
                raise ValueError("سرمایه اولیه باید بیشتر از صفر باشد")
        defaults = {"initial_capital": value}
        if cash_balance is not _UNSET:
            if cash_balance in (None, ""):
                defaults["cash_balance"] = None
            else:
                cash = exact_decimal(cash_balance, name="cash_balance")
                if cash < 0:
                    raise ValueError("موجودی نقدی نمی‌تواند منفی باشد")
                defaults["cash_balance"] = cash
        AccountPreference.objects.update_or_create(
            owner_id=self._require_owner(), defaults=defaults
        )
        return self.read()


class DjangoUnderlyingPositionStore(UnderlyingPositionStore):
    def __init__(self, owner_id: int | None = None) -> None:
        self.path = Path("django://underlying-positions")
        self._lock = threading.RLock()
        self.owner_id = owner_id

    def _queryset(self):
        if self.owner_id is None:
            raise RuntimeError("Underlying store requires an authenticated owner")
        return UnderlyingPositionRecord.objects.filter(owner_id=self.owner_id)

    def _read(self) -> list[dict]:
        queryset = self._queryset().order_by("created_at","id")
        if transaction.get_connection().in_atomic_block:
            queryset = queryset.select_for_update()
        records = []
        for row in queryset.values(
            "payload", "quantity_kind", "currency_unit", "calculation_version"
        ):
            payload = dict(row["payload"])
            for key in ("quantity_kind", "currency_unit", "calculation_version"):
                if row[key] not in (None, ""):
                    payload[key] = row[key]
            records.append(payload)
        return records

    def _write(self, items: list[dict]) -> None:
        ids={str(item.get("id") or "") for item in items if item.get("id")}
        self._queryset().exclude(id__in=ids).delete()
        for item in items:
            item_id=str(item.get("id") or "")
            if item_id:
                defaults = {
                    "owner_id": self.owner_id,
                    "status": str(item.get("status") or "open"),
                    "payload": dict(item),
                }
                if item.get("quantity_kind") == "unit":
                    defaults["quantity_kind"] = "unit"
                if item.get("currency_unit") in {"rial", "toman"}:
                    defaults["currency_unit"] = item["currency_unit"]
                if item.get("calculation_version") not in (None, ""):
                    defaults["calculation_version"] = int(item["calculation_version"])
                UnderlyingPositionRecord.objects.update_or_create(
                    id=item_id,
                    defaults=defaults,
                )

    def create(self,payload:dict)->dict:
        with transaction.atomic():
            self._lock_owner()
            return super().create(payload)

    def update(self,position_id:str,payload:dict)->dict:
        with transaction.atomic():
            self._lock_owner()
            return super().update(position_id,payload)

    def create_from_exercise(self,trade:dict)->dict|None:
        with transaction.atomic():
            self._lock_owner()
            return super().create_from_exercise(trade)

    def sell_quantity(self,position_id:str,quantity:float,**kwargs)->dict:
        with transaction.atomic():
            self._lock_owner()
            return super().sell_quantity(position_id,quantity,**kwargs)

    def rebase_released_quantity(self, position_id: str, quantity: float, **kwargs) -> dict:
        with transaction.atomic():
            self._lock_owner()
            return super().rebase_released_quantity(position_id, quantity, **kwargs)

    def delete(self,position_id:str)->None:
        with transaction.atomic():
            self._lock_owner()
            super().delete(position_id)

    def _lock_owner(self) -> None:
        if self.owner_id is None:
            raise RuntimeError("Underlying store requires an authenticated owner")
        get_user_model().objects.select_for_update().only("pk").get(pk=self.owner_id)
