"""Shared helpers: findings file I/O and locating text on a page (text layer first, then OCR words)."""
import json, os, re, sqlite3

SEVERITIES = ("high", "medium", "low")
TASKS = {
    "index": "Index Check",
    "spelling": "Spelling",
    "overlap": "Overlapping Text",
    "quantity": "Quantities",
    "notematch": "Note Match",
    "color": "Print Color",
}


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def squash(s):
    return re.sub(r"\s+", "", s or "").upper()


def locate_text(page, index_db, text, near=None):
    """Return page rects for `text` on this page: exact text-layer hits first, then OCR lines that contain it.
    `near` (a Rect) prefers the hit closest to it when there are several."""
    import pymupdf
    hits = [pymupdf.Rect(r) for r in page.search_for(text)] if text else []
    if not hits and text and index_db and os.path.exists(index_db):
        db = sqlite3.connect(index_db)
        target = squash(text)
        for x0, y0, x1, y1, t in db.execute(
                "SELECT x0,y0,x1,y1,text FROM words WHERE page=? AND source='ocr'", (page.number + 1,)):
            st = squash(t)
            k = st.find(target)
            if k < 0 or not st:
                continue
            # OCR boxes are whole lines: narrow to the matched part by character position
            a, b = k / len(st), (k + len(target)) / len(st)
            w = x1 - x0
            hits.append(pymupdf.Rect(x0 + w * a - 1, y0, x0 + w * b + 1, y1))
        db.close()
    if near is not None and hits:
        c = near.tl + (near.br - near.tl) * 0.5
        hits.sort(key=lambda r: abs((r.tl + (r.br - r.tl) * 0.5) - c))
    return hits
