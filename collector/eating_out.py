#!/usr/bin/env python3
"""Eating-out collector: a fixed list of menu items read from restaurants' own websites.

The list lives in <public-dir>/eating_out/items.csv. Each row names a restaurant, a menu
page and a regular expression that locates one item and captures its price. `{P}` in a
pattern stands for the price number. Patterns are matched against the page's visible text
(tags removed, whitespace collapsed), so they survive most markup changes.

Only menus published on a restaurant's own site are read. Delivery platforms and review
sites are not used. Menu prices change rarely, so the check runs weekly.

Outputs under <public-dir>/eating_out/
  prices.csv      date, item_id, price     one row per item per check that found it
  anomalies.csv   observations set aside (a price that more than doubles or halves)
  runs.csv        one row per check: items found, missing, pages that failed

A menu may also be a PDF. Give its address directly in `url`, or, when the file name
changes with each edition, give the page that links to it in `url` and a pattern for
the link in `doc_link`. PDF text needs the optional pypdf package; without it those
items are reported as missing and everything else still runs.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import os
import re
import sys
import time
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; cy-price-index-bot/0.1; +https://github.com/George649451/cy-grocery-index)"
PRICE = r"(\d{1,3}(?:[.,]\d{1,2})?)"
PRICE_FIELDS = ["date", "item_id", "price"]
ANOMALY_FIELDS = ["date", "item_id", "price_listed", "previous_price"]
RUN_FIELDS = ["date", "items", "found", "missing", "pages_failed", "changed", "ok", "detail"]


def fetch(url: str, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            with urlopen(Request(quote(url, safe=":/?&=%#+,;@()!*'~$-._"), headers={"User-Agent": USER_AGENT}), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def pdf_text(blob: bytes) -> str:
    try:
        import pypdf  # type: ignore
    except ImportError as e:
        raise RuntimeError("PDF menu but pypdf is not installed") from e
    import io
    import logging
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(io.BytesIO(blob))
    return re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in reader.pages)).strip()


def menu_text(url: str, doc_link: str = "") -> str:
    """Visible text of a menu: an HTML page, a PDF, or a PDF linked from a page."""
    blob = fetch(url)
    if doc_link:
        m = re.search(doc_link, blob.decode("utf-8", "replace"))
        if not m:
            raise RuntimeError(f"{url}: no link matching {doc_link!r}")
        blob = fetch(urljoin(url, html.unescape(m.group(1))))
    if blob[:5] == b"%PDF-":
        return pdf_text(blob)
    return visible_text(blob.decode("utf-8", "replace"))


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r'src="data:[^"]*"', "", page)          # inline images can run to megabytes
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def find_price(text: str, pattern: str):
    """First match of the item's pattern; the captured group is the price."""
    m = re.search(pattern.replace("{P}", PRICE), text)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return v if 0.3 <= v <= 300 else None


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in fields} for r in rows)
    os.replace(tmp, path)


def run(public_dir: str, date: str, dry_run: bool) -> int:
    edir = os.path.join(public_dir, "eating_out")
    items = [r for r in read_csv(os.path.join(edir, "items.csv")) if r.get("active", "1") != "0"]
    if not items:
        print("no items configured", file=sys.stderr)
        return 2

    pages, failed = {}, []
    for key in sorted({(r["url"], r.get("doc_link", "") or "") for r in items}):
        try:
            pages[key] = menu_text(*key)
        except Exception as e:  # noqa: BLE001
            failed.append(key[0])
            print(f"[{date}] page failed: {e}", file=sys.stderr, flush=True)
        time.sleep(1)

    prices_path = os.path.join(edir, "prices.csv")
    history = read_csv(prices_path)
    last = {}
    for r in sorted(history, key=lambda x: x["date"]):
        if r["date"] < date:
            last[r["item_id"]] = float(r["price"])

    found, missing, anomalies, changed = [], [], [], 0
    for it in items:
        text = pages.get((it["url"], it.get("doc_link", "") or ""))
        price = find_price(text, it["pattern"]) if text else None
        if price is None:
            missing.append(it["item_id"])
            continue
        prev = last.get(it["item_id"])
        if prev and not (0.5 <= price / prev <= 2):
            # a menu price does not double or halve between weekly checks; treat as a parsing slip
            anomalies.append({"date": date, "item_id": it["item_id"], "price_listed": f"{price:.2f}", "previous_price": f"{prev:.2f}"})
            missing.append(it["item_id"])
            continue
        if prev is not None and abs(price - prev) > 0.004:
            changed += 1
            print(f"[{date}] CHANGE {it['item_id']}: {prev:.2f} -> {price:.2f}", flush=True)
        found.append({"date": date, "item_id": it["item_id"], "price": f"{price:.2f}"})

    ok = len(found) >= 0.6 * len(items)
    detail = ("missing: " + " ".join(missing)) if missing else ""
    run_row = {"date": date, "items": len(items), "found": len(found), "missing": len(missing),
               "pages_failed": len(failed), "changed": changed, "ok": int(ok), "detail": detail[:300]}
    print(run_row, flush=True)
    if dry_run:
        for r in found:
            print("  ", r["item_id"], r["price"])
        return 0 if ok else 2

    runs_path = os.path.join(edir, "runs.csv")
    write_csv(runs_path, read_csv(runs_path) + [run_row], RUN_FIELDS)
    anomalies_path = os.path.join(edir, "anomalies.csv")
    write_csv(anomalies_path, read_csv(anomalies_path) + anomalies, ANOMALY_FIELDS)
    if not ok:
        return 2
    kept = [r for r in history if r["date"] != date]          # a same-day rerun replaces that day's rows
    write_csv(prices_path, sorted(kept + found, key=lambda r: (r["date"], r["item_id"])), PRICE_FIELDS)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public-dir", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return run(a.public_dir, a.date, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
