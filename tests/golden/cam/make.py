"""Writes freecad.json: what FreeCAD's CAM makes of each case of cases.py, for tests/test_cam_golden.py to hold the
app's CAM (cad_agent/cam_doc.py over cad_agent/fcshim and the vendored CAM Python) to.

    $FREECAD/freecadcmd tests/golden/cam/make.py [CASE ...]     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root after prep.py. Each case gets a fresh document, a Part::Feature per part read from
breps/ (Name and Label the part's), and each job's entries replayed by cad_agent/cam_replay.py (the app's own replay,
which only calls FreeCAD's API: Path.Main.Job.Create, the tool bit dock's Add to Job, each op's and dress-up's
Create) then one recompute. Recorded: every Path object's commands (Name and Parameters), the names of the document's
objects in order, and each post-processor's export() with its arguments.
"""
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(os.getcwd())
HERE = ROOT / "tests" / "golden" / "cam"
if not (HERE / "breps").is_dir():
    sys.exit("run make.py from the repository's root, after prep.py")
sys.path.insert(0, str(ROOT))

import FreeCAD  # noqa: E402
import Part  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("cam_golden_cases", HERE / "cases.py")
cases_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases_mod)

from cad_agent import cam as C  # noqa: E402
from cad_agent.cam_replay import Replayer  # noqa: E402


def run(name, case):
    doc = FreeCAD.newDocument("golden")
    FreeCAD.setActiveDocument(doc.Name)
    models = {}
    for part in case["parts"]:
        o = doc.addObject("Part::Feature", part)
        o.Label = part
        o.Shape = Part.read(str(HERE / "breps" / f"{part}.brep"))
        models[part] = o
    doc.recompute()
    r = Replayer(doc, models)
    out = {"objects": [], "paths": {}, "posts": {}, "errors": []}
    try:
        for file, job in case["jobs"].items():
            r.replay(file, [C.Entry(k, n, p) for k, n, p in job])
        doc.recompute()
    except Exception:
        out["errors"].append(traceback.format_exc())
    out["objects"] = [[o.Name, o.TypeId, o.Label] for o in doc.Objects]
    for o in doc.Objects:
        if o.TypeId == "Path::FeaturePython" and hasattr(o, "Path"):
            out["paths"][o.Name] = [[c.Name, dict(c.Parameters)] for c in o.Path.Commands]
        if not o.isValid():
            out["errors"].append(f"{o.Name}: {o.getStatusString()}")
    from Path.Post.Processor import PostProcessorFactory
    for file in case["jobs"]:
        job = r.made[case["jobs"][file][0][1]]
        for post, args in case.get("posts", []):
            try:
                job.PostProcessorArgs = args
                res = PostProcessorFactory.get_post_processor(job, post).export()
                out["posts"][f"{file}/{post}"] = [[s, g] for s, g in (res or [])]
            except Exception:
                out["errors"].append(traceback.format_exc())
    FreeCAD.closeDocument(doc.Name)
    return out


def main(names):
    path = HERE / "freecad.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["_freecad"] = ".".join(FreeCAD.Version()[:3]) + " " + FreeCAD.Version()[3]
    for name, case in cases_mod.CASES.items():
        if names and name not in names:
            continue
        data[name] = run(name, case)
        print(name, {k: len(v) for k, v in data[name]["paths"].items()}, "errors", len(data[name]["errors"]))
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


main([a for a in sys.argv[1:] if not a.endswith(".py")])
