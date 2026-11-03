#!/usr/bin/env python3
"""Merge agent findings into one file and apply the orchestrator's review verdicts.

  merge_findings.py <work_dir> --tasks index,spelling,overlap,quantity [--reviews reviews.json] [--project project.json]

Reads <work_dir>/findings/*.json (each {"findings": [...]}) and <work_dir>/qty/quantities.json when present.
Writes <work_dir>/findings_reviewed.json. Safe to re-run: verdicts already recorded are kept.
reviews.json: {"SPL-003": {"verdict": "confirmed", "note": "visible on crop"}, "OVL-p15-004": {"verdict": "rejected",
               "note": "stacked callout, legible"}}   verdict = confirmed | rejected | uncertain
Each finding needs: id, task, severity, sheet_ids, pdf_pages, finding, evidence, suggested_fix, locate.
"""
import argparse, glob, json, os
from qaqc_common import load_json, save_json, SEVERITIES

REQUIRED = ("id", "task", "severity", "finding")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work"); ap.add_argument("--tasks", required=True); ap.add_argument("--reviews")
    ap.add_argument("--project")
    a = ap.parse_args()
    tasks = [t.strip() for t in a.tasks.split(",") if t.strip()]
    out = os.path.join(a.work, "findings_reviewed.json")
    prev = {f["id"]: f for f in (load_json(out, {}) or {}).get("findings", [])}
    findings, problems, seen = [], [], set()
    for path in sorted(glob.glob(os.path.join(a.work, "findings", "*.json"))):
        for f in load_json(path, {}).get("findings", []):
            findings.append(f)
    q = load_json(os.path.join(a.work, "qty", "quantities.json"))
    if q:
        findings += q.get("findings", [])
    for f in findings:
        miss = [k for k in REQUIRED if not f.get(k)]
        if miss:
            problems.append(f"{f.get('id', '?')}: missing {miss}")
        if f.get("id") in seen:
            problems.append(f"duplicate id {f['id']}")
        seen.add(f.get("id"))
        if f.get("severity") not in SEVERITIES:
            problems.append(f"{f.get('id')}: severity {f.get('severity')!r}")
        f.setdefault("locate", [])
        f["review"] = (prev.get(f.get("id")) or {}).get("review") or f.get("review") or {"verdict": "uncertain"}
    reviews = load_json(a.reviews, {}) if a.reviews else {}
    for f in findings:
        if f.get("id") in reviews:
            f["review"] = reviews[f["id"]]
    for f in findings:
        if f.get("gate") and not f["gate"].get("pass") and f["review"].get("verdict") == "confirmed" \
                and not f["review"].get("gate_override"):
            f["review"] = {"verdict": "uncertain", "note": "confirmed but failed the evidence gate "
                           f"{f['gate']['problems']}: fix the evidence or add gate_override with the reason"}
            problems.append(f"{f['id']}: confirmed but failed the evidence gate; set back to uncertain")
    findings = [f for f in findings if f.get("task") in tasks]
    data = dict(project=load_json(a.project, {}) if a.project else {}, tasks=tasks, findings=findings, quantities=q)
    save_json(out, data)
    v = [f["review"]["verdict"] for f in findings]
    print(json.dumps(dict(findings=len(findings), confirmed=v.count("confirmed"), rejected=v.count("rejected"),
                          uncertain=v.count("uncertain"), problems=problems), indent=1))


if __name__ == "__main__":
    main()
