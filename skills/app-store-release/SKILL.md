---
name: app-store-release
description: "Ship an iOS app update end to end through the App Store Connect API and Expo EAS: create the new version, refresh outdated metadata and What's New in every locale, create new subscriptions or in-app purchases priced for all 175 countries by tier (40% off tier 2, 60% off tier 3), start the EAS cloud build with auto-submit, attach the processed build, and submit the version (plus new products) for App Review. Use when someone says they want a new version or update of their app, to ship or release an update, to add a subscription or in-app purchase, to update What's New, descriptions or keywords across locales, or to localize pricing."
---

# App Store release

One request ("new version of Brown Noise with the sleep timer, ship it") becomes a submitted update. The script
`scripts/asc.py` (call it `$A`) does every App Store Connect call; you write the words and run the steps in order.
Run `python3 $A --help` for all commands. Every write command accepts `--dry-run`.

Setup once per Mac: `~/.appstoreconnect/config.json` = `{"issuer_id": "...", "key_id": "..."}` with the key at
`~/.appstoreconnect/private_keys/AuthKey_<key_id>.p8` (App Manager role). `pip install pyjwt cryptography requests`.
EAS CLI logged in (`eas whoami`). Never print or commit key contents.

## 1. Understand the request (ask only what you cannot find)

- App: match by name with `python3 $A apps`. Project folder: `python3 $A project "<app>"`.
- Version: what the user said, else bump the live version (bug fixes: patch, features: minor). `python3 $A status "<app>"`.
- What changed: from the user, else from the project's git log since the last release commit or tag. This becomes
  What's New.
- New products: only if asked. Collect product ID, type or period, US price, display name and description per
  locale, and a review screenshot (the paywall screen from the simulator or the project's screenshots).
- Submit at the end? Yes when the user said ship, submit or release; otherwise stop after the check (step 7) and
  report what is ready.

## 2. Create the version

`python3 $A new-version "<app>" <x.y.z>`. Apple copies the previous version's text into it. If a version is already in
"Prepare for Submission", the script renames it rather than failing.

## 3. Metadata in every locale

1. `python3 $A meta-pull "<app>" --out work/meta.json`
2. Edit the JSON:
   - `whatsNew` for every locale: short, specific to this update, in that locale's language (translate yourself;
     natural phrasing, not word-for-word). Never leave last version's notes.
   - Outdated text in `description`, `promotionalText`, `keywords`: features that changed, old counts, a price or
     trial length that no longer matches, a mention of an old version. Change only what is outdated.
   - Keywords: comma-separated, no spaces, 100 characters max, no words already in the name or subtitle.
   - Name and subtitle (`app_info_locales`): only when the user asks.
3. `python3 $A meta-push "<app>" --file work/meta.json`. It checks Apple's length limits before sending anything and
   only sends fields that changed.

## 4. New subscriptions or in-app purchases (only if requested)

Write `work/products.json` in the shape of `assets/products.example.json`, then
`python3 $A --dry-run products "<app>" --file work/products.json` and read it, then run it without `--dry-run`.
It creates the group, products, localizations, availability in all countries, prices, an optional free trial,
and uploads the review screenshot.

Pricing is tiered by default (`assets/price_tiers.json`, taken from a live app): tier 1 (45 countries: US, Western
Europe, Japan, Gulf states...) pays Apple's equalized price for the US price; tier 2 (76 countries) gets 40% off and
tier 3 (54 countries) 60% off, each taken from that country's own equalized price and rounded down to the nearest
Apple price in its currency. Add `"pricing": "equalized"` to a product for plain equalized prices everywhere.
For in-app purchases the US price is the base, tier 1 follows it automatically, and tier 2/3 get manual prices.
The first tiered product downloads each country's price list (about 2 minutes) and caches it for 30 days in
`~/.appstoreconnect/price_ladders.json`; later products take seconds. To change who is in which tier, edit the
tier file. Products that already exist are skipped, so re-running
is safe. Periods: ONE_WEEK, ONE_MONTH, TWO_MONTHS, THREE_MONTHS, SIX_MONTHS, ONE_YEAR. A price must be an exact
Apple price point (the script lists the nearest ones if not). Make sure the app code uses the same product IDs
(RevenueCat or Adapty offerings included) before the build.

## 5. Build and upload with EAS

1. Set `expo.version` in the project's `app.json` (or app.config) to the new version. Build numbers come from EAS
   (`appVersionSource: remote`, `autoIncrement`), so do not touch them.
2. `eas.json` must have `submit.production.ios.ascAppId` set to the app's Apple ID, or auto-submit stops to ask.
   Add it if missing.
3. Keep caches off the internal disk: `export npm_config_cache=/Volumes/PGExtHD/npm-cache TMPDIR=/Volumes/PGExtHD/tmp`.
4. `python3 $A build "<project dir>"` (EAS cloud build with `--auto-submit --no-wait`). Note the build page URL.
5. `python3 $A build-wait "<app>" --version <x.y.z>`: run it in the background; a build plus Apple processing takes
   about 20-45 minutes. It also answers the export-compliance question (standard encryption only).

## 6. Attach the build

`python3 $A attach-build "<app>" --version <x.y.z>`

## 7. Check, then submit

`python3 $A check "<app>" --version <x.y.z>` lists anything Apple would reject at submission: no build, a locale
missing description, keywords or What's New, no screenshots, or a product missing metadata. Fix and re-check.

`python3 $A submit "<app>" --version <x.y.z>` queues every product that is "Ready to Submit" (or `--products id1,id2`,
or `none`), then submits the version for review. New products must go with a version, which this does.
A product the user did not ask about that shows "Missing Metadata" is reported, not submitted.

## 8. Report

One line per step: version created, locales updated (count), products created and prices set (countries), build
number, submitted at time. Then anything left for the user, such as a product still missing metadata.

## Rules

- Change only what the request covers. Do not edit live (Ready for Sale) metadata, prices of existing products, or
  other apps.
- Use `--dry-run` first for `products`, and for any command you have not run on this app before.
- If a call fails, the script prints Apple's error. Fix the cause and re-run the step; steps are safe to repeat.
- Screenshots are a separate job (the `appstore-screenshot-captioning` skill). A new locale needs screenshots before
  submission; `check` flags missing en-US ones.
