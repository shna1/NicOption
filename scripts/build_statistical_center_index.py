#!/usr/bin/env python3
"""Build a seek index for the prepared Statistical Center long-form CSV files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


DATA_FILES = ("website_main_data.csv", "website_detailed_data.csv")


def parse_line(raw: bytes) -> list[str]:
    return next(csv.reader([raw.decode("utf-8").rstrip("\r\n")]))


def build_index(data_dir: Path) -> dict:
    series: dict[str, dict] = {}
    files = {}
    for filename in DATA_FILES:
        path = data_dir / filename
        digest = hashlib.sha256()
        ranges: dict[str, list[list[int]]] = defaultdict(list)
        latest: dict[str, dict] = {}
        with path.open("rb") as stream:
            raw_header = stream.readline()
            digest.update(raw_header)
            header = parse_line(raw_header.decode("utf-8-sig").encode("utf-8"))
            positions = {name: index for index, name in enumerate(header)}
            required = {"source_file", "technical_id", "gregorian_date", "jalali_date", "value"}
            if missing := required - positions.keys():
                raise ValueError(f"{filename} missing columns: {', '.join(sorted(missing))}")
            active_key = None
            active_start = None
            rows = 0
            while True:
                start = stream.tell()
                raw = stream.readline()
                if not raw:
                    break
                digest.update(raw)
                row = parse_line(raw)
                if len(row) != len(header):
                    raise ValueError(f"{filename} has a multiline or malformed record at byte {start}")
                key = f"{row[positions['source_file']]}::{row[positions['technical_id']]}"
                if key != active_key:
                    if active_key is not None:
                        ranges[active_key].append([active_start, start])
                    active_key = key
                    active_start = start
                latest[key] = {
                    "gregorian_date": row[positions["gregorian_date"]],
                    "jalali_date": row[positions["jalali_date"]],
                    "value": row[positions["value"]],
                    "calc_growth_period_pct": row[positions["calc_growth_mom_pct"]]
                    or row[positions["calc_growth_qoq_pct"]],
                    "calc_growth_yoy_pct": row[positions["calc_growth_yoy_pct"]],
                    "calc_change_period_pp": row[positions["calc_change_period_pp"]],
                    "calc_change_yoy_pp": row[positions["calc_change_yoy_pp"]],
                }
                rows += 1
            if active_key is not None:
                ranges[active_key].append([active_start, stream.tell()])
        for key, key_ranges in ranges.items():
            if key in series:
                raise ValueError(f"duplicate composite series key: {key}")
            series[key] = {"file": filename, "ranges": key_ranges, "latest": latest[key]}
        files[filename] = {"size": path.stat().st_size, "sha256": digest.hexdigest(), "rows": rows}
    return {"version": 1, "files": files, "series": series}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("outputs/website_data_prepared"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.data_dir / "website_series_index.json"
    payload = build_index(args.data_dir)
    output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"series={len(payload['series'])} output={output}")


if __name__ == "__main__":
    main()
