"""Render part of a sheet to PNG to check extracted notes against the drawing.
Usage: python3 render_check.py plans.pdf PAGE out.png [x0 y0 x1 y1] [--dpi 150]
Box is in 100-dpi pixels (same units as notes.json x/y); default is the upper profile band.
Use a note's x/y from notes.json to zoom: e.g. x-40 y-60 x+400 y+260."""
import sys
import pymupdf

args = [a for a in sys.argv[1:] if not a.startswith("--")]
dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 150
if "--dpi" in sys.argv:
    args.remove(str(dpi))
pdf, page, out = args[0], int(args[1]), args[2]
pg = pymupdf.open(pdf)[page - 1]
k = 72 / 100
if len(args) >= 7:
    box = pymupdf.Rect(*[float(v) * k for v in args[3:7]])
else:
    r = pg.rect
    box = pymupdf.Rect(r.width * .07, r.height * .49, r.width * .92, r.height * .75)
pg.get_pixmap(dpi=dpi, clip=box & pg.rect).save(out)
print(out, [round(v / k) for v in box])
