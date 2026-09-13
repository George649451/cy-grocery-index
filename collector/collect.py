#!/usr/bin/env python3
"""Daily Alphamega catalogue collector.

Pulls the full catalogue from the public Unbxd search API, normalises each
product, and appends *changes* (not snapshots) to a change-log.

Outputs
  <data-dir>/prices/latest.csv           full current state, one row per product
  <data-dir>/prices/changes/YYYY-MM.csv  append-only change log
  <data-dir>/runs.csv                    one row per run (monitoring)
  <public-dir>/catalogue/products.csv    product master, no prices
  <public-dir>/summary/daily.csv         daily aggregate counts

The promotion label (Only, Price Drop, Pick Of The Week, Mix & Match) is not in
the default document; it has to be named in the fields= parameter.

The collector is deliberately ignorant of index methodology. It must never be
blocked by a classification or basket question. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = ("https://search.unbxd.io/b2fe883192293321a4225f18fb8c26af/"
        "ss-unbxd-auk-alphamega-en-prod51051734415860/")
USER_AGENT = ("cy-grocery-index-bot/0.1 "
              "(+https://github.com/George649451/cy-grocery-index; contact: george.g@cxm.com)")
PAGE = 100            # server-side maximum
FIELDS = ",".join([
    "uniqueId", "sku", "barcode", "title", "title_gr", "brand",
    "categoryPath1", "categoryPath2", "categoryPath3", "subCategory",
    "price", "originalPrice", "discount", "comparisonPrice", "packSizeMl",
    "availability", "stock_1003", "stock_1004", "stock_1005",
    "stockStatus_4", "stockStatus_5", "stockStatus_6", "promotion",
    "organic", "vegan", "vegetarian", "glutenFree", "lactoseFree", "kosher", "meatFree",
])
CONCURRENCY = 6
MIN_COVERAGE = 0.97   # fail the run if we fetched fewer distinct ids than this share of the reported total
TZ = ZoneInfo("Europe/Nicosia")

# Fields whose change is a price event. Compared only where the previous value is known.
PRICE_FIELDS = ["price", "original_price", "discount", "comparison_price", "availability",
                "stock_1003", "stock_1004", "stock_1005", "promotion"]
STATE_FIELDS = ["id", "ean", "title", "title_gr", "brand", "cat1", "cat2", "cat3", "subcategory",
                "price", "original_price", "discount", "comparison_price", "unit_value", "unit_basis",
                "availability", "stock_1003", "stock_1004", "stock_1005",
                "status_4", "status_5", "status_6", "promotion",
                "organic", "vegan", "vegetarian", "gluten_free", "lactose_free", "kosher", "meat_free",
                "pack_size_ml", "image_url", "first_seen", "last_seen", "delisted_on"]
CHANGE_FIELDS = ["date", "id", "event"] + PRICE_FIELDS + ["unit_value", "unit_basis"]
MASTER_FIELDS = ["id", "ean", "title", "title_gr", "brand", "cat1", "cat2", "cat3", "subcategory",
                 "unit_basis", "pack_size_ml", "organic", "vegan", "vegetarian", "gluten_free",
                 "lactose_free", "kosher", "meat_free", "image_url", "first_seen", "last_seen", "delisted_on"]


# ----------------------------------------------------------------------------- HTTP

def get_json(url: str, retries: int = 5) -> dict:
    last = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - IncompleteRead, timeouts, 5xx, bad JSON: all transient here
            last = e
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"failed after {retries} attempts: {url}: {last}")


def search_url(start: int, rows: int = PAGE, filt: str | None = None, fields: str | None = None) -> str:
    u = f"{BASE}search?q=*&rows={rows}&start={start}&sort=uniqueId%20asc"
    if fields:
        u += "&fields=" + quote(fields, safe=",")
    if filt:
        u += "&filter=" + quote(filt, safe="")
    return u


def fetch_all(filt: str | None = None, fields: str | None = FIELDS) -> tuple[int, list[dict]]:
    """Paginate a wildcard search (optionally filtered) and return (reported_total, products)."""
    first = get_json(search_url(0, filt=filt, fields=fields))
    total = int(first["response"]["numberOfProducts"])
    products = list(first["response"]["products"])
    starts = list(range(PAGE, total, PAGE))
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        for page in ex.map(lambda s: get_json(search_url(s, filt=filt, fields=fields)), starts):
            products.extend(page["response"]["products"])
    return total, products


# ----------------------------------------------------------------------------- normalisation

def first(x):
    if isinstance(x, list):
        return x[0] if x else ""
    return "" if x is None else x


def clean(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


_UNIT_RE = re.compile(r"^\s*([\d.,]+)\s*/\s*(\d*)\s*([a-zA-Z][a-zA-Z0-9]*)\s*$")


def parse_comparison(cp: str) -> tuple[str, str]:
    """'1.43/1ltr' -> ('1.43', 'L'); '2.50/100g' -> ('25', 'kg'); unknown -> ('', '')."""
    if not cp:
        return "", ""
    m = _UNIT_RE.match(cp.replace("²", "2"))
    if not m:
        return "", ""
    try:
        value = float(m.group(1).replace(",", "."))
    except ValueError:
        return "", ""
    qty = float(m.group(2)) if m.group(2) else 1.0
    unit = m.group(3).lower()
    if unit in ("kg",):
        basis, scale = "kg", 1.0
    elif unit in ("g",):
        basis, scale = "kg", 1000.0
    elif unit in ("ltr", "l", "lt"):
        basis, scale = "L", 1.0
    elif unit in ("ml",):
        basis, scale = "L", 1000.0
    elif unit in ("pcs", "pc", "piece", "pieces", "tem"):
        basis, scale = "pc", 1.0
    elif unit in ("m2",):
        basis, scale = "m2", 1.0
    else:
        return "", ""
    per_basis = value / qty * scale
    return f"{per_basis:.4f}".rstrip("0").rstrip("."), basis


def flag(v) -> str:
    s = str(first(v)).strip().lower()
    return "1" if s in ("true", "1", "yes") else ("0" if s in ("false", "0", "no", "") else s)


def normalise(p: dict) -> dict:
    pid = str(p.get("uniqueId") or p.get("sku") or "").strip()
    unit_value, unit_basis = parse_comparison(clean(first(p.get("comparisonPrice"))))
    return {
        "id": pid,
        "ean": clean(first(p.get("barcode"))),
        "title": clean(first(p.get("title"))),
        "title_gr": clean(first(p.get("title_gr"))),
        "brand": clean(first(p.get("brand"))),
        "cat1": clean(first(p.get("categoryPath1"))),
        "cat2": clean(first(p.get("categoryPath2"))),
        "cat3": clean(first(p.get("categoryPath3"))),
        "subcategory": clean(first(p.get("subCategory"))),
        "price": clean(first(p.get("price"))),
        "original_price": clean(first(p.get("originalPrice"))),
        "discount": clean(first(p.get("discount"))),
        "comparison_price": clean(first(p.get("comparisonPrice"))),
        "unit_value": unit_value,
        "unit_basis": unit_basis,
        "availability": clean(first(p.get("availability"))).lower(),
        "stock_1003": clean(first(p.get("stock_1003"))),
        "stock_1004": clean(first(p.get("stock_1004"))),
        "stock_1005": clean(first(p.get("stock_1005"))),
        "status_4": clean(first(p.get("stockStatus_4"))),
        "status_5": clean(first(p.get("stockStatus_5"))),
        "status_6": clean(first(p.get("stockStatus_6"))),
        "promotion": clean(first(p.get("promotion"))),
        "organic": flag(p.get("organic")),
        "vegan": flag(p.get("vegan")),
        "vegetarian": flag(p.get("vegetarian")),
        "gluten_free": flag(p.get("glutenFree")),
        "lactose_free": flag(p.get("lactoseFree")),
        "kosher": flag(p.get("kosher")),
        "meat_free": flag(p.get("meatFree")),
        "pack_size_ml": clean(first(p.get("packSizeMl"))),
        "image_url": f"https://alphamega.com.cy/Files/Images/Products/{pid}.jpg" if pid else "",
    }


# ----------------------------------------------------------------------------- state / IO

def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    os.replace(tmp, path)


def append_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def upsert_csv(path: str, row: dict, fields: list[str], key: str = "date") -> None:
    """Append, but replace an existing row with the same key (same-day reruns)."""
    rows = [r for r in read_csv(path) if r.get(key) != row.get(key)]
    rows.append(row)
    write_csv(path, rows, fields)


def price_changed(prev: dict, cur: dict) -> bool:
    """A change in any price-relevant field. A field that was unknown before and is known
    now also counts, so the change-log can always be replayed into a complete state."""
    for f in PRICE_FIELDS:
        if prev.get(f, "") != cur.get(f, ""):
            return True
    return False


# ----------------------------------------------------------------------------- main

def run(data_dir: str, public_dir: str, date: str, dry_run: bool) -> int:
    t0 = time.time()
    latest_path = os.path.join(data_dir, "prices", "latest.csv")
    prev_rows = read_csv(latest_path)
    prev = {r["id"]: r for r in prev_rows}

    print(f"[{date}] fetching catalogue", flush=True)
    try:
        total, products = fetch_all()
    except Exception as e:  # noqa: BLE001
        print(f"[{date}] ERROR fetch failed: {e}", file=sys.stderr, flush=True)
        if not dry_run:
            append_csv(os.path.join(data_dir, "runs.csv"),
                       [{"date": date, "coverage": "0", "seconds": f"{time.time() - t0:.0f}", "ok": 0, "error": str(e)[:200]}],
                       ["date", "reported_total", "distinct", "available", "with_unit_price", "promo_with_original_price",
                        "promo_labelled", "new", "changed", "delisted", "relisted", "coverage", "seconds", "ok", "error"])
        return 2
    cur: dict[str, dict] = {}
    for p in products:
        row = normalise(p)
        if row["id"]:
            cur[row["id"]] = row  # de-duplicate by id
    coverage = len(cur) / total if total else 0
    print(f"[{date}] reported {total}, fetched {len(products)}, distinct {len(cur)}, coverage {coverage:.3f}", flush=True)
    ok = coverage >= MIN_COVERAGE
    if not ok:
        print(f"[{date}] ERROR coverage below {MIN_COVERAGE}; not writing state", file=sys.stderr, flush=True)

    changes: list[dict] = []
    n_new = n_changed = n_delisted = n_relisted = 0
    if ok:
        for pid, row in cur.items():
            old = prev.get(pid)
            row["last_seen"] = date
            row["delisted_on"] = ""
            if old is None:
                row["first_seen"] = date
                changes.append({"date": date, "id": pid, "event": "new", **row})
                n_new += 1
            else:
                row["first_seen"] = old.get("first_seen") or date
                if old.get("delisted_on"):
                    changes.append({"date": date, "id": pid, "event": "relisted", **row})
                    n_relisted += 1
                elif price_changed(old, row):
                    changes.append({"date": date, "id": pid, "event": "change", **row})
                    n_changed += 1
        for pid, old in prev.items():
            if pid not in cur:
                kept = dict(old)
                if not old.get("delisted_on"):
                    kept["delisted_on"] = date
                    changes.append({"date": date, "id": pid, "event": "delisted"})
                    n_delisted += 1
                cur[pid] = kept  # keep delisted products in state so relisting is detectable

    state = sorted(cur.values(), key=lambda r: r["id"])
    active = [r for r in state if not r.get("delisted_on")]
    summary = {
        "date": date,
        "reported_total": total,
        "distinct": len(active),
        "available": sum(1 for r in active if r["availability"] == "true"),
        "with_unit_price": sum(1 for r in active if r["unit_value"]),
        "promo_with_original_price": sum(1 for r in active if r["original_price"] not in ("", "0", "0.0")),
        "promo_labelled": sum(1 for r in active if r["promotion"]),
        "new": n_new, "changed": n_changed, "delisted": n_delisted, "relisted": n_relisted,
    }
    run_row = {**summary, "coverage": f"{coverage:.4f}", "seconds": f"{time.time() - t0:.0f}", "ok": int(ok), "error": ""}
    print(json.dumps(run_row), flush=True)

    if dry_run:
        return 0 if ok else 2
    append_csv(os.path.join(data_dir, "runs.csv"), [run_row], list(run_row.keys()))
    if not ok:
        return 2
    write_csv(latest_path, state, STATE_FIELDS)
    append_csv(os.path.join(data_dir, "prices", "changes", f"{date[:7]}.csv"), changes, CHANGE_FIELDS)
    write_csv(os.path.join(public_dir, "catalogue", "products.csv"), state, MASTER_FIELDS)
    upsert_csv(os.path.join(public_dir, "summary", "daily.csv"), summary, list(summary.keys()))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, help="private data repo checkout (full change-log)")
    ap.add_argument("--public-dir", required=True, help="public data dir (product master, summaries)")
    ap.add_argument("--date", default=dt.datetime.now(TZ).date().isoformat(), help="collection date, Europe/Nicosia")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    a = ap.parse_args()
    return run(a.data_dir, a.public_dir, a.date, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
