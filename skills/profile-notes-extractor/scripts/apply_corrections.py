"""Apply user-approved line edits to notes.json, then rebuild the doc as a new (Rev N).
Usage: python3 apply_corrections.py notes.json corrections.json
corrections.json: [{"id": "507 A", "old": "196' - 28\"X18\" RCAP REQ'D.", "new": "196' - 18\" RCP REQ'D."}, ...]
"id" is a note's first line (structure ID, or the STA line for drives). Each "old" line must match exactly once.
Only apply what the user approved; flag other suspected errors instead of fixing them."""
import json, sys

notes = json.load(open(sys.argv[1]))
fixes = json.load(open(sys.argv[2]))
for f in fixes:
    hits = [n for n in notes if n["lines"][0] == f["id"]]
    assert len(hits) == 1, f"{f['id']}: {len(hits)} notes match"
    L = hits[0]["lines"]
    idx = [i for i, t in enumerate(L) if t == f["old"]]
    assert len(idx) == 1, f"{f['id']}: line {f['old']!r} not found exactly once in {L}"
    L[idx[0]] = f["new"]
    print(f"{f['id']}: {f['old']}  ->  {f['new']}")
json.dump(notes, open(sys.argv[1], "w"), indent=1)
