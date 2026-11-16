#!/usr/bin/env python3
"""Independent validation for prepared website CSV outputs."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


output_dir = Path("outputs/website_data_prepared")
main = pd.read_csv(output_dir / "website_main_data.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
detailed = pd.read_csv(output_dir / "website_detailed_data.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
metadata = pd.read_csv(output_dir / "website_series_metadata.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
quality = pd.read_csv(output_dir / "data_quality_report.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
combined = pd.concat([main, detailed], ignore_index=True)


def period_key(date_text: str, frequency: str) -> int:
    year, month, _ = map(int, date_text.split("-"))
    return year * 12 + month - 1 if frequency == "monthly" else year * 4 + (month - 1) // 3


def rounded_pct(current: str, base: str) -> str:
    value = ((Decimal(current) / Decimal(base)) - 1) * 100
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


spot_checks = []
for frequency, period_column, offset in [
    ("monthly", "calc_growth_mom_pct", 1),
    ("quarterly", "calc_growth_qoq_pct", 1),
]:
    subset = combined[(combined["frequency"] == frequency) & (combined[period_column] != "") & (combined["calc_growth_yoy_pct"] != "")]
    sample = subset.iloc[-1]
    series = combined[(combined["source_file"] == sample["source_file"]) & (combined["technical_id"] == sample["technical_id"])].copy()
    lookup = {period_key(row.jalali_date, frequency): row for row in series.itertuples() if row.value}
    key = period_key(sample["jalali_date"], frequency)
    previous = lookup[key - offset]
    year_offset = 12 if frequency == "monthly" else 4
    previous_year = lookup[key - year_offset]
    expected_period = rounded_pct(sample["value"], previous.value)
    expected_yoy = rounded_pct(sample["value"], previous_year.value)
    spot_checks.append(
        {
            "frequency": frequency,
            "technical_id": sample["technical_id"],
            "jalali_date": sample["jalali_date"],
            "period_expected": expected_period,
            "period_actual": sample[period_column],
            "yoy_expected": expected_yoy,
            "yoy_actual": sample["calc_growth_yoy_pct"],
            "pass": expected_period == sample[period_column] and expected_yoy == sample["calc_growth_yoy_pct"],
        }
    )

checks = {
    "main_rows": len(main),
    "detailed_rows": len(detailed),
    "metadata_rows": len(metadata),
    "quality_rows": len(quality),
    "main_only_classification_and_lifecycle": bool(((main["classification"] == "اصلی") & (main["lifecycle"] == "جاری")).all()),
    "detailed_only_classification": bool((detailed["classification"] == "تفکیکی").all()),
    "main_series": int(main[["source_file", "technical_id"]].drop_duplicates().shape[0]),
    "detailed_series": int(detailed[["source_file", "technical_id"]].drop_duplicates().shape[0]),
    "monthly_qoq_blank": bool((combined.loc[combined["frequency"] == "monthly", "calc_growth_qoq_pct"] == "").all()),
    "quarterly_mom_blank": bool((combined.loc[combined["frequency"] == "quarterly", "calc_growth_mom_pct"] == "").all()),
    "pp_blank_for_non_percent": bool((combined.loc[combined["unit"] != "percent", ["calc_change_period_pp", "calc_change_yoy_pp"]] == "").all().all()),
    "dates_populated": bool((combined["jalali_date"] != "").all() and (combined["gregorian_date"] != "").all()),
    "unexpected_quality_failures": int((quality["status"] == "fail").sum()),
    "spot_checks": spot_checks,
    "quality_by_check": {
        f"{check_name}/{status}": int(count)
        for (check_name, status), count in quality.groupby(["check_name", "status"]).size().items()
    },
    "files": {path.name: path.stat().st_size for path in output_dir.iterdir() if path.is_file()},
}

assert checks["main_only_classification_and_lifecycle"]
assert checks["detailed_only_classification"]
assert checks["main_series"] == 48
assert checks["detailed_series"] == 1769
assert checks["metadata_rows"] == 1817
assert checks["monthly_qoq_blank"]
assert checks["quarterly_mom_blank"]
assert checks["pp_blank_for_non_percent"]
assert checks["dates_populated"]
assert checks["unexpected_quality_failures"] == 0
assert all(check["pass"] for check in spot_checks)

print(json.dumps(checks, ensure_ascii=False, indent=2))
