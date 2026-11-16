from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

from .assets import canonical_asset, canonical_tehran_asset, normalize_fa
from .config import Settings
from .dates import parse_user_date
from .history import PriceHistoryClient
from .http import make_session
from .models import Contract, reprice_covered_contract


def _extract_items(payload: object, error_message: str) -> list[dict]:
    """Accept both Bambo's legacy list and its newer {items: [...]} shape."""
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        data = payload.get("data", payload)
        items = data.get("items") if isinstance(data, dict) else None
    else:
        items = None
    if not isinstance(items, list):
        raise RuntimeError(error_message)
    return [row for row in items if isinstance(row, dict)]


class BamboClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = make_session(settings.http_retries)
        self.option_session = make_session(0)
        self.ime_session = make_session(0)
        if settings.bambo_session_cookie:
            self.session.headers["Cookie"] = settings.bambo_session_cookie
            self.option_session.headers["Cookie"] = settings.bambo_session_cookie
        self.price_history = PriceHistoryClient(settings)
        self._hamtaraz_purchase_price: float | None = None
        self._hamtaraz_price_loaded = False
        self._goods_rows_cache: dict[str, list[dict]] = {}
        self._goods_base_price_cache: dict[str, float | None] = {}
        self._tsetmc_tehran_rows_cache: list[dict] | None = None
        self._ime_snapshot_cache: dict[str, list[dict]] | None = None
        self._ime_goods_rows_cache: list[dict] | None = None

    @staticmethod
    def _ime_asset_for_symbol(symbol: str) -> str | None:
        prefix = str(symbol or "").upper()
        families = (
            ("GB", "طلای 24 عیار"),
            ("SL", "شمش نقره"),
            ("NQ", "صندوق نقره کهکشان فیروزه"),
            ("CU", "مس کاتد"),
            ("TL", "صندوق طلای لوتوس"),
            ("KA", "کهربا"),
            ("ZR", "صندوق طلای کارآمد"),
            ("DG", "صندوق طلای درخشان"),
            ("JZ", "صندوق طلای دنا زاگرس"),
        )
        return next((asset for code, asset in families if prefix.startswith(code)), None)

    @staticmethod
    def _positive_number(*values):
        for value in values:
            try:
                number = float(value or 0)
            except (TypeError, ValueError):
                continue
            if number > 0:
                return number
        return None

    @staticmethod
    def _queue_status(bid, ask, bid_volume=0, ask_volume=0) -> str:
        """Infer one-sided queues without treating a stale opposite price as executable."""
        bid = BamboClient._positive_number(bid)
        ask = BamboClient._positive_number(ask)
        bid_volume = BamboClient._positive_number(bid_volume) or 0
        ask_volume = BamboClient._positive_number(ask_volume) or 0
        if bid and bid_volume > 0 and (not ask or ask_volume <= 0):
            return "صف خرید"
        if ask and ask_volume > 0 and (not bid or bid_volume <= 0):
            return "صف فروش"
        return "عادی" if bid and ask else "نامشخص"

    @classmethod
    def _sanitize_order_book_row(cls, row: dict) -> dict:
        """Drop order-book prices that contradict the official/queue price range."""
        item = dict(row)
        invalid: dict[str, str] = {}
        legs = (
            ("base", "bestBidBase", "bestAskBase", "baseQueueStatus", "basePriceMin", "basePriceMax"),
            ("option", "bidPrice1Option", "askPrice1Option", "optionQueueStatus", "optionPriceMin", "optionPriceMax"),
        )
        for leg, bid_key, ask_key, queue_key, min_key, max_key in legs:
            bid = cls._positive_number(item.get(bid_key))
            ask = cls._positive_number(item.get(ask_key))
            minimum = cls._positive_number(item.get(min_key))
            maximum = cls._positive_number(item.get(max_key))
            queue = str(item.get(queue_key) or "نامشخص")
            if queue == "صف خرید" and maximum is None:
                maximum = bid
            elif queue == "صف فروش" and minimum is None:
                minimum = ask
            if bid is not None and (
                (minimum is not None and bid < minimum)
                or (maximum is not None and bid > maximum)
            ):
                invalid[bid_key] = "بهترین پیشنهاد خرید خارج از دامنه مجاز است"
                item[bid_key] = None
            if ask is not None and (
                (minimum is not None and ask < minimum)
                or (maximum is not None and ask > maximum)
            ):
                invalid[ask_key] = "بهترین پیشنهاد فروش خارج از دامنه مجاز است"
                item[ask_key] = None
            item[min_key], item[max_key] = minimum, maximum
        item["quoteQualityWarnings"] = invalid
        item["quoteQualityValid"] = not invalid
        return item

    def _fetch_ime_snapshot(self) -> dict[str, list[dict]]:
        """Read the official IME SignalR snapshot consumed by cdn.ime.co.ir."""
        if self._ime_snapshot_cache is not None:
            return self._ime_snapshot_cache

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.settings.ime_cdn_url}/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        timeout = max(30, self.settings.http_timeout_seconds)
        self.ime_session.get(
            f"{self.settings.ime_cdn_url}/", headers=headers, timeout=timeout
        ).raise_for_status()

        hub_url = f"{self.settings.ime_cdn_url}/realTimeServer"
        connection_data = json.dumps(
            [{"name": "marketshub"}], separators=(",", ":")
        )
        negotiate = self.ime_session.get(
            f"{hub_url}/negotiate",
            params={
                "clientProtocol": "2.1",
                "connectionData": connection_data,
                "_": int(time.time() * 1000),
            },
            headers=headers,
            timeout=timeout,
        )
        negotiate.raise_for_status()
        token = negotiate.json().get("ConnectionToken")
        if not token:
            raise RuntimeError("Unexpected IME SignalR negotiation response")

        common = {
            "transport": "longPolling",
            "clientProtocol": "2.1",
            "connectionToken": token,
            "connectionData": connection_data,
        }
        connected = self.ime_session.get(
            f"{hub_url}/connect",
            params={**common, "tid": 10, "_": int(time.time() * 1000)},
            headers=headers,
            timeout=max(45, timeout),
        )
        connected.raise_for_status()
        message_id = connected.json().get("C")
        if not message_id:
            raise RuntimeError("Unexpected IME SignalR connection response")

        started = self.ime_session.get(
            f"{hub_url}/start", params=common, headers=headers, timeout=timeout
        )
        started.raise_for_status()
        snapshot: dict[str, list[dict]] = {}
        message_names = {
            "updateMarketsInfo": "options",
            "updateCDCMarketsInfo": "continuous",
            "updateSandoqMarketsInfo": "funds",
        }
        for _ in range(4):
            polled = self.ime_session.get(
                f"{hub_url}/poll",
                params={
                    **common,
                    "messageId": message_id,
                    "tid": 10,
                    "_": int(time.time() * 1000),
                },
                headers=headers,
                timeout=max(45, timeout),
            )
            polled.raise_for_status()
            payload = polled.json()
            message_id = payload.get("C", message_id)
            for message in payload.get("M", []):
                key = message_names.get(message.get("M"))
                args = message.get("A")
                rows = args[0] if isinstance(args, list) and args else None
                if key and isinstance(rows, list):
                    snapshot[key] = [row for row in rows if isinstance(row, dict)]
            if all(key in snapshot for key in message_names.values()):
                break
        if "options" not in snapshot:
            raise RuntimeError("IME option snapshot was not received")
        snapshot.setdefault("continuous", [])
        snapshot.setdefault("funds", [])
        self._ime_snapshot_cache = snapshot
        return snapshot

    @staticmethod
    def _normalize_depth_levels(
        row: dict,
        *,
        depth: int,
        bid_price: str,
        bid_volume: str,
        ask_price: str,
        ask_volume: str,
        bid_orders: str | None = None,
        ask_orders: str | None = None,
    ) -> list[dict]:
        """Normalize every aggregated depth level exposed by an official feed."""
        levels: list[dict] = []
        for level in range(1, depth + 1):
            def number(pattern: str | None):
                if not pattern:
                    return None
                try:
                    value = float(row.get(pattern.format(level=level)) or 0)
                except (TypeError, ValueError):
                    return None
                return value if value > 0 else None

            levels.append({
                "level": level,
                "bid_price": number(bid_price),
                "bid_volume": number(bid_volume) or 0,
                "bid_orders": number(bid_orders),
                "ask_price": number(ask_price),
                "ask_volume": number(ask_volume) or 0,
                "ask_orders": number(ask_orders),
            })
        return levels

    def fetch_tsetmc_order_book(self, ins_code: str) -> dict:
        """Fetch all public aggregated TSETMC depth levels (currently five)."""
        response = self.option_session.get(
            f"https://cdn.tsetmc.com/api/BestLimits/{ins_code}",
            timeout=max(15, self.settings.http_timeout_seconds),
        )
        response.raise_for_status()
        rows = response.json().get("bestLimits") or []
        rows = sorted(
            (row for row in rows if isinstance(row, dict)),
            key=lambda row: int(row.get("number") or 0),
        )
        levels = []
        for row in rows:
            def positive(key: str):
                return self._positive_number(row.get(key))
            levels.append({
                "level": int(row.get("number") or len(levels) + 1),
                "bid_price": positive("pMeDem"),
                "bid_volume": positive("qTitMeDem") or 0,
                "bid_orders": positive("zOrdMeDem"),
                "ask_price": positive("pMeOf"),
                "ask_volume": positive("qTitMeOf") or 0,
                "ask_orders": positive("zOrdMeOf"),
            })
        return {"source": "TSETMC", "levels": levels, "depth_limit": len(levels)}

    def fetch_tsetmc_intraday_candles(self, ins_code: str) -> list[dict]:
        """Build official 15-minute candles from TSETMC intraday observations."""
        root = "https://cdn.tsetmc.com/api/ClosingPrice"
        timeout = max(15, self.settings.http_timeout_seconds)
        info_response = self.option_session.get(
            f"{root}/GetClosingPriceInfo/{ins_code}", timeout=timeout
        )
        info_response.raise_for_status()
        info = info_response.json().get("closingPriceInfo") or {}
        trading_date = int(info.get("dEven") or info.get("finalLastDate") or 0)
        if trading_date <= 0:
            return []
        history_response = self.option_session.get(
            f"{root}/GetClosingPriceHistory/{ins_code}/{trading_date}", timeout=timeout
        )
        history_response.raise_for_status()
        rows = history_response.json().get("closingPriceHistory") or []
        if info.get("hEven") and info.get("pDrCotVal"):
            rows = [*rows, info]
        buckets: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
        for row in rows:
            try:
                raw_time = int(row.get("hEven") or 0)
                price = float(row.get("pDrCotVal") or 0)
            except (TypeError, ValueError):
                continue
            if raw_time <= 0 or price <= 0:
                continue
            hour, minute = raw_time // 10000, (raw_time // 100) % 100
            bucket_minute = minute // 15 * 15
            buckets[(hour, bucket_minute)].append((raw_time, price))
        date_text = str(trading_date)
        iso_date = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"
        candles = []
        for (hour, minute), values in sorted(buckets.items()):
            ordered = [price for _, price in sorted(values)]
            candles.append({
                "timestamp": f"{iso_date}T{hour:02d}:{minute:02d}:00+03:30",
                "open": ordered[0], "high": max(ordered),
                "low": min(ordered), "close": ordered[-1],
            })
        return candles

    def fetch_ime_order_book(
        self, *, symbol: str, asset: str, instrument_type: str
    ) -> dict:
        """Fetch every aggregated depth level published in the IME snapshot."""
        snapshot = self._fetch_ime_snapshot()
        if instrument_type == "option":
            row = next(
                (item for item in snapshot["options"]
                 if str(item.get("CallContractCode") or "").strip() == symbol),
                None,
            )
            if not row:
                raise KeyError("نماد اختیار در جریان زنده بورس کالا پیدا نشد")
            levels = self._normalize_depth_levels(
                row, depth=5,
                bid_price="CallBidPrice{level}", bid_volume="CallBidVolume{level}",
                ask_price="CallAskPrice{level}", ask_volume="CallAskVolume{level}",
            )
            last_price = self._positive_number(row.get("CallLastTradedPrice"))
        elif asset in {"طلای 24 عیار", "شمش نقره", "مس کاتد"}:
            code = {
                "طلای 24 عیار": "GoldBar", "شمش نقره": "SilverBar",
                "مس کاتد": "CopperCthd",
            }[asset]
            row = next(
                (item for item in snapshot["continuous"]
                 if str(item.get("ContractCode") or "") == code), None,
            )
            if not row:
                raise KeyError("دارایی پایه در جریان زنده بورس کالا پیدا نشد")
            levels = self._normalize_depth_levels(
                row, depth=3,
                bid_price="BidPrice{level}", bid_volume="BidVolume{level}",
                ask_price="AskPrice{level}", ask_volume="AskVolume{level}",
            )
            last_price = self._positive_number(row.get("LastTradedPrice"))
        else:
            fund_symbol = {
                "صندوق نقره کهکشان فیروزه": "نقرابی",
                "صندوق طلای لوتوس": "طلا", "کهربا": "کهربا",
                "صندوق طلای کارآمد": "زرگر", "صندوق طلای درخشان": "درخشان",
                "صندوق طلای دنا زاگرس": "جواهر",
            }.get(asset)
            row = next(
                (item for item in snapshot["funds"]
                 if normalize_fa(str(item.get("Symbol") or "")) == normalize_fa(fund_symbol or "")),
                None,
            )
            if not row:
                raise KeyError("دارایی پایه در جریان زنده بورس کالا پیدا نشد")
            levels = self._normalize_depth_levels(
                row, depth=5,
                bid_price="DemandPrice{level}", bid_volume="DemandVolume{level}",
                ask_price="OfferPrice{level}", ask_volume="OfferVolume{level}",
                bid_orders="DemandQuantity{level}", ask_orders="OfferQuantity{level}",
            )
            last_price = self._positive_number(row.get("LastPrice"))
        return {
            "source": "IME", "levels": levels, "depth_limit": len(levels),
            "last_price": last_price,
        }

    def _normalize_ime_goods_rows(
        self,
        option_rows: list[dict],
        continuous_rows: list[dict],
        fund_rows: list[dict],
    ) -> list[dict]:
        continuous = {
            str(row.get("ContractCode") or ""): row for row in continuous_rows
        }
        funds = {
            normalize_fa(str(row.get("Symbol") or "")): row for row in fund_rows
        }
        base_sources = {
            "طلای 24 عیار": continuous.get("GoldBar"),
            "شمش نقره": continuous.get("SilverBar"),
            "صندوق نقره کهکشان فیروزه": funds.get(normalize_fa("نقرابی")),
            "مس کاتد": continuous.get("CopperCthd"),
            "صندوق طلای لوتوس": funds.get(normalize_fa("طلا")),
            "کهربا": funds.get(normalize_fa("کهربا")),
            "صندوق طلای کارآمد": funds.get(normalize_fa("زرگر")),
            "صندوق طلای درخشان": funds.get(normalize_fa("درخشان")),
            "صندوق طلای دنا زاگرس": funds.get(normalize_fa("جواهر")),
        }
        today = datetime.now(ZoneInfo("Asia/Tehran")).date()
        normalized: list[dict] = []
        for row in option_rows:
            symbol = str(row.get("CallContractCode") or "").strip()
            asset = self._ime_asset_for_symbol(symbol)
            base = base_sources.get(asset or "")
            if not asset or not base:
                continue
            if asset in {"طلای 24 عیار", "شمش نقره", "مس کاتد"}:
                best_ask_base = self._positive_number(base.get("AskPrice1"))
                best_bid_base = self._positive_number(base.get("BidPrice1"))
                last_base = self._positive_number(base.get("LastTradedPrice"))
                close_base = self._positive_number(base.get("LastSettlementPrice"))
                base_price = self._positive_number(
                    best_ask_base, last_base, close_base,
                )
                base_bid_volume = self._positive_number(base.get("BidVolume1")) or 0
                base_ask_volume = self._positive_number(base.get("AskVolume1")) or 0
            else:
                best_ask_base = self._positive_number(base.get("OfferPrice1"))
                best_bid_base = self._positive_number(base.get("DemandPrice1"))
                last_base = self._positive_number(base.get("LastPrice"))
                close_base = self._positive_number(base.get("FinalPrice"))
                base_price = self._positive_number(
                    best_ask_base, last_base, close_base
                )
                base_bid_volume = self._positive_number(base.get("DemandVolume1")) or 0
                base_ask_volume = self._positive_number(base.get("OfferVolume1")) or 0
            strike = self._positive_number(row.get("StrikePrice"))
            try:
                expiry_date = parse_user_date(str(row.get("CallLastTradingPersianDate") or ""))
            except (TypeError, ValueError):
                continue
            if base_price is None or strike is None:
                continue
            volume = self._positive_number(row.get("CallTradesVolume")) or 0.0
            value_thousand_rials = self._positive_number(row.get("CallTradesValue")) or 0.0
            last_option = self._positive_number(row.get("CallLastTradedPrice"))
            state = "ITM" if base_price > strike else "OTM" if base_price < strike else "ATM"
            option_bid = self._positive_number(row.get("CallBidPrice1"))
            option_ask = self._positive_number(row.get("CallAskPrice1"))
            option_bid_volume = self._positive_number(row.get("CallBidVolume1")) or 0
            option_ask_volume = self._positive_number(row.get("CallAskVolume1")) or 0
            normalized.append(
                self._sanitize_order_book_row({
                    "baseSymbol": asset,
                    "symbolOption": symbol,
                    "askPrice1Base": base_price,
                    "bestAskBase": best_ask_base,
                    "bestBidBase": best_bid_base,
                    "lastTradeBase": last_base,
                    "closingPriceBase": close_base,
                    "previousPriceBase": self._positive_number(
                        base.get("LastSettlementPrice")
                        if asset in {"طلای 24 عیار", "شمش نقره", "مس کاتد"}
                        else base.get("YesterdayPrice")
                    ),
                    "previousPriceBaseDate": (
                        base.get("LastSettlementPricePersianDate")
                        if asset in {"طلای 24 عیار", "شمش نقره", "مس کاتد"}
                        else base.get("ModifyDate")
                    ),
                    "baseQueueStatus": self._queue_status(
                        best_bid_base, best_ask_base, base_bid_volume, base_ask_volume
                    ),
                    "baseBidVolume": base_bid_volume,
                    "baseAskVolume": base_ask_volume,
                    "askPrice1Option": option_ask,
                    "bidPrice1Option": option_bid,
                    "optionBidVolume": option_bid_volume,
                    "optionAskVolume": option_ask_volume,
                    "optionQueueStatus": self._queue_status(
                        option_bid, option_ask, option_bid_volume, option_ask_volume
                    ),
                    "lastTradeOption": last_option,
                    "optionPrice": last_option,
                    "closingPriceOption": self._positive_number(row.get("CallLastSettlementPrice")),
                    "previousPriceOption": self._positive_number(row.get("CallLastSettlementPrice")),
                    "previousPriceOptionDate": row.get("CallLastSettlementPricePersianDate"),
                    "dueDatePrice": strike,
                    "expiration_date": expiry_date.isoformat(),
                    "days": max(0, (expiry_date - today).days),
                    "state": state,
                    "itmPercent": (base_price - strike) / base_price * 100,
                    "value": value_thousand_rials * 1_000,
                    "volume": volume,
                    "code_id": symbol,
                    "close_price": last_option,
                    "vol_transaction": volume,
                    "contractSize": row.get("CallContractSize"),
                    "source": "IME",
                })
            )
        return normalized

    def _fetch_ime_goods_rows(self) -> list[dict]:
        if self._ime_goods_rows_cache is None:
            snapshot = self._fetch_ime_snapshot()
            self._ime_goods_rows_cache = self._normalize_ime_goods_rows(
                snapshot["options"], snapshot["continuous"], snapshot["funds"]
            )
        return [dict(row) for row in self._ime_goods_rows_cache]

    @staticmethod
    def _goods_symbol(row: dict) -> str:
        symbol = str(row.get("symbolOption") or "").strip()
        if symbol:
            return symbol
        title = str(row.get("title") or "").strip()
        match = re.match(r"^([^\s]+)\s+Long Call Strategy\b", title, re.I)
        return match.group(1) if match else ""

    @staticmethod
    def _goods_contract_key(row: dict) -> tuple[str, str, str, str]:
        """Stable fields shared by Bambo's covered and long-call rows."""
        return tuple(
            str(row.get(field) or "")
            for field in (
                "expiration_date",
                "dueDatePrice",
                "bidPrice1Option",
                "askPrice1Option",
            )
        )

    def _fetch_goods_strategy_rows(self, strategy: str) -> list[dict]:
        response = self.session.post(
            self.settings.api_url,
            json={"strategy": strategy},
            timeout=self.settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return _extract_items(response.json(), "Unexpected Bambo API response")

    def _enrich_goods_symbols(
        self, covered_rows: list[dict], long_rows: list[dict]
    ) -> list[dict]:
        symbols_by_key: dict[tuple[str, str, str, str], deque[str]] = defaultdict(deque)
        for row in long_rows:
            symbol = self._goods_symbol(row)
            if symbol:
                symbols_by_key[self._goods_contract_key(row)].append(symbol)

        enriched: list[dict] = []
        for row in covered_rows:
            item = dict(row)
            symbol = self._goods_symbol(item)
            if not symbol:
                candidates = symbols_by_key.get(self._goods_contract_key(item))
                symbol = candidates.popleft() if candidates else ""
            if symbol:
                item["symbolOption"] = symbol
            enriched.append(item)
        return enriched

    def _get_goods_base_price(self, symbol: str) -> float | None:
        prefix = symbol.upper()[:4]
        if prefix not in self._goods_base_price_cache:
            if prefix == "ZRMO":
                try:
                    price = self.price_history.fetch_current_purchase_price(
                        "صندوق طلای کارآمد", "صندوق طلای کارآمد"
                    )
                except Exception:
                    price = None
            elif prefix == "CUMO":
                # Bambo currently copies the option quote into the copper
                # underlying field, while the configured TSETMC resolver has no
                # authoritative copper-cathode spot quote. Exclude it rather
                # than publishing a fabricated return.
                price = None
            else:
                price = None
            self._goods_base_price_cache[prefix] = price
        return self._goods_base_price_cache[prefix]

    def _repair_goods_rows(self, rows: list[dict]) -> list[dict]:
        repaired: list[dict] = []
        for row in rows:
            item = dict(row)
            symbol = self._goods_symbol(item)
            if symbol:
                item["symbolOption"] = symbol

            prefix = symbol.upper()[:4]
            if prefix not in {"CUMO", "ZRMO"}:
                repaired.append(item)
                continue

            base_price = self._get_goods_base_price(symbol)
            if base_price is None:
                continue
            item["askPrice1Base"] = base_price
            item["_basePriceOverridden"] = True
            try:
                strike = float(item.get("dueDatePrice") or 0)
            except (TypeError, ValueError):
                strike = 0.0
            if strike > 0:
                item["state"] = (
                    "ITM" if base_price > strike
                    else "OTM" if base_price < strike
                    else "ATM"
                )
                item["itmPercent"] = (base_price - strike) / base_price * 100
            repaired.append(item)
        return repaired

    def _get_hamtaraz_purchase_price(self) -> float | None:
        if not self._hamtaraz_price_loaded:
            self._hamtaraz_price_loaded = True
            try:
                self._hamtaraz_purchase_price = (
                    self.price_history.fetch_current_purchase_price(
                        "هم‌تراز", "هم_وزن"
                    )
                )
            except Exception:
                self._hamtaraz_purchase_price = None
        return self._hamtaraz_purchase_price

    @staticmethod
    def _repair_tehran_symbols(rows: list[dict]) -> list[dict]:
        """Recover option symbols after Bambo moved them into the row title."""
        repaired: list[dict] = []
        for row in rows:
            item = dict(row)
            if not str(item.get("symbolOption") or "").strip():
                title = str(item.get("title") or "").strip()
                match = re.match(
                    r"^(\S+)\s+(?:Covered Call|Long Underlying) Strategy\b",
                    title,
                    re.I,
                )
                if match:
                    item["symbolOption"] = match.group(1)
            repaired.append(item)
        return repaired

    def _repair_tehran_base_prices(self, rows: list[dict]) -> list[dict]:
        if not any(
            str(row.get("symbolOption") or "").startswith("ضراز") for row in rows
        ):
            return rows
        hamtaraz_price = self._get_hamtaraz_purchase_price()
        repaired: list[dict] = []
        for row in rows:
            symbol = str(row.get("symbolOption") or "")
            if not symbol.startswith("ضراز"):
                repaired.append(row)
                continue
            # Never retain Bambo's mismatched Ham-Vazn price for this family.
            if hamtaraz_price is None:
                continue
            item = dict(row)
            item["askPrice1Base"] = hamtaraz_price
            item["_basePriceOverridden"] = True
            try:
                strike = float(item.get("dueDatePrice") or 0)
            except (TypeError, ValueError):
                strike = 0.0
            if strike > 0:
                item["state"] = (
                    "ITM" if hamtaraz_price > strike
                    else "OTM" if hamtaraz_price < strike
                    else "ATM"
                )
                item["itmPercent"] = (
                    (hamtaraz_price - strike) / hamtaraz_price * 100
                )
            repaired.append(item)
        return repaired

    def fetch_rows(self, strategy: str) -> list[dict]:
        # IME publishes raw quotes; both strategies are calculated locally.
        return self._fetch_ime_goods_rows()

    def fetch_contracts(self) -> list[Contract]:
        contracts: list[Contract] = []
        for row in self.fetch_rows("covered_call"):
            asset = canonical_asset(
                str(row.get("baseSymbol") or ""),
                str(row.get("symbolOption") or ""),
            )
            if asset:
                # Bambo's covered-call return is derived from a hidden last
                # trade even though the table exposes the best bid. Recompute
                # every contract from the visible/executable best bid.
                contracts.append(
                    reprice_covered_contract(Contract.from_api(row, asset), "bid")
                )
        return contracts

    def fetch_option_goods(self) -> list[dict]:
        return self._fetch_ime_goods_rows()

    @staticmethod
    def _normalize_tsetmc_option_rows(rows: list[dict]) -> list[dict]:
        """Convert TSETMC's paired put/call rows to the dashboard call shape."""
        normalized: list[dict] = []
        for row in rows:
            symbol = str(row.get("lVal18AFC_C") or "").strip()
            base_symbol = str(row.get("lval30_UA") or "").strip()
            expiry_raw = str(row.get("endDate") or "").strip()
            if not symbol or not base_symbol or not re.fullmatch(r"\d{8}", expiry_raw):
                continue

            try:
                base_last = float(row.get("pDrCotVal_UA") or 0)
                base_close = float(row.get("pClosing_UA") or 0)
                base_price = base_last if base_last > 0 else base_close
                strike = float(row.get("strikePrice") or 0)
            except (TypeError, ValueError):
                continue
            if base_price <= 0 or strike <= 0:
                continue

            expiry = f"{expiry_raw[:4]}-{expiry_raw[4:6]}-{expiry_raw[6:]}"
            state = "ITM" if base_price > strike else "OTM" if base_price < strike else "ATM"
            last_option = row.get("pDrCotVal_C")
            volume = row.get("qTotTran5J_C")
            transaction_value = row.get("qTotCap_C")
            option_bid = row.get("pMeDem_C")
            option_ask = row.get("pMeOf_C")
            option_bid_volume = row.get("qTitMeDem_C")
            option_ask_volume = row.get("qTitMeOf_C")
            option_queue = BamboClient._queue_status(
                option_bid, option_ask, option_bid_volume, option_ask_volume
            )
            normalized.append(
                {
                    "baseSymbol": base_symbol,
                    "symbolOption": symbol,
                    # TSETMC's option-watch response exposes the underlying's
                    # official last trade (and closing price as fallback).
                    "askPrice1Base": base_price,
                    "bestAskBase": None,
                    "bestBidBase": None,
                    "lastTradeBase": base_last if base_last > 0 else None,
                    "closingPriceBase": base_close if base_close > 0 else None,
                    "previousPriceBase": row.get("priceYesterday_UA"),
                    "baseQueueStatus": "نامشخص",
                    "askPrice1Option": option_ask,
                    "bidPrice1Option": option_bid,
                    "optionBidVolume": option_bid_volume,
                    "optionAskVolume": option_ask_volume,
                    "optionQueueStatus": option_queue,
                    "optionPriceMax": (
                        option_bid if option_queue == "صف خرید" else None
                    ),
                    "optionPriceMin": (
                        option_ask if option_queue == "صف فروش" else None
                    ),
                    "lastTradeOption": last_option,
                    "optionPrice": last_option,
                    "closingPriceOption": row.get("pClosing_C"),
                    "previousPriceOption": row.get("priceYesterday_C"),
                    "dueDatePrice": strike,
                    "expiration_date": expiry,
                    "days": row.get("remainedDay"),
                    "state": state,
                    "itmPercent": (base_price - strike) / base_price * 100,
                    "value": transaction_value,
                    "volume": volume,
                    "code_id": symbol,
                    "close_price": last_option,
                    "vol_transaction": volume,
                    "contractSize": row.get("contractSize"),
                    "insCodeOption": row.get("insCode_C"),
                    "insCodeBase": row.get("uaInsCode"),
                }
            )
        return normalized

    def _fetch_tsetmc_base_quote(self, ins_code: str) -> dict:
        """Return the executable top quote and queue state for one underlying."""
        root = "https://cdn.tsetmc.com/api"
        timeout = max(15, self.settings.http_timeout_seconds)
        limits_response = self.option_session.get(
            f"{root}/BestLimits/{ins_code}", timeout=timeout
        )
        limits_response.raise_for_status()
        limits = limits_response.json().get("bestLimits") or []
        top = next(
            (item for item in limits if int(item.get("number") or 0) == 1),
            limits[0] if limits else {},
        )

        threshold_response = self.option_session.get(
            f"{root}/Instrument/GetInstrumentInfo/{ins_code}", timeout=timeout
        )
        threshold_response.raise_for_status()
        info = threshold_response.json().get("instrumentInfo") or {}
        static = info.get("staticThreshold") or {}
        status_title = None
        status_code = None
        status_date = None
        try:
            status_response = self.option_session.get(
                f"{root}/ClosingPrice/GetClosingPriceInfo/{ins_code}",
                timeout=timeout,
            )
            status_response.raise_for_status()
            closing = status_response.json().get("closingPriceInfo") or {}
            instrument_state = closing.get("instrumentState") or {}
            status_title = str(instrument_state.get("cEtavalTitle") or "").strip() or None
            status_code = str(instrument_state.get("cEtaval") or "").strip() or None
            status_date = closing.get("dEven")
        except Exception:
            # Status enrichment is useful for valuation safety, but a temporary
            # failure must not remove the contract from the option chain.
            pass
        best_bid = self._positive_number(top.get("pMeDem"))
        best_ask = self._positive_number(top.get("pMeOf"))
        max_price = self._positive_number(static.get("psGelStaMax"))
        min_price = self._positive_number(static.get("psGelStaMin"))
        queue = "عادی"
        if best_bid is not None and max_price is not None and best_bid >= max_price:
            queue = "صف خرید"
        elif best_ask is not None and min_price is not None and best_ask <= min_price:
            queue = "صف فروش"
        return {
            "bestAskBase": best_ask,
            "bestBidBase": best_bid,
            "baseBidVolume": self._positive_number(top.get("qTitMeDem")) or 0,
            "baseAskVolume": self._positive_number(top.get("qTitMeOf")) or 0,
            "baseQueueStatus": queue,
            "basePriceMin": min_price,
            "basePriceMax": max_price,
            "baseTradingStatus": status_title,
            "baseTradingStatusCode": status_code,
            "baseTradingStatusDate": status_date,
            # Only the exact tradable state is considered open. Other explicit
            # TSETMC states (for example ممنوع-متوقف) block mark-to-market P/L.
            "baseIsClosed": status_title is not None and status_title != "مجاز",
        }

    def _enrich_tsetmc_base_quotes(self, rows: list[dict]) -> list[dict]:
        codes = sorted({str(row.get("insCodeBase") or "") for row in rows} - {""})
        quotes: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(codes)))) as executor:
            pending = {
                executor.submit(self._fetch_tsetmc_base_quote, code): code
                for code in codes
            }
            for future in as_completed(pending):
                try:
                    quotes[pending[future]] = future.result()
                except Exception:
                    # A missing order book must not hide the option chain.
                    continue
        sanitized: list[dict] = []
        for row in rows:
            quote = quotes.get(str(row.get("insCodeBase") or ""))
            if quote:
                row.update(quote)
                if quote.get("bestAskBase"):
                    row["askPrice1Base"] = quote["bestAskBase"]
                    strike = self._positive_number(row.get("dueDatePrice"))
                    base = quote["bestAskBase"]
                    if strike:
                        row["state"] = "ITM" if base > strike else "OTM" if base < strike else "ATM"
                        row["itmPercent"] = (base - strike) / base * 100
            sanitized.append(self._sanitize_order_book_row(row))
        return sanitized

    def _fetch_tsetmc_tehran_rows(self) -> list[dict]:
        if self._tsetmc_tehran_rows_cache is None:
            response = self.option_session.get(
                self.settings.tsetmc_option_market_watch_url,
                timeout=max(30, self.settings.http_timeout_seconds),
            )
            response.raise_for_status()
            body = response.json()
            raw_rows = body.get("instrumentOptMarketWatch") if isinstance(body, dict) else None
            if not isinstance(raw_rows, list):
                raise RuntimeError("Unexpected TSETMC option market-watch response")
            normalized = self._normalize_tsetmc_option_rows(
                [row for row in raw_rows if isinstance(row, dict)]
            )
            self._tsetmc_tehran_rows_cache = self._enrich_tsetmc_base_quotes(normalized)
        return [dict(row) for row in self._tsetmc_tehran_rows_cache]

    def fetch_tehran_rows(self, strategy: str) -> list[dict]:
        # TSETMC returns the complete call chain rather than precomputed
        # strategies. Both strategies are calculated locally from these rows.
        return self._fetch_tsetmc_tehran_rows()

    @staticmethod
    def _normalize_tehran_market_watch_rows(rows: list[dict]) -> list[dict]:
        """Convert the complete Tehran market watch into the strategy row shape.

        Strategy endpoints only contain contracts that currently qualify for a
        strategy.  The trade picker needs the whole live call-option universe.
        """
        normalized: list[dict] = []
        for row in rows:
            name = str(row.get("name") or "").strip()
            symbol = str(row.get("symbol") or "").strip()
            # The same endpoint also contains put options (اختیارف / ط...).
            if not symbol or not name.startswith("اختیارخ"):
                continue
            expiry = str(
                row.get("miladi_due_date") or row.get("jalali_due_date") or ""
            ).split("T", 1)[0]
            base_ask = row.get("ask_price_1_base")
            try:
                if float(base_ask or 0) <= 0:
                    base_ask = row.get("last_trade_base")
            except (TypeError, ValueError):
                base_ask = row.get("last_trade_base")
            item = {
                "baseSymbol": row.get("base_symbol"),
                "symbolOption": symbol,
                "askPrice1Base": base_ask,
                "askPrice1Option": row.get("ask_price_1_option"),
                "bidPrice1Option": row.get("bid_price_1_option"),
                "lastTradeOption": row.get("last_trade_option"),
                "optionPrice": row.get("last_trade_option"),
                "dueDatePrice": row.get("due_date_price"),
                "expiration_date": expiry,
                "days": row.get("days_until_due"),
                "value": row.get("value"),
            }
            try:
                base_price = float(base_ask or 0)
                strike = float(row.get("due_date_price") or 0)
            except (TypeError, ValueError):
                base_price = strike = 0.0
            if base_price > 0 and strike > 0:
                item["state"] = (
                    "ITM" if base_price > strike
                    else "OTM" if base_price < strike
                    else "ATM"
                )
                item["itmPercent"] = (base_price - strike) / base_price * 100
            normalized.append(item)
        return normalized

    def fetch_tehran_market_watch(self) -> list[dict]:
        """Fetch every currently listed Tehran call option directly from TSETMC."""
        return self._fetch_tsetmc_tehran_rows()

    def fetch_tehran_contracts(self, rows: list[dict] | None = None) -> list[Contract]:
        """Build covered-call contracts from the complete Tehran call universe.

        TSETMC's market-watch endpoint supplies the complete live call universe,
        including chains that third-party strategy endpoints may omit.
        """
        contracts: list[Contract] = []
        source_rows = rows if rows is not None else self.fetch_tehran_rows("covered_call")
        for row in source_rows:
            asset = canonical_tehran_asset(
                str(row.get("baseSymbol") or ""),
                str(row.get("symbolOption") or ""),
            )
            if asset and row.get("symbolOption"):
                contract = Contract.from_api(row, asset)
                # Always derive the result from the visible executable best
                # bid; strategy endpoint returns and market-watch rows are not
                # guaranteed to share the same calculation basis.
                contracts.append(reprice_covered_contract(contract, "bid"))
        return contracts
