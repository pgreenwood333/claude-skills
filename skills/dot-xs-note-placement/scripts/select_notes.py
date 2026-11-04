#!/usr/bin/env python3
"""Pick the profile notes that must be added to the cross sections.

  select_notes.py <note_match.json | findings_reviewed.json> <work_dir>
                  [--skip-through 337+08.26] [--only-from 300+00] [--only-to 510+00]
                  [--keep-removal-only] [--exclude NM-012,NM-044]

Input: the QA/QC note-match output (dot-plan-set-qaqc: qaqc_work/notematch/note_match.json, or the reviewed
findings qaqc_work/findings_reviewed.json). Every finding whose discrepancy says "MISSING on cross section" is a
profile note with no cross-section copy; its text is taken line for line from the profile.

Engineer's rule (default): a drainage note that ONLY removes or abandons existing drainage (EXIST. PIPE, REMOVE,
flowable fill, with no proposed structure or pipe) goes on the plan and profile only, not the cross sections, so it
is dropped. A note that combines a proposed structure with a removal is kept. --keep-removal-only turns this off.

Side (LT/RT) comes from the profile sheet the note is on (WK-30LT -> LT); if the sheet has no side, from the
note text; if neither, it is left blank and must be asked.

Writes <work_dir>/notes_to_add.json and notes_to_add.csv (for the engineer to review), and prints what was dropped
and why, plus the notes missing from the PROFILE (shown on the XS only), which this skill does not place.
"""
import argparse, csv, json, re, sys
from pathlib import Path

PROPOSED = re.compile(r"SS-\d|JB-|MI-\d|FE-\d|BC-\d|PC-\d|\bBOX\b|DRIVE|INLET|HEADWALL|"
                      r"(RCP|RCAP|ALT\.? PIPE|PIPE) ?REQ'D", re.I)
REMOVES = re.compile(r"EXIST\.? PIPE|FLOWABLE|\bREMOVE", re.I)


def sta_ft(label):
    m = re.search(r"(\d+)\+(\d+(?:\.\d+)?)", label)
    if not m:
        raise ValueError(f"no station in {label!r}")
    return int(m.group(1)) * 100 + float(m.group(2))


def removal_only(lines):
    t = " ".join(lines)
    return bool(REMOVES.search(t)) and not PROPOSED.search(t)


def side_of(sheet, lines):
    m = re.search(r"(LT|RT)\b", sheet or "")
    if m:
        return m.group(1)
    t = " ".join(lines)
    lt, rt = bool(re.search(r"\bLT\b", t)), bool(re.search(r"\bRT\b", t))
    return "LT" if lt and not rt else "RT" if rt and not lt else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings"); ap.add_argument("work")
    ap.add_argument("--skip-through", help="drop notes at or before this station (already fixed)")
    ap.add_argument("--only-from"); ap.add_argument("--only-to")
    ap.add_argument("--keep-removal-only", action="store_true")
    ap.add_argument("--exclude", default="", help="comma-separated finding ids to leave out")
    a = ap.parse_args()

    data = json.load(open(a.findings))
    findings = data["findings"] if isinstance(data, dict) else data
    if not isinstance(findings, list) or not findings:
        sys.exit(f"STOP: no findings list in {a.findings}\nFIX: point at qaqc_work/notematch/note_match.json "
                 "or qaqc_work/findings_reviewed.json from an dot-plan-set-qaqc run")
    missing = [f for f in findings if "MISSING on cross section" in (f.get("discrepancy") or "")]
    xs_only = [f for f in findings if "MISSING in profile" in (f.get("discrepancy") or "")]
    if not missing:
        sys.exit("STOP: the note-match output has no 'MISSING on cross section' findings.\n"
                 "FIX: confirm the note-match check ran on both the WK and XS sheets (its summary prints "
                 "profile_without_xs); if it really found none, there is nothing to place.")
    rejected = {f["id"] for f in findings if (f.get("review") or {}).get("verdict") == "rejected"}
    exclude = {x.strip() for x in a.exclude.split(",") if x.strip()}
    lo = sta_ft(a.only_from) if a.only_from else None
    hi = sta_ft(a.only_to) if a.only_to else None
    done = sta_ft(a.skip_through) if a.skip_through else None

    rows, dropped = [], []
    for f in sorted(missing, key=lambda f: f["note"]["sta"]):
        n = f["note"]
        sheet, _, body = (n.get("profile") or "").partition(": ")
        lines = [l.strip() for l in body.split(" | ") if l.strip()]
        sta = n["sta"]
        why = None
        if not lines:
            why = "no profile text in the finding (check it by hand)"
        elif f["id"] in rejected:
            why = "rejected in the QA/QC review"
        elif f["id"] in exclude:
            why = "excluded by the engineer"
        elif done is not None and sta <= done:
            why = f"at or before {a.skip_through} (already fixed)"
        elif (lo is not None and sta < lo) or (hi is not None and sta > hi):
            why = "outside the station range asked for"
        elif not a.keep_removal_only and removal_only(lines):
            why = "removal/abandon only: plan + profile only, not the XS (engineer's rule)"
        if why:
            dropped.append((f["id"], n.get("station"), why, " | ".join(lines)))
            continue
        rows.append({"id": f["id"], "kind": n.get("kind", ""), "station": n.get("station", ""), "sta": sta,
                     "side": side_of(sheet, lines), "profile_sheet": sheet, "lines": lines})

    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(work / "notes_to_add.json", "w"), indent=1)
    with open(work / "notes_to_add.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "kind", "station", "side", "profile_sheet", "note_text (lines split by |)"])
        for r in rows:
            w.writerow([r["id"], r["kind"], r["station"], r["side"], r["profile_sheet"], " | ".join(r["lines"])])

    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"{len(missing)} profile notes missing on the cross sections; {len(rows)} to add "
          f"({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}); {len(dropped)} dropped:")
    for d in dropped:
        print(f"  dropped {d[0]} {d[1]}: {d[2]}  |  {d[3]}")
    noside = [r["id"] + " " + r["station"] for r in rows if not r["side"]]
    if noside:
        print(f"ASK: no LT/RT side for {len(noside)} notes: {', '.join(noside)}")
    if xs_only:
        print(f"note: {len(xs_only)} notes are on the cross section but missing in the PROFILE "
              "(this skill does not place those; list them for the engineer):")
        for f in xs_only:
            print(f"  {f['id']} {f['note'].get('station')}: {f['note'].get('xs')}")


if __name__ == "__main__":
    main()
