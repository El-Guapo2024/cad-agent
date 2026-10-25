# DeepSeek lane log (ds/handoff-1025)

Standing in for the Claude lane, from `ui/HANDOFF.md`'s "Next" list. Items are taken in order; each one has the
failing test it started from, the commit, the checks run, and what was unsure.

## 1. Assembly joints — skipped, needs Juan

The handoff's "Next" starts with "Assembly joints (Assembly workbench, its solver)". FreeCAD's Assembly workbench
solves joints with the Ondsel solver (`src/Mod/Assembly`, vendored from Ondsel), which would be another vendored
solver next to PlaneGCS: a licensing/ownership call (the vendoring itself, the version, the lane that owns it) and
a sizeable piece of work on its own. It is also a new part-file vocabulary (assemblies, joints) beyond the editing
plan's step 5. **Question for Juan:** whether and where to vendor the Ondsel solver, and which lane owns the
Assembly workbench. Moved on to the next item, ShapeBinder.

## 2. ShapeBinder (PARITY.md leftover) — done

### What was done

- `cad_agent/feature_binder.py`: `ShapeBinder(name, support=[...], trace_support=False)`, the part file's
  `PartDesign::ShapeBinder`. Support is FreeCAD's `PropertyLinkSubList` in the attachment vocabulary
  (`("Pad", "Face6")`, a list for several elements, `""` for the whole object, an Origin feature by name).
  Shape building is `ShapeBinder::getFilteredReferences` + `buildShapeFromReferences`: first Part::Feature wins,
  its whole shape when its first entry has no element, else a compound of its elements; with no Part::Feature, the
  first Origin feature (infinite face/line/vertex). A whole sketch is `SketchObject::buildShape` (a Wire).
- `feature_attach.Context.add_binder`: kind `"binder"`, shape and Placement (the shape's, as `ShapeBinder::execute`
  sets it). A binder is not a solid: `feature.evaluate` adds it and the Body's solid/Tip are unchanged.
- References to a binder: a later sketch attaches to `("Binder", "Face1")`; a Pad/Pocket UpToFace or UpToShape can
  name it (`_ref_face`/`_up_to_shape` fall back to the Context for a Body object that is not a solid); another
  binder can copy it.
- `feature_edit`: `ShapeBinder` is a `KwFeature`, so add/set/rename/move/delete and `cad feature ...` come with it;
  the default Tip skips binders (and datums), as `Body::insertObject` leaves the Tip.
- `to_freecad`: the Support groups (one entry per object, as the PropertyLinkSubList's value is read back),
  TraceSupport; a recompute before TraceSupport is set, because FreeCAD leaves the whole Body null if the support
  was never computed (measured).
- Goldens: `tests/golden/binder/cases.py` (16 bodies), `make.py` recorded `freecad.json` from freecadcmd 26.3
  (3160daf1e2b6); `tests/test_feature_binder.py` holds the binder's shape/Placement/Support, the Body and Tip, the
  part-file round trip through `feature_edit`, the refusal of a reference to a later feature, and the support
  normalisation to FreeCAD's answers.

### Commit

`02c977b` PartDesign: the ShapeBinder, FreeCAD's copy of another object's geometry

### Tests run

- `pytest tests/test_feature_binder.py -q` — 36 passed.
- `pytest tests/affected.py origin/main -q` (the suite `tests/affected.py origin/main --list` picks for the changed
  modules: attacher, feature, feature_attach, feature_edit, curves, dressups, part, pick, revolve, sweep,
  transform, featurecmd, sketcher panels) — all passed (exit 0; a few skipped). The native PlaneGCS library had to
  be built first in this worktree (`PLANEGCS_TOOLCHAIN=~/work/research/toolchain ui/planegcs/build.sh native`):
  the affected suite's external-geometry sketches re-solve, and without it they fail with PlaneGCSNotBuilt.
- `tests/golden/binder/make.py` was run under `$FREECAD/freecadcmd` from the repository root to record the answers.

### Unsure / questions

- **Cross-Body support.** FreeCAD's ShapeBinder can copy geometry from another Body (that is a large part of what
  it is for). A part file here is one Body in one Python module and its references are names in FEATURES, so a
  cross-part reference has no vocabulary yet. The backend and, so far, the UI accept references to this part's own
  objects (features, sketches, datums, the Origin, other binders). If cross-Body binders are wanted, that is a
  design decision (how a part file names another part's feature, and how `Body()` sees it). Written here per the
  rules and left out of the golden set.
- `TraceSupport` inside one Body is a no-op (the source and target container are the same Body); the file keeps the
  flag, and `tests/golden/binder` case "trace" records FreeCAD's answer. Nothing else was measured for it.
- FreeCAD's task panel refuses the Origin features as a *pick* (they are not Part::Feature) but displays a Support
  that already holds one; the backend accepts them (cases `origin_plane`, `origin_axes`).

### UI, in the page — commit `8ef1b49`

What was done:

- `ui/src/pd_binder.tsx` (new): the whole panel, modelled on FreeCAD's `TaskShapeBinder.cpp`/`.ui` and
  `ViewProviderShapeBinder.cpp` (sources cited in the header, added to `ui/NOTICE`).
  - The command (`PartDesign_ShapeBinder`, menu in `ui/src/partdesign.tsx`, `ui/src/cmdreg.ts`): with one ShapeBinder
    selected, its edit panel; otherwise a new binder in the active Body whose Support is the selection (the active
    Body is dropped from it, as `CmdPartDesignShapeBinder::activated`'s `support.removeValue(pcActiveBody)`), name
    `ShapeBinder`, or `ShapeBinder001`… Nothing is written until OK; Cancel writes nothing.
  - The panel ("Shape Binder Parameters"): Object, Add Geometry and Remove Geometry are one-shot pick modes, as the
    C++ panel's `onButtonToggled`/`referenceSelected`/`onSelectionChanged` — a click in the 3D view or the tree applies
    the pick, then the mode ends whether it was accepted or refused (a refusal says why in the status line). Object
    replaces the support with the picked whole object; Add refuses duplicates and an empty element is the whole object
    (the first reference replaces the whole-object entry); Remove needs the element present, and removing the last one
    stores `(object, "")` — the whole object — as `PropertyLinkSubList::setValue` does. The reference list selects a
    row, Delete/Backspace and its context menu's Remove delete one element (last one → whole object). Typed text in the
    Object line is only used on OK when Support is empty (`TaskDlgShapeBinder::accept`).
  - The view, as `ViewProviderShapeBinder`: the support object is shown (`TaskShapeBinder::updateUI`'s `setVisible`),
    its references magenta (`highlightReferences`), the binder previewed golden 60 % transparent with orange lines
    (`cad feature shape` on the panel's ops, 150 ms debounced, seq-guarded, nothing written); a build error shows in
    the panel and OK keeps it open with FreeCAD's "Input Error" box. Every shown binder of every Body is drawn outside
    the server scene (the scene draws the Body at its Tip; a binder is not one of its solids), in the Body's frame,
    selectable (a click selects its tree row), the selected one in the selection colour, hidden with its Body.
  - A new binder goes where `Body::addObject` puts it: before the first solid feature after the Tip
    (`getNextSolidFeature`), at the end when there is none.
  - The tree: row and icon, "Edit Shape Binder" context menu, double-click opens the edit panel, visibility follows
    the Body (the datum rule). The Data tab (`BinderProps`): Base — Label, Support (read-only, `Pad:Face6`), Trace
    Support; Placement is hidden as `ViewProviderShapeBinder::hide()` does.
- Wiring so a binder is not a solid: `isSolid()` (`ui/src/partdesign.tsx`) now excludes binders as well as sketches and
  datums, and the places that used to test `!== SKETCH` by hand use it (`pd_pick.tsx` `baseOf`, `pd_dressup.tsx`
  `solidAtTip`, the subtractive guard in `pd_revolve.tsx`/`pd_sweep.tsx`, `pd_transform.tsx` `lastSolid`/`picked`,
  `pd_attach.tsx` `tipFeature`). `baseMesh` is exported from `pd_pick.tsx`; `refsOfSelection(part, wholeBody = true)`
  (`pd_attach.tsx`) lets the binder command take only elements and tree rows; `attached.ts` has `SHAPE_BINDER`/
  `isBinder`, `store.ts` the `'shapeBinder'` task kind, `panels.tsx` the dispatch, `cmdreg.ts` the command.
- `ui/scripts/editcheck.mjs`: a "shape binder" section (the edit section's scratch Body): command from the Pad
  selection, panel title and buttons, a 3D pick of `Pad.Face6` in Add Geometry, OK → `[["Pad","Face6"]]`, Tip stays
  `Hole`, undo name "Create Shape Binder", tree row, Data tab Support `Pad:Face6` and Trace Support, the context
  menu, double-click to edit, Remove Geometry → `[["Pad",""]]`, undo "Edit ShapeBinder", the command on a selected
  binder opening its panel, Cancel.
- `ui/PARITY.md`: a `PartDesign_ShapeBinder` row (done, with the knowing differences listed); the SubShapeBinder line
  now points at it; the editcheck count line updated. Bundle rebuilt from the new sources
  (`cad_agent/workbench/next/`, NOTICE included).

Tests run:

- `npx tsc -b --noEmit` — clean; `npm run build` — built, bundle committed.
- `pytest tests/test_feature_binder.py -q` — 38 passed (the 36 above was before `223cc64`, whose 56 added lines are
  two more tests).
- `pytest tests/test_licenses.py -q` — 242 passed (the new named files are in `ui/NOTICE`, and the bundle's copy
  matches).
- `pytest tests/affected.py origin/main -q` — all passed (exit 0).
- `ui/scripts/editcheck.mjs` — 79 ok, 0 failing, 12 known differences (whole run, including the new section).
- `ui/scripts/wirecheck.mjs --only=tree,properties` (the background run also did `context`) — 86 controls: WORKS 58,
  N/A 28, NO-OP 0, ERROR 0, WRONG 0.

Unsure / questions:

- **A binder hides with its Body.** FreeCAD's `ViewProviderShapeBinder` is a Body object, so hiding the Body hides it;
  the page's Body toggle hides sketcher objects with the Body and datums by their own eye, and the binder follows the
  Body. Not measured against FreeCAD's tree, only read from the sources.
- **Name or Label in the panel?** FreeCAD's Object line and tree show the Label (here name === Label until a rename is
  offered); the Data tab's Support text uses names (`Pad:Face6`). If labels diverge, the vocabulary needs deciding.
- **Magenta after the mode ends.** FreeCAD colours references when it enters edit/selection mode; whether they stay
  coloured after Add/Remove is checked off was not measured. Here the highlight follows the armed mode (Add/Remove
  down), not the support forever.
- **The selection vocabulary is the Body's.** A Body pick in the 3D view with no element is dropped (the active Body
  is dropped from Support), while selecting the Body's Tip tree row binds the whole Tip solid — that is
  `refsOfSelection`'s reading of the tree, and matches FreeCAD's feature selection, but the 3D-body case was not
  measured. A sketch or another binder only comes in whole from the tree; their elements are not pickable in the panel.
- **Origin features**: the panel refuses them as a pick (as FreeCAD's does — they are not Part::Feature) but displays a
  Support that already holds one. The backend still accepts them (goldens `origin_plane`, `origin_axes`).
- A support object is shown as its own mesh only when the server can mesh it (`cad feature shape`: a solid, a sketch,
  a binder); a datum's plane is infinite and an Origin feature is drawn by the Origin, so those show only the binder.
- `TraceSupport` stays a no-op inside one Body (above), and cross-Body support has no vocabulary yet (above).

## 3. Part's 3D picking and attachment (PARITY.md leftover) — done

### What was done

Tests written with the work (they fail without it): `tests/golden/part/cases_attach.py`, 12 documents attaching Part
objects (`attach_flat_face`, `attach_flip`, `attach_side`, `attach_object_xy`, `attach_chain`, `attach_deactivated`,
`attach_cut`, `attach_polygon`, `attach_circle_edge`, `attach_fuse_placement`, `attach_body_face`,
`attach_origin_plane`) with their answers recorded from FreeCAD 26.3 by `tests/golden/part/make.py attach` into
`tests/golden/part/freecad_attach.json`, together with AttachExtension's property values on a fresh object of every
Part type; `tests/test_feature_part.py` now checks each case's Placement against FreeCAD's and each type's
AttachExtension defaults; `tests/test_feature_edit_attach.py::test_cad_feature_attach_and_list_a_part_object` drives
`cad feature attach --before` and `cad feature list` on a part of Part objects; and
`tests/test_feature_edit_part.py::test_an_attachment_follows_a_rename_and_holds_a_delete` holds the support to the
edit rules. `ui/scripts/partcheck.mjs`'s attach section (17 checks) failed first: Part's Attachment entry was greyed.

- Backend, `cad_agent/feature_part.py`: `PartObject` holds AttachExtension — `COMMON`'s attachment_support, map_mode,
  attachment_offset, map_reversed and map_path_parameter, `engine = "3D"` (AttachEngine3D), `ATTACH` and `REFS`
  (a rename follows the support, a delete of a used object is refused, a move before the object it links is refused),
  `normalize`/`support_list` for the references, and `fc_attach` in `to_freecad`: AttachmentSupport, MapMode,
  AttachmentOffset, MapReversed and MapPathParameter, adding `Part::AttachExtensionPython` when the type lacks the
  extension (as `TaskAttachmentEditor.__init__` does). `Context.attach` gives an object the Placement its mode makes
  (`attacher.attach`), else its `placement=` when Deactivated or unsupported; `Context.resolve`/`ref` see the objects
  already built and the Body's attach Context.
- Backend, `cad_agent/feature_attach.py`: `_load` returns OBJECTS as well as FEATURES (a part of Part objects, of a
  Body, or both); `body_info`/`_part_info` place every object (and the Body) for `cad feature list`; `needs_body` is
  true when a Part object is attached; `attach_query` uses the Part object's own engine and resolves among the objects
  before it. `feature_part_prim.py`'s validation skips the AttachExtension keys.
- The page, `ui/src/pd_attach.tsx`: the Attachment panel on a Part object (it is found in `doc.objects`, engine 3D),
  its own shape previewed with the attachment taken off and moved to the answer's Placement (as TaskAttachmentEditor
  moves the object itself), the scene's joined Body giving way while it is open, faces and edges picked through
  `part_pick.tsx`, a click on the object itself ignored ("Ignored. Can't attach object to itself!"). The starting active
  button follows FreeCAD's two editors: TaskAttachmentEditor (references exist: none; none: the first, auto_next) and
  TaskAttacher with take_selection (a new datum or sketch starts the button after the selection's references, as
  `handleInitialSelection` + `addToReference` leave it).
- `ui/src/part_pick.tsx` (new): `cad feature shape`'s meshes with FreeCAD's FaceN/EdgeN names as view helpers, the
  document's shown objects and the Body's Tip from their own shapes, an `allow`/`onPick` per panel, a target drawn at a
  Placement; `parsePartPick` turns "@Base.Face6" back into the part file's reference.
- `ui/src/part_tasks.tsx`: Fillet and Chamfer pick edges over the chosen shape (a click checks/unchecks EdgeN),
  Thickness its faces tinted over the shape while armed, Project on surface its projection surface and the projected
  faces, wires or edges (the pick ends the arming).
- `ui/src/part_wb.tsx`: Part's Attachment entry (exactly one selected Part object, not a sketch) opens the panel; the
  Data tab shows the attached Placement, Map Mode and Attachment Support ("Base:Face6") and "Engine 3D".
  `ui/src/attached.ts` marks `doc.objects` with their attachments.
- `ui/NOTICE`: `Mod/Part/AttachmentEditor/Commands.py` and `TaskAttachmentEditor.py` for `src/pd_attach.tsx`, and
  `TaskAttacher.cpp`/`ViewProviderAttachExtension.cpp` are cited there too. `ui/PARITY.md`: the Part workbench's
  Attachment, its knowing differences, the four picking rows and the `part_pick.tsx` paragraph, and partcheck's count
  (406 checks pass, 21 known). Bundle rebuilt (`cad_agent/workbench/next/`, NOTICE included).

### Commit

`254f466` Part: the Attachment panel on a Part object, and picks in the 3D view

### Tests run

- `pytest` (whole suite) — 7,062 passed, 23 skipped (0:11:50).
- `pytest tests/test_licenses.py -q` — 244 passed (the new citations are in ui/NOTICE; the bundle's copy matches).
- `ui/scripts/attachcheck.mjs` — 89 ok, 0 failing, 0 known differences.
- `ui/scripts/partcheck.mjs` — 406 ok, 0 FAIL, 21 known (full run; the attach section is 17 of the 406).
- `npx tsc -b --noEmit` — clean; `npm run build` — built, bundle committed.

### Unsure / questions

- **Import order.** Importing `cad_agent.feature_attach` before `cad_agent.feature` raises a circular ImportError
  (`DatumLine`): feature_attach.py imports feature at module scope and feature.py imports feature_attach. It is
  pre-existing on origin/main (the same lines); the tests import `cad_agent.feature` first. Nothing changed here.
- **The Attachment menu's gate.** FreeCAD's Part_EditAttachment IsActive is "exactly one selected object with a
  Placement", which a Body's features have too; Part's menu here enables it for exactly one selected Part object that
  is not a sketch, and a Body feature's attachment stays with PartDesign's panel. Written in PARITY.md.
- **Vertices.** The 3D picking draws faces and edges only, so a mode that needs a vertex cannot be picked here. (FreeCAD
  reaches such a mode by typing the reference into a line; the page's lines accept only being cleared, not a typed
  reference.) Noted in PARITY.md; no test covers it.
- **A forward reference** is refused only when the attacher answers ("LinkBroken", "... no object 'Box' before it"),
  because a part file is in order. Same PARITY bullet.
- **Test paths.** Running `tests/test_feature_part.py` and `tests/test_feature_edit_attach.py` in one pytest command
  makes the latter fail to import: test_feature_part puts `tests/golden/part` on `sys.path`, and attach's `bodies.py`
  imports `cases`, which then resolves to part/cases.py (no `base_pad`). The full suite passes because
  test_feature_attach imports `cases` first. Pre-existing ordering fragility, not changed here.

## 4. Part Scale/Face/Ruled/Reverse (PARITY.md leftover) — done

### What was done

Tests written with the work (they fail without it): `tests/golden/part/cases_misc.py` (23 documents: Reverse on a Box, a
Cut chain and a Cut; Scale uniform, non-uniform, chained and a failing one; Face from one wire, two sketches, a compound,
a shape with a hole through both face makers, a vertex and none; Ruled surface from two edges, two wires, whole shapes,
an edge and a wire, the three orientations, a
shape with no edge and none), their answers recorded from FreeCAD 26.3 by `tests/golden/part/make.py misc` into
`tests/golden/part/freecad_misc.json`; `tests/test_feature_part.py::test_a_reverse_without_a_source_fails_as_its_execute_does`
(the message FreeCAD's `Reverse::execute` gives, which a fresh FreeCAD object never reaches); and `ui/scripts/partcheck.mjs`'s
standalone section (35 checks), which failed first because the four commands were greyed. `tests/test_feature_part.py`
now loads every `cases_*.py` and its `freecad_*.json` by itself, so the new documents were checked without touching the
harness.

- Backend, `cad_agent/feature_part_misc.py` (new): `Part.Reverse` (the source's own shape reversed, its Placement
  taken from the source through the new `base_placement` hook; "No part object linked." when source-less),
  `Part.Scale` (uniform `BRepBuilderAPI_Transform`/`gp_Trsf.SetScale`, non-uniform `BRepBuilderAPI_Copy` then
  `BRepBuilderAPI_GTransform`, `Part::Scale`'s base/uniform/uniform_scale/x_scale/y_scale/z_scale), `Part.Face`
  (`Face::execute`: one compound link is its `useCompound`, else a compound of the links, through the face makers;
  `Part::FaceMakerUnified` a new object's), and `Part.RuledSurface` (`makeElementRuledSurface`: edges or wires,
  Automatic orientation by the cross products, `BRepFill::Face`/`Shell`, the general error message). `MISC` is
  registered at the bottom of the module, imported by `feature_part.py` like the other areas.
- Backend, `cad_agent/feature_part.py`: `PartObject.base_placement(ctx, params)` (its `placement=`, as before) used by
  `Context.add`, overridden by Reverse to return the source's Placement, as `Reverse::execute` leaves it.
- Goldens: `tests/golden/part/freecad.json` re-recorded (254f466's `make.py` records every object's Placement and
  normalises `App.Placement` lists; the old file predated it, so all 47 cases gain `placement` and the defaults'
  Placement lists are normalised); `freecad_attach.json` gains AttachExtension's values on the four new types.
- The page, `ui/src/part_wb.tsx`: Reverse Shapes, Scale, Face From Wires and Ruled Surface replace the greyed entries
  (`CmdPartReverseShape`'s one `<name>_rev`/`<Label> (Rev)` per selected object in one "Reverse" step and the sources
  left shown; `Part_Scale` opening the panel; `CmdPartMakeFace`'s one "Face" with the selection as Sources, "Make
  face"; `CmdPartRuledSurface`'s warning for 0 or 3+ and `Ruled_Surface` with `Curve1`/`Curve2` otherwise, including its
  `ok`-stays-true check); TYPES rows and their icons.
- The page, `ui/src/part_tasks.tsx`: `ScaleTask` (`DlgScale`: Uniform scaling / Factor, Non-uniform scaling /
  X-, Y-, Z-factor with the enable swap `onUniformScaleToggled` makes, the "Shape" tree list, OK | Close | Apply, the
  "No scalable shapes selected" box where OK still closes and Apply does not, one "Scale" step, each source hidden) and
  `scalableList` (a document's objects by type, a Vertex and an empty Compound left out, the Body when there is a Tip);
  `ObjList` finds a Body feature by name too. `.tsx` header and `ui/NOTICE` cite `DlgScale.cpp`/`.ui`.
- `ui/src/part_props.ts` regenerated by `ui/scripts/partprops.py` from the refreshed `ui/scripts/fcpart.json`: the four
  new types' groups and rows, and the catch-up from 254f466 (`Placement`, `AttachmentSupport`, `MapMode` are part-file
  keywords now, so their `k` is no longer null across the types that carry them). With the row held by the part file the
  Data tab's Attachment Support would have taken the generic link rendering ("[Base (Face6)]"); `part_wb.tsx` keeps
  FreeCAD's "Base:Face6" text for it, written by the Attachment panel (the full partcheck's attach section caught it).
- `ui/scripts/fcpart_dump.py`+`fcpart.json`: the six new command dumps (Reverse, Scale ok, Scale with no selection, Make
  Face, Ruled Surface, Ruled Surface with no selection) on their own fresh objects, and the refreshed dump.
- `ui/PARITY.md`: the four types, the commands, the Scale panel, the two knowing-difference bullets (whole-object Ruled
  Surface; the Scale list), the golden counts (247 documents) and partcheck's count.
- Bundle rebuilt (`cad_agent/workbench/next/`, NOTICE included).

### Commit

`ecfc12b` Part: Reverse, Scale, Face and Ruled Surface, as FreeCAD's commands make them

### Tests run

- `pytest tests/test_feature_part.py -q` — 853 passed in 7.55s (the 23 misc documents among them).
- `pytest tests/test_licenses.py -q` — 244 passed (the new citations are in `ui/NOTICE`, and the bundle's copy matches).
- `ui/scripts/partcheck.mjs --only=standalone` — 35 ok, 0 FAIL, 0 known.
- `ui/scripts/partcheck.mjs --only=menus,toolbars,standalone` — 94 ok, 0 FAIL, 15 known.
- `ui/scripts/partcheck.mjs` (full run, rebuilt bundle) — 441 ok, 0 FAIL, 17 known (the attach section's 17 and the
  standalone section's 35 among them). The first full run found one regression the new `part_props.ts` caused in the Data
  tab ("[Base (Face6)]" for Attachment Support); after the fix the attach section alone passed 17 ok, 0 FAIL, 0 known,
  and the second full run is the 441/0/17 above.
- `pytest $(tests/affected.py origin/main --list) -q` — 5,614 passed, 3 skipped (exit 0; the new `cases_misc.py` is
  collected by `test_feature_part.py` and `test_feature_edit_part.py` in that order too).
- `npx tsc -b --noEmit` — clean; `npm run build` — built, bundle committed.
- `tests/golden/part/make.py misc` and `make.py` (re-record) under `$FREECAD/freecadcmd`; `ui/scripts/fcpart.py` under
  the real FreeCAD GUI wrote the refreshed `ui/scripts/fcpart.json`.

### Unsure / questions

- **Ruled surface takes whole objects only.** FreeCAD's `getSelectionEx` carries sub-elements (an edge or a wire picked
  in the 3D view); the page's tree selection is whole objects, so one or two selected rows are taken as they are, as
  `CmdPartRuledSurface` itself does with whole shapes (`(obj, [''])`, the part file's bare name), and an object that is
  not an edge or a wire makes an object that fails to build, exactly as the C++ does. Written in PARITY.md; no test
  covers a sub-element pick because there is none.
- **A failed ruled surface is put back here, kept in error by FreeCAD.** As every `cad feature` change that does not
  build; PARITY.md's standing bullet.
- **The Scale list is by type, not by built shape.** `DlgScale::findShapes` asks every object's built shape and keeps
  those `canScale` takes; here the list is the part file's objects by type (a Vertex and an edge-less Compound left
  out), so an object that failed to build is listed here and not in FreeCAD. Written in PARITY.md.
- **The Scale list is captured when the panel opens**, as `findShapes` runs once from the dialog's constructor; an
  Apply's new Scale objects do not join it while the panel stays open.
- **The none-case undo name in the dump is an artifact.** `cmd_Part_Scale_none`/`cmd_Part_RuledSurface_none` open no
  transaction (DlgScale's `apply` returns before `openTransaction`, the Ruled command's validation runs before
  `openCommand`), so `fcpart_dump.py` falls back to the document's undo history for its "first new undo name"; the
  partcheck checks do not compare it.
- **`freecad.json`'s re-record is churn from 254f466's `make.py`**, not a shape change: every object gained a
  `placement` and the defaults' Placement lists were normalised. The test passes with the new file.
- **`part_props.ts`'s larger diff is the missing regeneration from 254f466** (the attach commit added `placement`,
  `attachment_support` and `map_mode` to `PartObject.COMMON` without re-running `partprops.py`); nothing about it is
  item 4's, but the refresh could not leave it out.
- **`cases_misc.py`'s helpers.** `from cases import P` failed when the whole suite was collected: another golden area's
  `cases` module can be the one `cases` resolves to (tests/golden/feature/cases.py has `rect` but no `P`), so `P` is
  spelled out in cases_misc.py; `rect` still comes from `cases`, as cases_attach.py's does, and both rects are the same
  four line segments. This is the item 3 note's path fragility, reached by the new file.
