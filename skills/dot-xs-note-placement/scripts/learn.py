#!/usr/bin/env python3
"""Job memory: record each job, take the engineer's corrections, and propose lessons (same idea as the QA/QC skill).

  learn.py record   <work_dir> [<memory_dir>] [--stage dryrun|place]   after you deliver the files, and again after PLACE
  learn.py feedback <memory_dir> <run_id> <note_id|RUN> ok|fix|bug "<their words>" [--stage S]
  learn.py ingest   <checklist.xlsx> <memory_dir> <run_id>              the engineer's returned checklist (OK / Fix)
  learn.py lessons  <memory_dir>                                        candidate lessons to show the engineer
  learn.py accept   <stage> "<rule>"                                    engineer approved: add to the skill's lessons.md
  learn.py stats    <memory_dir>                                        per job: notes placed, fixes, bugs

Stages (the sections of references/lessons.md): notes, sections, settings, macro, steps.
  notes     which notes, their text and side          sections  which section each note goes on, new sections
  settings  level, color, style, size, placement      macro     a VBA error, stop, or wrong result from the macro
  steps     the engineer's click path / instructions

Approved lessons live INSIDE the skill (references/lessons.md), so they ship to GitHub and Cowork.
The memory dir holds the job history and stays with the job folders, never inside the skill. Default: the nearest
`xs_notes_memory/` above the work dir, else one is created beside the work dir.
  ledger.jsonl  one line per note per run (and per correction): run, job, note, stage, engineer verdict, words
  audit_log.md  one readable entry per run, plus each correction as it comes in
Safety against learning the wrong thing:
  - A "fix" pattern is proposed as a lesson only when it shows up in 2 or more jobs. A "bug" (the macro itself was
    wrong) is proposed at once, but the code gets fixed first; the lesson records why.
  - Nothing reaches lessons.md without the engineer's OK (`accept`). At most 12 lessons per stage.
"""
import datetime, json, os, re, sys
from collections import Counter, defaultdict

CAP = 12
STAGES = ("notes", "sections", "settings", "macro", "steps")
LESSONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "lessons.md")
# words in an engineer's comment -> the stage it most likely belongs to (used when --stage is not given)
STAGE_WORDS = [("settings", r"corner|position|overlap|size|style|level|color|colour|weight|font|0\.01|left|right|top"),
               ("sections", r"section|station|nearest|cut"),
               ("notes", r"text|line|wrong note|missing|typo|side|LT|RT"),
               ("macro", r"error|stop|crash|compile|batch|log|remove")]


def guess_stage(text):
    for st, pat in STAGE_WORDS:
        if re.search(pat, text or "", re.I):
            return st
    return "notes"


def find_memory(work):
    d = os.path.abspath(work)
    while True:
        cand = os.path.join(d, "xs_notes_memory")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.join(os.path.dirname(os.path.abspath(work)), "xs_notes_memory")


def ledger(mem):
    p = os.path.join(mem, "ledger.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def write_ledger(mem, rows):
    with open(os.path.join(mem, "ledger.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def append(mem, rows):
    os.makedirs(mem, exist_ok=True)
    with open(os.path.join(mem, "ledger.jsonl"), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def audit(mem, text):
    os.makedirs(mem, exist_ok=True)
    with open(os.path.join(mem, "audit_log.md"), "a") as f:
        f.write(text.rstrip() + "\n")


def keywords(text):
    return sorted(set(w.lower() for w in re.findall(r"[A-Za-z]{4,}", text or "")) - {"note", "notes", "this", "that",
                  "with", "should", "were", "have", "from", "into", "they", "there"})[:8]


def cmd_record(work, mem, stage="dryrun"):
    notes = json.load(open(os.path.join(work, "notes_to_add.json")))
    settings = json.load(open(os.path.join(work, "macro_settings.json")))
    job = str(settings.get("job"))
    run = f"{job}-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}"
    rows = [dict(run=run, job=job, stage=stage, id=n["id"], station=n.get("station"), side=n.get("side"),
                 status=n.get("status"), file=n.get("dgn_file"), kind=n.get("kind"), engineer=None)
            for n in notes]
    append(mem, rows)
    per_file = Counter(n.get("dgn_file") for n in notes if n.get("status") != "SKIP")
    dec = Counter(n.get("status") for n in notes)
    nt = settings.get("note_text", {})
    audit(mem, f"\n## {run} (job {job}, {stage})\n"
               f"- Notes: {sum(per_file.values())} in {len(per_file)} files ("
               + ", ".join(f"{f}: {c}" for f, c in sorted(per_file.items())) + ")\n"
               f"- Sections: " + ", ".join(f"{k} {v}" for k, v in sorted(dec.items())) + "\n"
               f"- Settings: level {nt.get('level')}, color {nt.get('color')}, style {nt.get('text_style')}, "
               f"placement {json.dumps(settings.get('placement'))}\n")
    print(json.dumps(dict(run=run, notes=len(rows), memory=mem), indent=1))


def cmd_feedback(mem, run, nid, verdict, words, stage=None, quiet=False):
    if verdict not in ("ok", "fix", "bug"):
        sys.exit("verdict must be ok, fix or bug")
    stage = stage or ("macro" if verdict == "bug" else guess_stage(words))
    if stage not in STAGES:
        sys.exit(f"stage must be one of {STAGES}")
    rows = ledger(mem)
    hit = [r for r in rows if r.get("run") == run and r.get("id") == nid]
    for r in hit:
        r.update(engineer=verdict, words=words, stage_fb=stage, keywords=keywords(words))
    if hit:
        write_ledger(mem, rows)
    else:   # a correction about the whole run, or a note the run did not list
        append(mem, [dict(run=run, job=run.split("-")[0], id=nid, engineer=verdict, words=words, stage_fb=stage,
                          keywords=keywords(words))])
    if verdict != "ok":
        audit(mem, f"- {run} {verdict.upper()} [{stage}] {nid}: {words}")
    if not quiet:
        print(f"recorded {verdict} ({stage}) for {nid}")


def cmd_ingest(xlsx, mem, run):
    import openpyxl
    ws = openpyxl.load_workbook(xlsx, data_only=True).active
    head = [c.value for c in ws[1]]
    for need in ("ID", "Checked", "Comments"):
        if need not in head:
            sys.exit(f"STOP: {xlsx} has no '{need}' column.\nFIX: use the checklist make_checklist.py wrote.")
    ii, ci, mi = head.index("ID"), head.index("Checked"), head.index("Comments")
    sec = head.index("Section model") if "Section model" in head else None
    counts = Counter()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[ii]:
            continue
        val = str(row[ci] or "").strip().lower()
        if val == "ok":
            cmd_feedback(mem, run, row[ii], "ok", "", "notes", quiet=True); counts["ok"] += 1
        elif val == "fix":
            words = (row[mi] or "(no comment)") + (f" [{row[sec]}]" if sec is not None else "")
            cmd_feedback(mem, run, row[ii], "fix", words, quiet=True); counts["fix"] += 1
        else:
            counts["not checked"] += 1
    print(json.dumps(dict(counts), indent=1))
    if counts["fix"]:
        print("Next: read every Fix with the engineer, fix the cause, then `learn.py lessons`.")


def section_counts():
    counts, cur = Counter(), None
    if os.path.exists(LESSONS):
        for line in open(LESSONS):
            if line.startswith("## "):
                cur = line[3:].strip()
            elif line.startswith("- ") and cur:
                counts[cur] += 1
    return counts


def cmd_lessons(mem):
    rows = ledger(mem)
    props = []
    # 1) the same kind of fix in 2+ jobs: same stage and a shared keyword
    seen = defaultdict(set); words = defaultdict(list)
    for r in rows:
        if r.get("engineer") == "fix":
            for k in r.get("keywords") or []:
                seen[(r.get("stage_fb"), k)].add(r.get("job"))
                words[(r.get("stage_fb"), k)].append(r.get("words"))
    for (st, k), jobs in seen.items():
        if len(jobs) >= 2:
            props.append(dict(stage=st, kind="repeated fix", pattern=k, jobs=sorted(jobs), examples=words[(st, k)][:3]))
    # 2) every bug, at once (the code is fixed first; the lesson says why)
    for r in rows:
        if r.get("engineer") == "bug":
            props.append(dict(stage=r.get("stage_fb"), kind="bug", run=r.get("run"), what=r.get("words")))
    full = [s for s, n in section_counts().items() if n >= CAP]
    print(json.dumps(dict(proposed=props, sections_full=full,
                          how="Show these to the engineer. Only `accept` the ones they agree with, written as a rule "
                              "the next job can follow."), indent=1))


def cmd_accept(stage, text):
    if stage not in STAGES:
        sys.exit(f"stage must be one of {STAGES}")
    if section_counts().get(stage, 0) >= CAP:
        sys.exit(f"{stage} already has {CAP} lessons: merge or remove some first")
    lines = open(LESSONS).read().splitlines()
    head = f"## {stage}"
    if head not in lines:
        lines += ["", head]
    i = lines.index(head) + 1
    while i < len(lines) and not lines[i].startswith("## "):
        i += 1
    while lines[i - 1] == "":
        i -= 1
    lines.insert(i, f"- {text} ({datetime.date.today().isoformat()})")
    open(LESSONS, "w").write("\n".join(lines) + "\n")
    print(f"added to {LESSONS} under {stage}")


def cmd_stats(mem):
    by = defaultdict(Counter)
    for r in ledger(mem):
        j = r.get("job")
        if r.get("stage") and r.get("engineer") is None:
            by[j]["listed"] += 1
        if r.get("engineer"):
            by[j][r["engineer"]] += 1
    print(json.dumps({j: dict(c) for j, c in by.items()}, indent=1))


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    opt = {}
    for flag in ("--stage",):
        if flag in a:
            i = a.index(flag); opt[flag] = a[i + 1]; a = a[:i] + a[i + 2:]
    cmd, rest = a[0], a[1:]
    if cmd == "record":
        cmd_record(rest[0], rest[1] if len(rest) > 1 else find_memory(rest[0]), opt.get("--stage", "dryrun"))
    elif cmd == "feedback":
        if len(rest) != 5:
            sys.exit('usage: learn.py feedback <memory_dir> <run_id> <note_id|RUN> ok|fix|bug "<words>" [--stage S]')
        cmd_feedback(*rest, stage=opt.get("--stage"))
    elif cmd == "ingest":
        cmd_ingest(*rest[:3])
    elif cmd == "lessons":
        cmd_lessons(rest[0])
    elif cmd == "accept":
        if len(rest) != 2:
            sys.exit('usage: learn.py accept <stage> "<rule>"  (saved in the skill, not the memory dir)')
        cmd_accept(*rest)
    elif cmd == "stats":
        cmd_stats(rest[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
