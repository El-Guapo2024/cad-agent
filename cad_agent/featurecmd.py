"""cad feature: a part's PartDesign feature list, edited from the CLI and the workbench alike.

A part made in the app is a part module whose shape is a FEATURES list (cad_agent/feature.py): sketches, pads
and pockets in FreeCAD's order, named and optioned as FreeCAD's objects are. These commands edit that list in
place through the part-file layer (cad_agent/feature_edit.py: `read(path)` and `apply(path, ops)`), which they
reach only through `serve.feature_layer()`, the one seam the tests replace with a fake:

    cad feature list   SLUG [PART]                     the Body's tree: Origin, BaseFeature, features, Tip
    cad feature new    SLUG PART                       a new part module with an empty Body (PartDesign_Body)
    cad feature new    SLUG PART --document            a new part module of Part workbench objects, OBJECTS
    cad feature add    SLUG PART TYPE NAME [k=v ...] [--after NAME]
    cad feature set    SLUG PART NAME k=v ...          FreeCAD's property names in snake_case (length=8)
    cad feature delete SLUG PART NAME ...
    cad feature rename SLUG PART NAME TO
    cad feature move   SLUG PART NAME (--after NAME | --first)
    cad feature tip    SLUG PART NAME                  PartDesign_MoveTip
    cad feature apply  SLUG PART --ops JSON            several ops as one step (what the workbench sends)
    cad feature shape  SLUG PART [--ops JSON] [--feature NAME]   a feature's solid after ops, nothing written
                                                       (cad_agent/feature_shape.py; a dress-up's task panel)

A dress-up's Base is (feature, sub-elements), as FreeCAD's Python writes it: base='["Pad", ["Edge1", "Face6"]]',
or base=Pad:Edge1,Face6 for short (Fillet, Chamfer, Draft, Thickness: cad_agent/feature_dressup.py).

Each change is one step of the shared undo journal (undo.py), named as FreeCAD names the transaction ("Make
Pad", "Edit Pad.Length", "Move tip to selected feature", ...), so `cad undo` and the page's Edit > Undo take it
back. As `cad set` does, a change is built before it stays: a feature list that no longer builds is put back
as it was and the command fails with the build's reason. The one exception is a Body that has nothing to build
yet (no feature but sketches, and no BaseFeature), as a new Body is in FreeCAD before its first Pad.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

from . import state as st
from .cmdbase import (OK, BuildFailed, NotBuilt, Result, UsageError, actor, build, pairs, part,
                      project, verdict, rows_text)

SKETCH = "Sketcher::SketchObject"
# What `cad feature add` takes for TYPE: FreeCAD's short names, or the type itself.
TYPES = {"Sketch": SKETCH, "Pad": "PartDesign::Pad", "Pocket": "PartDesign::Pocket"}
# The transaction FreeCAD opens for each (PartDesign/Gui/Command.cpp's "Make " + which, SketchWorkflow.cpp's
# "New Sketch", CommandBody.cpp, Gui/CommandDoc.cpp's "Delete", Tree.cpp's "Rename <obj>.Label").
ADD_NAMES = {SKETCH: "New Sketch", "PartDesign::Pad": "Make Pad", "PartDesign::Pocket": "Make Pocket"}
# The datums: Part's, which FreeCAD 26.3's Edit > Datums makes (Part/Gui/Command.cpp: "Add datum plane", ...), and
# PartDesign's own (PartDesign/Gui/Command.cpp's UnifiedDatumCommand: "Create " + the default name)
DATUMS = {"DatumPlane": "Part::DatumPlane", "DatumLine": "Part::DatumLine", "DatumPoint": "Part::DatumPoint",
          "LocalCoordinateSystem": "Part::LocalCoordinateSystem", "PartDesignPlane": "PartDesign::Plane",
          "PartDesignLine": "PartDesign::Line", "PartDesignPoint": "PartDesign::Point",
          "PartDesignCoordinateSystem": "PartDesign::CoordinateSystem"}
TYPES.update(DATUMS)


def _kw_types() -> dict:
    """The features feature_kw.py declares (Mirrored, LinearPattern, ..., AdditiveBox, ...): {short name: TypeId} and
    {TypeId: FreeCAD's transaction}. Looked up when a command needs them, so `cad` starts without the kernel."""
    from . import feature_part  # noqa: F401  the Part workbench's objects (Part.Box, ...) register themselves
    from .feature_kw import classes
    cs = classes().values()
    return {c.kind: c.TYPE_ID for c in cs}, {c.TYPE_ID: c.TRANSACTION for c in cs}

TEMPLATE = '''"""{part}: a PartDesign Body made in the workbench (cad feature new).

Its shape is FEATURES, the Body's tree in FreeCAD's order (cad_agent/feature.py). The workbench edits the
lists in place; so can you.
"""
from cad_agent.feature import (ArcOfCircle, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, Body, BSplineCurve,
                               Circle, Constraint, Ellipse, LineSegment, Pad, Pocket, Point, Sketch)

MATERIAL = {material!r}
PROCESS = {process!r}

PARAMS = {{}}

FEATURES = []


def build(**p):
    return Body(FEATURES, p)
'''


def layer():
    """The part-file layer, through serve's seam. Until feature_edit.py is there, the command is not built."""
    from . import serve
    try:
        return serve.feature_layer()
    except ModuleNotFoundError as e:
        raise NotBuilt(f"not built yet: the part-file layer ({e.name}) comes with the feature-list branch") from None


def _camel(key: str) -> str:
    """FreeCAD's property name for a snake_case key: up_to_face -> UpToFace, length2 -> Length2; type1 is the Type
    property (feature_edit.py's dicts keep `type` for the TypeId)."""
    if key == "type1":
        return "Type"
    return "".join(w[:1].upper() + w[1:] for w in key.split("_"))


def _type(text: str) -> str:
    types = {**TYPES, **_kw_types()[0]}
    if text in types:
        return types[text]
    if text in types.values():
        return text
    raise UsageError(f"feature type {text!r}: one of {', '.join(types)} (or {', '.join(types.values())})")


def _read(path: Path) -> dict:
    try:
        return layer().read(path)
    except NotBuilt:
        raise
    except (SyntaxError, ValueError) as e:
        raise BuildFailed(f"{path.stem} does not parse as a feature list: {e}") from e


def _builds_anything(doc: dict) -> bool:
    """Whether the Body has a solid to build: a BaseFeature, or a feature that is not a sketch; or the document a
    Part object (feature_part.py)."""
    return bool(doc.get("base")) or any(f.get("type") not in (SKETCH, *DATUMS.values())
                                         for f in doc.get("features", [])) or \
        any(f.get("type") != SKETCH for f in doc.get("objects") or [])


def _objects_text(part_name: str, doc: dict) -> list[str]:
    """A document's Part objects as FreeCAD's tree has them: the ones nothing uses at the top, each object's inputs
    (claimChildren, feature_part.PartObject.INPUTS) under it."""
    from .feature_kw import kw_class
    objs = {o["name"]: o for o in doc.get("objects") or []}
    kids = {}
    for o in objs.values():
        cls = kw_class(o["type"].replace("::", ".")) if o["type"] != SKETCH else None
        if cls is not None:
            kids[o["name"]] = cls.from_dict(o).inputs()
    used = {k for ks in kids.values() for k in ks}
    lines = [f"{part_name}  (document{', Body' if doc.get('body') else ''})"]

    def row(name, depth):
        o = objs.get(name)
        what = o["type"] if o else "PartDesign::Body" if name == "Body" else "feature of Body"
        label = f" \"{o['label']}\"" if o and o.get("label") else ""
        lines.append(f"{'  ' * depth}{name}{label}  {what}")
        for k in kids.get(name, []):
            row(k, depth + 1)
    if doc.get("body") and "Body" not in used:
        lines.append("  Body  PartDesign::Body")
    for n in objs:
        if n not in used:
            row(n, 1)
    if not objs:
        lines.append("  (no objects)")
    return lines


def _tree_text(part_name: str, doc: dict) -> list[str]:
    if "objects" in doc:
        return _objects_text(part_name, doc) + (["  Body:"] + ["  " + x for x in _body_text(part_name, doc)[1:]]
                                                if doc.get("body") else [])
    return _body_text(part_name, doc)


def _body_text(part_name: str, doc: dict) -> list[str]:
    tip = doc.get("tip")
    lines = [f"{part_name}  (Body{', BaseFeature' if doc.get('base') else ''})"]
    after_tip = False
    for f in doc.get("features", []):
        mark = "  <- Tip" if f["name"] == tip else ""
        extra = f" profile {f['profile']}" if f.get("profile") else \
            f" base {f['base'][0]} {','.join(f['base'][1])}" if isinstance(f.get("base"), list) else ""
        lines.append(f"  {'(' if after_tip else ''}{f['name']}  {f.get('type', '?')}{extra}{')' if after_tip else ''}{mark}")
        if f["name"] == tip:
            after_tip = True
    if not doc.get("features"):
        lines.append("  (no features)")
    return lines


def name_of(ops: list, doc_before: dict) -> str:
    """The undo step's name, as FreeCAD names the transaction."""
    if len(ops) == 1 or (ops and all(o.get("op") == "delete" for o in ops)):
        op = ops[0]
        kind = op.get("op")
        if kind == "add":
            return {**ADD_NAMES, **_kw_types()[1]}.get(op.get("feature", {}).get("type"), "Add feature")
        if kind == "set":
            props = list(op.get("props") or {})
            first = _camel(props[0]) if props else "property"
            return f"Edit {op.get('name')}.{first}" + ("..." if len(props) > 1 else "")
        if kind == "delete":
            return "Delete"
        if kind == "rename":
            return f"Rename {op.get('name')}.Label"
        if kind == "move":
            return "Move a feature inside body"
        if kind == "tip":
            return "Move tip to selected feature"
    adds = [o for o in ops if o.get("op") == "add"]
    if adds:   # a task panel's OK: the feature it made, with the edits that came with it
        return {**ADD_NAMES, **_kw_types()[1]}.get(adds[-1].get("feature", {}).get("type"), "Add feature")
    return "Edit features"


def apply_ops(a, ops: list, cmd: str, step: str | None = None) -> Result:
    """Apply ops to a part's feature list as one undo step, build it, then run its part gates (as `cad set`)."""
    if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and o.get("op") for o in ops):
        raise UsageError('ops is a list of {"op": "add"|"set"|"delete"|"rename"|"move"|"tip", ...}')
    path = part(a.slug, a.part)
    pdir = project(a.slug)
    lay = layer()
    before_doc = _read(path)
    before_text = path.read_text()
    try:
        doc = lay.apply(path, ops)
    except ValueError as e:              # all-or-nothing: the file is as it was
        raise UsageError(str(e)) from None
    rows, built = [], False
    if _builds_anything(doc):
        try:
            build(a.slug, a.part)
            built = True
        except BuildFailed as e:
            path.write_text(before_text)          # a change that breaks the Body does not stay
            raise BuildFailed(f"{e}; {a.part} is as it was") from None
    after_text = path.read_text()
    name = step or name_of(ops, before_doc)
    from . import undo as un
    un.record(pdir, name, cmd, [{"path": path.relative_to(pdir).as_posix(), "before": before_text,
                                 "after": after_text}], by=actor(a))
    code = OK
    if built:
        from .runner import part_check
        r = part_check(a.slug, a.part, {}, cached=True)     # the next `cad scene` finds it in the cache
        rows = r["rows"]
        code = verdict(x["state"] for x in rows)
    lines = [f"{a.slug}/{a.part}: {name}"] + _tree_text(a.part, doc)[1:]
    if not built:
        lines.append("  nothing to build yet: " + ("the document has no object" if "objects" in doc else
                                                  "the Body has no Pad and no BaseFeature"))
    lines += rows_text(rows, False)
    _attached(a.slug, a.part, doc)
    data = {"project": a.slug, "part": a.part, "step": name, "doc": doc, "built": built,
            "failing": sum(1 for x in rows if x["state"] == "FAIL"), "file": str(path)}
    return Result(code, data, "\n".join(lines), f"{a.part}: {name}", [str(path)])


def _cmd(a, *words: str) -> str:
    return shlex.join(["cad", "feature", a.feature_cmd, a.slug, a.part, *words])


# ── the commands ─────────────────────────────────────────────────────────────────────────────────

def cmd_feature_list(a) -> Result:
    project(a.slug)
    names = [a.part] if a.part else st.part_names(a.slug)
    if a.part:
        part(a.slug, a.part)
    docs, errors = {}, {}
    for n in names:
        try:
            docs[n] = _read(part(a.slug, n))
        except BuildFailed as e:
            if a.part:
                raise
            errors[n] = str(e)
    lines = []
    for n, doc in docs.items():
        lines += _tree_text(n, doc) if (doc.get("features") or not doc.get("base") or "objects" in doc) \
            else [f"{n}  (hand-written)"]
        _attached(a.slug, n, doc)
    lines += [f"{n}  (does not parse: {e})" for n, e in errors.items()]
    data = {"project": a.slug, "parts": docs, "errors": errors}
    if a.part:
        data = {"project": a.slug, "part": a.part, **docs[a.part]}
    return Result(OK, data, "\n".join(lines) or "no parts", f"features of {a.part or a.slug}")


def _attached(slug: str, name: str, doc: dict) -> None:
    """doc["attached"]: where each sketch and datum sits as the Body attaches it, and each sketch's external
    geometry (feature_attach.body_info), for a Body with something that only the built Body places."""
    from .feature_attach import body_info, needs_body
    if needs_body(doc):
        doc["attached"] = body_info(part(slug, name))


def cmd_feature_new(a) -> Result:
    pdir = project(a.slug)
    if not st_name_ok(a.part):
        raise UsageError(f"part name {a.part!r}: letters, digits and _, not starting with a digit or _")
    path = pdir / "parts" / f"{a.part}.py"
    if path.exists():
        raise UsageError(f"{a.slug} already has a part {a.part!r} ({path})")
    path.parent.mkdir(parents=True, exist_ok=True)
    if getattr(a, "document", False):            # a part of Part workbench objects (feature_edit_part.py)
        from .feature_edit_part import new_document
        path.write_text(new_document(a.part, a.material, a.process))
    else:
        path.write_text(TEMPLATE.format(part=a.part, material=a.material, process=a.process))
    from . import undo as un
    un.record(pdir, "New document" if getattr(a, "document", False) else "Add a Body",
              shlex.join(["cad", "feature", "new", a.slug, a.part] + (["--document"] if getattr(a, "document", False)
                                                                     else [])),
              [{"path": path.relative_to(pdir).as_posix(), "before": None, "after": path.read_text()}],
              by=actor(a))
    try:
        doc = layer().read(path)
    except NotBuilt:
        doc = {"part": a.part, "params": {}, "base": False, "features": [], "tip": None}
    return Result(OK, {"project": a.slug, "part": a.part, "file": str(path), "doc": doc},
                  f"{a.slug}/{a.part}: a new Body, {path}", f"new body {a.part}", [str(path)])


def st_name_ok(name: str) -> bool:
    return name.isidentifier() and not name.startswith("_") and name.isascii()


def _links(props: dict) -> dict:
    """base=Pad:Edge1,Face6 (and neutral_plane=Pad:Face5, pull_direction=Pad:Edge2) as the lists they stand for."""
    for k in ("base", "neutral_plane", "pull_direction"):
        v = props.get(k)
        if isinstance(v, str) and ":" in v:
            obj, _, subs = v.partition(":")
            names = [x for x in subs.split(",") if x]
            props[k] = [obj, names] if k == "base" else [obj, names[0] if names else ""]
    return props


def cmd_feature_add(a) -> Result:
    kind = _type(a.type)
    feature = {"name": a.name, "type": kind, **_links(pairs(a.props, "cad feature add"))}
    words = [a.type, a.name, *a.props] + (["--after", a.after] if a.after else [])
    op = {"op": "add", "feature": feature}
    if a.after:                       # no "after": at the end (feature_edit's apply); "after": None would put it first
        op["after"] = a.after
    return apply_ops(a, [op], _cmd(a, *words))


def cmd_feature_set(a) -> Result:
    props = _links(pairs(a.props, "cad feature set"))
    if not props:
        raise UsageError("say what to change: cad feature set SLUG PART NAME key=value ...")
    return apply_ops(a, [{"op": "set", "name": a.name, "props": props}], _cmd(a, a.name, *a.props))


def cmd_feature_delete(a) -> Result:
    return apply_ops(a, [{"op": "delete", "name": n} for n in a.names], _cmd(a, *a.names))


def cmd_feature_rename(a) -> Result:
    return apply_ops(a, [{"op": "rename", "name": a.name, "to": a.to}], _cmd(a, a.name, a.to))


def cmd_feature_move(a) -> Result:
    if (a.after is None) == (not a.first):
        raise UsageError("say where to: --after NAME, or --first")
    words = [a.name] + (["--first"] if a.first else ["--after", a.after])
    return apply_ops(a, [{"op": "move", "name": a.name, "after": None if a.first else a.after}], _cmd(a, *words))


def cmd_feature_tip(a) -> Result:
    return apply_ops(a, [{"op": "tip", "name": a.name}], _cmd(a, a.name))


def cmd_feature_apply(a) -> Result:
    text = a.ops
    if text.startswith("@"):
        text = Path(text[1:]).read_text()
    try:
        ops = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--ops is JSON: {e}") from None
    words = ["--ops", json.dumps(ops, separators=(",", ":"))] + (["--name", a.name] if a.name else [])
    return apply_ops(a, ops, _cmd(a, *words), a.name)


def cmd_feature_attach(a) -> Result:
    """What FreeCAD's Attachment panel shows for references: their types, the modes that fit and the best one
    (suggestMapModes), and the Placement of the chosen mode, resolved in the Body before --before."""
    from .feature import FeatureError
    from .feature_attach import attach_query
    path = part(a.slug, a.part)
    try:
        offset = json.loads(a.offset) if a.offset else None
        out = attach_query(path, a.support or [], a.engine, a.mode, offset, a.reversed, a.parameter, a.before,
                           a.prefer)
    except (FeatureError, ValueError) as e:
        raise UsageError(str(e)) from None
    refs = ", ".join(".".join(x for x in r if x) for r in out.get("references", []))
    lines = [f"references: {refs or 'none'}"]
    if out.get("types"):
        lines.append(f"types: {', '.join(out['types'])}")
    if out.get("suggestion"):
        sug = out["suggestion"]
        lines.append(f"{sug['message']}: best {sug['best']}; fit: {', '.join(sug['all']) or 'none'}")
    if out.get("placement"):
        pl = out["placement"]
        lines.append(f"{out['mode']}: position {pl['position']}, yaw-pitch-roll {pl['ypr']}")
    if out.get("error"):
        lines.append(f"error: {out['error']}")
    return Result(OK, {"project": a.slug, "part": a.part, **out}, "\n".join(lines), f"attachment in {a.part}")


def cmd_feature_project(a) -> Result:
    """What Sketcher_External adds: references projected onto a sketch as the Body places it."""
    from .feature import FeatureError
    from .feature_attach import project_query
    path = part(a.slug, a.part)
    try:
        out = project_query(path, a.sketch, a.ref or [])
    except (FeatureError, ValueError) as e:
        raise UsageError(str(e)) from None
    lines = [f"{r}: {len(g)} geometr{'y' if len(g) == 1 else 'ies'}" + (f" ({e})" if e else "")
             for r, g, e in zip(a.ref or [], out["external"], out["errors"])]
    return Result(OK, {"project": a.slug, "part": a.part, "sketch": a.sketch, **out}, "\n".join(lines) or "no references",
                  f"external geometry for {a.sketch}")
def cmd_feature_resolve(a) -> Result:
    """A feature's properties as FreeCAD's would hold them, from what a task panel has chosen (read-only, no step)."""
    path = part(a.slug, a.part)
    text = Path(a.feature[1:]).read_text() if a.feature.startswith("@") else a.feature
    try:
        feature = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--feature is JSON: {e}") from None
    fn = getattr(layer(), "resolve_feature", None)
    if fn is None:
        raise NotBuilt("not built yet: the part-file layer has no resolve_feature")
    try:
        out = fn(path, feature, a.through_all)
    except ValueError as e:
        raise UsageError(str(e)) from None
    lines = [f"{a.slug}/{a.part}: {out.get('name')} ({out.get('type')})"]
    lines += [f"  {k} = {v!r}" for k, v in out.items() if k not in ("name", "type", "enums", "read_only")]
    return Result(OK, {"project": a.slug, "part": a.part, "feature": out}, "\n".join(lines),
                  f"{a.part}: {out.get('name')} resolved")


def cmd_sketchkernel(a) -> Result:
    # sketch_kernel imports OCP at its top, so it is loaded when the command runs, not when the parser is built
    from .sketch_kernel import cmd_sketchkernel as run
    return run(a)


def add_parsers(add, sub) -> None:
    """cli.py's build_parser hands its `add` and the subparsers here, so the arguments live with the commands."""
    fp = add("feature", None, "a part's PartDesign feature list (Body, Sketch, Pad, Pocket, Fillet, Chamfer, Draft, Thickness): list, new, add, "
             "set, delete, rename, move, tip; each change one undo step")
    from .cmdbase import Parser
    fsub = fp.add_subparsers(dest="feature_cmd", metavar="<action>", parser_class=Parser)

    def one(name, func, help, part_optional=False):
        sp = add(name, func, help, parent=fsub)
        sp.set_defaults(cmd_name=f"feature {name}", feature_cmd=name)
        sp.add_argument("slug")
        sp.add_argument("part", nargs="?" if part_optional else None)
        return sp

    one("list", cmd_feature_list, "the Body's tree of one part, or of every part", part_optional=True)
    sp = one("new", cmd_feature_new, "a new part module with an empty Body (FreeCAD's Create body)")
    sp.add_argument("--material", default="petg", help="MATERIAL of the new part (default petg)")
    sp.add_argument("--process", default="fdm", help="PROCESS of the new part (default fdm)")
    sp.add_argument("--document", action="store_true", help="a part of Part workbench objects (OBJECTS: Part.Box, "
                    "Part.Cut, ...) instead of a Body")
    sp = one("add", cmd_feature_add, "add a Sketch, Pad, Pocket, Mirrored, LinearPattern, PolarPattern, "
             "MultiTransform, an Additive/Subtractive primitive, Fillet, Chamfer, Draft or Thickness (FreeCAD's "
             "property names in snake_case; a dress-up's base=Pad:Edge1,Face6)")
    sp.add_argument("type", help=", ".join(TYPES) + ", Mirrored, LinearPattern, PolarPattern, MultiTransform, "
                    "AdditiveBox ... SubtractiveWedge, Fillet, Chamfer, Draft, Thickness")
    sp.add_argument("name")
    sp.add_argument("props", nargs="*", metavar="KEY=VALUE")
    sp.add_argument("--after", help="the feature it goes after (default: at the end)")
    sp = one("set", cmd_feature_set, "change a feature's properties (length=8 type1=ThroughAll profile=Sketch001; type1 is the Type property)")
    sp.add_argument("name")
    sp.add_argument("props", nargs="+", metavar="KEY=VALUE")
    sp = one("delete", cmd_feature_delete, "delete features (the layer refuses one another feature still uses)")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp = one("rename", cmd_feature_rename, "rename a feature, and every reference to it")
    sp.add_argument("name")
    sp.add_argument("to")
    sp = one("move", cmd_feature_move, "move a feature in the Body's order (PartDesign_MoveFeatureInTree)")
    sp.add_argument("name")
    sp.add_argument("--after", help="the feature it goes after")
    sp.add_argument("--first", action="store_true", help="to the start of the Body")
    sp = one("tip", cmd_feature_tip, "set the Body's Tip (PartDesign_MoveTip): what comes after it is not built")
    sp.add_argument("name")
    sp = one("attach", cmd_feature_attach, "the Attachment panel's answer for references: their types, FreeCAD's "
             "mode suggestion and the placement (--support Pad.Face6 --mode FlatFace)")
    sp.add_argument("--support", action="append", metavar="OBJ.ELEMENT",
                    help="a reference, as FreeCAD names it (Pad.Face6, XY_Plane, DatumLine); up to four")
    sp.add_argument("--engine", default="Plane", choices=("Plane", "Line", "Point", "3D"),
                    help="AttacherType: Plane (sketch, datum plane), Line, Point, 3D (coordinate system)")
    sp.add_argument("--mode", help="MapMode (default: the best fit)")
    sp.add_argument("--prefer", metavar="MODE", help="the mode to keep if it fits the references (else the best fit)")
    sp.add_argument("--offset", help="AttachmentOffset, JSON: [[x, y, z], [yaw, pitch, roll]]")
    sp.add_argument("--reversed", action="store_true", help="MapReversed (Flip sides)")
    sp.add_argument("--parameter", type=float, default=0.0, help="MapPathParameter (0 to 1 along an edge)")
    sp.add_argument("--before", metavar="FEATURE", help="resolve in the Body before this feature (the one being "
                    "edited); default: all of it")
    sp = one("project", cmd_feature_project, "external geometry: references projected onto a sketch as the Body "
             "places it (Sketcher_External), --ref Pad.Edge3")
    sp.add_argument("sketch")
    sp.add_argument("--ref", action="append", metavar="OBJ.ELEMENT", help="an edge, vertex or face (Pad.Edge3)")
    sp = one("apply", cmd_feature_apply, "several ops as one undo step: --ops '[{\"op\": \"set\", ...}]' "
             "(or --ops @file.json)")
    sp.add_argument("--ops", required=True, metavar="JSON")
    from .feature_shape import add_parser as shape_parser
    shape_parser(add, fsub)
    sp = add("sketchkernel", cmd_sketchkernel, "OCCT's answers for the Sketcher's curve tools (B-spline degree, knots, "
             "conversion, trim of a B-spline, fillet between curves, offset): --req JSON, a list of requests",
             parent=fsub)
    sp.set_defaults(cmd_name="feature sketchkernel", feature_cmd="sketchkernel")
    sp.add_argument("slug", nargs="?")
    sp.add_argument("--req", required=True, metavar="JSON", help="the requests (or @file.json)")
    sp = fsub.choices["apply"]
    sp.add_argument("--name", help="the undo step's name (default: FreeCAD's for the ops, as \"Make Pad\"); a task panel "
                    "that edits a feature says \"Edit Pad\", as FreeCAD's double-click does")
    sp = one("resolve", cmd_feature_resolve, "a feature's every property as FreeCAD's would be, from the ones chosen "
             "(a Hole's diameter from its thread; read-only, writes nothing)")
    sp.add_argument("--feature", required=True, metavar="JSON", help='{"type": "PartDesign::Hole", "profile": ..., ...}')
    sp.add_argument("--through-all", type=float, default=None, help="the Body's through-all length, if known")
