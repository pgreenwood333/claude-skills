#!/usr/bin/env python3
"""Evidence gate: every flag must point at something that is really on the sheet. No evidence, no flag.

  validate_findings.py <plans.pdf> <index_dir> <work_dir>

Runs after the agents and before review. For each finding in <work>/findings/*.json it checks, by code:
  SHEET     each pdf_page exists and its Sheet ID (from the index) is in sheet_ids
  LOCATE    every locate entry lands on its page (a rect inside the page, or text that is found on it)
  QUOTE     the quoted evidence is printed on that page (text layer or OCR words; spacing and case ignored).
            Quotes are the parts of `evidence` in backticks (agents put every printed string in backticks and their
            own words outside them; backticks because plans use " for inches). Older findings: double quotes, else
            each " | "-separated part is checked.
            Skipped for quantity findings (numbers come from transcribed tables) and for text the agent marks
            `"evidence_source": "visual"` (read from a render because it has no text copy; then a crop is required)
  CROP      a crop named in the finding exists
Writes `gate` into each finding ({"pass": bool, "problems": [...]}) in place, and prints a summary.
A failed gate is not a rejection: merge_findings.py keeps the flag as uncertain and the grader must look at it.
An agent that keeps failing the gate is guessing; send its failures back to it once (see SKILL.md Step 4).
"""
import glob, json, os, re, sys
import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qaqc_common import load_json, save_json, squash, locate_text  # noqa: E402

QUOTE = re.compile(r"`([^`]{2,})`")          # printed text goes in backticks (plans use " for inches)
DQUOTE = re.compile(r'"([^"]{2,})"|“([^”]{2,})”')


def page_text(doc, db, pno, cache):
    if pno not in cache:
        t = doc[pno - 1].get_text()
        if db:
            import sqlite3
            con = sqlite3.connect(db)
            t += " " + " ".join(r[0] for r in con.execute("SELECT text FROM words WHERE page=?", (pno,)))
        cache[pno] = squash(t)
    return cache[pno]


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    pdf, index, work = sys.argv[1:]
    doc = pymupdf.open(pdf)
    idx = load_json(os.path.join(index, "index.json"))
    sid = {p["pdf_page"]: p["sheet_id"] for p in idx["pages"]}
    db = os.path.join(index, "index.db")
    db = db if os.path.exists(db) else None
    cache, summary = {}, {}
    for path in sorted(glob.glob(os.path.join(work, "findings", "*.json"))):
        data = load_json(path, {})
        for f in data.get("findings", []):
            probs = []
            pages = f.get("pdf_pages") or sorted({l.get("page") for l in f.get("locate", []) if l.get("page")})
            for p in pages:
                if not isinstance(p, int) or not 1 <= p <= doc.page_count:
                    probs.append(f"SHEET: page {p} does not exist")
            real = [p for p in pages if isinstance(p, int) and 1 <= p <= doc.page_count]
            if f.get("sheet_ids") and real and not any(sid.get(p) in f["sheet_ids"] for p in real):
                probs.append(f"SHEET: pages {real} are {[sid.get(p) for p in real]}, finding says {f['sheet_ids']}")
            for l in f.get("locate", []):
                p = l.get("page")
                if not isinstance(p, int) or not 1 <= p <= doc.page_count:
                    probs.append(f"LOCATE: bad page {p}")
                    continue
                pg = doc[p - 1]
                if l.get("rect"):
                    r = pymupdf.Rect(l["rect"])
                    if r.is_empty or not pg.rect.contains(r):
                        probs.append(f"LOCATE: rect {l['rect']} is not inside page {p}")
                elif l.get("text"):
                    near = pymupdf.Rect(l["near"]) if l.get("near") else None
                    if not locate_text(pg, db, l["text"], near):
                        probs.append(f"LOCATE: text {l['text']!r} not found on page {p}")
                else:
                    probs.append("LOCATE: entry has neither rect nor text")
            if not f.get("locate"):
                probs.append("LOCATE: none given")
            ev = f.get("evidence") or ""
            if f.get("task") != "quantity" and f.get("evidence_source") != "visual" and ev and pages:
                quotes = (QUOTE.findall(ev) or [a or b for a, b in DQUOTE.findall(ev)]
                          or [x for x in re.split(r"\s\|\s", ev)])
                for q in quotes:
                    if len(squash(q)) < 2:
                        continue
                    if not any(squash(q) in page_text(doc, db, p, cache) for p in pages if isinstance(p, int)
                               and 1 <= p <= doc.page_count):
                        probs.append(f"QUOTE: {q[:60]!r} is not printed on page(s) {pages}")
            if f.get("evidence_source") == "visual" and not f.get("crop"):
                probs.append("CROP: visual evidence needs a crop")
            if f.get("crop") and not os.path.exists(f["crop"]):
                probs.append(f"CROP: {f['crop']} missing")
            f["gate"] = {"pass": not probs, "problems": probs}
            s = summary.setdefault(f.get("task", "?"), {"pass": 0, "fail": 0, "failed_ids": []})
            if probs:
                s["fail"] += 1
                s["failed_ids"].append(f.get("id"))
            else:
                s["pass"] += 1
        save_json(path, data)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
