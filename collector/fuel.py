#!/usr/bin/env python3
"""Daily collector for the Cyprus Retail Fuel Price Observatory.

Source: Consumer Protection Service, Ministry of Energy, Commerce and Industry,
https://eforms.eservices.cyprus.gov.cy/MCIT/MCIT/PetroleumPrices (linked from
https://www.gov.cy/en/service/retail-fuel-price-observatory/). An ASP.NET form:
POST fuel type x district with the page's anti-forgery token, parse the HTML table.

Outputs (all public: this is government open data)
  <public-dir>/fuel/stations.csv            station master (id, brand, name, address, area, district)
  <public-dir>/fuel/latest.csv              current price per station x fuel
  <public-dir>/fuel/changes/YYYY-MM.csv     append-only change log (new / change / delisted)
  <public-dir>/fuel/daily.csv               per date x fuel x district: n, median, mean, min, max
  <public-dir>/fuel/runs.csv                one row per run

Standard library only. 25 requests per run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import http.cookiejar
import os
import re
import statistics
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from zoneinfo import ZoneInfo

BASE = "https://eforms.eservices.cyprus.gov.cy"
FORM = BASE + "/MCIT/MCIT/PetroleumPrices"
USER_AGENT = ("cy-price-index-bot/0.1 "
              "(+https://github.com/George649451/cy-grocery-index; contact: george.g@cxm.com)")
TZ = ZoneInfo("Europe/Nicosia")
FUELS = {"1": "unleaded95", "2": "unleaded98", "3": "diesel", "4": "heating_oil", "5": "kerosene"}
DISTRICTS = ["Nicosia", "Limassol", "Larnaca", "Paphos", "Famagusta"]

STATE_FIELDS = ["key", "station_id", "fuel", "price", "first_seen", "last_seen", "delisted_on"]
CHANGE_FIELDS = ["date", "key", "station_id", "fuel", "event", "price", "prev_price"]
STATION_FIELDS = ["station_id", "brand", "name", "address", "phone", "area", "district", "lat", "lon", "first_seen", "last_seen"]
DAILY_FIELDS = ["date", "fuel", "district", "n", "median", "mean", "min", "max"]


def opener():
    cj = http.cookiejar.CookieJar()
    op = build_opener(HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", USER_AGENT), ("Accept", "text/html")]
    return op


def fetch(op, url, data=None, retries=4) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = Request(url, data=urlencode(data).encode() if data else None)
            if data:
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with op.open(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(min(30, 3 * 2 ** attempt))
    raise RuntimeError(f"failed: {url}: {last}")


def get_token(op) -> str:
    page = fetch(op, FORM)
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', page)
    if not m:
        raise RuntimeError("no anti-forgery token on form page")
    return m.group(1)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse_rows(page: str) -> list[dict]:
    """Rows of the results table: brand, station, address(+phone), area, price."""
    m = re.search(r'<table[^>]*id="petroleumPriceDetailsFootable".*?</table>', page, re.S)
    if not m:
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S):
        cm = re.search(r"coordinates=([\d.\-]+)(?:%2C|,)([\d.\-]+)", tr)
        lat, lon = (cm.group(1), cm.group(2)) if cm else ("", "")
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 5:
            continue
        brand, name, address, area, price = cells[:5]
        phone = ""
        pm = re.search(r"τηλ:\s*([\d\s/+-]+)", address)
        if pm:
            phone = pm.group(1).strip()
            address = clean(address[: pm.start()])
        try:
            p = float(price.replace(",", "."))
        except ValueError:
            continue
        out.append({"brand": brand, "name": name, "address": address, "phone": phone, "area": area, "lat": lat, "lon": lon, "price": f"{p:.3f}"})
    return out


def station_id(r: dict, district: str) -> str:
    h = hashlib.sha1("|".join([r["brand"], r["name"], r["address"], r["area"], district]).lower().encode()).hexdigest()
    return h[:12]


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in fields} for r in rows)
    os.replace(tmp, path)


def append_csv(path, rows, fields):
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows({k: r.get(k, "") for k in fields} for r in rows)


def upsert_rows(path, rows, fields, keys):
    """Replace rows sharing the same key tuple (same-day reruns), keep the rest."""
    newkeys = {tuple(r[k] for k in keys) for r in rows}
    kept = [r for r in read_csv(path) if tuple(r[k] for k in keys) not in newkeys]
    write_csv(path, kept + rows, fields)


def run(public_dir: str, date: str, dry_run: bool) -> int:
    t0 = time.time()
    fdir = os.path.join(public_dir, "fuel")
    op = opener()
    token = get_token(op)

    observations: dict[str, dict] = {}   # key -> row
    stations: dict[str, dict] = {}
    requests_made = 1
    for fid, fuel in FUELS.items():
        for district in DISTRICTS:
            page = fetch(op, FORM, {"__RequestVerificationToken": token, "Entity.PetroleumType": fid,
                                    "Entity.StationCityEnum": district})
            requests_made += 1
            for r in parse_rows(page):
                sid = station_id(r, district)
                stations.setdefault(sid, {**r, "station_id": sid, "district": district})
                observations[f"{sid}:{fuel}"] = {"key": f"{sid}:{fuel}", "station_id": sid, "fuel": fuel, "price": r["price"]}
    print(f"[{date}] {requests_made} requests, {len(stations)} stations, {len(observations)} station x fuel prices", flush=True)
    ok = len(observations) > 500  # a healthy day is ~1,000+
    if not ok:
        print(f"[{date}] ERROR too few observations; not writing state", file=sys.stderr, flush=True)

    # changes vs previous state
    prev = {r["key"]: r for r in read_csv(os.path.join(fdir, "latest.csv"))}
    changes, n_new, n_changed, n_delisted, n_relisted = [], 0, 0, 0, 0
    if ok:
        for key, row in observations.items():
            old = prev.get(key)
            row["last_seen"] = date
            row["delisted_on"] = ""
            if old is None:
                row["first_seen"] = date
                changes.append({"date": date, **row, "event": "new", "prev_price": ""})
                n_new += 1
            else:
                row["first_seen"] = old.get("first_seen") or date
                if old.get("delisted_on"):
                    changes.append({"date": date, **row, "event": "relisted", "prev_price": old.get("price", "")})
                    n_relisted += 1
                elif old.get("price") != row["price"]:
                    changes.append({"date": date, **row, "event": "change", "prev_price": old.get("price", "")})
                    n_changed += 1
        for key, old in prev.items():
            if key not in observations:
                kept = dict(old)
                if not old.get("delisted_on"):
                    kept["delisted_on"] = date
                    changes.append({"date": date, "key": key, "station_id": old["station_id"], "fuel": old["fuel"],
                                    "event": "delisted", "price": "", "prev_price": old.get("price", "")})
                    n_delisted += 1
                observations[key] = kept

    # daily aggregates per fuel x district (+ national)
    daily = []
    active = [r for r in observations.values() if not r.get("delisted_on")]
    for fuel in FUELS.values():
        for district in DISTRICTS + ["Cyprus"]:
            ps = [float(r["price"]) for r in active if r["fuel"] == fuel and (district == "Cyprus" or stations.get(r["station_id"], {}).get("district") == district)]
            if not ps:
                continue
            daily.append({"date": date, "fuel": fuel, "district": district, "n": len(ps), "median": f"{statistics.median(ps):.3f}",
                          "mean": f"{statistics.mean(ps):.4f}", "min": f"{min(ps):.3f}", "max": f"{max(ps):.3f}"})

    run_row = {"date": date, "requests": requests_made, "stations": len(stations), "observations": len([r for r in observations.values() if not r.get('delisted_on')]),
               "new": n_new, "changed": n_changed, "delisted": n_delisted, "relisted": n_relisted,
               "seconds": f"{time.time() - t0:.0f}", "ok": int(ok)}
    print(run_row, flush=True)
    if dry_run:
        return 0 if ok else 2
    append_csv(os.path.join(fdir, "runs.csv"), [run_row], list(run_row.keys()))
    if not ok:
        return 2

    # station master
    prev_st = {r["station_id"]: r for r in read_csv(os.path.join(fdir, "stations.csv"))}
    for sid, s in stations.items():
        s["first_seen"] = prev_st.get(sid, {}).get("first_seen") or date
        s["last_seen"] = date
        prev_st[sid] = {**prev_st.get(sid, {}), **s}
    write_csv(os.path.join(fdir, "stations.csv"), sorted(prev_st.values(), key=lambda r: (r["district"], r["brand"], r["name"])), STATION_FIELDS)
    write_csv(os.path.join(fdir, "latest.csv"), sorted(observations.values(), key=lambda r: r["key"]), STATE_FIELDS)
    append_csv(os.path.join(fdir, "changes", f"{date[:7]}.csv"), changes, CHANGE_FIELDS)
    upsert_rows(os.path.join(fdir, "daily.csv"), daily, DAILY_FIELDS, ["date", "fuel", "district"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public-dir", required=True)
    ap.add_argument("--date", default=dt.datetime.now(TZ).date().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(a.public_dir, a.date, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
