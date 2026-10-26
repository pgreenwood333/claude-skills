# Agent: Detailed Index check

Goal: every sheet listed in the Detailed Index (DI-#) matches the plans: same Sheet ID, same sheet number, and a
description that matches the sheet's title block; every sheet in the PDF is listed; nothing is duplicated.

Paths you are given: PDF, `index/` (from build_index.py), work dir, scripts `$S`.

1. Find the DI sheet(s): `python3 $S/build_index.py sheets <index>` and look for type INDEX.
2. Transcribe the index. It is usually a pasted image and often low resolution, so read it visually:
   `python3 $S/build_index.py render <pdf> <index> <page> --dpi 250 --tiles 3x2` and read every row of every tile.
   Use the OCR text in the DI chunk (`chunks/p000N_DI-1.md`) as a second reader: where the two disagree (a digit,
   a letter, a Sheet ID), zoom further (`--clip` around that row, `--dpi 350`) and decide from the image.
   Write `<work>/index_check/di_entries.json` in the format at the top of `$S/check_index.py`:
   group headings with their counts in parentheses, every entry with description, Sheet ID, sheet no, and the
   index total sheets. Keep Sheet IDs exactly as printed (spaces after the dash are fine; they are normalised).
3. Run `python3 $S/check_index.py <index> <work>/index_check/di_entries.json <work>/findings/index.json`.
   What the script checks for every listed sheet: the Sheet ID exists, the sheet number equals the title block's
   sheet number exactly, and the description matches the title-block title WORD FOR WORD (it reads the title twice:
   from the text layer and by OCR; a word counts as missing only if neither reader has it). Line order, dashes used
   as separators, line breaks and hyphen spacing ("MULTI- USE") are ignored; every other difference, including one
   wrong letter, is flagged. It also checks the index lists sheets in the same order as the PDF.
4. Judge the output before you finish:
   - Description flags: render the title block (`title_box` in index.json, `--dpi 250`) and confirm the difference
     is printed, not a reading error. Keep it with the exact wording of both; drop it only if the title block truly
     matches.
   - Missing / not-in-PDF flags: confirm with `search <index> "<Sheet ID>"` that the sheet really is absent.
   - Duplicate Sheet IDs in the index are high severity (a sheet listed under the wrong ID is a real error).
5. Title-block consistency across sheets: project number, county and FMS/construction number should be identical on
   every sheet. Use `search` for each value and the title-block text in the chunks; flag any sheet that differs.
6. Cross-references: notes like "SEE SHEET WK-5", "SEE DCS, SHEET PCMS-1", "SEE WK NO 38". Search for `SEE`,
   `SHEET`, `WK NO` and flag any reference to a sheet that is not in the PDF or the index.
7. Make sure every finding in `findings/index.json` has a `locate`. For index rows, the DI page plus the exact Sheet ID
   or description text as printed. Add your own findings (steps 5-6) with ids IDX-101 onward, same format
   (`references/findings_schema.md`).
Reply with: counts by severity, and any row you could not read with certainty.
