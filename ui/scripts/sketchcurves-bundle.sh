#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Bundles ui/src/sketchbspline.ts and sketchops.ts (the curve tools) and what they import into tests/golden/sketchcurves/engine.mjs,
# which tests/test_sketchcurves.py runs under node against FreeCAD's answers. Run it after changing those sources (it
# needs only ui/node_modules: `npm ci` in ui/).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ui="$(dirname "$here")"
root="$(dirname "$ui")"
out="$root/tests/golden/sketchcurves/engine.mjs"
# from the repository's root, as tests/test_sketchcurves.py bundles it to compare (the regions name paths from there)
cd "$root"
"$ui/node_modules/.bin/rolldown" ui/scripts/sketchcurves-entry.ts --format esm --file "$out" --platform neutral
echo "wrote $out"
