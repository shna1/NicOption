from __future__ import annotations

import re
import unicodedata


def canonical_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"\s*[（(][0-9۰-۹٠-٩]+[）)]\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    compact = text.replace("‌", " ").strip()
    folded = compact.casefold()
    if folded.startswith("پایه پولی از سمت مصارف") or folded.startswith("پايه پولي از سمت مصارف"):
        return "پایه پولی"
    if folded.startswith("پایه پولی") or folded.startswith("پايه پولي"):
        return "پایه پولی"
    return compact


def merge_series_items(items: list[dict]) -> list[dict]:
    """Join duplicate CBI table rows into one dated series per indicator."""
    grouped: dict[str, dict] = {}
    for item in items:
        canonical = canonical_name(item.get("name"))
        current = grouped.setdefault(canonical, {**item, "name": canonical, "points_by_period": {}, "merged_from": []})
        current["merged_from"].append(str(item.get("name") or ""))
        for point in item.get("points") or []:
            period = str(point.get("period") or "").strip()
            if not period:
                continue
            old = current["points_by_period"].get(period)
            if old is None or old.get("value") in (None, ""):
                current["points_by_period"][period] = point
    result = []
    for item in grouped.values():
        item["points"] = list(item.pop("points_by_period").values())
        item["merged_from"] = sorted(set(item["merged_from"]))
        result.append(item)
    return result
