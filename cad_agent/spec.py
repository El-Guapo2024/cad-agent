"""spec.toml: the brief as acceptance tests.

A spec says what a design must do, in terms the kernel can measure, and the
verifier checks every entry. Nothing in it is advice. An entry that cannot be
checked (a body that does not exist, a missing field, an unknown section) is
UNCHECKED, which fails the gate exactly as a FAIL does. A project with no
spec.toml is UNCHECKED too: nothing states what the design must do.

    [envelope]                  # the whole assembly's bounding box
    max_mm = [560, 520, 300]    # x, y, z; min_mm is optional

    [[size]]                    # one placed body's own bounding box, x, y, z
    body = "motor"              # min_mm and/or max_mm, at least one. Held to its real
    min_mm = [42.2, 42.2, 64]   # size, a given part can't be swapped for a smaller one
    max_mm = [42.4, 42.4, 65]

    [[position]]                # where a placed body's bounding-box center must be
    body = "motor"
    center_mm = [0, 0, 20]      # x, y, z
    tol_mm = 0.1                # distance allowed; default 0.1
    pose = "park"               # optional on position, clearance and keepout: judged with the machine at that
                                # pose of POSES in assembly.py (cad_agent/subassembly.py), the row says so

    [[clearance]]               # a gap two placed bodies must keep
    a = "x_carriage"
    b = "gantry_end_left"
    min_mm = 3.0                # min_mm and/or max_mm, at least one; overlap always fails
    max_mm = 20.0               # both bound the closest approach only: a small max_mm says "touches
                                # somewhere"; for a round part held all round, use [[shaft_fit]]

    [[keepout]]                 # a tool's volume the listed bodies must stay out of
    tool = "laser_cone"         # drill, end_mill, collet_nose, laser_cone, needle
    params = { focal_length = 210, field = 150, lens_dia = 30 }
    at = [0, 0, 0]              # where the tool point sits
    clear = ["gantry_beam"]     # or "all"

    [[mass]]                    # a weight budget over part modules
    parts = { x_carriage = 1, syringe_clamp = 1 }       # or bodies = ["x_carriage", "motor_x"], the placed
    max_g = 400                                         # bodies, or moving = "x", everything axis x moves

    [[interface]]               # bolt holes in `a` that point into `b` must line up
    a = "top_plate"             # with a hole in `b`
    b = "base_plate"
    fastener = "M3"             # optional: hole sizes must suit it
    tol_mm = 0.1                # axis offset allowed; default 0.1
    near_mm = 15                # optional: also only holes of `a` this close to `b`

    [[holes]]                   # how many holes a body has, of a size and along an axis
    body = "bracket"
    count = 4                   # or min_count and/or max_count
    min_dia_mm = 3.2            # optional, with max_dia_mm: the hole's size, its narrowest bore
    max_dia_mm = 3.6
    axis = "z"                  # optional: x, y, z or [x, y, z]; also kind = "slot" or "any"
    through = true              # optional: every hole of the size through; false, all blind; depth_mm = 8 (to the drill point's shoulder),
                                # depth_tol_mm (default 0.1)

    [[shaft_fit]]               # a round shaft in the bores of another body
    shaft = "pin_1"
    bore = "carrier"
    min_mm = 0                  # bore minus shaft diameter (diametral, so 0.1 a side is 0.2)
    max_mm = 0.2                # min_mm and/or max_mm; below 0 is a press fit; also tol_mm, pose
                                # or fit = "H7/g6" instead: ISO 286 limits for the modelled sizes, nominal_mm

    [[heat]]                    # every other body within radius_mm of the source needs a rating of temp_c
    source = "hot_plate"        # a body, or at = [x, y, z]
    temp_c = 250
    radius_mm = 15
    margin_c = 20               # optional headroom; clear = ["pcb"] also keeps those bodies out of the zone

    [[deflection]]              # a body held as a beam: the most it may sag under a load
    body = "gantry_beam"
    support = "simple"          # simple, fixed or cantilever
    load_g = 350                # or load_n, or load_moving = "y" (the mass axis y moves); self_weight = true
    max_um = 50                 # also span_mm, at, direction, axis, solid

    [[axis]]                    # the design must declare this axis in AXES, and it must do this
    name = "x"                  # a sub-assembly's axis is "gantry/x"
    moves = ["block", "tool"]   # optional: at least these (only = true: and no others); also direction,
    travel_min_mm = 80          # tol_deg, travel_max_mm, work_min_mm and tool

    [bodies]                    # exactly this many bodies, and/or exactly these names
    count = 6

    [shop]                      # the design goes to a shop: the shop part rules run, and these hold the BOM
    bom = { wheel = 2 }         # also orderable, mass and files

An interface judges holes, not every round face. A hole is the cylinders of one radius on one
axis that turn 270 degrees or more, and its size is its smallest bore, so a counterbore is part
of its hole, and a teardrop's point, a D's flat or a clamp's slit leave the bore what it was. A
slot is judged by its centre line: the other body's hole axis has to lie on it, and its width
is the size. Fillets and other shorter arcs are not holes.

It judges the holes of `a` that point into `b`: those whose axis lands on `b`, on its material
or in one of its holes. A button's cutout over a window in `b` lands on nothing, so it is no
mounting hole and needs no mate. `near_mm` adds a distance: only holes this close to `b`.

With a fastener, one hole of each pair must be a clearance hole and the other a clearance, tap
or heat-set size. Clearance is anything from ISO 273's fine to its coarse series (M3: 3.2 to
3.6 mm); a tap drill or insert bore is its table size to within 0.15 mm (`cad tables`).

Bodies are the names assembly.py places; parts in [[mass]] are part modules.

Each section is a kind: a function registered with @spec_kind in its own module of
cad_agent/speckinds/ (kit.py has what a kind uses), and check_spec runs whatever is registered. The
seven there before step 6 are documented above in full. The five that came with it (heat, deflection, axis,
bodies, shop), the two added after it (holes, shaft_fit) and the `bodies` and `moving` forms of mass are
shown above in their shape only: each
module's docstring has every key, every case it calls UNCHECKED and what it does not model. A section
nobody registered is UNCHECKED, like a malformed entry: the list of kinds is `spec.KINDS`.
"""
from __future__ import annotations

import tomllib

from . import state as st
from .registry import SpecCtx, spec_kind_names, spec_kinds
# Where these used to be defined. checks/cuts.py and the eval reference designs import `holes` from
# here, and tests/test_spec.py reaches for the helpers by name.
from .speckinds.interface import (_concave_cylinders, _kind_of, _on_hole, _on_material,  # noqa: F401
                                  _segment_gap, _sizes, holes)
from .speckinds.keepout import TOOLS  # noqa: F401
from .speckinds.kit import Unusable as _Unusable
from .speckinds.kit import row as _row


def __getattr__(name):
    if name == "KINDS":           # every registered section, in the order a message lists them
        return spec_kind_names()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def check_spec(slug: str, parts: dict, machine=None):
    """Every entry of the project's spec.toml, as rows.

    `parts` is the positioned solids; `machine` is the bodies.Assembly they came from, when the caller
    has one (the `spec` rule does), for the kinds that need more than solids.
    """
    path = st.project_dir(slug) / "spec.toml"
    if not path.exists():
        yield _row(slug, "present", "UNCHECKED",
                   "no spec.toml: nothing states what this design must do",
                   "a spec.toml with at least one requirement",
                   "write the brief as acceptance tests (see cad_agent/spec.py)")
        return
    try:
        spec = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        yield _row(slug, "present", "UNCHECKED", f"spec.toml does not parse: {e}")
        return
    names = spec_kind_names()
    unknown = sorted(set(spec) - set(names))
    for key in unknown:
        yield _row(slug, key, "UNCHECKED", f"unknown section [{key}]",
                   f"one of {', '.join(names)}")
    if not set(spec) & set(names):
        yield _row(slug, "present", "UNCHECKED", "spec.toml states no requirement",
                   f"at least one of {', '.join(names)}")
        return

    ctx = SpecCtx(slug=slug, parts=parts, machine=machine)
    for kind in spec_kinds():
        if kind.name not in spec:
            continue
        if kind.table:
            yield from _guard(kind.name, f"[{kind.name}]", lambda k=kind: k.fn(spec[k.name], ctx))
        else:
            for i, entry in enumerate(_entries(spec, kind.name), 1):
                yield from _guard(kind.name, f"[[{kind.name}]] #{i}", lambda e=entry, k=kind: k.fn(e, ctx),
                                  source=f"spec.toml [[{kind.name}]] #{i}")


def _entries(spec: dict, kind: str) -> list:
    value = spec.get(kind, [])
    return value if isinstance(value, list) else [value]


def _guard(kind, where, fn, source="spec.toml"):
    """One broken entry becomes an UNCHECKED row, never a crash that hides the rest."""
    try:
        rows = list(fn())
    except _Unusable as e:
        rows = [_row(where, kind, "UNCHECKED", str(e))]
    except Exception as e:  # noqa: BLE001 - a rule must not take the run down
        rows = [_row(where, kind, "UNCHECKED", f"{type(e).__name__}: {e}")]
    for r in rows:
        if r.source == "spec.toml":
            r.source = source
        yield r
