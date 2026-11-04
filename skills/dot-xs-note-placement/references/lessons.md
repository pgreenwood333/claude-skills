# XS note placement lessons (approved by the engineer)

Read your section before each stage of a job. These override the defaults in SKILL.md. Each is a rule from a real
mistake or an engineer's correction, dated. Add new ones only with `learn.py accept` after the engineer agrees;
at most 12 per section (merge old ones when a section is full).

## notes
- Only proposed drainage and driveway notes go on the cross sections. Removal-only notes (REMOVE / ABANDON / EXIST. PIPE / FLOWABLE FILL with no proposed structure) are plan and profile only; a note that combines a proposed structure with a removal does go on the XS. The QA/QC note match applies this rule; don't re-decide it. (2026-11-03)
- A fresh note match (no QA/QC review) flags some notes as missing that are on the XS but unreadable to the script (6 on 123456: 372+65, 372+75, 389+00, 391+20, 430+38 among them). Check every "MISSING on cross section" flag on the XS sheets before placing it. (2026-11-04)
- Take each note's side from its profile sheet suffix (WK-30LT). The note text can name both sides (box culverts) or neither (junction boxes). (2026-11-03)
- Copy the note text line for line from the profile, exactly as printed; never retype or reformat it. (2026-11-03)

## sections
- Match notes against the DGN drawing-model names (`<group> - <station>`), not the PDF: the DGNs can be newer and already have sections the PDF lacks. (2026-11-03)
- A note within 0.5 ft of a section is the same structure (the note rounds the station). Anything farther is the engineer's call: nearest section, cut new, or skip. On 123456 they took nearest for gaps up to ~3 ft and cut new sections for 4 to 30 ft. (2026-11-03)
- Never script cutting cross sections or named boundaries, and never write a DGN or .mvba. The engineer cuts new sections by hand, drawing model only, no sheet model. (2026-11-03)
- From the Mac only the DGN model names can be read (OLE + zlib streams); element text is packed. Don't try to decode it, and don't suggest Bentley's MicroStation MCP (Windows-only, no civil tools) for this. (2026-11-03)
- Some sections have no -140/140 offset labels (508+30.75 on 123456). Find the grid edges from its widest horizontal line; use any matching offset-label pair only for the scale. (2026-11-03)

## settings
- Notes are level XS_P_DRAINAGE, color 15 (the number, not ByLevel), weight 2, text style _Gen_Notes at its own size (0.01 in the Text Editor). (2026-11-04)
- Never copy a nearby note to get text settings: in 3.1 the macro copied "439 B" (Style (none), 0.0106) into 42 notes. Always build from the text style. (2026-11-04)
- Build each note with its section model active. VBA text takes the active model's annotation scale; in Batch Process that's the default model (x0.2 / x0.5 on 123456), which forces a size override. Active section = x1.000, no override. (2026-11-04)
- The standard note "354 A" (8 lines, _Gen_Notes) is 15.001 ft tall at 1"=10'. The macro checks it in every section before placing and stops if it is off by more than 3%. (2026-11-04)
- Place notes tucked into the grid corner: LT left edge 1 ft in from the left grid edge, RT right edge 1 ft in from the right edge, top 1 ft under the top grid line. (2026-11-04)
- Two notes in one corner go side by side, toward the centerline; stacked notes don't fit. (2026-11-03)

## macro
- Read the text style from a text node's first TextElement sub-element (TextNodeElement has no TextStyle). Set a style with plain `=`, not `Set`. (2026-11-03)
- `ActiveSettings.TextStyle = style` fails (-2147218305) when the style is only in the library; fall back to the key-in `TEXTSTYLE ACTIVE <name>` (and `ACTIVE LEVEL <name>` for a level). (2026-11-03)
- Pass array or Variant items into helpers ByVal, or the compile fails with "ByRef argument type mismatch". (2026-11-03)
- Setting level/color on a text node may not reach its lines: set every line and read them back before placing. (2026-11-04)
- Batch subs must only act on the default model: with "All Models" Batch Process runs the macro once per model (243 runs, 34 minutes on 123456). (2026-11-03)
- The log is written with LF line ends and VBA `Line Input` only splits on CR: read logs whole and split on LF. Only retire a log when every listed note was removed. (2026-11-04)
- Batch runs show no dialogs: every result and every stop goes to the report and `_xsnotes_SUMMARY.txt`. A missing summary line means the macro never ran for that file. (2026-11-03)

## steps
- Give the engineer the exact click path (SKILL.md Step 5) and nothing looser. The module must go into their own project (XSNotes): imported into a shared `status.mvba`, Batch Process ran `[XSNotes]` and quietly did nothing. (2026-11-03)
- Projects are created in VBA Manager with New; Editor > Save writes into the .mvba, Export only writes .bas files. Never hand the engineer a .mvba. (2026-11-03)
- Always Debug > Compile after an import, and remove the old module before importing an updated one. (2026-11-03)
- Batch Process: Initial Model = Default Model Only, every time. (2026-11-03)
- Big files from Google Drive: ask for "anyone with the link" and download with curl into its own new folder on the external drive; check the size and that it's a zip. (2026-11-03)
