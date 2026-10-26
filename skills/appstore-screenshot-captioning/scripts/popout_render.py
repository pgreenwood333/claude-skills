"""Render App Store screenshots (iPhone 6.9", 1320x2868) from raw phone captures.

Layout follows the category leader (Cleanup): centered two-tone title + subtitle on a
flat solid background, upright phone below, cropped by the bottom edge.
Built on the appstore-screenshot-captioning skill's type spec (SF Pro Display
Heavy/Medium, measured sizes) with FreeUpStorage's dark-theme palette.

Usage: python3 scripts/store-screenshots/render.py [lang ...]
Reads  screenshots/<lang-Name>/{1-photos,2-contacts,3-profile,4-duplicates}.png
Writes screenshots/appstore/<lang-Name>/0N.png
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "screenshots")
OUT = os.path.join(SRC, "appstore")
FD = "/Library/Fonts"

W, H = 1320, 2868
BG = (0x1E, 0x33, 0x27)        # deep forest — darker than the old cream, distinct from app bg #1A1F1B
TITLE_C = (0xEE, 0xE8, 0xDC)   # app text cream
ACCENT = (0x9C, 0xC2, 0xA6)    # app sage #6F8F79 lifted for contrast on dark
SUB_C = (0xB9, 0xC6, 0xBB)
BEZEL = (0x0C, 0x10, 0x0D)
RIM = (0x4A, 0x5E, 0x50)

TF = ImageFont.truetype(f"{FD}/SF-Pro-Display-Heavy.otf", 118)
SF = ImageFont.truetype(f"{FD}/SF-Pro-Display-Medium.otf", 62)

# slide order -> source capture
SLIDES = [("01", "1-photos"), ("02", "4-duplicates"), ("03", "2-contacts"), ("04", "3-profile")]


def tokens(title):
    """'Delete [Duplicate Photos]' -> [(word, color)...]"""
    out, acc = [], False
    for w in title.split():
        start = w.startswith("[")
        end = w.endswith("]")
        if start: acc = True
        out.append((w.strip("[]"), ACCENT if acc else TITLE_C))
        if end: acc = False
    return out


def wrap(d, words, font, max_w):
    lines, cur = [], []
    for w in words:
        test = cur + [w]
        if cur and d.textlength(" ".join(x for x, _ in test), font=font) > max_w:
            lines.append(cur); cur = [w]
        else:
            cur = test
    if cur: lines.append(cur)
    return lines


def fit_title(d, title, max_w=1180, max_lines=2):
    """'|' in the title forces a line break."""
    size = 118
    while size > 70:
        f = ImageFont.truetype(f"{FD}/SF-Pro-Display-Heavy.otf", size)
        lines = [l for seg in title.split("|") for l in wrap(d, tokens(seg), f, max_w)]
        if len(lines) <= max_lines and all(
            d.textlength(" ".join(x for x, _ in l), font=f) <= max_w for l in lines):
            return f, size, lines
        size -= 4
    return f, size, lines


# Demo numbers painted over the captures (the test library only had 177 duplicates).
# Slide 1's totals are recomputed so both slides agree:
#   items 2957 - 177 + 1177 = 3957;  size 8.1 GB - 238 MB + 24.3 GB = 32.2 GB
DEMO = {"dup_count": "1177", "dup_size": "24.3 GB", "total_count": "3957", "total_size": "32.2 GB"}


def _tokens(px, y0, y1, x0, x1, is_ink):
    cols = [x for x in range(x0, x1) if any(is_ink(px[x, y]) for y in range(y0, y1))]
    groups, s, p = [], cols[0], cols[0]
    for c in cols[1:]:
        if c - p > 9:
            groups.append((s, p)); s = c
        p = c
    groups.append((s, p))
    return groups


def _t(tmpl, count, size):
    return tmpl.replace("{{count}}", count).replace("{{size}}", size)


def _text(d, xy, text, weight, size, fill, track=0.0):
    """Draw with per-glyph tracking (px) so widths match iOS's SF rendering."""
    f = ImageFont.truetype(f"{FD}/SF-Pro-Text-{weight}.otf", size)
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill, anchor="ls")
        x += f.getlength(ch) + track
    return x - xy[0] - track


def _width(text, weight, size, track=0.0):
    f = ImageFont.truetype(f"{FD}/SF-Pro-Text-{weight}.otf", size)
    return sum(f.getlength(ch) for ch in text) + track * (len(text) - 1)


def restate_duplicates(shot, i18n):
    """Duplicates capture: rewrite the Delete button and '177 selected · 238 MB' header
    from the app's own i18n templates with the DEMO numbers. 920x2000 layout."""
    shot = shot.copy(); px = shot.load(); d = ImageDraw.Draw(shot)
    n, size = DEMO["dup_count"], DEMO["dup_size"]
    # Delete button: [trash icon] + semibold dark label, centered on the pill.
    red = px[120, 1830]
    toks = _tokens(px, 1830, 1920, 150, 800, lambda c: sum(c) < 250)
    icon = shot.crop((toks[0][0], 1840, toks[0][1] + 1, 1906))
    label = _t(i18n["deleteWithSize"], n, size)
    total = icon.width + 28 + _width(label, "Semibold", 38, -0.45)
    d.rectangle((toks[0][0] - 4, 1840, toks[-1][1] + 4, 1906), fill=red)
    x = round(460 - total / 2)
    shot.paste(icon, (x, 1840))
    _text(d, (x + icon.width + 28, 1887), label, "Semibold", 38, (11, 16, 1), -0.45)
    # Header subtitle, left-aligned muted text.
    d.rectangle((120, 214, 760, 258), fill=px[600, 235])
    _text(d, (126, 245), _t(i18n["selectedCount"], n, size), "Regular", 31, (174, 179, 173), 0.25)
    return shot


def restate_photos(shot, i18n):
    """Photos home capture: rewrite the screen subtitle totals and the Duplicates card."""
    shot = shot.copy(); px = shot.load(); d = ImageDraw.Draw(shot)
    d.rectangle((44, 288, 900, 340), fill=px[880, 310])
    _text(d, (49, 325), _t(i18n["subtitleClean"], DEMO["total_count"], DEMO["total_size"]),
          "Regular", 35.5, (172, 180, 175))
    d.rectangle((224, 486, 770, 527), fill=px[760, 505])
    _text(d, (227, 517), _t(i18n["itemsSize"], DEMO["dup_count"], DEMO["dup_size"]),
          "Regular", 30.5, (173, 181, 174))
    return shot


def phone(shot, screen_w=1000):
    sh = round(shot.height * screen_w / shot.width)
    shot = shot.resize((screen_w, sh), Image.LANCZOS)
    b = 30  # bezel
    pw, ph = screen_w + 2 * b, sh + 2 * b
    ph_im = Image.new("RGBA", (pw + 8, ph + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(ph_im)
    d.rounded_rectangle((0, 0, pw + 7, ph + 7), radius=168, fill=RIM)
    d.rounded_rectangle((4, 4, pw + 3, ph + 3), radius=164, fill=BEZEL)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), radius=136, fill=255)
    ph_im.paste(shot, (b + 4, b + 4), mask)
    # dynamic island over the (captured) status bar area
    iw, ih = 250, 72
    ix = (pw + 8 - iw) // 2
    d.rounded_rectangle((ix, b + 4 + 26, ix + iw, b + 4 + 26 + ih), radius=36, fill=(0, 0, 0))
    return ph_im


# Pop-outs: key UI pieces cropped from the capture, enlarged, and lifted off the phone
# (Cleanup-style). Boxes are in capture pixels (920-wide captures; scaled if different).
# (x0, y0, x1, y1, corner_radius, target_width)
POPS = {
    "01": [(46, 385, 874, 573, 44, 1210), (46, 1048, 874, 1237, 44, 1210)],
    "02": [(38, 432, 882, 712, 40, 1240), (46, 1812, 874, 1934, 61, 1150)],
    "03": [(46, 385, 874, 573, 44, 1220)],
    "04": [(46, 1024, 874, 1279, 44, 1220)],
}
SCREEN_W = 940
BEZ = 34  # bezel + rim offset used in phone()


def pop(im, shot, box, phone_xy, scale):
    """Lift box out of `shot`, enlarge to target width, center it over its spot on the phone."""
    x0, y0, x1, y1, r, tw = box
    k = shot.width / 920
    crop = shot.crop((round(x0 * k), round(y0 * k), round(x1 * k), round(y1 * k)))
    th = round(crop.height * tw / crop.width)
    crop = crop.resize((tw, th), Image.LANCZOS)
    rr = round(r * tw / (x1 - x0))
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw - 1, th - 1), radius=rr, fill=255)
    # where the element sits on the phone
    cy = phone_xy[1] + BEZ + (y0 + y1) / 2 * k * scale
    px, py = (W - tw) // 2, round(cy - th / 2)
    # soft contact shadow (dark, low opacity — depth, not glow)
    pad = 80
    sh = Image.new("L", (tw + 2 * pad, th + 2 * pad), 0)
    ImageDraw.Draw(sh).rounded_rectangle((pad, pad, pad + tw, pad + th), radius=rr, fill=120)
    sh = sh.filter(ImageFilter.GaussianBlur(30))
    im.paste((0, 0, 0), (px - pad, py - pad + 28), sh)
    im.paste(crop, (px, py), mask)
    ImageDraw.Draw(im).rounded_rectangle((px, py, px + tw - 1, py + th - 1), radius=rr,
                                         outline=RIM, width=3)


def render(lang_dir, spec):
    os.makedirs(os.path.join(OUT, lang_dir), exist_ok=True)
    for num, src in SLIDES:
        path = os.path.join(SRC, lang_dir, src + ".png")
        if not os.path.exists(path) or num not in spec:
            print(f"  skip {lang_dir}/{num} ({'no capture' if not os.path.exists(path) else 'no caption'})")
            continue
        title, sub = spec[num]
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        f, size, lines = fit_title(d, title)
        pitch = int(size * 1.13)
        subs = [" ".join(x for x, _ in l) for l in wrap(d, [(w, 0) for w in sub.split()], SF, 1180)]
        y = 190
        for l in lines:
            text_w = d.textlength(" ".join(x for x, _ in l), font=f)
            x = (W - text_w) / 2
            for i, (w, c) in enumerate(l):
                d.text((x, y), w, font=f, fill=c)
                x += d.textlength(w + (" " if i < len(l) - 1 else ""), font=f)
            y += pitch
        y += 34
        for s in subs:
            d.text((W / 2, y), s, font=SF, fill=SUB_C, anchor="ma")
            y += 80
        shot = Image.open(path).convert("RGB")
        i18n = json.load(open(os.path.join(ROOT, "src/i18n", lang_dir.split("-")[0] + ".json")))["photos"]
        if src == "4-duplicates":
            shot = restate_duplicates(shot, i18n)
        elif src == "1-photos":
            shot = restate_photos(shot, i18n)
        ph = phone(shot, SCREEN_W)
        top = max(y + 80, 700)
        im.paste(ph, ((W - ph.width) // 2, top), ph)
        for box in POPS.get(num, []):
            pop(im, shot, box, (0, top), SCREEN_W / shot.width)
        out = os.path.join(OUT, lang_dir, num + ".png")
        im.save(out)
        print("  wrote", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    captions = json.load(open(os.path.join(os.path.dirname(__file__), "captions.json")))
    want = sys.argv[1:] or list(captions)
    for lang in want:
        print(lang)
        render(lang, captions[lang])
