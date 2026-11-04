# Lessons from the first job (123456, US 51, Nov 2026)

These all happened. Use them to set things up right the first time and to recognize errors when the engineer sends a report or a screenshot.

## Files and formats
- OpenRoads V8/CONNECT DGNs are OLE files with zlib-compressed streams. From the Mac you can read **model names** (`match_sections.py`), but **not the text inside models**: element data is packed. Don't try to decode it. That's reverse-engineering Bentley's format, and the engineer has ruled it out.
- No free tool writes a V8 DGN or a `.mvba` VBA project. Never hand-build either one. Deliver a `.bas` the engineer imports.
- A DGN can be newer than the PDF set. On 123456 the DGNs already had sections cut at most of the stations the PDF was missing. Always match against the DGN model names, not the PDF.
- Files sent from Drive come zipped. A file over ~100 MB can't come through the Drive connector, which returns files inline. Ask the engineer to share it "anyone with the link", then `curl -L "https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t"` into its own new folder on the external drive. Check the size and that `file` reports a zip.

## Cross sections
- Dynamic cross-section drawing models are named `<named boundary group> - <station>`, e.g. `MLUS51 - 471+91.4300`. Sheet models add ` [Sheet]`.
- Cutting new sections from VBA isn't supported: civil named-boundary creation is only in Bentley's .NET SDK, and its docs are thin. The engineer chose to cut new sections by hand rather than risk the file. Never script it. List the stations and the Place Named Boundary settings, drawing model only.
- Bentley's MicroStation MCP server (early access, Windows only, tied to Bentley Copilot) can't do civil work either. Don't suggest it for this. An npm package called `openroads-mcp` doesn't exist, and OpenROAD-MCP is a chip-design tool.

## VBA gotchas (all hit on 123456)
- **The module landed in the wrong project.** The engineer had a shared `status.mvba` open, and the import went into it. Batch Process then ran `[XSNotes]...` and quietly did nothing. Always say: click your own project in the Project tree, import, and check the module is under it.
- **The engineer couldn't save the project as `.mvba`.** Projects are created in the VBA Manager with **New**. Editor > Save writes into that file, and Export only writes `.bas` files.
- **`TextNodeElement` has no `TextStyle`.** Read the style from its first `TextElement` sub-element.
- **Setting a text style uses plain `=`, not `Set`** (`ActiveSettings.TextStyle = style`). This matches the office's working `status` macro.
- **Pass array or Variant items into helpers ByVal**, or the compile fails with "ByRef argument type mismatch".
- **`ActiveSettings.TextStyle = style` fails** with -2147218305 ("Unknown error") when the style only exists in the library. The fallback is the key-in `TEXTSTYLE ACTIVE <name>`. For a library-only level, use `ACTIVE LEVEL <name>`.
- **Batch Process runs the command file once per model** when a file is set to "All Models": 243 runs, 34 minutes. The batch subs only work on the default model. Tell the engineer to set each file to the default model.
- **Batch runs show no dialogs.** All output goes to `<file>_xsnotes_report.txt` and `_xsnotes_SUMMARY.txt` next to the DGNs. A missing summary line means the macro never ran for that file.
- Have the engineer run **Debug > Compile** after every import. It catches every compile error at once, before a run.

## Text size
- Drawing-model text is annotation-scaled. Text built from a style by VBA starts at a size set by the active model's annotation scale, and that differs per file: x0.20 in one file, x0.50 in another on 123456. So measure; don't compute from the style's height.
- `TextStyle.Height` returns the style's nominal value (0.01), not the drawn size. Don't use it.
- Per-line range height changes with the line count, because line spacing counts toward it. Compare **identical text**: build the reference note's exact lines from the style and compare total range heights. That's `ProbeScale`.
- **Standard size (built in since 2026-11-04):** "354 A" (8 lines, `_Gen_Notes`) = 15.001 ft tall in a 1"=10' drawing model. Probing every file against this fixed reference gave x0.2000 (3.1) and x0.5000 (3.2), and matched the copied notes in 2.1. The engineer confirmed the size is the same every time.
- Before the standard: copy an existing note in the same file (`CreateTextNodeElement1(template, ...)`). Next: the reference note saved by an earlier file (`_xsnotes_textsize.txt`). Last: from scratch (see SKILL.md).
- Notes built from a style are scaled geometry. If the drawing's annotation scale changes later, they won't follow it. Mention this when copy mode wasn't used.

## Placement
- Existing notes on 123456 sat at -115 (LT) / +108 (RT). The engineer then asked (2026-11-04) for notes tucked into the corner: LT left edge on the grid's left edge, RT right edge on the right edge (1 ft gaps), color 15 instead of ByLevel.
- Setting color/level on a text node in VBA may not reach its lines, so the macro sets every line too and reads them back before placing.
- Two notes in one corner: stacking them didn't fit, so they go **side by side**, toward the centerline. The dry run has to include notes placed earlier in the same run, or it won't show the second note's position.
- Some sections (508+30.75 on 123456) have no "-140"/"140" labels. Find the grid's edges from its widest horizontal line, and use any matching ±N offset label pair only for the scale.
- Side comes from the profile sheet suffix (WK-30**LT**). The note text can name both sides (box culverts), and junction-box notes may name neither.
- A note station that rounds the section station (388+41 vs 388+40.58) is the same structure. Anything farther than ~0.5 ft is the engineer's call: nearest section, cut new, or skip. On 123456 they chose nearest for gaps up to about 3 ft at 382+91 and 383+71, and for 455 B (1 ft). They chose to cut new sections for 4 to 30 ft.
