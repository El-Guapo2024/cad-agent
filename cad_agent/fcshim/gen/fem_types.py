"""Writes cad_agent/fcshim/fem_types.json: the properties of a fresh object of each FEM C++ type, as FreeCAD 26.3
(3160daf1e2b6) gives them (name, type, group, documentation, editor mode, default, enumeration), and the types it
derives from. Run in freecadcmd: $FREECAD/freecadcmd cad_agent/fcshim/gen/fem_types.py > out; the JSON line is the file."""
import FreeCAD as App, json
doc = App.newDocument("T")
TYPES = ["Fem::FemAnalysis", "Fem::FemAnalysisPython", "Fem::FeaturePython", "Fem::ConstraintPython", "Fem::FemSolverObjectPython",
 "App::MaterialObjectPython", "Fem::FemMeshShapeBaseObjectPython", "Fem::FemResultObjectPython", "Fem::FemMeshObjectPython",
 "Fem::ConstraintFixed", "Fem::ConstraintForce", "Fem::ConstraintPressure", "Fem::ConstraintDisplacement", "Fem::ConstraintTemperature",
 "Fem::ConstraintInitialTemperature", "Fem::ConstraintHeatflux", "Fem::ConstraintPlaneRotation", "Fem::ConstraintContact",
 "Fem::ConstraintSpring", "Fem::ConstraintTransform", "Fem::ConstraintRigidBody", "Fem::FemMeshObject", "Fem::FemSolverObject",
 "Fem::FemResultObject", "Fem::Constraint", "App::MaterialObject", "Fem::FemPostPipeline"]
def plain(v):
    if isinstance(v, (bool, int, float, str)) or v is None: return v
    if hasattr(v, "Value") and hasattr(v, "Unit"): return {"q": v.Value, "u": str(v.Unit)}
    if isinstance(v, App.Vector): return {"v": [v.x, v.y, v.z]}
    if isinstance(v, App.Placement): return {"p": [list(v.Base), list(v.Rotation.Q)]}
    if isinstance(v, (list, tuple)): return [plain(x) for x in v]
    if isinstance(v, dict): return {str(k): plain(x) for k, x in v.items()}
    return None
out = {}
for t in TYPES:
    try:
        o = doc.addObject(t, t.split("::")[1])
    except Exception as e:
        out[t] = {"error": str(e)}; continue
    chain = []
    ty = o.TypeId
    props = []
    for p in o.PropertiesList:
        props.append([p, o.getTypeIdOfProperty(p), o.getGroupOfProperty(p), o.getDocumentationOfProperty(p),
                      list(o.getEditorMode(p)), plain(getattr(o, p)) if p not in ("Shape", "FemMesh", "Proxy", "ExpressionEngine") else None,
                      o.getEnumerationsOfProperty(p) if o.getTypeIdOfProperty(p) == "App::PropertyEnumeration" else None])
    out[t] = {"type": o.TypeId, "derived": [b for b in TYPES + ["App::DocumentObjectGroup", "App::GeoFeature", "Part::Feature", "App::FeaturePython", "App::DocumentObject"] if o.isDerivedFrom(b)],
              "props": props, "ext": [e for e in ("App::GroupExtension", "App::SuppressibleExtension") if o.hasExtension(e)]}
print("JSON" + json.dumps(out))
