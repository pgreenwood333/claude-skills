#!/usr/bin/env python3
"""Stitch the section PDFs into one numbered quantity-calculations binder and write the table of contents.

  assemble.py <plan.json> <out.pdf> [--start 3]

plan.json (you write it after the user confirms the order):
  {"sections": [
     {"title": "Asphalt, Tack Coat, Borrow, Sidewalk & Curb/Gutter",
      "parts": [{"pdf": "work/pdf/ASPHALT PAVEMENT__Sheet1.pdf"}]},
     {"title": "Permanent Erosion Control",
      "parts": [{"pdf": "work/pdf/PERM EROSION CONTROL__Calc.pdf", "drop": [1]}]},    # drop = pages to leave out
     {"title": "Earthwork Calculations",
      "parts": [{"pdf": ".../Summary.pdf"}, {"pdf": ".../Hand_Calc.pdf", "pages": "1-2"}]}]}
Each page keeps its own size and orientation. Page numbers go bottom-center only, Helvetica 10 pt, starting
at --start (the title sheet and table of contents are pages 1-2). Pages that already carry a number in a
bottom-center box are reported so you can check for doubles.
Writes <out.pdf> and <out>.toc.json: [{"title": ..., "pages": "3-4"}, ...] for build_title_index.py.
"""
import argparse, json, os
import pymupdf


def page_list(spec, n):
    if not spec or spec == "all":
        return list(range(1, n + 1))
    out = []
    for part in str(spec).split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 1 <= p <= n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("out"); ap.add_argument("--start", type=int, default=3)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    out = pymupdf.open()
    toc, num = [], a.start
    for sec in plan["sections"]:
        first = num
        for part in sec["parts"]:
            src = pymupdf.open(part["pdf"])
            keep = [p for p in page_list(part.get("pages"), src.page_count) if p not in set(part.get("drop", []))]
            for p in keep:
                out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
                num += 1
        last = num - 1
        if last < first:
            raise SystemExit(f"section {sec['title']!r} has no pages")
        toc.append(dict(title=sec["title"], pages=str(first) if first == last else f"{first}-{last}"))
    warnings = []
    for i, page in enumerate(out):
        label = str(a.start + i)
        r = page.rect
        box = pymupdf.Rect(r.width / 2 - 30, r.height - 32, r.width / 2 + 30, r.height - 12)
        if page.get_text("text", clip=box).strip():
            warnings.append(f"page {label}: text already in the page-number spot: "
                            f"{page.get_text('text', clip=box).strip()[:30]!r}")
        w = pymupdf.get_text_length(label, fontname="helv", fontsize=10)
        page.insert_text(((r.width - w) / 2, r.height - 17), label, fontname="helv", fontsize=10, color=(0, 0, 0))
    out.save(a.out, garbage=3, deflate=True)
    json.dump(toc, open(os.path.splitext(a.out)[0] + ".toc.json", "w"), indent=1)
    print(json.dumps(dict(pages=out.page_count, numbered=f"{a.start}-{a.start + out.page_count - 1}", toc=toc,
                          warnings=warnings), indent=1))


if __name__ == "__main__":
    main()
