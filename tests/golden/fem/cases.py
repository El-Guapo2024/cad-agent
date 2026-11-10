"""FEM analyses (FreeCAD's FEM Python, cad_agent/fcfem, over the stand-ins): each case builds its document with the
same lines in FreeCAD (make.py) and here (tests/test_fem_golden.py), through ObjectsFem as the FEM workbench's commands
do. Gmsh runs on one thread (FEM's Gmsh preference NumOfThreads) so the mesh is the same each run.
"""


def _box(doc, length, width, height):
    b = doc.addObject("Part::Box", "Box")
    b.Length, b.Width, b.Height = length, width, height
    return b


def _steel(ObjectsFem, doc):
    mat = ObjectsFem.makeMaterialSolid(doc, "Material")
    m = mat.Material
    m["Name"] = "Steel"
    m["YoungsModulus"] = "210000 MPa"
    m["PoissonRatio"] = "0.30"
    m["Density"] = "7900 kg/m^3"
    mat.Material = m
    return mat


def cantilever(doc, App, ObjectsFem):
    """A 100 x 10 x 10 steel bar fixed at x = 0, 100 N down on its far end."""
    box = _box(doc, 100, 10, 10)
    doc.recompute()
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    an.addObject(ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiXccxTools"))
    an.addObject(_steel(ObjectsFem, doc))
    fix = ObjectsFem.makeConstraintFixed(doc, "Fixed")
    fix.References = [(box, "Face1")]
    an.addObject(fix)
    f = ObjectsFem.makeConstraintForce(doc, "Force")
    f.References = [(box, "Face2")]
    f.Force = "100 N"
    f.Direction = (box, ["Edge5"])
    f.Reversed = True
    an.addObject(f)
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = box
    mesh.CharacteristicLengthMax = "5 mm"
    an.addObject(mesh)
    return an, mesh


def pressure_plate(doc, App, ObjectsFem):
    """A 60 x 40 x 4 plate fixed on both ends, 0.5 MPa on its top, second order tetrahedra."""
    box = _box(doc, 60, 40, 4)
    doc.recompute()
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    an.addObject(ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiXccxTools"))
    an.addObject(_steel(ObjectsFem, doc))
    fix = ObjectsFem.makeConstraintFixed(doc, "Fixed")
    fix.References = [(box, "Face1"), (box, "Face2")]
    an.addObject(fix)
    p = ObjectsFem.makeConstraintPressure(doc, "Pressure")
    p.References = [(box, "Face6")]
    p.Pressure = "0.5 MPa"
    an.addObject(p)
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = box
    mesh.CharacteristicLengthMax = "8 mm"
    mesh.ElementOrder = "2nd"
    an.addObject(mesh)
    return an, mesh


def plate_hole(doc, App, ObjectsFem):
    """A 80 x 30 x 5 plate with a 10 mm hole, fixed at one end, 2 kN along X on the other."""
    box = _box(doc, 80, 30, 5)
    cyl = doc.addObject("Part::Cylinder", "Cylinder")
    cyl.Radius, cyl.Height = 5, 5
    cyl.Placement = App.Placement(App.Vector(40, 15, 0), App.Rotation())
    doc.recompute()
    cut = doc.addObject("Part::Feature", "Cut")              # the plate as a shape (Part_SimpleCopy of a Cut)
    cut.Shape = box.Shape.cut(cyl.Shape)
    doc.recompute()
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    an.addObject(ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiXccxTools"))
    an.addObject(_steel(ObjectsFem, doc))
    fix = ObjectsFem.makeConstraintFixed(doc, "Fixed")
    fix.References = [(cut, "Face1")]
    an.addObject(fix)
    f = ObjectsFem.makeConstraintForce(doc, "Force")
    f.References = [(cut, "Face2")]
    f.Force = "2000 N"
    f.Direction = (cut, ["Edge2"])
    an.addObject(f)
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = cut
    mesh.CharacteristicLengthMax = "4 mm"
    an.addObject(mesh)
    return an, mesh


def displacement_bar(doc, App, ObjectsFem):
    """The cantilever's bar fixed at x = 0, its far end moved 0.5 mm down (a prescribed displacement)."""
    box = _box(doc, 100, 10, 10)
    doc.recompute()
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    an.addObject(ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiXccxTools"))
    an.addObject(_steel(ObjectsFem, doc))
    fix = ObjectsFem.makeConstraintFixed(doc, "Fixed")
    fix.References = [(box, "Face1")]
    an.addObject(fix)
    d = ObjectsFem.makeConstraintDisplacement(doc, "Displacement")
    d.References = [(box, "Face2")]
    d.zFree = False
    d.zDisplacement = "-0.5 mm"
    an.addObject(d)
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = box
    mesh.CharacteristicLengthMax = "5 mm"
    an.addObject(mesh)
    return an, mesh


def self_weight(doc, App, ObjectsFem):
    """The cantilever's bar under its own weight only (gravity, 9806.65 mm/s^2 down)."""
    box = _box(doc, 100, 10, 10)
    doc.recompute()
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    an.addObject(ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiXccxTools"))
    an.addObject(_steel(ObjectsFem, doc))
    fix = ObjectsFem.makeConstraintFixed(doc, "Fixed")
    fix.References = [(box, "Face1")]
    an.addObject(fix)
    an.addObject(ObjectsFem.makeConstraintSelfWeight(doc, "SelfWeight"))
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = box
    mesh.CharacteristicLengthMax = "5 mm"
    an.addObject(mesh)
    return an, mesh


def thermomech(doc, App, ObjectsFem):
    """A steel bar fixed at x = 0, held at 373 K there and 293 K at its far end, from 293 K: steady-state
    thermo-mechanical (its thermal expansion)."""
    box = _box(doc, 100, 10, 10)
    doc.recompute()
    an = ObjectsFem.makeAnalysis(doc, "Analysis")
    sol = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiXccxTools")
    sol.AnalysisType = "thermomech"
    an.addObject(sol)
    mat = _steel(ObjectsFem, doc)
    m = mat.Material
    m["ThermalConductivity"] = "50 W/m/K"
    m["ThermalExpansionCoefficient"] = "12 um/m/K"
    m["SpecificHeat"] = "500 J/kg/K"
    mat.Material = m
    an.addObject(mat)
    fix = ObjectsFem.makeConstraintFixed(doc, "Fixed")
    fix.References = [(box, "Face1")]
    an.addObject(fix)
    hot = ObjectsFem.makeConstraintTemperature(doc, "Hot")
    hot.References = [(box, "Face1")]
    hot.Temperature = "373 K"
    an.addObject(hot)
    cold = ObjectsFem.makeConstraintTemperature(doc, "Cold")
    cold.References = [(box, "Face2")]
    cold.Temperature = "293 K"
    an.addObject(cold)
    t0 = ObjectsFem.makeConstraintInitialTemperature(doc, "InitialTemperature")
    t0.InitialTemperature = "293 K"
    an.addObject(t0)
    mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
    mesh.Shape = box
    mesh.CharacteristicLengthMax = "5 mm"
    an.addObject(mesh)
    return an, mesh


CASES = {"cantilever": cantilever, "pressure_plate": pressure_plate, "plate_hole": plate_hole,
         "displacement_bar": displacement_bar, "self_weight": self_weight, "thermomech": thermomech}
