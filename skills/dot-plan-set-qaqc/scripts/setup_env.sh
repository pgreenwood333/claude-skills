#!/usr/bin/env bash
# Set up (once) and check the Python environment the QA/QC scripts run in. Prints the two lines to eval:
#   eval "$(bash $S/setup_env.sh)"     ->  sets PY (the python to run every script with) and FASTEMBED_CACHE
#
# Why a separate Python 3.12 environment: OCR (rapidocr) and the vector search model (fastembed) both need
# onnxruntime, which has no build for Python 3.13+ yet. Without them the index has no OCR of pasted table images
# and no vector search, so the run is less accurate. This is the supported setup, not a fallback.
# Location: $QAQC_VENV if set; else /Volumes/PGExtHD/venvs/qaqc312 when that drive is mounted; else ~/.qaqc-venv.
set -euo pipefail

if [ -n "${QAQC_VENV:-}" ]; then VENV="$QAQC_VENV"
elif [ -d /Volumes/PGExtHD ]; then VENV=/Volumes/PGExtHD/venvs/qaqc312
else VENV="$HOME/.qaqc-venv"; fi
BASE="$(dirname "$VENV")"
CACHE="${FASTEMBED_CACHE:-$BASE/.fastembed-cache}"
PKGS=(pymupdf==1.28.2 pdfplumber==0.11.10 openpyxl==3.1.5 pyspellchecker==0.9.1 numpy==2.5.4
      rapidocr==3.10.0 onnxruntime==1.23.2 fastembed==0.9.1)

check() { "$VENV/bin/python" -c "import pymupdf, pdfplumber, openpyxl, spellchecker, numpy, rapidocr, onnxruntime, fastembed" 2>/dev/null; }

if ! check; then
  echo "setting up $VENV (Python 3.12, one time)..." >&2
  command -v uv >/dev/null || { echo "ERROR: uv is not installed (https://docs.astral.sh/uv/). Install it, then re-run." >&2; exit 1; }
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$BASE/.uv-cache}"
  [ -x "$VENV/bin/python" ] || uv venv --python 3.12 "$VENV" >&2
  VIRTUAL_ENV="$VENV" uv pip install -q "${PKGS[@]}" >&2
  check || { echo "ERROR: packages installed but do not import in $VENV; do not run the QA/QC without OCR." >&2; exit 1; }
fi
mkdir -p "$CACHE"
echo "PY=$VENV/bin/python"
echo "export FASTEMBED_CACHE=$CACHE"
