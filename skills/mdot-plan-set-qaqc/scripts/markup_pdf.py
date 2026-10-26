#!/usr/bin/env python3
"""Mark up the plan set with red highlighter for every confirmed finding.

  markup_pdf.py <plans.pdf> <index_dir> <findings_reviewed.json> <out.pdf> [--include-uncertain]

Each finding's `locate` list says where to highlight:
  {"page": 15, "rect": [x0, y0, x1, y1]}      exact area in PDF points (overlaps, OCR words, anything measured)
  {"page": 2,  "text": "PERMAMENT"}             searched on that page (text layer, then OCR words)
  {"page": 7,  "text": "203-A001", "near": [x0, y0, x1, y1]}   pick the hit closest to `near`
Anything that cannot be located gets a red sticky note on its page instead, so nothing is silently dropped.
The tool writes `markup` back into the findings file: "highlighted", "note", or "skipped".
"""
import argparse, os, sys
import pymupdf
from qaqc_common import load_json, save_json, locate_text

RED = (0.85, 0.0, 0.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("index"); ap.add_argument("findings"); ap.add_argument("out")
    ap.add_argument("--include-uncertain", action="store_true")
    a = ap.parse_args()
    data = load_json(a.findings)
    doc = pymupdf.open(a.pdf)
    db = os.path.join(a.index, "index.db")
    counts = dict(highlighted=0, note=0, skipped=0)
    note_slots = {}
    for f in data["findings"]:
        verdict = (f.get("review") or {}).get("verdict", "uncertain")
        if verdict == "rejected" or (verdict != "confirmed" and not a.include_uncertain):
            f["markup"] = "skipped"
            counts["skipped"] += 1
            continue
        label = f"{f['id']} [{f.get('severity', '').upper()}] {f.get('finding', '')}"
        if f.get("suggested_fix"):
            label += f"\nSuggested: {f['suggested_fix']}"
        done = False
        for loc in f.get("locate", []):
            pno = int(loc["page"])
            if not 1 <= pno <= len(doc):
                continue
            page = doc[pno - 1]
            if page.rotation:
                print(f"warning: page {pno} is rotated {page.rotation} deg; check highlight positions", file=sys.stderr)
            rects = []
            if loc.get("rect"):
                rects = [pymupdf.Rect(loc["rect"])]
            elif loc.get("text"):
                near = pymupdf.Rect(loc["near"]) if loc.get("near") else None
                found = locate_text(page, db, loc["text"], near)
                rects = found[:1] if near is not None or not loc.get("all") else found
            for r in rects:
                annot = page.add_highlight_annot(r)
                annot.set_colors(stroke=RED)
                annot.set_opacity(0.45)
                annot.set_info(title="QA/QC", content=label)
                annot.update()
                done = True
        if not done:  # fall back to a sticky note on the first page the finding names
            pages = [int(l["page"]) for l in f.get("locate", []) if l.get("page")] or f.get("pdf_pages") or [1]
            page = doc[int(pages[0]) - 1]
            k = note_slots.get(page.number, 0)
            note_slots[page.number] = k + 1
            pt = pymupdf.Point(page.rect.width * 0.86 - (k % 6) * 30, page.rect.height * 0.04 + (k // 6) * 30)
            annot = page.add_text_annot(pt, label + "\n(Location not found automatically.)", icon="Comment")
            annot.set_colors(stroke=RED)
            annot.set_info(title="QA/QC")
            annot.update()
        f["markup"] = "highlighted" if done else "note"
        counts["highlighted" if done else "note"] += 1
    # stamp on the first page
    p0 = doc[0]
    n = counts["highlighted"] + counts["note"]
    stamp = pymupdf.Rect(p0.rect.width * 0.02, p0.rect.height * 0.015, p0.rect.width * 0.40, p0.rect.height * 0.055)
    fa = p0.add_freetext_annot(stamp, f"QA/QC MARKUP: {n} flagged items highlighted in red. "
                                      f"See the QA/QC workbook for details. Flags are for engineer review.",
                               fontsize=14, text_color=RED)
    fa.set_info(title="QA/QC")
    fa.update()
    doc.save(a.out, garbage=3, deflate=True)
    save_json(a.findings, data)
    print(counts)


if __name__ == "__main__":
    main()
