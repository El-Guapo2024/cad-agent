// SPDX-License-Identifier: LGPL-2.1-or-later
// ui/src/attachsuggest.ts and attachmodes.ts bundled for Node (tests/test_attach_suggest.py): npx esbuild src/attachsuggest.ts --bundle --format=esm --outfile=../tests/golden/attach/suggest.mjs

// src/attachmodes.ts
var ENGINE_MODES = { "3D": ["Deactivated", "Translate", "ObjectXY", "ObjectXZ", "ObjectYZ", "FlatFace", "TangentPlane", "NormalToEdge", "FrenetNB", "FrenetTN", "FrenetTB", "Concentric", "SectionOfRevolution", "ThreePointsPlane", "ThreePointsNormal", "Folding", "InertialCS", "OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX", "ParallelPlane", "MidPlane"], "Plane": ["Deactivated", "Translate", "ObjectXY", "ObjectXZ", "ObjectYZ", "FlatFace", "TangentPlane", "NormalToEdge", "FrenetNB", "FrenetTN", "FrenetTB", "Concentric", "SectionOfRevolution", "ThreePointsPlane", "ThreePointsNormal", "Folding", "InertialCS", "OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX", "ParallelPlane", "MidPlane"], "Line": ["Deactivated", "ObjectX", "ObjectY", "ObjectZ", "AxisOfCurvature", "Directrix1", "Directrix2", "Asymptote1", "Asymptote2", "Tangent", "Normal", "Binormal", "TwoPointLine", "IntersectionLine", "ProximityLine", "AxisOfInertia1", "AxisOfInertia2", "AxisOfInertia3", "FaceNormal"], "Point": ["Deactivated", "ObjectOrigin", "Focus1", "Focus2", "OnEdge", "CenterOfCurvature", "CenterOfMass", "Vertex", "ProximityPoint1", "ProximityPoint2"] };
var MODE_REFS = { "3D": { "Translate": [["Vertex"]], "ObjectXY": [["Any|Placement"], ["Conic"]], "ObjectXZ": [["Any|Placement"], ["Conic"]], "ObjectYZ": [["Any|Placement"], ["Conic"]], "FlatFace": [["Plane"]], "TangentPlane": [["Face", "Vertex"], ["Vertex", "Face"]], "NormalToEdge": [["Edge"], ["Edge", "Vertex"], ["Vertex", "Edge"]], "FrenetNB": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "FrenetTN": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "FrenetTB": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "Concentric": [["Curve"], ["Circle"], ["Curve", "Vertex"], ["Circle", "Vertex"], ["Vertex", "Curve"], ["Vertex", "Circle"]], "SectionOfRevolution": [["Curve"], ["Circle"], ["Curve", "Vertex"], ["Circle", "Vertex"], ["Vertex", "Curve"], ["Vertex", "Circle"]], "ThreePointsPlane": [["Vertex", "Vertex", "Vertex"], ["Line", "Vertex"], ["Vertex", "Line"], ["Line", "Line"]], "ThreePointsNormal": [["Vertex", "Vertex", "Vertex"], ["Line", "Vertex"], ["Vertex", "Line"], ["Line", "Line"]], "Folding": [["Line", "Line", "Line", "Line"]], "InertialCS": [["Any"], ["Any", "Any"], ["Any", "Any", "Any"], ["Any", "Any", "Any", "Any"]], "OZX": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OZY": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OXY": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OXZ": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OYZ": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OYX": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "ParallelPlane": [["Plane|Placement", "Vertex"], ["Any|Placement", "Vertex"]], "MidPlane": [["Plane", "Plane"]] }, "Plane": { "Translate": [["Vertex"]], "ObjectXY": [["Any|Placement"], ["Conic"]], "ObjectXZ": [["Any|Placement"], ["Conic"]], "ObjectYZ": [["Any|Placement"], ["Conic"]], "FlatFace": [["Plane"]], "TangentPlane": [["Face", "Vertex"], ["Vertex", "Face"]], "NormalToEdge": [["Edge"], ["Edge", "Vertex"], ["Vertex", "Edge"]], "FrenetNB": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "FrenetTN": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "FrenetTB": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "Concentric": [["Curve"], ["Circle"], ["Curve", "Vertex"], ["Circle", "Vertex"], ["Vertex", "Curve"], ["Vertex", "Circle"]], "SectionOfRevolution": [["Curve"], ["Circle"], ["Curve", "Vertex"], ["Circle", "Vertex"], ["Vertex", "Curve"], ["Vertex", "Circle"]], "ThreePointsPlane": [["Vertex", "Vertex", "Vertex"], ["Line", "Vertex"], ["Vertex", "Line"], ["Line", "Line"]], "ThreePointsNormal": [["Vertex", "Vertex", "Vertex"], ["Line", "Vertex"], ["Vertex", "Line"], ["Line", "Line"]], "Folding": [["Line", "Line", "Line", "Line"]], "InertialCS": [["Any"], ["Any", "Any"], ["Any", "Any", "Any"], ["Any", "Any", "Any", "Any"]], "OZX": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OZY": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OXY": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OXZ": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OYZ": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "OYX": [["Vertex", "Vertex", "Vertex"], ["Vertex", "Vertex", "Line"], ["Vertex", "Line", "Vertex"], ["Vertex", "Line", "Line"], ["Vertex", "Vertex"], ["Vertex", "Line"]], "ParallelPlane": [["Plane|Placement", "Vertex"], ["Any|Placement", "Vertex"]], "MidPlane": [["Plane", "Plane"]] }, "Line": { "ObjectX": [["Any|Placement"], ["Conic"]], "ObjectY": [["Any|Placement"], ["Conic"]], "ObjectZ": [["Any|Placement"], ["Conic"]], "AxisOfCurvature": [["Curve"], ["Circle"], ["Curve", "Vertex"], ["Circle", "Vertex"], ["Vertex", "Curve"], ["Vertex", "Circle"]], "Directrix1": [["Conic"]], "Directrix2": [["Ellipse"], ["Hyperbola"]], "Asymptote1": [["Hyperbola"]], "Asymptote2": [["Hyperbola"]], "Tangent": [["Edge"], ["Edge", "Vertex"], ["Vertex", "Edge"]], "Normal": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "Binormal": [["Curve"], ["Curve", "Vertex"], ["Vertex", "Curve"]], "TwoPointLine": [["Vertex", "Vertex"], ["Line"]], "IntersectionLine": [["Face", "Face"]], "ProximityLine": [["Any", "Any"]], "AxisOfInertia1": [["Any"], ["Any", "Any"], ["Any", "Any", "Any"], ["Any", "Any", "Any", "Any"]], "AxisOfInertia2": [["Any"], ["Any", "Any"], ["Any", "Any", "Any"], ["Any", "Any", "Any", "Any"]], "AxisOfInertia3": [["Any"], ["Any", "Any"], ["Any", "Any", "Any"], ["Any", "Any", "Any", "Any"]], "FaceNormal": [["Face", "Vertex"], ["Vertex", "Face"]] }, "Point": { "ObjectOrigin": [["Any|Placement"], ["Conic"]], "Focus1": [["Conic"]], "Focus2": [["Ellipse"], ["Hyperbola"]], "OnEdge": [["Edge"], ["Edge", "Vertex"], ["Vertex", "Edge"]], "CenterOfCurvature": [["Curve"], ["Circle"], ["Curve", "Vertex"], ["Circle", "Vertex"], ["Vertex", "Curve"], ["Vertex", "Circle"]], "CenterOfMass": [["Any"], ["Any", "Any"], ["Any", "Any", "Any"], ["Any", "Any", "Any", "Any"]], "Vertex": [["Vertex"], ["Line"]], "ProximityPoint1": [["Any", "Any"]], "ProximityPoint2": [["Any", "Any"]] } };
var REF_TYPES = ["Any", "Vertex", "Edge", "Face", "Line", "Curve", "Circle", "Conic", "Ellipse", "Parabola", "Hyperbola", "Plane", "Sphere", "Revolve", "Cylinder", "Torus", "Cone", "Object", "Solid", "Wire"];

// src/attachsuggest.ts
var FLAG = 256;
var T = Object.fromEntries(REF_TYPES.map((n, i) => [n, i]));
var refType = (name) => {
  const [b, f] = name.split("|");
  return (T[b] ?? 0) | (f === "Placement" ? FLAG : 0);
};
var refTypeName = (t) => REF_TYPES[t & 255] + (t & FLAG ? "|Placement" : "");
function downgrade(t) {
  t &= FLAG - 1;
  const n = REF_TYPES[t];
  if (["Vertex", "Edge", "Face", "Any", "Object"].includes(n)) return T.Any;
  if (n === "Line" || n === "Curve") return T.Edge;
  if (n === "Conic" || n === "Circle") return T.Curve;
  if (["Ellipse", "Parabola", "Hyperbola"].includes(n)) return T.Conic;
  if (["Plane", "Sphere", "Revolve"].includes(n)) return T.Face;
  if (["Cylinder", "Torus", "Cone"].includes(n)) return T.Revolve;
  if (n === "Solid" || n === "Wire") return T.Object;
  throw new Error("AttachEngine::downgradeType: unknown type");
}
function rank(t) {
  t &= FLAG - 1;
  let r = 0;
  while (t !== T.Any) {
    t = downgrade(t);
    r++;
  }
  return r;
}
function isShapeOfType(shape, req) {
  if (req & FLAG && !(shape & FLAG)) return -1;
  shape &= FLAG - 1;
  req &= FLAG - 1;
  if (req === T.Any) return 1;
  const r = rank(req);
  for (let d = shape; d !== T.Any; d = downgrade(d)) if (d === req) return r;
  req = downgrade(req);
  if (req !== T.Any) {
    for (let d = shape; d !== T.Any; d = downgrade(d)) if (d === req) return 0;
  }
  return -1;
}
function suggest(engine, types) {
  const ts = types.map(refType);
  let bestScore = -1, best = "Deactivated", message = "NoModesFit";
  const all = [], reachable = {}, hints = /* @__PURE__ */ new Set();
  for (const m of ENGINE_MODES[engine].slice(1)) {
    for (const combo of MODE_REFS[engine][m]) {
      const s = combo.map(refType);
      let score = 1;
      for (let k = 0; k < Math.min(s.length, ts.length); k++) {
        const match = isShapeOfType(ts[k], s[k]);
        if (match === -1) {
          score = -1;
          break;
        }
        if (match === 0) score = 0;
        else if (match >= 2 && score > 0) score += match;
      }
      if (score > 0 && s.length > ts.length) {
        hints.add(s[ts.length]);
        (reachable[m] ??= []).push(s.slice(ts.length).map(refTypeName));
      }
      if (s.length !== ts.length) score = -1;
      if (score > -1 && score > bestScore) {
        bestScore = score;
        best = m;
        message = score > 0 ? "OK" : "IncompatibleGeometry";
      }
      if (score > 0 && all[all.length - 1] !== m) all.push(m);
    }
  }
  for (const m of all) delete reachable[m];
  return { message, best, all, reachable, hints: [...hints].sort((a, b) => a - b).map(refTypeName), types: ts.map(refTypeName) };
}
export {
  isShapeOfType,
  refType,
  refTypeName,
  suggest
};
