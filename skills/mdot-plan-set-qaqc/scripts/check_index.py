#!/usr/bin/env python3
"""Compare the Detailed Index (as transcribed by the index agent) against the sheets actually in the PDF.

  check_index.py <index_dir> <di_entries.json> <out_findings.json>

di_entries.json:
  {"groups":  [{"name": "QUANTITY SHEETS", "count": 8}],
   "entries": [{"group": "QUANTITY SHEETS", "description": "SUMMARY OF QUANTITIES", "sheet_id": "SQ-2",
                "sheet_no": "8", "di_page": 2}],
   "total_sheets": 85}
Checks: listed sheets missing from the PDF, PDF sheets missing from the index, duplicate IDs or numbers in the index,
sheet number in the index vs the sheet's title block, description vs title-block title (word overlap, for the agent
to judge), group counts, and sheet-number order. Sheets numbered as standard drawings (6000s), bridge (8000s) or
cross sections (9000s) that are absent are reported as low severity "not in this PDF" (often intentional).
"""
import json, os, re, sys
from collections import Counter
from qaqc_common import load_json, save_json


def nid(s):
    return re.sub(r"\s+", " ", re.sub(r"\s*-\s*", "-", (s or "").upper())).strip()


def toks(s):
    """Words of a title for exact comparison: case, dashes used as separators, line breaks and trailing commas
    are ignored; hyphenated words are joined (MULTI- USE = MULTI-USE = MULTIUSE)."""
    s = (s or "").upper().replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"(\w)-\s*(\w)", r"\1\2", s)          # MULTI- USE -> MULTIUSE
    s = re.sub(r"\s-\s|\s-$|^-\s", " ", s)            # " - " separators
    out = []
    for t in s.split():
        t = t.strip(",;:")
        if t and t not in {"-", "&"}:
            out.append(t)
    return out


def main():
    idx = load_json(os.path.join(sys.argv[1], "index.json"))
    di = load_json(sys.argv[2])
    out = sys.argv[3]
    pages = [p for p in idx["pages"] if p["sheet_id"] not in ("UNKNOWN",)]
    by_id = {}
    for p in pages:
        by_id.setdefault(nid(p["sheet_id"]), []).append(p)
    F = []

    def add(sev, finding, evidence, sheet_ids, pdf_pages, locate, fix=""):
        F.append(dict(task="index", severity=sev, sheet_ids=sheet_ids, pdf_pages=pdf_pages, evidence=evidence,
                      finding=finding, suggested_fix=fix, locate=locate))

    entries = di["entries"]
    absent_std, extras = [], []
    di_page = next((e.get("di_page") for e in entries if e.get("di_page")), None)
    seen_id, seen_no = {}, {}
    for e in entries:
        sid, sno = nid(e.get("sheet_id")), (e.get("sheet_no") or "").strip()
        loc = [dict(page=e.get("di_page") or di_page, text=e.get("sheet_id") or e.get("description"), all=True)]
        if sid:
            if sid in seen_id:
                add("high", f"Sheet ID {sid} is listed twice in the Detailed Index "
                            f"('{seen_id[sid]['description']}' no. {seen_id[sid].get('sheet_no')} and "
                            f"'{e['description']}' no. {sno})",
                    f"{sid} / {sno}", [sid], [loc[0]["page"]], loc, "Correct the duplicate Sheet ID in the index")
            seen_id[sid] = e
        if sno and not re.match(r"^\d+-\d+$", sno):
            if sno in seen_no and sno != sid:
                add("high", f"Sheet number {sno} is listed twice in the Detailed Index ({seen_no[sno].get('sheet_id')} and {sid})",
                    sno, [sid], [loc[0]["page"]], loc)
            seen_no[sno] = e
        if not sid:
            continue
        actual = by_id.get(sid)
        if not actual:
            n = int(sno) if sno.isdigit() else None
            if n and (6000 <= n < 7000 or 8000 <= n < 10000):
                absent_std.append(f"{sid} ({sno})")
            else:
                add("high", f"{sid} ('{e['description']}', no. {sno}) is listed in the Detailed Index but is not in the PDF",
                    sid, [sid], [], loc, "Add the sheet or remove it from the index")
            continue
        p = actual[0]
        if sno and p.get("sheet_no") and nid(sno) != nid(p["sheet_no"]):
            add("high", f"{sid}: index lists sheet no. {sno} but the title block shows {p['sheet_no']}",
                f"Index {sno} vs title block {p['sheet_no']}", [sid], [loc[0]["page"], p["pdf_page"]],
                loc + [dict(page=p["pdf_page"], text=p["sheet_no"])], "Make the index and title block agree")
        di_t = Counter(toks(e["description"]))
        tb_txt, tb_ocr = Counter(toks(p.get("title"))), Counter(toks(p.get("title_ocr")))
        if not tb_txt and not tb_ocr:
            add("medium", f"{sid}: title block title could not be read; compare to '{e['description']}' visually",
                e["description"], [sid], [p["pdf_page"]], [], "Agent: read the title block and compare")
            continue
        missing = (di_t - tb_txt) if tb_txt else (di_t - tb_ocr)
        if tb_txt and tb_ocr:
            missing = missing & (di_t - tb_ocr)       # a word counts as missing only if neither reader found it
        extra = (tb_txt or tb_ocr) - di_t
        if tb_txt and tb_ocr:
            extra = extra & (tb_ocr - di_t)
        tb_show = p.get("title") or p.get("title_ocr")
        if missing:
            ex = f" In the title block but not the index: {' '.join(sorted(extra.elements()))}." if extra else ""
            add("medium", f"{sid}: index description does not match the title block. In the index but not the title "
                          f"block: {' '.join(sorted(missing.elements()))}.{ex} Index: '{e['description']}'. "
                          f"Title block: '{tb_show}'",
                f"{e['description']} | {tb_show}", [sid], [loc[0]["page"], p["pdf_page"]],
                [dict(page=loc[0]["page"], text=e.get("sheet_id"), all=True)] +
                ([dict(page=p["pdf_page"], rect=p["title_box"])] if p.get("title_box") else []),
                "Make the index description and the sheet title identical")
        if extra and not missing:
            extras.append((sid, " ".join(sorted(extra.elements())), e, p, tb_show, loc))
    series = Counter(x[1] for x in extras)
    for text, n in series.items():
        sheets = [x[0] for x in extras if x[1] == text]
        if n >= 3:
            add("low", f"Title blocks of {n} sheets carry words the index descriptions leave out: '{text}' "
                       f"({', '.join(sheets)}). Usually a project line; confirm the index wording is intended.",
                text, sheets, [], [])
        else:
            for sid, _, e, p, tb_show, loc in [x for x in extras if x[1] == text]:
                add("medium", f"{sid}: title block has words the index description lacks: {text}. "
                              f"Index: '{e['description']}'. Title block: '{tb_show}'",
                    f"{e['description']} | {tb_show}", [sid], [loc[0]["page"], p["pdf_page"]],
                    [dict(page=loc[0]["page"], text=e.get("sheet_id"), all=True)] +
                    ([dict(page=p["pdf_page"], rect=p["title_box"])] if p.get("title_box") else []),
                    "Make the index description and the sheet title identical")
    # the index must list sheets in the same order as they are bound
    order = [(e, by_id[nid(e.get("sheet_id"))][0]["pdf_page"]) for e in entries if nid(e.get("sheet_id")) in by_id]
    for (e1, p1), (e2, p2) in zip(order, order[1:]):
        if p2 < p1:
            add("medium", f"Index order differs from the plan set: {nid(e2['sheet_id'])} (pdf page {p2}) is listed after "
                          f"{nid(e1['sheet_id'])} (pdf page {p1})", f"{nid(e1['sheet_id'])} -> {nid(e2['sheet_id'])}",
                [nid(e2["sheet_id"])], [p2], [dict(page=e2.get("di_page") or di_page, text=e2.get("sheet_id"))])
    listed = set(seen_id)
    for sid, ps in by_id.items():
        if sid not in listed and sid != "TITLE":
            for p in ps:
                add("high", f"{sid} (pdf page {p['pdf_page']}, '{p.get('title')}') is in the PDF but not in the Detailed Index",
                    sid, [sid], [p["pdf_page"]], [dict(page=p["pdf_page"], text=p["sheet_id"])], "Add it to the index")
    # group counts
    for g in di.get("groups", []):
        n = 0
        for e in entries:
            if e.get("group") != g["name"] or not (e.get("sheet_id") or e.get("sheet_no")):
                continue
            m = re.match(r"^(\d+)\s*-\s*(\d+)$", (e.get("sheet_no") or "").strip())
            n += int(m.group(2)) - int(m.group(1)) + 1 if m else 1  # "9001-9004" is four sheets
        if g.get("count") is not None and n != int(g["count"]):
            add("medium", f"Index group '{g['name']}' says ({g['count']}) but lists {n} sheets", g["name"], [], [di_page],
                [dict(page=di_page, text=g["name"])])
    # sheet number order within the PDF
    nums = [(p["pdf_page"], int(p["sheet_no"])) for p in pages if (p.get("sheet_no") or "").isdigit()]
    for (pa, na), (pb, nb) in zip(nums, nums[1:]):
        if nb <= na:
            add("medium", f"Sheet numbers out of order: pdf page {pa} is no. {na}, pdf page {pb} is no. {nb}",
                f"{na} -> {nb}", [], [pa, pb], [dict(page=pb, text=str(nb))])
    if absent_std:
        add("low", f"{len(absent_std)} standard drawing / bridge / cross-section sheets are listed but not bound in this "
                   f"PDF (normal when they are issued separately; confirm): " + ", ".join(absent_std),
            "", [], [di_page], [])
    if di.get("total_sheets"):
        add("low", f"Index total sheets = {di['total_sheets']}; this PDF has {len(idx['pages'])} pages "
                   f"({len(listed & set(by_id))} of {len(listed)} listed sheets present)",
            str(di["total_sheets"]), [], [di_page], [])
    for i, f in enumerate(F, 1):
        f["id"] = f"IDX-{i:03d}"
    save_json(out, dict(findings=F))
    print(json.dumps({s: sum(f["severity"] == s for f in F) for s in ("high", "medium", "low")}))


if __name__ == "__main__":
    main()
