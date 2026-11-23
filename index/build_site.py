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


def build_eating_out(public_dir):
    edir = os.path.join(public_dir, "eating_out")
    if not (os.path.exists(os.path.join(edir, "items.csv")) and os.path.exists(os.path.join(edir, "prices.csv"))):
        return None
    items = [r for r in read(os.path.join(edir, "items.csv")) if r.get("active", "1") != "0"]
    obs = read(os.path.join(edir, "prices.csv"))
    if not obs:
        return None
    dates = sorted({r["date"] for r in obs})
    price = {(r["date"], r["item_id"]): fnum(r["price"]) for r in obs}
    base, latest = dates[0], dates[-1]
    ids = [it["item_id"] for it in items]

    # Chained Jevons: each check is linked to the one before it through the items priced on
    # both. An item missing on a check therefore moves with the rest, never as unchanged, and
    # an item added to the list later joins from its first check without disturbing the level.
    series = []
    level = 100.0
    for k, d in enumerate(dates):
        n = sum(1 for i in ids if (d, i) in price)
        if k:
            prev = dates[k - 1]
            rel = [math.log(price[(d, i)] / price[(prev, i)]) for i in ids if (d, i) in price and (prev, i) in price]
            if rel:
                level *= math.exp(sum(rel) / len(rel))
        series.append({"date": d, "index": round(level, 2), "items": n})

    out_items = []
    for it in items:
        i = it["item_id"]
        seen = [d for d in dates if (d, i) in price]
        if not seen:
            continue
        first, last = seen[0], seen[-1]
        out_items.append({"id": i, "restaurant": it["restaurant"], "area": it["area"], "type": it["type"], "category": it["category"],
                          "label": it["label"], "url": it["url"], "note": it["note"], "price": price[(last, i)],
                          "price_start": price[(first, i)], "last_seen": last, "current": last == latest})

    def med(pred):
        vals = [x["price"] for x in out_items if pred(x)]
        return {"median": round(statistics.median(vals), 2), "n": len(vals), "min": min(vals), "max": max(vals)} if vals else None

    restaurants = []
    for name in dict.fromkeys(it["restaurant"] for it in items):
        its = [x for x in out_items if x["restaurant"] == name]
        if its:
            restaurants.append({"name": name, "area": its[0]["area"], "type": its[0]["type"], "url": its[0]["url"],
                                "note": next((x["note"] for x in its if x["note"] and "operator" not in x["note"] and x["note"] not in ("minimum two", "specialty coffee")), "")})
    return {
        "start": base, "latest": latest, "checks": len(dates), "n_items": len(out_items), "n_restaurants": len(restaurants),
        "series": series, "items": out_items, "restaurants": restaurants,
        "typical": {
            "meze": med(lambda x: x["category"] == "meze"),
            "taverna_main": med(lambda x: x["category"] == "main" and "Cypriot" in x["type"]),
            "coffee": med(lambda x: x["category"] == "coffee"),
            "souvlaki_pitta": med(lambda x: x["id"].endswith(":souvlaki-pitta")),
            "beer_33cl": med(lambda x: x["id"].endswith(":beer-33cl")),
        },
    }


# Standard household used for the utilities bills. Stated on the site; change here only.
STD_KWH_PER_2_MONTHS = 700      # 4,200 kWh a year
STD_WATER_M3_PER_MONTH = 15     # four people at about 125 litres a day each


def water_bill(rows, m3_per_month):
    """Monthly water charge before VAT for a district's tariff rows, plus sewerage."""
    period = next((int(r["period_months"]) for r in rows if r["period_months"]), None)
    if not period:
        return None
    q = m3_per_month * period
    fixed = sum(fnum(r["value_eur"]) for r in rows if r["component"] in ("fixed", "maintenance"))
    usage = 0.0
    for r in rows:
        if r["component"] != "band":
            continue
        lo = fnum(r["from_m3"]) or 1
        hi = fnum(r["to_m3"]) if r["to_m3"] else float("inf")
        usage += max(0.0, min(q, hi) - (lo - 1)) * fnum(r["value_eur"])
    sew = next((fnum(r["value_eur"]) for r in rows if r["component"] == "sewerage_per_m3"), None)
    return {"period_months": period, "m3_per_period": q, "fixed_per_period": round(fixed, 2),
            "usage_per_period": round(usage, 2), "monthly": round((fixed + usage) / period, 2),
            "sewerage_per_m3": sew, "sewerage_monthly": round(sew * m3_per_month, 2) if sew is not None else None}


def build_utilities(public_dir):
    udir = os.path.join(public_dir, "utilities")
    if not os.path.exists(os.path.join(udir, "eac_tariff.csv")):
        return None
    tariffs = read(os.path.join(udir, "eac_tariff.csv"))
    fuel = read(os.path.join(udir, "eac_fuel_adjustment.csv")) if os.path.exists(os.path.join(udir, "eac_fuel_adjustment.csv")) else []
    water = read(os.path.join(udir, "water_tariffs.csv")) if os.path.exists(os.path.join(udir, "water_tariffs.csv")) else []
    changes = read(os.path.join(udir, "changes.csv")) if os.path.exists(os.path.join(udir, "changes.csv")) else []
    runs = read(os.path.join(udir, "runs.csv")) if os.path.exists(os.path.join(udir, "runs.csv")) else []

    electricity = None
    if tariffs:
        t = tariffs[-1]
        base_units = fnum(t["energy_cent_kwh"]) + fnum(t["network_cent_kwh"]) + (fnum(t["ancillary_cent_kwh"]) or 0.0)
        fixed = fnum(t["meter_eur_bimonthly"]) + fnum(t["supply_eur_bimonthly"])
        start_month = (t["effective_from"] or t["first_seen"])[:7]
        months = []
        for r in sorted(fuel, key=lambda x: x["bill_month"]):
            # only months billed under this tariff: on or after its start, and adjusted from the same base fuel price
            same_base = not t["base_fuel_eur_mt"] or abs(fnum(r["implied_base_eur_mt"]) - fnum(t["base_fuel_eur_mt"])) < 1
            if r["bill_month"] < start_month or not same_base:
                continue
            unit = base_units + fnum(r["revised_cent_kwh"])
            bill = STD_KWH_PER_2_MONTHS * unit / 100 + fixed
            months.append({"month": r["bill_month"], "fuel_price_eur_mt": fnum(r["fuel_price_eur_mt"]),
                           "fuel_adjustment_cent": fnum(r["revised_cent_kwh"]), "unit_cent_kwh": round(unit, 4),
                           "bill_2_months": round(bill, 2), "bill_monthly": round(bill / 2, 2)})
        electricity = {
            "tariff": {"code": t["code"], "effective_from": t["effective_from"], "energy_cent_kwh": fnum(t["energy_cent_kwh"]),
                       "network_cent_kwh": fnum(t["network_cent_kwh"]), "ancillary_cent_kwh": fnum(t["ancillary_cent_kwh"]) or 0.0,
                       "fixed_eur_2_months": round(fixed, 2), "base_fuel_eur_mt": fnum(t["base_fuel_eur_mt"]), "source_doc": t["source_doc"]},
            "kwh_per_2_months": STD_KWH_PER_2_MONTHS, "months": months,
        }

    districts = []
    for name in sorted({r["district"] for r in water}):
        rows = [r for r in water if r["district"] == name]
        bands = [{"from": fnum(r["from_m3"]), "to": fnum(r["to_m3"]) if r["to_m3"] else None, "rate": fnum(r["value_eur"])}
                 for r in rows if r["component"] == "band"]
        flat = next((r for r in rows if r["component"] == "flat_including_first_band"), None)
        districts.append({
            "district": name, "area": rows[0]["area"], "source_url": rows[0]["source_url"], "last_checked": rows[0]["last_checked"],
            "fixed": next((fnum(r["value_eur"]) for r in rows if r["component"] == "fixed"), None),
            "maintenance": next((fnum(r["value_eur"]) for r in rows if r["component"] == "maintenance"), None),
            "flat": {"to": fnum(flat["to_m3"]), "value": fnum(flat["value_eur"])} if flat else None,
            "bands": sorted(bands, key=lambda b: b["from"]),
            "bill": water_bill(rows, STD_WATER_M3_PER_MONTH),
        })
    ok_runs = [r for r in runs if r["ok"] == "1"]
    return {"electricity": electricity, "water": districts, "m3_per_month": STD_WATER_M3_PER_MONTH,
            "changes": changes[-20:], "last_checked": max((r["date"] for r in ok_runs), default=None),
            "failed_sources": sorted({r["source"] for r in runs if r["ok"] == "0" and r["date"] == max(x["date"] for x in runs)}) if runs else []}


EC_FUELS = ["unleaded95", "diesel", "heating_oil"]


def build_fuel_ec(public_dir, station_daily):
    """Weekly national averages from the EC Oil Bulletin: the fuel module's ongoing series."""
    path = os.path.join(public_dir, "fuel", "ec_weekly.csv")
    if not os.path.exists(path):
        return None
    rows = [r for r in read(path) if r["unleaded95"] and r["diesel"]]
    if not rows:
        return None
    wk = [{"date": r["date"], **{f: fnum(r[f]) if r[f] else None for f in EC_FUELS}} for r in rows]
    latest = wk[-1]

    def at_or_before(date):
        prior = [w for w in wk if w["date"] <= date]
        return prior[-1] if prior else None

    def shift(date, days):
        return (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()

    prev_week = wk[-2] if len(wk) > 1 else None
    year_ago = at_or_before(shift(latest["date"], 364))
    by_m = defaultdict(list)
    for w in wk:
        by_m[w["date"][:7]].append(w)
    this_month = dt.date.today().isoformat()[:7]
    monthly = []
    for m in sorted(by_m)[-14:]:
        rec = {"month": m, "weeks": len(by_m[m]), "complete": m < this_month}
        for f in EC_FUELS:
            vals = [w[f] for w in by_m[m] if w[f] is not None]
            rec[f] = round(statistics.mean(vals), 3) if vals else None
        monthly.append(rec)
    # agreement with our own station-level collection on the Mondays where both exist
    st = {(r["date"], r["fuel"]): fnum(r["mean"]) for r in station_daily if r["district"] == "Cyprus"}
    diffs = [abs(w["unleaded95"] - st[(w["date"], "unleaded95")]) for w in wk if (w["date"], "unleaded95") in st]
    return {
        "latest": latest, "prev_week": prev_week, "year_ago": year_ago,
        "first_week": wk[0]["date"], "weeks": len(wk),
        "series": wk[-105:],
        "monthly": monthly,
        "overlap": {"mondays": len(diffs), "mean_abs_diff_u95": round(statistics.mean(diffs), 4) if diffs else None},
    }


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
        "ec": build_fuel_ec(public_dir, daily),
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
    utilities = build_utilities(a.public_dir)
    eating_out = build_eating_out(a.public_dir)

    out = {
        "modules": modules,
        "fuel": fuel,
        "utilities": utilities,
        "eating_out": eating_out,
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
