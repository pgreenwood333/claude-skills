---
name: "dot-xs-note-placement"
description: "Add missing drainage and driveway notes to DOT OpenRoads Designer cross sections. Pulls the exact profile notes from the plan-profile (WK) sheets with the dot-plan-set-qaqc note match, keeps the ones that belong on the cross sections, matches each to its dynamic cross-section drawing model in the XS DGNs, and builds a MicroStation VBA macro (dry run, place, undo, Batch Process) plus exact run instructions for the engineer. Use when someone wants to add, place, copy or fix cross-section notes, put profile notes on the cross sections, fix 'missing on cross section' QA/QC flags, or write a VBA macro or script to place text on OpenRoads/MicroStation cross sections."
---

# DOT cross-section note placement

You build everything; the engineer runs it in OpenRoads Designer on Windows. Claude can't edit a DGN from the Mac, because V8 DGN and `.mvba` are closed Bentley formats, so the deliverable is a VBA module (`.bas`) plus instructions.
Work folder: `/Volumes/PGExtHD/OpenRoads/<job>_xs_notes/` (heavy files stay on the external drive).
Scripts: this skill's `scripts/` (`$X`). Which notes go on the cross sections comes from the QA/QC skill's note match: `$Q` = `~/.claude/skills/dot-plan-set-qaqc/scripts`.
**Lessons and memory (same as the QA/QC skill).** Read `references/lessons.md` now: one section per stage (notes, sections, settings, macro, steps), each an engineer-approved rule from a past mistake. They override the defaults below. Job history lives in `xs_notes_memory/` (the nearest one above the work folder, `/Volumes/PGExtHD/OpenRoads/xs_notes_memory/` for jobs there), written by `scripts/learn.py`; read the last entry of its `audit_log.md` before you start.

**Hard rules**
- **When you're unsure about anything, ask.** That includes which notes, which side, which section, level, style, size, placement, file, VBA project, or what a report means. Use AskUserQuestion, with your recommendation as the first option. Never guess and carry on.
- **Never fail silently.** If a script prints `STOP:`/`FIX:`, exits non-zero, or gives a result that can't be right (0 notes, 0 sections, a file not found), stop, tell the engineer what it means, give the fix, and wait. The macro follows the same rule: it stops with the step and a fix, never skips.
- **Never script cutting cross sections or named boundaries, and never write to a DGN.** New sections are cut by hand: drawing model only, no sheet model. The engineer would rather do it than risk the file.
- Terminal commands for the engineer start with `cd <absolute path>` and are complete and copy-pasteable, one per block.

## Step 0: Ask how to find the notes (always first)

Open with one question (AskUserQuestion), recommendation first, and ask for the plan PDF with it. The three starting points:

1. **"Here's my QA/QC results"** (recommended when a QA/QC note match was run on this set). Ask for the `qaqc_work/` folder (or `findings_reviewed.json`). Only the profile notes it flagged "MISSING on cross section" get placed, not every note. The QA/QC already leaves out removal-only notes (EXIST. PIPE / REMOVE / ABANDON / FLOWABLE FILL with nothing proposed).
2. **"No cross-section notes placed yet"** (fresh sections). Ask for the plan-profile (WK) sheets only. Every proposed drainage and driveway note in the profiles gets placed. The QA/QC note match decides what counts: drainage and driveway kinds, never removal-only or "other" notes (silt basins, barrier, bridge).
3. **"Some sections are already noted, no QA/QC run."** Ask for the plan-profile sheets and the cross-section sheets (combine into one PDF: plans first, then XS). The QA/QC note match compares them, and only the notes missing from the XS get placed.

Also ask for whatever else isn't given yet:
- **Scope:** stations already fixed ("done through 337+08.26"), or a station range.
- **Software:** OpenRoads Designer version, and whether the sections are dynamic (named-boundary) sections. This skill is for dynamic sections; if they're plain drawn sheets, ask how the sections are organized before going on.

The XS DGN files come after the note list (Step 3).

## Step 1: Get the notes from the QA/QC note match

`$Q` = `~/.claude/skills/dot-plan-set-qaqc/scripts`. For starting points 2 and 3, follow that skill's Step 1 (setup) and Step 2 (index) quality gate, then run only its note match:

```bash
eval "$(bash $Q/setup_env.sh)"
$PY $Q/build_index.py index "<plans.pdf>" <work>/qaqc_work/index
$PY $Q/build_index.py sheets <work>/qaqc_work/index
# starting point 2 (no XS notes yet):
$PY $Q/note_match.py "<plans.pdf>" <work>/qaqc_work/notematch --index <work>/qaqc_work/index --profile-only
# starting point 3 (compare against the XS sheets):
$PY $Q/note_match.py "<plans+xs.pdf>" <work>/qaqc_work/notematch --index <work>/qaqc_work/index
```

Check the printed counts (`wk_pages`, `xs_pages`, `profile_notes`, `profile_without_xs`). If any that should be there is 0, stop and ask.

**Starting point 3 needs the by-eye check.** The script misses some XS notes it can't read (on 123456 a fresh run flagged 6 notes the reviewed QA/QC had already found on the XS: 372+65, 372+75, 389+00, 391+20, 430+38 among them). For every "MISSING on cross section" flag, search the XS sheets for it as the QA/QC note-match brief says (`references/agent_notematch.md` step 3: search the index for the ID and the station; compare by eye). Leave out any you find, with `--exclude`. Starting point 1 already had this review.

## Step 2: Choose the notes

```bash
python3 $X/select_notes.py <work>/qaqc_work/notematch/note_match.json <work> [--skip-through <sta>] [--only-from <sta> --only-to <sta>] [--exclude NM-142,NM-156]
```

(Starting point 1: pass `qaqc_work/findings_reviewed.json` instead.) It knows which starting point it's in from the file.
- **Removal-only rule.** Kept as a safety net for older QA/QC results: a note that only removes or abandons existing drainage is dropped; one that combines a proposed structure with a removal stays.
- **Show the engineer** the count by kind, the drop list, and (starting point 2) the full list, since it's every proposed note. Confirm before going on.
- **Sides.** Each note's side comes from its profile sheet (WK-30**LT**). Every `ASK:` line (no side) must be answered.
- **Notes missing from the profile.** Notes on the XS but not in the profile are listed, not placed. Tell the engineer.

## Step 3: The XS files, then every note without an exact section

Now ask for **the XS DGN files** (often a zip in Google Drive: the cross-section files plus everything they reference). Unzip into `<work>/dgn/`, then:

```bash
pip3 install olefile   # once
python3 $X/match_sections.py <work> <work>/dgn/<path>/XS-*.dgn [--group MLUS51]
```

It reads the drawing-model names (`<group> - <station>`, read-only) and gives each note a status:
- **EXACT:** a section at the note's station. **CLOSE:** within 0.5 ft (same structure, the note rounds the station).
- **NEEDS DECISION:** the nearest section is farther away.

Give the engineer **one table of every NEEDS DECISION note**: station, structure, nearest section, gap. For each: **nearest section**, **cut a new section**, or **skip**. Record answers in `<work>/decisions.json` (`{"NM-151": "nearest", "NM-181": "cut"}`) and re-run with `--decisions <work>/decisions.json`. Any `ASK:` about model groups gets asked too.

## Step 4: Settings: level, color, style, placement

Ask about the defaults in one message: show the DOT standard below (proven on job 123456, every note checked by the engineer) and ask the engineer to confirm or say what's different. Only ask for screenshots (Change Attributes, Text Editor, Place Named Boundary) when something differs or there are new sections to cut and the cut settings aren't known.
- **Change Attributes on an existing XS note:** level, color, weight. Standard: **XS_P_DRAINAGE, color 15** (the number, not ByLevel), weight 2.
- **The Text Editor on an existing note:** text style. Standard: **_Gen_Notes at its own size (0.01)**, Engineering Vert. Also check the note's line format against the profile text.
- **Place Named Boundary, Civil Cross Section, as used for the existing sections:** drawing seed, detail scale, group, left/right offsets, top/bottom clearance, vertical exaggeration. These go in the run guide for the sections the engineer cuts.
- **Placement.** Standard: tucked into the grid corner. LT note: left edge 1 ft in from the grid's left edge; RT note: right edge 1 ft in from the right edge; top 1 ft under the top grid line. Left-justified, no leaders. Two notes in one corner go side by side, toward the centerline.
- **Their own VBA project name.** Never a shared office project like `status`.

**Text size: nothing to set, even when no file has a note yet.**
- Every note is built from the text style itself. The macro makes each section model active while it builds that model's note, so the drawing's annotation scale applies and nothing is rescaled: the Text Editor shows the style and its own size, no override. It never copies a nearby note (one can carry another style or a size override).
- **Size check, built in** (`STANDARD_SIZE` in `make_macro.py`): before each note, the 8-line note "354 A" built from `_Gen_Notes` in that section must measure 15.001 ft at 1"=10' (within 3%). Every report shows a `Size check:` line; it should read x1.000. If not, the macro stops, dry run included.
- Set `text_size.drawing_scale_ft_per_in` (1"=10' → 10; the check scales with it).
- **Different text style:** the notes still come out at that style's own size. The built-in check is for `_Gen_Notes`, so either set `"use_standard": false` (no check; have the engineer check the first note's Text Editor before batching) or measure one hand-placed note and give `text_size.standard` (`{"height", "scale_ft_per_in", "lines"}`). Ask which.
- **Level and style missing from a file:** the macro brings them in from the DOT libraries (key-ins `ACTIVE LEVEL` / `TEXTSTYLE ACTIVE`) and restores the old active ones afterwards.

Write `<work>/macro_settings.json`:

```json
{
  "job": "123456", "vba_project": "XSNotes", "group_prefix": "MLUS51 - ",
  "note_text": {"level": "XS_P_DRAINAGE", "text_style": "_Gen_Notes", "weight": 2, "color": 15, "class": "Primary"},
  "grid": {"left_offset": -140, "right_offset": 140},
  "placement": {"edge_gap": 1, "top_gap": 1, "side_gap": 3},
  "text_size": {"drawing_scale_ft_per_in": 10},
  "new_sections": {"drawing_seed": "DOT Cross Section Sheet - 10 Scale", "detail_scale": "1\"=10'", "group": "MLUS51",
                   "left_offset": -140, "right_offset": 140, "top_clearance": 10, "bottom_clearance": 5,
                   "vertical_exaggeration": 1, "elevation_datum_spacing": 10, "create": "drawing model only, no sheet model"}
}
```

## Step 5: Build and deliver

```bash
python3 $X/make_macro.py <work>
python3 $X/make_checklist.py <work>
```

`make_macro.py` refuses (`STOP:`) while any note needs a decision, has no side, or a setting is wrong. Fix and re-run.
It writes `PlaceXSNotes.bas`, `xsnotes_batch_DRYRUN.txt`, `xsnotes_batch_PLACE.txt`, `xsnotes_batch_REMOVE.txt` and `HOW_TO_RUN.md`; `make_checklist.py` writes `<job>_XS_notes_checklist.xlsx` (every note, its section model, corner, full text, an OK/Fix column).
Send all of them with SendUserFile.

In chat, lead with:
- the note count per XS file
- the list of new sections to cut, with stations and settings
- the run order (below)

**The engineer's steps** (exactly these; `HOW_TO_RUN.md` spells them out with the job's names):
1. Cut any new sections first (drawing model only, no sheet model).
2. Search ribbon → **VBA Manager** → **New** → name it **XSNotes** (their own project; skip if it exists, just load it).
3. Click **XSNotes** → **Show the VBA Editor** → click **XSNotes** in the left sidebar → **File > Import File** → pick `PlaceXSNotes.bas`.
4. **Debug > Compile XSNotes.** Nothing shows → **File > Save**. An error box → screenshot it to Claude, stop.
5. Search ribbon → **Batch Process** → **Initial Model: Default Model Only** → **Add** files (every XS file on the list) → **Command File:** `xsnotes_batch_DRYRUN.txt` → **Process**.
6. From the folder that holds the DGNs on the C drive, send Claude `_xsnotes_SUMMARY.txt` and every `*_xsnotes_report.txt`.
7. Only when Claude gives the go-ahead: same Batch Process, command file `xsnotes_batch_PLACE.txt` → **Process**.
8. Check the notes were added, using the checklist spreadsheet.
9. If any were added wrong: same Batch Process, command file `xsnotes_batch_REMOVE.txt` → **Process** (removes only what the macro placed), tell Claude what was wrong.

**What the macro does:**
- **Entry points:** `DryRun`, `PlaceNotes`, `RemovePlacedNotes`, plus dialog-free `DryRunBatch` / `PlaceNotesBatch` / `RemovePlacedNotesBatch` for Batch Process. The batch versions only work on the default model and return at once on any other.
- **Models:** it activates each section model while building that model's note, then goes back to the model it started in (a few seconds per section).
- **Grid:** it finds the grid from its widest horizontal line, and the scale from any ±N offset label pair.
- **Duplicates:** it skips notes already on a section.
- **Level/color check:** it sets level, color and weight on the note and every line in it, reads them back, and stops (dry run included) if they didn't take.
- **Output:** a report per file, a summary line per file per run (`_xsnotes_SUMMARY.txt`), and a log of placed element IDs for undo.

## Step 6: Read the results with the engineer

Read every file the engineer sends. Check:
- every file has a summary line for the run, and the counts add up to the note total
- each report's `Size check:` line reads about x1.000
- no STOPPED lines, CHECK flags or grid warnings; "beside the other note" only where two notes share a corner; "already on" skips explained
- after PLACE: `placed N` per file matches the counts you gave

If the macro has a bug:
1. Fix `scripts/make_macro.py` in this skill, not a job copy.
2. Run `bash tests/check.sh`. If the change is intended, update the known-good copy (`bash tests/check.sh --update`) and say so.
3. Regenerate, and have the engineer remove the old module, import, compile.
4. Add the lesson to `references/lessons.md`.

## Step 7: Learn from the job

```bash
python3 $X/learn.py record <work> --stage place          # after PLACE; prints the run id
python3 $X/learn.py ingest <returned checklist.xlsx> <memory> <run_id>   # OK / Fix answers from the engineer
python3 $X/learn.py feedback <memory> <run_id> <note_id|RUN> ok|fix|bug "<their words>" [--stage notes|sections|settings|macro|steps]
python3 $X/learn.py lessons <memory>
```

- Record **every** correction as it comes in during the job, not just at the end: a Fix on the checklist, a macro error or wrong result (`bug`, stage `macro`), a wrong step or confusing instruction (`steps`), a setting the engineer changed (`settings`). Use their words.
- `lessons` proposes a rule when the same kind of fix shows up in 2 or more jobs, and every bug at once (fix the code first; the lesson records why).
- Show the proposals to the engineer. Only for the ones they agree with: `learn.py accept <stage> "<rule>"`, written as a rule the next job can follow. It goes into `references/lessons.md` in the skill (dated, at most 12 per stage), so it ships to GitHub and Cowork. Never add a lesson they didn't approve.
- `learn.py stats <memory>` shows notes placed, fixes and bugs per job.

**Done:** every file's summary reads `PLACE placed N` matching the per-file counts, and the engineer has checked every note on the checklist.

## Known-good state

Job 123456 (Nov 2026): 60 notes in 3 files, every one checked correct by the engineer, with the settings shown above. `tests/fixture/` holds a small sample job and `tests/expected/` the macro the current generator must produce for it; `tests/check.sh` regenerates and compares. Don't change the proven behavior (style-built notes, corner placement, color 15, the size check) without asking the engineer.
