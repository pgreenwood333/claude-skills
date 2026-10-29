#!/usr/bin/env python3
"""MDOT (Mississippi DOT) item bid price lookup.

Pulls MDOT's public "Item Bid Prices" report (AASHTOWare report page embedded on
mdot.ms.gov/portal/item_bid_prices) for any date range and returns, per pay item:
min/max/avg quantity and low/high/avg unit price.

Lookup rule for each item: search Jan 1 of this year -> today. If the item has no bids,
widen to Jan 1 of last year -> today, and so on, up to 10 years back. Because the ranges
nest, an item first found in the range starting Jan 1 of year X was last bid in year X,
so that range's numbers all come from year X (the "price year").

Usage:
  mdot_bid_prices.py lookup 203-A002 907-403-A015 [--today 2026-10-29] [--refresh]
  mdot_bid_prices.py lookup --file items.json --out prices.json
  mdot_bid_prices.py range 1/1/2025 12/31/2025 --out bids_2025.xlsx
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import openpyxl
import requests

URL = "https://aashtoreports.mdot.ms.gov/trnsreportspublic/reports/BidPrices.aspx"
def _cache_dir() -> Path:
    """MDOT_BID_CACHE if set, else the external drive on Peyton's Mac, else ~/.cache (e.g. in Cowork)."""
    if os.environ.get("MDOT_BID_CACHE"):
        return Path(os.environ["MDOT_BID_CACHE"])
    if Path("/Volumes/PGExtHD").is_dir():
        return Path("/Volumes/PGExtHD/OPCC/cache")
    return Path.home() / ".cache" / "mdot-bid-prices"


CACHE_DIR = _cache_dir()
MAX_YEARS_BACK = 10
FRESH_DAYS = 7  # ranges that end "today" are reused for this many days

# DevExpress asks for these on every postback (copied from the live page).
_DX = {
    "DXScript": "1_11,1_12,1_252,1_23,1_64,1_14,1_15,1_183,1_184,1_21,1_22,1_190,1_192,1_17,1_41,"
                "1_194,1_182,1_19,1_213,1_224,1_225,1_211,1_227,1_236,1_238,1_239,1_230,1_234,1_240",
    "DXCss": "1_68,1_209,1_206,1_210,1_207,1_254,1_74,1_253,1_73",
}
_COLS = ["item", "description", "unit", "min_qty", "low_price", "max_qty", "high_price", "avg_qty", "avg_price"]


class MDOTError(RuntimeError):
    pass


def _mdy(d: dt.date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def _hidden(html: str) -> dict:
    return dict(re.findall(r'name="(__[A-Z]+)"[^>]*value="([^"]*)"', html))


def _date_fields(start: dt.date, end: dt.date) -> dict:
    out = {}
    for name, d in (("f_sdate", start), ("f_edate", end)):
        ms = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
        out[name] = _mdy(d)
        out[name + "$State"] = ('{&quot;rawValue&quot;:&quot;%d&quot;,'
                                '&quot;useMinDateInsteadOfNull&quot;:false}' % ms)
    return out


def download_range(start: dt.date, end: dt.date, retries: int = 3) -> bytes | None:
    """Download MDOT's Excel export for [start, end]. Returns None when MDOT has no bids in the range."""
    want = f"From {_mdy(start)} to {_mdy(end)}"
    last = None
    for attempt in range(retries):
        try:
            s = requests.Session()
            s.headers["User-Agent"] = "Mozilla/5.0 (OPCC bid price lookup)"
            html = s.get(URL, timeout=60).text
            form = {"__EVENTTARGET": "", "__EVENTARGUMENT": "", **_date_fields(start, end), **_DX}
            html = s.post(URL, data={**_hidden(html), **form, "run": "Retrieve Data"}, timeout=600).text
            if want not in html:
                raise MDOTError(f"MDOT did not run the requested range ({want}); the page may have changed")
            if not re.search(r">\d{3,4}-[A-Z0-9]+<", html):  # grid has no pay items
                return None
            r = s.post(URL, data={**_hidden(html), **form, "Button2": "Save to Excel"}, timeout=600)
            if "spreadsheetml" not in r.headers.get("content-type", ""):
                raise MDOTError("MDOT did not return an Excel file")
            rows = _read_rows(r.content)
            if rows["title"] != want:
                raise MDOTError(f"Excel export is for '{rows['title']}', expected '{want}'")
            return r.content
        except (requests.RequestException, MDOTError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise MDOTError(f"Could not download MDOT bid prices for {want}: {last}")


def _read_rows(xlsx: bytes) -> dict:
    ws = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    title = str(rows[0][0] or "").strip() if rows else ""
    items = {}
    for r in rows[2:]:
        if not r or not r[0]:
            continue
        rec = dict(zip(_COLS, r))
        rec["item"] = str(rec["item"]).strip()
        items[rec["item"]] = rec
    return {"title": title, "items": items}


def _cache_path(start: dt.date, end: dt.date, today: dt.date) -> Path:
    # Ranges ending today are stored by download date so they can be refreshed.
    return CACHE_DIR / f"bids_{start:%Y%m%d}_{end:%Y%m%d}.xlsx"


def get_range(start: dt.date, end: dt.date, refresh: bool = False) -> dict:
    """Items for a date range, using the cache. Returns {'title','items','downloaded','empty'}."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    open_ended = end >= today - dt.timedelta(days=1)
    if not refresh:
        for f in sorted(CACHE_DIR.glob(f"bids_{start:%Y%m%d}_*.*"), reverse=True):
            m = re.match(r"bids_\d{8}_(\d{8})\.(xlsx|empty)$", f.name)
            if not m:
                continue
            cend = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
            if cend == end or (open_ended and cend >= end - dt.timedelta(days=FRESH_DAYS) and cend <= end):
                return _load_cached(f, start, cend)
    data = download_range(start, end)
    path = _cache_path(start, end, today)
    if data is None:
        path.with_suffix(".empty").write_text(dt.datetime.now().isoformat())
        return {"title": f"From {_mdy(start)} to {_mdy(end)}", "items": {}, "start": start, "end": end,
                "downloaded": dt.date.today().isoformat(), "empty": True}
    path.write_bytes(data)
    return _load_cached(path, start, end)


def _load_cached(path: Path, start: dt.date, end: dt.date) -> dict:
    downloaded = dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
    if path.suffix == ".empty":
        return {"title": f"From {_mdy(start)} to {_mdy(end)}", "items": {}, "start": start, "end": end,
                "downloaded": downloaded, "empty": True}
    rows = _read_rows(path.read_bytes())
    return {**rows, "start": start, "end": end, "downloaded": downloaded, "empty": False}


def lookup(items: list[str], today: dt.date | None = None, refresh: bool = False,
           years_back: int = MAX_YEARS_BACK, log=lambda m: None) -> dict:
    """Apply the widening date-range rule to each pay item. Returns {item: result}."""
    today = today or dt.date.today()
    wanted = [i.strip().upper() for i in items if i and i.strip()]
    out = {}
    pending = list(dict.fromkeys(wanted))
    for k in range(years_back):
        if not pending:
            break
        start = dt.date(today.year - k, 1, 1)
        log(f"Searching {_mdy(start)} - {_mdy(today)} for {len(pending)} item(s)")
        rng = get_range(start, today, refresh=refresh)
        still = []
        for it in pending:
            rec = rng["items"].get(it)
            if rec is None:
                still.append(it)
                continue
            out[it] = {
                "found": True, **rec,
                "range": f"{_mdy(start)} - {_mdy(today)}",
                "price_year": today.year - k,
                "downloaded": rng["downloaded"],
            }
        pending = still
    for it in pending:
        out[it] = {"found": False, "item": it,
                   "range": f"{_mdy(dt.date(today.year - years_back + 1, 1, 1))} - {_mdy(today)}",
                   "note": "No MDOT bid price found"}
    return out


def inflate(price: float, year: int, to_year: int, rate: float = 0.08, old_rate: float = 0.03,
            base: int = 2020) -> float:
    """Same inflation as the OPCC sheet: old_rate/yr up to `base`, then rate/yr up to `to_year`."""
    if year < base:
        return price * (1 + old_rate) ** (base - year) * (1 + rate) ** (to_year - base)
    return price * (1 + rate) ** (to_year - year)


def widen_single_project(prices: dict, today: dt.date | None = None, years_back: int = MAX_YEARS_BACK,
                         refresh: bool = False, log=lambda m: None, **rates) -> dict:
    """Guardrail: an item whose search range holds only ONE bid quantity (one project) is not a reliable price.
    For those items, pull earlier years one at a time (single-year ranges) until the bids come from at least two
    different quantities, up to `years_back` years. Each year's prices are inflated to today's year on their own
    (same rates as the sheet) and then combined: low = lowest, high = highest, avg = mean of the yearly averages,
    quantity range = across all years. The result is in today's dollars (price_year = today's year, inflated=True).
    If ten years still show one project, the item is kept as found and marked single_project=True."""
    today = today or dt.date.today()
    oldest = today.year - years_back + 1
    single = [k for k, r in prices.items() if r.get("found") and r["min_qty"] == r["max_qty"]]
    if not single:
        return prices
    log(f"{len(single)} item(s) have bids from only one project; checking earlier years one at a time")
    yearly = {}
    out = dict(prices)
    for code in single:
        rec = prices[code]
        recs = {}
        y = rec["price_year"]
        while y >= oldest:
            if y not in yearly:
                end = min(dt.date(y, 12, 31), today)
                yearly[y] = get_range(dt.date(y, 1, 1), end, refresh=refresh)["items"]
            r = yearly[y].get(code)
            if r:
                recs[y] = r
                qtys = {v for x in recs.values() for v in (x["min_qty"], x["max_qty"])}
                if len(qtys) >= 2:
                    break
            y -= 1
        qtys = {v for x in recs.values() for v in (x["min_qty"], x["max_qty"])}
        if len(recs) < 2 and len(qtys) < 2:
            out[code] = {**rec, "single_project": True}
            continue
        yrs = sorted(recs)
        f = lambda v, yr: round(inflate(v, yr, today.year, **rates), 2)
        out[code] = {**rec,
                     "min_qty": min(x["min_qty"] for x in recs.values()),
                     "max_qty": max(x["max_qty"] for x in recs.values()),
                     "avg_qty": round(sum(x["avg_qty"] for x in recs.values()) / len(recs), 2),
                     "low_price": min(f(x["low_price"], yr) for yr, x in recs.items()),
                     "high_price": max(f(x["high_price"], yr) for yr, x in recs.items()),
                     "avg_price": round(sum(f(x["avg_price"], yr) for yr, x in recs.items()) / len(recs), 2),
                     "price_year": today.year, "inflated": True, "years_used": yrs,
                     "range": f"{yrs[0]}-{yrs[-1]} by year ({', '.join(str(v) for v in yrs)}), "
                              f"inflated to {today.year}",
                     "yearly": {yr: {k2: x[k2] for k2 in ("min_qty", "max_qty", "low_price", "avg_price",
                                                           "high_price")} for yr, x in recs.items()}}
    return out


def _main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("lookup")
    lk.add_argument("items", nargs="*")
    lk.add_argument("--file", help="JSON list of pay item numbers")
    lk.add_argument("--out")
    lk.add_argument("--today", help="YYYY-MM-DD (default: today)")
    lk.add_argument("--refresh", action="store_true")
    rg = sub.add_parser("range")
    rg.add_argument("start")
    rg.add_argument("end")
    rg.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.cmd == "range":
        p = lambda s: dt.datetime.strptime(s, "%m/%d/%Y").date()
        data = download_range(p(a.start), p(a.end))
        if data is None:
            sys.exit("MDOT has no bids in that range")
        Path(a.out).write_bytes(data)
        print(f"Saved {a.out}")
        return

    items = list(a.items)
    if a.file:
        items += json.loads(Path(a.file).read_text())
    today = dt.date.fromisoformat(a.today) if a.today else None
    res = lookup(items, today=today, refresh=a.refresh, log=lambda m: print(m, file=sys.stderr))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2, default=str))
        print(f"Saved {a.out}", file=sys.stderr)
    else:
        for it, r in res.items():
            if r["found"]:
                print(f"{it:16} {r['unit']:12} {r['range']:24} yr {r['price_year']}  "
                      f"qty {r['min_qty']}-{r['max_qty']}  low {r['low_price']}  avg {r['avg_price']}  "
                      f"high {r['high_price']}")
            else:
                print(f"{it:16} {r['note']}")


if __name__ == "__main__":
    _main()
