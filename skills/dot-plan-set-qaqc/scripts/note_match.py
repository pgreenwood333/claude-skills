#!/usr/bin/env python3
"""Note match: plan note vs profile note on each WK sheet, and profile note vs cross-section (XS) note.

  note_match.py <plans.pdf> <out_dir> [--index <index_dir>] [--wk-pages 1-20] [--xs-pages 40-60]

Rules (from the engineer):
  * Profile note (WK, profile view) and the XS note for the same structure must match EXACTLY, line for line,
    stations and elevations included.
  * Plan note (WK, plan view above the profile) shows the structure label ("[465 B]") and the pipe length, size
    and material ("156' - 18\" RCP REQ'D"). These must agree with the profile note's structure ID and pipe line.
Pages: with --index, WK pages are prefix WK and XS pages are sheets numbered 9000-9999 or prefixed XS/X;
--wk-pages / --xs-pages override. Writes <out>/note_match.json: findings (findings-schema format, task
"notematch") plus every comparison made, so the agent and orchestrator can verify each one.
"""
import argparse, json, os, re
import functools
import pymupdf


@functools.lru_cache(maxsize=4)
def open_pdf(path):
    """Open each PDF once; big sets were re-opened inside loops."""
    return pymupdf.open(path)


OPENING = re.compile(r"\b\d+\s*@\s*\d+\"")   # opening counts like 2 @ 18"
from notes_core import extract_notes, K

PIPE = re.compile(r"(\d+(?:\.\d+)?)'\s*(-)?\s*(\d+(?:\.\d+)?)\"\s*(?:X\s*(\d+)\"\s*)?([A-Z][A-Z0-9-]*)?", re.I)
DASHLESS = []  # pipe lines written without the " - " between length and size
LABEL = re.compile(r"^\[?\s*(\d{3,4})\s*([A-Z]{1,2})\s*\]?(?:\s*\((?:MEDIAN|LT|RT)\))?$")
TAG = re.compile(r"\[\s*(\d{3,4})\s*([A-Z]{1,2})\s*\]")
DOUBLED = re.compile(r"^(\d{3,4}) \1 ([A-Z]{1,2}) \2\b")   # CAD overprint read twice: "425 425 B B"


def sid_of(line):
    """Structure ID ("465 B") from a note's first line or a plan label, else None (station-headed notes)."""
    m = LABEL.match(DOUBLED.sub(r"\1 \2", norm(line)))
    return f"{m.group(1)} {m.group(2)}" if m else None


def fmt_sta(v):
    return f"{int(v // 100)}+{v % 100:05.2f}"


def pages_arg(s):
    out = []
    for part in (s or "").split(","):
        if part:
            a, _, b = part.partition("-")
            out += list(range(int(a), int(b or a) + 1))
    return out


def norm(t):
    return re.sub(r"\s+", " ", t.replace("’", "'").replace("”", '"').replace("″", '"')).strip()


def pipes_in(text):
    """[(length, size, material)] from a pipe line; material None when the line has none (e.g. 18\" REQ'D.)."""
    out = []
    if "=" in text:
        return out  # H = / W = 2'6" lines are dimensions, not pipe runs
    for m in PIPE.finditer(text):
        mat = (m.group(5) or "").upper()
        if mat in ("REQ'D", "REQ'D.", "REQD", "REQ") or mat.startswith("REQ"):
            mat = None
        size = m.group(3) + (("X" + m.group(4)) if m.group(4) else "")
        out.append((float(m.group(1)), size, mat))
        if m.group(2) is None:
            DASHLESS.append(text)
    return out


def same_material(a, b, size):
    a, b = ("RCP" if (m or "").startswith("CL") else m for m in (a, b))   # "30\" CL. V, RCP" is class V RCP
    if a == b:
        return True
    if "EXIST" in (a, b):
        return True   # profile "EXIST. PIPE" vs plan "RCP IN PLACE": both describe the pipe in place
    return "X" in size and {a, b} <= {"RCP", "RCAP"}  # arch pipe: plan writes 65" X 40" RCP, profile writes RCAP


@functools.lru_cache(maxsize=None)
def sheet_name(pdf, page_no):
    page = open_pdf(pdf)[page_no - 1]
    r = page.rect
    t = page.get_text("text", clip=pymupdf.Rect(r.width * 0.9, r.height * 0.85, r.x1, r.y1))
    m = re.findall(r"\b([A-Z]{1,4}-\d+[A-Z]{0,3})\b", t)
    return m[-1] if m else None


def profile_top(page):
    """Top of the profile grid: elevation labels printed on both edges at the same height."""
    W = page.get_text("words")
    nums = [w for w in W if re.fullmatch(r"\d{2,4}", w[4])]
    ys = []
    for a in nums:
        for b in nums:
            if a[4] == b[4] and abs(a[1] - b[1]) < 3 and b[0] - a[0] > page.rect.width * 0.6:
                ys.append(a[1])
    return min(ys) - 20 if len(ys) >= 3 else page.rect.height * 0.49


def plan_items(pdf, page_no):
    """Structure labels and pipe labels in the plan view (above the profile), as text lines with boxes (points)."""
    page = open_pdf(pdf)[page_no - 1]
    top = profile_top(page)
    labels, pipes = [], []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            r = pymupdf.Rect(ln["bbox"])
            if r.y1 > top or r.x0 > page.rect.width * 0.92:
                continue
            t = norm("".join(s["text"] for s in ln["spans"]))
            sid = sid_of(t)
            if sid:
                labels.append(dict(id=sid, rect=list(r), text=t))
                continue
            # tags and pipe labels can run together in one text line: "[257A]34' - 24\" RCP REQ'D [257B] ..."
            for m in TAG.finditer(t):
                labels.append(dict(id=f"{m.group(1)} {m.group(2)}", rect=list(r), text=t))
            rest = TAG.sub(" ; ", t)
            if PIPE.search(rest) and not OPENING.search(rest):   # "2 @ 18\"" is an opening count, not a pipe run
                for part in rest.split(";"):
                    for pp in pipes_in(part):
                        pipes.append(dict(pipe=pp, rect=list(r), text=norm(part)))
    return labels, pipes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("out"); ap.add_argument("--index")
    ap.add_argument("--wk-pages"); ap.add_argument("--xs-pages")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sheet = {}
    wk, xs = pages_arg(a.wk_pages), pages_arg(a.xs_pages)
    if a.index:
        for p in json.load(open(os.path.join(a.index, "index.json")))["pages"]:
            sheet[p["pdf_page"]] = p["sheet_id"]
            no = str(p.get("sheet_no") or "")
            if not a.wk_pages and p["prefix"].upper() == "WK":
                wk.append(p["pdf_page"])
            if not a.xs_pages and (re.fullmatch(r"9\d{3}", no) or p["prefix"].upper() in ("XS", "X")):
                xs.append(p["pdf_page"])
    F, checks = [], []

    def add(sev, sids, pages, finding, evidence, fix, locate):
        F.append(dict(id=f"NM-{len(F) + 1:03d}", task="notematch", severity=sev, sheet_ids=sids, pdf_pages=pages,
                      finding=finding, evidence=evidence, suggested_fix=fix, locate=locate))

    prof = extract_notes(a.pdf, wk)
    by_id = {}
    for n in prof:
        n["sid"] = sid_of(n["lines"][0])
        if n["sid"]:
            by_id.setdefault(n["sid"], []).append(n)

    # ---- plan note vs profile note (same WK sheet)
    plan_cache = {}
    for n in prof:
        sid = n["sid"] or n["lines"][0]   # station-headed notes (drives, JBs, culverts) are checked by pipe alone
        p = n["page"]
        if p not in plan_cache:
            plan_cache[p] = plan_items(a.pdf, p)
        labels, pipes = plan_cache[p]
        sh = sheet.get(p, f"p{p}")
        lab = [l for l in labels if l["id"] == sid]
        if n["sid"] and not lab:   # tag drawn on the LT/RT partner sheet only
            for q in wk:
                if q != p and sheet_name(a.pdf, q) and sheet_name(a.pdf, p) and \
                        re.sub(r"(LT|RT)$", "", sheet_name(a.pdf, q)) == re.sub(r"(LT|RT)$", "", sheet_name(a.pdf, p)):
                    if q not in plan_cache:
                        plan_cache[q] = plan_items(a.pdf, q)
                    lab = [l for l in plan_cache[q][0] if l["id"] == sid]
                    if lab:
                        break
        n_pipes = []
        for line in n["lines"]:
            if "@" in line or "OPENINGS" in line:
                continue  # openings ("1 @ 18\"") are not pipe runs
            n_pipes += [pp for pp in pipes_in(line) if pp[0] >= 1]
        loc_prof = [dict(page=p, rect=n["bbox"])]
        if n["sid"] and not lab:
            add("medium", [sh], [p], f"{sid}: structure label not found in the plan view of {sh}",
                f"profile note {sid} at STA {n['lines'][1] if len(n['lines']) > 1 else ''}", "Check the plan label",
                loc_prof)
            checks.append(dict(kind="plan", id=sid, page=p, result="label missing"))
            continue
        L = lab[0] if lab else dict(rect=n["bbox"])
        # pipe labels can sit anywhere along the run, or on the LT/RT partner sheet when the pipe crosses the road
        # where to look: this sheet, its LT/RT partner, every sheet showing the same structure label, and the two
        # sheets either side (pipes that cross a match line are labelled on the next sheet)
        for q in wk:
            if q not in plan_cache:
                plan_cache[q] = plan_items(a.pdf, q)
        label_pages = {q for q in wk if n["sid"] and any(l["id"] == sid for l in plan_cache[q][0])}
        partner = [q for q in wk if q != p and sheet_name(a.pdf, q) and sheet_name(a.pdf, p) and
                   re.sub(r"(LT|RT)$", "", sheet_name(a.pdf, q)) == re.sub(r"(LT|RT)$", "", sheet_name(a.pdf, p))]
        num = lambda q: int(m.group(1)) if (m := re.match(r"[A-Z]+-(\d+)", sheet_name(a.pdf, q) or "")) else None
        near_no = {q for q in wk if num(q) is not None and num(p) is not None and abs(num(q) - num(p)) <= 1}
        partner = sorted(set(partner) | label_pages | near_no |
                         {q for q in wk for lp in label_pages | {p} if abs(q - lp) <= 2} - {p})
        pool = [(p, pp) for pp in pipes]
        for q in partner:
            if q not in plan_cache:
                plan_cache[q] = plan_items(a.pdf, q)
            pool += [(q, pp) for pp in plan_cache[q][1]]
        lx = (L["rect"][0] + L["rect"][2]) / 2
        for npipe in n_pipes:
            same = [(q, pp) for q, pp in pool if pp["pipe"][0] == npipe[0] and pp["pipe"][1] == npipe[1]]
            same.sort(key=lambda t: (t[0] != p, abs((t[1]["rect"][0] + t[1]["rect"][2]) / 2 - lx)))
            if same:
                q, best = same[0]
                ok_mat = npipe[2] is not None and same_material(best["pipe"][2], npipe[2], npipe[1])
                checks.append(dict(kind="plan", id=sid, page=p, profile=npipe, plan=best["text"], plan_page=q,
                                   result="match" if ok_mat else "material differs"))
                if not ok_mat:
                    what = "has no material" if npipe[2] is None else f"says {npipe[2]}"
                    add("medium", [sh], [p], f"{sid}: profile note pipe line {what}; plan label says "
                                             f"'{best['text']}' on {sheet.get(q, f'p{q}')}",
                        f"profile pipe {npipe[0]:g}' - {npipe[1]}\" {npipe[2] or ''} | plan: {best['text']}",
                        "Make plan and profile agree", loc_prof + [dict(page=q, rect=best["rect"])])
            else:
                nearest = sorted(pipes, key=lambda pp: abs((pp["rect"][0] + pp["rect"][2]) / 2 - lx))[:2]
                plan_txt = "; ".join(pp["text"] for pp in nearest) or "no pipe labels in plan view"
                checks.append(dict(kind="plan", id=sid, page=p, profile=npipe, plan=plan_txt, result="mismatch"))
                add("high", [sh], [p], f"{sid}: profile note pipe {npipe[0]:g}' - {npipe[1]}\" "
                                       f"{npipe[2] or '(no material)'} has no matching pipe label in the plan view "
                                       f"of {sh} or nearby sheets",
                    f"nearest plan labels: {plan_txt}", "Make the plan label and the profile note agree",
                    loc_prof + [dict(page=p, rect=pp["rect"]) for pp in nearest] + ([dict(page=p, rect=L["rect"])] if lab else []))

    # ---- profile note vs cross-section note (exact)
    if xs:
        xsn = extract_notes(a.pdf, xs, region=(0.02, 0.03, 0.92, 0.97))
        for n in prof:
            sid = n["sid"] or n["lines"][0]
            for x in xsn:
                x.setdefault("sid", sid_of(x["lines"][0]) if x["lines"] else None)
            cands = [x for x in xsn if x["sid"] == n["sid"]] if n["sid"] else []
            if not cands:   # fall back to station, but never pair two different structure IDs (337 A vs 337 B)
                cands = [x for x in xsn if abs(x["sta"] - n["sta"]) < 0.005 and len(x["lines"]) > 2
                         and x["lines"][1:3] == n["lines"][1:3] and x["sid"] == n["sid"]]
            sh = sheet.get(n["page"], f"p{n['page']}")
            if not cands:
                checks.append(dict(kind="xs", id=sid, page=n["page"], result="no xs note"))
                add("medium", [sh], [n["page"]], f"{sid}: no cross-section note found for this profile note",
                    " | ".join(n["lines"][:3]), "Confirm the structure is noted on its cross section",
                    [dict(page=n["page"], rect=n["bbox"])])
                continue
            x0 = min(cands, key=lambda c: abs(c["sta"] - n["sta"]))
            # the same structure is often noted on two cross-section sheets (sheet breaks): check every copy
            copies = [c for c in cands if abs(c["sta"] - x0["sta"]) < 0.005]
            texts = {}
            for c in copies:
                texts.setdefault(tuple(norm(t) for t in c["lines"]), []).append(c)
            if len(texts) > 1:
                xshs = sorted({sheet.get(c["page"], f"p{c['page']}") for c in copies})
                add("high", xshs, sorted({c["page"] for c in copies}),
                    f"{sid}: the cross-section notes for this structure disagree ({', '.join(xshs)})",
                    " || ".join(" | ".join(c["lines"]) for c in copies)[:600],
                    "Make every cross-section copy of this note identical (and match the profile)",
                    [dict(page=c["page"], rect=c["bbox"]) for c in copies])
            for x in copies:
                a_l, b_l = [norm(t) for t in n["lines"]], [norm(t) for t in x["lines"]]
                if a_l == b_l:
                    checks.append(dict(kind="xs", id=sid, page=n["page"], xs_page=x["page"], result="match"))
                    continue
                diffs = []
                for k in range(max(len(a_l), len(b_l))):
                    pa = a_l[k] if k < len(a_l) else "(missing)"
                    pb = b_l[k] if k < len(b_l) else "(missing)"
                    if pa != pb:
                        diffs.append(f"line {k + 1}: profile '{pa}' vs XS '{pb}'")
                xsh = sheet.get(x["page"], f"p{x['page']}")
                checks.append(dict(kind="xs", id=sid, page=n["page"], xs_page=x["page"], result="mismatch", diffs=diffs))
                add("high", [sh, xsh], [n["page"], x["page"]],
                    f"{sid}: profile note on {sh} does not match the cross-section note on {xsh}",
                    "; ".join(diffs[:4]), "Make the profile and cross-section notes identical",
                    [dict(page=n["page"], rect=n["bbox"]), dict(page=x["page"], rect=x["bbox"])])

        # ---- the other direction: a cross-section note (drainage structure or driveway) with no profile note.
        # Proposed drainage and driveway notes normally appear on both the profile and the cross section.
        XS_NOTE = re.compile(r"REQ'?D|EXIST\.?\s+PIPE|FLOWABLE", re.I)
        prof_sids = {n["sid"] for n in prof if n["sid"]}
        seen = set()
        for x in xsn:
            if not x["lines"] or not XS_NOTE.search(" ".join(x["lines"])):
                continue
            if x["sid"]:
                matched = x["sid"] in prof_sids
            else:   # station-headed note (driveway, JB, culvert): any profile note within 1 ft
                matched = any(abs(n["sta"] - x["sta"]) <= 1.0 for n in prof)
            key = (x["sid"] or norm(x["lines"][0]), round(x["sta"], 1))
            if matched or key in seen:
                continue
            seen.add(key)
            xsh = sheet.get(x["page"], f"p{x['page']}")
            label = x["sid"] or norm(x["lines"][0])
            checks.append(dict(kind="xs_reverse", id=label, page=x["page"], result="no profile note"))
            add("medium", [xsh], [x["page"]], f"{label}: cross-section note on {xsh} has no matching profile note",
                " | ".join(x["lines"][:3]), "Add the note to the profile (or remove it from the cross section)",
                [dict(page=x["page"], rect=x["bbox"])])

    # same structure ID used for different structures (different stations)
    for sid_, ns in by_id.items():
        stas = sorted({round(n["sta"], 2) for n in ns})
        if len(stas) > 1:
            add("high", sorted({sheet.get(n["page"], f"p{n['page']}") for n in ns}), sorted({n["page"] for n in ns}),
                f"Structure ID {sid_} is used for more than one structure (stations {', '.join(fmt_sta(v) for v in stas)})",
                " || ".join(" | ".join(n["lines"][:3]) for n in ns), "Give each structure a unique ID",
                [dict(page=n["page"], rect=n["bbox"]) for n in ns])
    for n in prof:
        for line in n["lines"]:
            if line in DASHLESS and "=" not in line:
                add("low", [sheet.get(n["page"], f"p{n['page']}")], [n["page"]],
                    f"{n['lines'][0]}: pipe line is missing the dash between length and size", line,
                    line.replace("' ", "' - ", 1), [dict(page=n["page"], text=line.split()[0])])
    summary = dict(profile_notes=len(prof), wk_pages=len(set(wk)), xs_pages=len(set(xs)),
                   plan_checks=sum(c["kind"] == "plan" for c in checks),
                   plan_mismatches=sum(c["kind"] == "plan" and c["result"] != "match" for c in checks),
                   xs_without_profile=sum(c["kind"] == "xs_reverse" for c in checks),
                   xs_checks=sum(c["kind"] == "xs" for c in checks),
                   xs_mismatches=sum(c["kind"] == "xs" and c["result"] != "match" for c in checks))
    json.dump(dict(summary=summary, findings=F, checks=checks, profile_notes=prof),
              open(os.path.join(a.out, "note_match.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
