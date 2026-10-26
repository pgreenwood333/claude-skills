---
name: mdot-extract-standard-drawings
description: "Extracts the roadway standard drawings called out in an MDOT plan set's Detailed Index into a standalone \"Standards\" companion PDF, pulled from the current MDOT standards master in OneDrive and named from the plan set's own title-sheet data."
---

# MDOT Standard Drawings Extractor

## What this produces

A single PDF containing every roadway standard drawing (working number + sheet number, e.g. ECD-1 / 6101) listed in the plan set's Detailed Index under "STANDARD DRAWINGS - ROADWAY SHEETS," pulled from the current MDOT standards master, assembled in the same order the Detailed Index lists them, and named from the plan set's own title-sheet data.

Scope is fixed to the "ROADWAY STD. DWGS" section of the Detailed Index only — do not also pull Box Culvert, Bridge, or other categories even if their General Index checkboxes are marked. Bridge standards live inside the plan set itself ("SEE BRIDGE SHEET BEGINNING ON 8001"), not in the standards master, and are out of scope here.

This skill may be shared with other users whose OneDrive layout differs from the original author's, so it never assumes the expected folders exist — it checks first (Step 0).

## Steps

0. **Preflight: confirm the folder structure before doing anything else.** Using the OneDrive MCP connector, check that both of these exist:
   - Documents > ALLI WORKS (where plan sets live and the output gets delivered)
   - Documents > MDOT > MDOT Standards 2017 (where the standards master lives)

   If both are present as expected, briefly confirm this to the user and continue. If either is missing, renamed, or nested differently, **stop and ask the user** for the correct path rather than guessing or failing partway through — show them what you did find (e.g. sibling folder names under Documents) so they can point you to the right one. Do not proceed to Step 1 until both locations are confirmed, since a wrong guess here means silently reading or writing the wrong project's files.

1. **Find the plan set.** Once the folder structure is confirmed, go to Documents > ALLI WORKS. List the PDF files directly in that folder. If more than one plausible plan set is present, list them for the user and ask which one to use — do not guess.

2. **Read the plan set's Title Sheet.** Open the first sheet (Title Sheet) and find the "CONSTRUCTION PROJECT DATA" box. Read the "FMS & DETAIL" number (formatted like `123456/301000`). This is the base of the output filename.

3. **Ask the user two things**, one at a time (don't batch them into one question, and don't skip either):
   - What date should appear in the filename? (Default suggestion: today's date, but let the user confirm or override — the plan set's own PS&E/issue date may differ from today.)
   - What type of plans is this? Offer a fixed quick-pick list: **Field Review, Office Review, Draft Final, Final** (with an "Other" free-text fallback for anything that doesn't fit).

4. **Read the plan set's Detailed Index sheet** (usually sheet ID `DI-1`). Locate the "STANDARD DRAWINGS - ROADWAY SHEETS (N)" section specifically. Record every row's Working Number (e.g. `ECD-1`) and Sheet Number (e.g. `6101`) in the order they appear — this order is the final document's page order.

5. **Find the standards master.** In Documents > MDOT > MDOT Standards 2017, open the "Roadway Design Standard Drawings No Watermark" file's title/cover page and find its revision or issue date.

6. **Confirm currency with the user.** Tell the user the revision date you found on the standards master and explicitly ask them to confirm this is the most current version before proceeding. Never assume it's current on your own — this is a checkpoint, not a formality; wait for their answer before extracting anything.

7. **Build the sheet-ID → page-number map, fresh every run** (the master file can be re-split, re-paginated, or replaced between runs, so don't reuse or cache a prior mapping):
   - Extract the standards master's own internal "TABLE OF CONTENTS" pages (there are usually two: "SHEET 1 OF 2" and "SHEET 2 OF 2") to get the full ordered catalog of working numbers, titles, and sheet numbers.
   - Dump per-page text (e.g. `pdftotext -layout`, one page at a time) across the master file(s) and search for each target working number. Because these are CAD-exported PDFs, the working-number label near the "SHEET NUMBER" title-block field often merges into an adjacent text line rather than sitting alone — search for the ID as a substring/word match near "SHEET NUMBER," not just on an isolated line, and use the TOC's sequential ordering (each working number is usually immediately followed by the next TOC entry) to sanity-check candidate page numbers when a match is ambiguous.
   - **Never include a page on text-match alone.** Visually render every candidate page (image, not just text) and confirm the printed Working Number and Sheet Number in the title block match the target before accepting it into the map. This applies to all 28 (or however many) targets, not just a spot sample — the text layer is unreliable enough on these drawings that a silent wrong-page substitution is a real risk.

8. **Extract and assemble.** Pull each confirmed page as its own single-page PDF, then merge them into one PDF in the exact order the Detailed Index lists the sheets (not the order they happen to sit in the standards master).

9. **Name the output file:**
   `<FMS>-<Detail>-<YYYY-MM-DD>-<PlanType>-Standards.pdf`
   e.g. `123456-301000-2026-08-28-DraftFinal-Standards.pdf`
   - FMS and Detail numbers: the slash from "FMS & DETAIL" becomes a dash.
   - Date: the date the user confirmed in step 3, formatted YYYY-MM-DD.
   - Plan type: CamelCase with no spaces (Field Review → FieldReview, Office Review → OfficeReview, Draft Final → DraftFinal, Final → Final; for "Other" free text, CamelCase it the same way).
   - Always end with `-Standards`.

10. **Deliver.** Write the finished file back to OneDrive under Documents > ALLI WORKS (the same folder the plan set came from) using the MCP connector, and also send the file into the conversation so the user has it immediately.

## Verification

- Preflight check: both expected OneDrive folders were confirmed present (or the user supplied corrected paths) before any file was read or written.
- Count check: the merged PDF's page count must equal the number of rows found in the Detailed Index's "STANDARD DRAWINGS - ROADWAY SHEETS (N)" section.
- Identity check: for every page in the final merge, the rendered title block's Working Number and Sheet Number must match the corresponding Detailed Index row — confirmed by image, not text extraction alone (per step 7).
- Order check: the page order in the final PDF matches the Detailed Index's listed order top-to-bottom, not the standards master's internal order.
- Naming check: the filename matches the convention exactly, using the date and plan type the user actually confirmed (not assumed defaults).
- Currency check: confirm the user was shown the standards master's revision date and explicitly confirmed it before any extraction began.