from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Prefetch
from django.db.models import Q
from django.utils import timezone

from bambo_bot.dates import format_jalali_date, gregorian_to_jalali, jalali_to_gregorian

from .models import EconomicIndicator, IndicatorObservation, IndicatorRelease, IndicatorSource
from .economic_data import freshness_deadline


LOGGER = logging.getLogger(__name__)

DERIVED_SCALE = Decimal("0.000000000001")
MARKET_PRICE_CODES = {
    "IR_USD_FREE_MARKET",
    "IR_COIN_BAHAR_AZADI",
    "IR_GOLD_18K",
    "IR_TETHER",
    "IR_TEDPIX",
}


def _years_ago(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _months_ago(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _jalali_months_ago(value: date, months: int) -> date:
    jalali_year, jalali_month, _ = gregorian_to_jalali(value.year, value.month, value.day)
    month_index = jalali_year * 12 + jalali_month - 1 - months
    target_year, zero_based_month = divmod(month_index, 12)
    return date(*jalali_to_gregorian(target_year, zero_based_month + 1, 1))


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(DERIVED_SCALE)


def _point_map(item: dict) -> dict[date, dict]:
    return {date.fromisoformat(point["period_date"]): point for point in item.get("series", [])}


def _derived_freshness(period: date | None) -> dict:
    if period is None:
        return {"status": "pending", "label": "در انتظار داده پایه"}
    deadline = period + timedelta(days=31 + 45)
    if deadline < timezone.localdate():
        return {"status": "stale", "label": "داده پایه قدیمی", "stale_after": deadline.isoformat()}
    return {"status": "fresh", "label": "به‌روز", "stale_after": deadline.isoformat()}


def _derived_point(period: date, value: Decimal, inputs: list[dict]) -> dict:
    published = [item.get("published_at") for item in inputs if item.get("published_at")]
    collected = [item.get("collected_at") for item in inputs if item.get("collected_at")]
    revisions = [int(item.get("revision") or 0) for item in inputs]
    return {
        "period_date": period.isoformat(),
        "period_date_jalali": format_jalali_date(period),
        "value": _decimal(_rounded(value)),
        "published_at": max(published) if published else None,
        "collected_at": max(collected) if collected else None,
        "revision": max(revisions, default=0),
        "status": "published",
    }


def _derived_indicator(*, code: str, name_fa: str, name_en: str, unit: str,
                       definition: str, description: str, inputs: list[str],
                       series: list[dict], source_items: list[dict],
                       category: str = "macro") -> dict:
    current = series[-1] if series else None
    previous = series[-2] if len(series) > 1 else None
    change = Decimal(current["value"]) - Decimal(previous["value"]) if current and previous else None
    change_percent = None
    if change is not None and Decimal(previous["value"]) != 0:
        change_percent = change / Decimal(previous["value"]) * Decimal("100")
    source_names = [item.get("source", {}).get("name") for item in source_items]
    source_urls = [item.get("source", {}).get("url") for item in source_items]
    return {
        "code": code,
        "name_fa": name_fa,
        "name_en": name_en,
        "kind": "analytical",
        "category": category,
        "frequency": "monthly",
        "unit": unit,
        "definition": definition,
        "current": {
            **(current or {"value": None, "period_date": None, "period_date_jalali": None, "published_at": None, "collected_at": None, "revision": None, "status": None}),
            "previous_value": previous["value"] if previous else None,
            "change": _decimal(_rounded(change)) if change is not None else None,
            "change_percent": _decimal(_rounded(change_percent)) if change_percent is not None else None,
        },
        "freshness": _derived_freshness(date.fromisoformat(current["period_date"]) if current else None),
        "source": {
            "name": " + ".join(dict.fromkeys(name for name in source_names if name)) or "داده پایه ثبت نشده",
            "organization": "nicoption",
            "type": "derived",
            "url": next((url for url in source_urls if url), None),
        },
        "methodology": {
            "description": description,
            "model_version": "economic-derived-v1",
            "inputs": inputs,
        },
        "access": {
            "free_history_years": 5,
            "full_history_requires_subscription": True,
            "full_history_granted": False,
        },
        "series": series,
    }


def _growth_series(source: dict, prior_period) -> list[dict]:
    points = _point_map(source)
    series = []
    for period, point in sorted(points.items()):
        prior = points.get(prior_period(period))
        if prior is None or Decimal(prior["value"]) == 0:
            continue
        value = (Decimal(point["value"]) / Decimal(prior["value"]) - Decimal("1")) * Decimal("100")
        series.append(_derived_point(period, value, [point, prior]))
    return series


def _growth_indicator(source: dict, *, code: str, name_fa: str, name_en: str,
                      rate_type: str, calendar: str = "gregorian") -> dict:
    months_ago = _jalali_months_ago if calendar == "solar_hijri" else _months_ago
    if rate_type == "yoy":
        series = _growth_series(
            source,
            (lambda period: months_ago(period, 12))
            if calendar == "solar_hijri"
            else (lambda period: _years_ago(period, 1)),
        )
        definition = f"رشد سالانه {source['name_fa']}"
        description = "((مقدار ماه جاری ÷ مقدار ماه مشابه سال قبل) − ۱) × ۱۰۰"
        calculation = "((current / same_month_last_year) - 1) * 100"
    elif rate_type == "mom":
        series = _growth_series(source, lambda period: months_ago(period, 1))
        definition = f"رشد ماهانه {source['name_fa']}"
        description = "((مقدار ماه جاری ÷ مقدار ماه قبل) − ۱) × ۱۰۰"
        calculation = "((current / previous_month) - 1) * 100"
    else:
        raise ValueError(f"Unsupported growth rate type: {rate_type}")
    result = _derived_indicator(
        code=code, name_fa=name_fa, name_en=name_en, unit="درصد",
        definition=definition, description=description,
        inputs=[source["code"]], series=series, source_items=[source],
        category=source.get("category", "macro"),
    )
    result["methodology"].update({
        "primary_rate": rate_type,
        "calculation": calculation,
        "calendar": calendar,
    })
    return result


def _ratio_indicator(numerator: dict, denominator: dict, *, code: str, name_fa: str,
                     name_en: str, definition: str, description: str,
                     subtract_denominator: bool = False) -> dict:
    numerator_points = _point_map(numerator)
    denominator_points = _point_map(denominator)
    series = []
    for period in sorted(set(numerator_points) & set(denominator_points)):
        top = Decimal(numerator_points[period]["value"])
        bottom = Decimal(denominator_points[period]["value"])
        if bottom == 0:
            continue
        value = (top - bottom) / bottom if subtract_denominator else top / bottom
        series.append(_derived_point(period, value, [numerator_points[period], denominator_points[period]]))
    return _derived_indicator(
        code=code, name_fa=name_fa, name_en=name_en, unit="برابر",
        definition=definition, description=description,
        inputs=[numerator["code"], denominator["code"]], series=series,
        source_items=[numerator, denominator],
    )


def _derived_indicators(raw_by_code: dict[str, dict]) -> list[dict]:
    derived = []
    monetary_base = raw_by_code.get("IR_MONETARY_BASE")
    liquidity = raw_by_code.get("IR_M2")
    money = raw_by_code.get("IR_MONEY")
    if monetary_base:
        derived.append(_growth_indicator(
            monetary_base, code="IR_MONETARY_BASE_YOY_GROWTH",
            name_fa="رشد سالانه پایه پولی", name_en="Monetary Base YoY Growth",
            rate_type="yoy",
        ))
        derived.append(_growth_indicator(
            monetary_base, code="IR_MONETARY_BASE_MOM_GROWTH",
            name_fa="رشد ماهانه پایه پولی", name_en="Monetary Base MoM Growth",
            rate_type="mom",
        ))
    if liquidity:
        derived.append(_growth_indicator(
            liquidity, code="IR_M2_YOY_GROWTH",
            name_fa="رشد سالانه نقدینگی", name_en="Liquidity YoY Growth",
            rate_type="yoy",
        ))
        derived.append(_growth_indicator(
            liquidity, code="IR_M2_MOM_GROWTH",
            name_fa="رشد ماهانه نقدینگی", name_en="Liquidity MoM Growth",
            rate_type="mom",
        ))
    if liquidity and monetary_base:
        derived.append(_ratio_indicator(
            liquidity, monetary_base, code="IR_MONEY_MULTIPLIER",
            name_fa="ضریب فزاینده نقدینگی", name_en="Money Multiplier",
            definition="نسبت حجم نقدینگی به پایه پولی",
            description="نقدینگی ÷ پایه پولی",
        ))
    if liquidity and money:
        derived.append(_ratio_indicator(
            liquidity, money, code="IR_QUASI_MONEY_TO_MONEY",
            name_fa="شبه‌پول به پول", name_en="Quasi-money to Money Ratio",
            definition="نسبت شبه‌پول به پول؛ شبه‌پول برابر نقدینگی منهای پول است",
            description="(نقدینگی − پول) ÷ پول", subtract_denominator=True,
        ))
    market_growth_specs = (
        ("IR_USD_FREE_MARKET", "IR_USD_FREE_MARKET", "قیمت دلار بازار آزاد", "Free-Market USD/IRR"),
        ("IR_COIN_BAHAR_AZADI", "IR_COIN_BAHAR_AZADI", "قیمت سکه بهار آزادی", "Bahar Azadi Coin Price"),
        ("IR_GOLD_18K", "IR_GOLD_18K", "قیمت طلای ۱۸ عیار", "18K Gold Price"),
        ("IR_TETHER", "IR_TETHER", "قیمت تتر", "Tether Price"),
        ("IR_TEDPIX", "IR_TEDPIX", "شاخص کل بورس تهران", "Tehran Stock Exchange Total Index"),
    )
    for source_code, derived_prefix, name_fa, name_en in market_growth_specs:
        source = raw_by_code.get(source_code)
        if not source:
            continue
        derived.append(_growth_indicator(
            source,
            code=f"{derived_prefix}_YOY_CHANGE",
            name_fa=f"رشد سالانه {name_fa}",
            name_en=f"{name_en} YoY Growth",
            rate_type="yoy",
            calendar="solar_hijri",
        ))
        derived.append(_growth_indicator(
            source,
            code=f"{derived_prefix}_MOM_CHANGE",
            name_fa=f"رشد ماهانه {name_fa}",
            name_en=f"{name_en} MoM Growth",
            rate_type="mom",
            calendar="solar_hijri",
        ))
    return derived


def _freshness(indicator: EconomicIndicator, current: IndicatorObservation | None) -> dict:
    if current is None:
        return {"status": "pending", "label": "در انتظار انتشار"}
    deadline = freshness_deadline(indicator, current.period_date)
    if deadline < timezone.localdate():
        return {"status": "stale", "label": "داده قدیمی", "stale_after": deadline.isoformat()}
    return {"status": "fresh", "label": "به‌روز", "stale_after": deadline.isoformat()}


def _source_payload(source) -> dict:
    return {
        "name": source.name,
        "organization": source.organization,
        "type": source.source_type,
        "url": source.data_url or source.homepage_url or None,
    }


def _serialize_indicator(indicator: EconomicIndicator) -> dict:
    observations = list(indicator.current_observations)
    if indicator.code in MARKET_PRICE_CODES:
        jalali_observations = [
            item for item in observations if ":jalali:" in (item.external_id or "")
        ]
        if jalali_observations:
            observations = jalali_observations
    by_source: dict[int, list[IndicatorObservation]] = {}
    for observation in observations:
        by_source.setdefault(observation.source_id, []).append(observation)
    source_links = list(indicator.prefetched_source_links)
    selected_source_id = next((link.source_id for link in source_links if link.is_primary and link.source_id in by_source), None)
    if selected_source_id is None:
        selected_source_id = next((link.source_id for link in source_links if link.source_id in by_source), None)
    if selected_source_id is None and observations:
        selected_source_id = max(observations, key=lambda item: item.period_date).source_id
    series = sorted(by_source.get(selected_source_id, []), key=lambda item: item.period_date)
    current = series[-1] if series else None
    previous = series[-2] if len(series) > 1 else None
    change = current.value - previous.value if current and previous else None
    change_percent = None
    if change is not None and previous.value != 0:
        change_percent = change / previous.value * Decimal("100")
    source = current.source if current else next((link.source for link in source_links if link.is_primary), None)
    source_payload = _source_payload(source) if source else {}
    if current and current.source_url:
        source_payload["url"] = current.source_url
    category = "capital" if indicator.category == EconomicIndicator.Category.CAPITAL_MARKET else indicator.category
    return {
        "code": indicator.code,
        "name_fa": indicator.name_fa,
        "name_en": indicator.name_en,
        "kind": indicator.kind,
        "category": category,
        "frequency": indicator.frequency,
        "unit": indicator.unit,
        "definition": indicator.definition,
        "current": {
            "value": _decimal(current.value) if current else None,
            "period_date": current.period_date.isoformat() if current else None,
            "period_date_jalali": format_jalali_date(current.period_date) if current else None,
            "published_at": current.published_at.isoformat() if current and current.published_at else None,
            "collected_at": current.collected_at.isoformat() if current else None,
            "revision": current.revision if current else None,
            "status": current.status if current else None,
            "previous_value": _decimal(previous.value) if previous else None,
            "change": _decimal(change),
            "change_percent": _decimal(change_percent),
        },
        "freshness": _freshness(indicator, current),
        "source": source_payload,
        "access": {
            "free_history_years": indicator.free_history_years,
            "full_history_requires_subscription": indicator.full_history_requires_subscription,
            "full_history_granted": False,
        },
        "series": [
            {
                "period_date": item.period_date.isoformat(),
                "period_date_jalali": format_jalali_date(item.period_date),
                "value": _decimal(item.value),
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "collected_at": item.collected_at.isoformat(),
                "revision": item.revision,
                "status": item.status,
            }
            for item in series
        ],
    }


def economic_indicators_payload() -> dict:
    today = timezone.localdate()
    broadest_cutoff = _years_ago(today, 6)
    current_observations = IndicatorObservation.objects.filter(
        is_current_revision=True,
        period_date__gte=broadest_cutoff,
    ).select_related("source").order_by("period_date")
    source_links = IndicatorSource.objects.filter(source__is_active=True).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=today),
        Q(valid_to__isnull=True) | Q(valid_to__gte=today),
    ).select_related("source").order_by("priority", "source__name")
    indicators = EconomicIndicator.objects.filter(is_active=True).prefetch_related(
        Prefetch("observations", queryset=current_observations, to_attr="current_observations"),
        Prefetch("source_links", queryset=source_links, to_attr="prefetched_source_links"),
    )
    payload_indicators = []
    raw_by_code = {}
    for indicator in indicators:
        try:
            item = _serialize_indicator(indicator)
            raw_by_code[item["code"]] = {**item, "series": list(item["series"])}
            years = max(1, indicator.free_history_years)
            cutoff = _years_ago(today, years).isoformat()
            item["series"] = [point for point in item["series"] if point["period_date"] >= cutoff]
            if item["code"] != "IR_MONEY":
                payload_indicators.append(item)
        except Exception:
            LOGGER.exception("Economic indicator serialization failed", extra={"indicator_code": indicator.code})
            payload_indicators.append({
                "code": indicator.code,
                "name_fa": indicator.name_fa,
                "name_en": indicator.name_en,
                "kind": indicator.kind,
                "category": indicator.category,
                "frequency": indicator.frequency,
                "error": "indicator_unavailable",
            })
    inflation_template = raw_by_code.get("IR-INF")
    cpi = raw_by_code.get("IR_CPI")
    if inflation_template and cpi:
        annual_inflation = _growth_indicator(
            cpi,
            code=inflation_template["code"],
            name_fa=f"{inflation_template['name_fa']} سالانه",
            name_en="Consumer Inflation YoY",
            rate_type="yoy",
        )
        monthly_inflation = _growth_indicator(
            cpi,
            code="IR-INF_MOM",
            name_fa=f"{inflation_template['name_fa']} ماهانه",
            name_en="Consumer Inflation MoM",
            rate_type="mom",
        )
        inflation_cutoff = _years_ago(
            today,
            max(1, int(inflation_template["access"]["free_history_years"])),
        ).isoformat()
        for rate in (annual_inflation, monthly_inflation):
            rate["series"] = [
                point for point in rate["series"]
                if point["period_date"] >= inflation_cutoff
            ]
        separated_inflation = []
        for item in payload_indicators:
            if item.get("code") == inflation_template["code"]:
                separated_inflation.extend((annual_inflation, monthly_inflation))
            else:
                separated_inflation.append(item)
        payload_indicators = separated_inflation
    derived_cutoff = _years_ago(today, 5).isoformat()
    for item in _derived_indicators(raw_by_code):
        item["series"] = [point for point in item["series"] if point["period_date"] >= derived_cutoff]
        payload_indicators.append(item)
    releases = IndicatorRelease.objects.filter(
        expected_at__gte=timezone.now(),
        status__in=(IndicatorRelease.Status.SCHEDULED, IndicatorRelease.Status.DELAYED),
    ).select_related("indicator", "source").order_by("expected_at")[:50]
    return {
        "generated_at": timezone.now().isoformat(),
        "indicators": payload_indicators,
        "upcoming_releases": [
            {
                "release_date": item.expected_at.isoformat(),
                "indicator_code": item.indicator.code,
                "indicator_name": item.indicator.name_fa,
                "period_date": item.period_date.isoformat(),
                "period_label": item.period_date.isoformat(),
                "publisher": item.source.organization or item.source.name,
                "status": item.status,
                "status_label": item.get_status_display(),
                "date_is_tentative": item.status == IndicatorRelease.Status.DELAYED,
            }
            for item in releases
        ],
    }
