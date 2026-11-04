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
2. Run **{{FIRST_FILE}} first.** It's the file the other files take their text size from.
3. **By hand:** open the file, go to **Utilities > Macros > Macros...**, pick **DryRun**, and click **Run**. A box at the end shows the counts and the report path.
4. **Or all files at once:**
   - Tick **Auto-load** for {{PROJ}} in the VBA Manager.
   - Open **Utilities > Batch Process** and add the XS files, with {{FIRST_FILE}} first.
   - For each file, set **All Models** to the default model only.
   - Use the command file `xsnotes_batch_DRYRUN.txt`.

Then read the output, which is written in the folder that holds the DGNs:
- **`_xsnotes_SUMMARY.txt`:** one line per file per run. Every file must have a line. "STOPPED" plus a reason means nothing was placed in that file.
- **`<file>_xsnotes_report.txt`:** one line per note, with where it would go. Look for **CHECK** flags, "beside the other note", grid warnings and the text scale factor at the top.

## 4. Place

1. Run **PlaceNotes** by hand on **{{FIRST_FILE}}**. It asks you to confirm before placing anything.
2. Open two or three sections and check the level, text size and corner position against an existing note. Include one with two notes in the same corner.
3. If it looks right, place the rest by hand, or use Batch Process with `xsnotes_batch_PLACE.txt`.
4. Check a few sections in each file, including any new sections and any note the report flagged.

## Undo

**RemovePlacedNotes**, run by hand in a file, deletes exactly the notes the macro placed in that file. It reads them from `<file>_xsnotes_log.txt` and touches nothing else. After that you can change the settings and place them again.

## If something stops

The macro never skips a note silently. It stops and writes the step it was on, the last model it read and a suggested fix to the report and the summary. Send those lines (or a screenshot of the error box) and the macro gets fixed. Nothing is placed in a file after a stop, and notes placed before it are in the log.
