# Findings file format (all agents)

Write `{"findings": [ ... ]}` to the path in your brief. One object per flag:

```json
{
  "id": "SPL-001",
  "task": "spelling",
  "severity": "medium",
  "sheet_ids": ["EQ-1"],
  "pdf_pages": [10],
  "evidence": "`PERMAMENT EROSION CONTROL` in the table title",
  "finding": "Misspelling in the EQ-1 table title: PERMAMENT",
  "suggested_fix": "PERMANENT EROSION CONTROL",
  "locate": [{"page": 10, "text": "PERMAMENT"}],
  "agent_confidence": "high",
  "crop": "qaqc_work/overlap/overlaps/OVL-p15-003.png"
}
```

- `id`: prefix by task (IDX, SPL, OVL, NM, COL, QTY) plus a number; unique within your file.
- `task`: `index`, `spelling`, `overlap`, `notematch`, `color` or `quantity`.
- `severity`: `high` (wrong information a contractor could build or bid from: wrong sheet number, missing sheet,
  quantity mismatch, unreadable dimension), `medium` (clear error with low impact: misspelling in a title or note,
  overlapping labels that are still decipherable), `low` (cosmetic or consistency).
- `evidence`: every printed string in backticks, exactly as printed (same word order and spelling); your own words
  outside them. Backticks, not double quotes, because plans use " for inches. Both values when two conflict:
  `` `18" RCP` on the WK-3 plan vs `24" RCP` in the profile ``. `validate_findings.py` checks each backticked string
  against the page. Text with no text copy (read from a render): add `"evidence_source": "visual"` and a `crop`.
- `locate`: where to highlight. Prefer `{"page": N, "rect": [x0, y0, x1, y1]}` in PDF points when you have a box
  (word lists, OCR boxes, overlap candidates, tile coordinates). Otherwise `{"page": N, "text": "exact string"}`;
  add `"near": [x0, y0, x1, y1]` if the string appears more than once on the page.
  Converting a point in a rendered PNG to PDF points: `x_pt = clip_x0 + x_px * 72 / dpi`, same for y.
- `agent_confidence`: `high`, `medium` or `low`, which tells the orchestrator where to look hardest.
- Leave `review` out; the orchestrator sets it.
- `candidate_ids`: the script candidate(s) this finding came from (`OVL-p12-003`, `COL-C-p8-0012`, `SPC-U014`,
  `NM-E03`…), when your finding's id is not the candidate's own id.
- `unsure`: one line, when you cannot settle a flag yourself (unreadable, judgment call). Keep the flag and say
  what the engineer should look at; it reaches the workbook as an Unsure row if no reviewer settles it.

## Save as you go

Write your findings file and `_cleared` file early and update them after every sheet (or every ~20 items), not
only at the end. An agent can be cut off (usage limit, error); whatever is on disk survives and the orchestrator
resumes you from it.

## Errors: stop and report

If a script fails, prints `STOP:`, or gives an impossible result (no pages, no candidates where there must be some),
stop and report it in your reply with the error text. Do not work around it or continue with part of the check.

## No skipping (checked by code)

Every candidate your script produced must end in one of two places, and `check_coverage.py` checks it:
1. **Kept**: a finding in `findings/<task>.json` (same id, or listed in `candidate_ids`). Not sure? Keep it, with `unsure`.
2. **Cleared**: an entry in `findings/<task>_cleared.json`:
   ```json
   {"cleared": [{"ids": ["OVL-p12-003"], "reason": "stacked callout, both labels legible",
                 "sheet": "WK-12", "seen": "`STA. 235+34.00` above `36' DRIVE REQ'D.`"}]}
   ```
   `reason`, `sheet` and `seen` (what you read on the sheet) are required; spelling may clear many words with one
   reason and no sheet ("DOT abbreviation"). Clear only what you looked at. "Probably fine", "minor",
   "normally omitted" or "not checked" are not reasons.
Anything in neither place goes back to you once, then lands in the workbook as Unsure. Your reply gives
kept / cleared / unsure counts.
