#!/usr/bin/env python3
"""Run memory: record how each run's flags were judged, take the engineer's corrections, and propose lessons.

  learn.py record   <work_dir> <memory_dir> [--plan-set NAME]      after the run is delivered
  learn.py feedback <memory_dir> <run_id> <flag_id> confirmed|rejected|missed "<note>" [--task T]
  learn.py lessons  <memory_dir>                                  candidate lessons to show the engineer
  learn.py accept   <memory_dir> <task> "<lesson text>"           engineer approved: add to lessons.md
  learn.py stats    <memory_dir>                                  precision per check over time
  learn.py ingest   <returned.xlsx> <memory_dir> <run_id> [--work <work_dir>]
                    read the engineer's Review dropdowns from a returned workbook: N/A = the flag was wrong
                    (recorded as rejected, so lessons can be proposed), Correct = fixed (confirmed), Incorrect =
                    still open (nothing recorded). With --work, also saves each answer on the finding
                    (`engineer_review`) so a rebuilt workbook keeps the engineer's choices.

Files in <memory_dir> (keep it with the user's plan-set folders, never inside the skill):
  ledger.jsonl  one line per flag per run: run, task, rule/keywords, grader verdict, engineer verdict, notes
  lessons.md    approved lessons, one section per check; agents and the grader read it at the start of a run
Safety against learning the wrong thing (drift):
  - The engineer's verdict outranks the grader's; a lesson is only proposed when the same pattern shows up in at
    least 2 different runs; nothing reaches lessons.md without the engineer's OK (`accept`).
  - lessons.md is capped at 12 lessons per check; `lessons` warns when a section is full so old ones get merged.
"""
import datetime, json, os, re, sys
from collections import Counter, defaultdict

CAP = 12
TASK_BY_PREFIX = {"SPL": "spelling", "NM": "notematch", "OVL": "overlap", "COL": "color", "IDX": "index",
                  "QTY": "quantity", "ORD": "index"}


def ledger(mem):
    p = os.path.join(mem, "ledger.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def append(mem, rows):
    os.makedirs(mem, exist_ok=True)
    with open(os.path.join(mem, "ledger.jsonl"), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def keywords(f):
    words = re.findall(r"[A-Z][A-Z'.\"]{2,}", (f.get("evidence") or "").upper())
    return sorted(set(words))[:6]


def cmd_record(work, mem, name=None):
    data = json.load(open(os.path.join(work, "findings_reviewed.json")))
    grade = {}
    gp = os.path.join(work, "grade.json")
    if os.path.exists(gp):
        grade = json.load(open(gp))
    run = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    rows = []
    for f in data.get("findings", []):
        rows.append(dict(run=run, plan_set=name, task=f.get("task"), id=f.get("id"), severity=f.get("severity"),
                         rules=f.get("rules"), keywords=keywords(f), evidence=(f.get("evidence") or "")[:160],
                         gate=(f.get("gate") or {}).get("pass"), verdict=(f.get("review") or {}).get("verdict"),
                         note=(f.get("review") or {}).get("note"), engineer=None))
    for task, c in (grade.get("checks") or {}).items():
        for m in c.get("missed", []):
            rows.append(dict(run=run, plan_set=name, task=task, id="MISSED", verdict="missed",
                             note=m.get("what"), keywords=[], engineer=None))
    for l in grade.get("lessons", []):
        rows.append(dict(run=run, plan_set=name, task=l.split(":")[0].strip(), id="LESSON", verdict="proposed",
                         note=l, keywords=[], engineer=None))
    append(mem, rows)
    print(json.dumps(dict(run=run, rows=len(rows)), indent=1))


def cmd_feedback(mem, run, fid, verdict, note, task=None, quiet=False):
    rows = ledger(mem)
    hit = [r for r in rows if r.get("run") == run and r.get("id") == fid]
    if hit:
        for r in hit:
            r["engineer"] = verdict
            r["engineer_note"] = note
        with open(os.path.join(mem, "ledger.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    else:   # something the run missed entirely
        append(mem, [dict(run=run, task=task or TASK_BY_PREFIX.get(fid.split("-")[0]), id=fid,
                          verdict="missed" if verdict == "missed" else None, engineer=verdict, engineer_note=note,
                          keywords=[])])
    if not quiet:
        print("recorded")


def cmd_ingest(xlsx, mem, run, work=None):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    answers = defaultdict(list)          # flag id -> [(tab, sheet id, answer, what was flagged)]
    for ws in wb.worksheets:
        head = [c.value for c in ws[1]]
        if "Review" not in head or "Flag ID" not in head:
            continue
        ri, fi = head.index("Review"), head.index("Flag ID")
        wi = next((i for i, h in enumerate(head) if h in ("What's Wrong", "Text Found")), 2)
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[fi]:
                answers[row[fi]].append((ws.title, row[0], (row[ri] or "Incorrect").strip(), row[wi]))
    counts = Counter()
    for fid, rs in answers.items():
        vals = {a for _, _, a, _ in rs}
        if "N/A" in vals:
            sheets = ", ".join(str(s) for _, s, a, _ in rs if a == "N/A")
            cmd_feedback(mem, run, fid, "rejected", f"engineer marked N/A (nothing to fix) on {sheets}: {rs[0][3]}",
                         task=None, quiet=True)
            counts["N/A"] += 1
        elif vals == {"Correct"}:
            cmd_feedback(mem, run, fid, "confirmed", "engineer fixed it on the plans", task=None, quiet=True)
            counts["Correct"] += 1
        else:
            counts["open"] += 1
    if work:
        p = os.path.join(work, "findings_reviewed.json")
        data = json.load(open(p))
        for f in data["findings"]:
            rs = answers.get(f["id"])
            if rs:
                vals = {a for _, _, a, _ in rs}
                f["engineer_review"] = "N/A" if "N/A" in vals else ("Correct" if vals == {"Correct"} else "Incorrect")
        json.dump(data, open(p, "w"), indent=1)
    print(json.dumps(dict(flags=len(answers), **counts), indent=1))
    print("Next: `learn.py lessons` to see if the N/A answers point to a rule worth adding.")


def final(r):
    return r.get("engineer") or r.get("verdict")


def cmd_stats(mem):
    by = defaultdict(Counter)
    for r in ledger(mem):
        if r.get("id") in ("LESSON",):
            continue
        by[r.get("task")][final(r)] += 1
    out = {}
    for t, c in by.items():
        judged = c["confirmed"] + c["rejected"]
        out[t] = dict(c, precision=round(c["confirmed"] / judged, 2) if judged else None)
    print(json.dumps(out, indent=1))


def cmd_lessons(mem):
    rows = ledger(mem)
    props = []
    # 1) rejections that repeat across runs: same task + same keyword or rule
    rej = defaultdict(set)
    notes = defaultdict(list)
    for r in rows:
        if final(r) == "rejected":
            for k in (r.get("rules") or []) + (r.get("keywords") or []):
                rej[(r["task"], k)].add(r["run"])
                notes[(r["task"], k)].append(r.get("engineer_note") or r.get("note"))
    for (task, k), runs in rej.items():
        if len(runs) >= 2:
            props.append(dict(task=task, kind="false alarm", pattern=k, runs=len(runs),
                              examples=[n for n in notes[(task, k)] if n][:3]))
    # 2) misses that repeat
    miss = defaultdict(set)
    for r in rows:
        if final(r) == "missed":
            miss[(r.get("task"), (r.get("engineer_note") or r.get("note") or "")[:40])].add(r["run"])
    for (task, n), runs in miss.items():
        props.append(dict(task=task, kind="missed", pattern=n, runs=len(runs)))
    # 3) grader-proposed lessons seen in 2+ runs
    gl = defaultdict(set)
    for r in rows:
        if r.get("id") == "LESSON":
            gl[(r.get("task"), r.get("note"))].add(r["run"])
    for (task, n), runs in gl.items():
        if len(runs) >= 2:
            props.append(dict(task=task, kind="grader", pattern=n, runs=len(runs)))
    full = [t for t, n in section_counts(mem).items() if n >= CAP]
    print(json.dumps(dict(proposed=props, sections_full=full,
                          how="Show these to the engineer. Only `accept` the ones they agree with, in your own "
                              "words, as a rule the agents can follow."), indent=1))


def section_counts(mem):
    p = os.path.join(mem, "lessons.md")
    counts, cur = Counter(), None
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("## "):
                cur = line[3:].strip()
            elif line.startswith("- ") and cur:
                counts[cur] += 1
    return counts


def cmd_accept(mem, task, text):
    os.makedirs(mem, exist_ok=True)
    p = os.path.join(mem, "lessons.md")
    lines = open(p).read().splitlines() if os.path.exists(p) else [
        "# QA/QC lessons (approved by the engineer)", "",
        "Agents and the grader read their section before a run. These override the defaults in the briefs.", ""]
    if section_counts(mem).get(task, 0) >= CAP:
        sys.exit(f"{task} already has {CAP} lessons: merge or remove some first")
    date = datetime.date.today().isoformat()
    head = f"## {task}"
    if head not in lines:
        lines += [head, ""]
    i = lines.index(head) + 1
    while i < len(lines) and not lines[i].startswith("## "):
        i += 1
    while lines[i - 1] == "":
        i -= 1
    lines.insert(i, f"- {text} ({date})")
    open(p, "w").write("\n".join(lines) + "\n")
    print(f"added to {p}")


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd, rest = a[0], a[1:]
    task = None
    if "--task" in rest:
        i = rest.index("--task"); task = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
    name = None
    if "--plan-set" in rest:
        i = rest.index("--plan-set"); name = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
    if cmd == "record":
        cmd_record(rest[0], rest[1], name)
    elif cmd == "feedback":
        cmd_feedback(*rest[:5], task=task)
    elif cmd == "lessons":
        cmd_lessons(rest[0])
    elif cmd == "accept":
        cmd_accept(*rest[:3])
    elif cmd == "ingest":
        work = None
        if "--work" in rest:
            i = rest.index("--work"); work = rest[i + 1]; rest = rest[:i] + rest[i + 2:]
        cmd_ingest(rest[0], rest[1], rest[2], work)
    elif cmd == "stats":
        cmd_stats(rest[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
