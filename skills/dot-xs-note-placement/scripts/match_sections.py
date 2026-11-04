#!/usr/bin/env python3
"""Find each note's cross-section drawing model in the XS DGN files (read-only).

  match_sections.py <work_dir> <xs1.dgn> [<xs2.dgn> ...] [--group "MLUS51"] [--decisions decisions.json]
                    [--close 0.5]

Reads the model names out of each OpenRoads V8 DGN (an OLE file with zlib-compressed streams; read-only, nothing is
written to the DGN). Dynamic cross-section drawing models are named "<group> - <station>", e.g.
"MLUS51 - 471+91.4300"; their sheet models end in "[Sheet]" and are ignored. The group (named boundary group) is
detected as the most common prefix unless --group is given.

Each note in <work_dir>/notes_to_add.json gets dgn_file, dgn_section, dgn_offset_ft and a status:
  EXACT          a section at the note's station (within 0.01 ft)
  CLOSE          a section within --close ft (default 0.5): same structure, the note just rounds the station
  NEEDS DECISION farther than that: ask the engineer (place on nearest section / cut a new section / skip)
  NEAREST | CUT | SKIP   the engineer's answer from --decisions ({"NM-151": "nearest", "NM-181": "cut", ...})
CUT notes get new_section_sta = the note's station: the engineer cuts that section by hand before running the macro.
Writes notes_to_add.json/.csv back and xs_sections.json (every section found, per file).
"""
import argparse, collections, csv, json, re, sys, zlib
from pathlib import Path

try:
    import olefile
except ImportError:
    sys.exit("STOP: olefile is not installed.\nFIX: pip3 install olefile")

MODEL = re.compile(r"^(.+?) - (\d+)\+(\d+(?:\.\d+)?)(\s*\[Sheet\])?\s*$")


def strings(b, n=3):
    out = [m.decode("utf-16le") for m in re.findall(rb"(?:[\x20-\x7e]\x00){%d,}" % n, b)]
    out += [m.decode() for m in re.findall(rb"[\x20-\x7e]{%d,}" % (n + 3), b)]
    return out


def model_names(path):
    if not olefile.isOleFile(str(path)):
        sys.exit(f"STOP: {path} is not a V8/CONNECT DGN (not an OLE file).\nFIX: check the file; V7 DGNs are not supported.")
    o = olefile.OleFileIO(str(path))
    names = set()
    for e in o.listdir():
        if e[-1] != "Dgn~Mh":
            continue
        b = o.openstream("/".join(e)).read()
        if b[:1] == b"x":
            try:
                b = zlib.decompress(b)
            except zlib.error:
                pass
        for s in strings(b):
            s = s.strip().rstrip("@").strip()
            if MODEL.match(s):
                names.add(s)
    o.close()
    return names


def sta_ft(label):
    m = re.search(r"(\d+)\+(\d+(?:\.\d+)?)", label)
    return int(m.group(1)) * 100 + float(m.group(2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work"); ap.add_argument("dgns", nargs="+")
    ap.add_argument("--group"); ap.add_argument("--decisions"); ap.add_argument("--close", type=float, default=0.5)
    a = ap.parse_args()
    work = Path(a.work)
    notes = json.load(open(work / "notes_to_add.json"))
    decisions = json.load(open(a.decisions)) if a.decisions else {}

    found = {}
    for d in a.dgns:
        p = Path(d)
        names = model_names(p)
        found[p.name] = names
        print(f"{p.name}: {sum(1 for n in names if '[Sheet]' not in n)} section models, "
              f"{sum(1 for n in names if '[Sheet]' in n)} sheet models")
    groups = collections.Counter(MODEL.match(n).group(1) for ns in found.values() for n in ns)
    if not groups:
        sys.exit("STOP: no '<group> - <station>' models found in these files.\n"
                 "FIX: these may not be the dynamic cross-section files; ask the engineer which DGN holds the sections.")
    group = a.group or groups.most_common(1)[0][0]
    if not a.group and len(groups) > 1:
        print(f"ASK: several model groups found {dict(groups)}; using '{group}'. Confirm with the engineer (--group).")
    sections = []
    for f, names in found.items():
        for n in names:
            m = MODEL.match(n)
            if m.group(1) == group and not m.group(4):
                sections.append((int(m.group(2)) * 100 + float(m.group(3)), f"{m.group(2)}+{m.group(3)}", f))
    if not sections:
        sys.exit(f"STOP: no '{group} - <station>' section models.\nFIX: check --group")
    sections.sort()
    dup = [k for k, v in collections.Counter(round(s[0], 2) for s in sections).items() if v > 1]
    if dup:
        print(f"ASK: {len(dup)} stations have a section in more than one file: {dup[:10]}")
    json.dump({"group": group, "group_prefix": f"{group} - ",
               "sections": [{"sta": s[0], "label": s[1], "file": s[2]} for s in sections]},
              open(work / "xs_sections.json", "w"), indent=1)
    by_file = collections.defaultdict(list)
    for s in sections:
        by_file[s[2]].append(s[0])
    for f, v in sorted(by_file.items()):
        print(f"  {f}: {len(v)} sections, {v[0] / 100:.2f} to {v[-1] / 100:.2f} (x100 ft)")

    counts = collections.Counter()
    for n in notes:
        near = min(sections, key=lambda s: abs(s[0] - n["sta"]))
        off = round(n["sta"] - near[0], 4)
        n.update(dgn_file=near[2], dgn_section=near[1], dgn_offset_ft=off)
        n.pop("new_section_sta", None)
        d = (decisions.get(n["id"]) or "").lower()
        if abs(off) < 0.01:
            n["status"] = "EXACT"
        elif abs(off) <= a.close:
            n["status"] = "CLOSE"
        elif d in ("nearest", "cut", "skip"):
            n["status"] = d.upper()
            if d == "cut":
                n["new_section_sta"] = re.search(r"\d+\+\d+(?:\.\d+)?", n["station"]).group(0)
                # a cut section belongs in the file whose station range holds it
                inside = [f for f, v in by_file.items() if v[0] <= n["sta"] <= v[-1]]
                if inside:
                    n["dgn_file"] = inside[0]
        else:
            n["status"] = "NEEDS DECISION"
        counts[n["status"]] += 1
    json.dump(notes, open(work / "notes_to_add.json", "w"), indent=1)
    with open(work / "notes_to_add.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "kind", "station", "side", "status", "dgn_file", "section", "offset_ft", "profile_sheet",
                    "note_text (lines split by |)"])
        for n in notes:
            w.writerow([n["id"], n["kind"], n["station"], n["side"], n["status"], n["dgn_file"],
                        n.get("new_section_sta") or n["dgn_section"], n["dgn_offset_ft"], n["profile_sheet"],
                        " | ".join(n["lines"])])
    print(f"group '{group}'; " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    for n in notes:
        if n["status"] == "NEEDS DECISION":
            print(f"ASK: {n['id']} {n['station']} ({n['kind']}): nearest section {n['dgn_section']} in "
                  f"{n['dgn_file']} is {n['dgn_offset_ft']:+.2f} ft away -> nearest / cut / skip?")
        elif n["status"] == "CUT":
            print(f"CUT: {n['id']} needs a new section at {n['new_section_sta']} in {n['dgn_file']}")


if __name__ == "__main__":
    main()
