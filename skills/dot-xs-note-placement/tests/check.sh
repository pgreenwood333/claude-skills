#!/bin/bash
# Regenerate the sample job's macro and compare it with the known-good copy.
#   bash tests/check.sh            compare (exit 1 on any difference)
#   bash tests/check.sh --update   accept the current output as the new known-good copy
set -e
T="$(cd "$(dirname "$0")" && pwd)"; W="$(mktemp -d)"
cp "$T/fixture/"*.json "$W/"
python3 "$T/../scripts/make_macro.py" "$W" >/dev/null
for f in PlaceXSNotes.bas xsnotes_batch_DRYRUN.txt xsnotes_batch_PLACE.txt xsnotes_batch_REMOVE.txt HOW_TO_RUN.md; do
  if [ "$1" = "--update" ]; then cp "$W/$f" "$T/expected/$f"
  elif ! cmp -s "$W/$f" "$T/expected/$f"; then echo "DIFFERENT: $f"; diff <(tr -d '\r' < "$T/expected/$f") <(tr -d '\r' < "$W/$f") | head -40; rm -rf "$W"; exit 1; fi
done
rm -rf "$W"
[ "$1" = "--update" ] && echo "known-good copy updated" || echo "OK: generator output matches the known-good copy"
