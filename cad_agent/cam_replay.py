# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It replays FreeCAD's CAM GUI commands (src/Mod/CAM/Path/Op/Gui/Base.py Create,
# Path/Dressup/Gui/Tags.py and DogboneII.py Create, Path/Tool/library/ui/dock.py _add_tool_controller,
# Path/Main/Gui/JobCmd.py) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your
# option) any later version; the text is in ../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit
# 3160daf1e2b6. See ../NOTICE.
"""A job file's JOB list replayed into a FreeCAD document by FreeCAD's own CAM Python, through FreeCAD's API only:
the same code runs in the real FreeCAD (tests/golden/cam/make.py, under freecadcmd) and over the app's stand-ins
(cad_agent/cam_doc.py), so the goldens hold the CAM code and the stand-ins, not this glue.

    r = Replayer(doc, models)          models: {part name: the Part::Feature holding its shape}
    r.replay(file, entries)            each entry made as FreeCAD's command makes it, then its properties set
"""
from __future__ import annotations

import importlib

from . import cam as C

LINK = ("App::PropertyLink", "App::PropertyLinkGlobal", "App::PropertyLinkHidden", "App::PropertyLinkChild")
LINKLIST = ("App::PropertyLinkList", "App::PropertyLinkListGlobal", "App::PropertyLinkListHidden",
            "App::PropertyLinkListChild")
LINKSUBLIST = ("App::PropertyLinkSubList", "App::PropertyLinkSubListGlobal", "App::PropertyLinkSubListHidden",
               "App::PropertyXLinkSubList")


class ReplayError(C.CamError):
    pass


def kind_of(obj):
    """The JOB kind of a document object, from its proxy's module (None for the Job's internals)."""
    p = getattr(obj, "Proxy", None)
    if p is None:
        return None
    mod = type(p).__module__
    if mod.startswith("Path.Tool.toolbit"):
        return "ToolBit"
    if mod == "Path.Main.Stock":
        return "Stock"
    for k, kind in C.KINDS.items():
        if kind.module and k != "ToolBit" and (mod == kind.module or mod.startswith(kind.module + ".")):
            return k
    return None


class Replayer:
    def __init__(self, doc, models):
        self.doc = doc
        self.models = models          # part -> Part::Feature
        self.clones = {}              # (job name, part) -> clone
        self.made = {}                # entry name -> object
        self.job_of = {}              # object name -> job file

    def replay(self, file, entries, prune=True):
        import Path.Main.Job as PathJob
        if not entries or entries[0].kind != "Job":
            raise ReplayError(f"cam/{file}.py: JOB starts with a Job entry")
        je = entries[0]
        parts = je.props.get("Model") or []
        if isinstance(parts, str):
            parts = [parts]
        if not parts:
            raise ReplayError(f"{je.name}: a Job needs the parts it machines (Model=[...])")
        missing = [p for p in parts if p not in self.models]
        if missing:
            raise ReplayError(f"{je.name}: {', '.join(missing)} is not a part of the project")
        before = {o.Name for o in self.doc.Objects}
        job = PathJob.Create(je.name, [self.models[p] for p in parts], None)
        self._check(job, je)
        auto = [o for o in self.doc.Objects if o.Name not in before]
        for o in auto:
            self.job_of[o.Name] = file
        for clone in job.Model.Group:
            objs = getattr(clone, "Objects", None) or []
            for p, m in self.models.items():
                if objs and objs[0] is m:
                    self.clones[(je.name, p)] = clone
        self.made[je.name] = job
        self.set_props(job, je, je.name, skip=("Model",))
        listed = {e.name for e in entries}
        for e in entries[1:]:
            obj = self.make(job, e)
            self.made[e.name] = obj
            self.job_of[obj.Name] = file
            self.set_props(obj, e, je.name)
        # what Job.Create made that the file does not list was deleted (its default tool controller and bit)
        for o in (auto if prune else []):
            k = kind_of(o)
            if k in ("ToolController", "ToolBit") and o.Name not in listed:
                if k == "ToolController" and o in job.Tools.Group:
                    job.Tools.removeObject(o)
                if k == "ToolBit":
                    body = getattr(o, "BitBody", None)
                    if body is not None:
                        self.doc.removeObject(body.Name)
                self.doc.removeObject(o.Name)
        return job

    def _check(self, obj, e):
        if e.name != "\x00" and obj.Name != e.name:
            raise ReplayError(f"{e.name}: FreeCAD names the {e.kind} {obj.Name} here (the file's names follow the "
                              "order FreeCAD's commands made the objects in)")

    def make(self, job, e):
        """The object for an entry: the one Job.Create made (Stock, SetupSheet, its default tool controller and
        bit) or a new one as FreeCAD's command makes it."""
        doc = self.doc
        if e.kind == "Stock":
            return job.Stock
        if e.kind == "SetupSheet":
            return job.SetupSheet
        existing = doc.getObject(e.name) if e.name != "\x00" else None
        if existing is not None and self.job_of.get(e.name) and e.kind in ("ToolController", "ToolBit"):
            return existing
        if e.kind == "ToolBit":
            obj = self._toolbit(e)
        elif e.kind == "ToolController":
            obj = self._tool_controller(job, e)
        else:
            kind = C.KINDS[e.kind]
            mod = importlib.import_module(kind.module)
            if kind.op:
                # Op/Gui/Base.py Create: res.objFactory(res.name, obj=None, parentJob=res.job)
                obj = mod.Create(C.DEFAULT_NAMES[e.kind], obj=None, parentJob=job)
            else:
                base = self.made.get(e.props.get("Base")) or doc.getObject(e.props.get("Base") or "")
                if base is None:
                    raise ReplayError(f"{e.name}: Base {e.props.get('Base')!r} is not an operation of {job.Name}")
                # the base op's task panel was accepted and the document recomputed before the dress-up's command
                doc.recompute()
                if e.kind == "DressupDogbone":
                    # Dressup/Gui/DogboneII.py Create: DogboneII.Create, then the job's addOperation(obj, base)
                    obj = mod.Create(base, C.DEFAULT_NAMES[e.kind])
                    import PathScripts.PathUtils as PathUtils
                    PathUtils.findParentJob(base).Proxy.addOperation(obj, base)
                else:
                    obj = mod.Create(base, C.DEFAULT_NAMES[e.kind])
                # the dress-up's view provider, attached as the GUI makes it (DogboneII.py ViewProviderDressup.attach,
                # Tags.py PathDressupTagViewProvider.attach): the base op leaves every group it is in, so the job posts
                # the dress-up and not its base as well
                for parent in base.InList:
                    if hasattr(parent, "Group") and base.Name in [o.Name for o in parent.Group]:
                        parent.Group = [o for o in parent.Group if o.Name != base.Name]
        if obj is None:
            raise ReplayError(f"{e.name}: FreeCAD did not make the {e.kind}")
        self._check(obj, e)
        return obj

    def _toolbit(self, e):
        from Path.Tool.toolbit import ToolBit
        bit, shape = e.props.get("Bit"), e.props.get("ShapeID")
        if bit:
            from Path.Tool.camassets import cam_assets
            from Path.Tool.assets import AssetUri
            tb = cam_assets.get(AssetUri.build(asset_type="toolbit", asset_id=bit))
        elif shape:
            tb = ToolBit.from_shape_id(f"{shape}.fcstd")
        else:
            raise ReplayError(f"{e.name}: a ToolBit is a library bit (Bit=\"5mm_Endmill\") or a shape "
                              "(ShapeID=\"endmill\")")
        return tb.attach_to_doc(self.doc)

    def _tool_controller(self, job, e):
        """ToolBitLibraryDock._add_tool_controller: TC: <bit's label>, numbered, added to the job."""
        import Path.Tool.Controller as PathToolController
        tool = self.made.get(e.props.get("Tool")) or self.doc.getObject(e.props.get("Tool") or "")
        if tool is None:
            raise ReplayError(f"{e.name}: Tool {e.props.get('Tool')!r} is not a tool bit of {job.Name}")
        number = e.props.get("ToolNumber") or job.Proxy.nextToolNumber()
        tc = PathToolController.Create(f"TC: {tool.Label}", tool, int(number))
        job.Proxy.addToolController(tc)
        return tc

    def resolve(self, obj, prop, v, job):
        """A file value as the property takes it: names of objects as the objects, (part, [subs]) as the job's
        clone of the part with its sub-elements."""
        t = obj.getTypeIdOfProperty(prop)
        if t in LINK:
            if v is None:
                return None
            o = self.made.get(v) or self.doc.getObject(v)
            if o is None:
                raise ReplayError(f"{obj.Name}.{prop}: {v!r} is not an object of the document")
            return o
        if t in LINKLIST:
            out = []
            for x in v or []:
                o = self.made.get(x) or self.doc.getObject(x)
                if o is None:
                    raise ReplayError(f"{obj.Name}.{prop}: {x!r} is not an object of the document")
                out.append(o)
            return out
        if t in LINKSUBLIST:
            out = []
            for item in v or []:
                if isinstance(item, str):
                    item = (item, [""])
                o, subs = item
                target = self.clones.get((job, o)) or self.made.get(o) or self.doc.getObject(o)
                if target is None:
                    raise ReplayError(f"{obj.Name}.{prop}: {o!r} is not a part of {job} or an object")
                out.append((target, [subs] if isinstance(subs, str) else list(subs)))
            return out
        return v

    def set_props(self, obj, e, job, skip=()):
        for k, v in e.props.items():
            if k in skip or (e.kind == "ToolBit" and k in ("Bit", "ShapeID")):
                continue
            if k == "ExpressionEngine":
                for path, expr in (v or {}).items():
                    obj.setExpression(path, expr)
                continue
            if k not in obj.PropertiesList:
                raise ReplayError(f"{e.name}: {k} is not a property of a {e.kind}")
            if any(p == k for p, _ in obj.ExpressionEngine):
                obj.setExpression(k, None)
            try:
                setattr(obj, k, self.resolve(obj, k, v, job))
            except (TypeError, ValueError) as err:
                raise ReplayError(f"{e.name}.{k} = {v!r}: {err}") from None

    def part_of(self, obj):
        for (_, part), c in self.clones.items():
            if c is obj:
                return part
        for part, o in self.models.items():
            if o is obj:
                return part
        return obj.Name
