#!/usr/bin/env python3
"""Read an MDOT Summary of Quantities (PDF plan sheets or Excel) into JSON.

Output:
{
  "source": "...", "county": "HINDS", "job": "123456-301000",
  "qty_column": "Final" | "Prelim",
  "sections": [ {"name": "BASE BID", "items": [
        {"item": "201-B001", "description": "Clearing and Grubbing", "unit": "ACRE",
         "qty": 2, "prelim": 2, "final": null, "sheet": 1}, ...]}, ... ]
}

Section rows: a row with no pay item number and text in the PAY ITEM column ("BASE BID",
"A2", "ADD OPTION 1", ...). "A<n>" is written out as "ADD OPTION <n>".
Quantity: Final when the Final column has any value in the whole SQ, otherwise Prelim.
Several project/county column groups are added together (and listed in "projects").

Usage: read_sq.py <SQ.pdf|SQ.xlsx> [more SQ files...] [--out sq.json]
An item whose description ends in "Base Bid" / "Add Option n" goes on that section's sheet.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ITEM_RE = re.compile(r"^(?:\d{3,4}-)?\d{3,4}-[A-Z]{1,3}\d{3,5}$|^\d{3}-[A-Z]+\d+$")
NUM_RE = re.compile(r"^-?[\d,]+(\.\d+)?$")


def _num(s):
    s = str(s).replace(",", "").strip()
    try:
        v = float(s)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def _section_name(text: str) -> str:
    t = " ".join(text.split()).upper()
    m = re.fullmatch(r"A(?:O)?\s*-?\s*(\d+)", t)
    if m:
        return f"ADD OPTION {m.group(1)}"
    m = re.fullmatch(r"ADD(?:ITIVE)?\s+(?:OPTION|ALT(?:ERNATE)?)\s*#?\s*(\d+)", t)
    if m:
        return f"ADD OPTION {m.group(1)}"
    return t


# ---------------------------------------------------------------- PDF
def _rules(page):
    """Vertical (x, y0, y1) and horizontal (y, x0, x1) rules from lines and hairline rectangles."""
    v, h = [], []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                p1, p2 = it[1], it[2]
                if abs(p1.x - p2.x) < 0.5 and abs(p1.y - p2.y) > 8:
                    v.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))
                elif abs(p1.y - p2.y) < 0.5 and abs(p1.x - p2.x) > 8:
                    h.append((p1.y, min(p1.x, p2.x), max(p1.x, p2.x)))
            elif it[0] == "re":
                r = it[1]
                if r.width < 2 and r.height > 8:
                    v.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif r.height < 2 and r.width > 8:
                    h.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
                elif d.get("color") is not None and r.width > 8 and r.height > 8:  # stroked box = 4 rules
                    v += [(r.x0, r.y0, r.y1), (r.x1, r.y0, r.y1)]
                    h += [(r.y0, r.x0, r.x1), (r.y1, r.x0, r.x1)]
    return v, h


def read_pdf(path: str) -> dict:
    import pymupdf

    doc = pymupdf.open(path)
    rows_out, projects, county, job = [], [], None, None
    for pno, page in enumerate(doc):
        words = page.get_text("words")
        if not any(w[4].upper() == "QUANTITIES" for w in words):
            continue
        # header words
        def find(*texts):
            return [w for w in words if w[4].lower() in [t.lower() for t in texts]]
        unit_h = find("UNIT")
        prelim_h, final_h = find("Prelim", "Preliminary", "Prelim."), find("Final")
        if not unit_h or not (prelim_h or final_h):
            raise SystemExit(f"Page {pno + 1}: could not find UNIT / Prelim / Final headers")
        header_bottom = max(w[3] for w in prelim_h + final_h)
        # table rules, drawn either as lines or as thin rectangles
        vsegs, hsegs = _rules(page)
        vlines = sorted({round(x) for x, y0, y1 in vsegs})
        def cell(x_center):
            left = max([v for v in vlines if v <= x_center], default=None)
            right = min([v for v in vlines if v > x_center], default=None)
            return left, right

        unit_cell = cell((unit_h[0][0] + unit_h[0][2]) / 2)
        groups = []  # (prelim_cell, final_cell) per project column group
        for p in prelim_h:
            pc = cell((p[0] + p[2]) / 2)
            f = min((w for w in final_h if w[0] > p[0]), key=lambda w: w[0] - p[0], default=None)
            fc = cell((f[0] + f[2]) / 2) if f else None
            groups.append((pc, fc))
        table_right = max((g[1] or g[0])[1] for g in groups)
        # project labels above Prelim/Final, e.g. "HINDS : 123456-301000"
        for w in words:
            m = re.fullmatch(r"(\d{6}-\d{6})", w[4])
            if m and w[3] <= header_bottom:
                line = " ".join(x[4] for x in words if abs(x[1] - w[1]) < 3 and x[0] < w[2] and x[0] > w[0] - 200)
                job = job or m.group(1)
                cm = re.match(r"([A-Z][A-Z ]+?)\s*:", line)
                county = county or (cm.group(1).strip() if cm else None)
                if line not in projects:
                    projects.append(line)

        # bottom of the table = lowest rule reaching the table's right edge (rules may be drawn per cell)
        hlines = [y for y, x0, x1 in hsegs if x1 >= table_right - 2 and x0 < table_right - 20 and x1 < table_right + 20]
        table_bottom = max(hlines) if hlines else page.rect.y1
        body = [w for w in words if header_bottom + 1 < w[1] < table_bottom + 1 and w[0] < table_right]
        lines = {}
        for w in body:
            key = round((w[1] + w[3]) / 2 / 3)  # 3-pt row bands
            lines.setdefault(key, []).append(w)
        for key in sorted(lines):
            ws = sorted(lines[key], key=lambda w: w[0])
            item = next((w[4] for w in ws if w[0] < unit_cell[0] - 300 and ITEM_RE.match(w[4])), None)
            desc_words = [w for w in ws if w[4] != item and w[2] <= unit_cell[0] + 1]
            unit = " ".join(w[4] for w in ws if unit_cell[0] <= (w[0] + w[2]) / 2 < unit_cell[1])
            qtys = []
            for pc, fc in groups:
                def val(c):
                    if not c:
                        return None
                    t = "".join(w[4] for w in ws if c[0] <= (w[0] + w[2]) / 2 < c[1])
                    return _num(t) if t and NUM_RE.match(t) else None
                qtys.append((val(pc), val(fc)))
            desc = " ".join(w[4] for w in desc_words)
            rows_out.append({"item": item, "description": desc, "unit": unit, "qtys": qtys, "sheet": pno + 1})
    return _assemble(path, rows_out, county, job, projects)


# ---------------------------------------------------------------- Excel
def read_xlsx(path: str) -> dict:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    rows_out, county, job, projects = [], None, None, []
    for si, ws in enumerate(wb.worksheets):
        if ws.sheet_state != "visible":
            continue
        grid = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        hdr = next((i for i, r in enumerate(grid) if any(str(c or "").strip().upper() == "PAY ITEM NO." for c in r)), None)
        if hdr is None:
            continue
        flat = [str(c or "").strip() for r in grid[hdr:hdr + 3] for c in r]
        width = max(len(r) for r in grid)
        def col_of(label, rows=range(hdr, min(hdr + 3, len(grid)))):
            return [j for i in rows for j, c in enumerate(grid[i]) if str(c or "").strip().lower() == label.lower()]
        c_item = col_of("PAY ITEM NO.")[0]
        c_desc = col_of("PAY ITEM")[0]
        c_unit = col_of("UNIT")[0]
        prel, fin = col_of("Prelim"), col_of("Final")
        groups = [(p, min((f for f in fin if f > p), default=None)) for p in prel] or [(None, f) for f in fin]
        for i in range(max(0, hdr - 2), hdr + 2):
            for c in grid[i]:
                m = re.search(r"([A-Z][A-Z ]+?)\s*:\s*(\d{6}-\d{6})", str(c or ""))
                if m:
                    county, job = county or m.group(1).strip(), job or m.group(2)
                    projects.append(str(c).strip())
        start = hdr + 1 + (1 if prel or fin else 0)
        for r in grid[start:]:
            r = list(r) + [None] * (width - len(r))
            item = str(r[c_item] or "").strip()
            qtys = [(_num(r[p]) if p is not None and r[p] not in (None, "") else None,
                     _num(r[f]) if f is not None and r[f] not in (None, "") else None) for p, f in groups]
            rows_out.append({"item": item if ITEM_RE.match(item) else None,
                             "description": str(r[c_desc] or "").strip(), "unit": str(r[c_unit] or "").strip(),
                             "qtys": qtys, "sheet": si + 1})
    return _assemble(path, rows_out, county, job, projects)


# ---------------------------------------------------------------- shared
def _assemble(path, rows, county, job, projects) -> dict:
    use_final = any(f is not None for r in rows for _, f in r["qtys"])
    sections, cur, warnings = [], None, []
    for r in rows:
        if not r["item"]:
            name = r["description"].strip()
            if name and not r["unit"] and not any(p or f for p, f in r["qtys"]):
                cur = {"name": _section_name(name), "items": []}
                sections.append(cur)
            continue
        if cur is None:
            cur = {"name": "BASE BID", "items": []}
            sections.append(cur)
        target = cur
        m = re.search(r"\b(Base Bid|Add(?:itive)?\s+(?:Option|Alt(?:ernate)?)\s*#?\s*\d+)\s*$", r["description"], re.I)
        if m:  # e.g. "Sunshade Add Option 3" belongs on that sheet whatever block it sits in
            target = {"name": _section_name(m.group(1)), "items": []}
            sections.append(target)
        prelim = sum(p for p, _ in r["qtys"] if p is not None) if any(p is not None for p, _ in r["qtys"]) else None
        final = sum(f for _, f in r["qtys"] if f is not None) if any(f is not None for _, f in r["qtys"]) else None
        qty = final if use_final else prelim
        if use_final and final is None and prelim is not None:
            warnings.append(f"{r['item']} ({target['name']}): Final is blank, Prelim is {prelim}")
        if qty is None:
            warnings.append(f"{r['item']} ({target['name']}): no quantity")
        target["items"].append({"item": r["item"], "description": r["description"], "unit": r["unit"].upper(),
                             "qty": qty, "prelim": prelim, "final": final, "sheet": r["sheet"]})
    # merge sections split across sheets (same name appearing again)
    merged = {}
    for s in sections:
        if s["items"]:
            merged.setdefault(s["name"], []).extend(s["items"])
    return {"source": str(path), "county": county, "job": job, "projects": projects,
            "qty_column": "Final" if use_final else "Prelim",
            "sections": [{"name": n, "items": its} for n, its in merged.items()], "warnings": warnings}


def merge(parts: list[dict]) -> dict:
    """Combine several SQs (e.g. roadway + bridge): same-named sections are joined, in file order."""
    if len(parts) == 1:
        return parts[0]
    order, secs = [], {}
    for p in parts:
        for s in p["sections"]:
            if s["name"] not in secs:
                order.append(s["name"]); secs[s["name"]] = []
            secs[s["name"]].extend(s["items"])
    qcols = {p["qty_column"] for p in parts}
    return {"source": [p["source"] for p in parts],
            "county": next((p["county"] for p in parts if p["county"]), None),
            "job": next((p["job"] for p in parts if p["job"]), None),
            "projects": [x for p in parts for x in p["projects"]],
            "qty_column": " / ".join(sorted(qcols)),
            "sections": [{"name": n, "items": secs[n]} for n in order],
            "warnings": [w for p in parts for w in p["warnings"]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sq", nargs="+", help="one or more SQ files (roadway, bridge, ...)")
    ap.add_argument("--out")
    a = ap.parse_args()
    parts = [read_xlsx(f) if f.lower().endswith((".xlsx", ".xlsm")) else read_pdf(f) for f in a.sq]
    data = merge(parts)
    txt = json.dumps(data, indent=2)
    if a.out:
        Path(a.out).write_text(txt)
    for s in data["sections"]:
        print(f"== {s['name']} ({len(s['items'])} items)", file=sys.stderr)
        for it in s["items"]:
            print(f"   {it['item']:15} {it['unit']:5} {str(it['qty']):>8}  {it['description']}", file=sys.stderr)
    for w in data["warnings"]:
        print("WARNING:", w, file=sys.stderr)
    print(f"county={data['county']} job={data['job']} qty={data['qty_column']}", file=sys.stderr)
    if not a.out:
        print(txt)


if __name__ == "__main__":
    main()
