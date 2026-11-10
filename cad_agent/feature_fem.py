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
    """ObjectsFem.makeSolverCalculiXCcxTools: CalculiX with FreeCAD's ccxtools, a static analysis by default."""
    MAKER = "makeSolverCalculiXCcxTools"
    DEFAULTS = {"analysis_type": None}


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


KINDS = {c.__name__: c for c in (SolverCalculiX, MaterialSolid, ConstraintFixed, ConstraintForce, ConstraintPressure,
                                 ConstraintDisplacement, ConstraintSelfWeight, ConstraintTemperature,
                                 ConstraintInitialTemperature, ConstraintHeatflux, MeshGmsh)}


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
        objs = []
        for o in fem:
            for n in o.links():
                obj_of(n)
            objs.append(o.make(doc, ObjectsFem, obj_of))
            an.addObject(objs[-1])
        doc.recompute()
        meshes = [x for x in objs if x.isDerivedFrom("Fem::FemMeshObjectPython")
                  or x.isDerivedFrom("Fem::FemMeshShapeBaseObjectPython")]
        solvers = [x for x in objs if x.isDerivedFrom("Fem::FemSolverObjectPython")]
        if not meshes or not solvers:
            raise FemError("the analysis needs a MeshGmsh and a SolverCalculiX")
        err = GmshTools(meshes[0]).create_mesh()
        if err:
            raise FemError(f"Gmsh: {err}")
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
        if list(r.Temperature):          # a thermo-mechanical analysis
            out["max_temperature_k"], out["min_temperature_k"] = max(r.Temperature), min(r.Temperature)
        if workdir is not None:         # what Results > Show Result draws (cad fem result)
            import json
            from .fem_edit import surface
            s = surface(m, r)
            if s is not None:
                (Path(workdir) / RESULTS).write_text(json.dumps({**s, "nodes": out["nodes"], "volumes": out["volumes"]}))
        return out
    finally:
        App.closeDocument(doc.Name)
