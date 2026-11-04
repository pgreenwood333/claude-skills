---
name: "dot-xs-note-placement"
description: "Add missing drainage and driveway notes to DOT OpenRoads Designer cross sections. Pulls the exact profile notes from the plan-profile (WK) sheets with the dot-plan-set-qaqc note match, keeps the ones that belong on the cross sections, matches each to its dynamic cross-section drawing model in the XS DGNs, and builds a MicroStation VBA macro (dry run, place, undo, Batch Process) plus exact run instructions for the engineer. Use when someone wants to add, place, copy or fix cross-section notes, put profile notes on the cross sections, fix 'missing on cross section' QA/QC flags, or write a VBA macro or script to place text on OpenRoads/MicroStation cross sections."
---

# DOT cross-section note placement

You build everything; the engineer runs it in OpenRoads Designer on Windows. Claude can't edit a DGN from the Mac, because V8 DGN and `.mvba` are closed Bentley formats, so the deliverable is a VBA module (`.bas`) plus instructions.
Work folder: `/Volumes/PGExtHD/OpenRoads/<job>_xs_notes/` (heavy files stay on the external drive).
Scripts: this skill's `scripts/` (`$X`). Profile notes come from the QA/QC skill: `$Q` = `~/.claude/skills/dot-plan-set-qaqc/scripts`.
Read `references/lessons.md` before you start. It lists every way the first job went wrong.

**Hard rules**
- **When you're unsure about anything, ask.** That includes which notes, which side, which section, level, style, size, placement, file, VBA project, or what a report means. Use AskUserQuestion, with your recommendation as the first option. Never guess and carry on.
- **Never fail silently.** If a script prints `STOP:`/`FIX:`, exits non-zero, or gives a result that can't be right (0 notes, 0 sections, a file not found), stop, tell the engineer what it means, give the fix, and wait. The macro follows the same rule: it stops with the step and a fix, never skips.
- **Never script cutting cross sections or named boundaries, and never write to a DGN.** New sections are cut by hand: drawing model only, no sheet model. The engineer would rather do it than risk the file.
- Terminal commands for the engineer start with `cd <absolute path>` and are complete and copy-pasteable, one per block.

## Step 0: Ask for the inputs (always first)

Ask for whatever the engineer hasn't already given:
1. **The plan-profile sheets** (the WK sheet PDF) and **the cross-section sheets** (XS PDF). If they're separate, combine them, plans first then XS. Or, if a QA/QC run already exists for this set, the path to its `qaqc_work/`.
2. **The XS DGN files** (often a zip in Google Drive): the cross-section files plus everything they reference, i.e. corridors, alignments, terrain and drainage.
3. **Scope:** any stations already fixed ("done through 337+08.26"), or a station range.
4. **Software:** OpenRoads Designer version and year, and whether the sections are dynamic (named-boundary) cross sections. This skill is for dynamic sections. If they're plain drawn sheets, ask how the sections are organized before going on.

## Step 1: Get the exact profile notes

If a QA/QC run exists, use its `qaqc_work/findings_reviewed.json` (or `qaqc_work/notematch/note_match.json`). Otherwise run only the note match from `dot-plan-set-qaqc`. Follow that skill's Step 1 (setup) and Step 2 (index) quality gate:

```bash
eval "$(bash $Q/setup_env.sh)"
$PY $Q/build_index.py index "<plans+xs.pdf>" <work>/qaqc_work/index
$PY $Q/build_index.py sheets <work>/qaqc_work/index
$PY $Q/note_match.py "<plans+xs.pdf>" <work>/qaqc_work/notematch --index <work>/qaqc_work/index
```

Check the printed counts (WK pages, XS pages, profile notes, `profile_without_xs`). If any is 0, stop and ask.
Before trusting a "missing on cross section" note, spot-check a few against the XS sheets as that skill's note-match brief describes (search the index for the ID and station). The note text is taken line for line from the profile.

## Step 2: Choose the notes

```bash
python3 $X/select_notes.py <findings json> <work> [--skip-through <sta>] [--only-from <sta> --only-to <sta>]
```

- **Removal-only rule (default).** A drainage note that only removes or abandons existing drainage (EXIST. PIPE, REMOVE, flowable fill, with no proposed structure) belongs on the plan and profile only, so it's dropped. A note that combines a proposed structure with a removal stays.
- **Review the drop list.** Show it to the engineer with the counts and confirm.
- **Sides.** Each note's side comes from its profile sheet (WK-30**LT**). Every `ASK:` line (no side) must be answered.
- **Notes missing from the profile.** Notes on the XS but not in the profile are listed, not placed. Tell the engineer about them.

## Step 3: Match notes to sections in the DGNs

Unzip the DGNs into `<work>/dgn/` (their own folder), then:

```bash
pip3 install olefile   # once
python3 $X/match_sections.py <work> <work>/dgn/<path>/XS-*.dgn [--group MLUS51]
```

It reads the drawing-model names (`<group> - <station>`, read-only) and gives each note a status:
- **EXACT:** a section exists at the note's station.
- **CLOSE:** a section is within 0.5 ft. It's the same structure; the note just rounds the station.
- **NEEDS DECISION:** the nearest section is farther away than that.

For every NEEDS DECISION note, ask the engineer: **place on the nearest section**, **cut a new section**, or **skip**. Show the station, structure, nearest section and gap, ideally in one table, then ask. Record the answers in `<work>/decisions.json` (`{"NM-151": "nearest", "NM-181": "cut"}`) and re-run with `--decisions <work>/decisions.json`.
**Any group question** (`ASK:` several model groups) gets asked too.

## Step 4: Settings: level, text, placement, size

Ask for the screenshots and answers below, and confirm anything you read from them:
- **Change Attributes on an existing XS note:** level, color, weight, class. DOT default: XS_P_DRAINAGE, **color 15** (the number, not ByLevel), weight 2.
- **The Text Editor on an existing note:** text style and font. Also check the note's line format against the profile text.
- **Place Named Boundary, Civil Cross Section, as used for the existing sections:** drawing seed, detail scale, group, left/right offsets, top/bottom clearance, vertical exaggeration. These go in the run guide for the sections the engineer cuts.
- **Placement (engineer's standard, 2026-11-04):** tucked into the grid corner. LT note: left edge `edge_gap` (1 ft) in from the grid's left edge; RT note: right edge 1 ft in from the right edge; top 1 ft under the top grid line. Left-justified, no leaders. Two notes in one corner go side by side, toward the centerline. Confirm it still applies.
- **Which XS file already has a note** on that level and style. That file runs first (`first_file`), because the others size their text from it.
- **Their own VBA project name.** Never a shared office project like `status`.

**Text size.**
- **Every note is the text style itself** (engineer, 2026-11-04): `_Gen_Notes` at the style's own size (0.01 in the Text Editor), never a copy of a nearby note, because a nearby note can carry another style or a size override (3.1's "439 B" did: Style (none), 0.0106).
- **How:** the macro makes each section model active while it builds that model's note, so the drawing's own annotation scale applies and nothing is rescaled. Building in the default model and scaling (the old way) gives the right look but a size override.
- **Safety check, built in** (`STANDARD_SIZE` in `make_macro.py`): before each note, the 8-line note "354 A" built from the style in that model must measure 15.001 ft (1"=10'), within 3%. If not, it stops (dry run included) and says why.
- **Only set `text_size.drawing_scale_ft_per_in`** (1"=10' → 10). At another scale the standard scales linearly; then have the engineer check the first placed note against an existing one before batching.
- **Different text style or a non-DOT standard:** ask. Then either give `text_size.standard` (`{"height", "scale_ft_per_in", "lines"}` measured from a hand-placed note) or set `"use_standard": false` and choose:
  1. **Place one note by hand (recommended).** With Place Text, active level and style set as the standard, they place one note in any section model. MicroStation applies the annotation scale correctly. The macro then copies that note everywhere, and saves it as the size reference for the other files. Measure it as described above.
  2. **Fully from scratch.** Ask for the plotted text height for notes (inches on the sheet) and the drawing scale (e.g. 1"=10'). Set `scratch_height` = plotted height × feet per inch: 0.10" at 1"=10' gives 1.0. Never assume the standard height; ask.
     - **How the macro sizes it:** it builds a capital-letter line from the style, measures it, and scales the note so that line is `scratch_height` tall in the drawing model.
     - **Check it before batching:** after placing on the first file, have the engineer use Element Information on one note and compare the text height with the plotted height × scale. This path is less proven than copying a note. Say so.
- **Level.** If the level isn't in a file yet, the macro brings it in from the level library (key-in `ACTIVE LEVEL`) and then puts the old active level back. The text style is handled the same way (`TEXTSTYLE ACTIVE`).

Write `<work>/macro_settings.json`:

```json
{
  "job": "123456", "vba_project": "XSNotes", "group_prefix": "MLUS51 - ",
  "first_file": "XS-US51-2.1-35850 to 39200.dgn",
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
```

It refuses (`STOP:`) while any note needs a decision, has no side, or a setting is missing. Fix and re-run.
It writes `PlaceXSNotes.bas`, `xsnotes_batch_DRYRUN.txt`, `xsnotes_batch_PLACE.txt` and `HOW_TO_RUN.md` into `<work>`.
Send the `.bas`, the two command files and `HOW_TO_RUN.md` with SendUserFile.

In chat, lead with:
- the note count per XS file
- the list of new sections to cut, with stations and settings
- the run order: compile, dry run on `first_file`, read the report, place on `first_file` and check it, then the rest by hand or Batch Process

**What the macro does:**
- **Entry points:** `DryRun`, `PlaceNotes`, `RemovePlacedNotes`, plus dialog-free `DryRunBatch` / `PlaceNotesBatch` for Batch Process. The batch versions only work on the default model.
- **Placing:** each note goes into its section drawing model with `AddElement`, without opening the model.
- **Grid:** it finds the grid from its widest horizontal line, and the scale from any ±N offset label pair.
- **Duplicates:** it skips notes already on a section.
- **Models:** it opens (activates) each section model while it builds that model's note, then goes back to the model it started in. That's slower than before (a few seconds per section).
- **Level/color check:** it sets level, color and weight on the note and every line in it, reads them back, and stops (dry run included) if they didn't take.
- **Output:** it writes a report per file, a summary per folder, and a log of placed element IDs for undo.

## Step 6: Read the results with the engineer

The engineer sends back `_xsnotes_SUMMARY.txt`, the per-file reports, error screenshots, and what the notes look like. Read every file. Check:
- every file has a summary line
- the text scale factor is the same idea in each file (x0.2 and x0.5 are both fine; it depends on the file's default model)
- any CHECK flags, grid warnings, "beside the other note" lines and "already on" skips

If the macro has a bug:
1. Fix `scripts/make_macro.py` in this skill, not just the job copy.
2. Regenerate, and ask the engineer to re-import (remove the old module first) and compile.
3. Add the lesson to `references/lessons.md`.

If notes need moving after a real placement, `RemovePlacedNotes` in that file takes out exactly what the macro placed, then they place again.

**Done:** every file's summary reads `PLACE placed N`, matching the per-file counts, and the engineer has checked the placed notes.
