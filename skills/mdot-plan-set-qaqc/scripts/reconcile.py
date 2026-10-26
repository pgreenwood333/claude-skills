#!/usr/bin/env python3
"""Quantity reconciliation arithmetic. The agent transcribes; this script does every comparison and sum.

  reconcile.py <qty_dir>          reads sqs.json, eq.json, recap.json, overrides.json (optional) from qty_dir
                                  writes qty_dir/quantities.json (Table 1, Table 2, discrepancies, findings)

Input rows (one per table row read from the plans; quantities as written, commas allowed):
  sqs.json   [{"pay_item": "203-A001", "description": "...", "unit": "CY", "qty": "262", "sheet_id": "SQ-1",
               "pdf_page": 7, "footnotes": ["3"]}]
  eq.json    [{"pay_item": "203-A001" or null, "description": "...", "unit": "CY", "qty": "261.4", "sheet_id": "EQ-2",
               "pdf_page": 11, "table": "EARTHWORK", "column": "JOB TOTALS",
               "recap_expected": true, "recap_sheets_listed": ["WK-3", "WK-3A"]}]
  recap.json [{"pay_item": ..., "description": "...", "unit": "CY", "qty": "130.7", "sheet_id": "WK-3", "pdf_page": 15,
               "table": "EARTHWORK TOTAL THIS SHEET"}]
  Optional on any row: "locate": [{"page": 15, "rect": [x0,y0,x1,y1]}] or "locate_text": "92.25" (printed text to
                  highlight on that row's page; defaults to the pay item number).
  overrides.json  {"<pay_item or description>": {"table1_status": "ESTIMATED-NOT RECONCILED", "table2_status": "...",
                   "note": "...", "cause": "...", "eq_qty": "for OR items: paired item's qty"}}
Matching: pay item number first (spaces and dashes ignored), then exact description. Multiple EQ rows for one item are
summed (e.g. one item listed in two EQ tables); recap rows are summed across all working sheets.
SQS = EQ rounded UP to the next whole number counts as MATCH (MDOT rounding).
"""
import json, math, os, re, sys
from qaqc_common import load_json, save_json

T1 = ["MATCH", "MISMATCH", "VERIFIED WITH FOOTNOTE", "ESTIMATED-NOT RECONCILED", "NOT FOUND ON SQS", "NOT FOUND ON EQ"]
T2 = ["MATCH", "MISMATCH", "N/A-NO RECAP EXPECTED", "RECAP NOT FOUND", "PARTIAL-SOME RECAP SHEETS MISSING"]


def num(v):
    if v is None or v == "":
        return None
    s = str(v).replace(",", "").replace("$", "").strip()
    m = re.match(r"^-?\d+(\.\d+)?$", s)
    return float(s) if m else None


def key_item(p):
    return re.sub(r"[\s-]", "", (p or "").upper())


def key_desc(d):
    return re.sub(r"\s+", " ", (d or "").upper()).strip()


def fmt(x):
    if x is None:
        return None
    return int(x) if abs(x - round(x)) < 1e-9 else round(x, 3)


def sec(r):
    """Bid schedule (BASE BID, ADD OPTION 1 ...). The same pay item is reconciled separately in each schedule."""
    s = re.sub(r"\s+", " ", (r.get("section") or "BASE BID").upper()).strip()
    m = re.match(r"^A(\d+)$", s)
    return f"ADD OPTION {m.group(1)}" if m else s


def rkey(r):
    return sec(r) + "|" + (key_item(r.get("pay_item")) or "D:" + key_desc(r.get("description")))


def where(rows):
    """Highlight targets for a set of rows: each row's own `locate` (list of {page, text|rect}) if the agent gave one,
    else its printed quantity text (`locate_text`) or pay item on its page."""
    out = []
    for r in rows:
        if r.get("locate"):
            out += r["locate"]
        elif r.get("pdf_page"):
            out.append(dict(page=r["pdf_page"], text=r.get("locate_text") or r.get("pay_item") or str(r.get("qty")),
                            all=bool(r.get("locate_text"))))
    return out


def group(rows):
    """Group rows by bid schedule + pay item (or description when there is no pay item)."""
    g = {}
    for r in rows:
        g.setdefault(rkey(r), []).append(r)
    return g


def main():
    d = sys.argv[1]
    sqs = load_json(os.path.join(d, "sqs.json"), [])
    eq = load_json(os.path.join(d, "eq.json"), [])
    recap = load_json(os.path.join(d, "recap.json"), [])
    ov_raw = load_json(os.path.join(d, "overrides.json"), {})
    ov = {}
    for k, v in ov_raw.items():  # keys: "203-A001" (every schedule) or "ADD OPTION 1|203-A001"
        if "|" in k:
            sc, it = k.split("|", 1)
            ik = "D:" + key_desc(it[2:]) if it.startswith("D:") else (key_item(it) or "D:" + key_desc(it))
            ov[sec({"section": sc}) + "|" + ik] = v
        else:
            ov["*|" + (key_item(k) or "D:" + key_desc(k))] = v

    def get_ov(k):
        return ov.get(k) or ov.get("*|" + k.split("|", 1)[1], {})
    gs, ge, gr = group(sqs), group(eq), group(recap)
    # allow description fallback: EQ rows without a pay item that match an SQS description
    desc_to_item = {sec(r) + "|D:" + key_desc(r.get("description")): k for k, rows in gs.items() for r in rows}
    for k in list(ge):
        if "|D:" in k and k in desc_to_item:
            ge.setdefault(desc_to_item[k], []).extend(ge.pop(k))
    for k in list(gr):
        if "|D:" in k and k in desc_to_item:
            gr.setdefault(desc_to_item[k], []).extend(gr.pop(k))

    table1, table2, disc, findings, problems = [], [], [], [], []
    for k in list(gs) + [k for k in ge if k not in gs]:
        s_rows, e_rows, o = gs.get(k, []), ge.get(k, []), get_ov(k)
        t2_only = bool(e_rows) and not s_rows and all(r.get("table2_only") for r in e_rows)
        ref = (s_rows or e_rows)[0]
        s_vals = [num(r.get("qty")) for r in s_rows]
        e_vals = [num(r.get("qty")) for r in e_rows]
        for r, v in zip(s_rows + e_rows, s_vals + e_vals):
            if v is None and r.get("qty") not in (None, ""):
                problems.append(f"unreadable qty {r.get('qty')!r} for {r.get('pay_item') or r.get('description')} on {r.get('sheet_id')}")
        s_q = sum(v for v in s_vals if v is not None) if s_rows else None
        e_q = sum(v for v in e_vals if v is not None) if e_rows else None
        if o.get("eq_qty") is not None:
            e_q = num(o["eq_qty"])
        note = []
        if not s_rows:
            status = "NOT FOUND ON SQS"
        elif e_q is None:
            status = "NOT FOUND ON EQ"
        elif abs(s_q - e_q) < 1e-6:
            status = "MATCH"
        elif s_q == math.ceil(e_q - 1e-9):
            status = "MATCH"
            note.append(f"EQ {fmt(e_q)} rounded up to {fmt(s_q)}")
        else:
            status = "MISMATCH"
        if len(e_rows) > 1:
            note.append("EQ sum of " + " + ".join(f"{fmt(v)} ({r.get('sheet_id')})" for r, v in zip(e_rows, e_vals)))
        if o.get("table1_status"):
            assert o["table1_status"] in T1, o["table1_status"]
            if o["table1_status"] != status:
                note.append(f"computed {status}; set to {o['table1_status']} by rule")
            status = o["table1_status"]
        if o.get("note"):
            note.append(o["note"])
        row = dict(section=sec(ref), pay_item=ref.get("pay_item"), description=ref.get("description"), unit=ref.get("unit"),
                   eq_qty=fmt(e_q), eq_sheets=sorted({r.get("sheet_id") for r in e_rows if r.get("sheet_id")}),
                   sqs_qty=fmt(s_q), sqs_sheets=sorted({r.get("sheet_id") for r in s_rows if r.get("sheet_id")}),
                   status=status, notes="; ".join(note))
        if not t2_only:
            table1.append(row)
        if status == "MISMATCH" and not t2_only:
            disc.append(dict(table="Table 1", pay_item=row["pay_item"], description=row["description"],
                             values=f"EQ {row['eq_qty']} ({', '.join(row['eq_sheets'])}) vs SQS {row['sqs_qty']} ({', '.join(row['sqs_sheets'])})",
                             cause=o.get("cause", "")))
            loc = where(s_rows) + where(e_rows)
            findings.append(dict(task="quantity", severity="high", sheet_ids=row["eq_sheets"] + row["sqs_sheets"],
                                 pdf_pages=sorted({l["page"] for l in loc}), evidence=disc[-1]["values"],
                                 finding=f"Quantity mismatch for {row['pay_item'] or ''} {row['description']}: {disc[-1]['values']}",
                                 suggested_fix=o.get("cause", "Verify quantity source and correct SQS or EQ"), locate=loc))

        # Table 2 (only items with EQ rows)
        if not e_rows:
            continue
        expected = any(r.get("recap_expected") for r in e_rows)
        r_rows = gr.get(k, [])
        r_q = sum(num(r.get("qty")) or 0 for r in r_rows) if r_rows else None
        listed = sorted({s for r in e_rows for s in (r.get("recap_sheets_listed") or [])})
        found = sorted({r.get("sheet_id") for r in r_rows})
        note2 = []
        if not expected:
            st2 = "N/A-NO RECAP EXPECTED"
        elif not r_rows:
            st2 = "RECAP NOT FOUND"
        elif listed and set(listed) - set(found):
            st2 = "PARTIAL-SOME RECAP SHEETS MISSING"
            note2.append("listed but not summed: " + ", ".join(sorted(set(listed) - set(found))))
        elif abs(r_q - e_q) <= 0.01 + 1e-9:
            st2 = "MATCH"
        elif r_q == math.ceil(e_q - 1e-9):
            st2 = "MATCH"
            note2.append(f"recap shows EQ {fmt(e_q)} rounded up")
        else:
            st2 = "MISMATCH"
        if r_rows:
            note2.append(" + ".join(f"{fmt(num(r.get('qty')))} ({r.get('sheet_id')})" for r in r_rows) + f" = {fmt(r_q)}")
        if o.get("table2_status"):
            assert o["table2_status"] in T2, o["table2_status"]
            st2 = o["table2_status"]
        row2 = dict(section=sec(ref), description=ref.get("description"), unit=ref.get("unit"), recap_sum=fmt(r_q), recap_sheets=found,
                    eq_total=fmt(e_q), eq_sheets=row["eq_sheets"], status=st2, notes="; ".join(note2))
        table2.append(row2)
        if st2 == "MISMATCH":
            disc.append(dict(table="Table 2", pay_item=ref.get("pay_item"), description=ref.get("description"),
                             values=f"Recap {fmt(r_q)} ({', '.join(found)}) vs EQ {fmt(e_q)} ({', '.join(row['eq_sheets'])})",
                             cause=o.get("cause", "")))
            loc = where(e_rows) + where(r_rows)
            findings.append(dict(task="quantity", severity="medium", sheet_ids=found + row["eq_sheets"],
                                 pdf_pages=sorted({l["page"] for l in loc}), evidence=disc[-1]["values"],
                                 finding=f"Recap does not match EQ total for {ref.get('description')}: {disc[-1]['values']}",
                                 suggested_fix=o.get("cause", "Check recap tables on working sheets against EQ total"),
                                 locate=loc))
    for i, f in enumerate(findings, 1):
        f["id"] = f"QTY-{i:03d}"
    counts1 = {s: sum(r["status"] == s for r in table1) for s in T1}
    counts2 = {s: sum(r["status"] == s for r in table2) for s in T2}
    save_json(os.path.join(d, "quantities.json"), dict(table1=table1, table2=table2, discrepancies=disc,
                                                       findings=findings, problems=problems,
                                                       counts=dict(table1=counts1, table2=counts2)))
    print(json.dumps(dict(table1=counts1, table2=counts2, problems=problems), indent=1))


if __name__ == "__main__":
    main()
