# Job {{JOB}}: add the missing cross-section notes

The macro places **{{COUNT}} notes**:

| XS file | Notes |
|---|---|
{{FILE_TABLE}}

Notes go on level **{{LEVEL}}**, text style **{{STYLE}}**, weight {{WEIGHT}}, color {{COLOR}}, at the standard note size. Each note is tucked into the top-left corner of the section grid when the structure is LT (left edge on the grid edge), and the top-right corner when it's RT (right edge on the grid edge). A second note in the same corner goes beside the first, toward the centerline.

## 1. Cut the new sections by hand (if any are listed)

{{CUT_LIST}}

Use **Place Named Boundary, Civil Cross Section**, with the same settings as the existing sections:
{{CUT_SETTINGS}}

Cut each one at **exactly** the station listed. The macro finds the section by its drawing model name, `<group> - <station>`. Create the **drawing model only, not the sheet model**.

The macro never cuts or changes sections. Bentley's VBA has no supported way to create civil named boundaries, so this step stays manual.

## 2. Load the macro (once)

1. Copy `PlaceXSNotes.bas` to the PC that has OpenRoads.
2. Go to **Utilities > Macros > VBA Manager**. Load your own project **{{PROJ}}**, or click **New** to create it (it saves as `{{PROJ}}.mvba`).
   - Don't use a shared office project (`status`, `revisions` and so on). Check that **{{PROJ}}** is the project highlighted in the VBA Editor's Project tree before you import.
3. In the **VBA Editor**, click **{{PROJ}}**, then **File > Import File...** and pick `PlaceXSNotes.bas`.
4. Check that **PlaceXSNotes** shows up under **{{PROJ}} > Modules**.
5. **Debug > Compile {{PROJ}}.** It should show nothing. If it stops on a line, send a screenshot.
6. **File > Save {{PROJ}}.**

When you get an updated `.bas`, remove the old PlaceXSNotes module first (right-click > Remove, and answer **No** to exporting), then import the new one.

## 3. Dry run (places nothing)

1. **Back up the XS files.**
2. Tick **Auto-load** for {{PROJ}} in the VBA Manager.
3. Open **Utilities > Batch Process** and add every XS file. Set **Initial Model** to **Default Model Only**.
4. Use the command file `xsnotes_batch_DRYRUN.txt` and run it. It's slow-ish: the macro opens each section while it builds that section's note.

Or by hand, one file at a time: open it, **Utilities > Macros > Macros...**, pick **DryRun**, click **Run**.

Then read the output, written in the folder that holds the DGNs:
- **`_xsnotes_SUMMARY.txt`:** one line per file per run. Every file must have a line. "STOPPED" plus a reason means nothing was placed in that file.
- **`<file>_xsnotes_report.txt`:** one line per note, with where it would go. The `Size check:` line near the top should read about **x1.000**. Look for **CHECK** flags, "beside the other note" and grid warnings.

## 4. Place

1. Same Batch Process setup, command file `xsnotes_batch_PLACE.txt`. Or **PlaceNotes** by hand in each file (it asks before placing).
2. The summary should read `PLACE placed N` with the counts in the table above.
3. Check the notes with the checklist spreadsheet: section model, corner, text, and in the Text Editor the style **{{STYLE}}** at its own size, level **{{LEVEL}}**, color {{COLOR}}.

## Undo

**RemovePlacedNotes**, run by hand in a file, deletes exactly the notes the macro placed in that file. It reads them from `<file>_xsnotes_log.txt` and touches nothing else. After that you can change the settings and place them again.

For several files at once, use Batch Process (default model only) with `xsnotes_batch_REMOVE.txt`. Each file adds a `REMOVE` line to `_xsnotes_SUMMARY.txt` saying how many notes it removed.

## If something stops

The macro never skips a note silently. It stops and writes the step it was on, the last model it read and a suggested fix to the report and the summary. Send those lines (or a screenshot of the error box) and the macro gets fixed. Nothing is placed in a file after a stop, and notes placed before it are in the log.
