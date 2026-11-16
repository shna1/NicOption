from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from .cbi_mcp import CbiMcpError, StdioMcpClient


class AmarMcpError(RuntimeError):
    pass


@dataclass(frozen=True)
class AmarMcpResult:
    server_name: str
    server_version: str
    payload: dict[str, Any]
    errors: dict[str, str]


TOPICS: dict[str, dict[str, str]] = {
    "population": {
        "label": "جمعیت، نیروی انسانی و آموزش",
        "collection": "new",
        "source_org": "مرکز آمار ایران و ثبت احوال",
        "description": "پیش‌بینی جمعیت، خانوار، رویدادهای حیاتی، بازار کار و آموزش.",
    },
    "household": {
        "label": "بودجه خانوار و توزیع درآمد",
        "collection": "new",
        "source_org": "مرکز آمار ایران",
        "description": "ضریب جینی، سهم دهک‌ها و هزینه و درآمد خانوار شهری و روستایی.",
    },
    "accounts": {
        "label": "حساب‌های ملی تفصیلی",
        "collection": "new",
        "source_org": "مرکز آمار ایران",
        "description": "محصول ناخالص داخلی، ارزش افزوده فعالیت‌ها و درآمد ملی.",
    },
    "budget": {
        "label": "مالی دولت",
        "collection": "new",
        "source_org": "وزارت امور اقتصادی و دارایی",
        "description": "منابع و مصارف بودجه، مالیات و نسبت مالیات به تولید ناخالص داخلی.",
    },
    "trade": {
        "label": "تجارت خارجی و حساب‌های خارجی",
        "collection": "new",
        "source_org": "گمرک و بانک مرکزی",
        "description": "صادرات، واردات، تراز پرداخت‌ها، سرمایه‌گذاری و بدهی خارجی.",
    },
    "energy": {
        "label": "انرژی و آب",
        "collection": "new",
        "source_org": "دستگاه‌های تخصصی بخش انرژی",
        "description": "نفت، گاز، آب و برق با تفکیک تولید، مصرف و تجارت.",
    },
    "industry": {
        "label": "صنعت و معدن",
        "collection": "new",
        "source_org": "وزارت صمت و مرکز آمار ایران",
        "description": "مجوزها، سرمایه، اشتغال و شاخص مقدار تولید صنعت و معدن.",
    },
    "agriculture": {
        "label": "کشاورزی و دام",
        "collection": "new",
        "source_org": "مرکز آمار ایران",
        "description": "دام، کشتار، طیور، تخم‌مرغ و شاخص مقدار تولید کشاورزی.",
    },
    "money": {
        "label": "پول و اعتبار تکمیلی",
        "collection": "complementary",
        "source_org": "بانک مرکزی جمهوری اسلامی ایران",
        "description": "عوامل عرضه نقدینگی، ضریب فزاینده، سپرده و تسهیلات بخشی.",
    },
    "stock": {
        "label": "بازار سرمایه تکمیلی",
        "collection": "complementary",
        "source_org": "بورس تهران، فرابورس و سازمان بورس",
        "description": "شاخص‌ها، ارزش بازار، ارزش معاملات و سرمایه‌گذاری خارجی.",
    },
    "housing": {
        "label": "مسکن و ساختمان تکمیلی",
        "collection": "complementary",
        "source_org": "مرکز آمار ایران و بانک مرکزی",
        "description": "پروانه، سرمایه‌گذاری، قیمت و اجاره در کنار نهاده‌های ساختمانی موجود.",
    },
}

RELEASE_SEARCHES: tuple[tuple[str, str], ...] = (
    ("tourism", "گردشگری"),
    ("research", "تحقیق و توسعه"),
    ("environment", "محیط زیست"),
    ("social_justice", "عدالت اجتماعی"),
)


def configured_command() -> list[str]:
    return shlex.split(str(getattr(settings, "AMAR_MCP_COMMAND", "amar-mcp") or "").strip())


def _call(client: StdioMcpClient, name: str, arguments: dict[str, Any], errors: dict[str, str], key: str) -> dict:
    try:
        return client.call_tool(name, arguments)
    except (CbiMcpError, OSError) as exc:
        errors[key] = str(exc)[:1000]
        return {}


def collect_amar_snapshot(*, year: int = 1405, client_class=StdioMcpClient) -> AmarMcpResult:
    payload: dict[str, Any] = {"macro": {}, "releases": {}, "travel_tables": []}
    errors: dict[str, str] = {}
    timeout = int(getattr(settings, "AMAR_MCP_TIMEOUT_SECONDS", 180))
    try:
        with client_class(configured_command(), timeout=timeout) as client:
            initialized = client.initialize()
            server_info = initialized.get("serverInfo") or {}
            direct_calls = (
                ("labour_force", "am_labour_force", {"measure": "all", "quarters": 16}),
                ("youth_unemployment", "am_labour_force", {"measure": "youth_unemployment", "quarters": 16}),
                ("gdp_quarterly", "am_gdp", {"frequency": "quarterly", "periods": 20}),
                ("gdp_annual", "am_gdp", {"frequency": "annual", "periods": 12}),
                ("population", "am_population", {}),
                ("calendar", "am_calendar", {"year": year}),
            )
            for key, name, arguments in direct_calls:
                value = _call(client, name, arguments, errors, key)
                if value:
                    payload[key] = value

            for topic, metadata in TOPICS.items():
                inventory = _call(client, "am_indicators", {"topic": topic}, errors, f"macro.{topic}.inventory")
                topic_payload = {**metadata, "source": inventory.get("source") or {}, "tables": []}
                for item in inventory.get("tables") or []:
                    number = item.get("n")
                    if not number:
                        continue
                    result = _call(
                        client,
                        "am_indicators",
                        {"topic": topic, "table": str(number), "last": 12, "max_cols": 30},
                        errors,
                        f"macro.{topic}.{number}",
                    )
                    tables = result.get("tables") or []
                    if not tables:
                        continue
                    table = tables[0]
                    topic_payload["tables"].append({"n": number, **table})
                payload["macro"][topic] = topic_payload

            for key, query in RELEASE_SEARCHES:
                arguments = {"query": query, "page": 1}
                if key == "tourism":
                    arguments["kind"] = "time-series"
                result = _call(client, "am_search", arguments, errors, f"releases.{key}")
                if result:
                    payload["releases"][key] = result
                if key != "tourism":
                    continue
                for item in result.get("results") or []:
                    release_id = item.get("id")
                    if not release_id or not (item.get("period") or item.get("frequency")):
                        continue
                    table = _call(
                        client,
                        "am_table",
                        {"id": release_id, "sheet": "1", "max_rows": 160, "max_cols": 80},
                        errors,
                        f"travel_tables.{release_id}",
                    )
                    if table.get("rows"):
                        payload["travel_tables"].append({
                            "id": release_id,
                            "title": item.get("title") or table.get("release") or "سری سفر",
                            "period": item.get("period") or "",
                            "frequency": item.get("frequency") or "",
                            "table": table,
                        })
    except (CbiMcpError, OSError) as exc:
        raise AmarMcpError(str(exc)) from exc
    return AmarMcpResult(
        server_name=str(server_info.get("name") or "amar-mcp"),
        server_version=str(server_info.get("version") or ""),
        payload=payload,
        errors=errors,
    )
