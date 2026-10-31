# Agent: Note match (plan note ↔ profile note ↔ cross-section note)

The engineer's rules:
- The note in the PROFILE view of a WK sheet must match the note on the CROSS-SECTION sheet (9000-series) for the
  same structure EXACTLY, line for line: ID, station, structure type and side, TOP, INV, H/L/W, openings, pipes.
- The PLAN note in the view above the profile (structure label box "[465 B]" and the pipe label along the run,
  "156' - 18\" RCP REQ'D") must correspond with the profile note: same structure ID, pipe length, size and material.

1. Run the check:
   `python3 $S/note_match.py <pdf> <work>/notematch --index <index>`
   (WK pages = prefix WK; XS pages = sheets numbered 9000-9999 or prefixed XS. Override with `--wk-pages` /
   `--xs-pages` if the index typed them differently; check the counts it prints.)
   The profile notes come from the same extraction as the profile-notes-extractor skill, which reproduced an
   approved 103-note document exactly. Pipe labels are searched on the sheet, its LT/RT partner, every sheet
   showing the same structure label, the two pages either side and the previous and next sheet numbers (pipes that cross a match line are labelled
   on the next sheet). Arch pipe written "65\" X 40\" RCP" in plan and "65\"X40\" RCAP" in profile is the same.
2. Verify every finding by looking at the sheets (`render ... --clip`, 200-250 dpi): the profile note, the plan label
   and pipe label, and the XS note. Confirm the numbers really differ before keeping a flag. Typical real findings:
   pipe length differs (plan 45' vs profile 40'), missing material ("18\" REQ'D."), size differs, a structure ID
   used for two structures, a pipe line missing its dash ("101' 65\"X40\""), an XS elevation or station differing
   from the profile note, a structure with no XS note.
3. "No cross-section note found": confirm by searching the XS sheets (`search <index> "<ID>"` and the station). The
   XS note may be laid out differently; if it exists but was not read, compare it by eye line by line and report
   any difference yourself.
   The check runs both ways: a profile note with no XS note, and an XS note (drainage structure or driveway)
   with no profile note ("cross-section note ... has no matching profile note"). Proposed drainage and driveway
   notes normally appear in both. Before keeping a reverse flag, look for the profile note: it may exist under a
   typo'd ID (626 B for 262 B) or be overprinted so the script could not read it (then it belongs to the overlap
   check, and the note-match flag points to that overlap finding instead).
4. Text drawn as linework is invisible to the script: if a plan or XS sheet has no text layer for its notes
   (index flag LOW_TEXT_DENSITY_POSSIBLE_SHX_TEXT), do the comparison visually and say so.
5. Every profile note with a pipe line gets a plan check, including station-headed notes (drives, junction boxes,
   culverts, existing pipes). Each structure note lists its DOWNSTREAM pipe, so compare it with the plan label on the
   run leaving that structure in the flow direction. Things the script cannot read, so check them by eye:
   - drive pipe labels written with an XX size (`40' - XX" ALT REQ'D.`): length and type (ALT vs RCP) must match the
     profile drive note, the size must match once filled in, and a drawn drive pipe with no label is a finding;
   - plan tags that are not the structure ID (`[SS-2_1]`, `B-9`, a typo like `[338A]` for 388 A).
6. Write `<work>/findings/notematch.json` with the confirmed findings (copy the script's findings, add any you found
   by eye with ids NM-101 onward). Format: `references/findings_schema.md`. Never drop a script flag silently: every
   one ends up either in the file or in a `not_flagged` list in your reply with a one-line reason (e.g. "drive
   pipe, no plan label expected", "label is on WK-26RT, the previous sheet number").
Reply with: plan checks, plan mismatches confirmed, XS checks, XS mismatches confirmed, the `not_flagged` list, and
anything read by eye.
