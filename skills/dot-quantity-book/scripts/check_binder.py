#!/usr/bin/env python3
"""Final check of the binder before it goes to the user. Code checks, not opinions.

  check_binder.py <binder.pdf> <toc.json> [--title-pdf <titlesheet_index.pdf>] [--start 3] [--renders <dir>]

Checks every problem caught on past binders:
  ERRORS      spreadsheet error values printed anywhere (#NAME?, #REF!, #VALUE!, #DIV/0!, #N/A, #NUM!)
  CUT_OFF     ink touching the page edge (a table or drawing cut off by the print area)
  STRAY_NUM   a lone number in the top-right corner (the engineer's own page numbers left in the sheet)
  PAGE_NUMS   bottom-center numbers run start..end with no gaps or doubles
  TOC         TOC ranges cover every page exactly once, in order, and match the binder's page count
  TOC_DOC     the title/index PDF shows the same TOC lines (when --title-pdf is given)
  BLANK       an empty page
  HIDDEN_ERROR (warning) an error value in the text layer that does not print (a cell under a picture)
Writes renders of every page (60 dpi) to --renders so you can look at the whole binder before delivering.
Exit code 1 when anything fails.
"""
import argparse, json, os, re, sys
import numpy as np
import pymupdf

ERR = re.compile(r"#(NAME\?|REF!|VALUE!|DIV/0!|N/A|NUM!|NULL!|SPILL!)")


def ink(page, dpi=50):
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return a < 200


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("toc"); ap.add_argument("--title-pdf"); ap.add_argument("--start", type=int, default=3)
    ap.add_argument("--renders")
    a = ap.parse_args()
    doc = pymupdf.open(a.pdf)
    toc = json.load(open(a.toc))
    probs, warns = [], []
    if a.renders:
        os.makedirs(a.renders, exist_ok=True)
    expect = a.start
    for i, page in enumerate(doc):
        n = a.start + i
        txt = page.get_text()
        for m in set(ERR.findall(txt)):
            for r_ in page.search_for("#" + m):
                pix = page.get_pixmap(dpi=150, clip=r_, colorspace=pymupdf.csGRAY)
                dark = (np.frombuffer(pix.samples, dtype=np.uint8) < 128).mean()
                if dark > 0.04:
                    probs.append(f"ERRORS p{n}: #{m} printed on the page at {[round(v) for v in r_]}")
                else:
                    warns.append(f"HIDDEN_ERROR p{n}: a cell holds #{m} under a picture or white fill at "
                                 f"{[round(v) for v in r_]}; it does not print, but the calc behind it may be broken")
        m = ink(page)
        h, w = m.shape
        e = 2
        edges = {"left": m[:, :e].mean(), "right": m[:, -e:].mean(), "top": m[:e, :].mean(), "bottom": m[-e:, :].mean()}
        for side, v in edges.items():
            if v > 0.03:
                probs.append(f"CUT_OFF p{n}: content runs into the {side} edge ({v:.0%} of the edge has ink)")
        if m.mean() < 0.002:
            probs.append(f"BLANK p{n}: page is empty")
        r = page.rect
        corner = pymupdf.Rect(r.width * 0.75, 0, r.width, r.height * 0.12)
        words = page.get_text("words", clip=corner)
        for wd in words:
            alone = not any(o is not wd and abs(o[1] - wd[1]) < 30 and abs(o[0] - wd[0]) < 80 for o in words)
            if re.fullmatch(r"\d{1,2}", wd[4]) and 1 <= int(wd[4]) <= 99 and alone:
                probs.append(f"STRAY_NUM p{n}: lone number {wd[4]!r} in the top-right corner")
        bottom = pymupdf.Rect(r.width / 2 - 30, r.height - 32, r.width / 2 + 30, r.height - 8)
        got = [wd[4] for wd in page.get_text("words", clip=bottom) if wd[4].isdigit()]
        if got != [str(expect)]:
            probs.append(f"PAGE_NUMS p{n}: bottom-center shows {got}, expected ['{expect}']")
        expect += 1
        if a.renders:
            page.get_pixmap(dpi=60).save(os.path.join(a.renders, f"p{n:03d}.png"))
    covered = []
    for row in toc:
        lo, _, hi = row["pages"].partition("-")
        covered += list(range(int(lo), int(hi or lo) + 1))
    want = list(range(a.start, a.start + doc.page_count))
    if covered != want:
        probs.append(f"TOC: sections cover pages {covered[:3]}..{covered[-3:]} ({len(covered)}), binder is "
                     f"{want[0]}-{want[-1]} ({len(want)})")
    if a.title_pdf:
        t = pymupdf.open(a.title_pdf)
        ttxt = re.sub(r"\.{3,}", " ", " ".join(p.get_text() for p in t))
        ttxt = re.sub(r"\s+", " ", ttxt)
        for row in toc:
            if row["title"] not in ttxt or row["pages"] not in ttxt:
                probs.append(f"TOC_DOC: {row['title']!r} {row['pages']} not shown in the title/index PDF")
    print(json.dumps(dict(pages=doc.page_count, problems=probs, warnings=warns, ok=not probs), indent=1))
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
