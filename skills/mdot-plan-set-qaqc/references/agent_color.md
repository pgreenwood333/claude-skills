# Agent: Print color (WK plan-profile sheets)

The rule (MDOT plan-profile sheets as printed):
- **Blue**: every proposed drainage item and its notes: pipes, inlets, boxes, headwalls, flowlines (US FL / DS FL), DA,
  skew, drainage notes in the profile ("18\" RCP REQ'D", "48\" DBL RCP").
- **Purple**: existing drainage structures and everything existing/surveyed: existing pipes drawn in the profile and
  their notes ("EXIST. 18\" RCP"), survey points and codes (MH, PBOX, POLE, BENCH), existing utilities, existing ROW
  lines and their labels. A plan-view label is purple when it labels something existing.
- **Black**: everything else, including proposed actions that refer to something existing: "TIE TO EXIST. ROW",
  "REMOVE EXIST. PIPE" are proposed work and print black (blue if the work itself is drainage, e.g.
  "CONNECT TO EXIST. INLET"). Ditch grades and their station/elevation callouts in the profile
  ("-4.79% LT DITCH GRADE", "RT 112+75.00 EL 283.00") print black. Roadway grades, VPI/VPC data, earthwork, erosion control (silt basins), ROW and
  easement acquisition (TEMPORARY EASEMENT REQ'D) are black.
Read `qaqc_memory/lessons.md` (section "color") before starting if the orchestrator gives you one; those are the
engineer's past corrections and they override the defaults above.

1. Measure (exact):
   `python3 $S/color_check.py <pdf> <index> <work>/color`
   Every letter's printed color is read from the PDF itself, so the color is a fact, not a guess. The script groups
   stacked lines into notes and lists candidates by rule (see the header of the script). Candidates are leads, not
   findings: decide each one.
2. For every candidate, open its `crop` and decide with the rule above:
   - Is the note about a proposed drainage item, an existing item, a proposed action on an existing item, or
     something else? Use the linework it points to (leader), the profile it sits in, and nearby labels.
   - A black drainage label can be wrong either way: blue if proposed, purple if existing (an "INLET TOP EL=" next
     to a purple surveyed manhole is existing survey data). Say which and why.
   - `MIXED`: confirm the lines are one note (same leader / block). Two separate labels that sit close are not.
   - Dismiss with a one-line reason; keep the list of dismissals for your reply.
3. Visual pass, one sheet at a time, on `<work>/color/overlays/*.png` (each note boxed in the color it measured as)
   and on 250 dpi renders of the profile (`build_index.py render ... --clip <profile box> --dpi 250`). Look for
   what the text rules cannot see:
   - **Linework**: pipes drawn in the profile: existing pipes purple, proposed pipes blue. A proposed pipe drawn
     purple or black, or an existing pipe drawn blue, is a finding.
   - A note whose wording says one thing and whose color says another, which the keyword rules missed.
   - Labels with no text copy (they do not appear in `notes`).
4. Write `<work>/findings/color.json` (format: `references/findings_schema.md`), ids COL-001 onward, task `color`:
   - finding: what is the wrong color and what it should be ("RT DITCH GRADE -6.10% prints blue; ditch grades print
     black in the profile (LT DITCH GRADE beside it is black)").
   - evidence: the text exactly as printed in backticks plus the measured color, e.g.
     `` `-6.10%` / `RT DITCH GRADE` measured #1337ff ``.
     Copy the hex from `line_colors`; never describe a color you did not measure or see.
   - severity: medium for a wrong-color drainage or existing item (a contractor could read existing as proposed);
     low for a cosmetic case (one line of a note on the wrong level when the item is clear).
   - locate: `{"page": N, "rect": <the candidate's rect>}`; crop: the candidate's crop.
Reply with: candidates confirmed, candidates dismissed (by rule, with the common reason), linework findings, and
sheets with no text found.
