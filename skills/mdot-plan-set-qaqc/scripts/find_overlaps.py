#!/usr/bin/env python3
"""Find text that really overlaps other text in profile views (WK sheets by default), by testing actual ink.

  find_overlaps.py <plans.pdf> <index_dir> <out_dir> [--prefixes WK] [--region profile|plan|all]
                   [--pages 15,17] [--min-px 6] [--tiles 2x4]

Why ink and not font boxes
  OpenRoads/MicroStation sheets draw every letter as a filled shape and lay an INVISIBLE text copy on top for
  searching. The invisible copy has odd per-letter sizes, so any test based on font size reports overlaps that are
  not there. This tool:
   1. Finds each profile grid (elevation labels printed on both edges at the same height).
   2. Builds labels: on vector-text sheets, each filled letter shape is assigned to the invisible text line it sits
      under; on sheets with real visible text, the text characters are used directly.
   3. Candidate pairs are labels whose letter boxes touch. Each pair is then redrawn in isolation (label A alone,
      label B alone, at 600 dpi) and counted as an overlap only if at least --min-px pixels carry ink from BOTH.
      Labels that merely sit close together are not reported.
  Text overlapping linework (grade lines, leaders) and labels with no text copy are not tested: review the tiles.
Output: <out>/overlap_candidates.json (confirmed overlaps with shared-ink area and a crop for each), region
previews in <out>/regions/, visual-review tiles in <out>/tiles/.
"""
import argparse, json, os, re, sys
import numpy as np
import pymupdf

NUM = re.compile(r"^\d{2,5}(\.\d+)?$")
DPI = 600


# ------------------------------------------------------------------ profile grid detection
def profile_regions(page):
    pr = page.rect
    nums = [w for w in page.get_text("words") if NUM.match(w[4])]
    by_val = {}
    for w in nums:
        by_val.setdefault(w[4], []).append(w)
    pairs = []
    for v, ws in by_val.items():
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                a, b = ws[i], ws[j]
                cya, cyb = (a[1] + a[3]) / 2, (b[1] + b[3]) / 2
                if abs(cya - cyb) < 4 and abs(a[0] - b[0]) > pr.width * 0.45:
                    l, r = (a, b) if a[0] < b[0] else (b, a)
                    pairs.append((float(v), (cya + cyb) / 2, l, r))
    if len(pairs) < 3:
        return []
    pairs.sort(key=lambda p: p[1])
    gaps = [pairs[k + 1][1] - pairs[k][1] for k in range(len(pairs) - 1)]
    med = sorted(gaps)[len(gaps) // 2] if gaps else 0
    groups, cur = [], [pairs[0]]
    for k, p in enumerate(pairs[1:]):
        if gaps[k] > 3 * med + 5:
            groups.append(cur)
            cur = []
        cur.append(p)
    groups.append(cur)
    regions = []
    for g in groups:
        vals = [p[0] for p in g]
        if len(g) < 3 or not (all(vals[k] > vals[k + 1] for k in range(len(vals) - 1)) or
                              all(vals[k] < vals[k + 1] for k in range(len(vals) - 1))):
            continue
        x0, x1 = min(p[2][0] for p in g), max(p[3][2] for p in g)
        y0 = min(p[2][1] for p in g) - pr.height * 0.045
        y1 = max(p[2][3] for p in g) + pr.height * 0.10
        regions.append(pymupdf.Rect(x0, max(y0, pr.y0), x1, min(y1, pr.y1 - pr.height * 0.012)))
    return regions


# ------------------------------------------------------------------ labels
def text_lines(page, area):
    """Text lines (visible or invisible) with their character boxes."""
    lines = []
    for b in page.get_text("rawdict", clip=area)["blocks"]:
        for ln in b.get("lines", []):
            chars = [c for sp in ln["spans"] for c in sp["chars"] if c["c"].strip()]
            text = "".join(c["c"] for sp in ln["spans"] for c in sp["chars"]).strip()
            if chars and text:
                lines.append(dict(text=text, chars=[pymupdf.Rect(c["bbox"]) for c in chars]))
    return lines


def text_is_invisible(page):
    tt = page.get_texttrace()
    return bool(tt) and sum(1 for s in tt if s["type"] == 3) > 0.8 * len(tt)


def vector_labels(page, area, lines):
    """Assign each filled letter shape to the invisible text line it belongs to."""
    if not lines:
        return []
    G = 20.0   # grid cell (pt) so each letter shape is only compared with nearby characters
    grid = {}
    for li, ln in enumerate(lines):
        for r in ln["chars"]:
            for gx in range(int((r.x0 - 1) // G), int((r.x1 + 1) // G) + 1):
                for gy in range(int((r.y0 - 1) // G), int((r.y1 + 1) // G) + 1):
                    grid.setdefault((gx, gy), []).append((li, r))
    glyphs = {}
    for d in page.get_drawings():
        if d.get("type") not in ("f", "fs") or d.get("fill") is None:
            continue
        r = d["rect"]
        if r.is_empty or not area.intersects(r) or max(r.width, r.height) > 40:
            continue
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        best, bd = None, 1e9
        for li, cr in grid.get((int(c.x // G), int(c.y // G)), ()):
            if (cr + (-1, -1, 1, 1)).contains(c):
                dist = abs(pymupdf.Point((cr.x0 + cr.x1) / 2, (cr.y0 + cr.y1) / 2) - c)
                if dist < bd:
                    best, bd = li, dist
        if best is not None:
            glyphs.setdefault(best, []).append(d)
    labels = []
    for li, ds in glyphs.items():
        rect = pymupdf.Rect(ds[0]["rect"])
        for d in ds[1:]:
            rect |= d["rect"]
        labels.append(dict(text=lines[li]["text"], rect=rect, boxes=[pymupdf.Rect(d["rect"]) for d in ds], paths=ds))
    return labels


def visible_labels(lines):
    out = []
    for ln in lines:
        rect = pymupdf.Rect(ln["chars"][0])
        for r in ln["chars"][1:]:
            rect |= r
        out.append(dict(text=ln["text"], rect=rect, boxes=ln["chars"], paths=None))
    return out


# ------------------------------------------------------------------ ink rendering
def draw_paths(paths, clip):
    """Render only these filled paths (black on white) inside clip -> boolean ink mask."""
    t = pymupdf.open()
    pg = t.new_page(width=clip.x1 + 5, height=clip.y1 + 5)
    sh = pg.new_shape()
    for p in paths:
        for it in p["items"]:
            if it[0] == "l":
                sh.draw_line(it[1], it[2])
            elif it[0] == "c":
                sh.draw_bezier(it[1], it[2], it[3], it[4])
            elif it[0] == "re":
                sh.draw_rect(it[1])
            elif it[0] == "qu":
                sh.draw_quad(it[1])
        sh.finish(fill=(0, 0, 0), color=None, even_odd=p.get("even_odd", False), closePath=p.get("closePath", True))
    sh.commit()
    pix = pg.get_pixmap(dpi=DPI, clip=clip, colorspace=pymupdf.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    return a < 128


def render_without(doc, pno, remove_rects, clip):
    t = pymupdf.open()
    t.insert_pdf(doc, from_page=pno - 1, to_page=pno - 1)
    pg = t[0]
    for r in remove_rects:  # tiny box at each character centre removes that character only
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        pg.add_redact_annot(pymupdf.Rect(c.x - 0.3, c.y - 0.3, c.x + 0.3, c.y + 0.3))
    if remove_rects:
        pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                            text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    pix = pg.get_pixmap(dpi=DPI, clip=clip, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width].astype(int)


def shared_ink(doc, pno, A, B, clip):
    if A["paths"] is not None:
        return int((draw_paths(A["paths"], clip) & draw_paths(B["paths"], clip)).sum())
    # visible text: ink of A = (page without A and B) vs (page without B)
    none = render_without(doc, pno, A["boxes"] + B["boxes"], clip)
    only_a = render_without(doc, pno, B["boxes"], clip)
    only_b = render_without(doc, pno, A["boxes"], clip)
    return int((((none - only_a) > 60) & ((none - only_b) > 60)).sum())


def touching_pairs(labels):
    pairs = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            A, B = labels[i], labels[j]
            if not (A["rect"] + (-1, -1, 1, 1)).intersects(B["rect"]):
                continue
            if A["text"] == B["text"] and abs(A["rect"].x0 - B["rect"].x0) < 1 and abs(A["rect"].y0 - B["rect"].y0) < 1:
                continue  # CAD overprint of the same string
            hits = [(a + (-0.5, -0.5, 0.5, 0.5)) & b for a in A["boxes"] for b in B["boxes"]
                    if (a + (-0.5, -0.5, 0.5, 0.5)).intersects(b)]
            if hits:
                u = pymupdf.Rect(hits[0])
                for h in hits[1:]:
                    u |= h
                pairs.append((A, B, u))
    return pairs


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("index"); ap.add_argument("out")
    ap.add_argument("--prefixes", default="WK")
    ap.add_argument("--region", default="profile", choices=["profile", "plan", "all"])
    ap.add_argument("--pages")
    ap.add_argument("--min-px", type=int, default=6, help="shared ink pixels at 600 dpi to count as overlap")
    ap.add_argument("--tiles", default="2x4")
    a = ap.parse_args()
    for d in ("overlaps", "regions", "tiles"):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    idx = json.load(open(os.path.join(a.index, "index.json")))
    prefixes = {p.strip().upper() for p in a.prefixes.split(",")}
    want = {int(p) for p in a.pages.split(",")} if a.pages else None
    doc = pymupdf.open(a.pdf)
    cands, report, tiles, checked = [], [], [], []
    for rec in idx["pages"]:
        pno = rec["pdf_page"]
        if (want and pno not in want) or (not want and rec["prefix"].upper() not in prefixes):
            continue
        page = doc[pno - 1]
        profiles = profile_regions(page)
        pr = page.rect
        if a.region == "profile":
            areas = [("profile", r) for r in profiles]
        elif a.region == "plan":
            top = min((r.y0 for r in profiles), default=pr.y1)
            areas = [("plan", pymupdf.Rect(pr.x0, pr.y0, pr.width * 0.92, top))]
        else:
            areas = [("sheet", pymupdf.Rect(pr.x0, pr.y0, pr.width * 0.92, pr.y1))]
        tmp = pymupdf.open()
        tmp.insert_pdf(doc, from_page=pno - 1, to_page=pno - 1)
        for _, r in areas:
            tmp[0].draw_rect(r, color=(1, 0, 0), width=4)
        prev = os.path.join(a.out, "regions", f"p{pno:04d}_{rec['sheet_id']}.png")
        tmp[0].get_pixmap(dpi=40).save(prev)
        vector_mode = text_is_invisible(page)
        report.append(dict(pdf_page=pno, sheet_id=rec["sheet_id"], areas=[(n, [round(v, 1) for v in r]) for n, r in areas],
                           text_mode="vector letters + invisible text" if vector_mode else "visible text",
                           preview=prev, note=None if areas else "no profile grid detected: review visually"))
        for name, area in areas:
            lines = text_lines(page, area)
            labels = vector_labels(page, area, lines) if vector_mode else visible_labels(lines)
            for A, B, hit in touching_pairs(labels):
                clip = (hit + (-3, -3, 3, 3)) & pr
                px = shared_ink(doc, pno, A, B, clip)
                checked.append(dict(pdf_page=pno, text_a=A["text"], text_b=B["text"], shared_ink_px=px))
                if px < a.min_px:
                    continue
                ctx = A["rect"] | B["rect"]
                crop = (ctx + (-20, -20, 20, 20)) & pr
                cid = f"OVL-p{pno}-{len(cands) + 1:03d}"
                png = os.path.join(a.out, "overlaps", f"{cid}.png")
                page.get_pixmap(dpi=300, clip=crop).save(png)
                cands.append(dict(id=cid, kind="overlap", pdf_page=pno, sheet_id=rec["sheet_id"], area=name,
                                  text_a=A["text"], text_b=B["text"], shared_ink_px=px,
                                  shared_ink_pt2=round(px * (72 / DPI) ** 2, 3),
                                  overlap_rect=[round(v, 1) for v in hit], context_rect=[round(v, 1) for v in ctx],
                                  crop=png))
            tr, tc = (int(v) for v in a.tiles.lower().split("x"))
            for i in range(tr):
                for j in range(tc):
                    w, h = area.width / tc, area.height / tr
                    pad = 0.05 * min(w, h)
                    c = pymupdf.Rect(area.x0 + j * w - pad, area.y0 + i * h - pad,
                                     area.x0 + (j + 1) * w + pad, area.y0 + (i + 1) * h + pad) & pr
                    tp = os.path.join(a.out, "tiles", f"p{pno:04d}_{name}_r{i + 1}c{j + 1}.png")
                    page.get_pixmap(dpi=200, clip=c).save(tp)
                    tiles.append(dict(pdf_page=pno, sheet_id=rec["sheet_id"], tile=tp, clip=[round(v, 1) for v in c]))
        print(f"p{pno:03d} {rec['sheet_id']:<8} areas={len(areas)} mode={'vector' if vector_mode else 'text'} "
              f"overlaps={sum(1 for c in cands if c['pdf_page'] == pno)}", file=sys.stderr)
    cands.sort(key=lambda c: (c["pdf_page"], -c["shared_ink_px"]))
    json.dump(dict(regions=report, candidates=cands, tiles=tiles, pairs_tested=checked),
              open(os.path.join(a.out, "overlap_candidates.json"), "w"), indent=1)
    print(json.dumps(dict(sheets=len(report), pairs_tested=len(checked), overlaps=len(cands), tiles=len(tiles),
                          no_profile_found=[r["sheet_id"] for r in report if not r["areas"]]), indent=1))


if __name__ == "__main__":
    main()
