# QA/QC lessons (approved by the engineer)

Agents and the grader read their section before a run. These override the defaults in the briefs.

## notematch
- Only drainage structures, drives and culverts need a cross-section note. Silt basins, barrier and pier-protection station ranges are not carried on the cross sections; do not flag them as missing an XS note. (2026-10-28)
- Before flagging a line as missing from a note, check the sheet image for overlapping text at that note. If the line is there but printed over another line, flag it as overlapping text (unless the overlap check already flagged that spot), not as a missing line or a note mismatch. Flag a missing line only when it is truly absent. (2026-10-28)
- When a profile note has an extra line such as (xx' JACKED OR BORED) or is printed in two columns, the line-by-line diff can pair unrelated lines; before keeping the flag, restate the discrepancy as the actual content difference (e.g. XS drops CL. V and the jacked-or-bored line). (2026-11-03)
- For existing-pipe abandonment notes (EXIST. PIPE + flowable fill), check the plan's REMOVE xx' EXIST. PIPE callouts and the length arithmetic before calling a plan length missing or different. (2026-11-03)
- For 'missing in plan' flags, quote the profile pipe line that is actually unlabelled (not the first pipe line of the note), and never list bearings or curve data as the nearest plan label. (2026-11-03)
- A note that only removes an existing drainage structure or pipe (REMOVE / EXIST. PIPE / flowable fill, with no proposed structure) is shown in the plan and profile views only; do not flag it as missing from the cross sections. A note that combines a proposed structure with a removal is shown in the plan, profile and cross section, so check all three. (2026-11-03)

## spelling
- Confirm the word is visible on the sheet image before flagging it. Text cut off at a viewport edge or hidden under a mask is not a misspelling; report clipped notes as a clipping problem instead. (2026-10-28)

## color
- Driveway notes in the profile print entirely black, pipe line included; the matching plan-view driveway pipe label prints blue. Never flag a black driveway note. (2026-10-29)

