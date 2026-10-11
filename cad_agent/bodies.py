"""Bodies: what each body of an assembly is, and the machine that assembly.py describes.

`state.load_machine(slug)` returns an `Assembly`: the positioned solids and everything else assembly.py
declares, with a `BodyInfo` for every body. The rules that came with step 6 (mass, heat, deflection,
the BOM, sub-assemblies) all start from here, so none of them guesses what a body is from its name.

    parts          {body: solid}, placements.toml applied, as every gate sees them
    clearance      CLEARANCE, allow_contact ALLOW_CONTACT, axes AXES (motion.Axis), as before
    poses          POSES: {"park": {...}}, named poses of the machine. Held as declared (a dict of dicts);
                   what a pose contains and how it is applied is piece B's (subassembly.py)
    bodies         {body: BodyInfo}
    children       {name: ...} the sub-assemblies, filled by piece B; empty until then

`state.load_assembly` is the same call returning the first four as a tuple, and does not describe the
bodies (`load_machine(slug, describe=False)`), which is what the commands that only need solids use.

What a body is
--------------
`kind` is "made" (one of the project's part modules), "bought" (from bought/) or "stock" (anything
else assembly.py builds itself, an extrusion blank for one). It is decided in this order:

  1. the solid carries the tag `bought_solid` sets, so it is that bought part, whatever it is called;
     the tag follows `Pos(...) * solid`, `.moved()`, `.rotate()` and a copy, and is lost by `mirror()`,
     `scale()` and a boolean (a body made of two bought solids is not either of them);
  2. its name is a part module (`part_for`: the same name, or the name without a position or index,
     so `end_plate_left` comes from `end_plate`), so it is made;
  3. its name is a file in bought/ (`bought_stems`), so it is bought;
  4. otherwise it is stock.

scene.py (the workbench's colours and kinds) still decides by steps 2 to 4 alone, so a body it shows as
stock can be bought here: arduino_car's `arduino` is `bought_solid(SLUG, "arduino_uno")`.

The first two fields of a body say where it is from; the rest are what a rule may rest on, and each is
`None` or "envelope" when nothing declares it, never a default that looks like a measurement:

    project       the slug whose files define it (a child project's, once it is flattened in)
    part          the part module (made), the bought/ name (bought), None (stock)
    material      MATERIAL of a made part; the declared `material` of a bought one
    mass_g        made: volume x density when the material has one; bought: the declared mass_g, and
                  only when it has a mass_source; stock: None. `mass_source` says which
    max_temp_c    the highest temperature the body may sit at for its life: the declared max_temp_c of a
                  bought part (with its max_temp_source), else materials.py's max_service_temp_c for
                  its material (with its basis), else None
    geometry      "exact" for a made part, "envelope" for stock, and for a bought part what it declares
                  (default "envelope"). Only exact geometry may give stiffness or a section: a motor's
                  STEP or an extrusion blank is a solid box standing for the part
    source        where the geometry came from: parts/<part>.py, the bought part's source, assembly.py
    process, vendor, pn, verified
                  the part's PROCESS; a bought part's vendor, part number and VERIFIED flag
    notes         what could not be settled about this body, in words (a declared mass with no source,
                  a material with no density), so a rule can say why it is UNCHECKED

Sub-assemblies (piece B)
------------------------
When assembly.py declares SUBASSEMBLIES, `load_machine` hands the machine it has built and that
declaration to `cad_agent.subassembly.expand(machine, declared) -> Assembly`, which returns the same
machine with the children's bodies flattened in (`child/body` names), their clearance, allow_contact
and axes lifted with the prefix, `children` filled, and a BodyInfo for each child body it adds (its
`project` is the child's slug). Bodies it leaves without one are described here. Until that module
exists, a design that declares SUBASSEMBLIES does not load: the machine would be missing its children
and every gate would pass on less of it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import state as st

KINDS = ("made", "bought", "stock")

# Words that only say which of several a body is: end_plate_left comes from the part end_plate.
POSITION = {"left", "right", "front", "back", "top", "bottom", "upper", "lower", "inner",
            "outer", "l", "r", "fl", "fr", "bl", "br", "tl", "tr"}


@dataclass(frozen=True)
class BodyInfo:
    name: str
    kind: str                         # "made" | "bought" | "stock"
    project: str
    part: str | None = None
    material: str | None = None
    mass_g: float | None = None
    mass_source: str | None = None
    max_temp_c: float | None = None
    max_temp_source: str | None = None
    geometry: str = "envelope"        # "exact" | "envelope"
    source: str | None = None
    process: str | None = None
    vendor: str | None = None
    pn: str | None = None
    verified: bool = True
    notes: tuple = ()

    def as_dict(self) -> dict:
        d = asdict(self)
        d["notes"] = list(self.notes)
        return d


@dataclass
class Assembly:
    slug: str
    parts: dict
    clearance: dict = field(default_factory=dict)
    allow_contact: set = field(default_factory=set)
    axes: dict = field(default_factory=dict)
    poses: dict = field(default_factory=dict)
    bodies: dict = field(default_factory=dict)
    children: dict = field(default_factory=dict)

    def as_tuple(self) -> tuple:
        """(parts, clearance, allow_contact, axes): what `state.load_assembly` returns."""
        return self.parts, self.clearance, self.allow_contact, self.axes


def load_machine(slug: str, placed: bool = True, describe: bool = True) -> Assembly | None:
    """`state.load_machine`, for a caller that already imports this module."""
    return st.load_machine(slug, placed, describe)


def part_for(body: str, parts: list[str]) -> str | None:
    """The part module a body comes from: the same name, or the name without
    a position or index suffix (end_plate_left -> end_plate), or the one part
    that name ends (standoff_fl -> plate_standoff). Anything else is stock:
    gantry_beam is not a gantry_end."""
    if body in parts:
        return body
    words = body.split("_")
    while len(words) > 1 and (words[-1] in POSITION or words[-1].isdigit()):
        words.pop()
    stem = "_".join(words)
    if stem in parts:
        return stem
    hits = [p for p in parts if p.endswith("_" + stem)]
    return hits[0] if len(hits) == 1 else None


def bought_stems(pdir: Path) -> set[str]:
    d = pdir / "bought"
    return {p.stem for p in d.glob("*") if p.suffix in (".py", ".step", ".stp")} if d.is_dir() else set()


def describe(slug: str, parts: dict) -> dict[str, BodyInfo]:
    """A BodyInfo for each body in `parts` (name -> solid), judged from the project's files and the solids.

    It never raises for a body it cannot place: that body is stock, or made with `notes` that say
    what is missing, so that a rule reports UNCHECKED with a reason and not a stack trace.
    """
    from . import bought as B
    pdir = st.project_dir(slug)
    part_names = st.part_names(slug)
    stems = bought_stems(pdir)
    modules: dict = {}                                  # part module -> (material, process, note)
    specs: dict = {}                                    # (project, bought name) -> BoughtSpec or None
    out = {}
    for name, solid in parts.items():
        try:
            tag = B.tag_of(solid)
            if tag:
                out[name] = _bought(name, solid, tag.get("project") or slug, tag["name"], specs)
                continue
            part = part_for(name, part_names)
            if part:
                out[name] = _made(slug, name, solid, part, modules)
            elif name in stems:
                out[name] = _bought(name, solid, slug, name, specs)
            else:
                out[name] = BodyInfo(name=name, kind="stock", project=slug, geometry="envelope",
                                     source="assembly.py")
        except Exception as e:                          # a body we cannot describe is not worth the whole run
            out[name] = BodyInfo(name=name, kind="stock", project=slug, geometry="envelope",
                                 source="assembly.py", notes=(f"could not be described: {st.why(e)}",))
    return out


def _made(slug: str, name: str, solid, part: str, modules: dict) -> BodyInfo:
    from . import materials
    if part not in modules:
        meta = st.built_meta(slug, part)                # a run that built the part already knows
        if meta is not None:
            modules[part] = (meta.get("material"), meta.get("process"), None)
        else:
            try:
                mod = st._load_module(st.project_dir(slug) / "parts" / f"{part}.py")
                modules[part] = (getattr(mod, "MATERIAL", None), getattr(mod, "PROCESS", None), None)
            except Exception as e:                      # the assembly would not have built either
                modules[part] = (None, None, f"parts/{part}.py did not load: {st.why(e)}")
    material, process, failed = modules[part]
    notes = [failed] if failed else []
    mass = mass_source = None
    if material:
        from .geom import mass_g
        try:
            mass = mass_g(solid, material)
            mass_source = f"volume x density of {material} (materials.py)"
        except KeyError:
            notes.append(f"material {material!r} has no density in materials.py, so its mass is unknown")
    else:
        notes.append(f"parts/{part}.py declares no MATERIAL, so its mass is unknown")
    temp = materials.prop(material, "max_service_temp_c") if material else None
    return BodyInfo(
        name=name, kind="made", project=slug, part=part, material=material, mass_g=mass,
        mass_source=mass_source, max_temp_c=temp.value if temp else None,
        max_temp_source=(f"materials.py {materials.key(material)} ({temp.basis}): {temp.source}"
                         if temp else None),
        geometry="exact", source=f"parts/{part}.py", process=process, notes=tuple(notes))


def _bought(name: str, solid, project: str, bought_name: str, specs: dict) -> BodyInfo:
    from . import bought as B
    from . import materials
    key = (project, bought_name)
    if key not in specs:
        try:
            specs[key] = B.bought_spec(project, bought_name)
        except FileNotFoundError:
            specs[key] = None
    spec = specs[key]
    if spec is None:
        return BodyInfo(name=name, kind="bought", project=project, part=bought_name, geometry="envelope",
                        notes=(f"no bought part {bought_name!r} in {project}",))
    temp, temp_source = spec.max_temp_c, spec.max_temp_source
    if temp is None and spec.material:
        table = materials.prop(spec.material, "max_service_temp_c")
        if table:
            temp = table.value
            temp_source = f"materials.py {materials.key(spec.material)} ({table.basis}): {table.source}"
    return BodyInfo(
        name=name, kind="bought", project=project, part=bought_name, material=spec.material,
        mass_g=spec.mass_g, mass_source=spec.mass_source, max_temp_c=temp, max_temp_source=temp_source,
        geometry=spec.geometry, source=spec.source, vendor=spec.vendor, pn=spec.pn,
        verified=spec.verified, notes=spec.problems)
