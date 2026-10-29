---
name: mdot-opcc
description: "Build a Mississippi DOT (MDOT) Opinion of Probable Construction Cost (OPCC, engineer's estimate) Excel workbook from a plan set's Summary of Quantities, pricing every pay item from MDOT's published Item Bid Prices (low / average / high bid and quantity range, searched from this year back up to 10 years). Also looks up MDOT bid prices for any pay item numbers on request. Use when someone wants an OPCC, cost estimate, engineer's estimate or opinion of probable cost for an MDOT job, wants unit prices or bid history for MDOT pay items, or drops in a summary of quantities and asks what the job will cost."
---

# MDOT Opinion of Probable Construction Cost

Scripts are in this skill's `scripts/` folder (call it `$S`). Needs Python 3 with `openpyxl`, `requests`, `pymupdf`,
and `pycel` (used for sizing columns; optional). If any are missing (e.g. in Cowork), run
`pip install openpyxl requests pymupdf pycel --break-system-packages -q`.
The scripts must be able to reach `aashtoreports.mdot.ms.gov` over the internet. If that is blocked, say so;
never make up prices.
MDOT downloads are cached in `/Volumes/PGExtHD/OPCC/cache/` when that drive is present, otherwise in
`~/.cache/mdot-bid-prices` (set `MDOT_BID_CACHE` to choose).

## Price lookup on its own

`python3 $S/mdot_bid_prices.py lookup 203-A002 907-403-A015 ...` prints, for each pay item: the date range
that found it, price year, min/max quantity, and low/avg/high price. Use it when the user only wants prices.
`range 1/1/2025 12/31/2025 --out file.xlsx` saves MDOT's raw export for one date range.

How it searches: Jan 1 of this year → today. If an item has no bids, widen to Jan 1 of last year → today, then
the year before, up to 10 years. The ranges nest, so an item first found in the range starting in year X was
last bid in year X: that is its price year. MDOT's data starts around 2017–2018, so older years add nothing.
Source: MDOT's Item Bid Prices report (`mdot.ms.gov/portal/item_bid_prices`, served from
`aashtoreports.mdot.ms.gov/trnsreportspublic/reports/BidPrices.aspx`). There is no official API; the script fills
in the report's date form and downloads its Excel export. If MDOT changes the page, the script stops with an
error instead of returning wrong data. Say so; never make up prices.

## Building an OPCC

### 1. Get the inputs
Ask in one message for anything missing:
- the Summary of Quantities (PDF plan sheets, or the SQ spreadsheet if they have it)
- project name as it should read on the sheet (e.g. "Lakeland Drive Pedestrian Bridge")
- federal-aid number (e.g. STBG-9999-05(413)), if any
- the name for "UPDATED BY"

Job number and county come from the SQ header (e.g. "HINDS : 123456-301000").

### 2. Read the SQ and confirm
`python3 $S/read_sq.py <roadway SQ.pdf> [<bridge SQ.pdf> ...] --out opcc_work/sq.json`
Pass every SQ sheet set (roadway, bridge, ...); same-named sections are combined. Ask for the bridge
SQ (SQ-BR sheets) if the job has a bridge and only the roadway SQ was given.
Everything is Base Bid unless the SQ has an explicit label row ("BASE BID", "ADD OPTION 1", "A1"/"A2" → ADD OPTION
1/2, "ADDITIVE ALTERNATE 2"); any other text-only row is ignored with a warning. "OR" rows mark alternates (e.g.
304-F001 OR 304-F002 OR 304-F003, same quantity): the OPCC gets ONE line for the group, priced with the alternate
whose suggested MDOT price is lowest, and REMARKS names the others with their prices.
It skips note bubbles and notes
below the table. An item whose description ends in "Base Bid" or "Add Option n" (e.g. "Sunshade Add Option 3")
goes on that sheet. The same pay item on both sheets (e.g. roadway and bridge Structure Excavation) stays as
separate rows. Mention any notes on the sheets (e.g. "NEED PAY ITEM FOR ...") in the delivery message.
It uses Final quantities if the Final column has any values, otherwise Prelim. Show the user each section's
item count and any WARNING lines. Ask them to confirm, especially when Final is only partly filled.

### 3. Build the workbook
```
python3 $S/build_opcc.py opcc_work/sq.json --project "<name>" --fa "<FA no>" --by "<NAME>" \
    --out "<folder of the SQ>/<job>-<yyyy-mm-dd>-OPCC.xlsx"
```
Add `--refresh` to force fresh MDOT downloads (otherwise ranges ending today are reused for 7 days).
Add `--prior <earlier OPCC.xlsx>` when the user has an earlier OPCC for the job (ask). For items with no MDOT
price, its UNIT PRICE is filled in (green cells, year = estimate year so it isn't inflated again), and
REMARKS keeps "No MDOT bid price found; used original OPCC price $...". Matching is by sheet + pay item +
description, so duplicate items such as roadway vs bridge Structure Excavation match correctly.

Column widths are sized to fit every shown value (formulas are calculated with `pycel` first) on every build.
Header labels sit in merged cells so nothing spills over. Excel can't widen columns by itself without a
macro, so a much bigger number typed in later may show `####` until the column is widened.

What it writes, one tab per bid section, in the firm's OPCC layout:
- **Columns C–I and L:** PAY ITEM NO., PAY ITEM, UNIT, QTY, UNIT PRICE, TOTAL, % OF ITEMS, then a blank
  two-column gap (J:K), then REMARKS in L.
  TOTAL ITEMS COST is in G4, followed by SUB-TOTAL, Contingencies and TOTAL rows.
- **Columns N–Q + S–T:** the inflation block. YEAR = price year, INITIAL COST = suggested price.
  Inflation is 8%/yr from 2020 and 3%/yr before 2020, up to the estimate year. UNIT PRICE = the inflated price.
- **Columns V–AE:** MDOT bid data used, with the exact MDOT values: search range, price year, min/max/avg
  quantity, low/avg/high price, suggested price before inflation, and the method used.
- **Percentage items** (MOT 907-618-A001, Mobilization 620-A001, Construction Stakes 699-A001, Clearing &
  Grubbing ONLY when paid by Lump Sum (201-A001 / unit LS), and the Contingency row): 5% each, with a dropdown in column I to change it.
  They are a % of TOTAL ITEMS COST (Contingency is a % of SUB-TOTAL). A hidden column M keeps this from
  becoming a circular reference. Clearing & Grubbing by the Acre (201-B001) is NOT a percentage item: it is priced
  from MDOT bids like any other item.

Suggested price rules (`suggest()` in `build_opcc.py`):
- Normal items use a line from (min qty, high price) to (max qty, low price), with quantity on a log scale.
  - At or below min qty: high price. At or above max qty: low price.
  - When MDOT's min qty = max qty (one project): the average price.
- If high > 10× low (usually penny or unbalanced bids): the average price, with "CHECK: wide MDOT price range"
  in REMARKS.
- Only one bid price: that price, with "CHECK: only one MDOT bid price".
- **Left blank for the engineer** (yellow cells N/O, reason in REMARKS):
  - Per Plans items (`-PP`)
  - no MDOT price found
  - unit on the SQ differs from MDOT's unit
  - no quantity

### 4. Check, then deliver
The script prints every BLANK and CHECK line. Open the workbook (openpyxl) and confirm:
- every SQ item is on its sheet with its quantity
- G4, SUB-TOTAL and TOTAL are formulas

Send the workbook. In the message give:
- the total for each sheet. openpyxl won't calculate formulas, so compute them with `pycel`. On Python 3.14,
  first run `import ast; ast.Str = lambda s=None, **k: ast.Constant(s)`.
- the BLANK items the engineer must price
- the CHECK items worth a look
- the MDOT download date

Say plainly that the prices are a starting point from MDOT bid history; the engineer picks the final number.

## Rules
- Quantities and descriptions come from the SQ only; prices come from MDOT only. Never fill a blank with a guess.
- Never edit the user's SQ; write the OPCC next to it (or where they say).
- If MDOT's description differs from the SQ, keep the SQ wording and note "MDOT: ..." in REMARKS.
- Revisions (a different %, a different price, re-run with a newer SQ): rebuild with the script. For a single
  price, the user can type over column O (INITIAL COST) and N (YEAR) themselves.
