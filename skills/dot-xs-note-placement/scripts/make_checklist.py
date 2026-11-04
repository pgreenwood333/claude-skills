#!/usr/bin/env python3
"""Checklist spreadsheet of every note the macro places, for the engineer to check one by one.

  make_checklist.py <work_dir>      reads notes_to_add.json + macro_settings.json, writes <job>_XS_notes_checklist.xlsx

Sorted by XS file then station. Columns: section model to open, corner (marks shared corners), note station,
section type (existing / nearest / NEW cut by hand), full note text, profile sheet, id, OK/Fix dropdown, comments.
"""
import json, sys
from collections import Counter
from pathlib import Path
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
except ImportError:
    sys.exit("STOP: openpyxl is not installed.\nFIX: pip3 install openpyxl")

if len(sys.argv) != 2:
    sys.exit("usage: make_checklist.py <work_dir>")
work = Path(sys.argv[1])
notes = json.load(open(work / "notes_to_add.json"))
settings = json.load(open(work / "macro_settings.json"))
group = settings["group_prefix"]


def sta(s):
    a, b = s.split(" ")[0].split("+")
    return int(a) * 100 + float(b)


rows = []
for n in notes:
    if n.get("status") == "SKIP":
        continue
    sec = n["new_section_sta"] if n["status"] == "CUT" else n["dgn_section"]
    rows.append((n["dgn_file"].rsplit(".dgn", 1)[0], sta(sec), sec, n))
rows.sort(key=lambda r: (r[0], r[1], r[3]["side"], r[3]["id"]))

wb = Workbook(); ws = wb.active; ws.title = "Placed notes"
ws.append(["#", "XS file", "Section model", "Corner", "Note station", "Section type", "Note text (as placed)",
           "Profile sheet", "ID", "Checked", "Comments"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="35506B")
    c.alignment = Alignment(vertical="center", wrap_text=True)
kinds = {"EXACT": "existing", "CLOSE": "existing", "NEAREST": "existing (nearest section)", "CUT": "NEW (cut by hand)"}
shared = Counter((r[0], r[2], r[3]["side"]) for r in rows); seen = Counter()
for i, (f, _, sec, n) in enumerate(rows, 1):
    key = (f, sec, n["side"]); seen[key] += 1
    corner = n["side"] + (" (2nd, beside the 1st)" if seen[key] > 1 else " (shares corner)" if shared[key] > 1 else "")
    ws.append([i, f, f"{group}{sec}", corner, n["station"], kinds.get(n["status"], n["status"]), "\n".join(n["lines"]),
               n.get("profile_sheet", ""), n["id"], "", ""])
dv = DataValidation(type="list", formula1='"OK,Fix"', allow_blank=True); ws.add_data_validation(dv)
dv.add(f"J2:J{len(rows) + 1}")
thin = Side(style="thin", color="BFBFBF")
for i, w in enumerate([5, 30, 24, 22, 18, 22, 34, 12, 9, 10, 30]):
    ws.column_dimensions[chr(65 + i)].width = w
for row in ws.iter_rows(min_row=2):
    for c in row:
        c.alignment = Alignment(vertical="top", wrap_text=True); c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    if "NEW" in str(row[5].value):
        row[5].font = Font(bold=True)
ws.freeze_panes = "C2"; ws.auto_filter.ref = f"A1:K{len(rows) + 1}"
ws.print_title_rows = "1:1"; ws.page_setup.orientation = "landscape"
ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0; ws.sheet_properties.pageSetUpPr.fitToPage = True
out = work / f"{settings['job']}_XS_notes_checklist.xlsx"
wb.save(out)
print(f"wrote {out} ({len(rows)} notes: " + ", ".join(f"{k}: {v}" for k, v in sorted(Counter(r[0] for r in rows).items())) + ")")
