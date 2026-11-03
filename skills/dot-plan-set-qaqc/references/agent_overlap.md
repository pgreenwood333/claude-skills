# Agent: Overlapping text (WK profile views)

Goal: text in the profile views whose ink actually runs into other text: VPI/VPC labels printed on elevation
callouts, grade percentages through ditch-grade labels, station/elevation callouts stacked into each other.
Close-but-clear labels are NOT overlaps and must not be reported. Plan views are skipped unless the orchestrator
asks for them (utilities overlap there all the time).

1. Ink test (exact):
   `python3 $S/find_overlaps.py <pdf> <index> <work>/overlap` (add `--region all` if asked for profile + plan).
   On OpenRoads sheets the visible letters are drawn shapes with an invisible text copy on top; the script assigns
   each letter shape to its label, redraws pairs of nearby labels separately at 600 dpi and reports a pair only when
   pixels carry ink from both. `pairs_tested` lists every close pair and its shared ink (0 = clear).
   Check `<work>/overlap/regions/*.png`: the red box must cover each profile grid including the station row and the
   elevation readings under it. If a sheet with a profile reports none, rerun it with `--pages <n> --region all`
   and judge only the profile part.
2. Open the `crop` of every reported overlap and confirm the letters really collide. Describe what collides.
3. Visual pass over every tile in `tiles`, looking only for what the ink test cannot see: text with no text copy
   (labels that do not show up in search), and text crossed by the grade line, ditch lines or leaders badly enough
   that a value cannot be read. Zoom before reporting anything (`render ... --clip <box> --dpi 400`): if the letters
   are separated by any visible white gap, it is not an overlap. Tiles are 200 dpi; convert a pixel box to PDF points
   with `x_pt = clip_x0 + x_px * 72 / 200` (clip is in the tile entry).
4. Write `<work>/findings/overlap.json` (format: `references/findings_schema.md`), ids OVL-001 onward:
   - finding: what overlaps what, with station if visible ("VPI +66.499 label overlaps elevation 284.27 at STA 100+66").
   - evidence: both strings as printed. Include `shared_ink_pt2` from the script when it applies.
   - severity: high if a value (elevation, station, grade) cannot be read with certainty; medium if readable but
     colliding. Do not report touching-only or crowded labels.
   - locate: `{"page": N, "rect": <overlap_rect or your converted box>}` (tight: just the colliding area).
   - crop: the crop path.
Reply with: overlaps confirmed by the ink test, overlaps found only visually, and pairs you dismissed.
