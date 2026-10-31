---
name: "mdot-plan-set-qaqc"
description: "QA/QC review of an MDOT roadway plan set PDF. Use when someone wants to QC, QA/QC, check or review plans or a plan set. Indexes and chunks the whole set (text layer + OCR of pasted tables, hybrid keyword/vector search), asks which checks to run (Detailed Index vs sheets, spelling, overlapping text in WK profiles, print color on WK sheets (proposed drainage blue, existing purple, rest black), plan/profile/cross-section note match, quantity reconciliation), runs one subagent per check, gates every flag on evidence printed on the sheet, has an independent grader score the run and send weak checks back, highlights confirmed flags in red in the PDF, builds a color-coded Excel workbook, and keeps a memory of the engineer's corrections so later runs improve."
---

# MDOT Plan Set QA/QC

You are the orchestrator. Input: one plan-set PDF. Outputs, next to the PDF unless the user says otherwise:
`<pdf name>_QAQC.xlsx` and `<pdf name>_QAQC_markup.pdf` (red highlights), plus a short chat summary.
Everything reported is a flag for the engineer, not a finding of fact. Sheet IDs are the keys; give PDF pages too.
Never skip an item silently: if something cannot be read, say so in the findings and keep going.

Scripts live in this skill's `scripts/` folder (call it `$S`). Agent briefs are in `references/`.

## Step 0: Ask which checks to run (always first)

Unless the user already named the checks, ask with AskUserQuestion before doing any work (one call, three
questions; the tool allows at most 4 options per question):
- Question 1 (multiSelect, header "Sheet checks"): "Which sheet checks should I run?"
  - Index check: Detailed Index descriptions, Sheet IDs and sheet numbers vs the actual sheets
  - Spelling: misspellings, repeated words, placeholders and inconsistent spellings on every sheet
  - Note match: plan note vs profile note on the WK sheets, and profile note vs cross-section (9000) note
- Question 2 (multiSelect, header "WK checks"): "Which WK plan-profile checks should I run?"
  - Overlapping text, profile view only (Recommended)
  - Overlapping text, profile and plan view (plan view is noisy because utilities overlap)
  - Print color: proposed drainage blue, existing/surveyed purple, everything else black
- Question 3 (single select, header "Quantities"): "Run the quantity reconciliation (EQ vs Summary of Quantities,
  working-sheet recaps vs EQ)?" Yes (Recommended) / No.
Run only what was picked. Indexing (Step 2) always runs, because every check uses it.

Memory: find `qaqc_memory/` beside the PDF or in a parent folder (the nearest one wins); if there is none, create it
beside the folder that holds the PDF. If `qaqc_memory/lessons.md` exists, read it now and give each agent and the
grader its section. These are the engineer's approved corrections from past runs and override the briefs.

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
could not read). Use the general-purpose agent type with the model and effort in the table (the engineer set
these: the scripts do the exact work, so Sonnet judges candidates well; quantities are read off low-resolution
table images where one misread digit is a high-severity error, so they get Opus). If the agent tool here cannot
set a model or effort, run them on the session's model and say so in the report.

| Check | Brief | Model, effort | Writes |
|---|---|---|---|
| Index check | `references/agent_index.md` | sonnet, high | `qaqc_work/findings/index.json` |
| Spelling | `references/agent_spelling.md` | sonnet, high | `qaqc_work/findings/spelling.json` |
| Overlapping text | `references/agent_overlap.md` (tell it profile-only or profile + plan) | sonnet, high | `qaqc_work/findings/overlap.json` |
| Quantity reconciliation | `references/agent_quantities.md` | opus, high | `qaqc_work/qty/*.json` and `quantities.json` |
| Note match | `references/agent_notematch.md` | sonnet, high | `qaqc_work/findings/notematch.json` |
| Print color | `references/agent_color.md` | sonnet, high | `qaqc_work/findings/color.json` |

Revision rounds (Step 4) re-run a check on the same model and effort.

## Step 4: Gate, grade, revise

You are the final checker, but you do not grade your own team's work alone. Three layers, in this order:

1. **Evidence gate (code, cannot be argued with).**
   `python3 $S/validate_findings.py "<plans.pdf>" qaqc_work/index qaqc_work`
   Every flag must name the right sheet, land on its page, and quote text that is really printed there. Failures
   are written into each finding as `gate.problems`. If one check fails the gate on more than 2 flags, send that
   agent its list once ("fix the quote to the exact printed text, or drop the flag") and re-run the gate.
2. **Independent grader (fresh subagent).** Merge first:
   `python3 $S/merge_findings.py qaqc_work --tasks <chosen,tasks>`   # index,spelling,overlap,notematch,color,quantity
   Then spawn one general-purpose subagent on **opus, high effort** with `references/grader.md`, the PDF, `qaqc_work/index`,
   `qaqc_work/findings_reviewed.json`, `$S`, the checks that ran and the lessons. Do not give it the agents' replies
   or your own opinions: it judges the output only. It writes `qaqc_work/grade.json`.
3. **Revise (at most 2 rounds).** If `grade.json` says `needs_revision`, send each failing check's `revise` list and
   `missed` items to that check's agent (SendMessage to the same agent if you can, else a new one with its brief),
   re-run the gate, merge, and grade again with a fresh grader. Stop after 2 rounds even if not satisfied, and say
   which criteria still fail in the report.

Then the final pass is yours. Copy the grader's verdicts to `qaqc_work/reviews.json` and check the ones that matter:
- Every high-severity flag and every flag the grader marked `uncertain`: render the area (`render ... --clip`
  around the `locate` rect, 250 dpi) and decide.
- Quantities: re-read both numbers of every MISMATCH at high zoom, and spot-check 5 MATCH rows against the sheets.
  If a number was misread, fix the agent's transcription file, re-run `reconcile.py`, and re-merge.
Format: `{"<id>": {"verdict": "confirmed|rejected|uncertain", "note": "..."}}`. Re-run merge with
`--reviews qaqc_work/reviews.json`. Reject with a reason; never delete a flag. Merge refuses a `confirmed` flag that
failed the gate unless the review carries `"gate_override": "<why the evidence is right>"` (e.g. text with no text
copy that you read on a render).

## Step 5: Mark up the PDF and build the workbook

```bash
python3 $S/markup_pdf.py "<plans.pdf>" qaqc_work/index qaqc_work/findings_reviewed.json "<name>_QAQC_markup.pdf"
python3 $S/build_simple_report.py qaqc_work/findings_reviewed.json qaqc_work/index "<name>_QAQC.xlsx"
```
The workbook is a plain punch list: one tab per check, one row per sheet (Spelling: Text Found / Correct To;
others: What's Wrong / Fix / Priority), XX placeholders on their own tab, plus Your Call and Rejected tabs.
Note Match is one row per flag, never duplicated: a profile-vs-XS flag lists both sheets in one row
(Sheet ID(s) / PDF Page(s)), with a What Doesn't Match column ("Profile: …" / "XS: …", or "XS: cross-section note
not found"). If the
engineer wants the detailed version (evidence, locate, review notes), also run `build_report.py` with the same
arguments into `<name>_QAQC_detail.xlsx`. Confirmed flags get a red highlight with the finding as the comment; any that cannot be located get a red sticky
note on the sheet, so nothing is dropped (add `--include-uncertain` to mark those as well). Before delivering, render two
marked-up pages to check the highlights sit on the right text, and open the workbook to check its tabs and counts.

## Step 6: Report in chat

Lead with counts per check (and Table 1 / Table 2 status counts if quantities ran), then the five most important
flags with Sheet IDs, then anything that could not be read. Add the grader's scoreboard per check in one line and
how many revision rounds ran. Link both output files.

## Step 7: Remember (every run)

```bash
python3 $S/learn.py record qaqc_work <qaqc_memory> --plan-set "<pdf name>"
```
This logs every flag with the grader's and your verdict. Tell the user the run ID it prints and that they can
correct any flag later ("SPL-005 was wrong, that's the street's real name"; "you missed X on WK-4"). When they do:
`learn.py feedback <qaqc_memory> <run_id> <id> confirmed|rejected|missed "<their words>" [--task <task>]`.
Then run `learn.py lessons <qaqc_memory>`. It proposes a lesson only when the same pattern repeats in 2 or more runs
(one bad call is not a pattern). Show the proposals to the user and add only the ones they approve, written as a rule
the agents can follow: `learn.py accept <qaqc_memory> <task> "<rule>"`. Never add a lesson they did not approve.
`learn.py stats` shows precision per check over time.

## Rules that apply to every agent

- Quote evidence exactly as printed, in backticks (plans use " for inches); your own words go outside them. The gate checks every
  quoted string against the sheet. Text read from a render because it has no text copy: set
  `"evidence_source": "visual"` and give a crop.
- If you cannot read something or are not sure, say so ("could not read the EQ-2 table at this zoom"). An honest
  "not sure" is always better than a guess; the grader treats it as useful, a wrong flag as a failure.
- Cite Sheet IDs, never just page numbers.
- Every finding carries a `locate` entry (a rect in PDF points, or exact text on a page) so it can be highlighted.
- Numbers come from the sheets, never from memory or inference. Transcribe, then let the scripts do the arithmetic.
- Do not read the whole PDF into context. Use search, chunks, word lists and targeted renders.
