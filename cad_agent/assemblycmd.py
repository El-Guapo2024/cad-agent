"""cad assembly: a project's Assembly (FreeCAD's Assembly workbench), edited from the CLI and the workbench alike.

The Assembly is the ASSEMBLY list of the project's assembly.py (docs/EDITING_PLAN.md, "Assembly in a part file"):
App::Link components and the JointGroup's joints, solved by FreeCAD's own solver (OndselSolver, ui/ondsel). These
commands edit it through cad_agent/assembly_edit.py, each change one step of the undo journal named as FreeCAD names
the transaction:

    cad assembly show    SLUG                              the tree, each component's placement, the solver's message
    cad assembly new     SLUG                              Assembly_CreateAssembly ("New assembly")
    cad assembly insert  SLUG PART [--name N] [--at X,Y,Z] [--no-ground]
                                                           Assembly_InsertLink ("Insert Component")
    cad assembly joint   SLUG TYPE COMP:ELEMENT[:VERTEX] COMP:ELEMENT[:VERTEX] [KEY=VALUE ...] [--reverse]
                                                           Assembly_CreateJoint<TYPE> ("Create <Type> Joint")
    cad assembly set     SLUG NAME KEY=VALUE ...           a joint's or a component's properties
    cad assembly reverse SLUG JOINT                        the joint panel's Reverse
    cad assembly ground  SLUG COMP                         Assembly_ToggleGrounded ("Toggle grounded")
    cad assembly rigid   SLUG COMP COMP ... [--name N]     Assembly_CreateJointRigidGroup ("Create Rigid Group")
    cad assembly update-rigid SLUG GROUP                   a suppressed rigid group's "Update Stored Positions"
    cad assembly move    SLUG COMP --at X,Y,Z [--ypr Y,P,R]   a component's Placement, then a recompute
    cad assembly solve   SLUG                              Assembly_SolveAssembly
    cad assembly delete  SLUG NAME ...                     Std_Delete (a component's joints go with it)
    cad assembly rename  SLUG NAME TO
    cad assembly apply   SLUG --ops JSON                   several ops as one step (what the workbench sends)
    cad assembly jcs     SLUG COMP ELEMENT [--vertex V | --at X,Y,Z] [--type T]
                                                           where a pick puts the JCS (nothing written)
    cad assembly asmt    SLUG [--out FILE]                 exportAsASMT: the system given to the solver

TYPE is one of Fixed, Revolute, Cylindrical, Slider, Ball, Distance, Parallel, Perpendicular, Angle, RackPinion,
Screw, Gears, Belt. A reference is the component, the element and the vertex FreeCAD keeps with it: arm:Face3:Edge2
(Face3 at the centre of its own Edge2), arm:Face3:Vertex4, arm:Face3 (the face's centre), arm:Vertex7. Properties are
FreeCAD's in snake_case: distance=5 angle=30 offset2='[[0,0,3],[90,0,0]]' enable_length_min=true length_min=2.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

from . import state as st
from .cmdbase import OK, Result, UsageError, actor, pairs, project

KEYS = {"distance", "distance2", "angle", "offset1", "offset2", "detach1", "detach2", "enable_length_min",
        "enable_length_max", "enable_angle_min", "enable_angle_max", "length_min", "length_max", "angle_min",
        "angle_max", "suppressed", "label", "joint_type", "placement", "reference1", "reference2", "visibility",
        "objects_to_rigid_group"}


def _ref(text: str):
    """COMP:ELEMENT[:VERTEX] as FreeCAD's (component, [element, vertex])."""
    bits = text.split(":")
    if len(bits) == 2 and bits[0] == "Origin" and not bits[1].endswith("."):
        bits[1] += "."                         # a feature of the Assembly's Origin: "XY_Plane." as a pick names it
    if len(bits) == 2:
        return [bits[0], [bits[1], bits[1]]]
    if len(bits) == 3:
        return [bits[0], [bits[1], bits[2]]]
    raise UsageError(f"{text!r} is not COMP:ELEMENT or COMP:ELEMENT:VERTEX (arm:Face3:Edge2)")


def _triple(text: str, what: str):
    try:
        v = [float(x) for x in text.split(",")]
    except ValueError:
        v = []
    if len(v) != 3:
        raise UsageError(f"{what} takes X,Y,Z, got {text!r}")
    return v


def step_name(ops: list, before: dict) -> str:
    """The undo step's name, as FreeCAD names the transaction."""
    real = [o for o in ops if o.get("op") != "new"]
    if not real:
        return "New assembly"
    op = real[-1]
    kind = op.get("op")
    if kind == "insert":
        return "Insert Component"
    if kind == "joint":
        return f"Create {op.get('type')} Joint"
    if kind in ("edit", "reverse"):
        label = next((o.get("label") or o["name"] for o in before.get("objects", []) if o["name"] == op.get("name")),
                     op.get("name"))
        return f"Edit {label} Joint"
    if kind == "ground":
        return "Toggle grounded"
    if kind == "rigid":
        return "Create Rigid Group"
    if kind == "update_rigid":
        return "Update Stored Positions"
    if kind in ("move", "drag"):
        return "Move part"
    if kind == "solve":
        return "Solve Assembly"
    if kind == "delete":
        return "Delete"
    if kind in ("rename", "label"):
        return f"Rename {op.get('name')}.Label"
    if kind == "set":
        props = list(op.get("props") or {})
        first = "".join(w.capitalize() for w in props[0].split("_")) if props else "property"
        return f"Edit {op.get('name')}.{first}" + ("..." if len(props) > 1 else "")
    return "Edit assembly"


def _status_lines(doc: dict) -> list[str]:
    lines = []
    for row in doc.get("tree", []):
        ind = "  " * (row["depth"] + 1)
        extra = ""
        if row["type"] == "App::Link":
            p = (doc.get("placements") or {}).get(row["name"])
            at = "" if p is None else "  at (" + ", ".join(f"{c:.6g}" for c in p["base"]) + ")"
            extra = f"  -> parts/{row['linked_object']}.py" + (" (grounded)" if row.get("grounded") else "") + at
        elif row["type"] == "Joint":
            extra = f"  {row['joint_type']}" + (" (suppressed)" if row.get("suppressed") else "")
        elif row["type"] == "GroundedJoint":
            extra = f"  grounds {row['object_to_ground']}"
        elif row["type"] == "RigidGroupJoint":
            extra = f"  rigid: {', '.join(row.get('members') or [])}" + (" (suppressed)" if row.get("suppressed") else "")
        label = row["label"] if row["label"] == row["name"] else f"{row['label']} ({row['name']})"
        lines.append(f"{ind}{label}{extra}")
    s = doc.get("status")
    if s:
        lines.append(f"  Solver messages: {s['text']}{s['link']}")
    for m in doc.get("messages", []):
        lines.append(f"  {m['kind']}: {m['text']}")
    return lines


def apply_ops(a, ops: list, cmd: str, step: str | None = None) -> Result:
    from . import assembly_edit as E
    if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and o.get("op") for o in ops):
        raise UsageError('ops is a list of {"op": "insert"|"joint"|"set"|"ground"|"move"|"solve"|"delete"|..., ...}')
    pdir = project(a.slug)
    path = pdir / E.FILE
    before_text = path.read_text() if path.exists() else None
    before = E.read(pdir)
    try:
        doc = E.apply(pdir, ops)
    except (ValueError, KeyError) as e:          # all or nothing: the file is as it was
        raise UsageError(str(e)) from None
    except Exception as e:
        if before_text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(before_text)
        raise UsageError(f"the assembly did not build: {st.why(e)}") from None
    after_text = path.read_text() if path.exists() else None
    name = step or step_name(ops, before)
    from . import undo as un
    un.record(pdir, name, cmd, [{"path": E.FILE, "before": before_text, "after": after_text}], by=actor(a))
    lines = [f"{a.slug}: {name}"] + [f"  {d}" for d in doc.get("done", [])] + _status_lines(doc)
    data = {"project": a.slug, "step": name, "doc": doc, "file": str(path)}
    return Result(OK, data, "\n".join(lines), f"{a.slug}: {name}", [str(path)])


def _cmd(a, *words: str) -> str:
    return shlex.join(["cad", "assembly", a.assembly_cmd, a.slug, *words])


# ── the commands ─────────────────────────────────────────────────────────────────────────────────

def cmd_show(a) -> Result:
    from . import assembly_edit as E
    pdir = project(a.slug)
    try:
        doc = E.solved(pdir)
    except Exception as e:
        raise UsageError(f"the assembly did not build: {st.why(e)}") from None
    if not doc["assembly"]:
        text = f"{a.slug}: no Assembly (cad assembly insert {a.slug} PART makes one)"
    else:
        text = "\n".join([f"{a.slug}: Assembly"] + _status_lines(doc))
    return Result(OK, doc, text, f"{a.slug}: Assembly")


def cmd_new(a) -> Result:
    return apply_ops(a, [{"op": "new"}], _cmd(a))


def cmd_insert(a) -> Result:
    op = {"op": "insert", "part": a.part}
    if a.name:
        op["name"] = a.name
    if a.at:
        op["placement"] = [_triple(a.at, "--at"), [0.0, 0.0, 0.0]]
    if a.no_ground:
        op["ground_first"] = False
    words = [a.part] + (["--name", a.name] if a.name else []) + (["--at", a.at] if a.at else []) + \
        (["--no-ground"] if a.no_ground else [])
    return apply_ops(a, [op], _cmd(a, *words))


def _props(items) -> dict:
    props = pairs(items, "cad assembly")
    bad = set(props) - KEYS
    if bad:
        raise UsageError(f"{', '.join(sorted(bad))} is not a property the Assembly's objects have "
                         f"({', '.join(sorted(KEYS))})")
    return props


def cmd_joint(a) -> Result:
    op = {"op": "joint", "type": a.type, "ref1": _ref(a.ref1), "ref2": _ref(a.ref2), "props": _props(a.props)}
    if a.name:
        op["name"] = a.name
    if a.reverse:
        op["props"]["reverse"] = True
    words = [a.type, a.ref1, a.ref2, *a.props] + (["--name", a.name] if a.name else []) + \
        (["--reverse"] if a.reverse else [])
    return apply_ops(a, [op], _cmd(a, *words))


def cmd_set(a) -> Result:
    props = _props(a.props)
    if not props:
        raise UsageError("say what to change: cad assembly set SLUG NAME key=value ...")
    return apply_ops(a, [{"op": "set", "name": a.name, "props": props}], _cmd(a, a.name, *a.props))


def cmd_reverse(a) -> Result:
    return apply_ops(a, [{"op": "reverse", "name": a.name}], _cmd(a, a.name))


def cmd_ground(a) -> Result:
    return apply_ops(a, [{"op": "ground", "name": a.name}], _cmd(a, a.name))


def cmd_rigid(a) -> Result:
    op = {"op": "rigid", "parts": list(a.parts)}
    if a.name:
        op["name"] = a.name
    return apply_ops(a, [op], _cmd(a, *a.parts, *(["--name", a.name] if a.name else [])))


def cmd_update_rigid(a) -> Result:
    return apply_ops(a, [{"op": "update_rigid", "name": a.name}], _cmd(a, a.name))


def cmd_move(a) -> Result:
    ypr = _triple(a.ypr, "--ypr") if a.ypr else [0.0, 0.0, 0.0]
    words = [a.name, "--at", a.at] + (["--ypr", a.ypr] if a.ypr else [])
    return apply_ops(a, [{"op": "move", "name": a.name, "placement": [_triple(a.at, "--at"), ypr]}],
                     _cmd(a, *words))


def cmd_solve(a) -> Result:
    return apply_ops(a, [{"op": "solve"}], _cmd(a))


def cmd_delete(a) -> Result:
    return apply_ops(a, [{"op": "delete", "name": n} for n in a.names], _cmd(a, *a.names))


def cmd_rename(a) -> Result:
    return apply_ops(a, [{"op": "rename", "name": a.name, "to": a.to}], _cmd(a, a.name, a.to))


def cmd_dry_run(a, ops) -> Result:
    """The ops' result, nothing written and no undo step: a task panel's preview before OK."""
    from . import assembly_edit as E
    pdir = project(a.slug)
    try:
        doc = E.apply(pdir, ops, write=False)
    except (ValueError, KeyError) as e:
        raise UsageError(str(e)) from None
    except Exception as e:
        raise UsageError(f"the assembly did not build: {st.why(e)}") from None
    return Result(OK, {"project": a.slug, "doc": doc, "dry_run": True}, "\n".join(_status_lines(doc)), f"{a.slug}: preview")


def cmd_apply(a) -> Result:
    text = a.ops
    if text.startswith("@"):
        text = Path(text[1:]).read_text()
    try:
        ops = json.loads(text)
    except ValueError as e:
        raise UsageError(f"--ops is JSON: {e}") from None
    if getattr(a, "dry_run", False):
        return cmd_dry_run(a, ops)
    words = ["--ops", json.dumps(ops, separators=(",", ":"))] + (["--name", a.name] if a.name else [])
    return apply_ops(a, ops, _cmd(a, *words), a.name)


def cmd_jcs(a) -> Result:
    """Where a pick puts a joint's coordinate system: TaskAssemblyCreateJoint's preview (findElementClosestVertex
    for the point under the cursor, then findPlacement), in the component's frame and globally."""
    from . import assembly_edit as E
    from . import assembly_jcs as J
    from . import assembly_wb as W
    pdir = project(a.slug)
    objs = E.objects_of((pdir / E.FILE).read_text()) if (pdir / E.FILE).exists() else None
    if not objs:
        raise UsageError(f"{a.slug} has no Assembly")
    if a.comp == "Origin":
        # a feature of the Assembly's Origin: the whole-part JCS, at the datum's placement
        name = a.element.rstrip(".")
        if name not in W.ORIGIN_DATUMS:
            raise UsageError(f"{a.element!r} is not a feature of the Assembly's Origin ({', '.join(W.ORIGIN_DATUMS)})")
        sub = name + "."
        doc = W.AssemblyDocument([], {})
        joint = W.Joint("Joint", a.type)
        r = doc.resolve(("Origin", (sub, sub)))
        jcs = doc.raw_jcs(joint, ("Origin", (sub, sub)))
        g = r.obj * jcs
        data = {"component": "Origin", "subs": [sub, sub], "placement": W.placement_json(jcs),
                "global": W.placement_json(g), "geom": "", "radius": 0.0}
        return Result(OK, data, f"Origin.{sub}: JCS at (0, 0, 0)", f"Origin.{sub}")
    link = next((o for o in objs if isinstance(o, W.Link) and o.name == a.comp), None)
    if link is None:
        raise UsageError(f"there is no component {a.comp!r}")
    solid, _ = st.build_part(a.slug, link.linked_object)
    shape = solid.wrapped
    plc = W.to_placement(link.placement)
    if a.vertex:
        vertex = a.vertex
    else:
        # the picked point; without one, a click at the element's centre of gravity
        at = _triple(a.at, "--at") if a.at else J.center_of_gravity(J.sub_shape(J.placed(shape, plc), a.element))
        vertex = J.find_element_closest_vertex(shape, plc, a.element, at)
    jcs = J.find_placement(shape, plc, [a.element, vertex], a.type == "Distance")
    g = plc * jcs
    data = {"component": a.comp, "subs": [a.element, vertex], "placement": W.placement_json(jcs),
            "global": W.placement_json(g), **J.element_geometry(shape, a.element)}
    text = (f"{a.comp}.{a.element} at {vertex}: JCS at (" + ", ".join(f"{c:.6g}" for c in g.pos) + "), z " +
            "(" + ", ".join(f"{c:.6g}" for c in g.rot.mult_vec((0, 0, 1))) + ")")
    return Result(OK, data, text, text)


def cmd_asmt(a) -> Result:
    from . import assembly_edit as E
    from . import assembly_wb as W
    pdir = project(a.slug)
    objs = E.objects_of((pdir / E.FILE).read_text()) if (pdir / E.FILE).exists() else None
    if not objs:
        raise UsageError(f"{a.slug} has no Assembly")
    text = W.load(a.slug, objs).export_asmt()
    files = []
    if a.out:
        Path(a.out).write_text(text)
        files = [a.out]
    return Result(OK, {"asmt": text}, text if not a.out else f"wrote {a.out}", "exportAsASMT", files)


def add_parsers(add, sub) -> None:
    """cli.py's build_parser hands its `add` and the subparsers here, so the arguments live with the commands."""
    ap = add("assembly", None, "a project's Assembly (FreeCAD's Assembly workbench): show, insert, joint, set, ground, "
             "move, solve, delete, rename; solved by FreeCAD's OndselSolver; each change one undo step")
    from .cmdbase import Parser
    asub = ap.add_subparsers(dest="assembly_cmd", metavar="<action>", parser_class=Parser)

    def one(name, func, help):
        sp = add(name, func, help, parent=asub)
        sp.set_defaults(cmd_name=f"assembly {name}", assembly_cmd=name)
        sp.add_argument("slug")
        return sp

    one("show", cmd_show, "the Assembly's tree, where each component is, the Solver messages")
    one("new", cmd_new, "Assembly_CreateAssembly: the ASSEMBLY list in assembly.py (made by the first insert too)")
    sp = one("insert", cmd_insert, "Assembly_InsertLink: a part of the project as a component (the first grounded)")
    sp.add_argument("part")
    sp.add_argument("--name", help="the component's Name (default: the part's, made unique)")
    sp.add_argument("--at", metavar="X,Y,Z", help="where it goes, mm")
    sp.add_argument("--no-ground", action="store_true", help="do not ground the first component (GroundFirstPart No)")
    sp = one("joint", cmd_joint, "Assembly_CreateJoint: TYPE and two picks, comp:Element[:Vertex] (arm:Face3:Edge2)")
    sp.add_argument("type", help="Fixed, Revolute, Cylindrical, Slider, Ball, Distance, Parallel, Perpendicular, "
                    "Angle, RackPinion, Screw, Gears, Belt")
    sp.add_argument("ref1", metavar="COMP:ELEMENT[:VERTEX]")
    sp.add_argument("ref2", metavar="COMP:ELEMENT[:VERTEX]")
    sp.add_argument("props", nargs="*", metavar="KEY=VALUE", help="distance=5 angle=30 offset2='[[0,0,3],[90,0,0]]'")
    sp.add_argument("--name", help="the joint's Name (default Joint, Joint001, ...)")
    sp.add_argument("--reverse", action="store_true", help="the panel's Reverse button before OK")
    sp = one("set", cmd_set, "change a joint's or a component's properties (distance=12, placement=..., suppressed=true)")
    sp.add_argument("name")
    sp.add_argument("props", nargs="+", metavar="KEY=VALUE")
    sp = one("reverse", cmd_reverse, "the joint panel's Reverse: the moving part flipped onto the other side")
    sp.add_argument("name")
    sp = one("ground", cmd_ground, "Assembly_ToggleGrounded")
    sp.add_argument("name")
    sp = one("rigid", cmd_rigid, "Assembly_CreateJointRigidGroup: lock two or more components together")
    sp.add_argument("parts", nargs="+", metavar="COMP")
    sp.add_argument("--name", help="the group's Name (default RigidGroupJoint, RigidGroupJoint001, ...)")
    sp = one("update-rigid", cmd_update_rigid, "a suppressed rigid group's Update Stored Positions")
    sp.add_argument("name")
    sp = one("move", cmd_move, "set a component's Placement, then recompute (the solver pulls it back to its joints)")
    sp.add_argument("name")
    sp.add_argument("--at", required=True, metavar="X,Y,Z")
    sp.add_argument("--ypr", metavar="YAW,PITCH,ROLL", help="degrees")
    one("solve", cmd_solve, "Assembly_SolveAssembly")
    sp = one("delete", cmd_delete, "delete objects (a component takes its joints and GroundedJoint with it)")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp = one("rename", cmd_rename, "rename an object, and the references to it")
    sp.add_argument("name")
    sp.add_argument("to")
    sp = one("apply", cmd_apply, "several ops as one undo step: --ops '[{\"op\": \"joint\", ...}]' (or --ops @file.json)")
    sp.add_argument("--ops", required=True, metavar="JSON")
    sp.add_argument("--name", help="the undo step's name (default: FreeCAD's transaction's)")
    sp.add_argument("--dry-run", action="store_true", help="the result of the ops, nothing written (a panel's preview)")
    sp = one("jcs", cmd_jcs, "where a pick puts the joint coordinate system (TaskAssemblyCreateJoint's preview)")
    sp.add_argument("comp")
    sp.add_argument("element", help="Face3, Edge2, Vertex4")
    sp.add_argument("--vertex", help="the vertex sub-name (Vertex4, Edge2 of the face, or the element itself)")
    sp.add_argument("--at", metavar="X,Y,Z", help="the picked point: the nearest vertex or centre is taken, as FreeCAD does "
                    "(default: the element's centre)")
    sp.add_argument("--type", default="Fixed", help="the joint's type (Distance ignores the vertex)")
    sp = one("asmt", cmd_asmt, "exportAsASMT: the system the solver is given, in OndselSolver's format")
    sp.add_argument("--out", metavar="FILE")
