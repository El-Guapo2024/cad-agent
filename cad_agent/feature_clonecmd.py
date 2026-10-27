# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It follows FreeCAD's CmdPartDesignClone (src/Mod/PartDesign/Gui/Command.cpp, Copyright (c) 2008
# Jürgen Riegel, FreeCAD at 3160daf1e2b62b0472854da4848255c6b3ad554c) and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE. See ../NOTICE.
"""cad feature clone SLUG SOURCE [--name PART]: PartDesign_Clone, a new Body (a part module) whose base is a Clone of
another (cad_agent/feature_boolean.py). Kept apart from feature_boolean so that building the CLI's parser imports no
kernel."""
from __future__ import annotations


CLONE_TEMPLATE = '''"""{part}: a PartDesign Body made by Clone from {source} (cad feature clone).

Its shape is FEATURES (cad_agent/feature.py); the Clone is its base, a copy of {source}'s Body that follows it.
"""
from cad_agent.feature import (ArcOfCircle, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, Body, BSplineCurve,
                               Circle, Clone, Constraint, Ellipse, LineSegment, Pad, Pocket, Point, Sketch)

MATERIAL = {material!r}
PROCESS = {process!r}

PARAMS = {{}}

FEATURES = [
    Clone("{clone}", "{source}"),
]
TIP = "{clone}"


def build(**p):
    return Body(FEATURES, p, tip=TIP)
'''


def cmd_feature_clone(a):
    """CmdPartDesignClone: a new Body (getUniqueObjectName("Body"): the next free part name) holding a Clone of the
    selected Body (or one of its features, SOURCE.Feature), its Tip; one undo step, "Create Clone"."""
    import shlex
    from .cmdbase import OK, Result, UsageError, actor, project
    from . import state as st
    from . import undo as un
    pdir = project(a.slug)
    source = a.source
    body, _, feat = source.partition(".")
    if not (pdir / "parts" / f"{body}.py").exists():
        raise UsageError(f"{a.slug} has no part {body!r} to clone")
    name = a.name
    if not name:
        taken = set(st.part_names(a.slug))
        name, n = "Body", 0
        while name in taken:
            n += 1
            name = f"Body{n:03d}"
    path = pdir / "parts" / f"{name}.py"
    if path.exists():
        raise UsageError(f"{a.slug} already has a part {name!r}")
    material, process = "petg", "fdm"
    try:                                       # the source's material, as copyVisual copies its look
        mod = st._load_module(pdir / "parts" / f"{body}.py")
        material, process = getattr(mod, "MATERIAL", material) or material, getattr(mod, "PROCESS", process) or process
    except Exception:  # noqa: BLE001 - a source that does not load still gets its clone, which then says why
        pass
    path.write_text(CLONE_TEMPLATE.format(part=name, source=source, clone="Clone", material=material, process=process))
    un.record(pdir, "Create Clone", shlex.join(["cad", "feature", "clone", a.slug, source, "--name", name]),
              [{"path": path.relative_to(pdir).as_posix(), "before": None, "after": path.read_text()}], by=actor(a))
    from . import feature_edit as E
    doc = E.read(path)
    return Result(OK, {"project": a.slug, "part": name, "source": source, "file": str(path), "doc": doc},
                  f"{a.slug}/{name}: a new Body, a Clone of {source}", f"clone {source} as {name}", [str(path)])


def add_parser(add, fsub) -> None:
    """featurecmd.add_parsers hands its subparsers here."""
    sp = add("clone", cmd_feature_clone, "a new Body whose base is a Clone of another (FreeCAD's PartDesign_Clone): "
             "SOURCE is a part, or PART.FEATURE for one of its features", parent=fsub)
    sp.set_defaults(cmd_name="feature clone", feature_cmd="clone")
    sp.add_argument("slug")
    sp.add_argument("source")
    sp.add_argument("--name", help="the new Body's part name (default: the next free Body, Body001, ...)")
