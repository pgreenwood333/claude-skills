---
name: mdot-quantity-book
description: "Build an MDOT quantity calculations binder (quantity book) from a plan set's title sheet and the engineer's quantity calculation files (Excel .xlsx/.xlsm, Word, PDF, text): a title sheet + table of contents Word document and PDF in the firm's approved binder format, and one combined quantity-calculations PDF numbered from page 3. Use when someone wants a quantity book, quantity binder, quantity calculations binder, title sheet and index for their calcs, or to put their quantity calculations together for submittal."
---

# MDOT quantity calculations binder

Outputs (next to the inputs unless the user says otherwise):
- `<Project>_TitleSheet_Index.docx` and `.pdf`: page 1 cover, page 2 table of contents
- `<Project>_Quantity_Calculations.pdf`: every calc sheet, fit to the page, numbered 3, 4, 5... at the bottom center

Scripts are in this skill's `scripts/` folder (call it `$S`). The format is in `references/format.md`; it matches the
binders the engineer approved (multi-project Mill & Overlay, Main Street Bridge Replacement). Do not restyle it.

## 1. Get the files

Ask for anything missing in one message: "Drop in the plan set title sheet (PDF) and all your quantity calculation
files (spreadsheets, PDFs, Word or text files). If you have a binder you want me to match instead of the usual
format, drop that too." Work on copies in `qb_work/`; never edit the originals.
`pip install pymupdf openpyxl python-docx pillow numpy --break-system-packages -q` if needed. LibreOffice (`soffice`)
prints the spreadsheets; it is present in Cowork. Without it, ask the user for PDF exports of the spreadsheets.

## 2. Project facts from the title sheet

`python3 $S/title_sheet.py <title.pdf> qb_work/title` reads the project name, job/FMS numbers (e.g. 123456/301000),
federal-aid numbers (e.g. STP-0000-00(001)), counties and the design firm, and saves a trimmed image of the sheet.
Every field comes from the sheet; an empty field means it was not found, so ask rather than guess.
Jobs with several projects list every number; ask the user the order (e.g. a job may want 001, 003, 002)
and whether the cover shows all of them. Project name in title case as the user writes it
("SR 12 Mill & Overlay/Ramp Widening"). Status line is "Final Plans", no date, unless they say otherwise.

## 3. Inventory the calc files

`python3 $S/prep_sources.py scan <files...> --out qb_work`
For each spreadsheet tab it reports the content area (cells plus any drawing or picture, so nothing is cut off),
CORNER NUMBERS (small page numbers the engineer typed near the top right, e.g. `N3=10`), error values, and
formulas never calculated. Use it to propose the binder:
- Order: the engineer's corner numbers first (they show the order they intended). Otherwise group by type in this
  order: Asphalt/pavement, Vegetation, Earthwork, Drainage/structure excavation (pipes), Permanent erosion control,
  Temporary erosion control, then anything else (crushed stone, geotextile, memos).
- Section titles: short and specific, the way the approved binders read ("Asphalt, Tack Coat, Borrow, Sidewalk &
  Curb/Gutter", "Earthwork Calculations", "Structure Excavation (Pipes)").
- Superseded drafts: a file whose numbers duplicate another file's (e.g. an old Word scratch file repeating the
  Excel numbers) is proposed for exclusion, with the reason. Hidden tabs are skipped.
Show the proposed sections (title, source file/tab, pages) and ask the user to confirm or change them before building.

## 4. Print the files to PDF

`python3 $S/prep_sources.py convert qb_work --clear "FILE.xlsx!Sheet!N3" ... [--skip FILE] [--landscape Sheet]`
Formulas are replaced with their saved values first (plain and array formulas), which prevents LibreOffice from
printing #NAME? on cells that work in Excel. Clear every corner number listed by the scan so only the binder's
bottom numbers show. Then look at every page (render at 60 dpi): content cut off at an edge, a table split onto a
second page that should fit on one, a tiny unreadable page. Fix and re-convert. Drop pages the user does not want
with `drop` in the plan (step 5), never by editing their files.

## 5. Assemble, build the title + index, check

1. Write `qb_work/plan.json` (format in `scripts/assemble.py`): sections in the confirmed order, each with its PDFs
   and any `pages` / `drop`.
2. `python3 $S/assemble.py qb_work/plan.json "<Project>_Quantity_Calculations.pdf" --start 3`
   It numbers every page bottom-center (Helvetica 10) and writes the TOC page ranges to `<...>.toc.json`.
3. Write `qb_work/cover.json` (firm, project_name, numbers in order, subtitle "Quantity Calculations Binder",
   status "Final Plans") and run
   `python3 $S/build_title_index.py qb_work/cover.json "<...>.toc.json" qb_work/title/title_sheet.png "<Project>_TitleSheet_Index.docx" --pdf`
4. `python3 $S/check_binder.py "<Project>_Quantity_Calculations.pdf" "<...>.toc.json" --title-pdf "<Project>_TitleSheet_Index.pdf" --renders qb_work/renders`
   It fails on: error values printed (#NAME?, #REF!...), content touching a page edge, a stray corner number, page
   numbers out of sequence, a TOC that does not cover every page once, or a title/index PDF whose TOC differs.
   Fix every problem and re-run until it passes. Then look at all renders and both pages of the title/index PDF.

## 6. Deliver

Send the three files. In the message: the sections with page ranges, the project numbers used, any file left out
and why, and every warning (e.g. `HIDDEN_ERROR`: a cell holding #VALUE! under a picture; it does not print, but the
calc behind it may be broken, so tell the engineer which sheet). Never claim a quantity is correct; you checked
the binder, not the engineering.

## Revisions

The user will ask for changes ("drop the first page of permanent erosion control", "page numbers only at the
bottom"). Change the plan, re-run step 5 in full (assemble, title + index, check) so the TOC always matches the
pages. Never hand-edit the TOC.

## Rules

- Numbers, names and project numbers come from the user's files and title sheet only.
- Never edit the user's original files; work on copies.
- Page 1-2 are the title sheet and TOC, so the calcs start at page 3 unless the user says otherwise.
- If something cannot be printed cleanly, say which file and why instead of leaving it out silently.
