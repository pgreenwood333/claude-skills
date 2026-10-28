#!/usr/bin/env python3
"""Plain QA/QC workbook: one simple tab per check, one row per sheet, written for the engineer fixing the set.

  build_simple_report.py <findings_reviewed.json> <index_dir> <out.xlsx>

Tabs: Summary (counts), then one tab per check that ran:
  Spelling          Sheet ID | PDF Page | Text Found | Correct To | Status | Notes
  Placeholders (XX) unfilled XX values pulled out of spelling, same columns as the other checks
  every other check Sheet ID | PDF Page | What's Wrong | Fix | Priority | Status
plus "Your Call" (flags the engineer decides) and "Rejected" (dismissed on review, kept for the record).
A flag that covers several sheets gets one row per sheet, like a punch list. Rows sort by sheet order.
build_report.py still makes the detailed workbook (evidence, locate, review notes) when someone wants it.
"""
import json, os, re, sys
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

PLACEHOLDER = re.compile(r"\bXX\b|placeholder", re.I)
TASKS = [("index", "Sheet Order"), ("spelling", "Spelling"), ("placeholder", "Placeholders (XX)"), ("notematch", "Note Match"),
         ("overlap", "Overlapping Text"), ("color", "Print Color"), ("quantity", "Quantities")]
PRIORITY = {"high": "High", "medium": "Medium", "low": "Low"}
FILL = {"High": "F4D6D2", "Medium": "FBEBCB", "Low": "E4ECF2", "Confirmed": "E3EFE0", "Your call": "FBEBCB",
        "Rejected": "ECECEC"}
HEAD = PatternFill("solid", fgColor="2F4858")
THIN = Side(style="thin", color="C9CED3")
QUOTE = re.compile(r"`([^`]+)`")


def status(f):
    return {"confirmed": "Confirmed", "rejected": "Rejected"}.get((f.get("review") or {}).get("verdict"), "Your call")


def rows_for(f, sid_by_page):
    """One (sheet_id, page) per sheet the flag covers, from its highlight locations, else its page list."""
    pages = [l["page"] for l in f.get("locate", []) if l.get("page")] or f.get("pdf_pages", [])
    out, seen = [], set()
    for p in pages:
        if p not in seen:
            seen.add(p)
            out.append((sid_by_page.get(p, ""), p))
    return out or [(", ".join(f.get("sheet_ids", [])), "")]


def short(text, n=220):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def table(wb, title, headers, rows, widths):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEAD
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = Border(bottom=THIN)
            if isinstance(c.value, str) and c.value in FILL and headers[c.column - 1] in ("Priority", "Status"):
                c.fill = PatternFill("solid", fgColor=FILL[c.value])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    data = json.load(open(sys.argv[1]))
    idx = json.load(open(os.path.join(sys.argv[2], "index.json")))
    sid_by_page = {p["pdf_page"]: p["sheet_id"] for p in idx["pages"]}
    findings = data["findings"]
    for f in findings:   # unfilled XX values are their own punch list, not misspellings
        if f["task"] == "spelling" and PLACEHOLDER.search(f.get("finding", "") + " " + f.get("evidence", "")):
            f["task"] = "placeholder"
    ran = [t for t, _ in TASKS if t in data.get("tasks", []) or (t == "placeholder" and
           any(f["task"] == "placeholder" for f in findings))] or sorted({f["task"] for f in findings})
    order = {"High": 0, "Medium": 1, "Low": 2}
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Check", "High", "Medium", "Low", "Your call", "Rejected"])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEAD
    for t, name in TASKS:
        if t not in ran:
            continue
        ft = [f for f in findings if f["task"] == t]
        kept = [f for f in ft if status(f) == "Confirmed"]
        ws.append([name] + [sum(1 for f in kept if f["severity"] == s) for s in ("high", "medium", "low")]
                  + [sum(1 for f in ft if status(f) == "Your call"), sum(1 for f in ft if status(f) == "Rejected")])
    ws.append([])
    ws.append(["Counts are flags; a flag that repeats on several sheets is one flag but one row per sheet in its tab."])
    ws.column_dimensions["A"].width = 22
    for col in "BCDEF":
        ws.column_dimensions[col].width = 11
    for t, name in TASKS:
        if t not in ran:
            continue
        ft = [f for f in findings if f["task"] == t and status(f) == "Confirmed"]
        rows = []
        for f in ft:
            pri = PRIORITY.get(f.get("severity"), "")
            quotes = QUOTE.findall(f.get("evidence", ""))
            for sid, pg in rows_for(f, sid_by_page):
                if t == "spelling":
                    rows.append([sid, pg, quotes[0] if quotes else short(f.get("evidence"), 80),
                                 short(f.get("suggested_fix"), 120), status(f), short(f.get("finding"), 160)])
                else:
                    rows.append([sid, pg, short(f.get("finding")), short(f.get("suggested_fix"), 160), pri, status(f)])
        if t == "spelling":
            rows.sort(key=lambda r: (r[1] if isinstance(r[1], int) else 9999))
            table(wb, name, ["Sheet ID", "PDF Page", "Text Found", "Correct To", "Status", "Notes"], rows,
                  [12, 9, 34, 34, 12, 60])
        else:
            rows.sort(key=lambda r: (order.get(r[4], 3), r[1] if isinstance(r[1], int) else 9999))
            table(wb, name, ["Sheet ID", "PDF Page", "What's Wrong", "Fix", "Priority", "Status"], rows,
                  [12, 9, 70, 48, 10, 12])
    for label, want in (("Your Call", "Your call"), ("Rejected", "Rejected")):
        rows = []
        for f in findings:
            if status(f) != want:
                continue
            sids = ", ".join(dict.fromkeys(s for s, _ in rows_for(f, sid_by_page)))
            rows.append([dict(TASKS).get(f["task"], f["task"]), sids, short(f.get("finding")),
                         short((f.get("review") or {}).get("note"), 200)])
        if rows:
            table(wb, label, ["Check", "Sheet ID(s)", "What Was Flagged",
                              "Why It Needs You" if want == "Your call" else "Why It Was Rejected"], rows, [16, 22, 70, 60])
    wb.save(sys.argv[3])
    print(f"wrote {sys.argv[3]}")


if __name__ == "__main__":
    main()
