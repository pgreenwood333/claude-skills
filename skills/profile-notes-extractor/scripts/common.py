"""Shared helpers (PyMuPDF only, no poppler). All coordinates are pixels at 100 dpi, top-left origin."""
import re
import statistics
import pymupdf

DPI = 100
K = DPI / 72  # PDF points -> 100-dpi pixels
_DOCS = {}


def doc(pdf):
    if pdf not in _DOCS:
        _DOCS[pdf] = pymupdf.open(pdf)
    return _DOCS[pdf]


def page_count(pdf):
    return len(doc(pdf))


def page_size_px(pdf, page=1):
    r = doc(pdf)[page - 1].rect
    return r.width * K, r.height * K


def words(pdf, page):
    """[(x0, y0, x1, y1, text), ...] for every word on the page (visible or invisible text layer)."""
    return [(w[0] * K, w[1] * K, w[2] * K, w[3] * K, w[4]) for w in doc(pdf)[page - 1].get_text("words")]


def note_height(ws):
    """Typical height of profile-note text on this plan set: median height of the 'STA.' words.
    Word heights depend on the PDF and the extractor, so the note filter is calibrated per plan set."""
    hs = [w[3] - w[1] for w in ws if w[4].startswith("STA.")]
    return statistics.median(hs) if hs else None


def sheet_info(pdf, page):
    """(sheet ID, sheet number) from the title block: the text under the 'SHEET ID' / 'WK. NO.' and 'SHEET NO.'
    labels in the bottom-right corner, with a regex fallback over that corner."""
    W, H = page_size_px(pdf, page)
    ws = sorted([w for w in words(pdf, page) if w[0] > W * 0.75 and w[1] > H * 0.75], key=lambda w: (w[1], w[0]))

    def below(first, second):
        for i in range(len(ws) - 1):
            a, b = ws[i], ws[i + 1]
            if a[4].upper() == first and b[4].upper().startswith(second) and abs(a[1] - b[1]) < 4:
                x0, x1, y = a[0] - 30, b[2] + 30, b[3]
                got = [w for w in ws if x0 <= (w[0] + w[2]) / 2 <= x1 and y - 2 <= w[1] <= y + 1.8 * (b[3] - b[1])]
                return " ".join(w[4] for w in sorted(got, key=lambda w: w[0])).strip() or None
        return None

    sid = below("SHEET", "ID") or below("WK.", "NO")
    sno = below("SHEET", "NO")
    if sid:
        sid = re.sub(r"\s*-\s*", "-", sid)
    if not sid:
        m = re.findall(r"\b([A-Z]{1,5}-\d+[A-Z]{0,3})\b", " ".join(w[4] for w in ws))
        sid = m[-1] if m else None
    m = re.search(r"\d+", sno or "")
    return sid, (int(m.group()) if m else None)
