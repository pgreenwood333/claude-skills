# Claude skills by Peyton Greenwood

Skills I built for Claude (Claude Code and Cowork). Each folder has a `SKILL.md` plus any scripts and references it uses.
This repo updates automatically whenever I change a published skill.

| Skill | What it does |
|---|---|
| [app-store-release](skills/app-store-release) | Ship an iOS app update end to end through the App Store Connect API and Expo EAS: create the new version, refresh outdated metadata and What's New in every locale, create new subscriptions or in-app purchases priced for  |
| [appstore-screenshot-captioning](skills/appstore-screenshot-captioning) | Make App Store / Google Play screenshots — from raw iPhone captures to finished, localized, keyword-rich marketing slides (flat brand-colored background, two-tone keyword titles, device frame, enlarged "3D pop-out" UI ca |
| [dot-extract-standard-drawings](skills/dot-extract-standard-drawings) | Extracts the roadway standard drawings called out in a DOT plan set's Detailed Index into a standalone \"Standards\" companion PDF, pulled from the current DOT standards master in OneDrive and named from the plan set's o |
| [dot-opcc](skills/dot-opcc) | Build a state DOT Opinion of Probable Construction Cost (OPCC, engineer's estimate) Excel workbook from a plan set's Summary of Quantities, pricing every pay item from DOT's published Item Bid Prices (low / average / hig |
| [dot-plan-set-qaqc](skills/dot-plan-set-qaqc) | QA/QC review of a DOT roadway plan set PDF. Use when someone wants to QC, QA/QC, check or review plans or a plan set. Indexes and chunks the whole set (text layer + OCR of pasted tables, hybrid keyword/vector search), as |
| [dot-quantity-book](skills/dot-quantity-book) | Build a DOT quantity calculations binder (quantity book) from a plan set's title sheet and the engineer's quantity calculation files (Excel .xlsx/.xlsm, Word, PDF, text): a title sheet + table of contents Word document a |
| [dot-xs-note-placement](skills/dot-xs-note-placement) | Add missing drainage and driveway notes to DOT OpenRoads Designer cross sections. Pulls the exact profile notes from the plan-profile (WK) sheets with the dot-plan-set-qaqc note match, keeps the ones that belong on the c |
| [expo-device-testing](skills/expo-device-testing) | > |
| [profile-notes-extractor](skills/profile-notes-extractor) | Pull the stacked notes in the profile view of DOT/roadway plan-profile sheets (drainage structure callouts like 337 B / STA. 337+36.00 / SS-2 REQ'D LT / TOP = / INV. =, drive, box culvert and bridge notes) into a Word do |

## Use

These are published so people can see how they work. Copyright (c) 2026 Peyton Greenwood.
All rights reserved: no permission is granted to copy, modify or redistribute them. See [LICENSE](LICENSE).
