#!/usr/bin/env python3
"""Audit log: one readable entry per run, appended to <qaqc_memory>/audit_log.md (never rewritten).

  audit_log.py event  <work_dir> <kind> "<text>"         log something as it happens during the run
  audit_log.py append <work_dir> <memory_dir> --run <run_id> --plan-set "<pdf name>" [--checks notematch,...]

Event kinds (use them as the run goes, one line each):
  ran        a skill, script or agent that ran, with model/effort ("note-match agent, sonnet high")
  looked     what was looked at that the numbers below do not show ("rendered XS-9065 at 250 dpi to read the drive note")
  problem    something that went wrong or could not be read ("XS-9102 has no text layer; read visually")
  decision   a call made during the run and why ("cleared NM-E02: label found on WK-44RT")
  improve    what will change next time ("agent brief: driveway notes on the XS put LT/RT on the drive line")

`append` builds the entry from the events plus the run's own files in <work_dir>: index/index.json (pages read),
notematch/note_match.json (notes compared), coverage_first.json / coverage_final.json (coverage gate before and
after the send-back), findings_reviewed.json (verdicts), grade.json (grader score, rejections, misses, lessons).
The entry has: what it looked at, what ran, results, what went wrong, how it will improve.
"""
import argparse, datetime, json, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qaqc_common import load_json  # noqa: E402

KINDS = ("ran", "looked", "problem", "decision", "improve")
NAMES = {"index": "Index check", "spelling": "Spelling", "overlap": "Overlapping text", "notematch": "Note match",
         "color": "Print color", "quantity": "Quantities", "placeholder": "Placeholders"}


def events(work):
    p = os.path.join(work, "run_log.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def cmd_event(work, kind, text):
    if kind not in KINDS:
        sys.exit(f"kind must be one of {KINDS}")
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, "run_log.jsonl"), "a") as f:
        f.write(json.dumps(dict(t=datetime.datetime.now().isoformat(timespec="seconds"), kind=kind, text=text)) + "\n")


def bullets(lines, empty="none"):
    return "\n".join(f"- {l}" for l in lines) if lines else f"- {empty}"


def cmd_append(work, mem, run, plan_set, checks):
    ev = events(work)
    by = lambda k: [e["text"] for e in ev if e["kind"] == k]
    idx = load_json(os.path.join(work, "index", "index.json"), {}) or {}
    pages = idx.get("pages", [])
    nm = load_json(os.path.join(work, "notematch", "note_match.json"), {}) or {}
    cov1 = load_json(os.path.join(work, "coverage_first.json"), {}) or {}
    cov2 = load_json(os.path.join(work, "coverage_final.json"), {}) or {}
    data = load_json(os.path.join(work, "findings_reviewed.json"), {}) or {}
    grade = load_json(os.path.join(work, "grade.json"), {}) or {}
    rounds = [g for g in (load_json(os.path.join(work, "grade_round1.json"), {}) or {}, grade) if g]
    F = data.get("findings", [])
    checks = checks or data.get("tasks") or sorted({f.get("task") for f in F})

    # ---- what it looked at
    looked = []
    if pages:
        pre = Counter((p.get("prefix") or "?").upper() for p in pages)
        looked.append(f"Indexed {len(pages)} pages (" + ", ".join(f"{k} {v}" for k, v in pre.most_common(8)) + ")")
    s = nm.get("summary") or {}
    if s:
        looked.append(f"Note match: {s.get('profile_notes')} profile notes on {s.get('wk_pages')} WK sheets, "
                      f"{s.get('xs_pages')} cross-section sheets; {s.get('plan_checks')} plan-vs-profile and "
                      f"{s.get('xs_checks')} profile-vs-XS comparisons; {s.get('eye_checks', 0)} items sent for a "
                      "by-eye check")
        for k, v in (s.get("one_sided_by_kind") or {}).items():
            if v.get("profile_only") or v.get("xs_only"):
                looked.append(f"  script, before review: {k} {v.get('profile_only', 0)} shown in the profile only, "
                              f"{v.get('xs_only', 0)} on the cross section only")
    looked += by("looked")

    # ---- results
    res = []
    for t in checks:
        ft = [f for f in F if f.get("task") == t]
        v = Counter((f.get("review") or {}).get("verdict", "uncertain") for f in ft)
        call = sum(1 for f in ft if (f.get("review") or {}).get("verdict") == "confirmed" and f.get("unsure"))
        sev = Counter(f.get("severity") for f in ft if (f.get("review") or {}).get("verdict") == "confirmed")
        if ft or t in cov2 or t in cov1:
            res.append(f"{NAMES.get(t, t)}: {v.get('confirmed', 0)} confirmed (high {sev.get('high', 0)}, medium "
                       f"{sev.get('medium', 0)}, low {sev.get('low', 0)}), {v.get('uncertain', 0) + call} Unsure "
                       f"({call} of them confirmed facts left to the engineer's call), {v.get('rejected', 0)} rejected")
    for i, g in enumerate(rounds, 1):
        def score(c):
            sc = c.get("scores") or {}
            if isinstance(sc, dict) and sc:
                fails = [k for k, v in sc.items() if str(v).lower().startswith("fail")]
                return f"{len(sc) - len(fails)}/{len(sc)}" + (f", failed criteria {', '.join(fails)}" if fails else "")
            return str(c.get("score", ""))
        sb = "; ".join(f"{NAMES.get(t, t)} {score(c)}".strip() for t, c in (g.get("checks") or {}).items())
        res.append(f"Grader round {i}: {g.get('result', '?')}" + (f" ({sb})" if sb else ""))

    # ---- what went wrong
    wrong = []
    for t, c in cov1.items():
        if c.get("unresolved") or c.get("bad_clears"):
            after = cov2.get(t, {})
            wrong.append(f"{NAMES.get(t, t)} agent left {len(c.get('unresolved', []))} candidate(s) unresolved and "
                         f"{len(c.get('bad_clears', []))} clear(s) without sheet/text on the first pass; after the "
                         f"send-back {len(after.get('unresolved', [])) if after else '?'} were still unresolved "
                         "(now Unsure rows)")
    gate_fail = Counter(f.get("task") for f in F if f.get("gate") and not f["gate"].get("pass"))
    for t, n in gate_fail.items():
        wrong.append(f"{NAMES.get(t, t)}: {n} flag(s) failed the evidence gate (quoted text not found on the sheet)")
    rej = [f for f in F if (f.get("review") or {}).get("verdict") == "rejected"]
    for t, n in Counter(f.get("task") for f in rej).items():
        reasons = [((f.get("review") or {}).get("note") or "")[:110] for f in rej if f.get("task") == t][:3]
        wrong.append(f"{NAMES.get(t, t)}: {n} flag(s) rejected on review, e.g. " + " | ".join(r for r in reasons if r))
    for i, g in enumerate(rounds, 1):
        for t, c in (g.get("checks") or {}).items():
            for m in c.get("missed", [])[:5]:
                wrong.append(f"Grader round {i} found a miss in {NAMES.get(t, t)} (see Decisions for how it was "
                             f"handled): {m.get('what') if isinstance(m, dict) else m}")
    wrong += by("problem")

    # ---- how it will improve
    imp = by("improve") + [f"Proposed lesson (needs your OK): {l}"
                           for l in dict.fromkeys(l for g in rounds for l in g.get("lessons", []))]
    lessons_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "lessons.md")
    if os.path.exists(lessons_p):
        n = sum(1 for l in open(lessons_p) if l.startswith("- "))
        imp.append(f"{n} approved lesson(s) in lessons.md were applied this run")

    entry = f"""
## Run {run}: {plan_set}
{datetime.datetime.now():%Y-%m-%d %H:%M} · checks: {", ".join(NAMES.get(t, t) for t in checks)}

**What it looked at**
{bullets(looked)}

**What ran**
{bullets(by("ran"), "no events logged (orchestrator did not call `audit_log.py event ... ran`)")}

**Results**
{bullets(res)}

**What went wrong**
{bullets(wrong)}

**Decisions made during the run**
{bullets(by("decision"))}

**How it will improve**
{bullets(imp)}
"""
    os.makedirs(mem, exist_ok=True)
    p = os.path.join(mem, "audit_log.md")
    new = not os.path.exists(p)
    with open(p, "a") as f:
        if new:
            f.write("# QA/QC audit log\n\nOne entry per run, newest at the bottom. Written by the skill at the end "
                    "of every run; never edited afterwards.\n")
        f.write(entry)
    print(f"appended run {run} to {p}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("event"); e.add_argument("work"); e.add_argument("kind"); e.add_argument("text")
    a = sub.add_parser("append"); a.add_argument("work"); a.add_argument("mem")
    a.add_argument("--run", required=True); a.add_argument("--plan-set", default="")
    a.add_argument("--checks", default="")
    x = ap.parse_args()
    if x.cmd == "event":
        cmd_event(x.work, x.kind, x.text)
    else:
        cmd_append(x.work, x.mem, x.run, x.plan_set, [c for c in x.checks.split(",") if c])


if __name__ == "__main__":
    main()
