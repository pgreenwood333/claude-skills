#!/usr/bin/env python3
"""Spelling candidates from every word in the plan set (text layer and OCR), for the spelling agent to judge.

  spell_candidates.py <index_dir> <out.json> [--allow extra_terms.txt]

Produces three lists, each item with page, sheet ID, box, source (text/ocr), OCR confidence and the full line:
  unknown     words not in the English dictionary or the MDOT allow-list, with the dictionary's best suggestion
  repeated    the same word twice in a row ("THE THE")
  variants    two spellings of one term used in the set (e.g. PERMANENT / PERMAMENT), with counts
Skipped: tokens with digits, station or pay-item notation, 1-2 letter tokens, and unknown words that recur
consistently on 3+ sheets of the text layer (project names, streets) unless they are a near-variant of another word.
OCR words are marked `ocr`: a candidate from OCR may be an OCR misread, so the agent must look at the crop.
"""
import argparse, json, os, re, sqlite3
from collections import defaultdict
from qaqc_common import save_json

HERE = os.path.dirname(os.path.abspath(__file__))


def edit1(a, b):
    if abs(len(a) - len(b)) > 1 or a == b:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("index"); ap.add_argument("out"); ap.add_argument("--allow")
    a = ap.parse_args()
    from spellchecker import SpellChecker
    sp = SpellChecker(distance=2)
    allow = set()
    for path in [os.path.join(HERE, "..", "assets", "mdot_terms.txt"), a.allow]:
        if path and os.path.exists(path):
            allow |= {l.strip().upper() for l in open(path) if l.strip() and not l.startswith("#")}
    idx = json.load(open(os.path.join(a.index, "index.json")))
    sheet = {p["pdf_page"]: p["sheet_id"] for p in idx["pages"]}
    db = sqlite3.connect(os.path.join(a.index, "index.db"))
    rows = db.execute("SELECT page,x0,y0,x1,y1,text,source,conf,block,line FROM words ORDER BY page,source,y0,x0").fetchall()
    # line context for text-layer words
    ctx = defaultdict(list)
    for r in rows:
        if r[6] == "text":
            ctx[(r[0], r[8], r[9])].append(r[5])
    occ = defaultdict(list)   # TOKEN -> occurrences
    seq = []
    for r in rows:
        line = " ".join(ctx[(r[0], r[8], r[9])]) if r[6] == "text" else r[5]
        for piece in r[5].split():
            if re.search(r"\d", piece):  # stations, pay items, dimensions, sheet IDs
                continue
            for tok in re.findall(r"[A-Za-z][A-Za-z']*[A-Za-z]|[A-Za-z]", piece):
                T = tok.upper().strip("'")
                item = dict(page=r[0], sheet_id=sheet.get(r[0]), rect=[round(v, 1) for v in r[1:5]], source=r[6],
                            conf=round(r[7], 2), word=tok, line=line[:160])
                seq.append((T, item, r))
                if len(T) >= 3:
                    occ[T].append(item)
    vocab = set(occ)
    known = {w for w in vocab if w in allow or not sp.unknown([w.lower()])}
    unknown = vocab - known
    # unknown words that recur consistently on several sheets of the text layer are probably names
    def sheets_of(w):
        return {o["sheet_id"] for o in occ[w] if o["source"] == "text"}
    variants = []
    for w in sorted(unknown):
        near = [k for k in known | unknown if k != w and len(k) >= 5 and edit1(w, k)
                and not (k == w + "S" or w == k + "S" or k == w + "ES" or w == k + "ES")]
        if near:
            for k in near:
                if (k, w) not in {(v["a"], v["b"]) for v in variants}:
                    variants.append(dict(a=w, b=k, count_a=len(occ[w]), count_b=len(occ[k]),
                                         where_a=occ[w][:5], where_b=occ[k][:5]))
    # short words: a same-length swap or substitution of a dictionary word (RAOD/ROAD) is a typo, not a name
    for w in sorted(unknown):
        if len(w) == 4 and not any(v["a"] == w for v in variants):
            fix = (sp.correction(w.lower()) or "").upper()
            if fix and fix != w and len(fix) == len(w) and edit1(w, fix) and fix in known:
                variants.append(dict(a=w, b=fix, count_a=len(occ[w]), count_b=len(occ[fix]),
                                     where_a=occ[w][:20], where_b=occ[fix][:5], note="4-letter swap of a dictionary word"))
    names = {w for w in unknown if len(sheets_of(w)) >= 3 and not any(v["a"] == w or v["b"] == w for v in variants)}
    cands = []
    for w in sorted(unknown - names):
        if len(w) < 3:
            continue
        sug = sp.correction(w.lower())
        cands.append(dict(word=w, suggestion=(sug or "").upper() or None, count=len(occ[w]),
                          ocr_only=all(o["source"] == "ocr" for o in occ[w]), where=occ[w][:8]))
    repeated = []
    for (t1, i1, r1), (t2, i2, r2) in zip(seq, seq[1:]):
        same_line = (r1 is r2) or (r1[6] == r2[6] == "text" and r1[0] == r2[0] and r1[8:10] == r2[8:10]
                                   and 0 <= r2[1] - r1[3] < (r1[4] - r1[2]) * 1.5)
        if t1 == t2 and len(t1) > 1 and same_line and t1 not in {"LT", "RT", "EA", "LF", "SY", "CY"}:
            repeated.append(dict(word=t1, **{k: i2[k] for k in ("page", "sheet_id", "rect", "source", "line")}))
    save_json(a.out, dict(unknown=cands, repeated=repeated, variants=variants, likely_names=sorted(names)))
    print(json.dumps(dict(words=len(vocab), unknown=len(cands), repeated=len(repeated), variants=len(variants),
                          likely_names=len(names))))


if __name__ == "__main__":
    main()
