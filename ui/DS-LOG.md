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

## 5. Pattern spacing labels (PARITY.md leftover) — done

### What was done

Tests written with the work (they failed first, with no `pd-spacing` helper drawn at all):
`ui/scripts/pickcheck.mjs`'s new `spacing` section (21 checks), held to the real FreeCAD's labels recorded through
`ui/scripts/fcpick_dump.py`, run under the FreeCAD GUI (`ui/scripts/fcpick.py`):

- `fcpick_dump.py` gained `datum_labels()` (walks the 3D view's Coin scene graph for the switched-on `SoDatumLabel`s,
  each with its text, its points in world coordinates through the node transforms, its colour, its datum type and an
  ANGLE's radius/start/range), `spacing()` (a LinearPattern: open, Occurrences 4, Mode Spacing, Spacings 20) and
  `polar_spacing_labels()` (a PolarPattern: open, Occurrences 4, Angular Spacing, Spacings 30), with
  `snap(..., labels=True)` recording them; `ui/scripts/fcpick.json` gained the resulting `spacing` key.
- The panel, `ui/src/pd_transform.tsx` (`TransformedTask`): `spacingLabels()` as TaskPatternParameters::
  updatePatternSpacingLabels computes the labels (one at the Extent; occurrences − 1 in Spacing, a `Spacings` entry of
  -1 at the global offset in EditableDatumLabel's deactivated #868E96 and an override in its activated #E03131), the
  points from TaskPatternParameters::getStartPoint (the originals' tools' combined bounding box centre, moved by the
  Body's placement), polar labels at the projected oriented start angle about the axis and the full 3D radius;
  `spacingSprite()`/`spacingOverlay()` draw each dimension (a line, or an arc sampled about the axis) and its text at
  EditableDatumLabel's 17 px; a click opens the label's spinbox (QDoubleSpinBox: text selected, Enter/Tab write,
  Escape and the focus leaving cancel, an unedited Enter committing the spinbox's own double — "33.33 mm" is its
  rounded text — and a value equal to the global offset going back to -1); a right click on an override offers
  "Reset spacing" (onSpacingLabelRightClicked), a -1 label leaving the view's own menu.
- The view, `ui/src/viewer.ts`: `labelPick`/`labelMenu`, the left-release branch for `spacing:` names, the popup's
  label menu, sprites in `helperPoint` (world position: a label has no mesh to sample), aspect-preserving
  `shapeScale` sizing, and the sprite map's disposal in `setHelper`. **`helperHit` lets a named sprite win outright**:
  the labels lie on the Body's top face and the Part/LCS datum planes are drawn in front of them, so nearest-wins
  picked the plane; Coin's dragger under an SoAnnotation takes the click on the text whatever is behind it. That was
  the last failure (the polar half's three checks; the linear half had already passed).
- `ui/PARITY.md`: the labels are in the panels row now, and the MultiTransform sub-patterns' missing labels are a
  recorded difference (TaskMultiTransformParameters' embedded TaskPatternParameters calls updatePatternSpacingLabels
  too).
- Bundle rebuilt (`cad_agent/workbench/next/`).

### Commit

`cd39bd5` PartDesign: the patterns' on-view spacing labels, as PatternParametersWidget draws them

### Tests run

- `ui/scripts/pickcheck.mjs --only=spacing` — 21 ok, 0 FAIL, 0 known. The first run, before the `helperHit` fix,
  failed the polar half's three checks (19 ok, 3 FAIL); the run after it, and the rerun once the diagnostics were
  removed, are 21/0/0.
- `ui/scripts/pickcheck.mjs --only=linear,polar,spacing,select` — 94 ok, 0 FAIL, 4 known (the two known datum-line
  rows in each of linear and polar). `select` because `helperHit` changed.
- `pytest tests/test_licenses.py -q` — 244 passed (the two `src/Gui` files `pd_transform.tsx` now cites are in
  `ui/NOTICE` already).
- `pytest $(tests/affected.py origin/main --list) -q` — 5,614 passed, 3 skipped (exit 0).
- `npx tsc --noEmit` — clean; `npm run build` — built, bundle committed (the hash did not change after the last
  comment-only edit, so the checked bundle is the built one).

### Unsure / questions

- **The golden was merged in by hand.** A full `fcpick_dump.py` regeneration from the real FreeCAD GUI exited 0 with no
  errors, but it also rewrites other sections with FreeCAD's nondeterministic bits (the `delete` section's heap names
  and message-box order) and adds empty `message_boxes` keys to sections that had none. The committed file is HEAD's
  JSON with only the `spacing` key inserted (`json.dumps(indent=1)`), so the diff is purely additive (2206 insertions,
  no other key changed — verified against HEAD).
- **The named-sprite precedence is a viewer-wide rule**, not a spacing-label special case: any future helper that makes
  a sprite pickable will win over the model geometry behind it. Stated in its comment; only the spacing labels are
  named sprites today.
- **The Sketcher's own `EditableDatumLabel` (`sketchovp.ts`) is not reused**: it works in the sketch's 2D coordinate
  system and reports into the Sketcher's draw state. The 3D view's labels have a small local sprite and box, with the
  same `.ovp-box` styling.
- **FreeCAD's DISTANCE labels' `param1`/`param2` are left out of the comparison**: they are EditableDatumLabel's own
  text offsets from the dimension's midpoint (a text placement detail), while `labels` carries the dimension's two
  points. Our text sits at the midpoint; the golden compares text, points, colour, and an ANGLE's radius and start
  angle.
- **The labels' text is drawn in the browser at a constant 17 px** with the label's colour, not through Coin's font
  rendering; the checks compare what the overlay records (`userData.labels`) and the label's click behaviour, not the
  pixels.

## 6a. Sketcher visual layers (the handoff's "Sketcher text and visual layers", first half) — done

### What was done

Tests written with the work (they failed first):

- Three cases in `ui/scripts/sketchcases-panels.json`: `layer-menu` (Extended information on; row 1
  moved with the context menu's Layer/Layer 1, then row 0 with Layer/Hidden), `layer-check` (the row
  check boxes: hide two, show one, hide another) and `layer-external` (a plate's Pad.Edge4 projected
  in, then the Layer menu on the external row), with FreeCAD's answers merged into
  `ui/scripts/sketchref-panels.json` (513 insertions, 0 deletions: the three keys only).
- The first run failed on two things, both fixed: `layer-menu` had row 0 still selected where FreeCAD
  has every row unselected (`SketchObject::acceptGeometry` rebuilds TaskSketcherElements' list, and a
  rebuilt list has no row selected, while the Gui selection stays), and `layer-external` read "Empty
  sketch" where FreeCAD reads "Fully constrained" (`ViewProviderSketch::UpdateSolverInformation` also
  wants ExternalGeo to hold nothing beyond the axes).
- Part-file tests: `tests/test_feature.py::test_geometry_layer_is_a_keyword_only_when_set` and
  `tests/test_feature_edit.py::test_set_sketch_geometry_layer` (the keyword appears when set and goes
  away at 0; an edit writes the one changed line).

Then:

- The part file: `layer=` on every geometry constructor (`cad_agent/feature.py`, the conics and
  B-splines in `feature_curves.py`), validated to 0/1/2, in `as_dict()`/`source()` only when not 0,
  read by `geometry_from_dict`; `feature_edit.py`'s `geometry_src` writes it back.
- The solver transport: `ui/planegcs/sketch.h`'s `Geometry.layer`, `api.cpp` parsing and writing
  `layer` (only when not 0), the rebuilt `dist/planegcs.wasm`, and `ui/src/planegcs.ts`'s `Geo`
  types. The solver never reads it.
- Drawing and picking (`ui/src/sketchdraw.ts`, `ui/src/sketcher.ts`'s `detect`): a Hidden geometry is
  not drawn and its edges and vertices are not picked.
- The Elements box (`ui/src/sketchpanels.tsx`): the row's check box is the visual layer (checked on
  Layer 0 and 1, unchecked on Hidden; disabled for external geometry, as `canBeHidden` leaves it),
  a click or the context menu's Layer 0 / Layer 1 / Hidden moves it in the "Geometry Layer Change"
  transaction; the Layer entries read the Gui selection as `ElementView::changeLayer` does
  (`getGeoIdsOfEdgesFromNames`: a vertex names its geometry only for a `GeomPoint`), and external
  geometry is refused with FreeCAD's TranslatedUserWarning text as a `report('warn')`. Labels carry
  `#VL<layer>` in the Extended information form, as FreeCAD's IdInformation does with its default
  three-layer list (the browser has no layer-list setting, so it always writes it).
- The list's row selection (`ui/src/sketcher.ts`, `ui/src/sketchpanels.tsx`): a counter that also says
  which of FreeCAD's two signals came last (`slotElementsChanged`'s rebuild on any geometry or
  constraint change vs `onSelectionChanged`), with the rows a snapshot of the selection; a Layer menu
  entry leaves the rows unselected while the selection stays.
- `messageOf`'s empty test now needs ExternalGeo at the axes only.
- Harness: `fcsketch_dump.py` reads a geometry's layer (`geom_layer`), carries each element row's
  layer, clicks the check box through `QTest.mouseClick`, and takes menu paths into sub-menus;
  `sketchcheck.mjs` compares geometry and element rows' `layer`, clicks `input[data-sub="check"]`,
  takes `Layer/Layer 1` paths, and compares a case's literal `labels` (FreeCAD's ElementItem keeps
  its label in a private C++ member that its delegate paints, so the oracle cannot read it back).
- `ui/PARITY.md`: the Elements box row, the panels suite's counts and the visual-layer paragraph (a
  part-file key, carried by the solver; FreeCAD keeps it in the SketcherGui geometry extension
  `ViewProviderSketchGeometryExtension`'s VisualLayerId, which the part file's FreeCAD export here
  does not write, so Hidden is not drawn or picked in the browser only).
- Bundle rebuilt (`cad_agent/workbench/next/`; its solver wasm has the same md5 as
  `ui/planegcs/dist/planegcs.wasm`).

The full-suite run also caught a harness regression from the Layer work: the new path syntax read
`Toggle Driving/Reference` as a submenu path, so `panel-toggle-reference` and
`panel-toggle-reference-back` silently did nothing. Both `sketchcheck.mjs`'s `pickCtx` and
`fcsketch_dump.py`'s `run_menu` now try the exact label first and fall back to splitting on `/`.

### Commit

`e3aa35d` Sketcher: the Elements box's visual layers, as FreeCAD's check box and Layer menu make them

### Tests run

- `sketchcheck.mjs --suite panels --only layer-menu,layer-check,layer-external,panel-toggle-reference,panel-toggle-reference-back`
  — 5/5 cases as FreeCAD, 0 known, 19 colours, 0 differences.
- `sketchcheck.mjs --suite panels` on the final bundle — 92/93 cases as FreeCAD, 1 known (el-shift),
  19 colours, 0 differences.
- `sketchcheck.mjs` every suite on the final bundle — 316/320 cases as FreeCAD, 4 known (c-parallel,
  el-shift, ovp-polyline-lengths, ovp-polyline-arc), 19 colours, 0 differences. (PARITY's
  every-suite sentence was still the pre-layer run's 313/317; refreshed in `1a70eac`.)
- `npx tsc --noEmit` clean; `npm run build` OK.
- `pytest tests/test_feature.py tests/test_feature_edit.py -q` — 151 passed.
- `pytest tests/test_licenses.py -q` — 244 passed.
- `pytest $(.venv/bin/python tests/affected.py origin/main --list) -q`
  — 5,616 passed, 3 skipped in 103.28 s.
  (An earlier attempt with the bare `tests/affected.py` failed the substitution — the file is tracked
  without the executable bit — so pytest ran the whole `tests/` tree instead: 7174 passed, 23 skipped
  in 596.75 s.)

### Unsure / questions

- **The labels are literals a case carries**, transcribed from FreeCAD's source (`ExtendedNaming`'s
  formats and its capitalization quirks, e.g. "Parabolic arc" against "Parabolic Arc" for an external
  one) because its `ElementItem` keeps the label private; a change in FreeCAD's formats would only
  show up by reading the source again.
- **The part file's `layer` is not part of the FreeCAD export** (`feature_part._sketch_to_freecad`
  calls `addGeometry` without an extension), so a document opened in FreeCAD loses it: Hidden is not
  drawn or picked in the browser only. Layer 1 (Discontinuous) is drawn like Layer 0 here; FreeCAD's
  discontinuous drawing is not ported.
- **Geometry tools that build new geometry** (trim/split/fillet/copy/arrays) do not carry a layer
  over; what FreeCAD does for each of them (some clone the geometry, with its extension) is not
  checked here.
- **The row selection is a one-counter model** of FreeCAD's two signals (`slotElementsChanged` and
  `onSelectionChanged`), equivalent while every list-changing call is synchronous, as this sketch
  layer is. The snapshot's key is the sketch ref, so opening another sketch starts it over.
- **The empty-sketch change is a behaviour change beyond layers**: a sketch holding only external
  geometry now reads "Fully constrained" (as FreeCAD does) instead of "Empty sketch".
- **The external geometry's check box is drawn disabled rather than left out**, because FreeCAD's
  delegate draws it with `State_Enabled` false (`canBeHidden`); Toggle Construction on external
  geometry still does nothing.

## 6b. Sketcher text — skipped, needs Juan

The last of the handoff's PARITY leftovers; PARITY's "not built yet, shown greyed" line for
Sketcher_CreateText still holds. What it is, read from FreeCAD main 3160daf1e2b6:

- `DrawSketchHandlerText` (`src/Mod/Sketcher/Gui/DrawSketchHandlerText.h`): two construction methods,
  Width and Height (M switches them), four on-view parameters (the handle line's start x and y, its
  length, its angle), a tool widget with a Text line edit and a Font combo box, and a two-click
  handle line (construction geometry in construction mode). `executeCommands` adds the handle
  (`Part.LineSegment`, construction), a `Sketcher.Constraint('Text', [handle, 0], text, fontPath,
  isHeight)` holding only the handle, then calls `setTextAndFont`.
- `SketchObject::setTextAndFont` (`SketchObject.cpp:710`) deletes the old text geometries, builds
  glyph wires with `Part::makeTextWires(text, fontFile)` (`Part/App/Geometry.cpp:7628`: FreeType's
  `FT_Outline_Decompose` for the outlines, HarfBuzz's `hb_shape` for the positions), transforms them
  onto the handle line (`Part::transformAndConvertToGeometry`, `Geometry.cpp:~7500`: scale by the
  handle's length or height, rotate, translate; each edge becomes a line, a circle, an arc, a conic
  or a B-spline), adds them as ordinary sketch geometry, and rebuilds the Text constraint over the
  handle and every new geometry, with Text, Font and IsTextHeight.
- The Font combo lists the font files installed on the machine (`FontProvider::findAvailableFontFiles`:
  the TechDraw resource fonts plus fontconfig's list on Linux), preferring `osifont-lgpl3fe`, then
  `DejaVu Sans`, then `Arial`; the constraint keeps the family name, `EditTextDialog` maps it back to
  a path to regenerate, and a double click on a Text constraint opens that dialog.
- The text geometry is ordinary sketch geometry (lines and B-splines), so a FreeCAD file with text
  draws without any font; only creating or editing the text needs one.

**Why it is blocked.** The font pipeline is a design decision, not a port:

- **Font source.** FreeCAD reads the host's font files. A browser cannot: its Canvas has no
  glyph-outline API and no font directory to scan. The choices are (a) ship one free font with the
  workbench (DejaVu Sans, Bitstream Vera licence, 760 KB; FreeCAD's default preferences are
  osifont-lgpl3fe then DejaVu Sans) and make it the only family, (b) have the Python server read the
  host's fonts as FreeCAD does — `fontTools` (present in the dev venv only as another package's
  transitive dependency) is pure Python and can read outlines and advances — with a new server call
  from inside the sketch editor, which is otherwise entirely client-side (planegcs wasm), or (c) a
  JS font parser (e.g. opentype.js, MIT) over a shipped font, another vendored dependency.
- **Shaping.** FreeCAD positions glyphs with HarfBuzz (kerning, ligatures, complex scripts).
  `fontTools` reads outlines and hmtx advances but does not shape, and no FreeType or HarfBuzz
  binding is installed here (no `freetype`, no `uharfbuzz`; OCP's `Font` module exposes no
  `Font_BRepFont`). An advances-only model would differ from FreeCAD wherever the font kerns: the
  oracle would have to document that difference, or its cases avoid kerning pairs.
- **Part-file vocabulary.** A Text constraint (FreeCAD's `Constraint::Text`, 21) holds the handle's
  GeoId and every generated geometry's GeoId plus Text, Font and IsTextHeight; the solver skips it
  (it is not a solver constraint). The part file's constraint vocabulary has no such type, and the
  FreeCAD export (`feature_part._sketch_to_freecad`) could not write one. This half is independent
  of the font question and could be done first if that is wanted.

**Question for Juan:** which font source (and so which dependency) should sketch text use — a free
font shipped with the workbench, the host's fonts server-side through fontTools, or a JS font parser
— and is text that does not match FreeCAD's HarfBuzz shaping acceptable as a documented difference,
or must the oracle compare it glyph for glyph? Moved on; this was the last item on the handoff's Next
list (Assembly joints was logged as a question in item 1, and everything else there is done).

## 7. The review's three small items — done

A Claude lane's review of `ds/handoff-1025` found code and documentation leftovers; the code findings it is fixing
itself (ShapeBinder placement, attachment query, empty binder, binder tests, editcheck's binder check, Direction 2
spacing labels) were left alone here, and so were the files that carry them.

### 7a. PARITY entries and the Data tab's Attachment Support — commits `736294c`, `59db590`

- `ui/src/part_wb.tsx`: a Part object's Data tab wrote Attachment Support as `Base:Face6`; FreeCAD's property view
  writes `Base [Face6]` (and `Origin [XY_Plane.]` for an Origin feature), the form `pd_attach.tsx`'s `attachmentRows`
  already uses, so `PartObjectProps` now renders that, and the unreachable `AttachmentSupport` arm inside the
  read-only row is gone. No PARITY line was needed for it. `ui/scripts/partcheck.mjs`'s property-view check now
  expects FreeCAD's `Base [Face6]` instead of the old `Base:Face6`.
- `ui/PARITY.md`, in the matching sections: Part_EditAttachment opens TaskAttacher's panel (not FreeCAD's Python
  TaskAttachmentEditor), its undo step is "Edit attachment" (FreeCAD's "Edit attachment of <name>"), an empty
  reference line reads "No reference selected" (FreeCAD's is empty), and a self-click is ignored without FreeCAD's
  "Ignored. Can't attach object to itself!"; Deactivated returns a Part object to its old `placement=` where FreeCAD
  keeps the last attached Placement; Scale at factor 0 is an error here, an empty shape in FreeCAD; the spacing
  labels' DISTANCE is a bare line with its text at the middle (FreeCAD: extension lines and arrows), fall back to X
  where FreeCAD falls back to Z, and carry the Body's Placement (FreeCAD's are Body-local, equal at the identity);
  Trim/Split/Fillet and the other tools drop their new geometry's layer, and the Elements list re-selects every
  selected row after a rebuild where FreeCAD changes one row at a time; the ShapeBinder panel takes only this Body's
  features, where FreeCAD takes any Part::Feature in the document. The stale ShapeBinder row's "a whole-Body
  selection binds the Tip solid" is gone: `refsOfSelection(part, false)` drops the Body, as FreeCAD's command does.
- Bundle rebuilt (`cad_agent/workbench/next/`).

### 7b. ShapeBinder panel fixes — commit `61a37d4`

- `ui/src/pd_binder.tsx`: the edit's undo step is "Edit Shape Binder", Command.cpp's transaction before
  `PartDesignGui::setEdit` (it was "Edit <name>"). The five refusal messages in `take` (self-pick, non-Part::Feature,
  another support object, duplicate, missing element) are gone: `referenceSelected` returns false silently and the
  mode still ends. The invented Object/Add/Remove tooltips are gone too: `TaskShapeBinder.ui` at 3160daf1e2b6 has no
  toolTip properties and `setupButtonGroup` sets none.
- Bundle rebuilt (`cad_agent/workbench/next/`).

### 7c. geometry_src's layer validation — commit `cfc2504`

- `cad_agent/feature_edit.py`: `geometry_src` asks `feature._layer` before writing any geometry, so a `layer` that is
  not an int 0, 1 or 2 (a float `2.0`, `True`, `-1`, `3`) is refused at write time with the build's own message,
  instead of being written and refused on read-back with the feature's name prefixed. Line/Circle/Arc/Point go
  through it; the conics already validated in their constructors.
- `tests/test_feature_edit.py`: `test_a_geometry_layer_is_validated_as_the_build_does`, the four types × four bad
  layers, compares the message to `feature.geometry_from_dict`'s and checks the file is untouched.

### Tests run

- `pytest tests/test_feature_edit.py tests/test_licenses.py -q` (PYTHONPATH this worktree) — 279 passed.
- `npx tsc -b --noEmit` — clean; `npm run build` — built, bundle committed.
- `ui/scripts/partcheck.mjs --only=attach` — 17 ok, 0 FAIL, 0 known (run with `CAD_PYTHON` the shared venv and
  `NODE_PATH` the folder with playwright; this worktree has neither a .venv nor playwright).
- `ui/scripts/editcheck.mjs` was not run: its Shape Binder section still expects the old undo name "Edit ShapeBinder"
  (`editcheck.mjs:332`), which the review's other lane is fixing along with the binder code findings; the file is
  outside this lane's edits.

### Unsure / questions

- None of the three needed a design decision. The Data tab's Origin form ("Origin [XY_Plane.]") follows
  `pd_attach.tsx` and `fcedit.json`; the ShapeBinder row now records "Edit Shape Binder" as both the panel's step and
  the tree menu's label.

## 8. PARITY corrections (docs only)

A Claude lane asked for three out-of-date PARITY passages to be corrected against the code, one commit per item
(`parity: …`); `ui/PARITY.md` and this log are the only files changed.

### 8a. Toolbars: the workbench selector and the Part Design toolbars — commit `parity: toolbars — the workbench selector's six workbenches and the Part Design buttons that run`

What: the "Workbench" row now lists the workbenches the selector actually offers; the "Part Design Helper /
Modeling / Dress-Up / Transformation Features" row names the commands that work and the ones still greyed "not yet".

Verified against `ui/src`: `chrome.tsx`'s `WORKBENCHES` has agent (CAD Agent), design (Part Design), assembly
(Assembly), inspection (Inspection), sketcher (Sketcher) and part (Part), and `workbenchList()` filters only what
Preferences > Workbenches disabled (`WB_DEFAULTS` disables none); the toolbar's combo/TabBar and View > Workbench
both draw that list. In `partdesign.tsx`, `pdToolbars()` builds the four toolbars from `partDesignMenu()`/`sketchMenu()`:
New Body, New Sketch (cmd `PartDesign_CompSketches`), Validate Sketch, Pad, Revolve, Additive Loft/Pipe/Helix, the
additive and subtractive primitive groups, Pocket, Hole, Groove, Subtractive Loft/Pipe/Helix, Mirror, Linear Pattern,
Polar Pattern, Multi-Transform, Fillet, Chamfer, Draft and Thickness are not disabled (the entity panels behind them are
in `pd_revolve.tsx`, `pd_sweep.tsx`, `pd_dressup.tsx`, `pd_transform.tsx`, and the build modules `cad_agent/feature_*.py`
exist); `soon()` marks Sub-Shape Binder, Clone, Boolean Operation and Defeaturing disabled with the "not yet" title,
and Check Geometry is disabled with its n/a reason. `editcheck.mjs` compares the toolbar buttons' commands to
`fcedit.json` and passes 79 ok (the count in PARITY.md is left as it was; it was not run here).

Unsure: none.

### 8b. PartDesign: the menus row and editcheck's 12 known lines — commit `parity: PartDesign menus — what is still greyed and the 12 known editcheck lines`

What: the "Sketch and Part Design menus" row no longer says "what step 5 builds later is greyed"; it names the
commands still greyed "not yet". The "PartDesign, 2026-10-24" paragraph's "12 known lines" keeps its count but now
says what the 12 are.

Verified against `ui/src/partdesign.tsx`: `partDesignMenu()` has `soon()` on Sub-Shape Binder and Clone (line 1135),
Defeaturing in Dress-Up (1147), Boolean Operation (1151), Involute Gear and Sprocket (1158) and Shaft Design Wizard
(1160); the material inspectors and Check Geometry are `disabled: true` with an n/a title, not "not yet". Counted
what `ui/scripts/editcheck.mjs` records as `known`, without running it: `compare()` notes each FreeCAD menu entry that is
enabled there and disabled here unless it is in `GREYED` — the Part Design menu gives 9 (the seven above plus
Inspect Appearance and Inspect Material, both enabled in `fcedit.json`), the Sketch menu gives 0 (`fcedit.json` has
Edit/Attach/Reorient/Validate/Merge/Mirror Sketch disabled); the tree-menu loop notes "Send to Console" once for
each of `menu_pad`, `menu_sketch` and `menu_body`, which all list FreeCAD's "Send to Python Console": 3. 9 + 3 = 12,
so the count stands.

Unsure: none.

### 8c. Still missing: the list of what is not done — commit `parity: still missing — the greyed and cut features, section by section`

What: "## Still missing" was one bullet that said only that PartDesign's features "after Pad and Pocket" come later (a
promise now met: Revolution, Groove, Hole, the patterns, the primitives, the dress-ups, Loft, Pipe and Helix all work). It is
now nine one-line bullets of what is left, each naming FreeCAD's commands and the section that explains it: PartDesign's
seven "not yet" commands and its four greyed tree entries; the Part workbench's greyed or unported commands; the Assembly
features cut whole, the drag and panel gaps; the Sketcher's external intersection, the external geometry refused, Validate's
Swap Endpoints; Loft/Pipe/Helix's non-planar ends and a solid face as Profile; TechDraw editing; and the workbenches the
selector does not offer.

Verified against the sections quoted and the code behind them: `ui/src/partdesign.tsx` (`soon()` at lines 1135, 1147, 1151,
1158, 1160; the tree's `na()` entries at 546-557), `ui/src/part_wb.tsx` (the greyed Part commands, as "Part workbench" line
655 lists them), `ui/src/assembly_wb.tsx` (`NA()`: Link Arrays, Exploded View, Snapshot, Simulation, Create Rigid Group, New
Part, Go to Linked Assembly, Bill of Materials) with "Assembly workbench, 2026-10-26" for the rest, `ui/src/sketchcmds.ts`
(`why()` returns "Not in this workbench yet" for an unimplemented command; Sketcher_Intersection is not in `RUN`),
"Attachment and datums, 2026-10-24" (line 457, the refused external geometry), "Sketcher text and the commands on sketch
objects, 2026-10-26" (Swap Endpoints, port_reversedExternalArcs), "PartDesign Loft, Pipe and Helix, 2026-10-24" (the
non-planar Pipe ends and the solid face as Profile), `ui/src/shopwb.tsx` (the drawing tab is `cad drawing`'s page, DXF/SVG/PDF
exports; no TechDraw editing code), and `ui/src/chrome.tsx`'s `WORKBENCHES` (six workbenches; no Spreadsheet or Draft).

Unsure: none.

## 9. Test loading: each golden's `cases.py` under its own name — done

### What was done

Several golden folders have a module called `cases.py`. Tests and helpers put the folder on `sys.path` and did a
bare `from cases import ...`, so `sys.modules["cases"]` held whichever golden's file was imported first and the
suite broke in another order. The brief's pair,
`pytest -q tests/test_feature_part.py tests/test_feature_transform.py`, passes in this worktree (1048 passed)
because nothing in that pair imports a bare `cases` after part's folder is on the path; the collision itself
reproduced with `pytest -q tests/test_feature_part.py tests/test_feature_attach.py`: `ImportError: cannot import
name 'base_pad' from 'cases' (tests/golden/part/cases.py)` — `cases_attach.py`'s `from cases import rect` had put
part's `cases.py` in `sys.modules`, and `bodies.py`'s `from cases import base_pad` then got it. Every test-side load
now follows `tests/test_feature_binder.py` and `tests/test_assembly_golden.py`: `importlib.util.spec_from_file_location`
by path, under a unique module name.

- `tests/test_feature.py`: `feature_cases` for `tests/golden/feature/cases.py`; no `sys.path.insert`.
- `tests/test_feature_attach.py`: `attach_bodies` for `golden/attach/bodies.py` and `feature_cases` for
  `golden/feature/cases.py`, both by path; no `sys.path.insert`.
- `tests/test_feature_edit_part.py`, `tests/test_feature_part.py`: the `sys.path.insert(golden/part)` is gone (both
  already loaded every `cases*.py` by path; the insert existed only for the helpers' bare `cases` import).
- `tests/golden/attach/bodies.py`: `feature_cases` (feature's `base_pad`, `rect`, `rect_constraints`).
- `tests/golden/dressup/dressup_cases.py`: `feature_cases` (feature's `base_pad`, `rect`, `rounded`, `step`).
- `tests/golden/part/cases_misc.py`, `tests/golden/part/cases_attach.py`: `part_base_cases`, the name
  `cases_split.py` already used, for part's `rect` (and `P` in `cases_misc.py`, replacing the spelled-out copy and
  its "another golden's `cases`" comment).
- `tests/golden/part/cases_split.py` already loaded by path, `cases_sweep.py` is self-contained; nothing to change.

No `tests/golden/*/make.py` changed. The files a make.py imports keep working both ways, because the by-path load
inside the helper does not depend on `sys.path` and the make script still imports the helper by its old name:

- `attach/make_bodies.py` → `from bodies import CASES` (attach and feature on its `sys.path`): imported, 33 cases.
- `dressup/make.py` → `from dressup_cases import CASES, FOLLOW`: imported, 51 cases + 5 FOLLOW.
- `part/make.py` → `importlib.import_module("cases_misc" / "cases_attach" / ...)` (part on its `sys.path`):
  imported; `cases` 47, `cases_misc` 24, `cases_attach` 12, `cases_split` 67, `cases_sweep` 98 (checked with the
  scripts' own `sys.path` setup in plain Python, not freecadcmd).
- `feature/make.py` → `from cases import CASES`: `tests/golden/feature/cases.py` itself is untouched and still
  importable that way.

The remaining test-side `sys.path.insert`s cannot shadow `cases.py`: `test_feature_dressup.py` imports
`dressup_cases`, `test_feature_edit_attach.py` imports `bodies`, and the sketch goldens' `freecad_side.py` (run by
freecadcmd, not pytest) import `freecad_side_geo` — all unique names.

### Commit

`tests: load each golden's cases.py by path under its own module name`

### Tests run

a) each touched test file alone (`PYTHONPATH=$PWD .venv/bin/python -m pytest -q <file>`):

```
== tests/test_feature.py
132 passed in 4.72s
== tests/test_feature_attach.py
332 passed in 3.11s
== tests/test_feature_edit_part.py
690 passed in 3.34s
== tests/test_feature_part.py
855 passed in 5.65s
== tests/test_feature_dressup.py
152 passed in 5.23s
== tests/test_feature_edit_attach.py
57 passed in 5.60s
```

(`test_feature_dressup.py` and `test_feature_edit_attach.py` were not edited, but their helpers changed.)

b) every pair of the touched test files plus `test_feature_transform.py`, `test_feature_dressup.py`,
`test_feature_part.py`, `test_feature_binder.py`, `test_assembly_golden.py`, in both orders (56 runs; assembly skips
because `ui/ondsel` is not built). All passed, `fail=0`:

```
PAIR 1: tests/test_feature.py tests/test_feature_attach.py :: 464 passed in 5.82s
PAIR 2: tests/test_feature_attach.py tests/test_feature.py :: 464 passed in 5.79s
PAIR 3: tests/test_feature.py tests/test_feature_edit_part.py :: 822 passed in 6.11s
PAIR 4: tests/test_feature_edit_part.py tests/test_feature.py :: 822 passed in 5.99s
PAIR 5: tests/test_feature.py tests/test_feature_part.py :: 987 passed in 9.95s
PAIR 6: tests/test_feature_part.py tests/test_feature.py :: 987 passed in 9.89s
PAIR 7: tests/test_feature.py tests/test_feature_transform.py :: 325 passed in 9.60s
PAIR 8: tests/test_feature_transform.py tests/test_feature.py :: 325 passed in 9.59s
PAIR 9: tests/test_feature.py tests/test_feature_dressup.py :: 284 passed in 7.98s
PAIR 10: tests/test_feature_dressup.py tests/test_feature.py :: 284 passed in 8.17s
PAIR 11: tests/test_feature.py tests/test_feature_binder.py :: 203 passed in 6.04s
PAIR 12: tests/test_feature_binder.py tests/test_feature.py :: 203 passed in 6.03s
PAIR 13: tests/test_feature.py tests/test_assembly_golden.py :: 132 passed, 98 skipped in 4.89s
PAIR 14: tests/test_assembly_golden.py tests/test_feature.py :: 132 passed, 98 skipped in 4.86s
PAIR 15: tests/test_feature_attach.py tests/test_feature_edit_part.py :: 1022 passed in 4.40s
PAIR 16: tests/test_feature_edit_part.py tests/test_feature_attach.py :: 1022 passed in 4.36s
PAIR 17: tests/test_feature_attach.py tests/test_feature_part.py :: 1187 passed in 8.24s
PAIR 18: tests/test_feature_part.py tests/test_feature_attach.py :: 1187 passed in 8.33s
PAIR 19: tests/test_feature_attach.py tests/test_feature_transform.py :: 525 passed in 7.70s
PAIR 20: tests/test_feature_transform.py tests/test_feature_attach.py :: 525 passed in 7.64s
PAIR 21: tests/test_feature_attach.py tests/test_feature_dressup.py :: 484 passed in 6.17s
PAIR 22: tests/test_feature_dressup.py tests/test_feature_attach.py :: 484 passed in 6.28s
PAIR 23: tests/test_feature_attach.py tests/test_feature_binder.py :: 403 passed in 4.37s
PAIR 24: tests/test_feature_binder.py tests/test_feature_attach.py :: 403 passed in 4.38s
PAIR 25: tests/test_feature_attach.py tests/test_assembly_golden.py :: 332 passed, 98 skipped in 3.14s
PAIR 26: tests/test_assembly_golden.py tests/test_feature_attach.py :: 332 passed, 98 skipped in 3.26s
PAIR 27: tests/test_feature_edit_part.py tests/test_feature_part.py :: 1545 passed in 8.67s
PAIR 28: tests/test_feature_part.py tests/test_feature_edit_part.py :: 1545 passed in 8.66s
PAIR 29: tests/test_feature_edit_part.py tests/test_feature_transform.py :: 883 passed in 7.78s
PAIR 30: tests/test_feature_transform.py tests/test_feature_edit_part.py :: 883 passed in 8.01s
PAIR 31: tests/test_feature_edit_part.py tests/test_feature_dressup.py :: 842 passed in 6.47s
PAIR 32: tests/test_feature_dressup.py tests/test_feature_edit_part.py :: 842 passed in 6.46s
PAIR 33: tests/test_feature_edit_part.py tests/test_feature_binder.py :: 761 passed in 4.47s
PAIR 34: tests/test_feature_binder.py tests/test_feature_edit_part.py :: 761 passed in 4.69s
PAIR 35: tests/test_feature_edit_part.py tests/test_assembly_golden.py :: 690 passed, 98 skipped in 3.29s
PAIR 36: tests/test_assembly_golden.py tests/test_feature_edit_part.py :: 690 passed, 98 skipped in 3.27s
PAIR 37: tests/test_feature_part.py tests/test_feature_transform.py :: 1048 passed in 11.60s
PAIR 38: tests/test_feature_transform.py tests/test_feature_part.py :: 1048 passed in 11.84s
PAIR 39: tests/test_feature_part.py tests/test_feature_dressup.py :: 1007 passed in 10.31s
PAIR 40: tests/test_feature_dressup.py tests/test_feature_part.py :: 1007 passed in 10.23s
PAIR 41: tests/test_feature_part.py tests/test_feature_binder.py :: 926 passed in 8.37s
PAIR 42: tests/test_feature_binder.py tests/test_feature_part.py :: 926 passed in 8.42s
PAIR 43: tests/test_feature_part.py tests/test_assembly_golden.py :: 855 passed, 98 skipped in 5.66s
PAIR 44: tests/test_assembly_golden.py tests/test_feature_part.py :: 855 passed, 98 skipped in 5.76s
PAIR 45: tests/test_feature_transform.py tests/test_feature_dressup.py :: 345 passed in 9.77s
PAIR 46: tests/test_feature_dressup.py tests/test_feature_transform.py :: 345 passed in 9.88s
PAIR 47: tests/test_feature_transform.py tests/test_feature_binder.py :: 264 passed in 7.83s
PAIR 48: tests/test_feature_binder.py tests/test_feature_transform.py :: 264 passed in 7.78s
PAIR 49: tests/test_feature_transform.py tests/test_assembly_golden.py :: 193 passed, 98 skipped in 6.62s
PAIR 50: tests/test_assembly_golden.py tests/test_feature_transform.py :: 193 passed, 98 skipped in 6.65s
PAIR 51: tests/test_feature_dressup.py tests/test_feature_binder.py :: 223 passed in 6.50s
PAIR 52: tests/test_feature_binder.py tests/test_feature_dressup.py :: 223 passed in 6.46s
PAIR 53: tests/test_feature_dressup.py tests/test_assembly_golden.py :: 152 passed, 98 skipped in 5.30s
PAIR 54: tests/test_assembly_golden.py tests/test_feature_dressup.py :: 152 passed, 98 skipped in 5.29s
PAIR 55: tests/test_feature_binder.py tests/test_assembly_golden.py :: 71 passed, 98 skipped in 3.37s
PAIR 56: tests/test_assembly_golden.py tests/test_feature_binder.py :: 71 passed, 98 skipped in 3.37s
MATRIX DONE: 56 runs, fail=0
```

Extra (the two tests that both load `golden/attach/bodies.py`, in both orders): 389 passed in 6.85s each.

c) collected count before and after (the working-tree diff reversed with `git apply -R`, collected, then
re-applied — equal):

```
before: 7397 tests collected in 3.26s
after:  7397 tests collected in 3.34s
```

### Unsure / questions

None.

## 10. User docs: the FreeCAD-style editing — done

What: the user docs did not mention the FreeCAD-style editing. `README.md`'s "## Commands" block gains one line each for
`cad feature`, `cad assembly` and `cad techdraw` (three lines, in the block's command-then-phrase style), and
`docs/DETAILS.md`'s "### The FreeCAD-style UI (in progress)" gains a short paragraph and four bullets: the workbenches
the page offers; that an edit in the page or through those three commands is written back into `parts/<Part>.py`
(`FEATURES`, `OBJECTS`), `assembly.py` (`ASSEMBLY`) and `techdraw/<Page>.py` (under `TechDraw`); one undo step per edit;
and that each edit is checked against the real FreeCAD, with `ui/PARITY.md` for what differs and `docs/EDITING_PLAN.md`
for the file formats. Docs only; no tests run.

### Help output the README lines were checked against

`feature` line ("list, add, set, delete, move, clone"):

```
$ cad feature --help
usage: cad feature [-h] [--json] <action> ...

a part's PartDesign feature list (Body, Sketch, Pad, Pocket, Fillet, Chamfer, Draft, Thickness): list, new, add, set, delete, rename, move, tip; each change one undo step
...
    list        the Body's tree of one part, or of every part
    new         a new part module with an empty Body (FreeCAD's Create body)
    add         add a Sketch, Pad, Pocket, ...
    set         change a feature's properties (length=8 type1=ThroughAll profile=Sketch001)
    delete      delete features (the layer refuses one another feature still uses)
    rename      rename a feature, and every reference to it
    move        move a feature in the Body's order (PartDesign_MoveFeatureInTree)
    tip         set the Body's Tip (PartDesign_MoveTip)
    attach      the Attachment panel's answer for references …
    project     external geometry …
    apply       several ops as one undo step …
    shape       a feature's solid and its base's …
    clone       a new Body whose base is a Clone of another (FreeCAD's PartDesign_Clone)
    …and sketchkernel, mirror, merge, reorient, map, validate, text, resolve
```

(Subcommand names verbatim; some descriptions shortened here.)

`assembly` line ("show, insert, joint, set, ground, solve"):

```
$ cad assembly --help
usage: cad assembly [-h] [--json] <action> ...

a project's Assembly (FreeCAD's Assembly workbench): show, insert, joint, set, ground, move, solve, delete, rename; solved by FreeCAD's OndselSolver; each change one undo step
...
    show      the Assembly's tree, where each component is, the Solver messages
    new       Assembly_CreateAssembly: the ASSEMBLY list in assembly.py
    insert    Assembly_InsertLink: a part of the project as a component
    joint     Assembly_CreateJoint: TYPE and two picks, comp:Element[:Vertex]
    set       change a joint's or a component's properties (distance=12, ...)
    …and reverse, ground, move, solve, delete, rename, apply, jcs, asmt
```

(Subcommand names verbatim; some descriptions shortened here.)

`techdraw` line ("view, section, dimension, balloon, export"): `cad techdraw --help` does not print — it exits 4 while
argparse formats the parent help, because the `set` subcommand's help string holds `format_spec='%.1f'`
(`cad_agent/techdrawcmd.py:383`) and argparse %-formats a subparser's help against a dict
(`TypeError: must be real number, not dict`). The subcommands were read from `add_parsers` (techdrawcmd.py:329-402) and
each one's `--help` run on its own:

```
$ cad techdraw <sub> --help   # usage line, for each subcommand
usage: cad techdraw ls [-h] [--json] slug
usage: cad techdraw show [-h] [--json] [--no-recompute] [--svg] slug page
usage: cad techdraw new [-h] [--json] [--page PAGE] [--template TEMPLATE] slug
usage: cad techdraw view [-h] [--json] [--direction X,Y,Z] [--x-direction X,Y,Z] [--name NAME] slug page PART [PART ...]
usage: cad techdraw projgroup [-h] [--json] [--direction X,Y,Z] [--x-direction X,Y,Z] [--projections TYPES] slug page PART [PART ...]
usage: cad techdraw projection [-h] [--json] [--off] slug page group type
usage: cad techdraw section [-h] [--json] [--direction {Right,Left,Up,Down}] [--origin X,Y,Z] [--symbol SYMBOL] slug page view
usage: cad techdraw dimension [-h] [--json] slug page type VIEW:ELEMENT [VIEW:ELEMENT ...]
usage: cad techdraw balloon [-h] [--json] --origin X,Y [--at X,Y] slug page view
usage: cad techdraw annotation [-h] [--json] [--at X,Y] slug page [LINE ...]
usage: cad techdraw set [-h] [--json] slug page name KEY=VALUE [KEY=VALUE ...]
usage: cad techdraw move [-h] [--json] --at X,Y slug page name
usage: cad techdraw delete [-h] [--json] slug page NAME [NAME ...]
usage: cad techdraw rename [-h] [--json] slug page name to
usage: cad techdraw apply [-h] [--json] --ops JSON [--name NAME] [--dry-run] [--svg] slug page
usage: cad techdraw export [-h] [--json] [--format FORMAT] [--out DIR] slug page
usage: cad techdraw delete-page [-h] [--json] slug page
```

Also run, as asked:

```
usage: cad feature add [-h] [--json] [--after AFTER] slug part type name [KEY=VALUE ...]
usage: cad feature set [-h] [--json] slug part name KEY=VALUE [KEY=VALUE ...]
usage: cad feature clone [-h] [--json] [--name NAME] slug source
```

### Checked in the sources

- Workbenches: `ui/src/chrome.tsx`'s `WORKBENCHES` — agent (CAD Agent), design (Part Design), assembly (Assembly),
  inspection (Inspection), sketcher (Sketcher), part (Part), techdraw (TechDraw).
- File formats: `docs/EDITING_PLAN.md` — `FEATURES` and `OBJECTS` in a part file (lines 22, 67, 74), `ASSEMBLY` in
  `assembly.py` (lines 109, 117), and `techdraw/<Page>.py` under `TechDraw` (line 197).
- One undo step: the three commands' help strings ("each change one undo step" for feature, assembly and techdraw).

### Commit

`docs: the user docs name the freecad-style editing commands`

### Unsure / questions

- `cad techdraw --help`'s crash is in `cad_agent/techdrawcmd.py`, a file outside this lane's edits; logged here, not
  fixed.
