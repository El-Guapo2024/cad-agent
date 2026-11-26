"""Borrowing open designs: rebuilds a FreeCAD assembly (e.g. LumenPnP's src/assembly.FCStd) for viewing and checking.
Usage: python -I tools/fcstd_read.py path/to/assembly.FCStd [out.step]

Read a FreeCAD .FCStd (a zip) without FreeCAD: solids from its BREP files, App::Link resolved to other files,
placements applied. Prints a table of bodies and writes them into one STEP."""
import re, sys, zipfile, tempfile, os, math
import xml.etree.ElementTree as ET
from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape
from OCP.gp import gp_Trsf, gp_Quaternion, gp_Vec
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

def brep_from_bytes(data):
    with tempfile.NamedTemporaryFile(suffix=".brp", delete=False) as f:
        f.write(data); p = f.name
    s = TopoDS_Shape(); BRepTools.Read_s(s, p, BRep_Builder()); os.unlink(p); return s

def placement(el):
    pp = el.find("PropertyPlacement")
    t = gp_Trsf()
    q = gp_Quaternion(float(pp.get("Q0")), float(pp.get("Q1")), float(pp.get("Q2")), float(pp.get("Q3")))
    t.SetRotation(q); t.SetTranslationPart(gp_Vec(float(pp.get("Px")), float(pp.get("Py")), float(pp.get("Pz"))))
    return t

class Doc:
    cache = {}
    def __init__(self, path):
        self.path = path; self.z = zipfile.ZipFile(path); root = ET.fromstring(self.z.read("Document.xml"))
        self.types = {o.get("name"): o.get("type") for o in root.find("Objects")}
        self.props = {}
        for o in root.find("ObjectData"):
            self.props[o.get("name")] = {p.get("name"): p for p in o.find("Properties")}
    @classmethod
    def get(cls, path):
        path = os.path.normpath(path)
        if path not in cls.cache:
            cls.cache[path] = cls(path) if os.path.exists(path) else None
        return cls.cache[path]
    def visible(self, name):
        v = self.props[name].get("Visibility")
        b = v.find("Bool") if v is not None else None
        return b is None or b.get("value") == "true"
    def shape(self, name):
        p = self.props.get(name, {}).get("Shape")
        if p is None: return None
        f = p.find("Part")
        if f is None or not f.get("file"): return None
        try: return brep_from_bytes(self.z.read(f.get("file")))
        except KeyError: return None
    def label(self, name):
        l = self.props[name].get("Label"); return l.find("String").get("value") if l is not None else name
    def link(self, name):
        x = self.props[name].get("LinkedObject")
        if x is None: return None
        xl = x.find("XLink")
        if xl is None: 
            l = x.find("Link"); return (None, l.get("value")) if l is not None else None
        return (xl.get("file") or None, xl.get("name"))

def resolve(doc, name, depth=0):
    """The solid for an object: its stored shape, or what its link points at, with the link's placement."""
    if depth > 6: return None
    if doc.types.get(name) in ("App::Link",):
        tgt = doc.link(name)
        if not tgt: return None
        f, obj = tgt
        d2 = Doc.get(os.path.join(os.path.dirname(doc.path), f)) if f else doc
        if d2 is None or obj not in d2.props: return None
        s = resolve(d2, obj, depth + 1)
        if s is None: return None
        lp = doc.props[name].get("Placement")
        return s.Moved(TopLoc_Location(placement(lp))) if lp is not None else s
    return doc.shape(name)

def bbox(s):
    b = Bnd_Box(); BRepBndLib.Add_s(s, b); lo, hi = b.CornerMin(), b.CornerMax(); return (lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z())

if __name__ == "__main__":
    path = sys.argv[1]; d = Doc.get(path)
    bodies = []
    for n, t in d.types.items():
        if t in ("App::Link",) or (t in ("Part::Feature", "Part::FeaturePython", "PartDesign::Body") and d.shape(n) is not None):
            if not d.visible(n): continue
            s = resolve(d, n)
            if s is None or s.IsNull(): print("  unresolved", n, t, d.link(n) if t == "App::Link" else ""); continue
            bodies.append((d.label(n), t, s))
    print(len(bodies), "bodies")
    for lab, t, s in bodies[:400]:
        b = bbox(s); print(f"{lab[:40]:40s} {t:22s} x {b[0]:7.1f}..{b[3]:7.1f} y {b[1]:7.1f}..{b[4]:7.1f} z {b[2]:7.1f}..{b[5]:7.1f}")
    if len(sys.argv) > 2:
        from build123d import Compound, Solid, export_step, Shape
        c = Compound([Shape(s) for _, _, s in bodies]); export_step(c, sys.argv[2]); print("wrote", sys.argv[2])

def render_png(bodies, out, view="iso"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cad_agent.render import tessellate, merge, draw
    from build123d import Shape
    meshes = []
    for _, _, s in bodies:
        try: meshes.append(tessellate(Shape(s), tolerance=0.5, angular=0.5))
        except Exception: pass
    draw(merge(meshes), out, view=view)
