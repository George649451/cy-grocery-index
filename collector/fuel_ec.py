#!/usr/bin/env python3
"""Weekly Cyprus fuel prices from the European Commission's Weekly Oil Bulletin.

Source: https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en
The price-history workbook holds, for every EU member state, the consumer price
inclusive of duties and taxes in force each Monday, in EUR per 1000 litres, from
January 2005. It is a plain download: no login, no form, no CAPTCHA.

This replaces the per-station daily collection, which ended on 29 October 2026 when
the national observatory moved behind a CAPTCHA (see docs/DECISIONS.md).

Output
  <public-dir>/fuel/ec_weekly.csv   date, unleaded95, diesel, heating_oil  (EUR/L, taxes included)
  <public-dir>/fuel/ec_runs.csv     one row per run

The whole file is rewritten each run from the source workbook, so revisions the
Commission makes to past weeks are picked up. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from urllib.request import Request, urlopen

URL = "https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
USER_AGENT = "cy-price-index-bot/0.1 (+https://github.com/George649451/cy-grocery-index)"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
COLUMNS = {"CY_price_with_tax_euro95": "unleaded95", "CY_price_with_tax_diesel": "diesel",
           "CY_price_with_tax_heating_oil": "heating_oil"}
FIELDS = ["date", "unleaded95", "diesel", "heating_oil"]


def download(url: str, retries: int = 4) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"download failed: {last}")


def parse(blob: bytes) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(blob))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    target = None
    for s in wb.find("m:sheets", NS):
        if "with tax" in s.get("name", "").lower():
            target = rels[s.get("{%s}id" % NS["r"])]
    if not target:
        raise RuntimeError("no 'Prices with taxes' sheet in workbook")
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = ["".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]
    path = "xl/" + target.lstrip("/").removeprefix("xl/")
    rows = []
    for row in ET.fromstring(z.read(path)).iter("{%s}row" % NS["m"]):
        cells = {}
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            if v is None:
                continue
            col = re.match(r"[A-Z]+", c.get("r")).group(0)
            cells[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(cells)
    header = next((r for r in rows if any(v in COLUMNS for v in r.values())), None)
    if header is None:
        raise RuntimeError("Cyprus columns not found; the workbook layout has changed")
    col_of = {COLUMNS[v]: k for k, v in header.items() if v in COLUMNS}
    if set(col_of) != set(COLUMNS.values()):
        raise RuntimeError(f"missing Cyprus columns: {set(COLUMNS.values()) - set(col_of)}")
    out = []
    for r in rows:
        try:
            date = (dt.date(1899, 12, 30) + dt.timedelta(days=float(r["A"]))).isoformat()
        except (KeyError, ValueError):
            continue
        rec = {"date": date}
        for name, col in col_of.items():
            try:
                v = float(r[col])
            except (KeyError, ValueError):
                v = None
            # EUR per 1000 L -> EUR per L; a zero or absurd figure is a hole in the source, not a price
            rec[name] = f"{v / 1000:.4f}" if v and 200 < v < 5000 else ""
        if any(rec[n] for n in col_of):
            out.append(rec)
    out.sort(key=lambda x: x["date"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public-dir", required=True)
    ap.add_argument("--file", help="parse a local workbook instead of downloading")
    a = ap.parse_args()
    t0 = time.time()
    fdir = os.path.join(a.public_dir, "fuel")
    os.makedirs(fdir, exist_ok=True)
    run = {"run_date": dt.date.today().isoformat(), "weeks": "", "latest_week": "", "seconds": "", "ok": 0, "error": ""}
    try:
        rows = parse(open(a.file, "rb").read() if a.file else download(URL))
        if len(rows) < 1000:
            raise RuntimeError(f"only {len(rows)} weekly rows parsed; expected 1,000+")
        prev_path = os.path.join(fdir, "ec_weekly.csv")
        if os.path.exists(prev_path):
            prev_latest = max(r["date"] for r in csv.DictReader(open(prev_path, encoding="utf-8")))
            if rows[-1]["date"] < prev_latest:
                raise RuntimeError(f"source ends {rows[-1]['date']}, before what is already stored ({prev_latest})")
        tmp = prev_path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, prev_path)
        run.update(weeks=len(rows), latest_week=rows[-1]["date"], ok=1)
        print(f"{len(rows)} weeks, {rows[0]['date']} -> {rows[-1]['date']}: {rows[-1]}", flush=True)
    except Exception as e:  # noqa: BLE001
        run["error"] = str(e)[:200]
        print(f"ERROR {e}", file=sys.stderr, flush=True)
    run["seconds"] = f"{time.time() - t0:.0f}"
    runs = os.path.join(fdir, "ec_runs.csv")
    new = not os.path.exists(runs)
    with open(runs, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(run.keys()))
        if new:
            w.writeheader()
        w.writerow(run)
    return 0 if run["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
