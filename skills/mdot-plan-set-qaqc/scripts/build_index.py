#!/usr/bin/env python3
"""Index, chunk and embed a plan-set PDF for QA/QC agents.

Commands
  index  <plans.pdf> <out>                 build out/index.json, out/index.db, out/chunks/, out/images/, out/embeddings.npz
  search <out> "<query>" [--k 15] [--sheet WK-3] [--kind ocr|text|table]
                                           hybrid search (exact keyword + fuzzy n-gram + dense vectors when available)
  sheets <out>                             one line per page: pdf page, sheet ID, sheet no, type, title, read quality
  render <plans.pdf> <out> <pdf_page> [--dpi 200] [--clip x0,y0,x1,y1] [--tiles RxC]
                                           PNG(s) for visual reads; --clip is in PDF points; --tiles splits the clip/page
  words  <out> <pdf_page> [--clip x0,y0,x1,y1]
                                           every word with its box and source (text layer or OCR) for one page

Every word, vector or OCR, is stored with page coordinates so findings can be located and highlighted later.
"""
import argparse, io, json, math, os, re, sqlite3, sys, time
import pymupdf

# ---------------------------------------------------------------- sheet IDs
ID_LABELS = [("SHEET", "ID"), ("WK.", "NO."), ("WK", "NO.")]
NO_LABELS = [("SHEET", "NO."), ("SHEET", "NO")]
ID_PATTERN = re.compile(r"^([A-Z]{1,6})-?([0-9]{0,4}[A-Z]{0,3})$|^E\d+ OF \d+$|^[A-Z]\d{3}[A-Z]?$")
TYPE_BY_PREFIX = {
    "SQ": "SQS", "SQS": "SQS", "EQ": "EQ", "DI": "INDEX", "RVP": "REVISIONS",
    "WK": "WORKING", "PMD": "WORKING", "TC": "WORKING", "ECP": "WORKING", "ID": "WORKING",
    "PSP": "WORKING", "DCS": "WORKING", "PCMS": "WORKING", "TS": "TYPICAL", "GN": "NOTES",
    "VS": "VEGETATION", "CP": "SPECIAL", "ESMTC": "SPECIAL", "TSS": "SPECIAL",
}
BOILERPLATE = re.compile(r"PROJECT NO|COUNTY|FMS CON|DESIGNED BY|DETAILED BY|CHECKED BY|DATE|DIR OF STRUCT|"
                         r"DEP\. DIR|STATE BRIDGE|PRELIMINARY|NOT FOR|CONSTRUCTION$|MISSISSIPPI|DEPARTMENT|"
                         r"TRANSPORTATION|SHEET ID|SHEET NO|WK\. NO|INC\.?$|^#$", re.I)


def norm_id(s):
    s = re.sub(r"\s*-\s*", "-", s.strip().upper())
    return re.sub(r"\s+", " ", s)


def find_label(words, pair, region):
    """Lowest-right occurrence of a two-word label inside region; returns its Rect."""
    hits = []
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if a[4].upper() == pair[0] and b[4].upper() == pair[1] and abs(a[1] - b[1]) < 3:
            r = pymupdf.Rect(a[:4]) | pymupdf.Rect(b[:4])
            if region.contains(r):
                hits.append(r)
    return max(hits, key=lambda r: (r.y1, r.x1)) if hits else None


def text_below(words, label, stop_y=None):
    h = label.height
    y_max = stop_y if stop_y else label.y1 + 3 * h
    cx0, cx1 = label.x0 - label.width * 0.6, label.x1 + label.width * 0.6
    got = [w for w in words if w[1] >= label.y1 - 1 and w[3] <= y_max + 1
           and cx0 <= (w[0] + w[2]) / 2 <= cx1]
    got.sort(key=lambda w: (round(w[1] / 3), w[0]))
    return " ".join(w[4] for w in got)


def title_from_text(page, clip):
    """Title text from the text layer: whole lines in the box, split words rejoined, boilerplate removed."""
    segs = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            lb = pymupdf.Rect(ln["bbox"])
            if not clip.contains(pymupdf.Point((lb.x0 + lb.x1) / 2, (lb.y0 + lb.y1) / 2)):
                continue
            t = "".join(sp["text"] for sp in ln["spans"])
            size = max((sp["size"] for sp in ln["spans"]), default=0)
            if t.strip():
                segs.append((ln["dir"], lb, t, size))
    if not segs:
        return ""
    vertical = sum(abs(g[0][1]) > 0.9 for g in segs) >= len(segs) / 2
    # rows: same baseline (x for vertical text, y for horizontal); reading order inside a row
    def base(g):
        return (g[1].x0 + g[1].x1) / 2 if vertical else (g[1].y0 + g[1].y1) / 2
    def along(g):
        return -g[1].y1 if vertical and g[0][1] < 0 else (g[1].y0 if vertical else g[1].x0)
    segs.sort(key=base)
    rows = []
    for g in segs:
        if rows and abs(base(rows[-1][-1]) - base(g)) < 0.4 * g[3]:
            rows[-1].append(g)
        else:
            rows.append([g])
    if vertical and segs[0][0][1] > 0:
        rows.reverse()  # text reading top-to-bottom: rightmost row first
    big = max(max(g[3] for g in row) for row in rows)
    rows = [row for row in rows if max(g[3] for g in row) >= 0.6 * big]  # title-size text only
    out = []
    for row in rows:
        row.sort(key=along)
        txt = ""
        for k, g in enumerate(row):
            if k:
                prev = row[k - 1][1]
                gap = (prev.y0 - g[1].y1) if vertical else (g[1].x0 - prev.x1)
                txt += "" if gap < 0.25 * g[3] and not txt.endswith(" ") else " "
            txt += g[2].strip()
        if not BOILERPLATE.search(txt):
            out.append(txt.strip())
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def title_from_ocr(page, clip):
    """Second reader for the title: render the title box upright and OCR it (line order comes out right)."""
    _, ocr = ocr_engine()
    if not ocr:
        return ""
    pix = page.get_pixmap(dpi=200, clip=clip)
    if clip.height > clip.width * 1.5:  # vertical strip: rotate so the title reads left to right
        d = pymupdf.open()
        pg = d.new_page(width=clip.height, height=clip.width)
        pg.show_pdf_page(pg.rect, page.parent, page.number, clip=clip, rotate=-90)
        pix = pg.get_pixmap(dpi=200)
    try:
        res = ocr(pix.tobytes("png"))
    except Exception:
        return ""
    if not res:
        return ""
    hmax = max(max(p[1] for p in o[0]) - min(p[1] for p in o[0]) for o in res)
    res = [o for o in res if max(p[1] for p in o[0]) - min(p[1] for p in o[0]) >= 0.6 * hmax]
    lines = sorted(res, key=lambda o: (min(p[1] for p in o[0]), min(p[0] for p in o[0])))
    txt = " ".join(o[1] for o in lines if not BOILERPLATE.search(o[1]))
    return re.sub(r"\s+", " ", txt).strip()


def title_block(page, words):
    r = page.rect
    region = pymupdf.Rect(r.x0 + r.width * 0.75, r.y0 + r.height * 0.75, r.x1, r.y1)
    id_lab = next((l for p in ID_LABELS if (l := find_label(words, p, region))), None)
    no_lab = next((l for p in NO_LABELS if (l := find_label(words, p, region))), None)
    sid = sno = None
    how = "none"
    if id_lab:
        stop = no_lab.y0 if no_lab and no_lab.y0 > id_lab.y1 else None
        sid = norm_id(text_below(words, id_lab, stop))
        how = "label"
    if no_lab:
        sno = text_below(words, no_lab).strip() or None
    if not sid:  # fallback: last ID-looking token in the bottom-right region
        toks = [norm_id(w[4]) for w in words if region.contains(pymupdf.Rect(w[:4]))]
        cands = [t for t in toks if ID_PATTERN.match(t) and "-" in t]
        if cands:
            sid, how = cands[-1], "regex"
    # sheet title: the title box in the right strip, between the project/county boxes and the ID box
    title, title_ocr, title_clip = "", "", None
    if id_lab:
        strip_x0 = id_lab.x0 - max(id_lab.width * 2.2, r.width * 0.04)
        labels = [w for w in words if w[0] > r.width * 0.85 and w[3] < id_lab.y0 and
                  re.match(r"^(COUNTY|PROJECT|FMS|DESIGNED|DETAILED|CHECKED|DIR|DEP\.?)\b", w[4], re.I)]
        if labels:  # the title box is as wide as the label column of the title block
            strip_x0 = max(strip_x0, min(w[0] for w in labels) - 15)
        top = id_lab.y0 - r.height * 0.45
        for w in words:  # bottom edge of the PROJECT NO / COUNTY / FMS boxes, if they sit above the title
            if w[0] >= strip_x0 and w[3] < id_lab.y0 - 20 and re.match(r"^(COUNTY|PROJECT|FMS|NO\.?:?)", w[4], re.I):
                top = max(top, w[3] + 2)
        title_clip = pymupdf.Rect(strip_x0, top, r.x1, id_lab.y0 - 2)
        title = title_from_text(page, title_clip)
        title_ocr = title_from_ocr(page, title_clip)
    if not sid and page.number == 0:
        sid, how = "TITLE", "assumed_title_sheet"
    sid = sid or "UNKNOWN"
    prefix = re.split(r"[-\s\d]", sid)[0] if sid != "UNKNOWN" else "UNKNOWN"
    if sid == "TITLE":
        stype = "TITLE"
    elif re.match(r"^E\d+ OF \d+$", sid):
        stype = "ELECTRICAL"
    elif re.match(r"^[A-Z]\d{3}[A-Z]?$", sid):
        stype = "LIGHTING/BRIDGE"
    else:
        stype = TYPE_BY_PREFIX.get(prefix, "OTHER" if sid != "UNKNOWN" else "UNKNOWN")
    return dict(sheet_id=sid, sheet_no=sno, id_source=how, prefix=prefix, type=stype, title=title,
                title_ocr=title_ocr, title_box=[round(v, 1) for v in title_clip] if title_clip else None)


# ---------------------------------------------------------------- OCR
_OCR = None


def _probe_png():
    """Tiny test image so a half-installed OCR engine fails here, not silently per page."""
    d = pymupdf.open()
    p = d.new_page(width=200, height=60)
    p.insert_text((10, 40), "TEST 123", fontsize=24)
    return p.get_pixmap(dpi=144).tobytes("png")


def ocr_engine():
    """RapidOCR (pip-only) first, Tesseract second, else None (agents fall back to visual reads)."""
    global _OCR
    if _OCR is not None:
        return _OCR
    try:
        from rapidocr import RapidOCR
        eng = RapidOCR()

        def run(png_bytes):
            res = eng(png_bytes)
            out = []
            if hasattr(res, "boxes") and res.boxes is not None:
                for box, txt, sc in zip(res.boxes, res.txts, res.scores):
                    out.append((box, txt, float(sc)))
            return out
        run(_probe_png())
        _OCR = ("rapidocr", run)
        return _OCR
    except Exception:
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR
        eng = RapidOCR()

        def run(png_bytes):
            res, _ = eng(png_bytes)
            return [(b, t, float(s)) for b, t, s in (res or [])]
        run(_probe_png())
        _OCR = ("rapidocr_onnxruntime", run)
        return _OCR
    except Exception:
        pass
    try:
        import pytesseract
        from PIL import Image
        pytesseract.get_tesseract_version()

        def run(png_bytes):
            d = pytesseract.image_to_data(Image.open(io.BytesIO(png_bytes)), config="--psm 11",
                                          output_type=pytesseract.Output.DICT)
            out = []
            for i, t in enumerate(d["text"]):
                if t.strip() and float(d["conf"][i]) > 0:
                    x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
                    out.append(([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], t, float(d["conf"][i]) / 100))
            return out
        _OCR = ("tesseract", run)
        return _OCR
    except Exception:
        _OCR = ("none", None)
        return _OCR


def pix_png(pix, min_width=1600):
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.n - pix.alpha >= 4 or pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    scale = 1
    if pix.width < min_width:  # small images OCR better upscaled
        scale = 2
        pix = pymupdf.Pixmap(pix, pix.width * 2, pix.height * 2, None)
    return pix.tobytes("png"), scale


def ocr_to_page(results, to_page, scale):
    """OCR boxes (image pixels) -> page-space word records."""
    out = []
    for box, txt, sc in results:
        pts = [to_page(x / scale, y / scale) for x, y in box]
        xs, ys = [p.x for p in pts], [p.y for p in pts]
        out.append((min(xs), min(ys), max(xs), max(ys), txt.strip(), sc))
    return [o for o in out if o[4]]


def raster_clusters(page, min_frac=0.02):
    """Union rectangles of touching image placements, keeping clusters that cover >= min_frac of the page."""
    pr = page.rect
    rects = []
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & pr
        if not r.is_empty and info["width"] >= 8 and info["height"] >= 8:
            rects.append(r)
    clusters = []
    for r in rects:
        g = pymupdf.Rect(r)
        merged = True
        while merged:
            merged = False
            for c in clusters:
                if (c + (-3, -3, 3, 3)).intersects(g):
                    g |= c
                    clusters.remove(c)
                    merged = True
                    break
        clusters.append(g)
    return [c for c in clusters if c.get_area() >= pr.get_area() * min_frac]


# ---------------------------------------------------------------- chunking helpers
def rows_from_boxes(items, ytol_ratio=0.55):
    """Group word/line boxes into visual rows (for OCR tables) -> list of (y, [items sorted by x])."""
    items = sorted(items, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows = []
    for it in items:
        cy, h = (it[1] + it[3]) / 2, max(it[3] - it[1], 1)
        if rows and abs(rows[-1][0] - cy) < h * ytol_ratio:
            rows[-1][1].append(it)
            rows[-1][0] = (rows[-1][0] * (len(rows[-1][1]) - 1) + cy) / len(rows[-1][1])
        else:
            rows.append([cy, [it]])
    return [(y, sorted(r, key=lambda w: w[0])) for y, r in rows]


def table_md(rows, sep=" | "):
    """Rows as pipe-separated text. OCR words under 0.80 confidence are tagged with a question mark marker."""
    def tok(w):
        return w[4] + ("⟨?⟩" if len(w) > 5 and w[5] < 0.80 else "")
    return "\n".join(sep.join(tok(w) for w in r) for _, r in rows)


def split_blank_bands(page, rect, dpi=60):
    """Split a raster region where a fully blank vertical band separates two tables.
    Column gaps inside a ruled table contain ink (the ruling line), so tables stay whole."""
    import numpy as np
    pix = page.get_pixmap(dpi=dpi, clip=rect, colorspace=pymupdf.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width]
    ink = (a < 150).mean(axis=0)
    blank = ink < 0.002
    W = pix.width
    min_run, cuts, k = max(int(W * 0.012), 4), [], 0
    inked = np.where(~blank)[0]
    if len(inked) == 0:
        return [rect]
    lo, hi = inked[0], inked[-1]
    k = lo
    while k <= hi:
        if blank[k]:
            j = k
            while j <= hi and blank[j]:
                j += 1
            if j - k >= min_run:
                cuts.append((k + j) / 2)
            k = j
        else:
            k += 1
    xs = [rect.x0] + [rect.x0 + c / W * rect.width for c in cuts] + [rect.x1]
    parts = [pymupdf.Rect(xs[i], rect.y0, xs[i + 1], rect.y1) for i in range(len(xs) - 1)]
    return [p for p in parts if p.width > rect.width * 0.04] or [rect]


# ---------------------------------------------------------------- embeddings
def char_ngrams(text, n=3, dim=2 ** 18):
    v = {}
    t = f" {re.sub(r'\s+', ' ', text.lower())} "
    for i in range(len(t) - n + 1):
        h = hash(t[i:i + n]) % dim
        v[h] = v.get(h, 0) + 1
    return v


def build_vectors(chunks, out):
    import numpy as np
    texts = [c["text"][:1500] for c in chunks]  # bge-small reads ~512 tokens anyway
    meta = {"dense_model": None}
    try:
        from fastembed import TextEmbedding
        cache = os.environ.get("FASTEMBED_CACHE", os.path.join(out, "..", "models"))
        model = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=cache)
        dense = np.array(list(model.embed(texts, batch_size=16)), dtype="float32")
        dense /= np.linalg.norm(dense, axis=1, keepdims=True) + 1e-9
        np.save(os.path.join(out, "dense.npy"), dense)
        meta["dense_model"] = "BAAI/bge-small-en-v1.5"
    except Exception as e:
        meta["dense_error"] = f"{type(e).__name__}: {e}"[:200]
    return meta


# ---------------------------------------------------------------- index
def cmd_index(pdf, out, ocr_all=False, only=None, dense=True):
    t0 = time.time()
    for d in ("chunks", "images"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    os.environ.setdefault("PYTHONHASHSEED", "0")
    doc = pymupdf.open(pdf)
    eng_name, ocr = ocr_engine()
    db_path = os.path.join(out, "index.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    db = sqlite3.connect(db_path)
    db.executescript("""
      CREATE TABLE words(page INT, x0 REAL, y0 REAL, x1 REAL, y1 REAL, text TEXT, source TEXT, conf REAL,
                         block INT, line INT);
      CREATE INDEX wp ON words(page);
      CREATE TABLE chunks(id INTEGER PRIMARY KEY, page INT, sheet_id TEXT, kind TEXT,
                          x0 REAL, y0 REAL, x1 REAL, y1 REAL, text TEXT);
      CREATE VIRTUAL TABLE fts USING fts5(text, sheet_id UNINDEXED, page UNINDEXED, kind UNINDEXED,
                          tokenize="unicode61 tokenchars '-.#/'");
    """)
    pages, chunks = [], []

    def add_chunk(page_no, sid, kind, rect, text):
        text = text.strip()
        if not text:
            return
        cid = len(chunks) + 1
        chunks.append(dict(id=cid, page=page_no, sheet_id=sid, kind=kind, rect=list(rect), text=text))
        db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?)", (cid, page_no, sid, kind, *rect, text))
        db.execute("INSERT INTO fts(rowid, text, sheet_id, page, kind) VALUES (?,?,?,?,?)",
                   (cid, text, sid, page_no, kind))

    for pno, page in enumerate(doc, start=1):
        if only and pno not in only:
            continue
        pr = page.rect
        words = page.get_text("words", sort=True)
        tb = title_block(page, words)
        sid = tb["sheet_id"]
        n_draw = len(page.get_cdrawings()) if len(words) < 80 else -1  # only needed for the SHX check
        rec = dict(pdf_page=pno, **tb, rotation=page.rotation, words_text=len(words),
                   drawings=n_draw, ocr_regions=[], ocr_words=0, ocr_low_conf=0, flags=[])
        for w in words:
            db.execute("INSERT INTO words VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (pno, *w[:4], w[4], "text", 1.0, w[5], w[6]))

        # ---- raster regions. CAD exports often slice one pasted table into several touching image tiles,
        # so tiles are stitched into clusters and each cluster is rendered and OCR'd as one picture.
        md_parts = []
        clusters = raster_clusters(page)
        scanned = len(words) < 40 and not clusters
        if scanned:
            rec["flags"].append("SCANNED_PAGE")
            clusters = [pr]
        elif ocr_all and not clusters:
            clusters = [pr]
        clusters = [p for c in clusters for p in split_blank_bands(page, c)]
        targets = []
        for k, rect in enumerate(clusters):
            dpi = min(300, int(72 * math.sqrt(24e6 / max(rect.get_area(), 1))))
            pix = page.get_pixmap(dpi=dpi, clip=rect)
            s_ = 72 / dpi
            targets.append((f"r{k}", pix, (lambda x, y, r=rect, s_=s_: pymupdf.Point(r.x0 + x * s_, r.y0 + y * s_)), rect))
        for tag, pix, to_page, bbox in targets:
            png, scale = pix_png(pix, min_width=0)
            img_path = os.path.join("images", f"p{pno:04d}_{tag}.png")
            with open(os.path.join(out, img_path), "wb") as f:
                f.write(png)
            region = dict(tag=tag, bbox=[round(v, 1) for v in bbox], image=img_path, engine=eng_name)
            dpis = [i["width"] / (pymupdf.Rect(i["bbox"]).width / 72) for i in page.get_image_info()
                    if pymupdf.Rect(i["bbox"]).intersects(bbox) and pymupdf.Rect(i["bbox"]).width > 20]
            if dpis:
                region["source_dpi"] = round(min(dpis))
                if min(dpis) < 150 and "LOW_RES_RASTER" not in rec["flags"]:
                    rec["flags"].append("LOW_RES_RASTER")  # OCR unreliable: transcribe visually, OCR is a cross-check
            if ocr:
                try:
                    ow = ocr_to_page(ocr(png), to_page, scale)
                except Exception as e:
                    ow, region["error"] = [], str(e)[:200]
                low = sum(1 for o in ow if o[5] < 0.80)
                region.update(words=len(ow), low_conf=low)
                rec["ocr_words"] += len(ow)
                rec["ocr_low_conf"] += low
                for o in ow:
                    db.execute("INSERT INTO words VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (pno, *o[:4], o[4], "ocr", o[5], -1, -1))
                for ci, col in enumerate([ow]):
                    rows = rows_from_boxes(col)
                    md = table_md(rows)
                    md_parts.append(f"### OCR region {tag} box={[round(v) for v in bbox]} (engine {eng_name}; "
                                    f"verify against {img_path})\n{md}")
                    # chunk OCR tables by ~25 rows, each with its own box for locating
                    for s in range(0, len(rows), 25):
                        grp = rows[s:s + 25]
                        ws = [w for _, r in grp for w in r]
                        rect = (min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws))
                        add_chunk(pno, sid, "ocr", rect, table_md(grp))
            else:
                region["note"] = "no OCR engine: read this image visually"
                rec["flags"].append("RASTER_NOT_OCRED")
            rec["ocr_regions"].append(region)

        # ---- vector text: long note blocks are their own chunk; short CAD labels merge by page tile (4 x 3)
        blocks = page.get_text("blocks", sort=True)
        tiles = {}
        for b in blocks:
            if b[6] != 0 or not b[4].strip():
                continue
            if len(b[4]) >= 150:
                add_chunk(pno, sid, "text", b[:4], b[4])
            else:
                key = (min(int((b[0] + b[2]) / 2 / pr.width * 4), 3), min(int((b[1] + b[3]) / 2 / pr.height * 3), 2))
                tiles.setdefault(key, []).append(b)
        for key, bl in tiles.items():
            rect = (min(b[0] for b in bl), min(b[1] for b in bl), max(b[2] for b in bl), max(b[3] for b in bl))
            add_chunk(pno, sid, "text", rect, " ; ".join(re.sub(r"\s+", " ", b[4]).strip() for b in bl))
        # ---- vector tables (only where quantities live, and not on very heavy pages)
        tables_md = []
        page_text = " ".join(w[4] for w in words)
        if len(page.get_images()) < 50 and re.search(r"TOTAL|QUANTIT|REQUIRED|SUMMARY|ITEMS|RECAP|SCHEDULE", page_text, re.I):
            try:
                for ti, t in enumerate(page.find_tables().tables):
                    rows = t.extract()
                    if len(rows) < 2:
                        continue
                    md = "\n".join(" | ".join((c or "").replace("\n", " ") for c in row) for row in rows)
                    toks = md.split()
                    if not toks or sum(len(t) == 1 for t in toks) / len(toks) > 0.35:
                        continue  # CAD linework mistaken for a table: letters scattered one per cell
                    tables_md.append(f"### Vector table {ti + 1} bbox={[round(v) for v in t.bbox]}\n{md}")
                    add_chunk(pno, sid, "table", t.bbox, md)
            except Exception as e:
                rec["flags"].append(f"TABLE_ERROR:{str(e)[:60]}")

        # ---- quality flags
        if 0 <= n_draw and n_draw > 3000 and len(words) < 60 and not big_imgs:
            rec["flags"].append("LOW_TEXT_DENSITY_POSSIBLE_SHX_TEXT")  # text drawn as linework: read visually
        if rec["ocr_words"] and rec["ocr_low_conf"] / max(rec["ocr_words"], 1) > 0.10:
            rec["flags"].append("OCR_LOW_CONFIDENCE")
        if sid == "UNKNOWN":
            rec["flags"].append("SHEET_ID_UNKNOWN")

        chunk_path = os.path.join("chunks", f"p{pno:04d}_{re.sub(r'[^A-Za-z0-9-]+', '_', sid)}.md")
        rec["chunk"] = chunk_path
        head = (f"# PDF page {pno} | Sheet ID {sid} | Sheet No {tb['sheet_no']} | Type {tb['type']}\n"
                f"Title: {tb['title']}\nFlags: {', '.join(rec['flags']) or 'none'}\n")
        body = "\n\n".join(md_parts + tables_md)
        text_layer = "\n".join(b[4].strip() for b in blocks if b[6] == 0 and b[4].strip())
        with open(os.path.join(out, chunk_path), "w") as f:
            f.write(head + ("\n## Raster/table content\n" + body if body else "") + "\n\n## Text layer\n" + text_layer)
        pages.append(rec)
        print(f"p{pno:03d} {sid:<12} {tb['type']:<16} words={len(words):<5} ocr={rec['ocr_words']:<5} "
              f"{' '.join(rec['flags'])}", file=sys.stderr)

    db.commit()
    db.close()
    ids = {}
    for p in pages:
        ids.setdefault(p["sheet_id"], []).append(p["pdf_page"])
    summary = dict(
        pdf=os.path.basename(pdf), pages=len(pages), ocr_engine=eng_name, dense_model="pending",
        seconds=round(time.time() - t0, 1), chunks=len(chunks),
        unknown_ids=[p["pdf_page"] for p in pages if p["sheet_id"] == "UNKNOWN"],
        duplicate_ids={k: v for k, v in ids.items() if len(v) > 1 and k != "UNKNOWN"},
        raster_pages=[p["pdf_page"] for p in pages if p["ocr_regions"]],
        flagged_pages={p["pdf_page"]: p["flags"] for p in pages if p["flags"]},
    )

    def write():
        with open(os.path.join(out, "index.json"), "w") as f:
            json.dump(dict(summary=summary, pages=pages), f, indent=1)
    write()  # usable by agents now; dense vectors are an add-on
    vec_meta = build_vectors(chunks, out) if dense else {"dense_model": None}
    summary.update(vec_meta)
    summary["seconds"] = round(time.time() - t0, 1)
    write()
    print(json.dumps(summary, indent=1))


# ---------------------------------------------------------------- search
def fts_query(q):
    terms = re.findall(r'[A-Za-z0-9][A-Za-z0-9.#/-]*', q)
    return " OR ".join('"' + t.replace('"', "") + '"' for t in terms)


def cmd_search(out, q, k=15, sheet=None, kind=None):
    import numpy as np
    db = sqlite3.connect(os.path.join(out, "index.db"))
    rows = db.execute("SELECT id, page, sheet_id, kind, x0, y0, x1, y1, text FROM chunks").fetchall()
    keep = [r for r in rows if (not sheet or r[2].upper() == sheet.upper()) and (not kind or r[3] == kind)]
    keep_ids = {r[0] for r in keep}
    ranks = []
    # 0) exact phrase, weighted double: the strongest signal when the user quotes a table title
    terms = re.findall(r'[A-Za-z0-9][A-Za-z0-9.#/-]*', q)
    if len(terms) > 1:
        phrase = '"' + " ".join(t.replace('"', "") for t in terms) + '"'
        hits = [h[0] for h in db.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 100", (phrase,))]
        ph = [h for h in hits if h in keep_ids]
        ranks += [ph, ph]
    # 1) exact keyword (BM25)
    fq = fts_query(q)
    if fq:
        hits = [h[0] for h in db.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 200", (fq,))]
        ranks.append([h for h in hits if h in keep_ids])
    # 2) fuzzy character n-grams (tolerates OCR errors and spacing like "DI- 1")
    qv = char_ngrams(q)
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1
    sc = []
    for r in keep:
        cv = char_ngrams(r[8][:4000])
        dot = sum(v * cv.get(h, 0) for h, v in qv.items())
        sc.append((dot / (qn * (math.sqrt(sum(v * v for v in cv.values())) or 1)), r[0]))
    ranks.append([i for s, i in sorted(sc, reverse=True)[:200] if s > 0.05])
    # 3) dense vectors when the index has them
    dpath = os.path.join(out, "dense.npy")
    if os.path.exists(dpath):
        try:
            from fastembed import TextEmbedding
            cache = os.environ.get("FASTEMBED_CACHE", os.path.join(out, "..", "models"))
            m = TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=cache)
            qe = np.array(list(m.embed([q]))[0], dtype="float32")
            qe /= np.linalg.norm(qe) + 1e-9
            dense = np.load(dpath)
            sims = dense @ qe
            order = [int(i) + 1 for i in np.argsort(-sims)[:200]]
            ranks.append([i for i in order if i in keep_ids])
        except Exception:
            pass
    fused = {}
    for rk in ranks:  # reciprocal rank fusion
        for pos, cid in enumerate(rk):
            fused[cid] = fused.get(cid, 0) + 1 / (60 + pos)
    by_id = {r[0]: r for r in keep}
    for cid, s in sorted(fused.items(), key=lambda x: -x[1])[:k]:
        r = by_id[cid]
        snippet = re.sub(r"\s+", " ", r[8])[:220]
        print(f"{r[2]}\tpdf p.{r[1]}\t{r[3]}\tbox={[round(v) for v in r[4:8]]}\t{snippet}")


def cmd_sheets(out):
    idx = json.load(open(os.path.join(out, "index.json")))
    for p in idx["pages"]:
        q = f"ocr={p['ocr_words']}" if p["ocr_regions"] else ""
        print(f"p{p['pdf_page']:03d}\t{p['sheet_id']}\tno={p['sheet_no']}\t{p['type']}\t{p['title'][:70]}\t{q}\t{' '.join(p['flags'])}")


def parse_clip(s):
    return pymupdf.Rect([float(v) for v in s.split(",")]) if s else None


def cmd_render(pdf, out, pno, dpi=200, clip=None, tiles=None):
    os.makedirs(os.path.join(out, "png"), exist_ok=True)
    page = pymupdf.open(pdf)[int(pno) - 1]
    area = parse_clip(clip) or page.rect
    rws, cls = (int(v) for v in tiles.lower().split("x")) if tiles else (1, 1)
    for i in range(rws):
        for j in range(cls):
            w, h = area.width / cls, area.height / rws
            pad = 0.04 * min(w, h) if tiles else 0  # small overlap so nothing is cut at a tile edge
            c = pymupdf.Rect(area.x0 + j * w - pad, area.y0 + i * h - pad,
                             area.x0 + (j + 1) * w + pad, area.y0 + (i + 1) * h + pad) & page.rect
            name = f"p{int(pno):04d}" + (f"_c{int(c.x0)}-{int(c.y0)}" if (clip or tiles) else "") + f"_{dpi}dpi.png"
            path = os.path.join(out, "png", name)
            page.get_pixmap(dpi=int(dpi), clip=c).save(path)
            print(f"{path}\tclip={[round(v, 1) for v in c]}")


def cmd_words(out, pno, clip=None):
    db = sqlite3.connect(os.path.join(out, "index.db"))
    c = parse_clip(clip)
    for r in db.execute("SELECT x0,y0,x1,y1,text,source,conf FROM words WHERE page=? ORDER BY y0, x0", (int(pno),)):
        if c and not c.intersects(pymupdf.Rect(r[:4])):
            continue
        print(f"{r[0]:.1f},{r[1]:.1f},{r[2]:.1f},{r[3]:.1f}\t{r[5]}\t{r[6]:.2f}\t{r[4]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("index"); a.add_argument("pdf"); a.add_argument("out"); a.add_argument("--ocr-all", action="store_true")
    a.add_argument("--pages", help="test subset, e.g. 2-14,20"); a.add_argument("--no-dense", action="store_true")
    a = sp.add_parser("search"); a.add_argument("out"); a.add_argument("query"); a.add_argument("--k", type=int, default=15)
    a.add_argument("--sheet"); a.add_argument("--kind")
    a = sp.add_parser("sheets"); a.add_argument("out")
    a = sp.add_parser("render"); a.add_argument("pdf"); a.add_argument("out"); a.add_argument("page")
    a.add_argument("--dpi", type=int, default=200); a.add_argument("--clip"); a.add_argument("--tiles")
    a = sp.add_parser("words"); a.add_argument("out"); a.add_argument("page"); a.add_argument("--clip")
    x = ap.parse_args()
    if x.cmd == "index":
        only = None
        if x.pages:
            only = set()
            for part in x.pages.split(","):
                lo, _, hi = part.partition("-")
                only.update(range(int(lo), int(hi or lo) + 1))
        cmd_index(x.pdf, x.out, x.ocr_all, only, not x.no_dense)
    elif x.cmd == "search":
        cmd_search(x.out, x.query, x.k, x.sheet, x.kind)
    elif x.cmd == "sheets":
        cmd_sheets(x.out)
    elif x.cmd == "render":
        cmd_render(x.pdf, x.out, x.page, x.dpi, x.clip, x.tiles)
    elif x.cmd == "words":
        cmd_words(x.out, x.page, x.clip)
