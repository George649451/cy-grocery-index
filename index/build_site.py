#!/usr/bin/env python3
"""Build site/data.json from the public data directory.

Everything the page shows is derived here, so the page itself is static and
the numbers are reproducible from the committed CSVs.
"""
import argparse
import csv
import datetime as dt
import json
import math
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


FUEL_NAMES = {"unleaded95": "Unleaded 95", "unleaded98": "Unleaded 98", "diesel": "Diesel", "heating_oil": "Heating oil", "kerosene": "Kerosene"}
FUEL_ORDER = ["unleaded95", "diesel", "unleaded98", "heating_oil", "kerosene"]
DISTRICT_ORDER = ["Nicosia", "Limassol", "Larnaca", "Paphos", "Famagusta"]


def build_fuel(public_dir):
    path = os.path.join(public_dir, "fuel", "daily.csv")
    if not os.path.exists(path):
        return None
    daily = read(path)
    if not daily:
        return None
    dates = sorted({r["date"] for r in daily})
    latest = dates[-1]
    nat = {r["fuel"]: r for r in daily if r["date"] == latest and r["district"] == "Cyprus"}
    first = {r["fuel"]: r for r in daily if r["date"] == dates[0] and r["district"] == "Cyprus"}
    series = {f: [{"date": r["date"], "median": fnum(r["median"]), "n": int(r["n"])} for r in sorted(daily, key=lambda x: x["date"]) if r["fuel"] == f and r["district"] == "Cyprus"] for f in FUEL_ORDER}
    # monthly averages of the national median
    monthly = {}
    for f in FUEL_ORDER:
        by_m = defaultdict(list)
        for pt in series[f]:
            by_m[pt["date"][:7]].append(pt["median"])
        monthly[f] = [{"month": m, "median": round(statistics.mean(v), 3), "days": len(v), "complete": m < max(latest[:7], dt.date.today().isoformat()[:7])} for m, v in sorted(by_m.items())]
    districts = []
    for d in DISTRICT_ORDER:
        row = {"district": d}
        for f in FUEL_ORDER:
            r = next((x for x in daily if x["date"] == latest and x["district"] == d and x["fuel"] == f), None)
            row[f] = {"median": fnum(r["median"]), "min": fnum(r["min"]), "max": fnum(r["max"]), "n": int(r["n"])} if r else None
        districts.append(row)
    # brands: median by brand for the two main fuels, from latest.csv + stations.csv
    brands = []
    st_path, lt_path = os.path.join(public_dir, "fuel", "stations.csv"), os.path.join(public_dir, "fuel", "latest.csv")
    if os.path.exists(st_path) and os.path.exists(lt_path):
        st = {r["station_id"]: r for r in read(st_path)}
        by_brand = defaultdict(lambda: defaultdict(list))
        for r in read(lt_path):
            if r.get("delisted_on"):
                continue
            b = st.get(r["station_id"], {}).get("brand", "?")
            by_brand[b][r["fuel"]].append(float(r["price"]))
        for b, fuels in by_brand.items():
            n = len(fuels.get("unleaded95", []))
            if n >= 3:
                brands.append({"brand": b, "n": n,
                               "unleaded95": round(statistics.median(fuels["unleaded95"]), 3) if fuels.get("unleaded95") else None,
                               "diesel": round(statistics.median(fuels["diesel"]), 3) if fuels.get("diesel") else None})
        brands.sort(key=lambda x: (x["unleaded95"] is None, x["unleaded95"] or 0))
    return {
        "start": dates[0], "latest": latest, "collection_days": len(dates),
        "names": FUEL_NAMES, "order": FUEL_ORDER,
        "national": {f: {"median": fnum(nat[f]["median"]), "mean": fnum(nat[f]["mean"]), "min": fnum(nat[f]["min"]), "max": fnum(nat[f]["max"]), "n": int(nat[f]["n"]),
                         "median_start": fnum(first[f]["median"]) if f in first else None} for f in FUEL_ORDER if f in nat},
        "stations": max(int(r["n"]) for r in nat.values()) if nat else 0,
        "series": series, "monthly": monthly, "districts": districts, "brands": brands,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-dir", default="data")
    ap.add_argument("--out", default="site/data.json")
    a = ap.parse_args()

    basket = read(os.path.join(a.public_dir, "basket", "real_basket.csv"))
    panel = read(os.path.join(a.public_dir, "basket", "prices.csv"))
    daily = read(os.path.join(a.public_dir, "summary", "daily.csv"))
    master = {r["id"]: r for r in read(os.path.join(a.public_dir, "catalogue", "products.csv"))}
    modules_path = os.path.join(a.public_dir, "modules.csv")
    modules = read(modules_path) if os.path.exists(modules_path) else []

    dates = sorted({r["date"] for r in panel})
    start, latest = dates[0], dates[-1]
    by_date = defaultdict(dict)
    for r in panel:
        by_date[r["date"]][r["id"]] = r

    # Weekly basket cost per collection date (paid price). A line with no price on a date
    # (delisted or absent) is imputed: its last observed unit price moved by the Jevons
    # movement, since that observation, of the lines in its group that are priced on both
    # dates. Never the last price carried forward. Falls back to the whole basket when the
    # group has no other priced line.
    group_of = {b["id"]: b["group"] for b in basket}
    observed = {}                      # date -> {id: unit price actually observed}
    for d in dates:
        obs = {}
        for b in basket:
            row = by_date[d].get(b["id"])
            if row and row["unit_value"] and not row.get("delisted"):
                obs[b["id"]] = fnum(row["unit_value"])
        observed[d] = obs

    # Source-error guard. The retailer's unit price occasionally glitches (20 Oct 2026: a
    # 1.5 L cola at an unchanged EUR 1.95 was listed at 13/L instead of 1.30/L for one day).
    # The pack size implied by price / unit price cannot plausibly halve or double overnight,
    # so such an observation is set aside and the line is imputed for that day - unless the
    # new implied size is still there two observations later, in which case it is a genuine
    # pack change and is accepted.
    anomalies = []
    for b in basket:
        i = b["id"]
        seq = []
        for d in dates:
            row = by_date[d].get(i)
            if i in observed[d] and row and fnum(row["price"]) and observed[d][i] > 0:
                seq.append((d, fnum(row["price"]) / observed[d][i]))
        accepted = None
        for k, (d, size) in enumerate(seq):
            if accepted is None or 0.5 <= size / accepted <= 2:
                accepted = size
                continue
            ahead = [sz for _, sz in seq[k + 1:k + 3]]
            persists = len(ahead) == 2 and all(0.5 <= sz / size <= 2 for sz in ahead)
            if persists:
                accepted = size
            else:
                anomalies.append({"date": d, "id": i, "title": b["title"], "unit_price_listed": observed[d][i],
                                  "implied_pack": round(size, 4), "usual_pack": round(accepted, 4)})
                del observed[d][i]

    def movement(ids, d_from, d_to):
        rel = [math.log(observed[d_to][i] / observed[d_from][i]) for i in ids
               if i in observed[d_from] and i in observed[d_to] and observed[d_from][i] > 0]
        return math.exp(sum(rel) / len(rel)) if rel else None

    series = []
    last_obs = {}                      # id -> (date, unit price)
    unit_on = {}                       # date -> {id: (unit price, imputed?)}
    for d in dates:
        total, priced, cur = 0.0, 0, {}
        for b in basket:
            i = b["id"]
            if i in observed[d]:
                last_obs[i] = (d, observed[d][i])
                cur[i] = (observed[d][i], False)
                priced += 1
            elif i in last_obs:
                d0, p0 = last_obs[i]
                peers = [j for j in group_of if group_of[j] == group_of[i] and j != i]
                mv = movement(peers, d0, d) or movement([j for j in group_of if j != i], d0, d) or 1.0
                cur[i] = (p0 * mv, True)
            if i in cur:
                total += cur[i][0] * float(b["weekly_qty"])
        unit_on[d] = cur
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
        cur = unit_on[latest].get(b["id"])
        uv = round(cur[0], 4) if cur else None
        imputed = bool(cur and cur[1])
        uv0 = fnum(s0["unit_value"]) if s0 else None
        m = master.get(b["id"], {})
        items.append({
            "id": b["id"], "group": b["group"], "title": b["title"], "brand": b["brand"],
            "qty": float(b["weekly_qty"]), "basis": b["basis"], "note": b["note"],
            "unit_price": uv, "unit_price_start": uv0, "imputed": imputed,
            "last_observed": last_obs.get(b["id"], (None, None))[0],
            "weekly_cost": round(uv * float(b["weekly_qty"]), 2) if uv is not None else None,
            "pack_price": fnum(r["price"]) if r and not imputed else None,
            "original_price": fnum(r["original_price"]) if r and not imputed else None,
            "promotion": r["promotion"] if r and not imputed else "",
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

    fuel = build_fuel(a.public_dir)

    out = {
        "modules": modules,
        "fuel": fuel,
        "anomalies": anomalies,
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
