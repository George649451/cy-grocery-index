#!/usr/bin/env python3
"""Import the 12 Sep 2026 snapshot (captured by an earlier tool with a narrower
schema) as t=0 of the price state, so the series starts a day earlier.

Legacy columns: alphamega_id, ean, name, price, was, unit_price, category,
stock_polemidia, stock_larnaca. Fields the legacy file lacks are left empty;
the collector only compares price fields whose previous value is known, so the
first real run will not record spurious changes for them.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import collect  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--public-dir", required=True)
    ap.add_argument("--date", default="2026-09-12")
    a = ap.parse_args()

    latest = os.path.join(a.data_dir, "prices", "latest.csv")
    if os.path.exists(latest) and os.path.getsize(latest) > 0:
        sys.exit(f"refusing to overwrite existing state at {latest}")

    rows, changes = [], []
    with open(a.csv, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            pid = r["alphamega_id"].strip()
            parts = [collect.clean(x) for x in r["category"].split(">")]
            unit_value, unit_basis = collect.parse_comparison(collect.clean(r["unit_price"]))
            row = {k: "" for k in collect.STATE_FIELDS}
            row.update({
                "id": pid, "ean": r["ean"].strip(), "title": collect.clean(r["name"]),
                "cat1": parts[0] if parts else "", "cat2": parts[1] if len(parts) > 1 else "",
                "cat3": parts[2] if len(parts) > 2 else "",
                "price": collect.clean(r["price"]), "original_price": collect.clean(r["was"]),
                "comparison_price": collect.clean(r["unit_price"]),
                "unit_value": unit_value, "unit_basis": unit_basis,
                "image_url": f"https://alphamega.com.cy/Files/Images/Products/{pid}.jpg",
                "first_seen": a.date, "last_seen": a.date,
            })
            rows.append(row)
            changes.append({"date": a.date, "id": pid, "event": "new", **row})

    rows.sort(key=lambda r: r["id"])
    collect.write_csv(latest, rows, collect.STATE_FIELDS)
    collect.append_csv(os.path.join(a.data_dir, "prices", "changes", f"{a.date[:7]}.csv"), changes, collect.CHANGE_FIELDS)
    collect.write_csv(os.path.join(a.public_dir, "catalogue", "products.csv"), rows, collect.MASTER_FIELDS)
    summary = {"date": a.date, "reported_total": len(rows), "distinct": len(rows), "available": "",
               "with_unit_price": sum(1 for r in rows if r["unit_value"]),
               "promo_with_original_price": sum(1 for r in rows if r["original_price"] not in ("", "0", "0.0")),
               "promo_labelled": "", "new": len(rows), "changed": 0, "delisted": 0, "relisted": 0}
    collect.append_csv(os.path.join(a.public_dir, "summary", "daily.csv"), [summary], list(summary.keys()))
    collect.append_csv(os.path.join(a.data_dir, "runs.csv"),
                       [{**summary, "coverage": "1.0000", "seconds": "0", "ok": 1}],
                       list(summary.keys()) + ["coverage", "seconds", "ok"])
    print(f"imported {len(rows)} products as of {a.date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
