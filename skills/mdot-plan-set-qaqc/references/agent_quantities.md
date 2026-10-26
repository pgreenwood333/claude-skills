# Agent: Quantity reconciliation

Goal: Table 1 (EQ vs Summary of Quantities) and Table 2 (working-sheet recaps vs EQ), with every number read from
the sheets. You transcribe; `reconcile.py` does every sum and comparison. Never add numbers in your head.

## Workflow

1. Identify sheets with `build_index.py sheets <index>`: SQS sheets (prefix SQ or SQS) are the bid sheets; EQ-# are
   estimated quantities by item type; recaps are quantity tables on working sheets (WK, PMD, TC, ECP, ID, PSP, ...).
   If a sheet's type cannot be identified, note it and continue.
2. Transcribe the SQS rows into `<work>/qty/sqs.json`, the EQ rows into `eq.json` and recap rows into `recap.json`
   (formats at the top of `$S/reconcile.py`). Include `pdf_page` on every row. Sources:
   - The sheet chunk (`chunks/p000N_<ID>.md`): OCR rows of pasted tables (`pay item | description | unit | qty`) and
     vector tables. Words tagged `⟨?⟩` are low confidence.
   - The image itself: `render <pdf> <index> <page> --clip <table box from the chunk header> --dpi 250 --tiles 2x1`.
     Check every quantity against the image. On LOW_RES_RASTER pages read from the image first and use OCR as the
     cross-check. One misread digit creates a false MISMATCH, so zoom (`--dpi 350`) wherever OCR and image differ.
   - Keep quantities exactly as printed (commas fine). Record SQS footnote markers in `footnotes`.
3. For each EQ row set `recap_expected` (rules below) and, if the EQ table lists which sheets carry the recap, put
   them in `recap_sheets_listed`.
4. Put every rule-based decision in `overrides.json` keyed by pay item, by "ADD OPTION 1|<pay item>" for one
   schedule only, or by "<schedule>|D:<description>" for rows without a pay item: special statuses, the
   note, the paired quantity for OR items, and the most likely `cause` for each mismatch.
5. Run `python3 $S/reconcile.py <work>/qty`. Fix every entry under `problems` (unreadable quantities). Then re-check
   each MISMATCH by zooming into both sheets again; correct any misread and re-run. A MISMATCH should only survive
   if you have looked at both numbers on the image.
6. Reply with Table 1 and Table 2 status counts, and every MISMATCH in one line each.

## Things this plan format does (learned on MDOT sets)

- Bid schedules: the SQ sheets are split into BASE BID, then A1, A2, A3 (Add Options 1-3), and the same pay item
  appears in several. Put `section` on every row ("BASE BID", "ADD OPTION 1" ...). EQ tables say their schedule in the
  title, e.g. "SUMMARY OF DRAINAGE (ADD OPTION 1)". Reconciliation is per schedule.
- Pasted tables are pictures cut into tiles; read them through the chunk OCR and confirm on the image. OCR misreads
  happen (e.g. 908 read as 806): a row value that disagrees with its own subtotal is almost always a misread.
- Traffic control items reused between phases are counted once (TC-1 36 LF + TC-1A 36 LF of barricade = 36), so a
  total smaller than the sum of the phase rows is normal; reconcile the table's TOTAL row.
- Earthwork and bid limits: the WK profile shows a bid-limit line (arrows labelled "BASE BID | ADD OPTION 1") above the
  "CUT = ... C.Y." / "FILL = ... C.Y." labels, and each label has arrows marking the station range it covers. Read
  both before assigning a label to a bid. A cut/fill segment whose arrows cross the bid limit belongs to BOTH bids
  (e.g. CUT = 2711 C.Y. spanning 109+00 to 114+70 across the limit at 110+16): never compare it to one bid's EQ
  value. Compare per bid only when every segment sits inside one bid; otherwise do not raise earthwork cut/fill
  mismatches from the profile labels, and use the "EARTHWORK TOTAL THIS SHEET" borrow line and the EQ formulas
  (unclassified = fill x 1.25, excess = cut - fill x 1.25) as the checks instead.
- Recap sources on working sheets: the "EARTHWORK TOTAL THIS SHEET" and "PERMANENT / TEMPORARY EROSION CONTROL
  ITEMS" tables on WK and ECP sheets, drainage
  callouts ("24' - 22" x 13" RCAP REQ'D", "4 - 48" FE-1 REQ'D"), quantity boxes on TC, PMD and PSP sheets. The vector
  "tables" extracted from CAD sheets are often garbled: read these tables from the image.
- Rows that only exist for Table 2 (earthwork cut/fill, sign counts) get `"table2_only": true` and no pay item.
- Lump-sum items (mobilization, MOT, stakes) and lighting/electrical items (quantities on the L/E sheets) have no
  roadway EQ total: ESTIMATED-NOT RECONCILED with that note. A placeholder pay item ("Need Pay Item For ...") is a
  high-severity finding of its own.
- Sign areas: check that the EQ sign charts use one convention for octagons (true octagon area vs the square).

## Quantity rules

**EQ vs SQS (Table 1, highest priority).** For each EQ item find the SQS match: pay item number is the key; if the
EQ sheet has none, match by description. MISMATCH cites both Sheet IDs (for example EQ-3 vs SQ-2).
- EQ quantities are exact decimals. SQS quantities are the EQ quantity rounded up to the next whole number. A
  difference due only to rounding up is a MATCH (the script applies this).
- When an EQ sheet has Phase I, Phase II and Job Totals sub-tables, use only the Job Totals row, never phase
  subtotals. This applies to earthwork.
- Multi-column recap tables: confirm the column header for each item. Never pull from an adjacent column.

Item-specific sources:
- Vegetation Schedule (VS-1) items (grassing, topsoil, agricultural limestone, superphosphate, mulch, insect pest
  control, temporary grassing) have no EQ total: `table1_status` ESTIMATED-NOT RECONCILED, note "Quantity derived
  from Vegetation Schedule (VS-1)". Never NOT FOUND ON EQ.
- Pavement items (asphalt, all stone base, milling, tack coat, rumble strips, transverse grooving, sawing/sealing)
  are estimated from typical sections and never appear on EQ sheets: always ESTIMATED-NOT RECONCILED.
- "OR" alternative items equal the quantity of the item they replace. If not on the EQ sheet, set `eq_qty` to the
  paired item's quantity in overrides (the result is then MATCH) and say so in the note.
- Bridge End Pavement table: read each column header. BEP area is SY, sawing and sealing joints LF, plus filter
  material, drain pipe, geotextile and others. Do not cross-contaminate adjacent columns. Bridge End Barrier is
  under the rail column (for example 37.5" Rail) of the same table; never NOT FOUND ON EQ.
- Fencing quantities are in the "Fencing Items Required" table on the EQ sheets.
- Combination Concrete Curb and Gutter quantities are in the "Combination Concrete Curb and Gutter Required" table.

**Footnotes.** SQS footnotes modify quantities; read and apply them before accepting a mismatch. Quantity from
multiple sources: VERIFIED WITH FOOTNOTE. "Estimated" or "as directed by the engineer": ESTIMATED-NOT RECONCILED.
If a footnote says the SQS quantity includes a bridge EQ contribution, check roadway EQ total + footnote bridge
quantity = SQS total and put the arithmetic in the note (add the bridge quantity as an extra eq.json row with its
source so the script sums it).

**EQ Recap vs EQ (Table 2).** Decide per EQ item whether a recap is expected.

Recap expected (distributed across working sheets): pavement markings (PMD-#), traffic control (TC-#), temporary
erosion control (ECP-#), permanent erosion control (WK-#), driveways, side drains, guardrail (WK-#), pipe culverts
and drainage (WK-#), permanent signing (PSP-#), combination concrete curb and gutter (ID-#).

Recap not expected: mobilization, maintenance of traffic, railway-highway provisions; lump-sum structural or bridge
items; single-quantity items not distributed by location; items where the EQ sheet shows one total with no sheet
breakdown; Vegetation Schedule items; internally estimated pavement items; removal items.

Recap source rules:
- Recap quantities come only from working plan sheets (WK, PMD, TC, ECP, ID, PSP and similar). Never source a recap
  from an EQ-# sheet. If an item's only source is an EQ sheet, it has no recap.
- Permanent erosion control: sum ALL WK sheets present (WK-3, WK-3A ... WK-3G, WK-4 ...), e.g. the "PERMANENT
  EROSION CONTROL ITEMS" table on each WK sheet. Temporary erosion control: sum ALL ECP sheets. PARTIAL-SOME RECAP
  SHEETS MISSING only if a sheet the EQ table lists is genuinely absent from the PDF.
- Permanent signing: recap source is the "SIGNING (PERMANENT)" table on PSP sheets, summed across all PSP sheets.
  The EQ total comes from the chart(s) titled "Standard Roadside Signs", which may be split by thickness
  (0.100", 0.125"); read all of them. Identify charts by title, not Sheet ID. "Summary of Traffic Control Signs
  Required" is temporary traffic control signing only and is never a source for permanent sign quantities.
- Earthwork: the "EARTHWORK TOTAL THIS SHEET" table on each WK sheet is the recap for the EQ earthwork Job Totals.

Statuses: Table 1: MATCH, MISMATCH, VERIFIED WITH FOOTNOTE, ESTIMATED-NOT RECONCILED, NOT FOUND ON SQS,
NOT FOUND ON EQ. Table 2: MATCH, MISMATCH, N/A-NO RECAP EXPECTED, RECAP NOT FOUND, PARTIAL-SOME RECAP SHEETS MISSING.

**Discrepancy Detail.** For each surviving MISMATCH give the most likely cause from plan-set context in `cause`
(e.g. "EQ-2 earthwork uses Phase I subtotal", "recap omits WK-3A", "SQ footnote 2 adds toe walls").
