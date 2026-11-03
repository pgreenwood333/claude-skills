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
