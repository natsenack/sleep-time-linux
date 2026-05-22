#!/usr/bin/env bash
set -euo pipefail

echo "1/ Validating metadata.json"
python3 -m json.tool metadata.json >/dev/null
python3 - <<'PY'
import json,sys
with open('metadata.json') as f:
    m=json.load(f)
for k in ('uuid','name','description','shell-version','url'):
    if k not in m:
        print('metadata.json missing key',k); sys.exit(2)
if not isinstance(m['shell-version'], list) or len(m['shell-version'])==0:
    print('metadata.json.shell-version must be non-empty list'); sys.exit(2)
PY
echo "OK metadata.json"

echo "2/ Checking forbidden imports in extension.js"
if grep -nE "gi://(Gtk|Gdk|Adw)|\b(Gtk|Gdk|Adw)\b" extension.js; then
    echo "Forbidden import found in extension.js"; exit 2
fi
echo "OK imports"

echo "3/ Shellcheck on scripts (warnings allowed)"
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck build-extension.sh build.sh launch.sh || true
    echo "OK shellcheck"
else
    echo "shellcheck not installed; skipping shellcheck (CI will run it)."
fi

echo "4/ ESLint on extension.js"
if command -v npx >/dev/null 2>&1; then
    npx eslint extension.js --max-warnings=0
elif command -v npm >/dev/null 2>&1; then
    npm install --no-audit --no-fund --no-save eslint || true
    if command -v npx >/dev/null 2>&1; then
        npx eslint extension.js --max-warnings=0 || true
    else
        echo "npx still not available after npm install; skipping ESLint locally"
    fi
else
    echo "npm/npx not available; skipping ESLint (CI will run it)."
fi

echo "5/ Build extension and validate zip"
bash build-extension.sh
ZIP=build/power-timer@natsenack.github.io.zip
if [ ! -f "$ZIP" ]; then echo "ZIP missing"; exit 2; fi
unzip -l "$ZIP"
if ! unzip -l "$ZIP" | awk '{print $4}' | grep -E '^extension.js$' >/dev/null; then echo "extension.js missing in zip"; exit 2; fi
if ! unzip -l "$ZIP" | awk '{print $4}' | grep -E '^metadata.json$' >/dev/null; then echo "metadata.json missing in zip"; exit 2; fi
if ! unzip -l "$ZIP" | awk '{print $4}' | grep -E '^LICENSE$' >/dev/null; then echo "LICENSE missing in zip"; exit 2; fi
if unzip -l "$ZIP" | awk '{print $4}' | grep -E '\\.(py|pyc|so|exe)$' >/dev/null; then echo "Prohibited file types in zip"; exit 2; fi
echo "ZIP validated"

echo "All checks passed"
