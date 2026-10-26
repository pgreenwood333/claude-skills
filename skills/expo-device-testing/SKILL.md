---
name: expo-device-testing
description: >
  Peyton's standard workflow for testing an Expo / React Native app on his physical
  iPhone — a dev build (EAS) loaded over a Cloudflare tunnel via a dev-client QR — plus
  the specific gotchas that have bitten before. Use this whenever setting up or fixing
  on-device testing: running the app on the phone, dev/development builds, Cloudflare
  tunnels, `tunnel.sh`, Expo Go vs dev client, or a QR code that won't open ("No usable
  data found"). Also encodes how Peyton wants terminal commands written.
---

# Expo on-device testing (Peyton's setup)

Peyton builds multiple Expo/React Native apps and tests them on a **physical iPhone** using
a **development build** loaded over a **Cloudflare tunnel**, scanning a **dev-client QR with
the iOS Camera**. This is the proven flow. Match it exactly; don't invent alternatives.

## The two-step model
1. **Dev build (native)** — only rebuild when NATIVE code/config changes (new native module,
   SDK bump, app.json scheme/plugins, bundle id). Cloud build via EAS, ~15–20 min.
2. **Tunnel dev server (JS)** — for any JS/TS change. Hot-reloads instantly, no rebuild.

## Commands (always `cd` into the project first — see "Terminal commands" below)

Build the dev app (one-time / after native changes):
```bash
cd <PROJECT_DIR>
eas login                       # or npx eas-cli
eas device:create               # register the iPhone (first time)
eas build --profile development --platform ios
```
Install the finished build on the phone via the EAS QR/link.

Run it (every session):
```bash
cd <PROJECT_DIR> && bash tunnel.sh
```
`tunnel.sh` starts a Cloudflare quick tunnel to Metro (port 8081), grabs the
`https://<x>.trycloudflare.com` URL, and runs `EXPO_PACKAGER_PROXY_URL="$URL" npx expo start`.
Because `expo-dev-client` is installed, `expo start` prints a **dev-client QR**. Scan it with
the **iOS Camera** → "Open in <App>".

A working `tunnel.sh` lives in each project (copy the pattern from Free Up Storage). It must:
free port 8081, launch `cloudflared tunnel --url http://localhost:8081`, parse the
trycloudflare URL from its log, then `EXPO_PACKAGER_PROXY_URL="$URL" npx expo start --port 8081`.

## GOTCHAS — check these FIRST when device testing breaks

1. **iOS Camera says "No usable data found" when scanning the QR.**
   The QR encodes a URL scheme no installed app claims. Diagnose the exact scheme:
   ```bash
   cd <PROJECT_DIR> && npx expo config --type introspect --json 2>/dev/null \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['ios']['infoPlist'].get('CFBundleURLTypes'))"
   ```
   The dev-client deep link is `exp+<slug>://expo-development-client/?url=...` (slug from
   app.json, hyphenated). It must be a scheme the INSTALLED build registers.
   - **#1 cause seen: a STALE local `ios/` (or `android/`) folder** from an old `expo prebuild`
     / `expo run:ios` / placeholder bundle id. `expo start` reads the scheme from that native
     folder, not app.json, so the QR gets the OLD scheme (e.g. an old bundle id) that the
     freshly EAS-built app doesn't register. **Fix: `rm -rf ios android`** so expo derives the
     scheme from app.json again. (EAS builds in the cloud, so this doesn't affect the build.)
   - Verify after: run `bash tunnel.sh` and read the **`› Metro:`** line — it should show the
     app's real scheme, not a stale one.

2. **SDK version changes the QR format.** Newer Expo SDKs print an iOS-Camera-openable
   dev-client QR; older ones print an `exp://` QR the Camera can't open. If a project is on an
   old SDK and the Camera won't scan, aligning it to the same SDK as the other working apps is
   often the real fix (but confirm the scheme first — see #1 — before a big SDK upgrade).

3. **`expo-dev-client` must be installed** or `expo start` serves an Expo-Go QR, not a
   dev-client one. `npx expo install expo-dev-client`.

4. **Full internal disk breaks builds/installs** (npm ENOSPC, CocoaPods "No space left on
   device", pod clone failures). Peyton's internal disk runs near-full and the project lives on
   an external drive. Route heavy caches/temp to the drive with space:
   ```bash
   export npm_config_cache=<EXTERNAL>/npm-cache TMPDIR=<EXTERNAL>/tmp
   ```
   Install big CLIs (wrangler, eas-cli, cloudflared) onto the external drive, not via bare
   `npx` (which downloads to the full internal `~/.npm`). Prefer **EAS cloud builds** over local
   `expo run:ios` when the disk is full.

5. **`cloudflared`** is installed at `/usr/local/bin/cloudflared` (on PATH). Quick-tunnel URLs
   change every restart — re-export the new URL / regenerate any QR.

6. **Expo Go ≠ dev client.** Native modules (RevenueCat, custom native) only work in the dev
   build, not Expo Go. Don't fall back to Expo Go to "make the QR work."

## Terminal commands — how Peyton wants them written
Whenever giving Peyton a command to run in his terminal:
- **Always include the full folder location** — start with `cd <absolute project path>` (or a
  full explicit path in the command). Never assume he's already in the right directory.
- Give the **complete, copy-pasteable** command with all needed `export`s/flags in the same
  block, not fragments he has to assemble.
- One logical action per fenced `bash` block.
- If it depends on state (a tunnel URL, a running server), say so explicitly.
