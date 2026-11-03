"""Stacked-note extraction shared by the note-match check (same algorithm as the profile-notes-extractor skill,
which reproduced an approved 103-note US 51 profile-notes document line for line).

extract_notes(pdf, pages, region) -> [{page, x, y, sta, lines, bbox}]   coordinates in 100-dpi pixels
  region: (x0, y0, x1, y1) as page fractions, or a callable(page_no) -> such a tuple.
  Note text is picked by height, measured per page (median height of the "STA." words, 85-115%).
  Each note is anchored on a "STA." word followed by a station; lines are collected down the anchor's left edge,
  plus the structure ID line just above it ("337 B"). Notes end at a >30 px gap or where the next note starts.
"""
import re, statistics
import pymupdf

K = 100 / 72
DROP = {"NG="}
_docs = {}


def _doc(pdf):
    if pdf not in _docs:
        _docs[pdf] = pymupdf.open(pdf)
    return _docs[pdf]


def words(pdf, page):
    return [(w[0] * K, w[1] * K, w[2] * K, w[3] * K, w[4]) for w in _doc(pdf)[page - 1].get_text("words")]


def sta_val(s):
    a, b = s.split("+")
    return int(a) * 100 + float(b)


def extract_notes(pdf, pages, region=(0.07, 0.49, 0.92, 0.94)):
    res = []
    for p in pages:
        r = _doc(pdf)[p - 1].rect
        PW, PH = r.width * K, r.height * K
        fx0, fy0, fx1, fy1 = region(p) if callable(region) else region
        X0, Y0, X1, Y1 = fx0 * PW, fy0 * PH, fx1 * PW, fy1 * PH
        reg = [w for w in words(pdf, p) if Y0 < w[1] < Y1 and X0 < w[0] < X1]
        hs = [w[3] - w[1] for w in reg if w[4].startswith("STA.")]
        if not hs:
            continue
        h = statistics.median(hs)
        W = [w for w in reg if h * 0.85 < (w[3] - w[1]) < h * 1.15]
        anchors = [w for w in W if w[4].startswith("STA.") and (
            re.match(r"STA\.\d{3}\+", w[4]) or
            any(-6 < v[0] - w[2] < 25 and abs(v[1] - w[1]) < 3 and re.match(r"\d{3}\+\d", v[4]) for v in W))]
        cols = [(c[0], c[1]) for c in anchors]
        for an in anchors:
            ax, ay = an[0], an[1]

            def row(y):
                rr = sorted([w for w in W if abs(w[1] - y) < 2 and ax - 8 <= w[0]], key=lambda w: w[0])
                out, last = [], None
                for w in rr:
                    if last is not None and (w[0] - last > 75 or any(abs(w[0] - c[0]) < 3 and -40 < y - c[1] < 320
                                                                    for c in cols if c[0] > ax + 5)):
                        break
                    out.append(w)
                    last = w[2]
                return [w for w in out if w[4] not in DROP]

            starts = sorted({round(w[1]) for w in W if abs(w[0] - ax) < 8})
            seq = [y for y in starts if ay - 25 < y < ay - 5] + [y for y in starts if y >= ay - 1]
            lines, boxes, last = [], [], None
            for y in seq:
                if last is not None and y - last > 30:
                    break
                if last is not None and y - last < 5:
                    continue
                rw = row(y)
                if len(lines) >= 2 and rw and (rw[0][4].startswith("STA.") or
                                               (len(rw) == 2 and re.match(r"^\d{3}$", rw[0][4]))):
                    break
                if rw:
                    lines.append(" ".join(w[4] for w in rw))
                    boxes += rw
                    last = y
            m = re.search(r"(\d{3}\+\d\d(?:\.\d+)?)", " ".join(lines))
            if not m:
                continue
            bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
            res.append(dict(page=p, x=round(ax), y=round(ay), sta=sta_val(m[1]), lines=lines,
                            bbox=[round(v / K, 1) for v in bbox]))  # bbox in PDF points for highlighting
    side = lambda b: 0 if " LT" in " ".join(b["lines"][:3]) else 1
    res.sort(key=lambda b: (b["sta"], side(b), b["lines"][0]))
    return res
