---
name: appstore-screenshot-captioning
description: Make App Store / Google Play screenshots — from raw iPhone captures to finished, localized, keyword-rich marketing slides (flat brand-colored background, two-tone keyword titles, device frame, enlarged "3D pop-out" UI callouts) and upload them via the App Store Connect API. Also overlays captions onto existing device-frame exports (AppScreens, Fastlane) with pixel-matched typography. Use whenever the user wants new or redesigned App Store screenshots, localized screenshot sets, screenshot captions, or to "make the screenshots look like the top apps".
user-invocable: true
---

# App Store Screenshots

## Workflow A — pop-out slides from raw phone captures (DEFAULT for new/redesigned sets)

This is the approved Peyton style (built for Free Up Storage, Sep 2026). Engine:
`scripts/popout_render.py` (copy it + a captions JSON into the project, e.g.
`scripts/store-screenshots/`; example: `scripts/popout_captions.example.json`). Upload:
`scripts/asc_push.py`. Run the steps in order.

### 0. Ask for keywords FIRST (captions are indexed for ASO)
Since June 2025 Apple OCR-indexes screenshot caption text for search ranking, so every caption is
keyword real estate. **Before writing any caption, ask the user for their keyword research** per
market (ASOMobile/Applyra exports, or run applyra). Then:
- Put the highest-traffic *relevant* keyword for each slide's feature in the title (the accent
  words). Use the verb people actually search, not the dictionary one (pt-BR "apagar" ≫ "excluir";
  es-MX "borrar" ≫ "eliminar"; de "Handy aufräumen"/"Speicher reinigen" ≫ "Speicher freigeben").
- Subtitle carries 1–2 secondary keywords ("armazenamento", "celular", "Speicherplatz").
- Never use a keyword for a feature the app doesn't have (email cleanup, antivirus, cache, AI…),
  never a competitor brand, and never "free/gratis" as a claim in a caption for a paid app.
- **Never put Apple trademarks (iPhone, iPad, iCloud…) in an app name, subtitle, or keyword
  field** — Free Up Storage 1.0.1 was rejected under Guideline 5.2.5 for "Limpar iPhone" in a name.
  Use the local word for phone instead (celular, móvil, Handy, телефон). Descriptive use in
  descriptions and captions ("your iPhone") is fine.
- Make each translation read the way natives talk — rewrite, don't translate word for word — and
  check false friends (pt "borrar" = blur).

### 1. Competitor research (don't guess the layout)
Pull the category #1's screenshots at full res and look at them next to the user's current listing:
```bash
curl -s "https://itunes.apple.com/search?term=<category>&entity=software&country=us&limit=10"   # top = highest userRatingCount
curl -s "https://itunes.apple.com/lookup?id=<id>&country=us"  # screenshotUrls; swap trailing /NNNxNNNbb.jpg for /1290x2796bb.jpg
```
Build a contact strip and name what they do (for cleaners → Cleanup: solid color bg, big centered
title + one-line subtitle, upright phone, UI enlarged and lifted off the phone). Copy the
*structure*, never their colors or copy.

### 2. Color scheme
Solid, flat background (no gradients/glow — see the global CLAUDE.md bans) derived from the app's
own theme file, *darker than or different from* the app's screen bg so the phone separates. Free Up
Storage: bg `#1E3327` deep forest; title cream `#EEE8DC` (the app's text color); accent = app primary
lifted for contrast on dark `#9CC2A6`; subtitle `#B9C6BB`; bezel `#0C100D` with a `#4A5E50` rim.
Pick per app.

### 3. Word placement
1320×2868 (iPhone 6.9"). Title SF Pro Display Heavy 118 px, centered, top at y≈190, max 2 lines
(auto-shrinks); `|` forces a break (hero: "[Free Up Storage]|in Minutes"). Subtitle SF Pro Display
Medium **62 px** (54 was too small to read), centered, one line on slides 2+. Shorten rather than
wrap, and never leave a 1–2-word orphan line. Phone (screen 940 px wide) starts ~80 px under the
subtitle.

### 4. Keyword coloring
Two-tone title: the keyword phrase in the accent color, the rest in cream. Mark it with brackets in
the captions JSON: `"Delete [Duplicate Photos]"`. The bracketed words should be the slide's target
search keyword.

### 5. The 3D pop-out (what makes it not look flat)
For each slide, crop the 1–2 most persuasive UI elements from the capture (biggest number, the
"Best" pick, the red Delete button, the Dark-mode switch). Enlarge them ~1.3–1.45× to ~1150–1240 px
wide so they overhang the phone on both sides, and center each over its own spot on the phone.
Depth = soft dark contact shadow (blur 30, opacity ~120/255, offset y+28) + a 3 px rim — depth, not
glow. Boxes live in `POPS` as capture-pixel coords `(x0,y0,x1,y1,radius,target_w)`. Measure them by
test-cropping every locale (layouts match across languages). Crop tight: drop section headers
("5 similar / Keep all") so only the payoff pops, and pop whatever shows the biggest number.
- Demo numbers: `DEMO` + `restate_*()` repaint small UI numbers (e.g. 238 MB → 24.3 GB, 177 → 1177)
  by re-rendering the whole string from the app's own i18n templates in SF Pro Text at the measured
  size, weight, color and tracking (button: Semibold 38, −0.45 px tracking; muted text: Regular
  31/35.5). Keep every related number consistent across slides (recompute totals).

### 6. Gemini for extras (optional)
The `gemini` MCP (`mcp__gemini__generate_image`, `edit_image`, `analyze_image`) is available for
"cool additions": inpainting a clean base, a hero illustration, or a background texture, as long as
it stays within the flat, no-glow rules. `analyze_image` is handy for a second opinion on
legibility. Don't use it for anything the deterministic PIL path already does well.

### 7. Captures, render, verify, ship
- Raw captures go in `screenshots/<lang-Name>/{1-photos,2-contacts,3-profile,4-duplicates}.png`.
  Chat-attached images arrive compressed (920×2000). Ask for AirDropped originals (iPhone 17 =
  1206×2622) for final sharpness; the renderer handles either.
- When the user sends duplicate captures, keep the one without truncated text. If both are flawed,
  keep the one whose flaw is least obvious.
- `python3 scripts/store-screenshots/render.py [lang-Name…]` → `screenshots/appstore/<lang>/0N.png`.
  Always build a contact strip of all locales and look at it before saying it's done; check that no
  subtitle wraps on slides 2+.
- Upload: `asc_push.py push` (API key is in the global CLAUDE.md). It replaces the `APP_IPHONE_67`
  set and can create locales with name/subtitle/keywords/description/whatsNew from `metadata.json`.
  Creating an appInfoLocalization auto-creates the version localization (PATCH it, don't POST).
  Don't overwrite an existing locale's name or keywords without asking — extra locales (es-MX, vi…)
  are often deliberate US-indexing plays.

## Real 3D iPhone frames (assets/devices)

Never draw or shear a phone bezel in PIL for a 3D/angled slide — render the real iPhone 17 Pro Max
model instead and composite the transparent PNG:
```bash
node assets/devices/render_device.mjs --screen cap.png --out phone.png --baseRotY 180 \
  --frameColor '#cfcfd4' --rotX .. --rotY .. --rotZ .. --fov .. --distance ..
```
Then crop the output to its bounding box (it's transparent PNG) and composite onto the slide.

- **Browser**: uses the installed Google Chrome via Playwright, loaded from
  `/Volumes/PGExtHD/tools/appscreen-mcp/mcp-server/node_modules` (override with `PLAYWRIGHT_PKG`;
  set `CHROME_CHANNEL=''` to fall back to bundled Chromium instead).
- **How the screen works**: the GLB's OLED isn't image-mapped, so the renderer measures the model's
  front "Glass" mesh at runtime and lays the capture on its own plane on top, with rounded corners
  and a Dynamic Island cutout (`--inset 0.035 --cornerRadius 0.13` are the tuned defaults — don't
  need to touch them per slide).
- **Angle conventions** (three.js YXZ euler order): negative `rotX` tilts the top away from camera;
  positive `rotY` turns the left side + buttons toward camera; positive `rotZ` leans the top left.
  Proven presets:
  - Hero leaning right, big (Green Noise slide 2 style): `rotX -30 rotY 35 rotZ 0 fov 34 distance 3.6`
  - Smaller phone leaning left (slide 3 style): `rotX -28 rotY 28 rotZ -14 fov 32 distance 4.0`
  - Front-facing (flat): `rotX 0 rotY 0 rotZ 0 fov 22 distance 6.2`
- **zsh gotcha**: don't try to batch angle presets with `set -- "a b c"` — zsh doesn't word-split
  that like bash does and the loop silently sees one arg. Drive multi-render batches from a small
  Python script instead.
- **Flat alternative**: for a plain front-facing frame with no 3D angle, Apple's official Product
  Bezels (developer.apple.com/design/resources) are a legitimate lighter-weight option.
- **Attribution**: the model (`iphone-17-pro-max.glb`) is CC BY 4.0 by Ranguel — see
  `assets/devices/CREDITS.md`. Credit Ranguel in the shipping app's own credits/CREDITS.md whenever
  a render of it goes out the door.
- The `appscreen` MCP (registered in Claude Code) is available if you want full automated slide
  layouts instead of building composites by hand.
- **Reference implementation**: `/Volumes/PGExtHD/BrownNoiseFree/scripts/store-screenshots/render_v2.py`
  — see `device()` for the render+crop+composite pattern and `slides23()` for a panorama phone that
  spans two adjacent slides.

---

# Workflow B — captioning existing device-frame exports (legacy)

Author polished caption overlays onto **blank** screenshot exports (device frame already
applied by AppScreens/Fastlane/etc. — you only add text). Everything is deterministic PIL,
so it's cheap and repeatable. Three slide types, one shared visual language.

## Workflow (the reliable path)

1. **Get two exports from the screenshot tool** (e.g. AppScreens → Export):
   - **"With Captions" for one reference locale (usually English)** → this is your *style
     reference* (font, size, color, position). Measure it, never guess.
   - **"No Captions" for every locale** → the blank device-frame slides you overlay onto.
   - Export per size (**iPhone 6.9″ = 1320×2868**, iPad 13″ = 2064×2752). Captions are OCR-indexed
     by Apple for ranking (since June 2025), so caption text is ASO, not just decoration.
2. **Measure the reference** (see "Calibrating to a reference" below) → accent hex, title/subtitle
   px sizes, y-positions.
3. **Render** each locale's blank slides with `scripts/caption.py` (content), `scripts/lady_hero.py`
   (photo hero), `scripts/overlay_body.py` (labeled figure hero).
4. Save each locale to its own folder, e.g. `Captioned/<locale>/iPhones 6.9/01..08.png`, then
   re-import into the tool or upload to App Store Connect.

## Locked spec (matched to the AppScreens "Real Dark" template, 1320×2868)

**Content slides (1–6) — `scripts/caption.py`:**
- Font: **SF Pro Display Heavy** title, **SF Pro Display Medium** subtitle
  (`/Library/Fonts/SF-Pro-Display-*.otf`).
- Title size **~116 px**, wraps to 2 lines, top-centered; block vertically centered at **y≈400**.
- Subtitle **~54 px**, ~90 px below the title.
- **Two-tone title**: lead keyword in **periwinkle `#9999F4`**, remainder **white**. Pass the
  split with a `|` in the title string: `"528 Hz|para Dormir"` → "528 Hz" lavender, "para Dormir"
  white. All-purple = trailing `|` empty (`"Ruido Blanco, Rosa y Marrón|"`).
- No drop shadow needed on the dark starfield (a faint one is baked into the helper).

**Photo hero (lady) — `scripts/lady_hero.py`:**
- Title font: **Palatino** (serif, faux-bolded), 2 lines, top-centered ~y235. Line 1 **white**,
  line 2 **lavender `#B89DF2`**. Auto-fits width.
- Bottom **keyword chips**: 2 rows × 3, **all darker gold `#D8A520`**, emphasis by **weight**
  (Heavy vs Medium) not color — bold indices default `{0,2,4}`. Auto-shrinks to fit width.
- **No stars / no review quote** for localized markets (drop them; they read as fabricated).
- Chips carry the *researched native keywords* (e.g. es `Acúfenos`=tinnitus, `TDAH`=ADHD).

**Figure hero (labeled infographic) — `scripts/overlay_body.py`:**
- Needs a **clean base** (figure with the old labels masked off — use Gemini/inpaint once, keep
  the PNG). Then it draws `NNN Hz` + localized name + a leader line per frequency.
- Labels pushed to the **edges** and kept **out of the arm-spread band (y≈0.38–0.47)** so text
  never overlaps the figure. Positions live in the `POS` dict (accent, side, xfrac, yfrac) —
  tune per-figure; move a label's yfrac to lift its leader clear of a limb.
- **Leader line = fixed length for ALL** (`UL=270` underline) + a **fixed diagonal kick**
  (`DX,DY=82,28`) angling toward the figure. Long names **stack to 2 lines** (`layout_name`)
  so the underline stays uniform. Per-frequency accent colors match the app's brand palette.
- Top caption via `caption.py` with `center_y≈215`, `title_size≈90`, `sub_size≈60`, subtitle
  forced to 2 lines — call out the extras (binaural beats, colored noise, nature, meditation).

## Calibrating to a reference (do this, don't eyeball)

```python
from PIL import Image
im = Image.open(REF).convert("RGB"); W,H = im.size; px = im.load()
# accent hex: scan the keyword region for the most saturated lavender pixel cluster
# title/subtitle y-extent: rows where count(sum(px)>430) exceeds a threshold
# font px: measure cap-height of a title glyph, size ≈ cap_height / 0.7
```
Sample the accent from the actual keyword pixels; measure title/subtitle bands by scanning bright
rows; derive font px from cap-height. See the git history of this project for the exact sampler.

## Gotchas
- **Colors from JSON come in as lists** → `tuple(c)` before PIL, or PIL raises "color must be int
  or tuple".
- **Diacritics**: SF Pro Display + Palatino both cover Polish/Czech (ł ż ę č ř ě ů) — verify by
  rendering; if a serif tofus, fall back to Times.ttc.
- **Frequency names**: pull the *authoritative* localized names from the app's own i18n
  (`i18n/content/<lang>.ts`), don't translate yourself.
- **macOS `._` files**: exFAT/AppleDouble junk after copies — `find OUT -name '._*' -delete`.
- **Keep "528 Hz" (and Hz numbers) in captions** — numeric keywords win internationally and need
  no translation; native word-translations of "solfeggio/healing" get ~zero search abroad.
- iPhone **6.9″ = 1320×2868**, iPhone 6.5″ = 1284×2778, iPad 13″ = 2064×2752 (all portrait, RGB,
  no alpha). 6.9″/6.5″ share the 19.5:9 aspect; iPad is 4:3 (needs its own art).

## Scripts
- `scripts/caption.py` — content-slide + generic top-caption engine (two-tone title + subtitle).
- `scripts/lady_hero.py` — photo hero (serif caption + gold weighted chips).
- `scripts/overlay_body.py` — labeled figure hero (uniform leader lines, stacking, top caption).
Run each standalone (they take a JSON spec or argv); read the file headers for signatures.
