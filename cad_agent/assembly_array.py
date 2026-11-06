# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's link arrays (src/Mod/Part/App/LinkArray.cpp and LinkArrayLinear.cpp, Copyright (c)
# 2026 Boyer Pierre-Louis; LinkArrayPolar.cpp, Copyright (c) 2026 FreeCAD Project Association; their pattern arithmetic
# is LinearPatternExtension and PolarPatternExtension's, ported in cad_agent/feature_transform.py; the circular one,
# CircularPatternExtension.cpp, no copyright line, is ported here) and
# Part_LinkArrayLinear / Part_LinkArrayPolar's activateLinkArrayCommand (src/Mod/Part/Gui/Command.cpp, Copyright (c)
# 2002 Jürgen Riegel).
"""Link arrays of an Assembly: Part_LinkArrays' Linear and Polar Link Array in a project's ASSEMBLY.

    Assembly.LinkArrayLinear("LinearLinkArray", "pin", direction="X_Axis", occurrences=3, length=40),
    Assembly.LinkArrayPolar("PolarLinkArray", "bolt", axis="Z_Axis", occurrences=6),

An array is a component (an App::Link with ElementCount elements, UtilsAssembly.isLinkArray): the solver moves it as one
body, its part repeated at each element's placement (LinkArray::getElementPlacements, then syncGeneratedElementPlacements
writes them onto the elements). A direction or axis is a role of the Assembly's Origin ("X_Axis", "Y_Axis", "Z_Axis");
none is X (the second direction Y) for a linear array, Z for a polar one, as LinkArrayLinear's
calculateOffsetVectorWithDefault and LinkArrayPolar::getRotation default them.
"""
from __future__ import annotations

from . import assembly_wb as W

AXES = ("X_Axis", "Y_Axis", "Z_Axis")
MODES = ("Extent", "Spacing")


class LinkArray(W.Link):
    """Part::LinkArray: an App::Link whose elements are its part at the placements the pattern computes."""
    PATTERN: dict = {}

    def validate(self):
        super().validate()
        for k in self.REF_KEYS:
            v = getattr(self, k)
            if v is not None and v not in AXES:
                raise W.AssemblyError(f"{self.name}: {k} is one of the Origin's axes ({', '.join(AXES)}), not {v!r}")
        for k in ("mode", "mode2"):
            if k in self.DEFAULTS and getattr(self, k) not in MODES:
                raise W.AssemblyError(f"{self.name}: {k} {getattr(self, k)!r} is not one of {', '.join(MODES)}")

    def pattern(self):
        raise NotImplementedError

    def element_placements(self) -> list:
        """getElementPlacements: each element's Placement in the array (Placement first, then each of them)."""
        from . import feature  # noqa: F401  (feature_transform is imported through it)
        from . import feature as F
        from .attacher import Placement
        try:
            trsfs = self.pattern().get_transformations({}, {}, [])
        except F.FeatureError as e:
            raise W.AssemblyError(f"{self.name}: {e}") from None
        return [Placement.from_trsf(t) for t in trsfs]

    def shape(self, base):
        """The array as the solver and the 3D view see it: base at every element placement, one compound."""
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.TopoDS import TopoDS_Compound
        comp = TopoDS_Compound()
        b = BRep_Builder()
        b.MakeCompound(comp)
        for p in self.element_placements():
            b.Add(comp, BRepBuilderAPI_Transform(base, p.trsf(), True).Shape())
        return comp


class LinkArrayLinear(LinkArray):
    """Part::LinkArrayLinear (Part_LinkArrayLinear, "Linear Link Array")."""
    kind = "LinkArrayLinear"
    TYPE_ID = "Part::LinkArrayLinear"
    REF_KEYS = ("direction", "direction2")
    DEFAULTS = {**W.Link.DEFAULTS, "direction": None, "reversed": False, "mode": "Extent", "length": 100.0,
                "offset": 10.0, "spacings": (-1.0,), "spacing_pattern": (0.0,), "occurrences": 2,
                "direction2": None, "reversed2": False, "mode2": "Extent", "length2": 100.0, "offset2": 10.0,
                "spacings2": (0.0,), "spacing_pattern2": (0.0,), "occurrences2": 1}
    TRANSACTION = "Linear Link Array"

    def pattern(self):
        from . import feature_transform as FT
        # calculateOffsetVectorWithDefault: no direction is X (the second Y)
        return FT.LinearPattern(self.name, direction=self.direction or "X_Axis",
                                direction2=self.direction2 or "Y_Axis",
                                **{k: getattr(self, k) for k in ("reversed", "mode", "length", "offset", "occurrences",
                                                                 "reversed2", "mode2", "length2", "offset2",
                                                                 "occurrences2")},
                                spacings=tuple(self.spacings), spacing_pattern=tuple(self.spacing_pattern),
                                spacings2=tuple(self.spacings2), spacing_pattern2=tuple(self.spacing_pattern2))


class LinkArrayPolar(LinkArray):
    """Part::LinkArrayPolar (Part_LinkArrayPolar, "Polar Link Array")."""
    kind = "LinkArrayPolar"
    TYPE_ID = "Part::LinkArrayPolar"
    REF_KEYS = ("axis",)
    DEFAULTS = {**W.Link.DEFAULTS, "axis": None, "reversed": False, "mode": "Extent", "angle": 360.0,
                "offset": 120.0, "spacings": (-1.0, -1.0), "spacing_pattern": (0.0,), "occurrences": 3}
    TRANSACTION = "Polar Link Array"

    def pattern(self):
        from . import feature_transform as FT
        # getRotation: no axis is gp_Ax2(), the Z axis through the origin
        return FT.PolarPattern(self.name, axis=self.axis,
                               **{k: getattr(self, k) for k in ("reversed", "mode", "angle", "offset", "occurrences")},
                               spacings=tuple(self.spacings), spacing_pattern=tuple(self.spacing_pattern))


class LinkArrayCircular(LinkArray):
    """Part::LinkArrayCircular (Part_LinkArrayCircular, "Circular Link Array"): concentric circles about an axis,
    CircularPatternExtension::calculateTransformations."""
    kind = "LinkArrayCircular"
    TYPE_ID = "Part::LinkArrayCircular"
    REF_KEYS = ("axis",)
    DEFAULTS = {**W.Link.DEFAULTS, "axis": None, "radial_distance": 50.0, "tangential_distance": 25.0,
                "number_circles": 3, "symmetry": 1}
    TRANSACTION = "Circular Link Array"
    MAXIMUM_OCCURRENCES = 10000          # PatternConstants::MaximumOccurrences

    def element_placements(self) -> list:
        import math
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
        from .attacher import Placement
        radial, tangential = float(self.radial_distance), float(self.tangential_distance)
        circles, symmetry = int(self.number_circles), max(1, int(self.symmetry))
        conf = 1e-7
        if not math.isfinite(radial) or radial <= conf:
            raise W.AssemblyError(f"{self.name}: Radial distance must be greater than zero")
        if not math.isfinite(tangential) or tangential <= conf:
            raise W.AssemblyError(f"{self.name}: Tangential distance must be greater than zero")
        if circles < 2:
            raise W.AssemblyError(f"{self.name}: At least two concentric circles are required")
        if circles > self.MAXIMUM_OCCURRENCES:
            raise W.AssemblyError(f"{self.name}: Circular pattern would create more than "
                                  f"{self.MAXIMUM_OCCURRENCES} circles")
        # getRotation: no reference, the role's axis through the origin (Z for none or Z_Axis: gp_Ax2())
        d = {"X_Axis": (1.0, 0.0, 0.0), "Y_Axis": (0.0, 1.0, 0.0)}.get(self.axis, (0.0, 0.0, 1.0))
        direction, center = gp_Dir(*d), gp_Pnt()
        lead = gp_Dir(1.0, 0.0, 0.0) if abs(direction.X()) <= conf and abs(direction.Z()) <= conf \
            else gp_Dir(0.0, 1.0, 0.0)
        radial_dir = gp_Vec(direction).Crossed(gp_Vec(lead))
        radial_dir.Normalize()
        out = [gp_Trsf()]
        full = 2.0 * math.acos(-1.0)
        for circle in range(1, circles):
            radius = circle * radial
            requested = math.floor(full * radius / tangential)
            if not math.isfinite(requested) or requested > self.MAXIMUM_OCCURRENCES \
                    or len(out) + requested > self.MAXIMUM_OCCURRENCES:
                raise W.AssemblyError(f"{self.name}: Circular pattern would create more than "
                                      f"{self.MAXIMUM_OCCURRENCES} occurrences")
            count = int(requested) // symmetry * symmetry
            if count == 0:
                continue
            translation = gp_Trsf()
            translation.SetTranslation(radial_dir.Multiplied(radius))
            step = full / count
            for k in range(count):
                rotation = gp_Trsf()
                rotation.SetRotation(gp_Ax1(center, direction), k * step)
                rotation.Multiply(translation)
                out.append(rotation)
        return [Placement.from_trsf(t) for t in out]


# activateLinkArrayCommand's object names
NAMES = {"LinkArrayLinear": "LinearLinkArray", "LinkArrayPolar": "PolarLinkArray", "LinkArrayCircular": "CircularLinkArray"}


def insert_array(doc, kind: str, part: str | None, shape, props: dict | None = None, name: str | None = None):
    """Part_LinkArrayLinear / Part_LinkArrayPolar with a part selected, the Assembly active: addObject(type, name),
    LinkedObject = the part, activeAsm.addObject(obj); then the panel's settings. Its Label is its Name (LinkArray's
    onChanged keeps the Label when LinkedObject is set)."""
    cls = W.CLASSES.get(kind)
    if cls is None or not issubclass(cls, LinkArray):
        raise W.AssemblyError(f"{kind!r} is not a link array ({', '.join(NAMES)})")
    if not part:
        raise W.AssemblyError("a link array here repeats a part of the project: select one")
    name = name or W.unique_name(doc.all_names(), NAMES[kind])
    a = cls(name, part, **(props or {}))
    if shape is not None:
        doc.shapes[part] = shape
    doc.objects.append(a)
    doc.plc[a.name] = W.to_placement(a.placement)
    return a


W.CLASSES[LinkArrayLinear.kind] = LinkArrayLinear
W.CLASSES[LinkArrayPolar.kind] = LinkArrayPolar
W.CLASSES[LinkArrayCircular.kind] = LinkArrayCircular
W.LinkArray, W.LinkArrayLinear, W.LinkArrayPolar = LinkArray, LinkArrayLinear, LinkArrayPolar
W.LinkArrayCircular = LinkArrayCircular
