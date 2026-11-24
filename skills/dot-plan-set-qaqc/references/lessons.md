# QA/QC lessons (approved by the engineer)

Agents and the grader read their section before a run; the `all` section applies to every agent and the grader. These override the defaults in the briefs.

## notematch
- Only drainage structures, drives and culverts need a cross-section note. Silt basins, barrier and pier-protection station ranges are not carried on the cross sections; do not flag them as missing an XS note. (2026-10-28)
- Before flagging a line as missing from a note, check the sheet image for overlapping text at that note. If the line is there but printed over another line, flag it as overlapping text (unless the overlap check already flagged that spot), not as a missing line or a note mismatch. Flag a missing line only when it is truly absent. (2026-10-28)
- When a profile note has an extra line such as (xx' JACKED OR BORED) or is printed in two columns, the line-by-line diff can pair unrelated lines; before keeping the flag, restate the discrepancy as the actual content difference (e.g. XS drops CL. V and the jacked-or-bored line). (2026-11-03)
- For existing-pipe abandonment notes (EXIST. PIPE + flowable fill), check the plan's REMOVE xx' EXIST. PIPE callouts and the length arithmetic before calling a plan length missing or different. (2026-11-03)
- For 'missing in plan' flags, quote the profile pipe line that is actually unlabelled (not the first pipe line of the note), and never list bearings or curve data as the nearest plan label. (2026-11-03)
- A note that only removes an existing drainage structure or pipe (REMOVE / EXIST. PIPE / flowable fill, with no proposed structure) is shown in the plan and profile views only; do not flag it as missing from the cross sections. A note that combines a proposed structure with a removal is shown in the plan, profile and cross section, so check all three. (2026-11-03)
- When a plan check matches a driveway pipe label, make sure that label is not already matched to another drive; if it is, find this drive's own label by its station before calling it a match (e.g. 485+86 LT vs 487+44 RT, 402+72 LT vs 408+91 RT). (2026-11-07)
- Differences only in spaces or line breaks (`18" , 1 @`, OPENINGS: on one line vs two) are not flags; punctuation-only differences (trailing period, INV vs INV., missing foot mark, 2'6" vs 2'-6") are low severity, and the workbook lists them in the Punctuation Mismatches section at the bottom of the Note Match tab, not in the main list. When a note has both an information and a punctuation difference, keep it in the main list and state both. (2026-11-07, updated 2026-11-09)
- A profile note headed only by a station that calls for a proposed structure (e.g. `1 - B-9 REQ'D.` with TOP/INV/OPENINGS) is a drainage note even with no structure ID heading: check it for its cross-section note and flag it when missing. (2026-11-07)
- When a 'missing in plan' candidate turns out to be a label that is there but different, replace the script's nearest-label highlights with the label actually quoted, and confirm that label sits on the run leaving the flagged structure in the flow direction. (2026-11-07)

## spelling
- Confirm the word is visible on the sheet image before flagging it. Text cut off at a viewport edge or hidden under a mask is not a misspelling; report clipped notes as a clipping problem instead. (2026-10-28)

## color
- Driveway notes in the profile print entirely black, pipe line included; the matching plan-view driveway pipe label prints blue. Never flag a black driveway note. (2026-10-29)
- Ditch grade labels and their station/elevation callouts in the profile may print blue or black; both are correct, never flag them. The ditch lines themselves print black: flag a ditch line drawn blue or purple. (2026-11-24)

## quantity
- Take every quantity locate rect from the build_index words boxes and confirm the highlighted row on a render; never estimate a row's y from the table's row pitch or from rendered pixels. (2026-11-22)
- On DOT traffic-control EQ summaries the TOTAL row can be the larger of the phase subtotals (devices reused between phases), not their sum; check how the other columns total before calling a TOTAL short. (2026-11-22)

## all
- A locate for a short bare number (e.g. a title-block sheet no. like 7) must be a rect from build_index words, not text: a text locate highlights the first match on the page, often inside the project number. (2026-11-22)

