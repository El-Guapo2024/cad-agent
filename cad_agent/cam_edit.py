# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's CAM commands do to a document (src/Mod/CAM/Path/Main/Gui/
# JobCmd.py, Path/Op/Gui/Base.py, Path/Dressup/Gui/*.py, Path/Tool/library/ui/dock.py) and keeps FreeCAD's licence,
# the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../NOTICE.
"""The app's and the CLI's edits of a project's CAM jobs, written back into cam/<Job>.py as Python.

read(pdir, job) gives the job as the tree, the property view and the task panels show it (its entries, and with
recompute FreeCAD's objects and each op's Path); apply(pdir, job, ops) runs FreeCAD's commands and writes the JOB list
back, all or nothing: an entry the edit did not change keeps its text. A new object gets the Name FreeCAD's Create()
gives it: the command is run in the recomputed document and its object's Name is what the file records.

The ops (each is what the FreeCAD command named does):

    {"op": "new_job", "parts": [part, ...]}                     CAM_Job: the Job, its stock, setup sheet, default
                                                                tool controller and bit
    {"op": "tool", "bit": "5mm_Endmill" | "shape": "endmill", "number"?, "props"?: {...}}
                                                                the ToolBit dock's Add to Job: a bit and its controller
    {"op": "op", "type": "Profile"|"PocketShape"|"MillFace"|"Drilling", "base"?: [[part, ["Face3"]]],
     "props"?: {...}}                                           CAM_Profile ... (Create, then the task panel's values)
    {"op": "dressup", "type": "DressupTag"|"DressupDogbone", "base": op, "props"?: {...}}
    {"op": "set", "name": n, "props": {...}}                    the property view (a value clears the property's
                                                                expression; "ExpressionEngine": {prop: expr | None})
    {"op": "delete", "name": n}                                 Std_Delete (refused while something links to it)
    {"op": "label", "name": n, "to": text}                      Std_Rename
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from . import cam as C

DIR = "cam"
LIST = "JOB"
PREFIX = "CAM."
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CamEditError(C.CamError):
    pass


# ── files ─────────────────────────────────────────────────────────────────────────────────────────────

def jobs(pdir) -> list[str]:
    d = Path(pdir) / DIR
    return sorted(p.stem for p in d.glob("*.py") if not p.stem.startswith(("_", "."))) if d.is_dir() else []


def job_file(pdir, job: str) -> Path:
    if not (isinstance(job, str) and NAME.match(job)):
        raise CamEditError(f"{job!r} is not a job name")
    return Path(pdir) / DIR / f"{job}.py"


def _list_node(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == LIST for t in node.targets):
            if not isinstance(node.value, ast.List):
                raise CamEditError(f"{LIST} is not a list the app can edit")
            return node.value
    return None


def _kind(call):
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "CAM":
        return f.attr
    return None


def _value(node, src):
    try:
        return ast.literal_eval(node)
    except ValueError:
        raise CamEditError(f"{ast.get_source_segment(src, node)!r} is not a literal the app can read") from None


def entries(src: str):
    """[(Entry, call node)] of a job file, or None when it has no JOB list."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise CamEditError(f"the job does not parse: {e}") from None
    lst = _list_node(tree)
    if lst is None:
        return None
    out = []
    for e in lst.elts:
        kind = _kind(e) if isinstance(e, ast.Call) else None
        if kind not in C.KINDS:
            raise CamEditError(f"{LIST} holds {ast.get_source_segment(src, e)[:60]!r}, not a CAM.{'/'.join(C.KINDS)} "
                               "call")
        if len(e.args) != 1:
            raise CamEditError(f"CAM.{kind}(...) takes the object's Name and its properties as keywords")
        name = _value(e.args[0], src)
        props = {k.arg: _value(k.value, src) for k in e.keywords}
        out.append((C.Entry(kind, name, props), e))
    return out


def load(pdir, job):
    path = job_file(pdir, job)
    if not path.exists():
        raise CamEditError(f"there is no job {job!r} (cam/{job}.py)")
    es = entries(path.read_text())
    if es is None:
        raise CamEditError(f"cam/{job}.py has no JOB list")
    return [e for e, _ in es]


def all_jobs(pdir, override=None):
    """[(file, [Entry])] of every job of the project, the one being edited replaced by its new entries."""
    out = []
    names = jobs(pdir)
    if override and override[0] not in names:
        names = sorted(names + [override[0]])
    for j in names:
        if override and j == override[0]:
            out.append((j, override[1]))
        else:
            try:
                out.append((j, load(pdir, j)))
            except CamEditError:
                continue
    return out


def lit(v) -> str:
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{lit(k)}: {lit(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        inner = ", ".join(lit(x) for x in v)
        if isinstance(v, tuple):
            return f"({inner},)" if len(v) == 1 else f"({inner})"
        return f"[{inner}]"
    raise CamEditError(f"{v!r} cannot be written in a job file")


def entry_src(e: C.Entry) -> str:
    parts = [json.dumps(e.name)] + [f"{k}={lit(v)}" for k, v in e.props.items()]
    return f"{PREFIX}{e.kind}({', '.join(parts)})"


TEMPLATE = '''"""{job}: a CAM job of {slug} (FreeCAD's CAM workbench).

JOB is the job's objects in the order FreeCAD's commands made them: the Job (the parts it machines as Model), its
stock and setup sheet, the tool bits and tool controllers, the operations and dress-ups, each with the properties set
on it by FreeCAD's own names. The app and `cad cam ...` edit it (cad_agent/cam_edit.py); FreeCAD's CAM code recomputes
the toolpaths from it (cad_agent/cam_doc.py) and its post-processors write the G-code (`cad cam post`).
"""
from cad_agent import cam as CAM

JOB = [
]
'''


def write_src(src: str, new_entries) -> str:
    from .feature_edit import _Text
    t = _Text(src)
    lst = _list_node(t.tree)
    if lst is None:
        raise CamEditError("the job file has no JOB list")
    old = entries(src) or []
    by_name = {e.name: (e, call) for e, call in old}
    ind = lst.elts[0].col_offset if lst.elts else 4
    lines = []
    for e in new_entries:
        prev = by_name.get(e.name)
        if prev is not None and prev[0] == e:
            text = t.raw[t.a(prev[1]):t.b(prev[1])].decode()
            end = t.after_comma(t.b(prev[1]))
            rest = t.raw[end:t.line_end(end)].decode().rstrip("\n")
            comment = rest if rest.strip().startswith("#") else ""
            out = text.split("\n")
            col = prev[1].col_offset
            text = "\n".join([out[0]] + [ln[col:] if ln[:col].strip() == "" else ln for ln in out[1:]])
            lines.append(" " * ind + text.replace("\n", "\n" + " " * ind) + "," + comment)
        else:
            lines.append(" " * ind + entry_src(e) + ",")
    body = "[\n" + "".join(line + "\n" for line in lines) + "]" if lines else "[\n]"
    return t.edit([(t.a(lst), t.b(lst), body)])


# ── reading ───────────────────────────────────────────────────────────────────────────────────────────

def part_names(pdir):
    parts_dir = Path(pdir) / "parts"
    return sorted(p.stem for p in parts_dir.glob("*.py") if not p.stem.startswith("_")) if parts_dir.is_dir() else []


def recomputed(pdir, job, override=None, shape_of=None):
    """The project's CAM document built, and the job's result (cam_doc.CamDocument.result())."""
    from . import cam_doc
    pdir = Path(pdir)
    js = all_jobs(pdir, override)
    doc = cam_doc.build(pdir.name, js, shape_of)
    res = doc.result()
    ents = override[1] if override else load(pdir, job)
    names = {e.name for e in ents}
    job_res = next((j for j in res["jobs"] if j["file"] == job), None)
    objs = [o for o in res["objects"] if o["file"] == job or o["name"] in names]
    return doc, {"project": pdir.name, "job": job, "entries": [e.as_dict() for e in ents],
                 "result": {"job": job_res, "objects": objs, "messages": res["messages"],
                            "errors": [x for x in res["errors"] if x["object"] in {o["name"] for o in objs}]}}


def read(pdir, job, recompute=True, shape_of=None):
    pdir = Path(pdir)
    ents = load(pdir, job)
    if not recompute:
        return {"project": pdir.name, "job": job, "entries": [e.as_dict() for e in ents]}
    _, out = recomputed(pdir, job, shape_of=shape_of)
    return out


# ── the ops ───────────────────────────────────────────────────────────────────────────────────────────

def _check_props(props):
    if props is None:
        return {}
    if not isinstance(props, dict):
        raise CamEditError("props is a dict of FreeCAD property names to values")
    for k in props:
        if not (isinstance(k, str) and NAME.match(k)):
            raise CamEditError(f"{k!r} is not a property name")
    return dict(props)


def _merge(entry, props):
    for k, v in props.items():
        if k == "ExpressionEngine":
            ee = dict(entry.props.get("ExpressionEngine") or {})
            ee.update(v or {})
            entry.props["ExpressionEngine"] = ee
            continue
        entry.props[k] = v
        ee = entry.props.get("ExpressionEngine")
        if ee and k in ee and ee[k] is not None:
            del ee[k]                     # a value given clears the expression the file set
            if not ee:
                del entry.props["ExpressionEngine"]


def _references(e):
    out = []
    for k, v in e.props.items():
        if k in ("Tool", "ToolController") and isinstance(v, str):
            out.append(v)
        elif k == "Base" and isinstance(v, str):
            out.append(v)
    return out


class Session:
    def __init__(self, pdir, job, ents, shape_of=None):
        self.pdir, self.job, self.ents = Path(pdir), job, ents
        self.shape_of = shape_of
        self.done = []

    def get(self, name):
        e = next((x for x in self.ents if x.name == name), None)
        if e is None:
            raise CamEditError(f"there is no object {name!r} in {self.job}")
        return e

    def doc(self):
        """The project's CAM document as the entries stand."""
        from . import cam_doc
        return cam_doc.build(self.pdir.name, all_jobs(self.pdir, (self.job, self.ents)),
                             self.shape_of or _default_shape(self.pdir))



def run_ops(s: Session, ops):
    for op in ops:
        kind = op.get("op")
        if kind == "new_job":
            s.done.append(_new_job(s, op))
        elif kind == "tool":
            s.done.append(_tool(s, op))
        elif kind == "op":
            s.done.append(_op(s, op))
        elif kind == "dressup":
            s.done.append(_dressup(s, op))
        elif kind == "set":
            e = s.get(op.get("name"))
            _merge(e, _check_props(op.get("props")))
            s.done.append(f"set {e.name}: {', '.join(op.get('props') or {})}")
        elif kind == "delete":
            name = op.get("name")
            e = s.get(name)
            if e.kind == "Job":
                raise CamEditError("delete the job with `cad cam delete-job`")
            users = [x.name for x in s.ents if name in _references(x)]
            if users:
                raise CamEditError(f"{name} is used by {', '.join(users)}")
            s.ents = [x for x in s.ents if x.name != name]
            s.done.append(f"deleted {name}")
        elif kind == "label":
            e = s.get(op.get("name"))
            to = op.get("to")
            if not isinstance(to, str) or not to:
                raise CamEditError("a Label is a non-empty string")
            e.props["Label"] = to
            s.done.append(f"{e.name} is labelled {to!r}")
        else:
            raise CamEditError(f"unknown op {kind!r}")
    return s.done


def _new_job(s, op):
    parts = op.get("parts") or []
    if isinstance(parts, str):
        parts = [parts]
    if not parts:
        raise CamEditError("a Job needs the parts it machines")
    known = part_names(s.pdir)
    for p in parts:
        if known and p not in known:
            raise CamEditError(f"there is no part {p!r} in the project (parts: {', '.join(known)})")
    if s.ents:
        raise CamEditError(f"{s.job} already has its Job")
    s.ents = [C.Entry("Job", s.job, {"Model": list(parts)})]
    from . import cam_doc
    doc = cam_doc.CamDocument(s.pdir.name, all_jobs(s.pdir, (s.job, s.ents)),
                              s.shape_of or _default_shape(s.pdir)).replay(prune=False)
    job = doc.made[s.job]
    made = []
    for tc in job.Tools.Group:
        bit = tc.Tool
        shape = getattr(bit, "ShapeID", None)
        made.append(C.Entry("ToolBit", bit.Name, {"ShapeID": shape} if shape else {}))
        made.append(C.Entry("ToolController", tc.Name, {"Tool": bit.Name}))
    s.ents += made
    return f"Job {s.job} on {', '.join(parts)}"


def _created(s, entry):
    """Run the command for entry in the document as the entries stand, and give the entry the Name FreeCAD's
    Create() chose."""
    from . import cam_doc
    js = all_jobs(s.pdir, (s.job, s.ents))
    doc = cam_doc.CamDocument(s.pdir.name, js, s.shape_of or _default_shape(s.pdir)).build()
    job = doc.made[s.ents[0].name]
    probe = C.Entry(entry.kind, "\x00", {k: v for k, v in entry.props.items()
                                         if k in ("Bit", "ShapeID", "Tool", "Base", "ToolNumber")})
    obj = doc.r.make(job, probe)
    entry.name = obj.Name
    return obj


def _default_shape(pdir):
    from .techdraw_edit import shape_loader
    return shape_loader(Path(pdir).name)


def _tool(s, op):
    props = _check_props(op.get("props"))
    bit = op.get("bit")
    shape = op.get("shape")
    if not bit and not shape:
        raise CamEditError('a tool is a library bit ("bit": "5mm_Endmill") or a shape ("shape": "endmill")')
    be = C.Entry("ToolBit", "\x00", {"Bit": bit} if bit else {"ShapeID": shape})
    _created(s, be)
    bit_props = {k: v for k, v in props.items() if k not in ("ToolNumber", "SpindleSpeed", "SpindleDir", "HorizFeed",
                                                              "VertFeed", "HorizRapid", "VertRapid", "LeadInFeed",
                                                              "LeadOutFeed", "RampFeed", "NoEngagementFeed")}
    tc_props = {k: v for k, v in props.items() if k not in bit_props}
    be.props.update(bit_props)
    s.ents.append(be)
    te = C.Entry("ToolController", "\x00", {"Tool": be.name})
    if op.get("number") is not None:
        te.props["ToolNumber"] = int(op["number"])
    _created(s, te)
    te.props.update(tc_props)
    s.ents.append(te)
    return f"tool {be.name} with controller {te.name}"


def _op(s, op):
    t = op.get("type")
    if t not in C.OPS:
        raise CamEditError(f"{t!r} is not an operation the app makes ({', '.join(C.OPS)})")
    props = _check_props(op.get("props"))
    if op.get("base") is not None:
        props["Base"] = [tuple(x) if isinstance(x, list) else x for x in op["base"]]
    e = C.Entry(t, "\x00", {})
    _created(s, e)
    e.props.update(props)
    s.ents.append(e)
    return f"{C.KINDS[t].transaction}: {e.name}"


def _dressup(s, op):
    t = op.get("type")
    if t not in C.DRESSUPS:
        raise CamEditError(f"{t!r} is not a dress-up the app makes ({', '.join(C.DRESSUPS)})")
    base = op.get("base")
    b = s.get(base)
    if b.kind not in C.OPS and b.kind not in C.DRESSUPS:
        raise CamEditError(f"{base} is not an operation")
    e = C.Entry(t, "\x00", {"Base": base})
    _created(s, e)
    e.props.update(_check_props(op.get("props")))
    s.ents.append(e)
    return f"{C.KINDS[t].transaction}: {e.name}"


def apply(pdir, job, ops, write=True, recompute=True, shape_of=None):
    """Run ops on the job and write it back; returns read()'s dict with 'done'."""
    pdir = Path(pdir)
    path = job_file(pdir, job)
    src = path.read_text() if path.exists() else TEMPLATE.format(job=job, slug=pdir.name)
    ents = [e for e, _ in (entries(src) or [])]
    s = Session(pdir, job, [e.copy() for e in ents], shape_of)
    done = run_ops(s, ops)
    new_src = write_src(src, s.ents)
    out = None
    if recompute:
        _, out = recomputed(pdir, job, (job, s.ents), shape_of)
        out["done"] = done
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_src)
    return out if out is not None else {"project": pdir.name, "job": job, "entries": [e.as_dict() for e in s.ents],
                                        "done": done}
