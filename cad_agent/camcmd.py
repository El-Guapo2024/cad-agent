"""cad cam: a project's CAM jobs (FreeCAD's CAM workbench), edited from the CLI and the workbench alike.

A job is cam/<Job>.py, its JOB list (docs/EDITING_PLAN.md, "CAM in a project"). These commands edit it through
cad_agent/cam_edit.py, each change one step of the undo journal named as FreeCAD names the transaction; the toolpaths
are FreeCAD's own CAM code's (cad_agent/cam_doc.py):

    cad cam ls       SLUG                                  the project's jobs
    cad cam show     SLUG JOB [--commands]                 the tree, each op's Path (its size, or every command)
    cad cam new      SLUG PART... [--job NAME]             CAM_Job: a Job machining the parts
    cad cam tool     SLUG JOB [KEY=VALUE ...] (--bit 5mm_Endmill | --shape endmill) [--number N]
                                                           the ToolBit dock's Add to Job: a bit and its controller
    cad cam op       SLUG JOB TYPE [KEY=VALUE ...] [--base PART:Face3,Face4 ...]
                                                           CAM_Profile, CAM_Pocket_Shape, CAM_MillFace, CAM_Drilling
    cad cam dressup  SLUG JOB TYPE OP [KEY=VALUE ...]       CAM_DressupTag (Tag), CAM_DressupDogbone (Dogbone)
    cad cam set      SLUG JOB NAME KEY=VALUE ...           the property view (KEY=expr:EXPR binds an expression)
    cad cam delete   SLUG JOB NAME ...                     Std_Delete
    cad cam label    SLUG JOB NAME TEXT                    Std_Rename
    cad cam apply    SLUG JOB --ops JSON                   several ops as one step (what the workbench sends)
    cad cam post     SLUG JOB [--post linuxcnc|grbl|generic] [--args ARGS] [--out FILE]
                                                           CAM_Post: FreeCAD's post-processor, unchanged
    cad cam delete-job SLUG JOB                            Std_Delete of the Job and everything in it

TYPE is Profile, PocketShape, MillFace or Drilling (and DressupTag, DressupDogbone for dressup). KEY=VALUE pairs come before the options. A value is what
FreeCAD's property takes: a number, a quantity with its unit ("2 mm", "600 mm/min"), a name, true/false, or JSON.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

from . import state as st
from .cmdbase import OK, Result, UsageError, actor, project

STEP_NAMES = {"new_job": "Create Job", "tool": "Add Tool Controller to the Job", "delete": "Delete"}


def step_name(ops: list) -> str:
    from . import cam as C
    op = ops[-1] if ops else {}
    kind = op.get("op")
    if kind in ("op", "dressup") and op.get("type") in C.KINDS:
        return C.KINDS[op["type"]].transaction
    if kind in STEP_NAMES:
        return STEP_NAMES[kind]
    if kind == "label":
        return f"Rename {op.get('name')}.Label"
    if kind == "set":
        props = list(op.get("props") or {})
        first = props[0] if props else "property"
        return f"Edit {op.get('name')}.{first}" + ("..." if len(props) > 1 else "")
    return "Edit job"


def parse_value(text: str):
    """KEY=VALUE's value: JSON when it reads as JSON (numbers, true/false, lists), else the string itself."""
    t = text.strip()
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    try:
        return json.loads(t)
    except ValueError:
        return text


def parse_props(pairs_in):
    props = {}
    for p in pairs_in or []:
        if "=" not in p:
            raise UsageError(f"{p!r} is not KEY=VALUE")
        k, v = p.split("=", 1)
        k = k.strip()
        if v.startswith("expr:"):
            props.setdefault("ExpressionEngine", {})[k] = v[5:] or None
        else:
            props[k] = parse_value(v)
    return props


def _lines(doc: dict, commands=False) -> list[str]:
    out = []
    res = doc.get("result") or {}
    objs = {o["name"]: o for o in res.get("objects", [])}

    def walk(node, depth):
        o = objs.get(node["name"], {})
        label = node["label"] if node["label"] == node["name"] else f"{node['label']} ({node['name']})"
        extra = ""
        if "commands" in o and o.get("kind") not in (None, "ToolController", "Job"):
            extra = f"  {len(o['commands'])} commands"
        if o and not o.get("valid", True):
            extra += f"  ERROR {o.get('status')}"
        out.append(f"{'  ' * (depth + 1)}{label}{'  [' + node['kind'] + ']' if node.get('kind') else ''}{extra}")
        if commands and "commands" in o and o.get("kind") not in (None, "Job"):
            for name, params in o["commands"]:
                out.append(f"{'  ' * (depth + 3)}{name} " + " ".join(f"{k}{v:g}" for k, v in params.items()))
        for c in node.get("children", []):
            walk(c, depth + 1)
    job = res.get("job")
    if job:
        walk(job["tree"], 0)
    for e in res.get("errors", []):
        out.append(f"  {e['object']}: {e['error']}")
    for m in res.get("messages", [])[:20]:
        out.append(f"  {m['kind']}: {m['text'].strip()}")
    return out


def apply_ops(a, job: str, ops: list, cmd: str, step: str | None = None) -> Result:
    from . import cam_edit as E
    if not isinstance(ops, list) or not ops or not all(isinstance(o, dict) and o.get("op") for o in ops):
        raise UsageError('ops is a list of {"op": "new_job"|"tool"|"op"|"dressup"|"set"|"delete"|"label", ...}')
    pdir = project(a.slug)
    try:
        path = E.job_file(pdir, job)
    except E.CamEditError as e:
        raise UsageError(str(e)) from None
    before = path.read_text() if path.exists() else None
    if before is None and ops[0].get("op") != "new_job":
        raise UsageError(f"there is no job {job!r}: make it first (cad cam new)")
    try:
        doc = E.apply(pdir, job, ops)
    except (ValueError, KeyError) as e:
        raise UsageError(str(e)) from None
    except Exception as e:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(before)
        raise UsageError(f"the job did not recompute: {st.why(e)}") from None
    after = path.read_text()
    name = step or step_name(ops)
    from . import undo as un
    rel = f"{E.DIR}/{job}.py"
    if getattr(a, "amend", False):
        un.amend(pdir, [{"path": rel, "before": before, "after": after}], by=actor(a))
    else:
        un.record(pdir, name, cmd, [{"path": rel, "before": before, "after": after}], by=actor(a))
    lines = [f"{a.slug}/{job}: {name}"] + [f"  {d}" for d in doc.get("done", [])] + _lines(doc)
    data = {"project": a.slug, "job": job, "step": name, "doc": doc, "file": str(path)}
    return Result(OK, data, "\n".join(lines), f"{a.slug}/{job}: {name}", [str(path)])


def _cmd(a, *words: str) -> str:
    return shlex.join(["cad", "cam", a.cam_cmd, a.slug, *words])


def cmd_ls(a) -> Result:
    from . import cam_edit as E
    pdir = project(a.slug)
    data = {"project": a.slug, "jobs": []}
    for j in E.jobs(pdir):
        try:
            ents = E.load(pdir, j)
            data["jobs"].append({"job": j, "model": ents[0].props.get("Model"), "objects": len(ents)})
        except E.CamEditError as e:
            data["jobs"].append({"job": j, "error": str(e)})
    text = "\n".join([f"{a.slug}: {len(data['jobs'])} job(s)"] +
                     [f"  {d['job']}  {d.get('model') or d.get('error')}" for d in data["jobs"]])
    return Result(OK, data, text, f"{a.slug}: {len(data['jobs'])} job(s)")


def cmd_show(a) -> Result:
    from . import cam_edit as E
    pdir = project(a.slug)
    try:
        doc = E.read(pdir, a.job)
    except E.CamEditError as e:
        raise UsageError(str(e)) from None
    except Exception as e:
        raise UsageError(f"the job did not recompute: {st.why(e)}") from None
    return Result(OK, doc, "\n".join([f"{a.slug}/{a.job}"] + _lines(doc, a.commands)), f"{a.slug}/{a.job}")


def cmd_new(a) -> Result:
    from . import cam_edit as E
    pdir = project(a.slug)
    taken = set(E.jobs(pdir))
    job = a.job
    if not job:
        job = "Job"
        i = 0
        while job in taken:
            i += 1
            job = f"Job{i:03d}"
    elif job in taken:
        raise UsageError(f"there is already a job {job!r}")
    return apply_ops(a, job, [{"op": "new_job", "parts": a.parts}], _cmd(a, *a.parts, "--job", job), "Create Job")


def cmd_tool(a) -> Result:
    op = {"op": "tool", "props": parse_props(a.props)}
    if a.bit:
        op["bit"] = a.bit
    if a.shape:
        op["shape"] = a.shape
    if a.number is not None:
        op["number"] = a.number
    words = [a.job] + (["--bit", a.bit] if a.bit else []) + (["--shape", a.shape] if a.shape else []) + (
        ["--number", str(a.number)] if a.number is not None else []) + list(a.props or [])
    return apply_ops(a, a.job, [op], _cmd(a, *words))


def _base(items):
    out = []
    for b in items or []:
        part, _, subs = b.partition(":")
        out.append([part, [s for s in subs.split(",") if s] if subs else [""]])
    return out


def cmd_op(a) -> Result:
    op = {"op": "op", "type": a.type, "props": parse_props(a.props)}
    if a.base:
        op["base"] = _base(a.base)
    words = [a.job, a.type] + sum((["--base", b] for b in a.base or []), []) + list(a.props or [])
    return apply_ops(a, a.job, [op], _cmd(a, *words))


def cmd_dressup(a) -> Result:
    op = {"op": "dressup", "type": a.type, "base": a.op, "props": parse_props(a.props)}
    return apply_ops(a, a.job, [op], _cmd(a, a.job, a.type, a.op, *(a.props or [])))


def cmd_set(a) -> Result:
    props = parse_props(a.props)
    if not props:
        raise UsageError("set takes KEY=VALUE ...")
    return apply_ops(a, a.job, [{"op": "set", "name": a.name, "props": props}],
                     _cmd(a, a.job, a.name, *a.props))


def cmd_delete(a) -> Result:
    return apply_ops(a, a.job, [{"op": "delete", "name": n} for n in a.names], _cmd(a, a.job, *a.names), "Delete")


def cmd_label(a) -> Result:
    return apply_ops(a, a.job, [{"op": "label", "name": a.name, "to": a.text}], _cmd(a, a.job, a.name, a.text))


def cmd_apply(a) -> Result:
    try:
        ops = json.loads(a.ops)
    except ValueError as e:
        raise UsageError(f"--ops is not JSON: {e}") from None
    return apply_ops(a, a.job, ops, _cmd(a, a.job, "--ops", a.ops), a.step)


def cmd_post(a) -> Result:
    from . import cam_edit as E
    pdir = project(a.slug)
    try:
        doc, _ = E.recomputed(pdir, a.job)
        sections = doc.post(a.job, a.post, a.args)
    except E.CamEditError as e:
        raise UsageError(str(e)) from None
    except Exception as e:
        raise UsageError(f"the post-processor failed: {st.why(e)}") from None
    if not sections:
        raise UsageError(f"{a.post} wrote no G-code for {a.job}")
    files = []
    out = Path(a.out) if a.out else pdir / "out" / "cam" / f"{a.job}.nc"
    out.parent.mkdir(parents=True, exist_ok=True)
    for i, (section, gcode) in enumerate(sections):
        path = out if len(sections) == 1 else out.with_name(f"{out.stem}-{section}{out.suffix}")
        path.write_text(gcode)
        files.append(str(path))
    lines = sum(g.count("\n") for _, g in sections)
    data = {"project": a.slug, "job": a.job, "post": a.post, "files": files,
            "gcode": sections[0][1] if a.print else None, "sections": [s for s, _ in sections]}
    text = f"{a.slug}/{a.job}: {a.post} wrote {lines} lines to {', '.join(files)}"
    if a.print:
        text += "\n" + "\n".join(g for _, g in sections)
    return Result(OK, data, text, f"{a.slug}/{a.job}: {a.post}", files)


def cmd_delete_job(a) -> Result:
    from . import cam_edit as E
    from . import undo as un
    pdir = project(a.slug)
    path = E.job_file(pdir, a.job)
    if not path.exists():
        raise UsageError(f"there is no job {a.job!r}")
    before = path.read_text()
    path.unlink()
    un.record(pdir, "Delete", _cmd(a, a.job), [{"path": f"{E.DIR}/{a.job}.py", "before": before, "after": None}],
              by=actor(a))
    return Result(OK, {"project": a.slug, "job": a.job}, f"{a.slug}: deleted {a.job}", f"{a.slug}: deleted {a.job}")


def add_parsers(add, sub) -> None:
    """cli.py's build_parser hands its `add` and the subparsers here."""
    cp = add("cam", None, "a project's CAM jobs (FreeCAD's CAM workbench): new, tool, op, dressup, set, delete, "
             "post; each change one undo step, the toolpaths FreeCAD's own CAM code's")
    from .cmdbase import Parser
    csub = cp.add_subparsers(dest="cam_cmd", metavar="<action>", parser_class=Parser)

    def one(name, func, help, job=True):
        sp = add(name, func, help, parent=csub)
        sp.set_defaults(cmd_name=f"cam {name}", cam_cmd=name)
        sp.add_argument("slug")
        if job:
            sp.add_argument("job")
        return sp

    one("ls", cmd_ls, "the project's jobs", job=False)
    sp = one("show", cmd_show, "the job's tree and each op's Path (a recompute)")
    sp.add_argument("--commands", action="store_true", help="every command of every op")
    sp = one("new", cmd_new, "CAM_Job: a Job machining the parts", job=False)
    sp.add_argument("parts", nargs="+", metavar="PART")
    sp.add_argument("--job", help="the Job's Name and file (default Job, Job001, ...)")
    sp = one("tool", cmd_tool, "the ToolBit dock's Add to Job: a library bit (--bit) or a shape (--shape) and its "
             "tool controller")
    sp.add_argument("--bit", help="a bit of FreeCAD's library: 5mm_Endmill, 3.175mm_Endmill, 5mm_Drill, "
                    "6mm_Ball_End, 45degree_chamfer, 60degree_Vbit ...")
    sp.add_argument("--shape", help="a shape: endmill, drill, ballend, bullnose, chamfer, v-bit ...")
    sp.add_argument("--number", type=int, help="ToolNumber (default the next free)")
    sp.add_argument("props", nargs="*", metavar="KEY=VALUE", help="the bit's (Diameter=6mm) and the controller's "
                    "(HorizFeed='600 mm/min', SpindleSpeed=12000) properties")
    sp = one("op", cmd_op, "CAM_Profile / CAM_Pocket_Shape / CAM_MillFace / CAM_Drilling")
    sp.add_argument("type", choices=["Profile", "PocketShape", "MillFace", "Drilling"])
    sp.add_argument("--base", action="append", metavar="PART:Face3,Face4", help="base geometry (repeatable)")
    sp.add_argument("props", nargs="*", metavar="KEY=VALUE")
    sp = one("dressup", cmd_dressup, "CAM_DressupTag / CAM_DressupDogbone on an op")
    sp.add_argument("type", choices=["DressupTag", "DressupDogbone"])
    sp.add_argument("op")
    sp.add_argument("props", nargs="*", metavar="KEY=VALUE")
    sp = one("set", cmd_set, "the property view: FreeCAD's property names (KEY=expr:EXPR binds an expression, "
             "KEY=expr: clears it)")
    sp.add_argument("name")
    sp.add_argument("props", nargs="+", metavar="KEY=VALUE")
    sp = one("delete", cmd_delete, "Std_Delete of objects of the job")
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp = one("label", cmd_label, "Std_Rename: an object's Label")
    sp.add_argument("name")
    sp.add_argument("text")
    sp = one("apply", cmd_apply, "several ops as one step (what the workbench sends)")
    sp.add_argument("--ops", required=True, help="JSON list of ops (cad_agent/cam_edit.py)")
    sp.add_argument("--step", help="the undo step's name")
    sp.add_argument("--amend", action="store_true", help="fold into the last undo step")
    sp = one("post", cmd_post, "CAM_Post: the job's G-code by FreeCAD's post-processor")
    sp.add_argument("--post", default="linuxcnc", choices=["linuxcnc", "grbl", "generic"])
    sp.add_argument("--args", help="the post-processor's arguments (PostProcessorArgs)")
    sp.add_argument("--out", help="the file (default out/cam/<JOB>.nc)")
    sp.add_argument("--print", action="store_true", help="the G-code on stdout too")
    one("delete-job", cmd_delete_job, "Std_Delete of the Job")
