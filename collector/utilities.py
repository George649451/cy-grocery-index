#!/usr/bin/env python3
"""Utilities collector: electricity (EAC) and water (district organisations).

Published tariffs change rarely, so this is a register of changes rather than a
daily price scrape. Each source is fetched and parsed independently; a source that
fails keeps its previous data and is reported in runs.csv.

Sources
  EAC domestic tariff, Code 01   kWh price calculation page (HTML table) on eac.com.cy
  EAC fuel adjustment            monthly table on eac.com.cy (current year)
  Limassol water                 eoalemesos.org.cy
  Larnaca water                  eoal.org.cy
  Famagusta water (Paralimni)    eoaa.org.cy

Outputs under <public-dir>/utilities/
  eac_tariff.csv            one row per tariff version seen (appended when anything changes)
  eac_fuel_adjustment.csv   one row per billing month (bi-monthly consumers, low voltage)
  water_tariffs.csv         current tariff components per district
  changes.csv               every detected change: date, source, item, old, new
  runs.csv                  one row per run and source

Standard library only. The EAC tariff PDF is read for its effective date only when
the optional pypdf package is installed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import os
import re
import sys
import time
from urllib.parse import urljoin
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; cy-price-index-bot/0.1; +https://github.com/George649451/cy-grocery-index)"

EAC_BASE = "https://www.eac.com.cy/en/supply/for-the-house/electricity-tariffs/"
EAC_CALC = EAC_BASE + "kwh-price-calculation/"
EAC_TYPES = EAC_BASE + "electricity-tariffs-types/"
EAC_FUEL = EAC_BASE + "fuel-price-adjustment/"
LIMASSOL_WATER = "https://eoalemesos.org.cy/el/water-supply-service"
LIMASSOL_FEES = "https://eoalemesos.org.cy/en/fees"
LARNACA_WATER = "https://eoal.org.cy/en/service/fees/water-charges/"
FAMAGUSTA_WATER = "https://eoaa.org.cy/en/water-fees/"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"])}

TARIFF_FIELDS = ["first_seen", "effective_from", "code", "base_fuel_eur_mt", "energy_cent_kwh", "network_cent_kwh",
                 "ancillary_cent_kwh", "meter_eur_bimonthly", "supply_eur_bimonthly", "source_doc"]
FUEL_FIELDS = ["bill_month", "fuel_price_eur_mt", "coefficient_low", "adjustment_cent_kwh", "revised_cent_kwh",
               "implied_base_eur_mt", "first_seen"]
WATER_FIELDS = ["district", "area", "period_months", "component", "from_m3", "to_m3", "value_eur", "source_url", "last_checked"]
CHANGE_FIELDS = ["date", "source", "item", "old", "new"]
RUN_FIELDS = ["date", "source", "ok", "detail"]


# ----------------------------------------------------------------------------- helpers

def fetch(url: str, binary: bool = False, retries: int = 3):
    last = None
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as r:
                data = r.read()
                return data if binary else data.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def strip_noise(page: str) -> str:
    return re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page, flags=re.S)


def clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def tables_after(page: str, marker: str, count: int = 1) -> list[list[list[str]]]:
    """The first `count` tables that follow `marker` in the page, as rows of cell text."""
    page = strip_noise(page)
    # tolerate tags and whitespace between the words of the marker
    pattern = r"(?:\s|<[^>]+>|&nbsp;)+".join(re.escape(w) for w in marker.split())
    m0 = re.search(pattern, page)
    if not m0:
        raise RuntimeError(f"marker not found: {marker!r}")
    i = m0.start()
    out = []
    for m in list(re.finditer(r"<table.*?</table>", page[i:], re.S))[:count]:
        out.append([[clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
                    for r in re.findall(r"<tr.*?</tr>", m.group(0), re.S)])
    if len(out) < count:
        raise RuntimeError(f"expected {count} table(s) after {marker!r}, found {len(out)}")
    return out


def num(text: str, decimal_comma: bool = True):
    """'1.234,56' -> 1234.56 with decimal_comma, '21.50' -> 21.5 without. None if not a number."""
    t = text.replace("€", "").replace("​", "").strip()
    if not re.search(r"\d", t):
        return None
    t = t.replace(".", "").replace(",", ".") if decimal_comma else t.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    return float(m.group(0)) if m else None


def fmt(v) -> str:
    return "" if v is None else (f"{v:.8f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v))


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


# ----------------------------------------------------------------------------- EAC

def parse_eac_tariff(calc_page: str) -> dict:
    """Code 01 basic prices from the 'kWh price calculation' example table."""
    text = clean(strip_noise(calc_page))
    base = re.search(r"fuel price of €\s?([\d.,]+) per Metric Tonne", text)
    table = tables_after(calc_page, "Code 01", 1)[0]
    found = {}
    for row in table:
        cells = [c for c in row if c != ""]
        if not cells:
            continue
        label = cells[0].lower()
        values = [num(c) for c in cells[1:] if num(c) is not None]
        if not values:
            continue
        if label.startswith("energy charge"):
            found["energy_cent_kwh"] = values[0]
        elif label.startswith("network charge"):
            found["network_cent_kwh"] = values[0]
        elif label.startswith("ancillary"):
            found["ancillary_cent_kwh"] = values[0]
        elif label.startswith("meter"):
            found["meter_eur_bimonthly"] = values[-1]
        elif label.startswith("supply charge"):
            found["supply_eur_bimonthly"] = values[-1]
    missing = {"energy_cent_kwh", "network_cent_kwh", "meter_eur_bimonthly", "supply_eur_bimonthly"} - set(found)
    if missing:
        raise RuntimeError(f"Code 01 table: missing {sorted(missing)}")
    found.setdefault("ancillary_cent_kwh", 0.0)
    if not (5 < found["energy_cent_kwh"] < 60 and 0 < found["network_cent_kwh"] < 20):
        raise RuntimeError(f"Code 01 values out of range: {found}")
    found["base_fuel_eur_mt"] = num(base.group(1)) if base else None
    found["code"] = "01"
    return found


def find_tariff_doc(types_page: str) -> str:
    m = re.search(r'href="([^"]*Domestic[^"]*Tariff[^"]*\.pdf)"', types_page, re.I)
    return urljoin(EAC_TYPES, m.group(1)) if m else ""


def effective_date_from_pdf(url: str) -> str:
    """'Applicable from 1st of May 2026' -> 2026-05-01. Needs the optional pypdf package."""
    try:
        import pypdf  # type: ignore
    except ImportError:
        return ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(fetch(url, binary=True)))
        text = " ".join((p.extract_text() or "") for p in reader.pages[:2])
        m = re.search(r"Applicable from\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+([A-Za-z]+)\s+(\d{4})", text)
        if m and m.group(2) in MONTHS:
            return dt.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).isoformat()
    except Exception:  # noqa: BLE001
        pass
    return ""


def parse_eac_fuel(page: str, today: dt.date) -> list[dict]:
    """Monthly fuel adjustment for low-voltage, bi-monthly (household) consumers."""
    year = None
    m = re.search(r'href="[^"]*Fuel-Adjustment-\d{4}-(\d{4})[^"]*\.xlsx"', page, re.I)
    if m:
        year = int(m.group(1))
    table = tables_after(page, "Fuel Adjustment for the current year", 1)[0]
    if year is None:
        nxt = [re.search(r"January (\d{4})", c) for r in table for c in r]
        nxt = [x for x in nxt if x]
        year = int(nxt[0].group(1)) - 1 if nxt else today.year
    out = []
    for i, row in enumerate(table):
        if not row or row[0] != "HIGH" or len(row) < 11:
            continue
        label, price = row[3], num(row[4])
        if price is None:
            continue                                   # month not published yet
        low = next((r for r in table[i + 1:i + 3] if r and r[0] == "LOW"), None)
        if low is None or len(low) < 8:
            raise RuntimeError(f"no LOW voltage row for {label}")
        name = label.split()[0]
        if name not in MONTHS:
            raise RuntimeError(f"unrecognised month label {label!r}")
        y = int(label.split()[1]) if len(label.split()) > 1 and label.split()[1].isdigit() else year
        coef, adj, revised = num(low[1]), num(low[3]), num(low[7])
        if None in (coef, adj, revised) or not (300 < price < 3000) or not (-20 < revised < 40):
            raise RuntimeError(f"implausible fuel adjustment row for {label}: {row} / {low}")
        out.append({"bill_month": f"{y}-{MONTHS[name]:02d}", "fuel_price_eur_mt": price, "coefficient_low": coef,
                    "adjustment_cent_kwh": adj, "revised_cent_kwh": revised,
                    "implied_base_eur_mt": round(price - adj / (coef * 100), 1) if coef else None})
    if not out:
        raise RuntimeError("fuel adjustment table has no published months")
    return out


# ----------------------------------------------------------------------------- water

def water_row(district, area, period, component, lo, hi, value, url):
    return {"district": district, "area": area, "period_months": period, "component": component,
            "from_m3": fmt(lo), "to_m3": fmt(hi), "value_eur": fmt(value), "source_url": url}


def check_bands(name: str, rows: list[dict]) -> None:
    bands = [r for r in rows if r["component"] == "band"]
    if len(bands) < 3:
        raise RuntimeError(f"{name}: only {len(bands)} consumption bands parsed")
    for r in rows:
        v = float(r["value_eur"])
        if not (0 <= v < 200):
            raise RuntimeError(f"{name}: implausible value {r}")


def parse_limassol(water_page: str, fees_page: str) -> list[dict]:
    fixed_t, band_t = tables_after(water_page, "Οικιακά τέλη ανά τετραμηνία", 2)
    rows = []
    for r in fixed_t:
        if len(r) >= 2 and num(r[1]) is not None:
            if r[0].startswith("Πάγιο"):
                rows.append(water_row("Limassol", "", 4, "fixed", None, None, num(r[1]), LIMASSOL_WATER))
            elif "Συντήρησης" in r[0]:
                rows.append(water_row("Limassol", "", 4, "maintenance", None, None, num(r[1]), LIMASSOL_WATER))
    for r in band_t:
        if len(r) >= 3 and num(r[0]) is not None and num(r[2]) is not None:
            rows.append(water_row("Limassol", "", 4, "band", num(r[0]), num(r[1]), num(r[2]), LIMASSOL_WATER))
    m = re.search(r"fee is set at €\s?([\d.]+) per cubic metre", clean(strip_noise(fees_page)))
    if m:
        rows.append(water_row("Limassol", "", 4, "sewerage_per_m3", None, None, float(m.group(1)), LIMASSOL_FEES))
    if not any(r["component"] == "fixed" for r in rows):
        raise RuntimeError("Limassol: fixed charge not found")
    check_bands("Limassol", rows)
    return rows


def parse_larnaca(page: str) -> list[dict]:
    table = tables_after(page, "Οικιακή (ανά τριμηνία)", 1)[0]
    rows = []
    for r in table:
        if len(r) == 2 and num(r[1]) is not None:
            if r[0].startswith("Πάγιο"):
                rows.append(water_row("Larnaca", "", 3, "fixed", None, None, num(r[1]), LARNACA_WATER))
            elif "Συντήρησης" in r[0]:
                rows.append(water_row("Larnaca", "", 3, "maintenance", None, None, num(r[1]), LARNACA_WATER))
        elif len(r) == 4 and num(r[3]) is not None:
            if r[0].startswith(">"):
                rows.append(water_row("Larnaca", "", 3, "band", num(r[0]) + 1, None, num(r[3]), LARNACA_WATER))
            elif num(r[0]) is not None and num(r[2]) is not None:
                rows.append(water_row("Larnaca", "", 3, "band", num(r[0]), num(r[2]), num(r[3]), LARNACA_WATER))
    m = re.search(r"αποχετευτικού \(Ευρώ\s?([\d,]+) ανά κ\.μ", clean(strip_noise(page)))
    if m:
        rows.append(water_row("Larnaca", "", 3, "sewerage_per_m3", None, None, num(m.group(1)), LARNACA_WATER))
    if not any(r["component"] == "fixed" for r in rows):
        raise RuntimeError("Larnaca: fixed charge not found")
    check_bands("Larnaca", rows)
    return rows


def parse_famagusta(page: str) -> list[dict]:
    """Paralimni, residential. The page does not state the billing period length."""
    table = tables_after(page, "Water rates for the Municipal District of Paralimni", 1)[0]
    rows = []
    for r in table:
        if len(r) != 2 or num(r[1], decimal_comma=False) is None:
            continue
        label, value = r[0], num(r[1], decimal_comma=False)
        span = re.findall(r"\d+", label)
        if "flat" in label.lower() or "fixed" in label.lower():
            rows.append(water_row("Famagusta", "Paralimni", "", "flat_including_first_band", 0,
                                  float(span[1]) if len(span) > 1 else None, value, FAMAGUSTA_WATER))
        elif label.strip().startswith(">") and span:
            rows.append(water_row("Famagusta", "Paralimni", "", "band", float(span[0]), None, value, FAMAGUSTA_WATER))
        elif len(span) >= 2:
            rows.append(water_row("Famagusta", "Paralimni", "", "band", float(span[0]), float(span[1]), value, FAMAGUSTA_WATER))
    if not any(r["component"] == "flat_including_first_band" for r in rows):
        raise RuntimeError("Famagusta: flat rate not found")
    check_bands("Famagusta", rows)
    return rows


# ----------------------------------------------------------------------------- main

def run(public_dir: str, date: str) -> int:
    udir = os.path.join(public_dir, "utilities")
    os.makedirs(udir, exist_ok=True)
    today = dt.date.fromisoformat(date)
    runs, changes = [], []

    def attempt(name, fn):
        try:
            detail = fn()
            runs.append({"date": date, "source": name, "ok": 1, "detail": detail})
            print(f"[{date}] {name}: {detail}", flush=True)
        except Exception as e:  # noqa: BLE001
            runs.append({"date": date, "source": name, "ok": 0, "detail": str(e)[:200]})
            print(f"[{date}] {name}: ERROR {e}", file=sys.stderr, flush=True)

    # --- EAC tariff: append a row when any value or the source document changes
    def eac_tariff():
        cur = parse_eac_tariff(fetch(EAC_CALC))
        try:
            cur["source_doc"] = find_tariff_doc(fetch(EAC_TYPES))
        except Exception:  # noqa: BLE001
            cur["source_doc"] = ""
        path = os.path.join(udir, "eac_tariff.csv")
        prev_rows = read_csv(path)
        prev = prev_rows[-1] if prev_rows else None
        keys = ["base_fuel_eur_mt", "energy_cent_kwh", "network_cent_kwh", "ancillary_cent_kwh",
                "meter_eur_bimonthly", "supply_eur_bimonthly"]
        row = {k: fmt(cur.get(k)) for k in keys}
        row.update(code="01", source_doc=cur["source_doc"], first_seen=date)
        if prev is not None:
            diffs = [k for k in keys if prev.get(k, "") != row[k]]
            doc_changed = bool(row["source_doc"]) and prev.get("source_doc", "") != row["source_doc"]
            if not diffs and not doc_changed:
                return f"unchanged: energy {row['energy_cent_kwh']} + network {row['network_cent_kwh']} cent/kWh"
            for k in diffs:
                changes.append({"date": date, "source": "eac_tariff", "item": k, "old": prev.get(k, ""), "new": row[k]})
            if doc_changed:
                changes.append({"date": date, "source": "eac_tariff", "item": "source_doc",
                                "old": prev.get("source_doc", ""), "new": row["source_doc"]})
        row["effective_from"] = effective_date_from_pdf(row["source_doc"]) if row["source_doc"] else ""
        append_csv(path, [row], TARIFF_FIELDS)
        return f"new tariff version recorded: energy {row['energy_cent_kwh']}, network {row['network_cent_kwh']} cent/kWh, effective {row['effective_from'] or 'unknown'}"

    # --- EAC fuel adjustment: upsert by billing month; revisions to a past month are logged
    def eac_fuel():
        cur = parse_eac_fuel(fetch(EAC_FUEL), today)
        path = os.path.join(udir, "eac_fuel_adjustment.csv")
        prev = {r["bill_month"]: r for r in read_csv(path)}
        added = 0
        for r in cur:
            row = {k: fmt(r[k]) for k in FUEL_FIELDS if k in r}
            old = prev.get(row["bill_month"])
            if old is None:
                row["first_seen"] = date
                added += 1
            else:
                row["first_seen"] = old.get("first_seen", date)
                if old.get("revised_cent_kwh") != row["revised_cent_kwh"]:
                    changes.append({"date": date, "source": "eac_fuel_adjustment", "item": row["bill_month"],
                                    "old": old.get("revised_cent_kwh", ""), "new": row["revised_cent_kwh"]})
            prev[row["bill_month"]] = row
        write_csv(path, sorted(prev.values(), key=lambda x: x["bill_month"]), FUEL_FIELDS)
        last = cur[-1]
        return f"{len(cur)} months on page, {added} new; latest {last['bill_month']}: fuel €{last['fuel_price_eur_mt']}/MT, revised adjustment {last['revised_cent_kwh']} cent/kWh"

    # --- water: replace a district's rows only when its page parsed cleanly; log component changes
    water_path = os.path.join(udir, "water_tariffs.csv")
    water = read_csv(water_path)

    def water_source(district, parse):
        def go():
            nonlocal water
            rows = parse()
            for r in rows:
                r["last_checked"] = date
            key = lambda r: (r["component"], r["from_m3"], r["to_m3"])
            old = {key(r): r for r in water if r["district"] == district}
            new = {key(r): r for r in rows}
            n_changes = 0
            if old:
                for k in sorted(set(old) | set(new)):
                    a, b = old.get(k, {}).get("value_eur", ""), new.get(k, {}).get("value_eur", "")
                    if a != b:
                        changes.append({"date": date, "source": f"water_{district.lower()}",
                                        "item": " ".join(x for x in k if x), "old": a, "new": b})
                        n_changes += 1
            water = [r for r in water if r["district"] != district] + rows
            return f"{len(rows)} components, {n_changes} changed"
        return go

    attempt("eac_tariff", eac_tariff)
    attempt("eac_fuel_adjustment", eac_fuel)
    attempt("water_limassol", water_source("Limassol", lambda: parse_limassol(fetch(LIMASSOL_WATER), fetch(LIMASSOL_FEES))))
    attempt("water_larnaca", water_source("Larnaca", lambda: parse_larnaca(fetch(LARNACA_WATER))))
    attempt("water_famagusta", water_source("Famagusta", lambda: parse_famagusta(fetch(FAMAGUSTA_WATER))))

    if water:
        write_csv(water_path, sorted(water, key=lambda r: (r["district"], r["component"] != "fixed", r["component"],
                                                          float(r["from_m3"] or 0))), WATER_FIELDS)
    append_csv(os.path.join(udir, "changes.csv"), changes, CHANGE_FIELDS)
    append_csv(os.path.join(udir, "runs.csv"), runs, RUN_FIELDS)
    failed = [r["source"] for r in runs if not r["ok"]]
    print(f"[{date}] {len(runs) - len(failed)} of {len(runs)} sources ok, {len(changes)} changes" +
          (f"; failed: {failed}" if failed else ""), flush=True)
    return 0 if len(failed) < len(runs) else 2      # fail the job only if every source failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--public-dir", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    return run(a.public_dir, a.date)


if __name__ == "__main__":
    sys.exit(main())
