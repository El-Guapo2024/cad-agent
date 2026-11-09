# SPDX-License-Identifier: LGPL-2.1-or-later
"""Editing a part file's FEM list, as the FEM workbench's task panels add and change an analysis's objects.

read_src(src) gives the list as plain data; apply_src(src, ops) changes it, all or nothing:

    {"op": "add", "kind": "ConstraintFixed", "name": "Fixed", "props": {"references": [["Box", "Face1"]]}}
    {"op": "set", "name": "Fixed", "props": {"references": [["Box", "Face2"]]}}
    {"op": "delete", "name": "Fixed"}

Only the entries an op touches are rewritten, so the file's other lines and comments stay as they are. Each entry is
checked by the class that will build it (feature_fem.py), so a list this writes is one `cad fem run` can read.
"""
from __future__ import annotations

import ast
import json

from . import feature_edit as E
from . import feature_edit_part as P
from . import feature_fem as Fem


def _top(tree):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FEM" for t in n.targets):
            return n
    return None


def _kind(call):
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "Fem" and f.attr in Fem.KINDS:
        return f.attr
    return None


def _entries(tree):
    """(the FEM list node or None, [(name, kind, call)])."""
    node = _top(tree)
    if node is None:
        return None, []
    if not isinstance(node.value, ast.List):
        raise Fem.FemError("FEM is not a list the app can edit")
    out = []
    for e in node.value.elts:
        kind = _kind(e) if isinstance(e, ast.Call) else None
        name = e.args[0] if kind and e.args else None
        if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
            raise Fem.FemError(f"FEM holds {ast.unparse(e)[:60]!r}, not a Fem object that starts with its name")
        out.append((name.value, kind, e))
    return node.value, out


def _props(kind, call):
    cls = Fem.KINDS[kind]
    try:
        given = {k: ast.literal_eval(v) for k, v in zip(cls.POS, call.args[1:])}
        given.update({k.arg: ast.literal_eval(k.value) for k in call.keywords})
    except ValueError:
        raise Fem.FemError(f"{ast.unparse(call)[:60]!r} holds an expression the app cannot edit") from None
    return given


def read_src(src: str) -> list[dict]:
    """The FEM list as written: each entry's name, kind, and every property with FreeCAD's default where left out."""
    out = []
    for name, kind, call in _entries(ast.parse(src))[1]:
        out.append({"name": name, "kind": kind, **Fem.KINDS[kind].DEFAULTS, **_props(kind, call)})
    return out


def _pairs(v):
    return [tuple(r) for r in v or ()]


def _normal(cls, props):
    """props as the part file writes them: references as (object, element) tuples, a direction as one tuple."""
    out = dict(props)
    if "references" in out:
        out["references"] = _pairs(out["references"])
    if out.get("direction"):
        out["direction"] = tuple(out["direction"])
    return out


def _lit(v):
    if isinstance(v, tuple):
        return "(" + ", ".join(_lit(x) for x in v) + ("," if len(v) == 1 else "") + ")"
    if isinstance(v, list):
        return "[" + ", ".join(_lit(x) for x in v) + "]"
    return json.dumps(v) if isinstance(v, str) else repr(v)


def _call(kind, name, props):
    cls = Fem.KINDS[kind]
    props = _normal(cls, {k: v for k, v in props.items() if k != "name" and k != "kind"})
    cls(name, **props)                  # refuses a property it does not have, before the file changes
    for r in props.get("references", ()):
        _check_ref(name, r)
    if props.get("direction"):
        _check_ref(name, props["direction"])
    parts = [json.dumps(name)]
    pos = [k for k in cls.POS if k in props and props[k] != cls.DEFAULTS[k]]
    parts += [_lit(props[k]) for k in pos]
    parts += [f"{k}={_lit(v)}" for k, v in props.items() if k not in pos and v != cls.DEFAULTS[k]]
    return f"Fem.{kind}({', '.join(parts)})"


def _check_ref(name, r):
    if len(r) != 2 or not all(isinstance(x, str) and x for x in r):
        raise Fem.FemError(f"{name}: {r!r} is not an (object, element) pair")


def _taken(src):
    """Every name a FEM object cannot have: the part's objects share one document with it."""
    d = E.read_src(src)
    return {x["name"] for x in [*(d.get("features") or []), *(d.get("objects") or [])]} | {"Body", "Analysis"}


def _add(src, op):
    kind, name = op.get("kind"), op.get("name")
    if kind not in Fem.KINDS:
        raise Fem.FemError(f"{kind!r} is not one of {', '.join(sorted(Fem.KINDS))}")
    if not isinstance(name, str) or not name.isidentifier():
        raise Fem.FemError(f"{name!r} is not a name for a FEM object (letters, digits and _)")
    if name in _taken(src) or name in [x["name"] for x in read_src(src)]:
        raise Fem.FemError(f"the part already has an object named {name}")
    text = _call(kind, name, op.get("props") or {})
    try:
        src = P.ensure_import(src, "feature_fem", "Fem")
    except E.FeatureEditError as e:
        raise Fem.FemError(str(e)) from None
    t = E._Text(src)
    lst, entries = _entries(t.tree)
    if lst is None:
        block = f"FEM = [\n    {text},\n]\n"
        at = next((n for n in t.tree.body if isinstance(n, ast.FunctionDef)), None)
        if at is None:
            return src.rstrip("\n") + "\n\n" + block
        start = min([at.lineno, *(d.lineno for d in at.decorator_list)])
        pos = t.starts[start - 1]
        return t.edit([(pos, pos, block + "\n\n")])
    if not entries:
        return t.edit([(t.a(lst), t.b(lst), f"[\n    {text},\n]")])
    last = lst.elts[-1]
    end = t.b(last)
    after = t.after_comma(end)
    spans = [(end, end, ",")] if after == end else []
    rest = t.raw[after:t.line_end(after)].strip()
    pos = t.line_end(after)
    if t.raw[t.line_start(t.a(last)):t.a(last)].strip() or (rest and not rest.startswith(b"#")):
        spans.append((after, after, f" {text},"))     # the entries share a line: beside the last one
    else:
        spans.append((pos, pos, " " * last.col_offset + text + ",\n"))
    return t.edit(spans)


def _find(t, name):
    lst, entries = _entries(t.tree)
    for i, (n, kind, call) in enumerate(entries):
        if n == name:
            return lst, i, kind, call
    raise Fem.FemError(f"the analysis has no object {name!r}")


def _set(src, op):
    t = E._Text(src)
    _, _, kind, call = _find(t, op.get("name"))
    props = {**_props(kind, call), **(op.get("props") or {})}
    return t.edit([(t.a(call), t.b(call), _call(kind, op["name"], props))])


def _delete(src, op):
    t = E._Text(src)
    lst, i, _, _ = _find(t, op.get("name"))
    a, b = E._entry_span(t, lst, i)
    return t.edit([(a, b, "")])


def apply_src(src: str, ops: list) -> str:
    do = {"add": _add, "set": _set, "delete": _delete}
    for op in ops:
        kind = op.get("op") if isinstance(op, dict) else None
        if kind not in do:
            raise Fem.FemError(f'{op!r} is not an edit (an "op" of add, set or delete)')
        src = do[kind](src, op)
    ast.parse(src)
    return src


# ── what the 3D view draws ───────────────────────────────────────────────────────────────────────────────────────

_FIELDS = {"displacement_x": None, "displacement_y": None, "displacement_z": None, "displacement": "DisplacementLengths",
           "von_mises": "vonMises", "max_principal": "PrincipalMax", "min_principal": "PrincipalMin",
           "max_shear": "MaxShear"}


def surface(mesh, result) -> dict | None:
    """The outside of a tetrahedral mesh with the result's values at its nodes (ResultShow's fields): triangles from each
    tetrahedron's corners, a face being outside when one tetrahedron alone has it. None for other elements."""
    if not mesh.Volumes:
        return None
    faces = {}
    nodes = mesh.Nodes
    for eid in mesh.Volumes:
        el = mesh.getElementNodes(eid)
        if len(el) not in (4, 10):
            return None
        a, b, c, d = el[:4]
        for f in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            faces.setdefault(tuple(sorted(f)), []).append(f)
    outer = [v[0] for v in faces.values() if len(v) == 1]
    index = {}
    for f in outer:
        for n in f:
            index.setdefault(n, len(index))
    points = [0.0] * (3 * len(index))
    for n, i in index.items():
        p = nodes[n]
        points[3 * i:3 * i + 3] = [p.x, p.y, p.z]
    numbers = list(result.NodeNumbers)
    pos = {n: i for i, n in enumerate(numbers)}
    disp = list(result.DisplacementVectors)
    vec = [0.0] * (3 * len(index))
    for n, i in index.items():
        d = disp[pos[n]]
        vec[3 * i:3 * i + 3] = [d.x, d.y, d.z]
    fields, ranges = {}, {}
    order = sorted(index, key=index.get)
    for key, prop in _FIELDS.items():
        if prop is None:
            axis = "xyz".index(key[-1])
            full = [getattr(d, "xyz"[axis]) for d in disp]
        else:
            full = list(getattr(result, prop, None) or [])
        if len(full) != len(numbers):
            continue
        fields[key] = [float(f"{full[pos[n]]:.6g}") for n in order]
        ranges[key] = [min(full), max(full)]
    return {"points": points, "triangles": [index[n] for f in outer for n in f], "displacement": vec,
            "fields": fields, "range": ranges}
