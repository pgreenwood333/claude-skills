"""Extract stacked profile-view notes (structure, drive, culvert, bridge callouts) from plan-profile sheets.

Usage:
  python3 extract_profile_notes.py plans.pdf notes.json [--pages 1-20] [--sta-min 335+00] [--sta-max 355+00]
                                   [--hmin PX --hmax PX] [--region x0,y0,x1,y1]

How it works (copies the PDF text exactly; never retype notes):
  * Profile region = lower part of the sheet (default x 7%-92%, y 49%-94% of the page).
  * Note text is picked by height. The height is measured on this plan set (median height of the "STA." words,
    kept within 85-115%), so grid elevations, stationing, rotated VPI/VPC labels and title-block text drop out.
    Override with --hmin/--hmax (pixels at 100 dpi) if a set needs it.
  * Each note is anchored on a "STA." word followed by a station (or "STA.472+80" fused).
  * Lines are collected down the anchor's left edge; the structure ID line just above the STA line ("337 B") is
    included. A note ends at a >30 px vertical gap or where the next note's ID/STA line starts in the same column.
  * A row stops where it reaches another note's column, so side-by-side notes do not merge.
  * Stray leader fragments such as "NG=" are dropped.
"""
import argparse, json, re
from common import words, page_count, page_size_px, note_height


def sta_val(s):
    a, b = s.split("+")
    return int(a) * 100 + float(b)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("pdf"); ap.add_argument("out")
ap.add_argument("--pages"); ap.add_argument("--sta-min"); ap.add_argument("--sta-max")
ap.add_argument("--hmin", type=float); ap.add_argument("--hmax", type=float)
ap.add_argument("--region", default="0.07,0.49,0.92,0.94", help="x0,y0,x1,y1 as page fractions")
a = ap.parse_args()

if a.pages:
    s, _, e = a.pages.partition("-")
    pages = range(int(s), int(e or s) + 1)
else:
    pages = range(1, page_count(a.pdf) + 1)
fx0, fy0, fx1, fy1 = map(float, a.region.split(","))
DROP = {"NG="}
res, heights = [], []
for p in pages:
    PW, PH = page_size_px(a.pdf, p)
    X0, Y0, X1, Y1 = fx0 * PW, fy0 * PH, fx1 * PW, fy1 * PH
    region = [w for w in words(a.pdf, p) if Y0 < w[1] < Y1 and X0 < w[0] < X1]
    h = note_height(region)
    hmin = a.hmin if a.hmin is not None else (h * 0.85 if h else 0)
    hmax = a.hmax if a.hmax is not None else (h * 1.15 if h else 0)
    if h:
        heights.append(round(h, 1))
    W = [w for w in region if hmin < (w[3] - w[1]) < hmax]
    anchors = [w for w in W if w[4].startswith("STA.") and (
        re.match(r"STA\.\d{3}\+", w[4]) or
        any(-6 < v[0] - w[2] < 25 and abs(v[1] - w[1]) < 3 and re.match(r"\d{3}\+\d", v[4]) for v in W))]
    cols = [(c[0], c[1]) for c in anchors]
    for an in anchors:
        ax, ay = an[0], an[1]

        def row(y):
            r = sorted([w for w in W if abs(w[1] - y) < 2 and ax - 8 <= w[0]], key=lambda w: w[0])
            out, last = [], None
            for w in r:
                if last is not None and (w[0] - last > 75 or any(abs(w[0] - c[0]) < 3 and -40 < y - c[1] < 320
                                                                for c in cols if c[0] > ax + 5)):
                    break
                out.append(w)
                last = w[2]
            return [w for w in out if w[4] not in DROP]

        starts = sorted({round(w[1]) for w in W if abs(w[0] - ax) < 8})
        seq = [y for y in starts if ay - 25 < y < ay - 5] + [y for y in starts if y >= ay - 1]
        lines, last = [], None
        for y in seq:
            if last is not None and y - last > 30:
                break
            if last is not None and y - last < 5:
                continue
            rw = row(y)
            if len(lines) >= 2 and rw and (rw[0][4].startswith("STA.") or
                                           (len(rw) == 2 and re.match(r"^\d{3}$", rw[0][4]))):
                break  # next stacked note in the same column
            if rw:
                lines.append(" ".join(w[4] for w in rw))
                last = y
        m = re.search(r"(\d{3}\+\d\d(?:\.\d+)?)", " ".join(lines))
        if not m:
            print(f"warning: page {p}: note at x={ax:.0f} y={ay:.0f} has no readable station: {lines}")
            continue
        res.append(dict(page=p, x=round(ax), y=round(ay), sta=sta_val(m[1]), lines=lines))

if a.sta_min:
    res = [b for b in res if b["sta"] >= sta_val(a.sta_min)]
if a.sta_max:
    res = [b for b in res if b["sta"] <= sta_val(a.sta_max)]
side = lambda b: 0 if " LT" in " ".join(b["lines"][:3]) else 1
res.sort(key=lambda b: (b["sta"], side(b), b["lines"][0]))
json.dump(res, open(a.out, "w"), indent=1)
for b in res:
    print(f"p{b['page']:>3} {b['sta']:>10.2f} | " + " | ".join(b["lines"]))
print(f"\n{len(res)} notes (note text height measured at {sorted(set(heights))[:3]} px)")
