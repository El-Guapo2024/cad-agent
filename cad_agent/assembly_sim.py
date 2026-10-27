# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's simulations (src/Mod/Assembly/CommandCreateSimulation.py, Copyright (c) 2024 Ondsel
# <development@ondsel.com>): Simulation (aTimeStart, bTimeEnd, cTimeStepOutput, fGlobalErrorTolerance,
# jFramesPerSecond and its Group of motions), Motion (Joint, MotionType, Formula, ViewProviderMotion.updateLabel),
# TaskAssemblyCreateSimulation's create and accept, MotionEditDialog's joints and motion types, and
# UtilsAssembly.getSimulationGroup. The run itself is AssemblyObject::generateSimulation's, in ui/ondsel.
"""Simulations of an Assembly: Assembly_CreateSimulation's objects in a project's ASSEMBLY.

    Assembly.SimulationGroup("Simulations"),
    Assembly.Simulation("Simulation", group=["Motion"]),
    Assembly.Motion("Motion", joint="Joint", formula="initialValue + 5*time", label="Revolute (Angular)"),

A Motion drives a joint (a Revolute or Cylindrical by an angle in radians, a Slider or Cylindrical by a length in mm) by
its Formula of `time` (OndselSolver's expression language; `initialValue` is the joint's angle or distance as the parts
are). The Simulation runs its motions from aTimeStart to bTimeEnd, a frame every cTimeStepOutput seconds, the joints'
limits left out (AssemblyObject::makeMbdJoint adds no limit while there are motions); nothing moves in the document.
"""
from __future__ import annotations

from . import assembly_wb as W

MOTION_TYPES = ["Angular", "Linear"]
JOINTS_DRIVEN = ["Revolute", "Slider", "Cylindrical"]      # MotionEditDialog.setup_joint_combo


class SimulationGroup(W.AsmObject):
    """Assembly::SimulationGroup, "Simulations" (getSimulationGroup makes it)."""
    kind = "SimulationGroup"
    TYPE_ID = "Assembly::SimulationGroup"
    POS = ()
    DEFAULTS = {"label": None}

    def references(self):
        return []


class Simulation(W.AsmObject):
    """CommandCreateSimulation.Simulation: the times, the tolerance, the frame rate and the motions (Group)."""
    kind = "Simulation"
    TYPE_ID = "App::FeaturePython"
    PROXY = "Simulation"
    POS = ()
    DEFAULTS = {"group": (), "a_time_start": 0.0, "b_time_end": 1.0, "c_time_step_output": 1.0e-2,
                "f_global_error_tolerance": 1.0e-6, "j_frames_per_second": 30, "label": None}
    TRANSACTION = "Create Simulation"

    def normalize(self, key, v):
        if key == "group":
            return tuple([v] if isinstance(v, str) else (v or ()))
        if key in ("a_time_start", "b_time_end", "c_time_step_output", "f_global_error_tolerance"):
            return float(v)
        if key == "j_frames_per_second":
            return int(v)
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key == "group":
            return list(v)
        return super().source_value(key, v)

    def references(self):
        return []


class Motion(W.AsmObject):
    """CommandCreateSimulation.Motion: Joint, MotionType (Angular, Linear), Formula."""
    kind = "Motion"
    TYPE_ID = "App::FeaturePython"
    PROXY = "Motion"
    POS = ()
    DEFAULTS = {"joint": None, "motion_type": "Angular", "formula": "", "label": None}

    def validate(self):
        if self.motion_type not in MOTION_TYPES:
            raise W.AssemblyError(f"{self.name}: {self.motion_type!r} is not a MotionType ({', '.join(MOTION_TYPES)})")

    def references(self):
        return [self.joint] if self.joint else []


def simulations(doc) -> list[Simulation]:
    return [o for o in doc.objects if isinstance(o, Simulation)]


def motions_of(doc, sim: Simulation) -> list[Motion]:
    return [o for o in (doc.get(n) for n in sim.group) if isinstance(o, Motion)]


def drivable_joints(doc) -> list:
    """getJointsOfType(assembly, ["Revolute", "Slider", "Cylindrical"]): what a motion can drive."""
    return [j for j in doc.objects if isinstance(j, W.Joint) and j.joint_type in JOINTS_DRIVEN]


def motion_types(joint) -> list[str]:
    """MotionEditDialog.setup_motiontype_combo: a Revolute turns, a Slider slides, a Cylindrical does either."""
    if joint.joint_type == "Revolute":
        return ["Angular"]
    if joint.joint_type == "Slider":
        return ["Linear"]
    return ["Angular", "Linear"]


def motion_label(doc, m: Motion) -> str:
    """ViewProviderMotion.updateLabel: "<the joint's Label> (Angular)"."""
    j = doc.get(m.joint)
    if j is None:
        return m.label or m.name
    return f"{j.label or j.name} ({'Linear' if m.motion_type == 'Linear' else 'Angular'})"


def ensure_group(doc) -> SimulationGroup:
    for o in doc.objects:
        if isinstance(o, SimulationGroup):
            return o
    g = SimulationGroup(W.unique_name(doc.all_names(), "Simulations"))
    doc.objects.append(g)
    return g


def set_simulation(doc, settings: dict, motions: list[dict], name: str | None = None) -> Simulation:
    """TaskAssemblyCreateSimulation's OK: the Simulation made (createSimulationObject, in the SimulationGroup) or the
    one double-clicked, its settings, its motions as the panel left them (createMotionObject: each a "Motion" in the
    Assembly, labelled updateLabel's way), the ones the panel deleted removed."""
    if name is None:
        ensure_group(doc)
        sim = Simulation(W.unique_name(doc.all_names(), "Simulation"))
        doc.objects.append(sim)
    else:
        sim = doc.get(name)
        if not isinstance(sim, Simulation):
            raise W.AssemblyError(f"there is no simulation {name!r}")
    for k, v in (settings or {}).items():
        if k not in Simulation.DEFAULTS or k in ("group", "label"):
            raise W.AssemblyError(f"{k} is not a setting of a Simulation")
        setattr(sim, k, sim.normalize(k, v))
    old = {m.name: m for m in motions_of(doc, sim)}
    keep = []
    for d in motions:
        j = doc.get(d.get("joint"))
        if not isinstance(j, W.Joint) or j.joint_type not in JOINTS_DRIVEN:
            raise W.AssemblyError(f"{d.get('joint')!r} is not a Revolute, Slider or Cylindrical joint to drive")
        m = old.get(d.get("name")) if d.get("name") else None
        if m is None:
            m = Motion(W.unique_name(doc.all_names(), "Motion"))
            doc.objects.append(m)
        m.joint = j.name
        m.motion_type = d.get("motion_type") or motion_types(j)[0]
        if m.motion_type not in motion_types(j):
            raise W.AssemblyError(f"a {j.joint_type} joint takes {' or '.join(motion_types(j))} motions")
        m.formula = d.get("formula", "initialValue + 5*time")
        m.label = motion_label(doc, m)
        keep.append(m.name)
    for n, m in old.items():
        if n not in keep:
            doc.objects.remove(m)
    sim.group = tuple(keep)
    return sim


def delete_simulation(doc, sim: Simulation):
    """ViewProviderSimulation.onDelete: its motions go with it."""
    for m in motions_of(doc, sim):
        doc.objects.remove(m)
    doc.objects.remove(sim)


def run(doc, sim: Simulation) -> dict:
    """TaskAssemblyCreateSimulation.runKinematics: generateSimulation(sim), then the frames (updateForFrame): {"status",
    "frames": [{component: placement}], "times": [s, ...], ...}."""
    from . import ondsel
    sdoc = doc.solver_doc()
    sdoc["motions"] = [{"name": m.name, "joint": m.joint, "type": m.motion_type, "formula": m.formula}
                       for m in motions_of(doc, sim)]
    sdoc["simulation"] = {"start": sim.a_time_start, "end": sim.b_time_end, "step": sim.c_time_step_output,
                          "tolerance": sim.f_global_error_tolerance}
    out = ondsel.simulate(sdoc)
    # onFrameChanged: frame i is at i * cTimeStepOutput
    out["times"] = [k * sim.c_time_step_output for k in range(len(out.get("frames", [])))]
    return out


W.CLASSES[SimulationGroup.kind] = SimulationGroup
W.CLASSES[Simulation.kind] = Simulation
W.CLASSES[Motion.kind] = Motion
W.SimulationGroup, W.Simulation, W.Motion = SimulationGroup, Simulation, Motion
