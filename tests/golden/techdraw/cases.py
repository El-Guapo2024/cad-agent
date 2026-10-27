"""TechDraw pages, each made by cad_agent/techdraw_edit.py's ops (prep.py) and recomputed by FreeCAD 26.3 (make.py,
freecadcmd) and by cad_agent/techdraw.py (tests/test_techdraw_golden.py).

A case is {"ops": [...], "template"?}: a fresh page (TechDraw_PageDefault, or TechDraw_PageTemplate with the
template) and the ops after it, as `cad techdraw apply` takes them. The parts are parts.py's, read from breps/.
"""

DIM = "dimension"


def dim(t, *refs, **props):
    out = [{"op": DIM, "type": t, "references": [list(r) for r in refs]}]
    return out


def setp(name, **props):
    return {"op": "set", "name": name, "props": props}


def cosmetics(view="View"):
    """Cosmetic vertices, lines, circles and arcs (TaskCosVertex, TaskCosmeticLine / TaskCosmeticCircle), the midpoint
    and quadrant vertices of an edge and an arc, and a line through two of the view's vertices."""
    return [
        {"op": "cosmetic_vertex", "view": view, "point": [5, 6], "tag": "cv-1"},
        {"op": "cosmetic_line", "view": view, "p0": [-5, -4], "p1": [12, 9], "tag": "cl-1"},
        {"op": "cosmetic_circle", "view": view, "center": [3, 4], "radius": 2.5, "tag": "cc-1"},
        {"op": "cosmetic_circle", "view": view, "center": [1, 2], "radius": 3.0, "arc": True, "start_angle": 10,
         "end_angle": 100, "tag": "ca-1"},
        {"op": "midpoints", "view": view, "edges": ["Edge2"]},
        {"op": "quadrants", "view": view, "edges": ["Edge5", "Edge1"]},
        {"op": "cosmetic_line", "view": view, "vertices": ["Vertex1", "Vertex4"], "tag": "cl-2"},
        {"op": "cosmetic_circle", "view": view, "vertices": ["Vertex6", "Vertex8"], "tag": "cc-2"},
    ]


def centerlines(view="View"):
    """Centre lines between two edges (vertical and horizontal), between two points, with a shift, a rotation and an
    extension (TaskCenterLine)."""
    return [
        {"op": "centerline", "view": view, "subs": ["Edge0", "Edge4"], "mode": "Vertical", "tag": "k-1"},
        {"op": "centerline", "view": view, "subs": ["Edge2", "Edge3"], "mode": "Horizontal", "extend": 2.0, "tag": "k-2"},
        {"op": "centerline", "view": view, "subs": ["Vertex3", "Vertex8"], "mode": "Vertical", "h_shift": 1.5,
         "v_shift": -2.0, "tag": "k-3"},
        {"op": "centerline", "view": view, "subs": ["Vertex0", "Vertex4"], "mode": "Aligned", "rotate": 15.0,
         "tag": "k-4"},
        {"op": "centerline", "view": view, "subs": ["Edge1", "Edge4"], "mode": "Aligned", "tag": "k-5"},
    ]


CASES = {
    # one view of the plate from above, hidden lines on, and every dimension type the app makes on it
    "plate_top_dims": {"template": "ISO/A4_Landscape_TD.svg", "ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        setp("View", hard_hidden=True),
        *dim("DistanceX", ("View", "Edge2")),
        *dim("DistanceY", ("View", "Edge4")),
        *dim("Distance", ("View", "Edge0")),
        *dim("Diameter", ("View", "Edge5")),
        *dim("Radius", ("View", "Edge1")),
        *dim("Distance", ("View", "Vertex1"), ("View", "Vertex6")),
        *dim("DistanceX", ("View", "Vertex8"), ("View", "Edge4")),
        *dim("Distance", ("View", "Edge0"), ("View", "Edge4")),
        *dim("DistanceY", ("View", "Vertex2"), ("View", "Vertex4")),
    ]},
    # DimensionFormatter: tolerances, format specs, units, arbitrary text, inverted
    "plate_dim_formats": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        *dim("DistanceX", ("View", "Edge2")),
        setp("Dimension", over_tolerance=0.1),
        *dim("DistanceY", ("View", "Edge4")),
        setp("Dimension001", equal_tolerance=False, over_tolerance=0.2, under_tolerance=-0.1),
        *dim("Diameter", ("View", "Edge5")),
        setp("Dimension002", format_spec="⌀%.3f"),
        *dim("Radius", ("View", "Edge1")),
        setp("Dimension003", format_spec="R%.1w mm max"),
        *dim("Distance", ("View", "Vertex1"), ("View", "Vertex6")),
        setp("Dimension004", format_spec="%0.5r"),
        *dim("DistanceX", ("View", "Edge3")),
        setp("Dimension005", show_units=True),
        *dim("DistanceX", ("View", "Vertex8"), ("View", "Edge4")),
        setp("Dimension006", arbitrary=True, format_spec="see note 3"),
        *dim("DistanceY", ("View", "Edge0")),
        setp("Dimension007", theoretical_exact=True),
        *dim("DistanceX", ("View", "Edge2")),
        setp("Dimension008", inverted=True, format_spec="%g"),
        *dim("DistanceY", ("View", "Edge4")),
        setp("Dimension009", equal_tolerance=False, over_tolerance=0.05, under_tolerance=0.0,
             format_spec_over_tolerance="%+.3f", format_spec_under_tolerance="%+.3f"),
        *dim("DistanceX", ("View", "Edge3")),
        setp("Dimension010", arbitrary_tolerances=True, equal_tolerance=False, format_spec_over_tolerance="H7",
             format_spec_under_tolerance=""),
    ]},
    # a projection group, first angle, at page scale 1:2, with every orthographic and two isometric projections
    "plate_projgroup_first": {"ops": [
        setp("Page", scale=0.5),
        {"op": "projgroup", "source": ["plate"], "direction": [0, -1, 0],
         "projections": ["Top", "Right", "Left", "Bottom", "Rear", "FrontTopLeft", "FrontBottomRight"]},
    ]},
    # third angle from the page (the group's ProjectionType Default), a custom group scale, more spacing
    "bracket_projgroup_third": {"ops": [
        setp("Page", projection_type="Third angle"),
        {"op": "projgroup", "source": ["bracket"], "direction": [0, -1, 0],
         "projections": ["Top", "Right", "Left", "FrontTopRight", "FrontBottomLeft"]},
        setp("ProjGroup", projection_type="Default", scale_type="Custom", scale=0.75, spacing_x=25.0, spacing_y=10.0),
    ]},
    # angle dimensions and hidden lines on the bracket's front
    "bracket_front_angles": {"ops": [
        {"op": "view", "source": ["bracket"]},
        setp("View", hard_hidden=True),
        *dim("Angle", ("View", "Edge3"), ("View", "Edge0")),
        *dim("Angle3Pt", ("View", "Vertex0"), ("View", "Vertex1"), ("View", "Vertex4")),
        *dim("Angle", ("View", "Edge3"), ("View", "Edge5")),
        setp("Dimension002", show_supplementary=True),
        *dim("Distance", ("View", "Edge3")),
    ]},
    # an isometric view, turned, smooth lines off, a custom scale
    "bracket_iso": {"ops": [
        {"op": "view", "source": ["bracket"], "direction": [0.577350269189626, -0.577350269189626, 0.577350269189626],
         "x_direction": [0.707106781186548, 0.707106781186548, 0.0]},
        setp("View", rotation=30.0, scale_type="Custom", scale=1.5, smooth_visible=False, hard_hidden=True),
    ]},
    # the shaft along its axis and from the front: circles, outlines, diameters
    "shaft_views": {"ops": [
        {"op": "view", "source": ["shaft"], "direction": [0, 0, 1]},
        {"op": "view", "source": ["shaft"]},
        {"op": "move", "name": "View", "x": 80.0, "y": 100.0},
        {"op": "move", "name": "View001", "x": 180.0, "y": 100.0},
        setp("View001", hard_hidden=True),
        *dim("Diameter", ("View", "Edge2")),
        *dim("Radius", ("View", "Edge0")),
        *dim("DistanceX", ("View", "Edge0"), ("View", "Edge2")),
        *dim("DistanceX", ("View001", "Edge5"), ("View001", "Edge9")),
        *dim("DistanceY", ("View001", "Vertex7"), ("View001", "Vertex3")),
    ]},
    # sections: through the plate's hole from above, and the shaft from the front
    "plate_section": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        {"op": "section", "base_view": "View", "direction": "Right", "origin": [10.0, 8.0, 5.0], "symbol": "A"},
        {"op": "section", "base_view": "View", "direction": "Up", "origin": [10.0, 8.0, 5.0], "symbol": "B"},
    ]},
    "shaft_section": {"ops": [
        {"op": "view", "source": ["shaft"]},
        {"op": "section", "base_view": "View", "direction": "Left", "symbol": "A"},
        setp("SectionView", hard_hidden=True),
    ]},
    # a part bigger than the sheet: ScaleType Automatic picks a sensible scale
    "big_automatic": {"ops": [
        {"op": "view", "source": ["big"], "direction": [0, 0, 1]},
        setp("View", scale_type="Automatic"),
        {"op": "projgroup", "source": ["big"], "projections": ["Top"]},
        setp("ProjGroup", scale_type="Automatic"),
    ]},
    # an annotation and a balloon (their properties; FreeCAD lays their text out in the GUI)
    "plate_annotations": {"template": "ISO/A3_Landscape_TD.svg", "ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        {"op": "annotation", "text": ["GENERAL TOLERANCE", "ISO 2768-m"], "at": [60.0, 40.0]},
        {"op": "balloon", "view": "View", "origin": [14.0, 8.0], "at": [30.0, 25.0]},
        {"op": "balloon", "view": "View", "origin": [-17.0, 15.0]},
    ]},
    # cosmetic geometry on a view at scale 1, and on one at 2:1 turned 30 degrees (rotated and scaled by the view's)
    "plate_cosmetic": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        *cosmetics(),
    ]},
    "plate_cosmetic_rotated": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        setp("View", scale_type="Custom", scale=2.0, rotation=30.0),
        *cosmetics(),
    ]},
    # centre lines
    "plate_centerlines": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        *centerlines(),
    ]},
    "plate_centerlines_rotated": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        setp("View", scale_type="Custom", scale=1.5, rotation=30.0),
        *centerlines(),
    ]},
    # an eraser: the cosmetic edge and vertex taken away again
    "plate_cosmetic_erased": {"ops": [
        {"op": "view", "source": ["plate"], "direction": [0, 0, 1]},
        {"op": "cosmetic_vertex", "view": "View", "point": [5, 6], "tag": "cv-1"},
        {"op": "cosmetic_line", "view": "View", "p0": [-5, -4], "p1": [12, 9], "tag": "cl-1"},
        {"op": "cosmetic_vertex", "view": "View", "point": [-5, 6], "tag": "cv-2"},
        {"op": "erase", "view": "View", "subs": ["Edge6", "Vertex9"]},
    ]},
}
