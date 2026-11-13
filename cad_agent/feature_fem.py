# SPDX-License-Identifier: LGPL-2.1-or-later
# A part file's FEM analysis. Its objects are FreeCAD's (ObjectsFem.make*, cad_agent/fcfem: FreeCAD 3160daf1e2b6's FEM
# Python, LGPL-2.1-or-later, vendored unchanged), made and run over the stand-ins (cad_agent/fem_runtime.py).
"""FreeCAD's FEM analysis of a part, as FEM beside its OBJECTS or FEATURES:

    from cad_agent import feature_fem as Fem

    FEM = [
        Fem.SolverCalculiX("CalculiXccxTools"),
        Fem.MaterialSolid("Material", youngs_modulus="210000 MPa", poisson_ratio=0.3, density="7900 kg/m^3"),
        Fem.ConstraintFixed("Fixed", [("Box", "Face1")]),
        Fem.ConstraintForce("Force", [("Box", "Face2")], force="100 N", direction=("Box", "Edge5"), reversed=True),
        Fem.MeshGmsh("Mesh", "Box", characteristic_length_max="5 mm"),
    ]

One Analysis holds them, in that order, as the FEM workbench's commands add them (ObjectsFem.makeAnalysis, then each
make*). A reference is (object, element) of the part's document: a Part object by its Name, a Body feature, or "Body";
its shape is the one the part builds (feature_part.evaluate), as a Part::Feature in the stand-in document. The mesh is
Gmsh's (femmesh.gmshtools) and the solver CalculiX (femtools.ccxtools), both separate programs found on the PATH (or in
FEM's preferences), as FreeCAD runs them; neither is part of this repository.

run(path) builds the analysis, meshes it, writes CalculiX's input and runs it: the node and element counts, the largest
displacement (mm) and von Mises stress (MPa), and the files, in a working directory (out/fem/<part>/ of the project).
"""
from __future__ import annotations

import os
from pathlib import Path


RESULTS = "results.json"                # in the working directory: the mesh's outside and the result's values on it


class FemError(ValueError):
    pass


class FemObject:
    """One FEM object of the analysis: its maker in ObjectsFem and the properties it sets (FreeCAD's names in
    snake_case; references are (object, element) pairs)."""
    MAKER = ""
    POS: tuple = ()
    DEFAULTS: dict = {}
    PROPS: dict = {}                    # {key: FreeCAD's property name} where camel(key) is not it

    def __init__(self, name, *args, **kw):
        if not isinstance(name, str) or not name:
            raise FemError(f"a {type(self).__name__} needs a name")
        self.name = name
        for k, v in zip(self.POS, args):
            if k in kw:
                raise FemError(f"{name}: {k} given twice")
            kw[k] = v
        unknown = set(kw) - set(self.DEFAULTS)
        if unknown:
            raise FemError(f"{name}: {', '.join(sorted(unknown))} is not a property of a {type(self).__name__}")
        for k, d in self.DEFAULTS.items():
            setattr(self, k, kw.get(k, d))

    def prop(self, key):
        from .feature_part import camel
        return self.PROPS.get(key) or camel(key)

    def links(self):
        """The part's objects it references."""
        out = []
        for v in self.DEFAULTS:
            x = getattr(self, v)
            if v == "references":
                out += [r[0] for r in x or ()]
            elif v in ("direction", "shape") and x:
                out.append(x[0] if isinstance(x, (list, tuple)) else x)
        return out

    def make(self, doc, ObjectsFem, obj_of):
        o = getattr(ObjectsFem, self.MAKER)(doc, self.name)
        self.setup(o, obj_of)
        return o

    def setup(self, o, obj_of):
        for k in self.DEFAULTS:
            v = getattr(self, k)
            if v is None:
                continue
            if k == "references":
                setattr(o, "References", [(obj_of(r[0]), r[1]) for r in v])
            elif k == "direction":
                setattr(o, "Direction", (obj_of(v[0]), [v[1]]))
            elif k == "shape":
                setattr(o, "Shape", obj_of(v))
            else:
                setattr(o, self.prop(k), v)


class SolverCalculiX(FemObject):
    """ObjectsFem.makeSolverCalculiXCcxTools: CalculiX with FreeCAD's ccxtools, a static analysis by default
    (analysis_type "frequency" with eigenmodes_count, "buckling" with buckling_factors, or "thermomech")."""
    MAKER = "makeSolverCalculiXCcxTools"
    DEFAULTS = {"analysis_type": None, "eigenmodes_count": None, "buckling_factors": None}


class SolverElmer(FemObject):
    """ObjectsFem.makeSolverElmer: Elmer (ElmerGrid and ElmerSolver, separate programs), solving the equations made
    for it (EquationElasticity, EquationHeat): a steady state, as the Solver Elmer command makes it."""
    MAKER = "makeSolverElmer"
    DEFAULTS: dict = {}


class SolverMystran(FemObject):
    """ObjectsFem.makeSolverMystran: Mystran (a separate program, https://github.com/MystranSolver/MYSTRAN), a static
    analysis of the Fixed and Force constraints, its input written with pyNastran as FEM's Mystran writer writes it."""
    MAKER = "makeSolverMystran"
    DEFAULTS: dict = {}


class SolverZ88(FemObject):
    """ObjectsFem.makeSolverZ88: Z88 (Z88OS's z88r, a separate program, https://github.com/LSCAD/Z88OS), a static
    analysis of the Fixed, Displacement, Force and Pressure constraints, run as the FEM workbench's Run runs it
    (femsolver/z88/z88tools.py): its displacements and nodal forces (FreeCAD reads no Z88 stresses into its result)."""
    MAKER = "makeSolverZ88"
    DEFAULTS = {"solver_type": None}


class _Equation(FemObject):
    """An Elmer equation (ObjectsFem.makeEquation*(doc, solver)): one of the solver's, not the analysis's."""
    POS = ("solver",)

    def make(self, doc, ObjectsFem, obj_of, solver=None):
        if solver is None:
            raise FemError(f"{self.name}: no SolverElmer {self.solver!r} before it in FEM")
        o = getattr(ObjectsFem, self.MAKER)(doc, solver, self.name)
        self.setup(o, obj_of)
        return o

    def setup(self, o, obj_of):
        for k in self.DEFAULTS:
            v = getattr(self, k)
            if k != "solver" and v is not None:
                setattr(o, self.prop(k), v)


class EquationElasticity(_Equation):
    """ObjectsFem.makeEquationElasticity: Elmer's StressSolver (linear elasticity); its stresses (von Mises and
    principal) only when calculate_stresses (None: the equation's own default)."""
    MAKER = "makeEquationElasticity"
    DEFAULTS = {"solver": None, "calculate_stresses": None, "calculate_principal": None, "calculate_strains": None}


class EquationHeat(_Equation):
    """ObjectsFem.makeEquationHeat: Elmer's HeatSolver (the temperatures, from ConstraintTemperature and
    ConstraintHeatflux)."""
    MAKER = "makeEquationHeat"
    DEFAULTS = {"solver": None}


class MaterialSolid(FemObject):
    """ObjectsFem.makeMaterialSolid: the material card (FreeCAD's Material map: Name, YoungsModulus, PoissonRatio,
    Density, ...)."""
    MAKER = "makeMaterialSolid"
    DEFAULTS = {"material_name": "Steel", "youngs_modulus": "210000 MPa", "poisson_ratio": 0.30,
                "density": "7900 kg/m^3", "references": (), "thermal_conductivity": None,
                "thermal_expansion_coefficient": None, "specific_heat": None}
    # the Material map's keys for the thermal properties a thermo-mechanical analysis reads (None: left out)
    THERMAL = {"thermal_conductivity": "ThermalConductivity", "thermal_expansion_coefficient": "ThermalExpansionCoefficient",
               "specific_heat": "SpecificHeat"}

    def setup(self, o, obj_of):
        m = o.Material
        m["Name"] = self.material_name
        m["YoungsModulus"] = str(self.youngs_modulus)
        m["PoissonRatio"] = str(self.poisson_ratio)
        m["Density"] = str(self.density)
        for k, key in self.THERMAL.items():
            if getattr(self, k) is not None:
                m[key] = str(getattr(self, k))
        o.Material = m
        if self.references:
            o.References = [(obj_of(r[0]), r[1]) for r in self.references]


class ConstraintFixed(FemObject):
    MAKER = "makeConstraintFixed"
    POS = ("references",)
    DEFAULTS = {"references": ()}


class ConstraintForce(FemObject):
    MAKER = "makeConstraintForce"
    POS = ("references",)
    DEFAULTS = {"references": (), "force": "0 N", "direction": None, "reversed": False}


class ConstraintPressure(FemObject):
    MAKER = "makeConstraintPressure"
    POS = ("references",)
    DEFAULTS = {"references": (), "pressure": "0 MPa", "reversed": False}


class ConstraintDisplacement(FemObject):
    """ObjectsFem.makeConstraintDisplacement: each axis free, or held at a displacement (and each rotation)."""
    MAKER = "makeConstraintDisplacement"
    POS = ("references",)
    DEFAULTS = {"references": (), "x_free": True, "x_displacement": "0 mm", "y_free": True, "y_displacement": "0 mm",
                "z_free": True, "z_displacement": "0 mm", "rotx_free": True, "x_rotation": "0 deg", "roty_free": True,
                "y_rotation": "0 deg", "rotz_free": True, "z_rotation": "0 deg"}
    PROPS = {"x_free": "xFree", "x_displacement": "xDisplacement", "y_free": "yFree", "y_displacement": "yDisplacement",
             "z_free": "zFree", "z_displacement": "zDisplacement", "rotx_free": "rotxFree", "x_rotation": "xRotation",
             "roty_free": "rotyFree", "y_rotation": "yRotation", "rotz_free": "rotzFree", "z_rotation": "zRotation"}


class ConstraintSelfWeight(FemObject):
    """ObjectsFem.makeConstraintSelfWeight: gravity on the whole part (no references)."""
    MAKER = "makeConstraintSelfWeight"
    DEFAULTS = {"gravity_acceleration": "9806.65 mm/s^2", "gravity_direction": (0.0, 0.0, -1.0)}

    def setup(self, o, obj_of):
        import FreeCAD as App
        o.GravityAcceleration = self.gravity_acceleration
        o.GravityDirection = App.Vector(*self.gravity_direction)


class ConstraintTemperature(FemObject):
    """ObjectsFem.makeConstraintTemperature: a temperature held on the references (or a concentrated heat flux)."""
    MAKER = "makeConstraintTemperature"
    POS = ("references",)
    DEFAULTS = {"references": (), "temperature": "300 K", "constraint_type": "Temperature",
                "concentrated_heat_flux": "0 W"}


class ConstraintInitialTemperature(FemObject):
    """ObjectsFem.makeConstraintInitialTemperature: the whole part's temperature at the start (no references)."""
    MAKER = "makeConstraintInitialTemperature"
    DEFAULTS = {"initial_temperature": "300 K"}


class ConstraintHeatflux(FemObject):
    """ObjectsFem.makeConstraintHeatflux: convection to an ambient temperature, or a distributed heat flux (DFlux)."""
    MAKER = "makeConstraintHeatflux"
    POS = ("references",)
    DEFAULTS = {"references": (), "constraint_type": "Convection", "film_coef": "0 W/m^2/K", "ambient_temp": "0 K",
                "distributed_heat_flux": "0 W/m^2"}
    PROPS = {"ambient_temp": "AmbientTemp", "film_coef": "FilmCoef", "distributed_heat_flux": "DistributedHeatFlux"}


class MeshGmsh(FemObject):
    """ObjectsFem.makeMeshGmsh: the shape to mesh and Gmsh's parameters."""
    MAKER = "makeMeshGmsh"
    POS = ("shape",)
    DEFAULTS = {"shape": None, "characteristic_length_max": None, "characteristic_length_min": None,
                "element_order": None, "element_dimension": None}


KINDS = {c.__name__: c for c in (SolverCalculiX, SolverElmer, SolverMystran, SolverZ88, EquationElasticity, EquationHeat, MaterialSolid,
                                 ConstraintFixed, ConstraintForce, ConstraintPressure, ConstraintDisplacement,
                                 ConstraintSelfWeight, ConstraintTemperature, ConstraintInitialTemperature,
                                 ConstraintHeatflux, MeshGmsh)}


def load(path):
    """(the part module's FEM list, its loaded module pieces as feature_attach._load returns them)."""
    from . import feature  # noqa: F401  (feature_attach is loaded through it)
    from .feature_attach import _load
    mod, features, params, base, objects = _load(Path(path))
    fem = list(getattr(mod, "FEM", None) or [])
    if not fem:
        raise FemError(f"{Path(path).name} has no FEM analysis (FEM = [...])")
    for o in fem:
        if not isinstance(o, FemObject):
            raise FemError(f"FEM holds {o!r}, not a FEM object")
    return fem, mod, features, params, base, objects


def run(path, workdir=None, threads=None) -> dict:
    """Build the part's analysis in a stand-in document, mesh it with Gmsh, run CalculiX: its results. What FEM's
    Python prints (its own debugging lines) goes to the result's "log", not to the command's output."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = _run(path, workdir, threads)
    out["log"] = buf.getvalue()
    return out


def _run(path, workdir=None, threads=None) -> dict:
    from . import feature_part as P
    fem, mod, features, params, base, objects = load(path)
    shapes = P.evaluate(objects, params, features if hasattr(mod, "FEATURES") else None, base,
                        getattr(mod, "TIP", None))
    from . import fem_runtime
    fem_runtime.activate()
    import FreeCAD as App
    import ObjectsFem
    import Part
    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools
    if threads is not None:
        App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetInt("NumOfThreads", int(threads))
    if workdir is not None:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        g = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/General")
        g.SetBool("UseTempDirectory", False)
        g.SetBool("UseCustomDirectory", True)
        g.SetString("CustomDirectoryPath", str(workdir))
    doc = App.newDocument("Fem")
    made = {}

    def obj_of(name):
        if name not in made:
            if name not in shapes or shapes[name] is None:
                raise FemError(f"no object {name!r} in the part")
            f = doc.addObject("Part::Feature", name)
            f.Shape = Part.Shape(shapes[name])
            made[name] = f
        return made[name]

    try:
        an = ObjectsFem.makeAnalysis(doc, "Analysis")
        objs, by_name = [], {}
        for o in fem:
            for n in o.links():
                obj_of(n)
            if isinstance(o, _Equation):
                s = by_name.get(o.solver)
                if s is not None and getattr(s.Proxy, "Type", "") != "Fem::SolverElmer":
                    s = None
                by_name[o.name] = o.make(doc, ObjectsFem, obj_of, s)     # the solver's, not the analysis's
                continue
            objs.append(o.make(doc, ObjectsFem, obj_of))
            by_name[o.name] = objs[-1]
            an.addObject(objs[-1])
        doc.recompute()
        meshes = [x for x in objs if x.isDerivedFrom("Fem::FemMeshObjectPython")
                  or x.isDerivedFrom("Fem::FemMeshShapeBaseObjectPython")]
        solvers = [x for x in objs if x.isDerivedFrom("Fem::FemSolverObjectPython")]
        if not meshes or not solvers:
            raise FemError("the analysis needs a MeshGmsh and a solver (SolverCalculiX, SolverElmer, SolverMystran or SolverZ88)")
        err = GmshTools(meshes[0]).create_mesh()
        if err:
            raise FemError(f"Gmsh: {err}")
        if getattr(solvers[0].Proxy, "Type", "") == "Fem::SolverElmer":
            return _run_elmer(an, solvers[0], meshes[0], workdir)
        if getattr(solvers[0].Proxy, "Type", "") == "Fem::SolverMystran":
            return _run_mystran(an, solvers[0], meshes[0], workdir)
        if getattr(solvers[0].Proxy, "Type", "") == "Fem::SolverZ88":
            return _run_z88(an, solvers[0], meshes[0], workdir)
        fea = ccxtools.FemToolsCcx(an, solvers[0])
        fea.update_objects()
        fea.setup_working_dir()
        fea.setup_ccx()
        msg = fea.check_prerequisites()
        if msg:
            raise FemError(msg.strip())
        fea.purge_results()
        fea.write_inp_file()
        fea.ccx_run()
        fea.load_results()
        res = [x for x in doc.Objects if x.isDerivedFrom("Fem::FemResultObject")]
        if not res:
            raise FemError("CalculiX gave no results: " + (getattr(fea, "ccx_stderr", "") or "").strip()[-400:])
        r = res[0]
        m = meshes[0].FemMesh
        out = {"nodes": m.NodeCount, "volumes": m.VolumeCount, "max_displacement_mm": max(r.DisplacementLengths),
               "max_von_mises_mpa": max(r.vonMises), "inp": fea.inp_file_name,
               "workdir": os.path.dirname(fea.inp_file_name)}
        modes = [x for x in res if getattr(x, "EigenmodeFrequency", 0)]
        if modes:                        # a frequency analysis: one result per mode, the first one's values above
            out["frequencies_hz"] = [x.EigenmodeFrequency for x in modes]
        factors = None
        if any("BucklingFactor_" in x.Name for x in res):   # a buckling analysis: the static result, then each mode
            dat = os.path.splitext(fea.inp_file_name)[0] + ".dat"
            factors = buckling_factors(Path(dat).read_text(errors="replace"))
            out["buckling_factors"] = factors
        if list(r.Temperature):          # a thermo-mechanical analysis
            out["max_temperature_k"], out["min_temperature_k"] = max(r.Temperature), min(r.Temperature)
        if workdir is not None:         # what Results > Show Result draws (cad fem result)
            import json
            from .fem_edit import surface
            s = surface(m, r)
            if s is not None and modes:  # each mode's shape and values on the same outside
                s["modes"] = [{"frequency": x.EigenmodeFrequency, **{k: v for k, v in surface(m, x).items()
                                                                      if k in ("displacement", "fields", "range", "histogram")}}
                              for x in modes]
            if s is not None and factors:  # each buckling mode's shape, after the static result
                s["modes"] = [{"factor": f, **{k: v for k, v in surface(m, x).items()
                                               if k in ("displacement", "fields", "range", "histogram")}}
                              for f, x in zip(factors, res[1:])]
            if s is not None:
                (Path(workdir) / RESULTS).write_text(json.dumps({**s, "nodes": out["nodes"], "volumes": out["volumes"]}))
        return out
    finally:
        App.closeDocument(doc.Name)


def buckling_factors(dat):
    """CalculiX's .dat BUCKLING FACTOR OUTPUT table (its *BUCKLE step): each mode's factor, in order. FreeCAD names each
    mode's result by its factor (importCcxFrdResults: CCX_BucklingFactor_<factor to 2 decimals>_Results)."""
    lines = dat.splitlines()
    try:
        i = next(k for k, line in enumerate(lines) if "B U C K L I N G" in line)
    except StopIteration:
        return []
    out = []
    for line in lines[i + 1:]:
        t = line.split()
        if len(t) == 2 and t[0].isdigit():
            out.append(float(t[1]))
        elif out and t:
            break
    return out


def _run_elmer(an, solver, mesh, workdir):
    """Elmer as the FEM workbench's Run runs it (femsolver.run.run_fem_solver: the writer's case.sif, the mesh as
    .unv through ElmerGrid, ElmerSolver), its results read back into the solver's FemPostPipeline."""
    import tempfile
    import FreeCAD as App
    from femsolver.run import run_fem_solver
    from femsolver import settings
    for b in ("ElmerGrid", "ElmerSolver"):
        import shutil
        if not shutil.which(settings.get_binary(b, silent=True) or b):
            raise FemError(f"{b} is not on the PATH (Elmer, https://www.elmerfem.org, runs the SolverElmer)")
    wd = str(workdir) if workdir is not None else tempfile.mkdtemp(prefix="fem_")
    start = len(App.Console.log)
    run_fem_solver(solver, wd, blocking=True)
    errors = [m for k, m in App.Console.log[start:] if k == "Err" and "DisplayMode" not in m]
    pipes = [r for r in solver.Results if r.isDerivedFrom("Fem::FemPostPipeline")]
    data = pipes[0].Data if pipes else None
    if data is None:
        raise FemError("Elmer gave no results: " + ("".join(errors).strip()[-400:] or f"see {wd}"))
    from cad_agent.fcshim import _fc_fempost
    frames = [_ElmerResult(f, mesh.FemMesh, wd) for f in _fc_fempost.frames(data)]
    r = frames[0]
    m = mesh.FemMesh
    out = {"nodes": m.NodeCount, "volumes": m.VolumeCount, "solver": "Elmer",
           "max_displacement_mm": max(r.DisplacementLengths) if r.DisplacementLengths else 0.0,
           "max_von_mises_mpa": max(r.vonMises) if r.vonMises else 0.0,
           "sif": os.path.join(wd, "case.sif"), "workdir": wd}
    if r.Temperature:
        out["max_temperature_k"], out["min_temperature_k"] = max(r.Temperature), min(r.Temperature)
    if workdir is not None:
        import json
        from .fem_edit import surface
        s = surface(m, r)
        if s is not None:
            (Path(workdir) / RESULTS).write_text(json.dumps({**s, "nodes": out["nodes"], "volumes": out["volumes"]}))
    return out


def _run_mystran(an, solver, mesh, workdir):
    """Mystran as femsolver/mystran/tasks.py's Prepare and Solve run it: the writer's .bdf (pyNastran's), `mystran
    Mesh.bdf` in the folder. FreeCAD 26.3's own run stops in Prepare (its `get_mesh_to_solve(...)[0]`: the function
    returns the mesh itself now), so these are its lines without the [0] (tests/golden/fem_mystran/make.py's). FreeCAD
    reads no Mystran results without the hfcMystranNeuIn add-on; they are read from the .F06 here (mystran_f06)."""
    import shutil
    import subprocess
    import tempfile
    from femsolver import settings
    binary = shutil.which(settings.get_binary("Mystran", silent=True) or "mystran")
    if not binary:
        raise FemError("mystran is not on the PATH (Mystran, https://github.com/MystranSolver/MYSTRAN, runs the "
                       "SolverMystran)")
    try:
        import numpy
        if not hasattr(numpy, "in1d"):          # numpy 2.4 dropped it; pyNastran 1.4 still calls it
            numpy.in1d = numpy.isin
        import pyNastran.bdf.bdf  # noqa: F401
    except ImportError:
        raise FemError("pyNastran is not installed (pip install pyNastran: FEM's Mystran writer writes with it)")
    import importlib
    from femmesh import meshsetsgetter
    from femsolver.mystran import writer
    from femtools import membertools
    if not hasattr(writer, "BDF"):              # imported before pyNastran was there
        importlib.reload(writer)
    for c in membertools.get_member(an, "Fem::Constraint"):
        t = getattr(getattr(c, "Proxy", None), "Type", None) or c.TypeId
        if t not in ("Fem::ConstraintFixed", "Fem::ConstraintForce"):
            raise FemError(f"{c.Name}: FEM's Mystran writer takes Fixed and Force constraints only, not {t}")
    wd = str(workdir) if workdir is not None else tempfile.mkdtemp(prefix="fem_")
    Path(wd).mkdir(parents=True, exist_ok=True)
    g = meshsetsgetter.MeshSetsGetter(an, solver, mesh, membertools.AnalysisMember(an))
    g.get_mesh_sets()
    bdf = writer.FemInputWriterMystran(an, solver, mesh, g.member, wd).write_solver_input()
    p = subprocess.run([binary, os.path.basename(bdf)], cwd=wd, capture_output=True, text=True)
    f06 = Path(wd, os.path.splitext(os.path.basename(bdf))[0] + ".F06")
    from .mystran_f06 import read_f06
    try:
        res = read_f06(f06.read_text(errors="replace"))
    except (OSError, ValueError):
        err = Path(wd, f06.stem + ".ERR")
        tail = err.read_text(errors="replace") if err.exists() else (p.stdout + p.stderr)
        raise FemError("Mystran gave no results: " + (tail.strip()[-400:] or f"see {wd}"))
    r = _MystranResult(res, mesh.FemMesh)
    m = mesh.FemMesh
    out = {"nodes": m.NodeCount, "volumes": m.VolumeCount, "solver": "Mystran",
           "max_displacement_mm": max(r.DisplacementLengths),
           "max_von_mises_mpa": max(res["von_mises"].values()) if res["von_mises"] else 0.0,
           "bdf": bdf, "workdir": wd}
    if workdir is not None:
        import json
        from .fem_edit import surface
        s = surface(m, r)
        if s is not None:
            (Path(workdir) / RESULTS).write_text(json.dumps({**s, "nodes": out["nodes"], "volumes": out["volumes"]}))
    return out


def _run_z88(an, solver, mesh, workdir):
    """Z88 as the FEM workbench's Run runs it (femsolver.run.run_fem_solver: z88tools.Z88Tools writes z88i1.txt and
    the rest, runs `z88r -t` then `z88r -c`, and reads z88o0/o2/o4.txt into the solver's FemPostPipeline)."""
    import shutil
    import tempfile
    import FreeCAD as App
    from femsolver.run import run_fem_solver
    from femsolver import settings
    if not shutil.which(settings.get_binary("Z88", silent=True) or "z88r"):
        raise FemError("z88r is not on the PATH (Z88OS, https://github.com/LSCAD/Z88OS, runs the SolverZ88)")
    try:
        import vtkmodules  # noqa: F401
    except ImportError:
        raise FemError("VTK's Python is not installed (pip install \"cad-agent[fem]\": FEM's Z88 tools read its results "
                       "with it)")
    from femtools import membertools
    for c in membertools.get_member(an, "Fem::Constraint"):
        t = getattr(getattr(c, "Proxy", None), "Type", None) or c.TypeId
        if t not in ("Fem::ConstraintFixed", "Fem::ConstraintForce", "Fem::ConstraintPressure",
                     "Fem::ConstraintDisplacement"):
            raise FemError(f"{c.Name}: FEM's Z88 writer takes Fixed, Displacement, Force and Pressure constraints "
                           f"only, not {t}")
    wd = str(workdir) if workdir is not None else tempfile.mkdtemp(prefix="fem_")
    Path(wd).mkdir(parents=True, exist_ok=True)
    start = len(App.Console.log)
    run_fem_solver(solver, wd, blocking=True)
    errors = [m for k, m in App.Console.log[start:] if k == "Err" and "DisplayMode" not in m]
    pipes = [r for r in solver.Results if r.isDerivedFrom("Fem::FemPostPipeline")]
    data = pipes[0].Data if pipes else None
    arrays = data.GetPointData() if data is not None else None
    if arrays is None or not arrays.HasArray("Displacement"):
        log = Path(wd, "z88r.log")
        tail = "".join(errors) or (log.read_text(errors="replace") if log.exists() else "")
        raise FemError("Z88 gave no results: " + (tail.strip()[-400:] or f"see {wd}"))
    r = _Z88Result(data, mesh.FemMesh)
    m = mesh.FemMesh
    out = {"nodes": m.NodeCount, "volumes": m.VolumeCount, "solver": "Z88",
           "max_displacement_mm": max(r.DisplacementLengths), "max_von_mises_mpa": None,
           "max_nodal_force_n": max(r.NodalForces) if r.NodalForces else 0.0,
           "z88i1": os.path.join(wd, "z88i1.txt"), "workdir": wd}
    if workdir is not None:
        import json
        from .fem_edit import surface
        s = surface(m, r)
        if s is not None:
            (Path(workdir) / RESULTS).write_text(json.dumps({**s, "nodes": out["nodes"], "volumes": out["volumes"]}))
    return out


class _Z88Result:
    """Z88's result (the pipeline's Data: z88o0.txt's points, z88o2.txt's displacements, z88o4.txt's nodal forces) as
    a FemResultObject's values at the mesh's nodes. FEM's Z88 writer numbers the nodes of the mesh's elements 1, 2, ...
    in the order of their numbers (writer.py's write_z88_mesh), the pipeline's points in that order."""

    def __init__(self, grid, femmesh):
        from vtkmodules.util import numpy_support as ns
        import FreeCAD as App
        used = set()
        for e in femmesh.Volumes or femmesh.Faces or femmesh.Edges:
            used.update(femmesh.getElementNodes(e))
        self.NodeNumbers = sorted(used)
        if len(self.NodeNumbers) != grid.GetNumberOfPoints():
            raise FemError("Z88's results are not on the mesh's nodes (z88o0.txt)")
        pd = grid.GetPointData()

        def arr(name):
            a = pd.GetArray(name)
            return None if a is None else ns.vtk_to_numpy(a).reshape(a.GetNumberOfTuples(), -1)
        d = arr("Displacement")
        self.DisplacementVectors = [App.Vector(*(float(x) for x in v[:3])) for v in d]
        self.DisplacementLengths = [v.Length for v in self.DisplacementVectors]
        f = arr("Nodal Force")
        self.NodalForces = [float(sum(float(x) ** 2 for x in v) ** 0.5) for v in f] if f is not None else []
        self.vonMises = self.PrincipalMax = self.PrincipalMin = self.Temperature = []
        self.EigenmodeFrequency = 0.0


class _MystranResult:
    """Mystran's results (mystran_f06.read_f06) as a FemResultObject's values at the mesh's nodes (Mystran's grids are
    the mesh's nodes, by number: exportNastranMesh's GRID cards), in the mesh's units (mm, N, MPa). Mystran gives each
    solid's stress at its centre; a node's von Mises is the mean of those of the solids it is a corner of."""

    def __init__(self, res, femmesh):
        import FreeCAD as App
        self.NodeNumbers = sorted(femmesh.Nodes)
        d = res["displacement"]
        self.DisplacementVectors = [App.Vector(*d.get(n, (0.0, 0.0, 0.0))) for n in self.NodeNumbers]
        self.DisplacementLengths = [v.Length for v in self.DisplacementVectors]
        acc = {}
        for eid, vm in res["von_mises"].items():
            try:
                nodes = femmesh.getElementNodes(eid)
            except Exception:
                continue
            for n in nodes:
                a = acc.setdefault(n, [0.0, 0])
                a[0] += vm
                a[1] += 1
        self.vonMises = [acc[n][0] / acc[n][1] if n in acc else 0.0 for n in self.NodeNumbers] if acc else []
        self.PrincipalMax = self.PrincipalMin = self.Temperature = []
        self.EigenmodeFrequency = 0.0


class _ElmerResult:
    """An Elmer result (one frame of the pipeline's Data, ElmerSolver's .vtu) as a FemResultObject's values at the
    mesh's nodes, in FreeCAD's units (mm, MPa, K). The .vtu's points are ElmerGrid's nodes in its order (mesh.nodes,
    where they are as meshed: Elasticity's Displace Mesh moves the .vtu's), each found in the mesh by its position."""

    def __init__(self, grid, femmesh, workdir):
        from vtkmodules.util import numpy_support as ns
        import FreeCAD as App
        key = {}
        for n, p in femmesh.Nodes.items():
            key[(round(p.x, 6), round(p.y, 6), round(p.z, 6))] = n
        idx = []
        with open(os.path.join(workdir, "mesh.nodes")) as f:
            for line in f:
                t = line.split()
                n = key.get(tuple(round(float(x), 6) for x in t[2:5]))
                if n is None:
                    raise FemError("ElmerGrid's nodes (mesh.nodes) are not the mesh's")
                idx.append(n)
        if len(idx) != grid.GetNumberOfPoints():
            raise FemError("Elmer's results are not on ElmerGrid's nodes (mesh.nodes)")
        self.NodeNumbers = idx
        pd = grid.GetPointData()

        def arr(name):
            a = pd.GetArray(name)
            return None if a is None else ns.vtk_to_numpy(a).reshape(a.GetNumberOfTuples(), -1)
        d = arr("displacement")
        self.DisplacementVectors = ([App.Vector(*(float(x) * 1e3 for x in v[:3])) for v in d] if d is not None
                                    else [App.Vector() for _ in idx])
        self.DisplacementLengths = [v.Length for v in self.DisplacementVectors] if d is not None else []
        vm = arr("vonmises")
        self.vonMises = [float(v[0]) * 1e-6 for v in vm] if vm is not None else []
        ps = arr("principal stress")             # the three principal stresses: the largest and the smallest
        self.PrincipalMax = [float(max(v)) * 1e-6 for v in ps] if ps is not None else []
        self.PrincipalMin = [float(min(v)) * 1e-6 for v in ps] if ps is not None else []
        t = arr("temperature")
        self.Temperature = [float(v[0]) for v in t] if t is not None else []
        self.EigenmodeFrequency = 0.0
