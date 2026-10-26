# Agent: Spelling and proofreading

Goal: real spelling errors on any sheet, including sheet titles, notes, table titles, legends and pasted tables.

1. `python3 $S/spell_candidates.py <index> <work>/spell_candidates.json`
   (add `--allow <file>` with project words if the user gave any).
2. Judge each candidate in `unknown`, `repeated` and `variants`. Report only real errors:
   - misspellings (PERMAMENT, GUTTTER, RECIEVE), repeated words, typos in titles and notes;
   - the same term spelled two ways in the set (`variants`): report the wrong form and where it is;
   - inconsistent spelling of proper names (streets, the project name) across sheets.
   Not errors: abbreviations, MDOT/AASHTO terms, pay-item wording, units, street and place names used consistently,
   intentional all-caps labels, words broken across two lines on purpose.
3. Candidates from OCR (`source: ocr`, especially with `ocr_only: true` or low `conf`) may be OCR misreads. Look at
   the plan before reporting: `render <pdf> <index> <page> --clip <rect padded by ~20 pt> --dpi 300`. Report it only
   if the printed text is wrong. Pasted table images are a common place for real typos, so do check them.
4. The candidate list cannot see text drawn as linework (pages flagged LOW_TEXT_DENSITY_POSSIBLE_SHX_TEXT). Read the
   titles and notes of those pages visually.
5. Unfinished placeholders are high severity: "XX:XX PM", "XXX", "XX MPH", "TBD", "???", "STA. XX+XX". Search for
   them (`search <index> "XX"`, `"TBD"`) as well as using the candidate list. Not placeholders: standard sign
   legends in sign charts ("ROAD WORK NEXT XX MILES", "XX MPH", "XXX FEET" are MUTCD sign texts), and "?' OF RCP12"
   style labels on existing utilities (unknown survey lengths); report those only as low "confirm".
6. Also skim each sheet's title (from `sheets`) and each chunk's notes for errors a dictionary passes: wrong word
   ("PAVEMENT MAKING"), missing letters forming another word, wrong units.
7. Write `<work>/findings/spelling.json` (format: `references/findings_schema.md`), ids SPL-001 onward. Use the
   candidate's `rect` in `locate` (it is already in PDF points). Severity: medium for titles, notes and pay-item
   text; low for minor typos elsewhere. Evidence = the word in its printed line; suggested_fix = the corrected text.
Reply with: count of errors, and how many OCR candidates you dismissed as misreads.
