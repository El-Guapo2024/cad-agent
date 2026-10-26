"""Part objects attached to other objects, as Part's Attachment editor (Part_EditAttachment) writes them: AttachExtension's
AttachmentSupport, MapMode, AttachmentOffset, MapReversed and MapPathParameter, and the Placement they give the object.

The editor adds Part::AttachExtensionPython to an object FreeCAD does not give the extension (a Cut, a Polygon), so a
case attaches one of those too. A Part object's own placement= is where it sits with MapMode Deactivated, and the
Placement of an object that is not a Part::Primitive (a Fuse) moves its built shape. The answers are in
freecad_attach.json (make.py attach), together with the extension's property values for the types FreeCAD makes
without it.
"""
from cad_agent import feature_part as Part
from cad_agent.feature import Pad, Sketch

from cases import rect


def flat(name, support, **kw):
    return Part.Box(name, length=4, width=6, height=2, attachment_support=support, map_mode="FlatFace", **kw)


# Base: 20 x 20 x 10, its top face Face6 (z = 10), its bottom Face5.
BASE = [Part.Box("Base", length=20, width=20, height=10)]
CASES = {}

CASES["attach_flat_face"] = {"objects": BASE + [
    flat("Box", [("Base", "Face6")], attachment_offset=((1, 2, 3), (0, 0, 30)))]}
CASES["attach_flip"] = {"objects": BASE + [
    flat("Box", [("Base", "Face6")], attachment_offset=(1, 2, 3), map_reversed=True)]}
CASES["attach_side"] = {"objects": BASE + [
    Part.Cylinder("Cylinder", radius=2, height=5, attachment_support=[("Base", "Face2")], map_mode="FlatFace",
                  attachment_offset=(0, 0, 2))]}
CASES["attach_object_xy"] = {"objects": BASE + [
    Part.Box("Box", length=4, width=6, height=2, attachment_support=[("Base", "")], map_mode="ObjectXY",
             attachment_offset=((5, 5, 10), (0, 0, -45)))]}
CASES["attach_chain"] = {"objects": BASE + [
    flat("BoxA", [("Base", "Face6")], attachment_offset=(0, 0, 5)),
    flat("BoxB", [("BoxA", "Face6")], attachment_offset=(2, 0, 0), map_reversed=True)]}
CASES["attach_deactivated"] = {"objects": BASE + [
    Part.Box("Box", length=4, width=6, height=2, placement=((30, 5, 0), (0, 0, 15)),
             attachment_support=[("Base", "Face6")])]}
CASES["attach_cut"] = {"objects": BASE + [
    Part.Cylinder("Cylinder", radius=3, height=30, placement=((10, 10, -10), (0, 0, 0))),
    Part.Cut("Cut", "Base", "Cylinder", attachment_support=[("Base", "Face5")], map_mode="FlatFace",
             attachment_offset=(0, 0, 25))]}
CASES["attach_polygon"] = {"objects": BASE + [
    Part.Polygon("Polygon", nodes=[(0, 0, 0), (8, 0, 0), (8, 6, 0)], close=True,
                 attachment_support=[("Base", "Face6")], map_mode="FlatFace", attachment_offset=(2, 2, 4))]}
CASES["attach_circle_edge"] = {"objects": [
    Part.Cylinder("Cylinder", radius=4, height=12),
    Part.Circle("Circle", radius=2, attachment_support=[("Cylinder", "Edge3")], map_mode="Concentric",
                attachment_offset=((0, 0, 3), (0, 0, 0)))]}
CASES["attach_fuse_placement"] = {"objects": BASE + [
    Part.Cylinder("Cylinder", radius=3, height=20, placement=((10, 10, -5), (0, 0, 0))),
    Part.Fuse("Fusion", "Base", "Cylinder", placement=((0, 0, 25), (0, 0, 45)))]}
CASES["attach_body_face"] = {"features": [Sketch("Sketch", support="XY", geometry=rect(0, 0, 30, 20)),
                                          Pad("Pad", "Sketch", length=6)],
                             "objects": [flat("Box", [("Pad", "Face6")], attachment_offset=(3, 3, 1))]}
CASES["attach_origin_plane"] = {"features": [Sketch("Sketch", support="XY", geometry=rect(0, 0, 30, 20)),
                                             Pad("Pad", "Sketch", length=6)],
                                "objects": [flat("Box", [("XY_Plane", "")], attachment_offset=(5, 5, 30))]}
