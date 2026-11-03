#!/usr/bin/env python3
"""Build the binder's title sheet + table of contents as a Word document (and a PDF of it).

  build_title_index.py <cover.json> <toc.json> <title_sheet.png> <out.docx> [--pdf]

cover.json: {"firm": "ACME ENGINEERING", "project_name": "Main Street Bridge Replacement",
             "numbers": ["123456/301000", "STP-0000-00(001)"],          # one line each, in the user's order
             "subtitle": "Quantity Calculations Binder", "status": "Final Plans"}
Layout (matches the approved approved binders exactly):
  page 1: firm (bold 11 pt), project name (28 pt), each number (13 pt), all blue #4472C4 with a blue bar down the
          left edge; subtitle (12 pt blue); the title sheet image 6.5" wide; status (13 pt blue), no date.
  page 2: "Table of Contents" (16 pt blue), then one bold 11 pt black line per section with a dotted leader
          to the right-aligned page range.
  Letter portrait, margins 0.5" top/bottom and 0.75" left/right, Word's default body font.
--pdf converts with LibreOffice (soffice) next to the .docx.
"""
import argparse, json, os, shutil, subprocess, sys
from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER, WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor, Twips

BLUE = RGBColor(0x44, 0x72, 0xC4)


def left_bar(p):
    ppr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    for k, v in (("w:val", "single"), ("w:color", "4472C4"), ("w:sz", "24"), ("w:space", "8")):
        left.set(qn(k), v)
    bdr.append(left)
    ppr.append(bdr)


def para(doc, text, size, before, after, bold=False, color=BLUE, bar=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Twips(before), Twips(after)
    if bar:
        left_bar(p)
    r = p.add_run(text)
    r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold or None, color
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cover"); ap.add_argument("toc"); ap.add_argument("image"); ap.add_argument("out")
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    cov, toc = json.load(open(a.cover)), json.load(open(a.toc))
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.top_margin = sec.bottom_margin = Twips(720)
    sec.left_margin = sec.right_margin = Twips(1080)
    st = doc.styles["Normal"]
    st.paragraph_format.space_after = Pt(0)
    nums = cov.get("numbers", [])
    if cov.get("firm"):
        para(doc, cov["firm"], 11, 200, 100, bold=True, bar=True)
    para(doc, cov["project_name"], 28, 100, 0, bar=True)
    for i, n in enumerate(nums):
        para(doc, n, 13, 150 if i == 0 else 60, 150 if i == len(nums) - 1 else 0, bar=True)
    para(doc, cov.get("subtitle", "Quantity Calculations Binder"), 12, 100, 200)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    from PIL import Image
    w, h = Image.open(a.image).size
    width = Inches(6.5)
    max_h = Inches(5.6 - 0.25 * max(0, len(nums) - 2))
    run = p.add_run()
    if width * h / w > max_h:
        run.add_picture(a.image, height=max_h)
    else:
        run.add_picture(a.image, width=width)
    para(doc, cov.get("status", "Final Plans"), 13, 300, 0)
    head = para(doc, "Table of Contents", 16, 0, 200)
    head.paragraph_format.page_break_before = True
    for row in toc:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Twips(120)
        p.paragraph_format.tab_stops.add_tab_stop(Twips(9360), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        for t in (row["title"], "\t", row["pages"]):
            r = p.add_run(t)
            r.font.size, r.font.bold, r.font.color.rgb = Pt(11), True, RGBColor(0, 0, 0)
    doc.save(a.out)
    print("wrote", a.out)
    if a.pdf:
        so = next((s for s in ("soffice", "libreoffice") if shutil.which(s)), None) or \
             ("/Applications/LibreOffice.app/Contents/MacOS/soffice"
              if os.path.exists("/Applications/LibreOffice.app/Contents/MacOS/soffice") else None)
        if not so:
            sys.exit("No LibreOffice here to make the PDF: open the .docx in Word and Save As PDF, or run in Cowork.")
        subprocess.run([so, "--headless", "--convert-to", "pdf", "--outdir", os.path.dirname(os.path.abspath(a.out)),
                        a.out], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        print("wrote", os.path.splitext(a.out)[0] + ".pdf")


if __name__ == "__main__":
    main()
