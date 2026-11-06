"""What a Draft case records of each object, the same in FreeCAD (make.py) and here (tests/test_draft_golden.py): its
Name, TypeId and Label, and its shape's type, length, area, volume, bounding box, and counts of vertices, edges, faces,
and the vertices themselves (sorted)."""


def r(x):
    return round(float(x), 6)


def record(doc):
    out = []
    for o in doc.Objects:
        d = {"name": o.Name, "type": o.TypeId, "label": o.Label}
        s = getattr(o, "Shape", None)
        if s is not None and not s.isNull():
            bb = s.BoundBox
            d["shape"] = {"type": s.ShapeType, "length": r(s.Length), "area": r(s.Area), "volume": r(s.Volume),
                          "box": [r(bb.XMin), r(bb.YMin), r(bb.ZMin), r(bb.XMax), r(bb.YMax), r(bb.ZMax)],
                          "vertices": len(s.Vertexes), "edges": len(s.Edges), "faces": len(s.Faces),
                          "points": sorted([r(v.Point.x), r(v.Point.y), r(v.Point.z)] for v in s.Vertexes)}
        out.append(d)
    return out
