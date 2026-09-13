#!/usr/bin/env python3
"""Extract the daily price panel for the real basket from the private change-log.

Replays <data-dir>/prices/changes/*.csv for the ids in
<public-dir>/basket/real_basket.csv and writes <public-dir>/basket/prices.csv:
one row per basket item per collection date, carrying the price state as of
that date. This is the basket-level raw data that is published; the full
catalogue change-log stays private.
"""
import argparse
import csv
import glob
import os
import sys

OUT_FIELDS = ["date", "id", "price", "original_price", "unit_value", "unit_basis", "promotion", "availability", "delisted"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--public-dir", required=True)
    a = ap.parse_args()

    basket = list(csv.DictReader(open(os.path.join(a.public_dir, "basket", "real_basket.csv"), encoding="utf-8")))
    ids = {b["id"]: b for b in basket}

    # collection dates = every date that has a run row with ok=1
    runs = list(csv.DictReader(open(os.path.join(a.data_dir, "runs.csv"), encoding="utf-8")))
    dates = sorted({r["date"] for r in runs if r.get("ok") == "1"})

    # replay the change-log for basket ids only
    events: dict[str, list[dict]] = {i: [] for i in ids}
    for path in sorted(glob.glob(os.path.join(a.data_dir, "prices", "changes", "*.csv"))):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r["id"] in events:
                events[r["id"]].append(r)
    for evs in events.values():
        evs.sort(key=lambda r: r["date"])

    out = []
    for d in dates:
        for pid, b in ids.items():
            state = None
            delisted = False
            for e in events[pid]:
                if e["date"] > d:
                    break
                if e["event"] == "delisted":
                    delisted = True
                else:
                    state = e
                    delisted = False
            if state is None:
                continue  # not yet in catalogue on that date
            if b.get("hand_pack_size"):
                # no comparisonPrice in the API: unit price = pack price / hand-assigned pack size
                try:
                    uv = f"{float(state['price']) / float(b['hand_pack_size']):.4f}".rstrip("0").rstrip(".")
                except (ValueError, ZeroDivisionError):
                    uv = ""
                ub = b["basis"]
            else:
                uv, ub = state.get("unit_value", ""), state.get("unit_basis", "")
            out.append({"date": d, "id": pid, "price": state.get("price", ""), "original_price": state.get("original_price", ""),
                        "unit_value": uv, "unit_basis": ub, "promotion": state.get("promotion", ""),
                        "availability": state.get("availability", ""), "delisted": "1" if delisted else ""})

    path = os.path.join(a.public_dir, "basket", "prices.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(out)} rows for {len(ids)} items over {len(dates)} dates -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
