# Vendored browser libraries

Copied from npm through jsdelivr on 2026-09-29, so the workbench and the review
page run offline, with the version pinned in git. Both are MIT licensed; each
file keeps its license header.

| File | Package | From |
|---|---|---|
| three-cad-viewer.esm.min.js | three-cad-viewer 5.0.7 (bundles three.js r184) | dist/three-cad-viewer.esm.min.js |
| three-cad-viewer.css | three-cad-viewer 5.0.7 | dist/three-cad-viewer.css |
| three.module.min.js, three.core.min.js | three 0.184.0 | build/ |
| TransformControls.js | three 0.184.0 | examples/jsm/controls/ |

The viewer bundles its own copy of three.js. Only the drag handle
(TransformControls) needs the separate one, at the same version.

To upgrade, download the same paths at the new versions, then run the
workbench tests and drag a part once in the pane.
