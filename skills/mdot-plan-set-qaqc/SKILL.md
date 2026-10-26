---
name: "mdot-plan-set-qaqc"
description: "QA/QC review of an MDOT roadway plan set PDF. Use when someone wants to QC, QA/QC, check or review plans or a plan set. Indexes and chunks the whole set (text layer + OCR of pasted tables, hybrid keyword/vector search), asks which checks to run (Detailed Index vs sheets, spelling, overlapping text in WK profiles, quantity reconciliation), runs one subagent per check, then the orchestrator verifies every flag, highlights them in red in the PDF and builds a color-coded Excel workbook."
---

# MDOT Plan Set QA/QC

You are the orchestrator. Input: one plan-set PDF. Outputs, next to the PDF unless the user says otherwise:
`<pdf name>_QAQC.xlsx` and `<pdf name>_QAQC_markup.pdf` (red highlights), plus a short chat summary.
Everything reported is a flag for the engineer, not a finding of fact. Sheet IDs are the keys; give PDF pages too.
Never skip an item silently: if something cannot be read, say so in the findings and keep going.

Scripts live in this skill's `scripts/` folder (call it `$S`). Agent briefs are in `references/`.

## Step 0: Ask which checks to run (always first)

Unless the user already named the checks, ask with AskUserQuestion before doing any work:
- Question 1 (multiSelect, header "Checks"): "Which QA/QC checks should I run on this plan set?"
  - Index check: Detailed Index descriptions, Sheet IDs and sheet numbers vs the actual sheets
  - Spelling: misspellings, repeated words and inconsistent spellings on every sheet
  - Overlapping text: text running into other text in the WK profile views
  - Quantity reconciliation: EQ vs Summary of Quantities, and working-sheet recaps vs EQ
- Question 2 (single select, header "Overlap area"), only meaningful if overlapping text is chosen: "Profile view only (Recommended)" or "Profile and plan view" (plan view is noisy because utilities overlap).
Run only what was picked. Indexing (Step 2) always runs, because every check uses it.

## Step 1: Set up

```bash
pip install "pymupdf==1.28.2" pdfplumber openpyxl pyspellchecker numpy rapidocr onnxruntime fastembed --break-system-packages -q
```
If `fastembed` or `rapidocr`/`onnxruntime` will not install, carry on: the index falls back to keyword + fuzzy
search, and pages without OCR must be read visually (the index flags them). Work folder: `qaqc_work/` beside the PDF.

## Step 2: Index, chunk, embed (once)

```bash
python3 $S/build_index.py index "<plans.pdf>" qaqc_work/index
python3 $S/build_index.py sheets qaqc_work/index
```
What it builds: every word with its page coordinates (text layer, plus OCR for tables pasted into the sheets as
images, which is how this set's Detailed Index, SQ and EQ tables are drawn), one markdown chunk per sheet named by
Sheet ID, a SQLite keyword index, and dense vectors (bge-small) when available.
Agents query it with `build_index.py search qaqc_work/index "<terms>" [--sheet EQ-2]`, read `chunks/`,
list words with boxes via `words`, and look at pages with `render ... --clip x0,y0,x1,y1 --dpi 250`.

Quality gate before any agent starts. Read the summary and the `sheets` listing:
- Every page has a Sheet ID (page 1 is the title sheet). Fix any UNKNOWN by rendering the title block and noting it.
- `LOW_RES_RASTER`: the pasted table image is under 150 dpi. OCR is a second reader only; agents must transcribe
  those tables visually from zoomed renders and use OCR to cross-check. `OCR_LOW_CONFIDENCE`: same rule.
- `LOW_TEXT_DENSITY_POSSIBLE_SHX_TEXT` or `RASTER_NOT_OCRED`: the text is drawn as linework or no OCR ran; that
  page can only be read visually.
- Render one WK sheet and one EQ sheet at 60 dpi and look at them once, so you know the layout the agents will see.
OCR words tagged `⟨?⟩` in chunks are under 80% confidence.

## Step 3: Run one subagent per chosen check, all at once

Spawn them in a single message so they run in parallel. Give each: the PDF path, `qaqc_work/index`, `qaqc_work`,
the scripts path, its brief, and `references/findings_schema.md`. Ask for a terse reply (counts and anything they
could not read). Use the general-purpose agent type.

| Check | Brief | Writes |
|---|---|---|
| Index check | `references/agent_index.md` | `qaqc_work/findings/index.json` |
| Spelling | `references/agent_spelling.md` | `qaqc_work/findings/spelling.json` |
| Overlapping text | `references/agent_overlap.md` (tell it profile-only or profile + plan) | `qaqc_work/findings/overlap.json` |
| Quantity reconciliation | `references/agent_quantities.md` | `qaqc_work/qty/*.json` and `quantities.json` |

## Step 4: Review every flag yourself

You are the final checker. The agents find; you confirm.
```bash
python3 $S/merge_findings.py qaqc_work --tasks <chosen,tasks>
```
Then go through `qaqc_work/findings_reviewed.json`, every item, highest severity first:
- Look at the evidence: render the area (`render ... --clip` around the `locate` rect or the text, 250 dpi) or open
  the crop the agent made. Confirm it is real and correctly described.
- Spelling from OCR: decide whether the plan is misspelled or the OCR misread it. Only the plan's errors count.
- Overlaps: confirm the text really collides or is unreadable; reject legible stacked callouts.
- Quantities: re-read both numbers of every MISMATCH at high zoom, and spot-check 5 MATCH rows against the sheets.
  If a number was misread, fix the agent's transcription file, re-run `reconcile.py`, and re-merge.
Record decisions in `qaqc_work/reviews.json` as `{"<id>": {"verdict": "confirmed|rejected|uncertain", "note": "..."}}`
and re-run merge with `--reviews qaqc_work/reviews.json`. Reject with a reason; never delete a flag.

## Step 5: Mark up the PDF and build the workbook

```bash
python3 $S/markup_pdf.py "<plans.pdf>" qaqc_work/index qaqc_work/findings_reviewed.json "<name>_QAQC_markup.pdf"
python3 $S/build_report.py qaqc_work/findings_reviewed.json qaqc_work/index "<name>_QAQC.xlsx"
```
Confirmed flags get a red highlight with the finding as the comment; any that cannot be located get a red sticky
note on the sheet, so nothing is dropped (add `--include-uncertain` to mark those as well). Before delivering, render two
marked-up pages to check the highlights sit on the right text, and open the workbook to check its tabs and counts.

## Step 6: Report in chat

Lead with counts per check (and Table 1 / Table 2 status counts if quantities ran), then the five most important
flags with Sheet IDs, then anything that could not be read. Link both output files.

## Rules that apply to every agent

- Quote evidence exactly as printed. Cite Sheet IDs, never just page numbers.
- Every finding carries a `locate` entry (a rect in PDF points, or exact text on a page) so it can be highlighted.
- Numbers come from the sheets, never from memory or inference. Transcribe, then let the scripts do the arithmetic.
- Do not read the whole PDF into context. Use search, chunks, word lists and targeted renders.
