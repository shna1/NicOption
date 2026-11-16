from __future__ import annotations

import json
import os
import selectors
import shlex
import subprocess
import time
import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from .cbi_series import merge_series_items


class CbiMcpError(RuntimeError):
    pass


@dataclass(frozen=True)
class CbiMcpResult:
    server_name: str
    server_version: str
    payload: dict[str, Any]
    errors: dict[str, str]


class StdioMcpClient:
    """Small JSON-RPC client for the cbi-mcp stdio transport."""

    def __init__(self, command: list[str], timeout: int = 120):
        if not command:
            raise CbiMcpError("فرمان اجرای cbi-mcp تنظیم نشده است")
        self.command = command
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self._request_id = 0

    def __enter__(self):
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=os.environ.copy(),
        )
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.process:
            return
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def _send(self, message: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise CbiMcpError("اتصال MCP برقرار نیست")
        self.process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _read_response(self, request_id: int) -> dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise CbiMcpError("خروجی MCP در دسترس نیست")
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + self.timeout
        try:
            while time.monotonic() < deadline:
                events = selector.select(max(0, deadline - time.monotonic()))
                if not events:
                    break
                line = self.process.stdout.readline()
                if not line:
                    stderr = self.process.stderr.read().strip() if self.process.stderr else ""
                    raise CbiMcpError(stderr or "cbi-mcp پیش از پاسخ بسته شد")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    error = message["error"]
                    raise CbiMcpError(str(error.get("message") if isinstance(error, dict) else error))
                return message.get("result") or {}
        finally:
            selector.close()
        raise CbiMcpError(f"پاسخ cbi-mcp بیش از {self.timeout} ثانیه طول کشید")

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        return self._read_response(request_id)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self) -> dict[str, Any]:
        result = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "nicoption", "version": "1.0"},
        })
        self.notify("notifications/initialized")
        return result

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            text = " ".join(item.get("text", "") for item in result.get("content", []) if item.get("type") == "text")
            raise CbiMcpError(text or f"اجرای {name} ناموفق بود")
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        for item in result.get("content", []):
            if item.get("type") != "text":
                continue
            try:
                parsed = json.loads(item.get("text") or "")
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise CbiMcpError(f"پاسخ {name} ساختار JSON معتبر ندارد")


TOOL_CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("cb_exchange_rates", {"currencies": ["USD", "EUR", "AED", "TRY", "CNY", "GBP", "JPY"]}),
    ("cb_rate_history", {"currency": "USD"}),
    ("cb_inflation", {"annual_years": 10}),
    ("cb_policy_rates", {"limit": 16}),
    ("cb_liquidity", {"limit": 3}),
    ("cb_bond_auctions", {"limit": 2}),
    ("cb_open_market", {"limit": 4}),
    ("cb_news", {"limit": 8}),
    ("cb_publications", {"kind": "economic_trends", "limit": 4}),
    ("cb_publications", {"kind": "monetary_reports", "limit": 4}),
    ("cb_publications", {"kind": "annual_review", "limit": 4}),
    ("cb_publications", {"kind": "interbank_reports", "limit": 4}),
    ("cb_statistics", {"section": "monetary", "max_rows": 80}),
    ("cb_statistics", {"section": "balance_of_payments", "max_rows": 80}),
    ("cb_statistics", {"section": "fiscal", "max_rows": 80}),
    ("cb_statistics", {"section": "capital_market", "max_rows": 80}),
)

PERSIAN_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)
STATISTICS_HISTORY = {
    "monetary": {"label": "پول و اعتبار", "sheet": "متغیرهای عمده", "value_index": 2, "unit": "هزار میلیارد ریال"},
    "balance_of_payments": {"label": "تراز پرداخت‌ها", "sheet": "نرخ دلار", "value_index": None, "unit": "ریال"},
    "fiscal": {"label": "مالی دولت", "sheet": "جدول گزيده1", "value_index": 2, "unit": "هزار میلیارد ریال"},
    "capital_market": {"label": "بازار سرمایه", "sheet": "شاخص فعالیت", "value_index": 3, "unit": "واحد اعلام‌شده در جدول"},
}


def _payload_key(name: str, arguments: dict[str, Any]) -> str:
    if name == "cb_publications":
        return f"publications_{arguments['kind']}"
    if name == "cb_statistics":
        return f"statistics_{arguments['section']}"
    return name.removeprefix("cb_")


def configured_command() -> list[str]:
    return shlex.split(str(getattr(settings, "CBI_MCP_COMMAND", "cbi-mcp") or "").strip())


def _period_parts(value: str) -> tuple[int, int]:
    match = re.search(r"(\d{4})\s+([^\s]+)", str(value or ""))
    if not match or match.group(2) not in PERSIAN_MONTHS:
        raise CbiMcpError(f"دوره آماری بانک مرکزی قابل تشخیص نیست: {value}")
    return int(match.group(1)), PERSIAN_MONTHS.index(match.group(2)) + 1


def _previous_periods(year: int, month: int, count: int = 18):
    index = year * 12 + month - 1
    for offset in range(count):
        current = index - offset
        y, zero_month = divmod(current, 12)
        yield y, zero_month + 1


def _numeric_values(row: list[Any]) -> list[int | float]:
    return [value for value in row if isinstance(value, (int, float)) and not isinstance(value, bool)]


def _series_from_snapshots(section: str, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config = STATISTICS_HISTORY[section]
    points_by_name: dict[str, list[dict[str, Any]]] = {}
    if section == "balance_of_payments":
        for snapshot in reversed(snapshots):
            rows = snapshot.get("rows") or []
            header = next((row for row in rows if len(row) >= 4 and sum(isinstance(x, str) for x in row[:4]) >= 3), [])
            values_row = next((row for row in rows if len(_numeric_values(row)) >= 4 and any(isinstance(x, str) and x in PERSIAN_MONTHS for x in row)), [])
            values = _numeric_values(values_row)
            names = [str(value).strip() for value in header if isinstance(value, str) and not value.startswith("سال")][:4]
            for name, value in zip(names, values[:4]):
                points_by_name.setdefault(name, []).append({"period": snapshot["period"], "value": value})
    else:
        for snapshot in reversed(snapshots):
            group = ""
            for row in snapshot.get("rows") or []:
                strings = [str(value).strip() for value in row if isinstance(value, str) and str(value).strip()]
                numbers = _numeric_values(row)
                if not numbers or not strings:
                    continue
                if section == "capital_market" and len(strings) >= 2:
                    group = strings[0]
                    name = f"{group} · {strings[1]}"
                elif section == "capital_market" and len(strings) == 1:
                    name = f"{group} · {strings[0]}" if group else strings[0]
                else:
                    name = strings[0]
                if name.strip() in {"_", "#", "-"} or name.rstrip().endswith(" · _"):
                    continue
                index = int(config["value_index"])
                if len(numbers) <= index:
                    continue
                points_by_name.setdefault(name, []).append({"period": snapshot["period"], "value": numbers[index]})
    series = []
    for name, points in points_by_name.items():
        unique = {point["period"]: point for point in points}
        normalized = list(unique.values())
        if normalized:
            series.append({"name": name, "unit": config["unit"], "points": normalized})
    return merge_series_items(series)


def _collect_statistics_history(client, payload: dict[str, Any], errors: dict[str, str]) -> dict[str, Any]:
    result = {"sections": []}
    for section, config in STATISTICS_HISTORY.items():
        latest = payload.get(f"statistics_{section}") or {}
        try:
            year, month = _period_parts(latest.get("period", ""))
        except CbiMcpError as exc:
            errors[f"statistics_history_{section}"] = str(exc)
            continue
        snapshots: list[dict[str, Any]] = []
        for candidate_year, candidate_month in _previous_periods(year, month, 18):
            if len(snapshots) >= 12:
                break
            try:
                item = client.call_tool("cb_statistics", {
                    "section": section,
                    "year": candidate_year,
                    "month": candidate_month,
                    "sheet": config["sheet"],
                    "max_rows": 200,
                })
            except CbiMcpError:
                continue
            snapshots.append({
                "period": item.get("period"),
                "sheet": item.get("sheet"),
                "file": item.get("file"),
                "rows": item.get("rows") or [],
            })
        series = _series_from_snapshots(section, snapshots)
        if not series:
            errors[f"statistics_history_{section}"] = "از ردیف‌های عددی این حوزه سری زمانی قابل اتکا ساخته نشد"
        result["sections"].append({
            "key": section,
            "label": config["label"],
            "sheet": config["sheet"],
            "period_count": len(snapshots),
            "series": series,
        })
    return result


def collect_cbi_snapshot(*, client_class=StdioMcpClient) -> CbiMcpResult:
    payload: dict[str, Any] = {}
    errors: dict[str, str] = {}
    timeout = int(getattr(settings, "CBI_MCP_TIMEOUT_SECONDS", 120))
    with client_class(configured_command(), timeout=timeout) as client:
        initialized = client.initialize()
        server_info = initialized.get("serverInfo") or {}
        for name, arguments in TOOL_CALLS:
            key = _payload_key(name, arguments)
            try:
                payload[key] = client.call_tool(name, arguments)
            except CbiMcpError as exc:
                errors[key] = str(exc)[:1000]
        payload["statistics_time_series"] = _collect_statistics_history(client, payload, errors)
    return CbiMcpResult(
        server_name=str(server_info.get("name") or "cbi-mcp"),
        server_version=str(server_info.get("version") or ""),
        payload=payload,
        errors=errors,
    )
