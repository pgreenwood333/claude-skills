#!/usr/bin/env python3
"""Print-color check for WK (plan-profile) sheets: proposed drainage = blue, existing/surveyed = purple, rest = black.

  color_check.py <plans.pdf> <index_dir> <out_dir> [--prefixes WK] [--pages 15,16] [--region all|profile|plan]

How the color is measured (exact, no guessing)
  OpenRoads/MicroStation sheets draw every letter as a filled shape and lay an invisible text copy on top. Each
  letter shape is assigned to the text line it sits under (same method as find_overlaps.py), and the line's printed
  color is the fill color of its letter shapes. Lines stacked under each other (same left edge, small gap) are
  grouped into one note. Sheets with real visible text use the text color directly.

Rules applied (these produce CANDIDATES for the agent to judge, not findings)
  EXIST_NOT_PURPLE   note labels an existing item (EXIST/EX./(E), no action word) but is not purple
  PROPOSED_PURPLE    purple note with proposed wording: an action on an existing item (TIE TO EXIST. ROW, REMOVE
                     EXIST. PIPE) or REQ'D / PROP. / TEMPORARY EASEMENT. Should be black, or blue if drainage work
  DRAIN_BLACK        note names a drainage item (pipe, inlet, ditch...) but prints black: blue if proposed,
                     purple if it is existing survey data (e.g. INLET TOP EL= beside a surveyed MH)
  DITCH_NOT_BLACK    ditch grade label not black (ditch grades print black in the profile)
  BLUE_NO_DRAIN      blue note with no drainage words (includes blue ditch station/elevation callouts)
  Purple labels with no proposed wording (PBOX, POLE, MH, BENCH, gas line) are survey items and are not flagged.
  MIXED              one note printed in more than one color          (part of the note on the wrong level)
  ODD_COLOR          text in a color that is not black, blue or purple
Output: <out>/color_candidates.json (candidates + per-sheet color counts + every note with its color), a crop per
candidate in <out>/crops/, and a color-coded overlay per sheet in <out>/overlays/ (each note boxed in the color it
measured as, so the agent can scan a whole sheet at a glance).
"""
import argparse, colorsys, json, os, re, sys
from collections import Counter
import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_overlaps import profile_regions, text_lines, text_is_invisible, vector_labels, visible_labels  # noqa: E402

EXIST = re.compile(r"\bEXIST|\bEX\.|\(E\)|\bEXIST(ING)?\b|\bSURVEY", re.I)
DRAIN = re.compile(
    r"\b(\d+\"?\s*(RCP|CMP|HDPE|PVC|RCAP|CPP|SRCP|RCBC|RCB)|RCP|RCAP|CMP|HDPE|PIPES?|CULVERTS?|INLETS?|J\.?B\.?|"
    r"JUNCTION BOX|MANHOLES?|M\.?H\.?|HEADWALLS?|ENDWALLS?|END SECTIONS?|FLUMES?|(BOX|BRIDGE) CULVERT|DBL\.?|"
    r"F\.?L\.?|FLOW ?LINE|[UD]S ?FL|USFL|DSFL|SKEW|D\.?A\.?\s*=|OUTLET|DROP INLET|TYPE \"?[A-Z0-9]+\"? INLET|"
    r"ALT|ALTERNATE|INV\.?|INVERT|(SS|GI|DI|JB|MH|FE|SE|CB|DS|HW|B)-\d{1,2}|PAVED DITCH|SUBDRAIN|UNDERDRAIN|STORM DRAIN|CATCH BASIN)\b", re.I)
NOT_DRAIN = re.compile(r"\b(GAS|WATER|FIBER|STEEL|TELEPHONE|ELECTRIC|POWER|SILT|EROSION|EARTHWORK|SANITARY)\b", re.I)
# drainage structure tags ([414 A]) and box dimension stacks (5.85' / 5.00' / 2'6") are drainage too
STRUCT = re.compile(r"^\[\s*\d+\s*[A-Z]?\s*\]?$|^\d+(\.\d+)?' / \d+(\.\d+)?' / \d+'\s*\d*\"?$|^\d+' - \d+\"$")
# a blue note is only judged when it has real words (bare stations/elevations are pieces of a drainage note)
WORDY = re.compile(r"\b(?!STA\b|EL\b|LT\b|RT\b|INV\b|TOP\b)[A-Z]{3,}\b")
# ditch grades print BLACK in the profile (engineer's rule), and so do their station/elevation callouts
DITCH = re.compile(r"\bDITCH GRADE\b|\b(LT|RT) DITCH\b", re.I)
CALLOUT = re.compile(r"^((LT|RT)\s*\d+\+\d+(\.\d+)?|EL\.?\s*\d+(\.\d+)?|[+-]?\d+(\.\d+)?%|NOTE:?|\s|/)+$", re.I)
PROPOSED = re.compile(r"\b(REQ'?D|REQUIRED|PROP(OSED|\.)|TEMP(ORARY|\.)? (CONST(RUCTION|\.)? )?EASEMENT|"
                      r"PERM(ANENT|\.)? EASEMENT|PROPOSED R\.?O\.?W|CONSTRUCT|BEGIN|END PROJECT)\b", re.I)
# A note that DOES something to an existing item is proposed work: black (blue if it is drainage work).
# "TIE TO EXIST. ROW" -> black.  "EXIST. 18\" RCP" (labels the existing item itself) -> purple.
ACTION = re.compile(
    r"\b(TIE[SD]? (IN(TO)?|TO)|CONNECT(ION)? (TO|INTO)|MATCH(ES)?|REMOVE[SD]?|REMOVAL|ABANDON(ED)?|PLUG(GED)?|ADJUST|"
    r"EXTEND|EXTENSION|REPLACE[SD]?|RECONSTRUCT|RELOCATE[SD]?|SAW ?CUT|MILL|OVERLAY|TRANSITION TO|JOIN|"
    r"CLEAN( OUT)?|RESET|REQ'?D|REQUIRED|PROP(OSED|\.)?|CONSTRUCT)\b", re.I)


def classify(rgb):
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.25 or s < 0.2:
        return "black" if v < 0.6 else "gray"
    hue = h * 360
    if 190 <= hue < 255:
        return "blue"
    if 255 <= hue < 335:
        return "purple"
    return "other"


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in rgb[:3])


def label_color(lab, page, vector_mode):
    cnt = Counter()
    if vector_mode:
        for d in lab["paths"]:
            if d.get("fill"):
                cnt[tuple(round(x, 3) for x in d["fill"][:3])] += 1
    else:
        for b in page.get_text("dict", clip=lab["rect"])["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln["spans"]:
                    if sp["text"].strip():
                        c = sp["color"]
                        cnt[((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)] += len(sp["text"])
    if not cnt:
        return None, None
    rgb = cnt.most_common(1)[0][0]
    return classify(rgb), hexc(rgb)


def group_notes(labels):
    """Stack horizontal lines that share a left edge and sit close under each other into one note."""
    horiz = sorted([l for l in labels if l["rect"].width >= l["rect"].height], key=lambda l: (l["rect"].y0, l["rect"].x0))
    vert = [l for l in labels if l["rect"].width < l["rect"].height]
    notes, used = [], set()
    for i, a in enumerate(horiz):
        if i in used:
            continue
        group, last = [a], a
        used.add(i)
        for j in range(i + 1, len(horiz)):
            if j in used:
                continue
            b = horiz[j]
            h = max(last["rect"].height, 3)
            gap = b["rect"].y0 - last["rect"].y1
            if gap > 0.9 * h:
                if b["rect"].y0 - last["rect"].y1 > 6 * h:
                    break
                continue
            ra, rb = last["rect"], b["rect"]
            tol = max(2.5, 0.6 * h)
            aligned = (abs(rb.x0 - ra.x0) <= tol or abs(rb.x1 - ra.x1) <= tol or
                       abs((rb.x0 + rb.x1) / 2 - (ra.x0 + ra.x1) / 2) <= tol)
            similar = 0.7 <= rb.height / max(ra.height, 0.1) <= 1.4
            if aligned and similar and -0.5 * h <= gap <= 0.9 * h:
                group.append(b)
                used.add(j)
                last = b
        notes.append(group)
    notes += [[v] for v in vert]
    return notes


def judge(note):
    text = " / ".join(l["text"] for l in note)
    cols = [l["color"] for l in note if l["color"]]
    main = Counter(cols).most_common(1)[0][0] if cols else None
    has_ex, has_act = bool(EXIST.search(text)), bool(ACTION.search(text))
    has_dr = (bool(DRAIN.search(text)) or bool(STRUCT.match(text.strip()))) and not NOT_DRAIN.search(text) \
        and len(note) <= 8
    existing_item = has_ex and not has_act        # labels the existing thing itself
    proposed_words = bool(PROPOSED.search(text)) or (has_ex and has_act)
    rules = []
    if len(set(c for c in cols if c != "gray")) > 1:
        rules.append("MIXED")
    if any(c == "other" for c in cols):
        rules.append("ODD_COLOR")
    if existing_item and main not in ("purple", None):
        rules.append("EXIST_NOT_PURPLE")
    if main == "purple" and proposed_words:
        rules.append("PROPOSED_PURPLE")
    if has_dr and not existing_item and main == "black":
        rules.append("DRAIN_BLACK")
    if DITCH.search(text) and main not in ("black", None):
        rules.append("DITCH_NOT_BLACK")
    elif main == "blue" and not has_dr and WORDY.search(text):
        rules.append("BLUE_NO_DRAIN")
    return text, main, rules, has_ex, has_dr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("index"); ap.add_argument("out")
    ap.add_argument("--prefixes", default="WK"); ap.add_argument("--pages")
    ap.add_argument("--region", default="all", choices=["all", "profile", "plan"])
    a = ap.parse_args()
    for d in ("crops", "overlays"):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)
    idx = json.load(open(os.path.join(a.index, "index.json")))
    prefixes = {p.strip().upper() for p in a.prefixes.split(",")}
    want = {int(p) for p in a.pages.split(",")} if a.pages else None
    doc = pymupdf.open(a.pdf)
    sheets, cands, all_notes = [], [], []
    draw = {"black": (0.3, 0.3, 0.3), "blue": (0, 0.3, 1), "purple": (0.6, 0, 0.6), "gray": (0.6, 0.6, 0.6),
            "other": (1, 0.5, 0), None: (1, 0.5, 0)}
    for rec in idx["pages"]:
        pno = rec["pdf_page"]
        if (want and pno not in want) or (not want and rec["prefix"].upper() not in prefixes):
            continue
        page = doc[pno - 1]
        pr = page.rect
        profiles = profile_regions(page)
        sheet_area = pymupdf.Rect(pr.x0, pr.y0, pr.width * 0.92, pr.y1)   # leave out the title block strip
        top = min((r.y0 for r in profiles), default=pr.y1)
        areas = {"all": [sheet_area], "profile": profiles,
                 "plan": [pymupdf.Rect(pr.x0, pr.y0, pr.width * 0.92, top)]}[a.region]
        vector_mode = text_is_invisible(page)
        labels = []
        for area in areas:
            lines = text_lines(page, area)
            labels += vector_labels(page, area, lines) if vector_mode else visible_labels(lines)
        for l in labels:
            l["color"], l["hex"] = label_color(l, page, vector_mode)
        notes = group_notes(labels)
        counts = Counter(l["color"] for l in labels)
        tmp = pymupdf.open()
        tmp.insert_pdf(doc, from_page=pno - 1, to_page=pno - 1)
        op = tmp[0]
        for n in notes:
            text, main_c, rules, has_ex, has_dr = judge(n)
            rect = pymupdf.Rect(n[0]["rect"])
            for l in n[1:]:
                rect |= l["rect"]
            in_profile = any(p.contains(rect.tl) for p in profiles)
            nid = f"p{pno}-{len(all_notes) + 1:04d}"
            note = dict(note_id=nid, pdf_page=pno, sheet_id=rec["sheet_id"], view="profile" if in_profile else "plan",
                        text=text, color=main_c, line_colors=[[l["text"], l["color"], l["hex"]] for l in n],
                        rect=[round(v, 1) for v in rect], exist_words=has_ex, drainage_words=has_dr)
            all_notes.append(note)
            op.draw_rect(rect + (-1, -1, 1, 1), color=draw.get(main_c), width=0.8 if not rules else 2.5)
            if rules:
                crop = (rect + (-60, -40, 60, 40)) & pr
                png = os.path.join(a.out, "crops", f"COL-{nid}.png")
                page.get_pixmap(dpi=250, clip=crop).save(png)
                cands.append(dict(note, rules=rules, crop=png))
        ov = os.path.join(a.out, "overlays", f"p{pno:04d}_{rec['sheet_id']}.png")
        op.get_pixmap(dpi=90).save(ov)
        sheets.append(dict(pdf_page=pno, sheet_id=rec["sheet_id"], text_mode="vector" if vector_mode else "text",
                           profiles=len(profiles), labels=len(labels), notes=len(notes),
                           label_colors=dict(counts), overlay=ov,
                           note=None if labels else "no text found: check this sheet visually"))
        print(f"p{pno:03d} {rec['sheet_id']:<8} labels={len(labels)} notes={len(notes)} colors={dict(counts)} "
              f"candidates={sum(1 for c in cands if c['pdf_page'] == pno)}", file=sys.stderr)
    rule_counts = Counter(r for c in cands for r in c["rules"])
    json.dump(dict(rules=__doc__.split("Rules applied")[1].split("Output:")[0].strip(), sheets=sheets,
                   candidates=cands, notes=all_notes), open(os.path.join(a.out, "color_candidates.json"), "w"), indent=1)
    print(json.dumps(dict(sheets=len(sheets), notes=len(all_notes), candidates=len(cands), by_rule=dict(rule_counts)),
                     indent=1))


if __name__ == "__main__":
    main()
