# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's assembly snapshots (src/Mod/Assembly/CommandCreateSnapshot.py, Copyright (c) 2026 AstoCAD):
# CommandCreateSnapshot (IsActive, Activated), Snapshot (ensureProperties, captureState, restoreState),
# ViewProviderSnapshot.doubleClicked, and UtilsAssembly.getSnapshotGroup.
"""Snapshots of an Assembly: Assembly_CreateSnapshot's objects in a project's ASSEMBLY.

    Assembly.SnapshotGroup("Snapshots"),
    Assembly.Snapshot("Snapshot", components=["Plate", "Pin"], placements=[((0, 0, 0), (0, 0, 0, 1)), ...],
                      visibilities=[True, True]),

A Snapshot holds each movable part's Placement and Visibility as they were when it was made (captureState over
getMovablePartsWithin(assembly, partsAsSolid=True)); a double click on it puts them back, then recomputes the Assembly
(the solve) when SolveOnActivation is set.
"""
from __future__ import annotations

from . import assembly_wb as W


class SnapshotGroup(W.AsmObject):
    """Assembly::SnapshotGroup, "Snapshots" (getSnapshotGroup makes it)."""
    kind = "SnapshotGroup"
    TYPE_ID = "Assembly::SnapshotGroup"
    POS = ()
    DEFAULTS = {"label": None}

    def references(self):
        return []


class Snapshot(W.AsmObject):
    """CommandCreateSnapshot.Snapshot: Components, Placements, Visibilities, SolveOnActivation."""
    kind = "Snapshot"
    TYPE_ID = "App::FeaturePython"
    PROXY = "Snapshot"
    POS = ()
    DEFAULTS = {"components": (), "placements": (), "visibilities": (), "solve_on_activation": True, "label": None}
    TRANSACTION = "Create Snapshot"

    def normalize(self, key, v):
        if key == "components":
            return tuple([v] if isinstance(v, str) else (v or ()))
        if key == "placements":
            return tuple(W.placement_literal(W.to_placement(p)) for p in (v or ()))
        if key == "visibilities":
            return tuple(bool(x) for x in (v or ()))
        if key == "solve_on_activation":
            return bool(v)
        return super().normalize(key, v)

    def source_value(self, key, v=None):
        v = getattr(self, key) if v is None else v
        if key in ("components", "visibilities"):
            return list(v)
        if key == "placements":
            return list(v)
        return super().source_value(key, v)

    def references(self):
        return list(self.components)


def snapshots(doc) -> list[Snapshot]:
    return [o for o in doc.objects if isinstance(o, Snapshot)]


def ensure_group(doc) -> SnapshotGroup:
    for o in doc.objects:
        if isinstance(o, SnapshotGroup):
            return o
    g = SnapshotGroup(W.unique_name(doc.all_names(), "Snapshots"))
    doc.objects.append(g)
    return g


def _visible(doc, name) -> bool:
    o = doc.get(name)
    return bool(getattr(o, "visibility", True)) if o is not None else True


def create_snapshot(doc, name: str | None = None) -> Snapshot:
    """CommandCreateSnapshot.Activated: a Snapshot in the SnapshotGroup with every movable part's Placement and
    Visibility (getMovablePartsWithin, partsAsSolid: a rigid sub-assembly as one, a flexible one's children)."""
    if not doc.solver_parts():
        raise W.AssemblyError("Snapshot needs an active Assembly with at least one part")
    ensure_group(doc)
    s = Snapshot(name or W.unique_name(doc.all_names(), "Snapshot"))
    parts = [p for p in doc.solver_parts() if p in doc.plc]
    s.components = tuple(parts)
    s.placements = tuple(W.placement_literal(doc.plc[p]) for p in parts)
    s.visibilities = tuple(_visible(doc, p) for p in parts)
    doc.objects.append(s)
    return s


def restore_snapshot(doc, s: Snapshot):
    """Snapshot.restoreState: each captured part's Placement and Visibility put back, then the Assembly recomputed when
    SolveOnActivation is set."""
    n = min(len(s.components), len(s.placements), len(s.visibilities))
    if not s.components:
        doc.messages.append(("warning", "Snapshot has no captured components to restore."))
        return
    for i in range(n):
        part = s.components[i]
        if part not in doc.plc:
            continue
        doc.plc[part] = W.to_placement(s.placements[i])
        o = doc.get(part)
        if o is not None and hasattr(o, "visibility"):
            o.visibility = s.visibilities[i]
    if s.solve_on_activation:
        doc.recompute()


W.CLASSES[SnapshotGroup.kind] = SnapshotGroup
W.CLASSES[Snapshot.kind] = Snapshot
W.SnapshotGroup, W.Snapshot = SnapshotGroup, Snapshot
