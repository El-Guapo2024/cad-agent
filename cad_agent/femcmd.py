# SPDX-License-Identifier: LGPL-2.1-or-later
"""cad fem run SLUG PART: a part's FEM analysis (its FEM list, cad_agent/feature_fem.py), meshed by Gmsh and solved by
CalculiX as FreeCAD's FEM workbench does; the results in out/fem/<part>/ of the project."""
from __future__ import annotations

from .cmdbase import OK, Result, UsageError, part, project


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
            f"  max von Mises stress {r['max_von_mises_mpa']:.6g} MPa\n"
            f"  files in {r['workdir']}")
    return Result(OK, {"project": a.slug, "part": a.part, **r}, text, f"FEM of {a.part}")


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
