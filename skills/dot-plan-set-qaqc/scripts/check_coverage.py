#!/usr/bin/env python3
"""Coverage gate: no agent may skip a candidate silently. Every candidate a check's script produced must end up
either kept (in that check's findings) or cleared with a reason. Whatever is neither becomes an Unsure flag.

  check_coverage.py <work_dir> [--tasks notematch,color,overlap,spelling,index] [--finalize]

Candidates (script output) per check:
  notematch  <work>/notematch/note_match.json      findings + eye_checks (ids NM-…, NM-E…)
  color      <work>/color/color_candidates.json    candidates (ids COL-C-…)
  overlap    <work>/overlap/overlap_candidates.json candidates (ids OVL-p…)
  spelling   <work>/spell_candidates.json           unknown / repeated / variants (ids SPC-U…, SPC-R…, SPC-V…)
  index      <work>/index_check/script_findings.json findings (ids IDX-…)
  (quantity flags go straight from reconcile.py into the merge, so none can be dropped.)

Kept: a finding in <work>/findings/<task>.json whose id is the candidate id, or that lists it in `candidate_ids`.
Cleared: an entry in <work>/findings/<task>_cleared.json:
  {"cleared": [{"ids": ["OVL-p12-003"], "reason": "stacked callout, both legible", "sheet": "WK-12",
                "seen": "`STA. 235+34.00` above `36' DRIVE REQ'D.`"}]}
  `reason` is always required. For every check but spelling, `sheet` and `seen` (what was read on the sheet) are
  required too: "cleared" means the agent looked, and says what it saw. Spelling may clear many words with one reason
  ("DOT abbreviation", "street name on 4 sheets").

Prints, per check: candidates, kept, cleared, bad clears, unresolved (with ids). Exit 1 if any are unresolved or
badly cleared, so the orchestrator sends that list back to the agent. With --finalize (after that one send-back),
writes the leftovers to <work>/findings/<task>_unresolved.json as flags with verdict `uncertain`, so they reach
the workbook as Unsure rows instead of disappearing.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qaqc_common import load_json, save_json  # noqa: E402

SOURCES = {"notematch": "notematch/note_match.json", "color": "color/color_candidates.json",
           "overlap": "overlap/overlap_candidates.json", "spelling": "spell_candidates.json",
           "index": "index_check/script_findings.json"}
NOTE = "The agent neither confirmed nor cleared this candidate: check it on the sheet."


def candidates(task, data):
    """[(id, ready-made flag)] for one check's script output."""
    out = []
    if task in ("notematch", "index"):
        for f in data.get("findings", []) + data.get("eye_checks", []):
            g = {k: v for k, v in f.items() if k != "look"}
            if f.get("look"):
                g["evidence"] = f"{g.get('evidence', '')} (look: {f['look']})"
            out.append((f["id"], g))
    elif task == "color":
        for c in data.get("candidates", []):
            out.append((c.get("id") or f"COL-C-{c['note_id']}", dict(task="color", severity="medium", sheet_ids=[c["sheet_id"]],
                                      pdf_pages=[c["pdf_page"]],
                                      finding=f"Possible print color problem ({', '.join(c['rules'])}) on {c['sheet_id']}",
                                      evidence=f"`{(c.get('line_colors') or [[c['text']]])[0][0][:120]}` "
                                               f"(note prints {c['color']})",
                                      suggested_fix="Check the print color against the rule",
                                      locate=[dict(page=c["pdf_page"], rect=c["rect"])], crop=c.get("crop"))))
    elif task == "overlap":
        for c in data.get("candidates", []):
            out.append((c["id"], dict(task="overlap", severity="medium", sheet_ids=[c["sheet_id"]],
                                      pdf_pages=[c["pdf_page"]], finding=f"Possible overlapping text on {c['sheet_id']}",
                                      evidence=(f"`{c['text_a']}` overlaps `{c['text_b']}`"
                                                if c.get("text_a", "").strip() and c.get("text_b", "").strip()
                                                else "overlapping linework/text with no text copy (see crop)"),
                                      suggested_fix="Move one of the labels so both read clearly",
                                      locate=[dict(page=c["pdf_page"], rect=c["overlap_rect"])], crop=c.get("crop"))))
    elif task == "spelling":
        for c in data.get("unknown", []):
            w = (c.get("where") or [{}])[0]
            out.append((c["id"], dict(task="spelling", severity="low", sheet_ids=[w.get("sheet_id") or ""],
                                      pdf_pages=[w.get("page")] if w.get("page") else [],
                                      finding=f"Possible misspelling `{c['word']}` ({c['count']}x)",
                                      evidence=f"`{w.get('word', c['word'])}` in `{(w.get('line') or '')[:100]}`",
                                      suggested_fix=c.get("suggestion") or "Check the spelling",
                                      locate=[dict(page=w["page"], text=w.get("word", c["word"]))] if w.get("page") else [])))
        for c in data.get("repeated", []):
            out.append((c["id"], dict(task="spelling", severity="low", sheet_ids=[c.get("sheet_id") or ""],
                                      pdf_pages=[c["page"]], finding=f"Repeated word `{c['word']} {c['word']}`",
                                      evidence=f"`{(c.get('line') or c['word'])[:100]}`",
                                      suggested_fix=f"Remove the repeated {c['word']}",
                                      locate=[dict(page=c["page"], text=c["word"])])))
        for c in data.get("variants", []):
            w = (c.get("where_a") or [{}])[0]
            out.append((c["id"], dict(task="spelling", severity="low", sheet_ids=[w.get("sheet_id") or ""],
                                      pdf_pages=[w.get("page")] if w.get("page") else [],
                                      finding=f"Inconsistent spelling `{c['a']}` vs `{c['b']}`",
                                      evidence=f"`{c['a']}`", suggested_fix=f"Use one spelling ({c['b']}?)",
                                      locate=[dict(page=w["page"], text=w.get("word", c["a"]))] if w.get("page") else [])))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("--tasks", default=",".join(SOURCES))
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args()
    report, failed = {}, False
    for task in [t for t in a.tasks.split(",") if t in SOURCES]:
        src = os.path.join(a.work, SOURCES[task])
        if not os.path.exists(src):
            continue
        cands = candidates(task, load_json(src, {}))
        kept_file = load_json(os.path.join(a.work, "findings", f"{task}.json"), {}) or {}
        kept = set()
        for f in kept_file.get("findings", []):
            kept.add(f.get("id"))
            kept.update(f.get("candidate_ids") or [])
        cleared, bad = set(), []
        for e in (load_json(os.path.join(a.work, "findings", f"{task}_cleared.json"), {}) or {}).get("cleared", []):
            need = ["reason"] + ([] if task == "spelling" else ["sheet", "seen"])
            miss = [k for k in need if not str(e.get(k) or "").strip()]
            if miss:
                bad.append(dict(ids=e.get("ids"), missing=miss))
            else:
                cleared.update(e.get("ids") or [])
        left = [(i, f) for i, f in cands if i not in kept and i not in cleared]
        report[task] = dict(candidates=len(cands), kept=sum(i in kept for i, _ in cands),
                            cleared=sum(i in cleared and i not in kept for i, _ in cands),
                            bad_clears=bad, unresolved=[i for i, _ in left])
        failed |= bool(left or bad)
        out = os.path.join(a.work, "findings", f"{task}_unresolved.json")
        if a.finalize:
            for i, f in left:
                f["id"] = i
                f["review"] = {"verdict": "uncertain", "note": NOTE}
                f["unresolved"] = True
            save_json(out, dict(findings=[f for _, f in left]))
        elif os.path.exists(out):
            os.remove(out)   # stale leftovers from an earlier finalize: recomputed on the next finalize
    print(json.dumps(report, indent=1))
    # kept for the audit log: the first pass (before any send-back) and the final one
    first = os.path.join(a.work, "coverage_first.json")
    save_json(os.path.join(a.work, "coverage_final.json") if a.finalize else
              (first if not os.path.exists(first) else os.path.join(a.work, "coverage_last.json")), report)
    if failed and not a.finalize:
        print("UNRESOLVED: send each check's `unresolved` and `bad_clears` back to its agent once "
              "(keep it as a flag, or clear it with reason + sheet + what you saw), then re-run; "
              "after that, run again with --finalize.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
