#!/usr/bin/env python3
"""Build an MDOT Opinion of Probable Construction Cost workbook.

Input: the JSON from read_sq.py. Prices come from mdot_bid_prices.lookup().
Layout follows the firm's OPCC sheet (one tab per bid section):
  C PAY ITEM NO. | D PAY ITEM | E UNIT | F QTY | G UNIT PRICE | H TOTAL | I % OF ITEMS | J ALT. COUNTED |
  (K:L gap) | M REMARKS | O YEAR | P INITIAL COST | Q COST IN 2020 | R ESTIMATE YR (inflation, T4:U6 rates)
  W..AF  MDOT bid data used (range, price year, quantities, low/avg/high, suggested, method)

Usage:
  build_opcc.py sq.json --project "Lakeland Drive Pedestrian Bridge" --fa "STBG-9999-05(413)" \
      --by GREENWOOD --out "123456-301000-2026-10-29-OPCC.xlsx" [--today 2026-10-29] [--refresh]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).parent))
import mdot_bid_prices as mbp  # noqa: E402

PERCENT_ITEMS = {  # pay item -> label used in REMARKS
    "201-A001": "Clearing and Grubbing (Lump Sum)",
    "907-618-A001": "Maintenance of Traffic",
    "620-A001": "Mobilization",
    "699-A001": "Roadway Construction Stakes",
}
DEFAULT_PCT = 0.05


def is_percent_item(item: dict) -> bool:
    """MOT, Mobilization, Construction Stakes, and Clearing & Grubbing ONLY when paid by Lump Sum (201-A001).
    Clearing & Grubbing by the Acre (201-B001) is priced from MDOT bids like any other item."""
    if item["item"] in PERCENT_ITEMS:
        return True
    unit = item.get("unit", "").upper().replace(".", "")
    return "clearing and grubbing" in item.get("description", "").lower() and unit in ("LS", "LUMP SUM")
WIDE_RANGE = 10  # flag when high price > 10x low price
UNITS = {
    "ACRE": "Acre", "AC": "Acre", "SY": "Square Yard", "LF": "Linear Feet", "CY": "Cubic Yard", "TON": "Ton",
    "EA": "Each", "LS": "Lump Sum", "GAL": "Gallon", "LBS": "Pounds", "LB": "Pounds", "SF": "Square Feet",
    "HRS": "Hours", "HR": "Hours", "STA": "Station", "MI": "Mile", "MILE": "Mile", "KGAL": "Thousand Gallon",
    "MGAL": "Thousand Gallon",
    "K": "Thousand", "M": "Thousand", "EA (K)": "Thousand", "CF": "Cubic Feet", "MBF": "Thousand Board Feet",
    "MFBM": "Thousand Board Feet",
}

# ------------------------------------------------------------------ pricing
def suggest(item: dict, rec: dict | None) -> dict:
    """Return {'price', 'year', 'method', 'flag'} for one SQ line."""
    code, qty = item["item"], item["qty"]
    if is_percent_item(item):
        return {"price": None, "year": None, "method": "% of total items cost", "flag": None, "percent": True}
    if not rec or not rec.get("found"):
        return {"price": None, "year": None, "method": "Flagged", "flag": "No MDOT bid price found"}
    sq_unit = UNITS.get(item["unit"].upper().replace(".", ""), item["unit"])
    if sq_unit.lower() != str(rec["unit"]).lower():
        return {"price": None, "year": None, "method": "Flagged",
                "flag": f"Unit differs: SQ {item['unit']} vs MDOT {rec['unit']}"}
    lo, hi, avg = rec["low_price"], rec["high_price"], rec["avg_price"]
    qmin, qmax = rec["min_qty"], rec["max_qty"]
    year = rec["price_year"]
    if "-PP" in code.upper():
        return {"price": None, "year": None, "method": "Flagged", "flag": "Per Plans item - use judgment"}
    if qmin == qmax and lo == hi:
        return {"price": round(avg, 2), "year": year, "method": "Only one bid price",
                "flag": None, "note": "CHECK: only one MDOT bid price"}
    if lo and hi > WIDE_RANGE * lo:
        # Penny / unbalanced bids make the low end meaningless, so use the average instead of the qty line.
        return {"price": round(avg, 2), "year": year, "method": f"Wide range ({hi / lo:,.0f}x) -> avg",
                "flag": None, "note": f"CHECK: wide MDOT price range (${lo:,.2f} - ${hi:,.2f}), used avg"}
    if qty is None:
        return {"price": None, "year": None, "method": "Flagged", "flag": "No quantity on SQ"}
    if qmin == qmax:
        return {"price": round(avg, 2), "year": year, "method": "One bid quantity -> avg", "flag": None}
    if qty <= qmin:
        return {"price": round(hi, 2), "year": year, "method": "At/below min qty -> high", "flag": None}
    if qty >= qmax:
        return {"price": round(lo, 2), "year": year, "method": "At/above max qty -> low", "flag": None}
    t = (math.log(qty) - math.log(qmin)) / (math.log(qmax) - math.log(qmin))
    return {"price": round(hi + t * (lo - hi), 2), "year": year, "method": "Qty line (log)", "flag": None}


def mark_alternates(items: list[dict], prices: dict) -> list[dict]:
    """SQ "OR" groups (alt_of) stay as separate lines, each with its own MDOT price, like the firm's OPCC sheet:
    every alternate is listed, only ONE is counted in the totals (the contractor bids one). The one counted at
    first is the lowest suggested MDOT price (or the first listed if none has a price); a YES/NO dropdown on each
    alternate row lets the engineer switch it. Repeated pay items WITHOUT an "OR" row (e.g. roadway and bridge
    Structure Excavation) are not alternates: they stay separate and are all counted."""
    grouped = []
    for it in items:
        if it.get("alt_of") and grouped and grouped[-1][0]["item"] == it["alt_of"]:
            grouped[-1].append(it)
        else:
            grouped.append([it])
    result = []
    for g in grouped:
        if len(g) == 1:
            result.append(dict(g[0]))
            continue
        priced = [(suggest(x, prices.get(x["item"]))["price"], i, x) for i, x in enumerate(g)]
        withp = [p for p in priced if p[0] is not None]
        pick = (min(withp)[1] if withp else 0)
        codes = ", ".join(x["item"] for x in g)
        for i, x in enumerate(g):
            y = dict(x)
            y["alt_group"] = codes
            y["alt_counted"] = i == pick
            y["alt_note"] = (f"ALTERNATE ({codes}; contractor bids one): only the row marked YES counts in the "
                             f"total" + ("; YES set on the lowest MDOT price" if withp and i == pick else ""))
            result.append(y)
    return result


def check_lines(sec: dict, lines: list[dict]):
    """Safety check: every SQ line must reach the OPCC (alternates included), with the same quantity per pay item,
    and each "OR" group must have exactly one alternate counted. Nothing can silently drop out or double count."""
    from collections import Counter
    want, got = Counter(), Counter()
    for it in sec["items"]:
        want[it["item"]] += it["qty"] or 0
    for it in lines:
        got[it["item"]] += it["qty"] or 0
    groups = Counter(it["alt_group"] for it in lines if it.get("alt_group") and it.get("alt_counted"))
    allg = {it["alt_group"] for it in lines if it.get("alt_group")}
    bad_groups = [g for g in allg if groups.get(g, 0) != 1]
    if len(lines) != len(sec["items"]) or want != got or bad_groups:
        missing = {k: (want[k], got.get(k, 0)) for k in set(want) | set(got) if want[k] != got.get(k, 0)}
        raise RuntimeError(f"{sec['name']}: OPCC lines don't match the SQ (SQ {len(sec['items'])} lines, "
                           f"OPCC {len(lines)} lines; qty SQ vs OPCC: {missing}; alternate groups without exactly "
                           f"one counted: {bad_groups}). Not saved.")


# ------------------------------------------------------------------ workbook
THIN = Side(style="thin", color="808080")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BOLD = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="D9D9D9")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")   # cells the engineer is expected to fill
PRIOR_FILL = PatternFill("solid", fgColor="E2EFDA")   # price carried over from the original OPCC
DATA_FILL = PatternFill("solid", fgColor="EDF2F8")    # MDOT data block
MONEY = '"$"#,##0.00'
MONEY0 = '"$"#,##0'
QTYF = '#,##0.##'
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def read_prior(path: str) -> dict:
    """Unit prices from an earlier OPCC: {sheet name upper: [(item, description, unit price)]}."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        hdr = None
        for row in ws.iter_rows(min_row=1, max_row=15):
            for c in row:
                if str(c.value or "").strip().upper() == "PAY ITEM NO.":
                    hdr = (c.row, c.column)
                    break
            if hdr:
                break
        if not hdr:
            continue
        hrow = [str(ws.cell(hdr[0], c).value or "").strip().upper() for c in range(1, ws.max_column + 1)]
        c_item = hdr[1]
        c_desc = hrow.index("PAY ITEM") + 1 if "PAY ITEM" in hrow else c_item + 1
        c_price = hrow.index("UNIT PRICE") + 1 if "UNIT PRICE" in hrow else None
        if not c_price:
            continue
        rows = []
        for r in range(hdr[0] + 1, ws.max_row + 1):
            item = str(ws.cell(r, c_item).value or "").strip().upper()
            price = ws.cell(r, c_price).value
            if item and isinstance(price, (int, float)):
                rows.append((item, str(ws.cell(r, c_desc).value or "").strip(), float(price)))
        out[ws.title.strip().upper()] = rows
    return out


def _norm(t: str) -> str:
    return " ".join(str(t).lower().replace("concrete curb", "curb").split())


def prior_price(prior: dict, sheet: str, item: str, desc: str):
    """Best match: same sheet + item + description, then same sheet + item, then any sheet + item + description."""
    if not prior:
        return None
    same = prior.get(sheet.upper(), [])
    for pool in (same, [x for v in prior.values() for x in v]):
        hits = [p for i, d, p in pool if i == item and _norm(d) == _norm(desc)]
        if hits:
            return hits[0]
        if pool is same:
            hits = [p for i, d, p in pool if i == item]
            if len(set(hits)) == 1:
                return hits[0]
    return None


def _q(text: str) -> str:
    """Text as an Excel string literal."""
    return '"' + str(text).replace('"', '""') + '"'


def write_sheet(wb, sec, prices, meta, pct_ref):
    """Layout (one tab per bid section):
      C PAY ITEM NO. | D PAY ITEM | E UNIT | F QTY | G UNIT PRICE | H TOTAL | I % OF ITEMS | J ALT. COUNTED |
      K:L blank gap | M REMARKS | N hidden helper | O YEAR | P INITIAL COST | Q COST IN 2020 | R ESTIMATE YR |
      T:U inflation rates | W..AF MDOT bid data used.
    Every pay item row has the same formulas: a % picked in column I makes that line I x TOTAL ITEMS COST and
    overrides its unit price; blank I uses the unit price (YEAR / INITIAL COST, inflated). Alternates have YES/NO
    in J; only YES rows count. TOTAL ITEMS COST (G4) = the hidden helper N, which never reads G or H, so there is no
    circular reference whichever lines are percentages."""
    ws = wb.create_sheet(sec["name"].title()[:31])
    est_year = meta["today"].year
    ws["D1"] = "OPINION OF PROBABLE CONSTRUCTION COST"; ws["D1"].font = Font(bold=True, size=14)
    ws["D2"] = meta["project"].upper(); ws["E2"] = "DATE:"; ws["G2"] = meta["today"]
    ws["G2"].number_format = "m/d/yyyy"
    ws["D3"] = f"{meta['county']} COUNTY" if meta["county"] else ""
    ws["E3"] = "UPDATED BY:"; ws["G3"] = meta["by"]
    ws["O3"] = "ENTER YEAR & COST"
    ws["D4"] = f"{meta['job_slash']}  {meta['fa']}".strip()
    ws["E4"] = "TOTAL ITEMS COST:"
    ws["T4"] = "UNIT PRICE INFLATION"
    heads = {"C": "PAY ITEM NO.", "D": "PAY ITEM", "E": "UNIT", "F": "QTY", "G": "UNIT PRICE", "H": "TOTAL",
             "I": "% OF ITEMS", "J": "ALT. COUNTED", "M": "REMARKS", "O": "INFLATION", "Q": "COST IN YR",
             "R": "ESTIMATE YR", "T": "2020 - 2025 @", "U": 0.08}
    for c, v in heads.items():
        ws[f"{c}5"] = v
    ws["O6"], ws["P6"], ws["Q6"], ws["R6"] = "YEAR", "INITIAL COST", 2020, est_year
    ws["T6"], ws["U6"] = "BEFORE 2020 @", 0.03
    ws["U5"].number_format = ws["U6"].number_format = "0%"
    ws["W3"] = (f"MDOT ITEM BID PRICES - aashtoreports.mdot.ms.gov BidPrices report, downloaded "
                f"{meta['downloaded']}. Exact values as published by MDOT.")
    ws["W3"].font = Font(italic=True, size=9)
    mdot_heads = ["SEARCH RANGE", "PRICE YEAR", "MIN QTY", "MAX QTY", "AVG QTY", "LOW PRICE", "AVG PRICE",
                  "HIGH PRICE", "SUGGESTED (BEFORE INFLATION)", "METHOD"]
    ws["W4"] = "MDOT BID DATA USED"; ws["W4"].font = BOLD
    for i, h in enumerate(mdot_heads):
        ws.cell(5, 23 + i, h)
    boxed = list(range(3, 11)) + [13] + list(range(15, 19))
    for row in (5, 6):
        for col in boxed + list(range(23, 33)):
            c = ws.cell(row, col); c.font = BOLD; c.alignment = CENTER; c.fill = HEAD_FILL; c.border = BOX
    ws.merge_cells("O5:P5")
    for rng in ("E2:F2", "E3:F3", "E4:F4"):
        ws.merge_cells(rng); ws[rng.split(":")[0]].alignment = Alignment(horizontal="right")
    for rng in ("O3:R3", "T4:U4", "W4:AF4"):
        ws.merge_cells(rng); ws[rng.split(":")[0]].alignment = Alignment(horizontal="center")
    ws.merge_cells("W3:AF3"); ws["W3"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[3].height = 26
    ws.row_dimensions[5].height = 45

    first = r = 7
    alt_rows, flagged, checks, from_prior = [], [], [], []
    lines = mark_alternates(sec["items"], prices)
    check_lines(sec, lines)
    for it in lines:
        code = it["item"]
        rec = prices.get(code)
        s = suggest(it, rec)
        ws[f"C{r}"], ws[f"D{r}"], ws[f"E{r}"], ws[f"F{r}"] = code, it["description"], it["unit"], it["qty"]
        orig = None
        if s.get("percent"):
            ws[f"I{r}"] = DEFAULT_PCT
        elif s["price"] is not None:
            ws[f"O{r}"], ws[f"P{r}"] = s["year"], s["price"]
        else:
            if s["flag"] == "No MDOT bid price found":
                orig = prior_price(meta.get("prior"), sec["name"], code, it["description"])
            if orig is not None:  # original OPCC price is already in estimate-year dollars: no extra inflation
                ws[f"O{r}"], ws[f"P{r}"] = est_year, round(orig, 2)
                ws[f"O{r}"].fill = ws[f"P{r}"].fill = PRIOR_FILL
                from_prior.append((code, it["description"], orig))
            else:
                ws[f"O{r}"].fill = ws[f"P{r}"].fill = INPUT_FILL
                flagged.append((code, it["description"], s["flag"]))
        ws[f"I{r}"].number_format = "0.0%"; ws[f"I{r}"].fill = INPUT_FILL
        ws[f"Q{r}"] = f'=IF(AND(O{r}<>"",O{r}<$Q$6),P{r}*(1+$U$6)^($Q$6-O{r}),"")'
        ws[f"R{r}"] = (f'=IF(OR(O{r}="",P{r}=""),"",ROUND(IF(O{r}<$Q$6,Q{r}*(1+$U$5)^($R$6-$Q$6),'
                       f'P{r}*(1+$U$5)^($R$6-O{r})),2))')
        ws[f"H{r}"] = f'=IF(I{r}<>"",ROUNDUP(I{r}*$G$4,0),IF(R{r}="","",F{r}*R{r}))'
        ws[f"G{r}"] = f'=IF(I{r}<>"",IF(F{r}>0,H{r}/F{r},H{r}),IF(R{r}="","",R{r}))'
        ws[f"N{r}"] = f'=IF(OR(I{r}<>"",J{r}="NO",R{r}=""),0,F{r}*R{r})'
        if it.get("alt_group"):
            ws[f"J{r}"] = "YES" if it["alt_counted"] else "NO"
            ws[f"J{r}"].fill = INPUT_FILL
            ws[f"J{r}"].alignment = Alignment(horizontal="center")
            alt_rows.append(r)
        notes = []
        if s["flag"] and not s.get("percent"):
            notes.append(s["flag"])
        if orig is not None:
            notes.append(f"used original OPCC price ${orig:,.2f}")
        if it.get("alt_note"):
            notes.append(it["alt_note"])
        if s.get("note"):
            notes.append(s["note"])
            checks.append((code, it["description"], s["note"]))
        if rec and rec.get("found") and rec.get("description") and \
                rec["description"].strip().lower() != it["description"].strip().lower():
            notes.append(f"MDOT: {rec['description']}")
        note = "; ".join(notes)
        ws[f"M{r}"] = (f'=IF(I{r}<>"",TEXT(I{r},"0.0%")&" OF TOTAL ITEMS COST"&{_q("; " if note else "")},"")'
                       f'&{_q(note)}')
        # MDOT data block (exact values)
        if rec and rec.get("found"):
            vals = [rec["range"], rec["price_year"], rec["min_qty"], rec["max_qty"], rec["avg_qty"],
                    rec["low_price"], rec["avg_price"], rec["high_price"], s["price"], s["method"]]
        else:
            vals = [rec["range"] if rec else None, None, None, None, None, None, None, None, None,
                    s["method"] if s.get("percent") else "No MDOT bid price found"]
            if orig is not None:
                vals[-1] = "No MDOT bid price -> original OPCC price"
        if s.get("percent") and rec and rec.get("found"):
            vals[-1] = "% of total items cost (MDOT data for reference only)"
        for i, v in enumerate(vals):
            c = ws.cell(r, 23 + i, v); c.fill = DATA_FILL; c.border = BOX
            if 2 <= i <= 4:
                c.number_format = QTYF
            elif 5 <= i <= 8:
                c.number_format = MONEY
        for col in boxed:
            ws.cell(r, col).border = BOX
        r += 1
    last = r - 1

    # totals
    ws["G4"] = f"=SUM(N{first}:N{last})"
    ws.column_dimensions["N"].hidden = True
    ws["G4"].number_format = MONEY0; ws["G4"].font = BOLD
    sub, cont, tot = r + 1, r + 3, r + 5
    # SUB-TOTAL = counted unit-price items (G4) + every line set to a % (alternates marked NO left out)
    ws[f"C{sub}"] = "SUB-TOTAL"
    ws[f"H{sub}"] = f'=G4+SUMIFS(H{first}:H{last},I{first}:I{last},">0",J{first}:J{last},"<>NO")'
    ws[f"D{cont}"] = "Contingencies"; ws[f"E{cont}"] = "LS"; ws[f"F{cont}"] = 1
    ws[f"I{cont}"] = DEFAULT_PCT; ws[f"I{cont}"].number_format = "0.0%"; ws[f"I{cont}"].fill = INPUT_FILL
    ws[f"H{cont}"] = f"=ROUNDUP(I{cont}*H{sub},0)"; ws[f"G{cont}"] = f"=H{cont}"
    ws[f"M{cont}"] = f'=TEXT(I{cont},"0.0%")&" OF SUB-TOTAL"'
    ws[f"C{tot}"] = "TOTAL"; ws[f"H{tot}"] = f"=H{sub}+H{cont}"
    for rr in (sub, cont, tot):
        ws[f"C{rr}"].font = ws[f"H{rr}"].font = BOLD
        ws[f"H{rr}"].number_format = MONEY0
        ws[f"G{rr}"].number_format = MONEY0

    # % dropdown on EVERY pay item row (blank = use the unit price) and on Contingencies
    dv = DataValidation(type="list", formula1=pct_ref, allow_blank=True,
                        prompt="Pick a % to price this line as % of TOTAL ITEMS COST (overrides the unit price). "
                               "Delete it to go back to the unit price. You can also type any %.",
                        promptTitle="% of total items cost", showInputMessage=True, showErrorMessage=False)
    ws.add_data_validation(dv)
    dv.add(f"I{first}:I{last}")
    dv.add(f"I{cont}")
    from openpyxl.formatting.rule import FormulaRule
    if alt_rows:
        dva = DataValidation(type="list", formula1='"YES,NO"', allow_blank=False,
                             prompt="Alternates: the contractor bids one. Mark exactly one row in this group YES.",
                             promptTitle="Count this alternate?", showInputMessage=True, showErrorMessage=True)
        ws.add_data_validation(dva)
        for rr in alt_rows:
            dva.add(f"J{rr}")
            ws.conditional_formatting.add(f"C{rr}:H{rr}", FormulaRule(formula=[f'$J${rr}="NO"'],
                                          font=Font(color="808080", italic=True)))

    for rr in range(first, last + 1):
        ws[f"F{rr}"].number_format = QTYF
        for col in "GHPQR":
            ws[f"{col}{rr}"].number_format = MONEY
        ws[f"E{rr}"].alignment = Alignment(horizontal="center")
        ws[f"I{rr}"].alignment = Alignment(horizontal="center")
    # K:L blank gap; N hidden helper
    widths = {"A": 2, "B": 2, "C": 15, "D": 48, "E": 7, "F": 10, "G": 16, "H": 17, "I": 10, "J": 10, "K": 9,
              "L": 9, "M": 40, "N": 2, "O": 8, "P": 16, "Q": 16, "R": 16, "S": 2, "T": 15, "U": 7, "V": 3, "W": 23,
              "X": 8, "Y": 10, "Z": 10, "AA": 10, "AB": 16, "AC": 16, "AD": 16, "AE": 16, "AF": 34}
    for k, v in widths.items():
        ws.column_dimensions[k].width = v
    ws.freeze_panes = "E7"
    ws.sheet_view.zoomScale = 85
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = f"C1:M{tot}"
    return flagged, checks, from_prior


def build(sq: dict, meta: dict, out: str, refresh=False, log=print):
    codes = [it["item"] for s in sq["sections"] for it in s["items"]]
    prices = mbp.lookup(codes, today=meta["today"], refresh=refresh, log=log)
    downloaded = sorted({p["downloaded"] for p in prices.values() if p.get("found")})
    meta["downloaded"] = ", ".join(downloaded) or meta["today"].isoformat()
    wb = Workbook()
    lists = wb.active; lists.title = "Lists"
    for i, v in enumerate([0.005] + [k / 100 for k in range(1, 21)], start=1):
        lists.cell(i, 1, v).number_format = "0.0%"
    lists.sheet_state = "hidden"
    report = {}
    for sec in sq["sections"]:
        report[sec["name"]] = write_sheet(wb, sec, prices, meta, "Lists!$A$1:$A$21")
    wb.move_sheet("Lists", offset=len(wb.sheetnames))
    wb.active = 0
    wb.save(out)
    autofit(out)
    return prices, report


def _display(v, fmt: str) -> str:
    """Roughly what Excel shows for a value with this number format."""
    if v is None or v == "":
        return ""
    if isinstance(v, (dt.date, dt.datetime)):
        return f"{v.month}/{v.day}/{v.year}"
    if isinstance(v, bool):
        return str(v).upper()
    if isinstance(v, (int, float)):
        if "%" in fmt:
            return f"{v * 100:.0f}%"
        if "$" in fmt:
            return f"${v:,.2f}" if ".00" in fmt else f"${v:,.0f}"
        if "#,##0" in fmt:
            return f"{v:,.2f}".rstrip("0").rstrip(".")
        return f"{v:,}" if isinstance(v, int) else f"{v:,.2f}"
    return str(v)


def autofit(path: str, spare: int = 2, max_width: int = 110):
    """Size every column to its widest shown value (formulas are calculated first), plus a little spare room.

    Excel won't widen columns by itself without a macro, so this runs every time the workbook is built.
    Formula results come from pycel when it is installed; otherwise formula cells get a safe default width."""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    xl = None
    try:
        import ast
        if not hasattr(ast, "Str"):  # pycel on Python 3.12+
            ast.Str = lambda s=None, **k: ast.Constant(s)
        from pycel import ExcelCompiler
        xl = ExcelCompiler(filename=path)
    except Exception:
        xl = None
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            continue
        merged = {c for rng in ws.merged_cells.ranges for row in ws[rng.coord] for c in [x.coordinate for x in row]}
        widths = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is None or c.coordinate in merged:
                    continue
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    if xl is None:
                        v = 1234567.89 if "$" in c.number_format else "x" * 12
                    else:
                        try:
                            v = xl.evaluate(f"'{ws.title}'!{c.coordinate}")
                        except Exception:
                            v = "x" * 12
                text = _display(v, c.number_format)
                if c.alignment is not None and c.alignment.wrap_text:
                    text = max(text.split(), key=len, default="")  # wrapped: longest word must fit
                size = (c.font.sz or 11) if c.font is not None else 11
                n = len(text) * (1.15 if c.font is not None and c.font.b else 1.0) * size / 11
                widths[c.column_letter] = max(widths.get(c.column_letter, 0), n)
        for col, n in widths.items():
            d = ws.column_dimensions[col]
            if d.hidden:
                continue
            d.width = min(max_width, max(n + spare, d.width or 0, 6))
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sq_json")
    ap.add_argument("--project", required=True)
    ap.add_argument("--fa", default="", help="federal-aid number, e.g. STBG-9999-05(413)")
    ap.add_argument("--by", default="")
    ap.add_argument("--county")
    ap.add_argument("--out", required=True)
    ap.add_argument("--today")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--prior", help="earlier OPCC .xlsx: its unit price is used where MDOT has no price")
    a = ap.parse_args()
    sq = json.loads(Path(a.sq_json).read_text())
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    job = sq.get("job") or ""
    meta = {"project": a.project, "fa": a.fa, "by": a.by.upper(), "county": (a.county or sq.get("county") or "").upper(),
            "today": today, "job_slash": job.replace("-", "/")}
    meta["prior"] = read_prior(a.prior) if a.prior else None
    prices, report = build(sq, meta, a.out, refresh=a.refresh, log=lambda m: print(m, file=sys.stderr))
    print(f"Saved {a.out}")
    for sec, (flagged, checks, from_prior) in report.items():
        for code, desc, p in from_prior:
            print(f"PRIOR {sec:14} {code:15} {desc[:45]:45} original OPCC ${p:,.2f}")
        for code, desc, why in flagged:
            print(f"BLANK {sec:14} {code:15} {desc[:45]:45} {why}")
        for code, desc, why in checks:
            print(f"CHECK {sec:14} {code:15} {desc[:45]:45} {why}")


if __name__ == "__main__":
    main()
