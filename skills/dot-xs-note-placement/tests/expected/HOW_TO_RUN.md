# Job 000000: add the missing cross-section notes

The macro places **3 notes**:

| XS file | Notes |
|---|---|
| XS-A.dgn | 2 |
| XS-B.dgn | 1 |

Notes go on level **XS_P_DRAINAGE**, text style **_Gen_Notes**, weight 2, color 15, at the standard note size. Each note is tucked into the top-left corner of the section grid when the structure is LT (left edge on the grid edge), and the top-right corner when it's RT (right edge on the grid edge). A second note in the same corner goes beside the first, toward the centerline.

## 1. Cut the new sections by hand (if any are listed)

- 105+50.00  (XS-B.dgn)

Use **Place Named Boundary, Civil Cross Section**, with the same settings as the existing sections:
- drawing seed: DOT Cross Section Sheet - 10 Scale
- detail scale: 1"=10'
- group: ML
- left offset: -140
- right offset: 140
- top clearance: 10
- bottom clearance: 5
- vertical exaggeration: 1
- elevation datum spacing: 10
- create: drawing model only, no sheet model

Cut each one at **exactly** the station listed. The macro finds the section by its drawing model name, `<group> - <station>`. Create the **drawing model only, not the sheet model**.

The macro never cuts or changes sections. Bentley's VBA has no supported way to create civil named boundaries, so this step stays manual.

## 2. Load the macro

1. Copy `PlaceXSNotes.bas` and the three `xsnotes_batch_*.txt` command files to the PC that has OpenRoads.
2. **Search ribbon → VBA Manager → New →** name it **XSNotes**. (Already have XSNotes? Load it instead. Never use a shared office project like `status`.)
3. Click **XSNotes** → **Show the VBA Editor**.
4. Click **XSNotes** in the left sidebar → **File → Import File** → pick `PlaceXSNotes.bas`.
5. **Debug → Compile XSNotes.**
   - Nothing shows: **File → Save**.
   - An error box: screenshot it to Claude and stop here.

Updated `.bas`? First right-click the old **PlaceXSNotes** module → **Remove** (answer **No** to exporting), then import the new one and compile again.

## 3. Dry run (places nothing)

1. **Back up the XS files.**
2. **Search ribbon → Batch Process.**
3. **Initial Model: Default Model Only.**
4. **Add** files: every XS file in the table above.
5. **Command File:** `xsnotes_batch_DRYRUN.txt`.
6. **Process** the batch job. It's slow-ish: the macro opens each section while it builds that section's note.
7. In the folder on the C drive that holds the DGNs, find `_xsnotes_SUMMARY.txt` and every `<file>_xsnotes_report.txt`, and send them all to Claude.

## 4. Place (only after Claude gives the go-ahead)

1. Same Batch Process: switch the **Command File** to `xsnotes_batch_PLACE.txt` → **Process**.
2. `_xsnotes_SUMMARY.txt` should read `PLACE placed N` with the counts in the table above.
3. Check every note was added right, with the checklist spreadsheet: section, corner, text, and in the Text Editor the style **_Gen_Notes** at its own size, level **XS_P_DRAINAGE**, color 15.

## 5. If notes were added wrong

Same Batch Process: switch the **Command File** to `xsnotes_batch_REMOVE.txt` → **Process**. It deletes only the notes the macro placed (from each file's `_xsnotes_log.txt`) and touches nothing else. Each file adds a `REMOVE` line to the summary (`8 of 8 placed notes removed`). Tell Claude what was wrong; after the fix, dry run and place again.

## If something stops

The macro never skips a note silently. It stops and writes the step it was on, the last model it read and a suggested fix to the report and the summary. Send those lines (or a screenshot of the error box) and the macro gets fixed. Nothing is placed in a file after a stop, and notes placed before it are in the log.
