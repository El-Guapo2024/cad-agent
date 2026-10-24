"""The Attachment panel's own suggestMapModes (ui/src/attachsuggest.ts) answers as FreeCAD's does.

The page lists the modes for references it can type itself (the origin's features, a datum) before the server's attacher
answers; that port is bundled for Node as tests/golden/attach/suggest.mjs and run here on the 220 reference sets of
tests/golden/attach/engine.json (FreeCAD 26.3's Part.AttachEngine.suggestModes()). After a change to attachsuggest.ts or
attachmodes.ts, bundle it again: `cd ui && npx esbuild src/attachsuggest.ts --bundle --format=esm
--outfile=../tests/golden/attach/suggest.mjs` (with the banner the file has).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden" / "attach"
NODE = shutil.which("node")

SCRIPT = """
import { readFileSync } from 'fs'
const { suggest } = await import(process.argv[2])
const data = JSON.parse(readFileSync(process.argv[3], 'utf8'))
const out = data.suggestions.map((s) => suggest(s.engine, s.types))
console.log(JSON.stringify(out))
"""


def test_the_bundle_holds_the_sources():
    text = (GOLDEN / "suggest.mjs").read_text()
    modes = (REPO / "ui" / "src" / "attachmodes.ts").read_text()
    for name in ("ENGINE_MODES", "MODE_REFS", "suggest", "isShapeOfType"):
        assert name in text
    first = modes.split('"ObjectXY": ', 1)[1][:40]       # the generated table is the one bundled
    assert first in text.replace(" ", "") or first.replace(" ", "") in text.replace(" ", "")


@pytest.mark.skipif(NODE is None, reason="needs Node")
def test_the_page_suggests_as_freecad(tmp_path):
    script = tmp_path / "run.mjs"
    script.write_text(SCRIPT)
    r = subprocess.run([NODE, str(script), str(GOLDEN / "suggest.mjs"), str(GOLDEN / "engine.json")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    want = json.loads((GOLDEN / "engine.json").read_text())["suggestions"]
    assert len(got) == len(want) == 220
    for g, w in zip(got, want):
        assert (g["message"], g["best"], g["all"], g["reachable"], sorted(g["hints"]), g["types"]) == \
            (w["message"], w["best"], w["all"], w["reachable"], w["hints"], w["types"]), w["refs"]
