"""Writes freecad.json: what FreeCAD's Assembly workbench does with each case of cases.py, for
tests/test_assembly_golden.py to hold cad_agent/assembly_wb.py and ui/ondsel to.

    $FREECAD/freecadcmd tests/golden/assembly/make.py [CASE]     (FREECAD: FreeCAD's bin folder, 26.3 at 3160daf1e2b6)

Run it from the repository's root. Each case gets a fresh document, "Unnamed" as FreeCAD names a new one: its parts
(cad_agent.feature_part.to_freecad), an Assembly with its JointGroup "Joints" as Assembly_CreateAssembly makes them,
an App::Link per component and the GroundedJoints (CommandInsertLink's accept and createGroundedJoint, then the
document recomputed), then the steps, each replayed as the GUI's command makes it (cases.py says how). After each
step every component's Placement (Base and Rotation.Q), each joint's References, Placement1/2 and limits, and what
FreeCAD printed (the solver's lines and the Console's warnings, stdout and stderr caught) are recorded; at the end
assembly.solve()'s return and exportAsASMT's file.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.getcwd())
if not (ROOT / "cad_agent" / "feature.py").exists():
    sys.exit("run make.py from the repository's root")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden" / "assembly"))

import FreeCAD as App  # noqa: E402
import JointObject  # noqa: E402
import UtilsAssembly  # noqa: E402

from cad_agent import feature_part as Part  # noqa: E402
from cases import CASES  # noqa: E402

V = App.Vector
PROPS = {"distance": "Distance", "distance2": "Distance2", "angle": "Angle", "offset1": "Offset1",
         "offset2": "Offset2", "enable_length_min": "EnableLengthMin", "enable_length_max": "EnableLengthMax",
         "enable_angle_min": "EnableAngleMin", "enable_angle_max": "EnableAngleMax", "length_min": "LengthMin",
         "length_max": "LengthMax", "angle_min": "AngleMin", "angle_max": "AngleMax", "suppressed": "Suppressed",
         "detach1": "Detach1", "detach2": "Detach2"}


def plc(p):
    if p is None:
        return App.Placement()
    pos, ypr = p
    return App.Placement(V(*pos), App.Rotation(*ypr))


def value(prop, v):
    return plc(v) if prop in ("offset1", "offset2") else v


def plc_json(p):
    return [p.Base.x, p.Base.y, p.Base.z, *p.Rotation.Q]


def q(v):
    return v.Value if hasattr(v, "Value") else v


class Capture:
    """stdout and stderr, at the file descriptors (the solver writes with std::cout, the Console with fprintf)."""

    def __enter__(self):
        sys.stdout.flush()
        sys.stderr.flush()
        self.f = tempfile.TemporaryFile(mode="w+b")
        self.saved = os.dup(1), os.dup(2)
        os.dup2(self.f.fileno(), 1)
        os.dup2(self.f.fileno(), 2)
        return self

    def __exit__(self, *exc):
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(self.saved[0], 1)
        os.dup2(self.saved[1], 2)
        os.close(self.saved[0])
        os.close(self.saved[1])
        self.f.seek(0)
        self.text = self.f.read().decode(errors="replace").replace(os.path.normpath(App.getHomePath()) + "/", "<FreeCAD>/")
        self.f.close()


def state(asm, jg, links):
    joints = {}
    rigid = {}
    for j in jg.Group:
        if hasattr(j, "ObjectsToRigidGroup"):
            rigid[j.Name] = {"label": j.Label, "members": [o.Name for o in j.ObjectsToRigidGroup],
                             "rigid_placements": [plc_json(p) for p in j.RigidPlacements], "suppressed": j.Suppressed}
            continue
        if not hasattr(j, "JointType"):
            continue

        def ref(r):
            return None if r is None else [r[0].Name, list(r[1])]
        joints[j.Name] = {
            "label": j.Label, "type": j.JointType, "reference1": ref(j.Reference1), "reference2": ref(j.Reference2),
            "placement1": plc_json(j.Placement1), "placement2": plc_json(j.Placement2),
            "offset1": plc_json(j.Offset1), "offset2": plc_json(j.Offset2),
            "distance": q(j.Distance), "distance2": q(j.Distance2), "angle": q(j.Angle),
            "enable_length_min": j.EnableLengthMin, "enable_length_max": j.EnableLengthMax,
            "enable_angle_min": j.EnableAngleMin, "enable_angle_max": j.EnableAngleMax,
            "length_min": q(j.LengthMin), "length_max": q(j.LengthMax), "angle_min": q(j.AngleMin),
            "angle_max": q(j.AngleMax), "suppressed": j.Suppressed}
    out = {"placements": {n: plc_json(l.Placement) for n, l in links.items()}, "joints": joints}
    if rigid:
        out["rigid_groups"] = rigid
    return out


def accept(asm, joint):
    """TaskAssemblyCreateJoint.accept: generatePropertySettings's commands, then assembly.recompute(True)."""
    exec(UtilsAssembly.generatePropertySettings(joint), {"App": App})
    asm.recompute(True)


def run(name, c):
    doc = App.newDocument("Unnamed")
    App.setActiveDocument(doc.Name)
    sources = {}
    for pname, objs in c["parts"].items():
        made = Part.to_freecad(objs, doc=doc)
        sources[pname] = made[objs[-1].name]
    doc.recompute()
    asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
    asm.Type = "Assembly"                       # Assembly_CreateAssembly sets it; JointObject solves only then
    jg = asm.newObject("Assembly::JointGroup", "Joints")
    links = {}
    for lname, pname, p in c["components"]:
        link = asm.newObject("App::Link", lname)
        link.LinkedObject = sources[pname]
        link.Label = lname
        if p is not None:
            link.Placement = plc(p)
        links[lname] = link
    for g in c["ground"]:
        gj = jg.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(gj, links[g])
    with Capture() as cap:
        doc.recompute()
    out = {"names": {n: l.Name for n, l in links.items()}, "steps": []}

    def target(name):
        """A reference's moving part: a component, or the Assembly's Origin (a pick on one of its features)."""
        return asm.Origin if name == "Origin" else links[name]
    for step in c["steps"]:
        with Capture() as cap:
            if step["op"] == "joint":
                t = step["type"]
                j = jg.newObject("App::FeaturePython", "Joint")
                j.Label = t
                JointObject.Joint(j, JointObject.JointTypes.index(t))
                j.purgeTouched()
                if t in JointObject.JointNoNegativeDistance:      # adaptUi
                    if j.Distance == 0.0:
                        j.Distance = 1.0
                    if t in ("Gears", "Belt") and j.Distance2 == 0.0:
                        j.Distance2 = 1.0
                r1 = [target(step["ref1"][0]), list(step["ref1"][1])]
                r2 = [target(step["ref2"][0]), list(step["ref2"][1])]
                j.Proxy.setJointConnectors(j, [r1])
                j.Proxy.setJointConnectors(j, [r1, r2])
                for k, v in step["props"].items():
                    setattr(j, PROPS[k], value(k, v))
                accept(asm, j)
            elif step["op"] == "set":
                j = doc.getObject(step["joint"])
                setattr(j, PROPS[step["prop"]], value(step["prop"], step["value"]))
                doc.recompute()
            elif step["op"] == "reverse":
                j = doc.getObject(step["joint"])
                j.Proxy.flipOnePart(j)
                accept(asm, j)
            elif step["op"] == "move":
                links[step["link"]].Placement = plc(step["placement"])
                doc.recompute()
            elif step["op"] == "rigid":
                # CommandCreateJointRigidGroup.Activated: createJointRigidGroupJoint(parts), then the recompute
                rg = jg.newObject("App::FeaturePython", "RigidGroupJoint")
                JointObject.RigidGroupJoint(rg, [links[n] for n in step["parts"]])
                doc.recompute()
            elif step["op"] == "update_rigid":
                # ViewProviderRigidGroupJoint's "Update Stored Positions"
                j = doc.getObject(step["joint"])
                j.Proxy.updateStoredPositions(j)
                doc.recompute()
            elif step["op"] == "suppress":
                doc.getObject(step["joint"]).Suppressed = step["value"]
                doc.recompute()
            else:
                raise ValueError(step["op"])
        out["steps"].append({**state(asm, jg, links), "printed": cap.text})
    with Capture() as cap:
        out["solve"] = asm.solve()
    out["solve_printed"] = cap.text
    out["after_solve"] = state(asm, jg, links)
    fd, path = tempfile.mkstemp(suffix=".asmt")
    os.close(fd)
    with Capture():
        asm.exportAsASMT(path)
    out["asmt"] = Path(path).read_text()
    os.remove(path)
    App.closeDocument(doc.Name)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.endswith(".py")]
    path = Path(__file__).with_name("freecad.json")
    old = json.loads(path.read_text()) if path.exists() and args else {}
    names = args or list(CASES)
    out = {"freecad": App.Version()[:4], "cases": dict(old.get("cases", {}))}
    for n in names:
        try:
            out["cases"][n] = run(n, CASES[n])
        except Exception as e:                  # a case FreeCAD refuses: its message is the answer
            out["cases"][n] = {"error": f"{type(e).__name__}: {e}"}
            for d in list(App.listDocuments()):
                App.closeDocument(d)
        print("made", n, file=sys.stderr)
    out["cases"] = {n: out["cases"][n] for n in CASES if n in out["cases"]}
    path.write_text(json.dumps(out, indent=1, sort_keys=False) + "\n")


main()
