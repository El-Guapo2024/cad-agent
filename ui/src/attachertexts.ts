// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/Gui/AttacherTexts.cpp: 2016 Victor Titov (DeepSOIC)
// Written by ui/scripts/attachertexts.py from FreeCAD's src/Mod/Part/Gui/AttacherTexts.cpp
// (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6; 2016 Victor Titov (DeepSOIC); LGPL-2.1-or-later).
// Do not edit: run the script again. The Attachment panel's mode captions and tooltips per attacher
// engine (AttacherGui::getUIStrings), and the reference types' names (getShapeTypeText), in eRefType order.
export const MODE_TEXTS: Record<string, Record<string, [string, string]>> = {
 "3D": {
  "Deactivated": [
   "Deactivated",
   "Attachment is disabled. Object can be moved by editing Placement property."
  ],
  "Translate": [
   "Translate origin",
   "Origin is aligned to match Vertex. Orientation is controlled by Placement property."
  ],
  "ObjectXY": [
   "Object's X Y Z",
   "Placement is made equal to Placement of linked object."
  ],
  "ObjectXZ": [
   "Object's X Z Y",
   "X', Y', Z' axes are matched with object's local X, Z, -Y, respectively."
  ],
  "ObjectYZ": [
   "Object's Y Z X",
   "X', Y', Z' axes are matched with object's local Y, Z, X, respectively."
  ],
  "ParallelPlane": [
   "XY parallel to plane",
   "X' Y' plane is parallel to the plane (object's XY) and passes through the vertex."
  ],
  "MidPlane": [
   "Midplane between faces",
   "Plane origin is midway between two planar faces and its orientation equally bisects their angle. For non-parallel faces the plane contains their intersection line."
  ],
  "FlatFace": [
   "XY on plane",
   "X' Y' plane is aligned to coincide planar face."
  ],
  "TangentPlane": [
   "XY tangent to surface",
   "X' Y' plane is made tangent to surface at vertex."
  ],
  "NormalToEdge": [
   "Z tangent to edge",
   "Z' axis is aligned to be tangent to edge. Optional vertex link defines where."
  ],
  "FrenetNB": [
   "Frenet NBT",
   "Align to Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "FrenetTN": [
   "Frenet TNB",
   "Align to Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "FrenetTB": [
   "Frenet TBN",
   "Align to Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "Concentric": [
   "Concentric",
   "Align XY-plane to osculating circle of an edge. Optional vertex link defines where."
  ],
  "SectionOfRevolution": [
   "Revolution Section",
   "Align Y' axis to match axis of osculating circle of an edge. Optional vertex link defines where."
  ],
  "ThreePointsPlane": [
   "XY-plane by 3 points",
   "Align XY-plane to pass through three vertices."
  ],
  "ThreePointsNormal": [
   "XZ-plane by 3 points",
   "Align XZ-plane to pass through 3 points; X axis will pass through two first points."
  ],
  "Folding": [
   "Folding",
   "Specialty mode for folding polyhedra. Select 4 edges in order: foldable edge, fold line, other fold line, other foldable edge. XY-plane will be aligned to folding the first edge."
  ],
  "InertialCS": [
   "Inertial CS",
   "Inertial coordinate system, constructed on principal axes of inertia and center of mass."
  ],
  "OZX": [
   "Align O-Z-X",
   "Match origin with first Vertex. Align Z' and X' axes towards vertex/along line."
  ],
  "OZY": [
   "Align O-Z-Y",
   "Match origin with first Vertex. Align Z' and Y' axes towards vertex/along line."
  ],
  "OXY": [
   "Align O-X-Y",
   "Match origin with first Vertex. Align X' and Y' axes towards vertex/along line."
  ],
  "OXZ": [
   "Align O-X-Z",
   "Match origin with first Vertex. Align X' and Z' axes towards vertex/along line."
  ],
  "OYZ": [
   "Align O-Y-Z",
   "Match origin with first Vertex. Align Y' and Z' axes towards vertex/along line."
  ],
  "OYX": [
   "Align O-Y-X",
   "Match origin with first Vertex. Align Y' and X' axes towards vertex/along line."
  ]
 },
 "Plane": {
  "Deactivated": [
   "Deactivated",
   "Attachment is disabled. Object can be moved by editing Placement property."
  ],
  "Translate": [
   "Translate origin",
   "Origin is aligned to match Vertex. Orientation is controlled by Placement property."
  ],
  "ObjectXY": [
   "Object's XY",
   "Plane is aligned to XY local plane of linked object."
  ],
  "ObjectXZ": [
   "Object's XZ",
   "Plane is aligned to XZ local plane of linked object."
  ],
  "ObjectYZ": [
   "Object's YZ",
   "Plane is aligned to YZ local plane of linked object."
  ],
  "ParallelPlane": [
   "XY parallel to plane",
   "X' Y' plane is parallel to the plane (object's XY) and passes through the vertex"
  ],
  "MidPlane": [
   "Midplane between faces",
   "Plane origin is midway between two planar faces and its orientation equally bisects their angle. For non-parallel faces the plane contains their intersection line."
  ],
  "FlatFace": [
   "Plane face",
   "Plane is aligned to coincide planar face."
  ],
  "TangentPlane": [
   "Tangent to surface",
   "Plane is made tangent to surface at vertex."
  ],
  "NormalToEdge": [
   "Normal to edge",
   "Plane is made tangent to edge. Optional vertex link defines where."
  ],
  "FrenetNB": [
   "Frenet NB",
   "Align to Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "FrenetTN": [
   "Frenet TN",
   "Align to Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "FrenetTB": [
   "Frenet TB",
   "Align to Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "Concentric": [
   "Concentric",
   "Align to plane to osculating circle of an edge. Origin is aligned to point of curvature. Optional vertex link defines where."
  ],
  "SectionOfRevolution": [
   "Revolution Section",
   "Plane is perpendicular to edge, and Y axis is matched with axis of osculating circle. Optional vertex link defines where."
  ],
  "ThreePointsPlane": [
   "Plane by 3 points",
   "Align plane to pass through three vertices."
  ],
  "ThreePointsNormal": [
   "Normal to 3 points",
   "Plane will pass through first two vertices, and perpendicular to plane that passes through three vertices."
  ],
  "Folding": [
   "Folding",
   "Specialty mode for folding polyhedra. Select 4 edges in order: foldable edge, fold line, other fold line, other foldable edge. Plane will be aligned to folding the first edge."
  ],
  "InertialCS": [
   "Inertia 2-3",
   "Plane constructed on second and third principal axes of inertia (passes through center of mass)."
  ],
  "OZX": [
   "Align O-N-X",
   "Match origin with first Vertex. Align normal and horizontal plane axis towards vertex/along line."
  ],
  "OZY": [
   "Align O-N-Y",
   "Match origin with first Vertex. Align normal and vertical plane axis towards vertex/along line."
  ],
  "OXY": [
   "Align O-X-Y",
   "Match origin with first Vertex. Align horizontal and vertical plane axes towards vertex/along line."
  ],
  "OXZ": [
   "Align O-X-N",
   "Match origin with first Vertex. Align horizontal plane axis and normal towards vertex/along line."
  ],
  "OYZ": [
   "Align O-Y-N",
   "Match origin with first Vertex. Align vertical plane axis and normal towards vertex/along line."
  ],
  "OYX": [
   "Align O-Y-X",
   "Match origin with first Vertex. Align vertical and horizontal plane axes towards vertex/along line."
  ]
 },
 "Line": {
  "Deactivated": [
   "Deactivated",
   "Attachment is disabled. Line can be moved by editing Placement property."
  ],
  "ObjectX": [
   "Object's X",
   "Line is aligned along local X axis of object. Works on objects with placements, and ellipse/parabola/hyperbola edges."
  ],
  "ObjectY": [
   "Object's Y",
   "Line is aligned along local Y axis of object. Works on objects with placements, and ellipse/parabola/hyperbola edges."
  ],
  "ObjectZ": [
   "Object's Z",
   "Line is aligned along local X axis of object. Works on objects with placements, and ellipse/parabola/hyperbola edges."
  ],
  "AxisOfCurvature": [
   "Axis of curvature",
   "Line that is an axis of osculating circle of curved edge. Optional vertex defines where."
  ],
  "Directrix1": [
   "Directrix1",
   "Directrix line for ellipse, parabola, hyperbola."
  ],
  "Directrix2": [
   "Directrix2",
   "Second directrix line for ellipse and hyperbola."
  ],
  "Asymptote1": [
   "Asymptote1",
   "Asymptote of a hyperbola."
  ],
  "Asymptote2": [
   "Asymptote2",
   "Second asymptote of hyperbola."
  ],
  "Tangent": [
   "Tangent",
   "Line tangent to an edge. Optional vertex link defines where."
  ],
  "Normal": [
   "Normal to edge",
   "Align to N vector of Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "Binormal": [
   "Binormal",
   "Align to B vector of Frenet-Serret coordinate system of curved edge. Optional vertex link defines where."
  ],
  "TangentU": [
   "Tangent to surface (U)",
   "Tangent to surface, along U parameter. Vertex link defines where."
  ],
  "TangentV": [
   "Tangent to surface (V)",
   "Tangent to surface, along U parameter. Vertex link defines where."
  ],
  "TwoPointLine": [
   "Through two points",
   "Line that passes through two vertices."
  ],
  "IntersectionLine": [
   "Intersection",
   "Intersection of two faces."
  ],
  "ProximityLine": [
   "Proximity line",
   "Line that spans the shortest distance between shapes."
  ],
  "AxisOfInertia1": [
   "1st principal axis",
   "Line follows first principal axis of inertia."
  ],
  "AxisOfInertia2": [
   "2nd principal axis",
   "Line follows second principal axis of inertia."
  ],
  "AxisOfInertia3": [
   "3rd principal axis",
   "Line follows third principal axis of inertia."
  ],
  "FaceNormal": [
   "Normal to surface",
   "Line perpendicular to surface at point set by vertex."
  ]
 },
 "Point": {
  "Deactivated": [
   "Deactivated",
   "Attachment is disabled. Point can be moved by editing Placement property."
  ],
  "ObjectOrigin": [
   "Object's origin",
   "Point is put at object's placement position. Works on objects with placements, and ellipse/parabola/hyperbola edges."
  ],
  "Focus1": [
   "Focus1",
   "Focus of ellipse, parabola, hyperbola."
  ],
  "Focus2": [
   "Focus2",
   "Second focus of ellipse and hyperbola."
  ],
  "OnEdge": [
   "On edge",
   "Point is put on edge, MapPathParameter controls where. Additionally, vertex can be linked in for making a projection."
  ],
  "CenterOfCurvature": [
   "Center of curvature",
   "Center of osculating circle of an edge. Optional vertex link defines where."
  ],
  "CenterOfMass": [
   "Center of mass",
   "Center of mass of all references (equal densities are assumed)."
  ],
  "IntersectionPoint": [
   "Intersection",
   "Not implemented"
  ],
  "Vertex": [
   "Vertex",
   "Put Datum point coincident with another vertex."
  ],
  "ProximityPoint1": [
   "Proximity point 1",
   "Point on first reference that is closest to second reference."
  ],
  "ProximityPoint2": [
   "Proximity point 2",
   "Point on second reference that is closest to first reference."
  ]
 }
}
export const REF_TYPE_TEXTS: string[] = ["Any", "Vertex", "Edge", "Face", "Line", "Curve", "Circle", "Conic", "Ellipse", "Parabola", "Hyperbola", "Plane", "Sphere", "Revolve", "Cylinder", "Torus", "Cone", "Object", "Solid", "Wire"]
