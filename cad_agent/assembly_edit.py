"""The app's and the CLI's edits of a project's Assembly, written back into assembly.py as Python.

read(pdir) gives the Assembly as the tree, the property view and the task panels show it; apply(pdir, ops) runs
the workbench's commands on it (cad_agent/assembly_wb.py has them as FreeCAD's) and writes the result into the
ASSEMBLY list, all or nothing: an entry the edit did not change keeps its text, a changed one is written again, a new
one goes in at its place in the document's order, and every component's placement is the solve's.

The ops:

    {"op": "new"}                                           Assembly_CreateAssembly: the ASSEMBLY list (the file too)
    {"op": "insert", "part": "base", "name"?, "placement"?} Assembly_InsertLink (the first one grounded)
    {"op": "joint", "type": "Revolute", "ref1": [comp, [elt, vtx]], "ref2": ..., "props"?: {...}, "name"?}
                                                            Assembly_CreateJoint<type>, picks and panel values
    {"op": "set", "name": joint, "props": {...}}            properties set (onChanged), then a recompute
    {"op": "edit", "name": joint, "ref1"?, "ref2"?, "props"?, "reverse"?: bool}
                                                            the joint's task panel opened again: new picks
                                                            (setJointConnectors), values, Reverse, then OK
    {"op": "reverse", "name": joint}                        the panel's Reverse button, then OK
    {"op": "ground", "name": comp}                          Assembly_ToggleGrounded
    {"op": "rigid", "parts": [comp, ...], "name"?}          Assembly_CreateJointRigidGroup (a RigidGroupJoint)
    {"op": "update_rigid", "name": group}                   the group's "Update Stored Positions" (while suppressed)
    {"op": "move", "name": comp, "placement": P}            the component's Placement set, then a recompute
    {"op": "drag", "placements": {comp: P}}                 where a drag with the solver left the parts
    {"op": "solve"}                                         Assembly_SolveAssembly
    {"op": "delete", "name": name}                          Std_Delete: a component takes its joints with it
    {"op": "rename", "name": name, "to": new}               an object's Name changed, the references to it too
    {"op": "label", "name": name, "to": label}              Label

P is ((x, y, z), (yaw, pitch, roll)) in degrees, ((x, y, z), (qx, qy, qz, qw)) or {"base", "rotation"}.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from . import assembly_wb as W

FILE = "assembly.py"
LIST = "ASSEMBLY"
PREFIX = "Assembly."
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AssemblyEditError(ValueError):
    pass


# ── reading ───────────────────────────────────────────────────────────────────────────────────────────

def _list_node(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == LIST for t in node.targets):
            if not isinstance(node.value, ast.List):
                raise AssemblyEditError(f"{LIST} is not a list the app can edit")
            return node.value
    return None


def _kind(call) -> str | None:
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "Assembly":
        return f.attr
    return None


def _value(node, src):
    try:
        return ast.literal_eval(node)
    except ValueError:
        raise AssemblyEditError(f"{ast.get_source_segment(src, node)!r} is not a literal the app can read") from None


def entries(src: str):
    """[(object, call node)] of the ASSEMBLY list, or None when the file has none."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise AssemblyEditError(f"assembly.py does not parse: {e}") from None
    lst = _list_node(tree)
    if lst is None:
        return None
    out = []
    for e in lst.elts:
        kind = _kind(e) if isinstance(e, ast.Call) else None
        cls = W.CLASSES.get(kind)
        if cls is None:
            raise AssemblyEditError(f"{LIST} holds {ast.get_source_segment(src, e)[:60]!r}, not an Assembly."
                                    f"{'/'.join(W.CLASSES)} call")
        args = [_value(a, src) for a in e.args]
        kw = {k.arg: _value(k.value, src) for k in e.keywords}
        try:
            out.append((cls(*args, **kw), e))
        except (TypeError, ValueError) as err:
            raise AssemblyEditError(str(err)) from None
    return out


def objects_of(src: str):
    es = entries(src)
    return None if es is None else [o for o, _ in es]


def read_src(src: str, slug: str = "") -> dict:
    objs = objects_of(src)
    if objs is None:
        return {"project": slug, "assembly": False, "objects": [], "tree": []}
    return {"project": slug, "assembly": True, "objects": [W.as_dict(o) for o in objs], "tree": tree(objs)}


def tree(objs) -> list:
    """The tree's rows as FreeCAD shows an Assembly: the Assembly, its Joints group (JointGroup) with the grounded
    joints and joints, then the components."""
    rows = [{"name": "Assembly", "label": "Assembly", "type": "Assembly::AssemblyObject", "depth": 0,
             "icon": "Geoassembly"},
            {"name": "Origin", "label": "Origin", "type": "App::Origin", "depth": 1, "icon": "Std_CoordinateSystem"}]
    # App::Origin's features, labelled as FreeCAD 26.3 labels them (fcassembly.json's tree)
    for name, label, kind in (("X_Axis", "X-axis", "App::Line"), ("Y_Axis", "Y-axis", "App::Line"),
                              ("Z_Axis", "Z-axis", "App::Line"), ("XY_Plane", "XY-plane", "App::Plane"),
                              ("XZ_Plane", "XZ-plane", "App::Plane"), ("YZ_Plane", "YZ-plane", "App::Plane"),
                              ("Origin001", "Origin-Point", "App::Point")):
        rows.append({"name": name, "label": label, "type": kind, "depth": 2, "icon": kind})
    rows.append({"name": "Joints", "label": "Joints", "type": "Assembly::JointGroup", "depth": 1,
                 "icon": "Assembly_JointGroup"})
    for o in objs:
        if isinstance(o, W.GroundedJoint):
            rows.append({"name": o.name, "label": o.label or o.name, "type": "GroundedJoint", "depth": 2,
                         "icon": "Assembly_ToggleGrounded", "object_to_ground": o.object_to_ground})
        elif isinstance(o, W.Joint):
            rows.append({"name": o.name, "label": o.label or o.name, "type": "Joint", "depth": 2,
                         "icon": f"Assembly_CreateJoint{o.joint_type}", "joint_type": o.joint_type,
                         "suppressed": o.suppressed})
        elif isinstance(o, W.RigidGroupJoint):
            rows.append({"name": o.name, "label": o.label or o.name, "type": "RigidGroupJoint", "depth": 2,
                         "icon": "Assembly_CreateJointRigidGroup", "suppressed": o.suppressed,
                         "members": list(o.objects_to_rigid_group)})
    grounded = {o.object_to_ground for o in objs if isinstance(o, W.GroundedJoint)}
    for o in objs:
        if isinstance(o, W.Link):
            rows.append({"name": o.name, "label": o.label or o.name, "type": "App::Link", "depth": 1,
                         "linked_object": o.linked_object, "grounded": o.name in grounded,
                         "icon": "Assembly_AssemblyLink"})
    return rows


def read(pdir) -> dict:
    """The Assembly of a project folder (its assembly.py)."""
    pdir = Path(pdir)
    path = pdir / FILE
    return read_src(path.read_text() if path.exists() else "", pdir.name)


def solved(pdir) -> dict:
    """read(), and the document recomputed: each component's placement, each joint's JCS (Placement1/2 in the
    component's frame, and globally), the solver's document (what the page's solver takes), the Solver messages."""
    from . import ondsel
    pdir = Path(pdir)
    out = read(pdir)
    if not out["assembly"]:
        return out
    doc = W.load(pdir.name, objects_of((pdir / FILE).read_text()))
    if ondsel.available():
        doc.recompute()                     # AssemblyObject::execute: SolveOnRecompute
    out.update(_solved_of(doc))
    return out


def _solved_of(doc) -> dict:
    out = {}
    out["placements"] = {n: W.placement_json(p) for n, p in doc.plc.items()}
    out["jcs"] = {n: {"placement1": W.placement_json(p1), "placement2": W.placement_json(p2),
                      "global1": W.placement_json(doc.global_jcs(doc.get(n), 0)),
                      "global2": W.placement_json(doc.global_jcs(doc.get(n), 1))}
                  for n, (p1, p2) in doc.jcs.items()}
    out["solver"] = doc.solver_doc()
    out["status"] = doc.status() if doc.last else None
    out["messages"] = [{"kind": k, "text": t} for k, t in doc.messages]
    out["dof"] = (doc.last or {}).get("dof")
    return out


# ── writing ───────────────────────────────────────────────────────────────────────────────────────────

def _num(v: float) -> str:
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if v == 0:
        return "0.0"
    if float(v).is_integer() and abs(v) < 1e15:
        return repr(float(v))
    return repr(float(v))


def lit(v) -> str:
    """Python source for a value, every digit kept (a placement is the document's own number)."""
    if v is None or isinstance(v, (bool, int, float)):
        return "None" if v is None else _num(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        inner = ", ".join(lit(x) for x in v)
        if isinstance(v, tuple):
            return f"({inner},)" if len(v) == 1 else f"({inner})"
        return f"[{inner}]"
    raise AssemblyEditError(f"{v!r} cannot be written in assembly.py")


def obj_src(o: W.AsmObject) -> str:
    """An entry's call: its name, its positional properties and the keywords that are not FreeCAD's defaults."""
    keep = set(o.source_props()) if hasattr(o, "source_props") else {k for k in o.DEFAULTS if not o.is_default(k)}
    parts = [json.dumps(o.name)]
    pos_done = True
    for k in o.POS:
        if k not in keep and k != o.POS[0]:
            pos_done = False
        if not pos_done:
            break
        parts.append(lit(o.source_value(k)))
    for k in o.DEFAULTS:
        if k in o.POS[:len(parts) - 1] or k not in keep:
            continue
        parts.append(f"{k}={lit(o.source_value(k))}")
    return f"{PREFIX}{o.kind}({', '.join(parts)})"


def _same(a: W.AsmObject, b: W.AsmObject) -> bool:
    return type(a) is type(b) and W.as_dict(a) == W.as_dict(b)


def write_src(src: str, objects) -> str:
    """src with its ASSEMBLY list holding objects: unchanged entries keep their text."""
    from .feature_edit import _Text
    t = _Text(src)
    lst = _list_node(t.tree)
    if lst is None:
        raise AssemblyEditError("assembly.py has no ASSEMBLY list")
    old = entries(src)
    by_name = {o.name: (o, call) for o, call in old}
    ind = lst.elts[0].col_offset if lst.elts else 4
    lines = []
    for o in objects:
        prev = by_name.get(o.name)
        if prev is not None and _same(prev[0], o):
            text = t.raw[t.a(prev[1]):t.b(prev[1])].decode()
            # a comment after the entry on its line stays with it
            end = t.after_comma(t.b(prev[1]))
            rest = t.raw[end:t.line_end(end)].decode().rstrip("\n")
            comment = rest if rest.strip().startswith("#") else ""
            text = _dedent_continuation(text, prev[1].col_offset)
            lines.append(" " * ind + text.replace("\n", "\n" + " " * ind) + "," + comment)
        else:
            lines.append(" " * ind + obj_src(o) + ",")
    body = "[\n" + "".join(line + "\n" for line in lines) + "]" if lines else "[\n]"
    return t.edit([(t.a(lst), t.b(lst), body)])


def _dedent_continuation(text: str, col: int) -> str:
    out = text.split("\n")
    return "\n".join([out[0]] + [line[col:] if line[:col].strip() == "" else line for line in out[1:]])


TEMPLATE = '''"""{slug}: the assembly, as FreeCAD's Assembly workbench makes it.

ASSEMBLY is the Assembly's document: its components (App::Link to a part of the project) and its JointGroup's joints;
the app and `cad assembly ...` edit it (cad_agent/assembly_edit.py), and parts() is the solved assembly.
"""
from cad_agent import assembly_wb as Assembly

SLUG = {slug_lit}

ASSEMBLY = [
]


def parts():
    return Assembly.parts(SLUG, ASSEMBLY)
'''


def new_src(src: str | None, slug: str) -> str:
    """Assembly_CreateAssembly: a new assembly.py, or ASSEMBLY added to the one the project has. A hand-written
    parts() stays what it was, as placed_parts(), and the new parts() returns its bodies and the Assembly's."""
    if not src:
        return TEMPLATE.format(slug=slug, slug_lit=json.dumps(slug))
    tree = ast.parse(src)
    if _list_node(tree) is not None:
        raise AssemblyEditError("assembly.py already has an Assembly (ASSEMBLY)")
    lines = src.split("\n")
    has_slug = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SLUG" for t in n.targets)
                   for n in tree.body)
    parts_def = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "parts"), None)
    # after the module's imports
    last_import = max([n.end_lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))] or
                      [tree.body[0].end_lineno if tree.body and isinstance(tree.body[0], ast.Expr) else 0])
    head, tail = lines[:last_import], lines[last_import:]
    add = ["from cad_agent import assembly_wb as Assembly"]
    if not has_slug:
        add += ["", f"SLUG = {json.dumps(slug)}"]
    add += ["", "# the Assembly's document (FreeCAD's Assembly workbench): components and joints; cad_agent/assembly_edit.py",
            "ASSEMBLY = [", "]"]
    out = "\n".join(head + add + tail)
    if parts_def is not None:
        out = re.sub(r"^def parts\(\):", "def placed_parts():", out, count=1, flags=re.M)
        out = out.rstrip("\n") + "\n\n\ndef parts():\n    return {**placed_parts(), **Assembly.parts(SLUG, ASSEMBLY)}\n"
    else:
        out = out.rstrip("\n") + "\n\n\ndef parts():\n    return Assembly.parts(SLUG, ASSEMBLY)\n"
    return out


# ── the ops ───────────────────────────────────────────────────────────────────────────────────────────

def _check_name(doc: W.AssemblyDocument, name, what="object"):
    if not (isinstance(name, str) and NAME.match(name)):
        raise AssemblyEditError(f"{name!r} is not a name FreeCAD takes (letters, digits and _)")
    if doc.get(name) is not None or name in ("Assembly", "Joints", doc.origin):
        raise AssemblyEditError(f"there is already an {what} {name!r}")


def _get(doc, name, cls=None, what="object"):
    o = doc.get(name)
    if o is None or (cls is not None and not isinstance(o, cls)):
        raise AssemblyEditError(f"there is no {what} {name!r}")
    return o


def _check_target(doc, r):
    """A reference's moving part is a component, or the Assembly's Origin with one of its features (MakeJointSelGate
    takes an App::Origin's datum elements)."""
    if r[0] == doc.origin:
        if doc.resolve(r) is None:
            raise AssemblyEditError(f"{r[1][0]!r} is not a feature of the Assembly's Origin "
                                    f"({', '.join(n + '.' for n in W.ORIGIN_DATUMS)})")
        return
    _get(doc, r[0], W.Link, "component")


def _ref(v, where):
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        subs = v[1]
        if isinstance(subs, str):
            subs = [subs, subs]
        return (v[0], list(subs))
    raise AssemblyEditError(f"{where}: {v!r} is not [component, [element, vertex]]")


def run_ops(doc: W.AssemblyDocument, ops, slug: str, part_names=None, hand_parts=()) -> list:
    """The ops on the document, in order; returns what each did (for the CLI's lines)."""
    from .state import build_part
    done = []
    for k, op in enumerate(ops):
        if not isinstance(op, dict) or "op" not in op:
            raise AssemblyEditError(f"op {k} is not an edit: {op!r}")
        kind = op["op"]
        if kind == "insert":
            part = op.get("part")
            if part_names is not None and part not in part_names:
                raise AssemblyEditError(f"there is no part {part!r} in the project (parts: {', '.join(part_names)})")
            name = op.get("name")
            if name is not None:
                _check_name(doc, name, "object")
            if name in hand_parts:
                raise AssemblyEditError(f"{name!r} is a body placed_parts() already gives")
            shape = doc.shapes.get(part)
            if shape is None:
                solid, _ = build_part(slug, part)
                shape = solid.wrapped
            link = W.insert_link(doc, part, shape, name=name, placement=op.get("placement"),
                                 ground_first=op.get("ground_first", True))
            doc.recompute()                         # createGroundedJoint: the document recomputed
            done.append(f"inserted {link.name} (App::Link to {part})")
        elif kind == "joint":
            r1, r2 = _ref(op.get("ref1"), "ref1"), _ref(op.get("ref2"), "ref2")
            for r in (r1, r2):
                if r is None:
                    raise AssemblyEditError("a joint needs two references (ref1 and ref2): select 2 elements from "
                                            "2 separate parts")
                _check_target(doc, r)
            if r1[0] == r2[0]:
                raise AssemblyEditError("Select 2 elements from 2 separate parts")
            props = dict(op.get("props") or {})
            bad = set(props) - set(W.Joint.DEFAULTS) - {"reverse"}
            if bad:
                raise AssemblyEditError(f"{', '.join(sorted(bad))} is not a property of a Joint")
            reverse = props.pop("reverse", False)
            name = op.get("name")
            if name is not None:
                _check_name(doc, name, "object")
            try:
                j = W.create_joint(doc, op.get("type"), r1, r2, props, name=name, reverse=reverse)
            except W.AssemblyError as e:
                raise AssemblyEditError(str(e)) from None
            done.append(f"made {j.name} ({j.label}, {j.joint_type})")
        elif kind == "set":
            o = _get(doc, op.get("name"))
            props = dict(op.get("props") or {})
            if isinstance(o, W.Link):
                for key, v in props.items():
                    if key == "placement":
                        doc.plc[o.name] = W.to_placement(v)
                    elif key in ("label", "visibility"):
                        setattr(o, key, v)
                    else:
                        raise AssemblyEditError(f"{key} is not a property the app sets on an App::Link")
                doc.recompute()
            elif isinstance(o, W.Joint):
                for key, v in props.items():
                    if key not in W.Joint.DEFAULTS:
                        raise AssemblyEditError(f"{key} is not a property of a Joint")
                    if key == "joint_type":
                        o.label = W.rename_label(o.label or o.name, v, set(doc.labels()) - {o.label})
                    if key in ("reference1", "reference2"):
                        v = _ref(v, key)
                    try:
                        doc.set(o, key, v)
                    except (W.AssemblyError, ValueError) as e:
                        raise AssemblyEditError(str(e)) from None
                doc.recompute()
            elif isinstance(o, W.RigidGroupJoint):
                for key, v in props.items():
                    if key == "objects_to_rigid_group":
                        for n in (v or ()):
                            _get(doc, n, W.Link, "component")
                    try:
                        W.set_rigid(doc, o, key, v)
                    except (W.AssemblyError, ValueError) as e:
                        raise AssemblyEditError(str(e)) from None
                doc.recompute()
            else:
                for key, v in props.items():
                    if key != "label":
                        raise AssemblyEditError(f"{key} is not a property the app sets on a GroundedJoint")
                    o.label = v
            done.append(f"set {o.name}: {', '.join(props)}")
        elif kind == "edit":
            j = _get(doc, op.get("name"), W.Joint, "joint")
            if "ref1" in op or "ref2" in op:
                r1 = _ref(op.get("ref1", j.reference1), "ref1")
                r2 = _ref(op.get("ref2", j.reference2), "ref2")
                doc.set_joint_connectors(j, [r1])
                doc.set_joint_connectors(j, [r1, r2])
            for key, v in (op.get("props") or {}).items():
                doc.set(j, key, v)
            if op.get("reverse"):
                doc.flip_one_part(j)
            doc.accept(j)
            done.append(f"edited {j.name}")
        elif kind == "reverse":
            j = _get(doc, op.get("name"), W.Joint, "joint")
            doc.flip_one_part(j)
            doc.accept(j)
            done.append(f"reversed {j.name}")
        elif kind == "ground":
            c = _get(doc, op.get("name"), W.Link, "component")
            g = W.toggle_grounded(doc, c.name)
            doc.recompute()
            done.append(f"grounded {c.name}" if g else f"{c.name} no longer grounded")
        elif kind == "rigid":
            parts = list(op.get("parts") or [])
            for n in parts:
                _get(doc, n, W.Link, "component")
            name = op.get("name")
            if name is not None:
                _check_name(doc, name, "object")
            g = W.create_rigid_group(doc, parts, name=name)
            if g is None:
                raise AssemblyEditError("Select at least 2 components to create a rigid group")
            done.append(f"made {g.name} ({', '.join(g.objects_to_rigid_group)})")
        elif kind == "update_rigid":
            g = _get(doc, op.get("name"), W.RigidGroupJoint, "rigid group")
            if not W.update_stored_positions(doc, g):
                raise AssemblyEditError(doc.messages[-1][1])
            doc.recompute()
            done.append(f"stored the positions of {g.name}")
        elif kind == "move":
            c = _get(doc, op.get("name"), W.Link, "component")
            if c.name in doc.grounded():
                raise AssemblyEditError(f"{c.name} is grounded: its Placement is read-only")
            doc.plc[c.name] = W.to_placement(op.get("placement"))
            doc.recompute()
            done.append(f"moved {c.name}")
        elif kind == "drag":
            for n, p in (op.get("placements") or {}).items():
                _get(doc, n, W.Link, "component")
                doc.plc[n] = W.to_placement(p)
            done.append("dragged " + ", ".join(op.get("placements") or {}))
        elif kind == "solve":
            out = doc.solve(True)
            done.append(f"solved: {W.solver_message(out, len(doc.components()))['text'].strip()}")
        elif kind == "delete":
            o = _get(doc, op.get("name"))
            gone = [o]
            if isinstance(o, W.Link):
                gone += [x for x in doc.objects if isinstance(x, (W.Joint, W.GroundedJoint)) and o.name in x.references()]
            for x in gone:
                doc.objects.remove(x)
                doc.jcs.pop(x.name, None)
                doc.plc.pop(x.name, None)
            names_gone = {x.name for x in gone}
            for g in doc.rigid_groups():           # a deleted component leaves the PropertyLinkList
                g.objects_to_rigid_group = tuple(n for n in g.objects_to_rigid_group if n not in names_gone)
            doc.recompute()
            done.append("deleted " + ", ".join(x.name for x in gone))
        elif kind == "rename":
            o = _get(doc, op.get("name"))
            to = op.get("to")
            _check_name(doc, to)
            old = o.name
            o.name = to
            for x in doc.objects:
                if isinstance(x, W.GroundedJoint) and x.object_to_ground == old:
                    x.object_to_ground = to
                if isinstance(x, W.RigidGroupJoint):
                    x.objects_to_rigid_group = tuple(to if n == old else n for n in x.objects_to_rigid_group)
                if isinstance(x, W.Joint):
                    for key in ("reference1", "reference2"):
                        r = getattr(x, key)
                        if r and r[0] == old:
                            setattr(x, key, (to, r[1]))
            if old in doc.plc:
                doc.plc[to] = doc.plc.pop(old)
            if old in doc.jcs:
                doc.jcs[to] = doc.jcs.pop(old)
            done.append(f"renamed {old} to {to}")
        elif kind == "label":
            o = _get(doc, op.get("name"))
            o.label = op.get("to") or None
            done.append(f"labelled {o.name} {o.label!r}")
        else:
            raise AssemblyEditError(f"{kind!r} is not an assembly edit (new, insert, joint, set, edit, reverse, "
                                    "ground, rigid, update_rigid, move, drag, solve, delete, rename, label)")
    return done


def apply(pdir, ops, write: bool = True) -> dict:
    """The ops applied to the project's assembly.py, all or nothing; returns solved() of the result and "done".
    With write False nothing is written: the result is the document the ops would leave (a panel's preview)."""
    from . import state
    pdir = Path(pdir)
    path = pdir / FILE
    slug = pdir.name
    src = path.read_text() if path.exists() else None
    ops = list(ops)
    new = src
    if ops and ops[0].get("op") == "new":
        new = new_src(src, slug)
        ops = ops[1:]
    elif new is None or _list_node(ast.parse(new)) is None:
        if any(op.get("op") == "insert" for op in ops):
            new = new_src(src, slug)                        # the first insert makes the Assembly
        else:
            raise AssemblyEditError(f"{slug} has no Assembly yet: insert a component first (cad assembly insert)")
    objs = objects_of(new)
    parts_dir = pdir / "parts"
    part_names = sorted(p.stem for p in parts_dir.glob("*.py")) if parts_dir.is_dir() else []
    doc = W.load(slug, objs)
    done = run_ops(doc, ops, slug, part_names)
    doc.write_back()
    new = write_src(new, doc.objects)
    if not write:
        out = read_src(new, slug)
        out.update(_solved_of(doc))
        out["done"] = done
        return out
    if new != src:
        state.write_atomic(path, new)
    out = solved(pdir) if objects_of(new) else read(pdir)
    out["done"] = done
    return out
