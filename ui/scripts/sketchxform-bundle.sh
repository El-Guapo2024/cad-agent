#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Bundles ui/src/sketchxform.ts (mirror, copy, clone, move, array, remove axes alignment) and what it imports into
# tests/golden/sketchxform/engine.mjs, which tests/test_sketchxform.py runs under node against FreeCAD's answers. Run it
# after changing those sources (it needs only ui/node_modules: `npm ci` in ui/).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ui="$(dirname "$here")"
root="$(dirname "$ui")"
out="$root/tests/golden/sketchxform/engine.mjs"
# from the repository's root, as tests/test_sketchxform.py bundles it to compare (the regions name paths from there)
cd "$root"
"$ui/node_modules/.bin/rolldown" ui/scripts/sketchxform-entry.ts --format esm --file "$out" --platform neutral
echo "wrote $out"
