#!/usr/bin/env python3
"""Read the plan-set title sheet: project facts for the cover, and a clean image of the sheet.

  title_sheet.py <title_sheet.pdf> <out_dir> [--page 1]

Writes <out>/title_sheet.png (300 dpi, white margins trimmed) and <out>/project.json with CANDIDATES:
  project_name, job_numbers (FMS / job nos like 123456/301000), federal_aid (like STP-0000-00(001) or
  IM-0000-00(001)), counties, firm (from "DESIGNED BY:"), and the raw text so you can check them.
Everything is read from the sheet's text layer; a field that is not found is left empty, never guessed.
Confirm the candidates with the user (multi-project jobs list several numbers; the user picks the order).
"""
import argparse, json, os, re
import pymupdf

JOB = re.compile(r"\b(\d{6}\s*/\s*\d{6})\b")
FED = re.compile(r"\b([A-Z]{2,5}(?:-[A-Z0-9]{1,5})*-\d{2,4}-\d{2}\(\d{3}\))")
COUNTY = re.compile(r"\b([A-Z][A-Z .]+?) COUNT(?:Y|IES)\b")
COUNTY2 = re.compile(r"\bCOUNT(?:Y|IES):?[ \t]*\n[ \t]*([A-Z][A-Z ,&]+?)[ \t]*\n")
FIRM = re.compile(r"DESIGNED\s+BY:?\s*([A-Z][A-Z&.,\- ]{2,40}?)(?:\s+INC\.?|\s+LLC|\s*$|\n)", re.M)


def trim(pix_path):
    from PIL import Image, ImageOps
    im = Image.open(pix_path).convert("RGB")
    box = ImageOps.invert(im.convert("L")).point(lambda v: 255 if v > 25 else 0).getbbox()
    if box:
        pad = 20
        box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width), min(box[3] + pad, im.height))
        im = im.crop(box)
    im.save(pix_path)
    return im.size


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("out"); ap.add_argument("--page", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    doc = pymupdf.open(a.pdf)
    page = doc[a.page - 1]
    png = os.path.join(a.out, "title_sheet.png")
    page.get_pixmap(dpi=200).save(png)
    size = trim(png)
    text = page.get_text()
    flat = re.sub(r"[ \t]+", " ", text)
    jobs = []
    for j in JOB.findall(flat):
        a_, b_ = re.sub(r"\s", "", j).split("/")
        if a_.startswith("30") and not b_.startswith("30"):   # stacked text read bottom-up: FMS no. comes first
            a_, b_ = b_, a_
        if f"{a_}/{b_}" not in jobs:
            jobs.append(f"{a_}/{b_}")
    feds = list(dict.fromkeys(FED.findall(flat.replace(" ", ""))))
    up = flat.upper()
    found = [c for c in COUNTY.findall(up) if "\n" not in c] + COUNTY2.findall(up)
    counties = list(dict.fromkeys(c.strip().title() for c in found
                                  if 2 < len(c.strip()) < 30 and not re.search(r"PROJECT|LINE|ROAD|SEAT", c)))
    firm = FIRM.search(flat.upper())
    # project name: the line(s) just above the county line under the PLAN AND PROFILE / project number block
    name = ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines):
        if re.search(r"\bCOUNT(Y|IES)\b", l.upper()) and i > 0 and len(lines[i - 1]) > 6 \
                and not FED.search(lines[i - 1].replace(" ", "")):
            name = lines[i - 1].title()
            break
    info = dict(project_name=name, job_numbers=jobs, federal_aid=feds, counties=counties,
                firm=(firm.group(1).strip().rstrip(",") if firm else ""), image=png, image_px=list(size),
                note="Candidates read from the title sheet text. Confirm with the user before building.",
                raw_text=text[:6000])
    json.dump(info, open(os.path.join(a.out, "project.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in info.items() if k != "raw_text"}, indent=1))


if __name__ == "__main__":
    main()
