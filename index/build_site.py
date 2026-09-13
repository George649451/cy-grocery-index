#!/usr/bin/env python3
"""Build site/data.json from the public data directory.

Everything the page shows is derived here, so the page itself is static and
the numbers are reproducible from the committed CSVs.
"""
import argparse
import csv
import json
import os
import statistics
import sys
from collections import defaultdict


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="data")
    ap.add_argument("--out", default="site/data.json")
    a = ap.parse_args()

    basket = read(os.path.join(a.public_dir, "basket", "real_basket.csv"))
    panel = read(os.path.join(a.public_dir, "basket", "prices.csv"))
    daily = read(os.path.join(a.public_dir, "summary", "daily.csv"))
    master = {r["id"]: r for r in read(os.path.join(a.public_dir, "catalogue", "products.csv"))}

    dates = sorted({r["date"] for r in panel})
    start, latest = dates[0], dates[-1]
    by_date = defaultdict(dict)
    for r in panel:
        by_date[r["date"]][r["id"]] = r

    # weekly basket cost per collection date (promotional/paid price); items missing on a date are
    # imputed at their last known unit price so the series never drops because of a stock-out
    series = []
    last_unit = {}
    for d in dates:
        total = 0.0
        priced = 0
        for b in basket:
            row = by_date[d].get(b["id"])
            uv = fnum(row["unit_value"]) if row and row["unit_value"] else None
            if uv is not None and not (row and row.get("delisted")):
                last_unit[b["id"]] = uv
                priced += 1
            uv = last_unit.get(b["id"])
            if uv is not None:
                total += uv * float(b["weekly_qty"])
        series.append({"date": d, "cost": round(total, 2), "priced": priced})

    # monthly readings: mean of the daily basket cost within each calendar month; a month
    # is "complete" once the last collection date is in a later month
    months = defaultdict(list)
    for s in series:
        months[s["date"][:7]].append(s["cost"])
    monthly = []
    for m in sorted(months):
        complete = m < latest[:7]
        monthly.append({"month": m, "cost": round(statistics.mean(months[m]), 2), "days": len(months[m]), "complete": complete})
    base = monthly[0]["cost"] if monthly else None
    for m in monthly:
        m["index"] = round(100 * m["cost"] / base, 1) if base else None

    # item table at latest date
    items = []
    latest_rows = by_date[latest]
    start_rows = by_date[start]
    for b in basket:
        r = latest_rows.get(b["id"])
        s0 = start_rows.get(b["id"])
        uv = fnum(r["unit_value"]) if r else None
        uv0 = fnum(s0["unit_value"]) if s0 else None
        m = master.get(b["id"], {})
        items.append({
            "id": b["id"], "group": b["group"], "title": b["title"], "brand": b["brand"],
            "qty": float(b["weekly_qty"]), "basis": b["basis"], "note": b["note"],
            "unit_price": uv, "unit_price_start": uv0,
            "weekly_cost": round(uv * float(b["weekly_qty"]), 2) if uv is not None else None,
            "pack_price": fnum(r["price"]) if r else None,
            "original_price": fnum(r["original_price"]) if r else None,
            "promotion": r["promotion"] if r else "",
            "unit_price_source": b["unit_price_source"],
            "image": m.get("image_url", ""),
            "url": f"https://www.alphamega.com.cy/en/groceries?productId={b['id']}",
        })

    groups = defaultdict(float)
    for it in items:
        if it["weekly_cost"] is not None:
            groups[it["group"]] += it["weekly_cost"]

    # catalogue summary (latest day)
    dl = daily[-1]
    total = int(dl["distinct"]) if dl["distinct"] else None
    catalogue = {
        "date": dl["date"], "products": total,
        "with_unit_price": int(dl["with_unit_price"]) if dl["with_unit_price"] else None,
        "promo_labelled": int(dl["promo_labelled"]) if dl["promo_labelled"] else None,
        "promo_with_original_price": int(dl["promo_with_original_price"]) if dl["promo_with_original_price"] else None,
        "changed": int(dl["changed"]) if dl["changed"] else 0,
        "new": int(dl["new"]) if dl["new"] else 0,
        "delisted": int(dl["delisted"]) if dl["delisted"] else 0,
    }
    promo_share = defaultdict(list)
    for r in daily:
        if r["promo_labelled"] and r["distinct"]:
            promo_share[r["date"]] = round(100 * int(r["promo_labelled"]) / int(r["distinct"]), 1)

    # basket promo intensity at latest date
    on_promo = sum(1 for it in items if it["promotion"])
    with_orig = [it for it in items if it["original_price"] and it["pack_price"]]
    promo_depth = round(100 * (1 - sum(it["pack_price"] for it in with_orig) / sum(it["original_price"] for it in with_orig)), 1) if with_orig else None

    out = {
        "generated_from": {"start": start, "latest": latest, "collection_days": len(dates)},
        "basket": {
            "household": "two adults, two school-age children",
            "lines": len(basket),
            "latest_cost": series[-1]["cost"],
            "start_cost": series[0]["cost"],
            "series": series,
            "monthly": monthly,
            "groups": [{"group": g, "cost": round(c, 2)} for g, c in sorted(groups.items(), key=lambda x: -x[1])],
            "items": items,
            "on_promo": on_promo,
            "promo_depth_pct": promo_depth,
        },
        "catalogue": catalogue,
        "promo_share_series": [{"date": d, "pct": p} for d, p in sorted(promo_share.items())],
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {a.out}: {len(dates)} days, basket €{series[-1]['cost']:.2f}, {len(items)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
