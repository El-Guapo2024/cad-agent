# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It follows FreeCAD's CAM view providers (src/Mod/CAM/Path/Main/Gui/Job.py claimChildren,
# Path/Op/Gui/Base.py, Path/Tool/Gui/Controller.py, src/Mod/CAM/Gui/ViewProviderPath.cpp) and keeps FreeCAD's licence,
# the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../NOTICE.
"""A project's CAM jobs recomputed by FreeCAD's own CAM code (docs/EDITING_PLAN.md, "CAM in a project").

build(slug, jobs, shape_of) makes a document of the stand-in App (cad_agent/fcshim), one Part::Feature per part the
jobs machine (Name the part's module name, its shape the part's build() in its frame), replays each job file's JOB
list (cad_agent/cam_replay.py, the same code tests/golden/cam/make.py runs in FreeCAD) and recomputes. result()
gives the objects with their properties as the property view lists them, each op's Path, the tree, and the messages
FreeCAD's code wrote; post() runs a post-processor."""
from __future__ import annotations

import math
import re

from . import cam as C
from .cam_replay import Replayer, ReplayError, kind_of

ICONS = {"Job": "CAM_Job", "Stock": "CAM_Stock", "SetupSheet": "CAM_SetupSheet", "ToolBit": "CAM_ToolBit",
         "ToolController": "CAM_ToolController", "Profile": "CAM_Profile", "PocketShape": "CAM_Pocket",
         "MillFace": "CAM_Face", "Drilling": "CAM_Drilling", "Adaptive": "CAM_Adaptive", "DressupTag": "CAM_Dressup",
         "DressupDogbone": "CAM_Dressup"}
GROUP_ICONS = {"Operations": "CAM_OpActive", "Model": "CAM_BaseGeometry", "Tools": "CAM_ToolTable"}

CamBuildError = ReplayError


class CamDocument:
    def __init__(self, slug, jobs, shape_of):
        from . import cam_runtime
        cam_runtime.activate()
        import FreeCAD
        from cad_agent.fcshim import _fc_params
        _fc_params.reset()
        FreeCAD.Console.log.clear()
        self.FreeCAD = FreeCAD
        self.slug = slug
        self.jobs = jobs                      # [(job file name, [Entry])]
        self.shape_of = shape_of
        self.doc = FreeCAD.newDocument(re.sub(r"\W", "_", slug or "Unnamed") or "Unnamed")
        FreeCAD.setActiveDocument(self.doc.Name)
        self.models = {}
        for _, entries in jobs:
            if entries and entries[0].kind == "Job":
                parts = entries[0].props.get("Model") or []
                for p in [parts] if isinstance(parts, str) else parts:
                    self._model(p)
        self.r = Replayer(self.doc, self.models)
        self.made = self.r.made
        self.job_of = self.r.job_of

    def _model(self, part):
        if part in self.models:
            return self.models[part]
        import Part
        o = self.doc.addObject("Part::Feature", part)
        o.Label = part
        s = self.shape_of(part)
        o.Shape = Part.wrap(s) if not isinstance(s, Part.Shape) else s
        self.models[part] = o
        return o

    def replay(self, prune=True):
        for file, entries in self.jobs:
            self.r.replay(file, entries, prune)
        return self

    def build(self):
        self.replay()
        self.doc.recompute()
        return self

    # ── results ──
    def result(self):
        from cad_agent.fcshim import _fc_app as A
        models = set(id(m) for m in self.models.values())
        objs = [self.object_json(o, A) for o in self.doc.Objects if id(o) not in models]
        msgs = [{"kind": k, "text": t} for k, t in self.FreeCAD.Console.log if k in ("Err", "Wrn")]
        errors = [{"object": n, "error": str(e)} for n, e, _ in self.doc._errors]
        jobs = []
        for file, entries in self.jobs:
            job = self.made.get(entries[0].name) if entries else None
            if job is None:
                continue
            jobs.append({"file": file, "name": job.Name, "label": job.Label, "tree": self.tree(job),
                         "stock": _box(job.Stock.Shape.BoundBox) if job.Stock else None,
                         "model": [self.r.part_of(c) for c in job.Model.Group],
                         "operations": [op.Name for op in job.Operations.Group]})
        return {"jobs": jobs, "objects": objs, "messages": msgs, "errors": errors}

    def object_json(self, o, A):
        k = kind_of(o)
        props = []
        for name in o.PropertiesList:
            p = o._props[name]
            props.append({"name": name, "type": p.type, "group": p.group, "doc": p.doc,
                          "mode": sorted(p.modes), "value": self.value_json(p, A),
                          "enums": list(p.enums) if p.type == "App::PropertyEnumeration" else None,
                          "expression": o._exprs.get(name)})
        out = {"name": o.Name, "label": o.Label, "type": o.TypeId, "kind": k,
               "icon": ICONS.get(k or "") or GROUP_ICONS.get(re.sub(r"\d+$", "", o.Name)),
               "file": self.job_of.get(o.Name), "props": props, "valid": o.isValid(),
               "status": o.getStatusString() if not o.isValid() else None}
        if o.TypeId == "Path::FeaturePython" and "Path" in o._props:
            path = o._props["Path"].value
            if path is not None:
                out["commands"] = [[c.Name, dict(sorted(c._params.items()))] for c in path._cmds]
        return out

    def value_json(self, p, A):
        v, t = p.value, p.type
        if t in A.QUANTITY_TYPES:
            return {"value": v, "unit": list(p.unit.sig)}
        if t in A.LINK_TYPES:
            return v.Name if v is not None else None
        if t in A.LINKLIST_TYPES:
            return [x.Name for x in v]
        if t in A.LINKSUBLIST_TYPES:
            groups = []
            for x, sub in v:
                name = self.r.part_of(x)
                if not groups or groups[-1][0] != name:
                    groups.append([name, []])
                groups[-1][1].append(sub)
            return groups
        if t in A.LINKSUB_TYPES:
            return [self.r.part_of(v[0]), list(v[1])] if v else None
        if t == "App::PropertyPlacement":
            pl = v if v is not None else self.FreeCAD.Placement()
            return {"base": list(pl.Base), "rotation": list(pl.Rotation.Q)}
        if t in ("App::PropertyVector", "App::PropertyVectorDistance", "App::PropertyPosition",
                 "App::PropertyDirection"):
            return list(v) if v is not None else [0.0, 0.0, 0.0]
        if t == "App::PropertyVectorList":
            return [list(x) for x in v]
        if t == "Path::PropertyPath":
            return {"size": len(v._cmds)} if v is not None else {"size": 0}
        if t in ("Part::PropertyPartShape", "App::PropertyPythonObject", "App::PropertyExpressionEngine",
                 "Materials::PropertyMaterial"):
            return None
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        if isinstance(v, (list, tuple)):
            return [x if isinstance(x, (str, int, float, bool)) else repr(x) for x in v]
        if isinstance(v, dict):
            return dict(v)
        return repr(v)

    def tree(self, job):
        """The Job's branch of FreeCAD's tree (ViewProviderJob.claimChildren: Operations, Model, Stock, Tools; a tool
        controller claims its bit, a dress-up its base op)."""
        def node(o, children=()):
            k = kind_of(o)
            return {"name": o.Name, "label": o.Label, "kind": k,
                    "icon": ICONS.get(k or "") or GROUP_ICONS.get(re.sub(r"\d+$", "", o.Name)),
                    "children": list(children)}

        def op_node(op):
            base = op._props.get("Base")
            kids = []
            if base is not None and base.type == "App::PropertyLink" and base.value is not None:
                kids = [op_node(base.value)]
            return node(op, kids)
        ops = [op_node(op) for op in job.Operations.Group]
        tools = [node(tc, [node(tc.Tool)] if getattr(tc, "Tool", None) is not None else [])
                 for tc in job.Tools.Group]
        return node(job, [node(job.Operations, ops), node(job.Model, [node(c) for c in job.Model.Group]),
                          node(job.Stock), node(job.Tools, tools)])

    # ── G-code ──
    def post(self, job_name, post="linuxcnc", args=None):
        """CAM_Post on the job: the post-processor's export(), [(section, gcode)]."""
        from Path.Post.Processor import PostProcessorFactory
        job = self.made.get(job_name)
        if job is None:
            raise CamBuildError(f"there is no job {job_name!r}")
        if args is not None:
            job.PostProcessorArgs = args
        processor = PostProcessorFactory.get_post_processor(job, post)
        if processor is None:
            raise CamBuildError(f"{post!r} is not a post-processor FreeCAD has ({', '.join(C.POSTS)})")
        return processor.export() or []


def _box(bb):
    return [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax] if bb.isValid() else None


def toolpath(commands, start=(0.0, 0.0, 0.0)):
    """A Path's moves as polylines to draw, as ViewProviderPath tells rapid moves from feed moves: [(rapid,
    [points])]; arcs (G2/G3, centre relative) in segments of at most 10°, drill cycles (G81-G89) as their moves."""
    out = []
    x, y, z = start
    for name, p in commands:
        if name in ("G0", "G00", "G1", "G01"):
            nx, ny, nz = p.get("X", x), p.get("Y", y), p.get("Z", z)
            rapid = name in ("G0", "G00")
            if out and out[-1][0] == rapid:
                out[-1][1].append((nx, ny, nz))
            else:
                out.append((rapid, [(x, y, z), (nx, ny, nz)]))
            x, y, z = nx, ny, nz
        elif name in ("G2", "G02", "G3", "G03"):
            nx, ny, nz = p.get("X", x), p.get("Y", y), p.get("Z", z)
            cx, cy = x + p.get("I", 0.0), y + p.get("J", 0.0)
            a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
            sweep = a1 - a0
            if name in ("G2", "G02"):
                while sweep >= 0:
                    sweep -= 2 * math.pi
            else:
                while sweep <= 0:
                    sweep += 2 * math.pi
            r = math.hypot(x - cx, y - cy)
            n = max(2, int(math.ceil(abs(sweep) / math.radians(10))))
            pts = [(x, y, z)]
            for i in range(1, n + 1):
                a = a0 + sweep * i / n
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z + (nz - z) * i / n))
            pts[-1] = (nx, ny, nz)
            if out and out[-1][0] is False:
                out[-1][1].extend(pts[1:])
            else:
                out.append((False, pts))
            x, y, z = nx, ny, nz
        elif re.fullmatch(r"G8[1-9]", name):
            nx, ny = p.get("X", x), p.get("Y", y)
            r = p.get("R", z)
            bottom = p.get("Z", z)
            out.append((True, [(x, y, z), (nx, ny, z), (nx, ny, r)]))
            out.append((False, [(nx, ny, r), (nx, ny, bottom)]))
            out.append((True, [(nx, ny, bottom), (nx, ny, r)]))
            x, y, z = nx, ny, r
    return out


def build(slug, jobs, shape_of=None):
    if shape_of is None:
        from .techdraw_edit import shape_loader
        shape_of = shape_loader(slug)
    return CamDocument(slug, jobs, shape_of).build()
