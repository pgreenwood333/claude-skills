---
name: profile-notes-extractor
description: "Pull the stacked notes in the profile view of MDOT/roadway plan-profile sheets (drainage structure callouts like 337 B / STA. 337+36.00 / SS-2 REQ'D LT / TOP = / INV. =, drive, box culvert and bridge notes) into a Word doc in station order, optionally for a station range; apply the user's approved corrections as a new revision; and reorder a plan PDF by the SHEET NO. in the title block. Use when someone uploads WK / plan-profile sheets and wants profile notes listed, extracted or put in Word, or the sheets put in sheet-number order."
---

# Profile Notes Extractor

Scripts are in this skill's `scripts/` folder (call it `$S`). Needs: `pip install pymupdf python-docx`
(add `--break-system-packages` if pip refuses). No other tools.

Reference output: `reference/us51-profile-notes-example.docx`, built from `reference/notes_example.json`
(103 notes, WK-45LT to WK-54RT, sheets 111-130). Match its format.

## Rules (each one came from a real mistake)
- Never type notes. Text comes from the PDF via `extract_profile_notes.py`; the doc is built from that JSON.
  Retyping once shifted pipe lines onto the wrong structures.
- Copy the sheet exactly, drafting errors included. List suspected errors for the user; change a line only after
  they approve it, with `apply_corrections.py`.
- Never say text is cut off or overlapping without seeing it in a rendered image. These OpenRoads sheets draw the
  visible letters as shapes with an invisible text copy on top, so the text layer alone can mislead.
- Never assume a sheet order (e.g. all LT then all RT): read SHEET NO. on every page.
- If a note lacks a line its neighbours have (e.g. no pipe-length line), flag it; never invent it.
- If the user's PDF is no longer available, ask for it again. Never rebuild a doc from memory.

## Reorder pages by sheet number
```bash
python3 $S/reorder_by_sheet.py "<plans>.pdf" "<plans> - Reordered.pdf"
```
Prints sheet ID and number per page, plus gaps and duplicates in the numbering. Tell the user about any.

## Profile notes to Word
1. Extract (add a station range or pages only if the user asked):
   ```bash
   python3 $S/extract_profile_notes.py "<plans>.pdf" notes.json [--sta-min 465+20 --sta-max 512+00] [--pages 1-20]
   ```
   Order: station, then LT before RT, then ID. `465+20` = 46520.
2. Check the printed list before building anything:
   - Every note starts with its ID line (`337 B`) or a `STA.` line (drives, culverts, bridges) and has a station.
   - Look for merged notes (two `STA.` lines in one), truncated notes (ending at `OPENINGS:`) and junk fragments.
   - Render and look at sheets with dense, side-by-side or LT/RT-paired notes:
     `python3 $S/render_check.py "<plans>.pdf" PAGE chk.png [x0 y0 x1 y1]` (use a note's x/y from notes.json to zoom).
   - Zero or wrong notes on a new plan set: the note height is measured automatically from the `STA.` words and
     printed at the end; check it, then override with `--hmin/--hmax` (px at 100 dpi) or `--region` if needed.
3. Build the doc (title format: `<Route> Profile Notes – STA. <a> to <b> (<first WK> to <last WK>)`):
   ```bash
   python3 $S/build_notes_docx.py notes.json "<Route> Profile Notes STA <a> to <b>.docx" "<title>"
   ```
4. Report:
   - Note count, sheet range, order rule.
   - What was left out: short leader labels beside pipes (`465 B SS-2 REQ'D LT INV. = ...`), pipe slope labels,
     leftover placeholder labels, and older duplicate notes still showing `XX"` sizes under a current note
     (drop a duplicate only after confirming it in a render).
   - A table of suspected drafting errors: Structure | Sheet | Issue. Look for: a pipe line with no material
     (`18" REQ'D.`); note length differing from the profile pipe label; pipe size differing from the plan view;
     opening size not matching the pipe; an odd L value (1.00' among 5.00'/10.00'); a pipe item that should be
     an end treatment (FE-1); a missing pipe-length line.
5. Corrections: write the approved edits to `corrections.json` (format: `reference/corrections_example.json`), then
   ```bash
   python3 $S/apply_corrections.py notes.json corrections.json
   python3 $S/build_notes_docx.py notes.json "<same name> (Rev N).docx" "<title>"
   ```
   Save each round as a new `(Rev N)`. Show a Was / Now table and confirm nothing else changed.

## Output format
Arial 10 pt, 1" margins, 0 pt paragraph spacing, Heading 1 title. One paragraph per note line, broken exactly as
on the sheet, with a blank paragraph between notes. No bold anywhere (title included), no tables, no sheet labels.
