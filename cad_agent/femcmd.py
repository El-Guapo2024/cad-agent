# SPDX-License-Identifier: LGPL-2.1-or-later
"""cad fem: a part's FEM analysis (its FEM list, cad_agent/feature_fem.py).

  cad fem run SLUG PART      mesh with Gmsh and solve with CalculiX, as FreeCAD's FEM workbench does (out/fem/<part>/)
  cad fem list SLUG PART     the analysis's objects
  cad fem apply SLUG PART    add, change or delete objects (one undo step; cad_agent/fem_edit.py has the ops)
  cad fem result SLUG PART   the last run's results on the mesh's outside, for the 3D view
"""
from __future__ import annotations

import json
import shlex

from .cmdbase import OK, Result, UsageError, actor, part, project


def cmd_run(a) -> Result:
    from . import feature_fem as FF
    path = part(a.slug, a.part)
    work = project(a.slug) / "out" / "fem" / a.part
    import os
    threads = a.threads if a.threads is not None else (int(os.environ["CAD_FEM_THREADS"])
                                                       if os.environ.get("CAD_FEM_THREADS") else None)
    try:
        r = FF.run(path, workdir=work, threads=threads)
    except FF.FemError as e:
        raise UsageError(str(e)) from None
    text = (f"{a.slug}/{a.part}: {r['nodes']} nodes, {r['volumes']} volume elements\n"
            f"  max displacement {r['max_displacement_mm']:.6g} mm\n"
            f"  max von Mises stress {r['max_von_mises_mpa']:.6g} MPa"
            + (f"\n  frequencies {', '.join(f'{f:.6g}' for f in r['frequencies_hz'])} Hz" if "frequencies_hz" in r else "")
            + (f"\n  temperature {r['min_temperature_k']:.6g} to {r['max_temperature_k']:.6g} K" if "max_temperature_k" in r else "")
            + f"\n  files in {r['workdir']}")
    return Result(OK, {"project": a.slug, "part": a.part, **r}, text, f"FEM of {a.part}")


def _text(slug, name, objects):
    return "\n".join([f"{slug}/{name}: {len(objects)} FEM object{'' if len(objects) == 1 else 's'}",
                      *(f"  {o['name']} ({o['kind']})" for o in objects)])


def cmd_list(a) -> Result:
    from . import feature_fem as FF
    from . import fem_edit as FE
    try:
        objects = FE.read_src(part(a.slug, a.part).read_text())
    except FF.FemError as e:
        raise UsageError(str(e)) from None
    return Result(OK, {"project": a.slug, "part": a.part, "objects": objects}, _text(a.slug, a.part, objects),
                  f"FEM objects of {a.part}")


def cmd_apply(a) -> Result:
    from . import feature_fem as FF
    from . import fem_edit as FE
    from . import undo as un
    path = part(a.slug, a.part)
    pdir = project(a.slug)
    try:
        ops = json.loads(a.ops)
    except ValueError as e:
        raise UsageError(f"--ops is not JSON: {e}") from None
    if not isinstance(ops, list) or not ops:
        raise UsageError('--ops is a list of {"op": "add"|"set"|"delete", ...}')
    before = path.read_text()
    try:
        after = FE.apply_src(before, ops)
        objects = FE.read_src(after)
    except FF.FemError as e:             # all or nothing: the file is as it was
        raise UsageError(str(e)) from None
    name = a.name or f"FEM: {ops[0]['op']} {ops[0].get('name', '')}".strip()
    if after != before:
        path.write_text(after)
        un.record(pdir, name, shlex.join(["cad", "fem", "apply", a.slug, a.part, "--ops", a.ops]),
                  [{"path": path.relative_to(pdir).as_posix(), "before": before, "after": after}], by=actor(a))
    return Result(OK, {"project": a.slug, "part": a.part, "objects": objects, "step": name},
                  _text(a.slug, a.part, objects), name)


def cmd_result(a) -> Result:
    from .feature_fem import RESULTS
    part(a.slug, a.part)
    f = project(a.slug) / "out" / "fem" / a.part / RESULTS
    if not f.exists():
        raise UsageError(f"{a.part} has no results yet: run `cad fem run {a.slug} {a.part}` first")
    d = json.loads(f.read_text())
    return Result(OK, {"project": a.slug, "part": a.part, **d},
                  f"{a.slug}/{a.part}: results on {len(d['triangles']) // 3} surface triangles", f"FEM results of {a.part}")


def add_parsers(add, sub) -> None:
    fp = add("fem", None, "a part's FEM analysis (FreeCAD's FEM workbench: Gmsh and CalculiX, as separate programs)")
    from .cmdbase import Parser
    fsub = fp.add_subparsers(dest="fem_cmd", metavar="<action>", parser_class=Parser)
    sp = add("run", cmd_run, "mesh the part's FEM analysis with Gmsh and solve it with CalculiX", parent=fsub)
    sp.set_defaults(cmd_name="fem run", fem_cmd="run")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("--threads", type=int, default=None,
                    help="Gmsh's threads (FEM's NumOfThreads; 1 gives the same mesh each run; default CAD_FEM_THREADS, "
                    "else FreeCAD's, every core)")
    sp = add("list", cmd_list, "the objects of the part's FEM analysis", parent=fsub)
    sp.set_defaults(cmd_name="fem list", fem_cmd="list")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp = add("apply", cmd_apply, "add, change or delete objects of the part's FEM analysis, as one undo step", parent=fsub)
    sp.set_defaults(cmd_name="fem apply", fem_cmd="apply")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("--ops", required=True, help='JSON: [{"op": "add", "kind": "ConstraintFixed", "name": "Fixed", '
                    '"props": {...}}, {"op": "set", "name": ..., "props": {...}}, {"op": "delete", "name": ...}]')
    sp.add_argument("--name", default=None, help="the undo step's name")
    sp = add("result", cmd_result, "the last FEM run's results on the mesh's outside, as JSON", parent=fsub)
    sp.set_defaults(cmd_name="fem result", fem_cmd="result")
    sp.add_argument("slug")
    sp.add_argument("part")
