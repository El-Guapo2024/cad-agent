"""Sub-assemblies and poses: a machine made of sibling projects, the way FreeCAD links another document.

A machine is too big for one assembly.py. The gantry is a design of its own, with its parts, its gates and its
own `cad verify`; the project that carries it says where it stands, and the machine is the two together:

    SUBASSEMBLIES = {
        "gantry": {"project": "gantry", "at": [0, 0, 120], "turn": [0, 0, 90]},
    }
    POSES = {"park": {"gantry/x": -150, "gantry/y": 0}}

`state.load_machine` hands the machine it has built and that declaration to `expand`, which returns the same
machine with every child flattened in. Nothing is copied into the parent's folder: the child is read where it
lives, so an edit to it is an edit to the machine.

What a declaration says
-----------------------
The key is the instance name and the prefix of its bodies, so one project can be placed twice ("z_left" and
"z_right" both of the project z_tower). `project` is a folder next to the parent's under the projects root
(never a path). `at` and `turn` are a rigid move of the child's whole frame: `turn` is [rx, ry, rz] degrees,
Rx . Ry . Rz about the child's own origin, then `at` in mm, which is `Pos(*at) * Rot(*turn)` in build123d and
what placements.toml means by a move. No mirror and no scale: `mirror()` drops what a body is (bodies.py).

What flattening does
--------------------
  bodies          `gantry/x_carriage`: the instance name, a "/", the child's body name. A child's own children
                  nest (`gantry/pulley/belt`). The solids are the child's as it loads (its placements.toml
                  applied), moved by the instance's frame
  BodyInfo        the child's, with the name prefixed; `project` stays the child's (or the grandchild's), which
                  is how the BOM nests, `cad shop` leaves a child's parts to the child's shop, and a rule finds
                  the module a part came from
  CLEARANCE, ALLOW_CONTACT
                  the child's, both names of every pair prefixed. The parent's own entry for a pair wins
  AXES            the child's, named `gantry/x`, moving the prefixed bodies. `direction` and `tool_point` turn
                  with the instance; `travel` and `work` are distances along the axis and stay. So a rule that
                  reads AXES (sweep, reach, com, [[mass]] moving=) sees the child's axes in the parent's frame
  POSES           the child's, named `gantry/park`, driving the prefixed axes
  the parent      may name a whole instance in an axis's `moves` as "gantry/*" (every body under it), since
                  its assembly.py cannot know a child's body names when it declares the axis
  children        {instance: Child}: the project, the frame, the depth, the names it added, and the child's own
                  Assembly in its own frame, which the parent's check hands to the child's gates

What stays the child's
----------------------
Each child is a full project: `cad check gantry` and `cad verify gantry` work on it alone, and a design that is
not done on its own does not become done by being linked. So the parent's check runs every gate of every
project in the tree, each as `cad check <child>` runs it, and reports the rows as `gantry:geometry/...`
(runner.py); the parent's verify rebuilds all of it from source in the one fresh process and never reads a
child's verify.json or checks.json, which are claims and not evidence. verify.py hashes the files of every
project in the tree (`tree_projects` finds them by reading assembly.py's source, without running it) and
cross-checks that list against what the run loaded. The build cache keeps a child's parts in the child's own
cache, keyed by the child's files, so an edit to a child is a miss there; buildcache.py also folds the tree's
files into the key of a parent's part that runs other files (it calls build_part or opens a file).

A parent is not done until every child is. The child's visual rows wait for `cad approve <child>` like any
project's, and a child with no spec.toml holds the parent open (`<child>:spec/present`). Each project's gates run
once for the tree, however many instances link it. Cost, measured on a laptop with simple parts: `verify` takes
2.0 s for 20 bodies (a parent of 6 and two sub-assemblies of 7) against 1.1 s for the same bodies in one project,
and 11 to 13 s against 6 to 7 s for 80. The fit rule's exact distance for every pair dominates, and the pairs
inside a child are measured twice (in its own check and in the parent's flattened one); a machine of heavy STEP
bodies costs more for each pair.

Failures are FAIL rows, never a crash. `expand` raises SubassemblyError with one Problem for each fault and the
runner turns each into a row (`subassembly/cycle`, `/depth`, `/name`, `/project`, `/build`, `/declaration`,
`/moves`):
  cycle         a project is its own ancestor (the chain is in the row)
  depth         more than MAX_DEPTH levels of sub-assemblies
  name          "/" in a body or instance name that is not the prefix of a sub-assembly's body, or a body that
                has an instance's name. The "/" is how a child's bodies are named, so a body that has one of
                its own would be taken for a child's
  project       the project does not exist or has no assembly.py
  build         the child's assembly.py or one of its parts raised
  declaration   not {project, at, turn}, or an `at` or `turn` that is not three numbers
  moves         "gantry/*" in an axis's moves with no sub-assembly or no body to match
A child's malformed placements.toml stays a PlacementError, which fails closed with its own message.

Hand moves. The parent's placements.toml may move a child's body by its full name (`cad place parent
gantry/x_carriage ...`, a quoted key in the file): load_machine applies the file after flattening, so the gates
and the workbench see the move. The child's own placements.toml is the child's design and is always applied.

Poses. A pose is a set of axis positions, `{axis: mm}` from home inside the axis's travel, and `apply_pose`
drives them all at once (translations add, so the order does not matter). `pose = "park"` on a [[clearance]],
[[keepout]] or [[position]] judges that entry with the machine there instead of at home; the `poses` rule
(ruleset/subassembly.py) checks every declared pose. Axes are driven one at a time by `sweep`; a pose is the
only place two axes are off home together, at the positions someone named.

Not here: a mirrored or scaled instance, a child moved by hand from the parent's workbench as a unit, the
product of two axes' travels (step 8), and the workbench's tree nesting (the viewer sees a flat name).

FreeCAD. This is its sub-assembly link, `Assembly::AssemblyLink` (src/Mod/Assembly/App/AssemblyLink.cpp at
3160daf1e2b6): a link to another assembly (LinkedObject) with a Placement of its own and a Rigid switch. Rigid
means the child acts as one body in the parent; otherwise its joints are taken into account, and
`synchronizeComponents` mirrors the child's objects into the link while `handleJointReference` points the
copied joints at the link's own objects. Here the bodies stay rigid at home, the child's axes (its joints) are
kept, and the pointing is a prefix on every name. FreeCAD's Placement is a base and a rotation applied to
the linked object's frame, which is what `at` and `turn` are. What FreeCAD does with that Placement is more than
this keeps: a link that goes flexible has its Placement reset to the identity and baked into its children's
(AssemblyLink.cpp:192-237), and a rigid one keeps every component's placement synchronized with its source
(`updateContents`, 536-541). Neither file has a LinkTransform or a mirror.

This module imports no CAD kernel until it needs one, so `cad done` can read the tree's files without it.
"""
from __future__ import annotations

import ast
import math
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from . import state as st
from .placements import PlacementError
from .registry import TOL_MM, Row

MAX_DEPTH = 8                       # levels of sub-assemblies below the project being checked
KEYS = ("project", "at", "turn")    # what a SUBASSEMBLIES entry may say
ALL_OF = "/*"                       # in an axis's `moves`: every body under that instance
NAME = "SUBASSEMBLIES"

_PATH: ContextVar = ContextVar("subassembly_path", default=())   # projects above the one being loaded


@dataclass(frozen=True)
class Problem:
    subject: str        # the sub-assembly, body or axis the fault is about
    kind: str           # declaration | project | build | cycle | depth | name | moves
    message: str


LIMITS = {
    "declaration": '{"project": ..., "at": [x, y, z], "turn": [rx, ry, rz]}',
    "project": "a project next to this one, with an assembly.py",
    "build": "a sub-assembly project that builds",
    "cycle": "a tree with no project above itself",
    "depth": f"at most {MAX_DEPTH} levels of sub-assemblies",
    "name": 'no "/" in a body\'s name unless a sub-assembly owns it',
    "moves": 'a sub-assembly with bodies for "name/*" to move',
}


class SubassemblyError(ValueError):
    """assembly.py's SUBASSEMBLIES cannot be flattened in. `problems` says why, one for each fault."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(p.message for p in self.problems))

    def rows(self) -> list:
        """A FAIL row for each fault, as the runner reports them: check `subassembly`, the kind as the rule."""
        return [Row(subject=p.subject, rule=p.kind, state="FAIL", measured=p.message,
                    limit=LIMITS.get(p.kind, "sub-assemblies that can be flattened in"),
                    source="SUBASSEMBLIES in assembly.py", check="subassembly") for p in self.problems]


class PoseError(ValueError):
    """A pose that cannot be applied: no such pose, an axis that is not declared, a position outside travel."""


@dataclass
class Child:
    """One sub-assembly of a machine, as `Assembly.children` holds it."""
    name: str                   # the instance: the prefix of its bodies
    project: str
    at: tuple
    turn: tuple
    depth: int                  # 1 for a child of the project being checked, 2 for its child's child
    bodies: tuple               # the names it added to the parent, nested ones included
    axes: tuple                 # the axes it added
    projects: tuple             # this project and every project under it, each once
    machine: object = field(default=None, repr=False, compare=False)   # its Assembly, in its own frame

    def as_dict(self) -> dict:
        return {"name": self.name, "project": self.project, "at": list(self.at), "turn": list(self.turn),
                "depth": self.depth, "bodies": len(self.bodies), "axes": list(self.axes),
                "projects": list(self.projects)}


@dataclass
class _Lifted:
    child: Child
    parts: dict
    bodies: dict
    clearance: dict
    allow_contact: set
    axes: dict
    poses: dict


# ─── Names ───────────────────────────────────────────────────────────────────

def split(name: str) -> tuple[str | None, str]:
    """('gantry', 'x_carriage') for 'gantry/x_carriage', (None, name) for a body of the project itself."""
    head, slash, rest = name.partition("/")
    return (head, rest) if slash else (None, name)


def file_stem(name: str) -> str:
    """A body's name as the stem of a file: 'gantry/x_carriage' -> 'gantry__x_carriage'. Whatever writes a file
    named after a body uses this, because a "/" in the name would make a folder."""
    return name.replace("/", "__")


def name_rule(name: str) -> str:
    return (f"{name!r} has a \"/\", which is how a sub-assembly's bodies are named (gantry/x_carriage): "
            "a body of a project's own cannot have one")


# ─── The frame of an instance ────────────────────────────────────────────────

def _frame(at, turn) -> dict:
    return {"move": tuple(at), "turn": tuple(turn), "about": (0.0, 0.0, 0.0)}


def instance_matrix(at, turn) -> list:
    """The 3x4 matrix [R | at] of an instance: p' = R p + at, R = Rx . Ry . Rz of `turn` in degrees."""
    from . import placements
    return placements.matrix(_frame(at, turn))


def instance_location(at, turn):
    """The build123d Location of an instance: Pos(*at) * Rot(*turn)."""
    from . import placements
    return placements.location(_frame(at, turn))


def _turned(m, v) -> tuple:
    """A direction or an offset turned by the rotation part of `m`, without the noise of a quarter turn."""
    return tuple(round(sum(m[i][j] * v[j] for j in range(3)), 12) + 0.0 for i in range(3))


# ─── The declaration ─────────────────────────────────────────────────────────

def _fault(subject: str, kind: str, message: str) -> SubassemblyError:
    return SubassemblyError([Problem(subject, kind, message)])


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _vec(inst: str, key: str, value) -> tuple:
    if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(_number(x) for x in value)):
        raise _fault(inst, "declaration", f"{inst!r}: `{key}` must be three numbers [x, y, z], got {value!r}")
    return tuple(float(x) for x in value)


def declaration(inst, decl) -> tuple[str, tuple, tuple]:
    """(project, at, turn) of one SUBASSEMBLIES entry; SubassemblyError for what cannot be used."""
    if not isinstance(inst, str) or not inst.strip() or "/" in inst or "|" in inst:
        raise _fault(str(inst), "name", f"a sub-assembly's name is text without a \"/\" or a \"|\", got {inst!r}")
    if not isinstance(decl, dict):
        raise _fault(inst, "declaration",
                     f"{inst!r} must be {{\"project\": ..., \"at\": [x, y, z], \"turn\": [rx, ry, rz]}}, "
                     f"got {type(decl).__name__}")
    unknown = sorted(str(k) for k in decl if k not in KEYS)
    if unknown:
        raise _fault(inst, "declaration", f"{inst!r} does not take {', '.join(unknown)} (keys: {', '.join(KEYS)})")
    project = decl.get("project")
    if not isinstance(project, str) or not st._is_name(project):
        raise _fault(inst, "declaration",
                     f"{inst!r} needs `project`, the name of a project next to this one, got {project!r}")
    return project, _vec(inst, "at", decl.get("at", (0, 0, 0))), _vec(inst, "turn", decl.get("turn", (0, 0, 0)))


# ─── Flattening ──────────────────────────────────────────────────────────────

def _lift_key(key, prefix: str):
    if isinstance(key, str):
        return "|".join(prefix + part for part in key.split("|"))
    return tuple(prefix + part for part in key)


def _lift(inst: str, project: str, at: tuple, turn: tuple, sub, depth: int) -> _Lifted:
    """The child's machine `sub`, in the parent's frame and under the prefix `inst/`."""
    from .bodies import BodyInfo
    prefix = inst + "/"
    m, loc = instance_matrix(at, turn), instance_location(at, turn)
    parts = {prefix + n: s.moved(loc) for n, s in sub.parts.items()}
    bodies = {}
    for n in sub.parts:
        info = sub.bodies.get(n)
        bodies[prefix + n] = (replace(info, name=prefix + n) if info is not None else
                              BodyInfo(name=prefix + n, kind="stock", project=project, geometry="envelope",
                                       source="assembly.py", notes=(f"{project} did not describe it",)))
    axes = {}
    for key, ax in sub.axes.items():
        axes[prefix + key] = replace(
            ax, name=prefix + ax.name, moves=tuple(prefix + b for b in ax.moves),
            direction=_turned(m, ax.direction), tool=(prefix + ax.tool if ax.tool else ax.tool),
            tool_point=_turned(m, ax.tool_point))
    poses = {prefix + p: {prefix + a: v for a, v in d.items()} for p, d in sub.poses.items()}
    nested = [p for c in sub.children.values() if isinstance(c, Child) for p in c.projects]
    child = Child(name=inst, project=project, at=at, turn=turn, depth=depth, bodies=tuple(parts), axes=tuple(axes),
                  projects=tuple(dict.fromkeys((project, *nested))), machine=sub)
    return _Lifted(child, parts, bodies,
                   {_lift_key(k, prefix): v for k, v in sub.clearance.items()},
                   {_lift_key(k, prefix) for k in sub.allow_contact}, axes, poses)


def _link(machine, inst, decl, path: tuple) -> _Lifted:
    project, at, turn = declaration(inst, decl)
    chain = " -> ".join(path + (project,))
    if project in path:
        raise _fault(inst, "cycle", f"{inst!r} links the project {project!r}, which is above it in the tree: {chain}")
    if len(path) > MAX_DEPTH:
        raise _fault(inst, "depth", f"{inst!r} would be level {len(path)} of sub-assemblies, "
                                    f"and the limit is {MAX_DEPTH}: {chain}")
    try:
        st.project_dir(project)
    except FileNotFoundError:
        have = ", ".join(p for p in st.list_projects() if p not in path) or "none"
        raise _fault(inst, "project", f"{inst!r} links the project {project!r}, which does not exist "
                                      f"(projects: {have})") from None
    token = _PATH.set(path)
    try:
        sub = st.load_machine(project, placed=True, describe=True)
    except SubassemblyError as e:
        raise SubassemblyError([replace(p, message=f"in {project!r}, linked as {inst!r}: {p.message}")
                                for p in e.problems]) from None
    except PlacementError as e:
        raise PlacementError(f"sub-assembly {inst!r} ({project}): {e}") from e
    except Exception as e:
        raise _fault(inst, "build", f"{inst!r} ({project}) did not build: {st.why(e)}") from e
    finally:
        _PATH.reset(token)
    if sub is None:
        raise _fault(inst, "project", f"{inst!r} links the project {project!r}, which has no assembly.py")
    nested = set(sub.children)
    stray = sorted(n for n in sub.parts if "/" in n and n.split("/", 1)[0] not in nested)
    if stray:
        raise SubassemblyError([Problem(f"{inst}/{n}", "name", f"in {project!r}: {name_rule(n)}") for n in stray])
    try:
        return _lift(inst, project, at, turn, sub, depth=len(path))
    except Exception as e:      # an axis or a body of the child that cannot be moved: its project's fault, said as a row
        raise _fault(inst, "build", f"{inst!r} ({project}) could not be flattened in: {st.why(e)}") from e


def expand(machine, declared):
    """The machine with every sub-assembly in `declared` flattened in (bodies.py: the hook state.load_machine calls).

    Raises SubassemblyError, with a Problem for every fault found, when a declaration cannot be used; the runner
    reports each as a FAIL row. The `machine` handed in is not changed.
    """
    path = _PATH.get() + (machine.slug,)
    if not isinstance(declared, dict):
        raise _fault(machine.slug, "declaration",
                     f"{NAME} must be {{name: {{\"project\": ..., \"at\": [..], \"turn\": [..]}}}}, "
                     f"got {type(declared).__name__}")
    problems = [Problem(n, "name", name_rule(n)) for n in machine.parts if "/" in n]
    parts, bodies = dict(machine.parts), dict(machine.bodies)
    clearance, allow = dict(machine.clearance), set(machine.allow_contact)
    axes, poses, children = dict(machine.axes), dict(machine.poses), {}
    for inst, decl in declared.items():
        try:
            lifted = _link(machine, inst, decl, path)
        except SubassemblyError as e:
            problems.extend(e.problems)
            continue
        if inst in machine.parts:
            problems.append(Problem(inst, "name", f"{inst!r} is the name of a body and of a sub-assembly"))
            continue
        children[inst] = lifted.child
        parts.update(lifted.parts)
        bodies.update(lifted.bodies)
        for key, mm in lifted.clearance.items():
            clearance.setdefault(key, mm)                   # the parent's own entry for a pair wins
        allow |= lifted.allow_contact
        axes.update(lifted.axes)
        for name, pose in lifted.poses.items():
            if name in poses:
                problems.append(Problem(name, "name", f"pose {name!r} is declared in POSES and by {inst!r}"))
            poses[name] = poses.get(name, pose)
    own = {k: v for k, v in machine.axes.items()}
    axes.update(_wholes(own, parts, children, problems))
    if problems:
        raise SubassemblyError(problems)
    return replace(machine, parts=parts, clearance=clearance, allow_contact=allow, axes=axes, poses=poses,
                   bodies=bodies, children=children)


def _wholes(own: dict, parts: dict, children: dict, problems: list) -> dict:
    """The parent's own axes with "gantry/*" in `moves` replaced by every body under that instance."""
    fixed = {}
    for key, axis in own.items():
        if not any(isinstance(m, str) and m.endswith(ALL_OF) for m in axis.moves):
            continue
        moves = []
        for m in axis.moves:
            if not (isinstance(m, str) and m.endswith(ALL_OF)):
                moves.append(m)
                continue
            inst = m[:-len(ALL_OF)]
            hit = [n for n in parts if n.startswith(inst + "/")] if inst in children else []
            if not hit:
                have = ", ".join(sorted(children)) or "none"
                problems.append(Problem(key, "moves", f"axis {key!r} moves {m!r}, but there is no sub-assembly "
                                                      f"{inst!r} with bodies (sub-assemblies: {have})"))
            moves.extend(hit)
        fixed[key] = replace(axis, moves=tuple(dict.fromkeys(moves)))
    return fixed


def tree_summary(machine) -> dict:
    """What checks.json says of the tree: each sub-assembly, and the projects whose gates the check ran."""
    return {"subassemblies": [c.as_dict() for c in machine.children.values() if isinstance(c, Child)],
            "projects": [p for p, _ in projects_of(machine)]}


def projects_of(machine) -> list:
    """[(project, its Assembly)] for every project below the machine, each once, depth first: the projects whose
    gates the machine's check runs after its own."""
    seen, out = set(), []

    def walk(m):
        for child in (getattr(m, "children", None) or {}).values():
            if not isinstance(child, Child):
                continue
            if child.project not in seen:
                seen.add(child.project)
                out.append((child.project, child.machine))
            if child.machine is not None:
                walk(child.machine)
    walk(machine)
    return out


# ─── Poses ───────────────────────────────────────────────────────────────────

def apply_pose(machine, name: str, parts: dict | None = None) -> dict:
    """The positioned solids with the machine at pose `name`: every axis the pose names driven to its position.

    `parts` are the solids to move (default: the machine's, at home). A pose that cannot be applied raises
    PoseError saying which part of it is wrong. Translations add, so an axis that moves bodies another axis moves
    too is as far along as both put it, whatever the order.
    """
    from .motion import pose as drive
    poses = getattr(machine, "poses", None) or {}
    if name not in poses:
        have = ", ".join(sorted(poses)) or "none declared"
        raise PoseError(f"no pose {name!r} in POSES (poses: {have})")
    axes = getattr(machine, "axes", None) or {}
    solids = dict(machine.parts if parts is None else parts)
    for axis_name, position in sorted(poses[name].items()):
        axis = axes.get(axis_name)
        if axis is None:
            have = ", ".join(sorted(axes)) or "none declared"
            raise PoseError(f"pose {name!r} drives {axis_name!r}, which is not an axis of AXES (axes: {have})")
        if not _number(position):
            raise PoseError(f"pose {name!r} puts {axis_name} at {position!r}, which is not a number of mm")
        lo, hi = axis.travel
        if not lo - TOL_MM <= position <= hi + TOL_MM:
            raise PoseError(f"pose {name!r} puts {axis_name} at {position:g} mm, outside its travel "
                            f"{lo:g} to {hi:g} mm")
        try:
            solids = drive(solids, axis, position)
        except KeyError as e:
            raise PoseError(f"pose {name!r}: {e.args[0] if e.args else e}") from None
    return solids


# ─── Finding the tree without running it ─────────────────────────────────────

def _entry_project(node) -> str | None:
    """The `project` of one SUBASSEMBLIES entry written as a dict literal or dict(...), if it is a plain string."""
    if isinstance(node, ast.Dict):
        pairs = [(k.value, v) for k, v in zip(node.keys, node.values)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        pairs = [(k.arg, k.value) for k in node.keywords if k.arg]
    else:
        return None
    for key, value in pairs:
        if key == "project" and isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def _declared(value) -> tuple[list, bool]:
    """The projects a SUBASSEMBLIES value names, and whether that is all it names."""
    if isinstance(value, ast.Dict):
        found, whole = [], True
        for key, entry in zip(value.keys, value.values):
            project = _entry_project(entry) if key is not None else None
            if project is None:
                whole = False
            else:
                found.append(project)
        return found, whole
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "dict" and not value.args:
        found = [_entry_project(k.value) for k in value.keywords if k.arg]
        return [p for p in found if p], all(p for p in found) and all(k.arg for k in value.keywords)
    return [], False


@lru_cache(maxsize=512)
def _scan(path: str, mtime_ns: int, size: int) -> tuple[tuple, bool]:
    try:
        tree = ast.parse(Path(path).read_bytes())
    except (OSError, SyntaxError, ValueError):
        return (), False                    # unreadable: not known to declare none
    names, whole = [], True
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets, value = [node.target], node.value
        elif isinstance(node, ast.ImportFrom):
            whole &= not any((a.asname or a.name) == NAME for a in node.names)
            continue
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name)
              and node.value.func.value.id == NAME):
            whole = False                   # SUBASSEMBLIES.update(...)
            continue
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == NAME:
                found, ok = _declared(value)
                names += found
                whole &= ok and not isinstance(node, ast.AugAssign)
            elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == NAME:
                project = _entry_project(value)
                names += [project] if project else []
                whole &= project is not None
    return tuple(dict.fromkeys(names)), whole


@lru_cache(maxsize=512)
def _scan_instances(path: str, mtime_ns: int, size: int) -> tuple:
    """((instance, project), ...) for every entry of a SUBASSEMBLIES dict literal whose key and project are strings."""
    try:
        tree = ast.parse(Path(path).read_bytes())
    except (OSError, SyntaxError, ValueError):
        return ()
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and any(isinstance(t, ast.Name) and t.id == NAME for t in node.targets):
            for key, entry in zip(node.value.keys, node.value.values):
                project = _entry_project(entry)
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and project:
                    found.append((key.value, project))
    return tuple(found)


def instance_project(pdir, instance: str) -> str | None:
    """The project a SUBASSEMBLIES instance is (the instance is only the name of its bodies' prefix: "gantry" may be the
    project "mini_gantry"), read from assembly.py's source with nothing run; None when it is not written as plain strings."""
    path = Path(pdir) / "assembly.py"
    try:
        stat = path.stat()
    except OSError:
        return None
    return dict(_scan_instances(str(path), stat.st_mtime_ns, stat.st_size)).get(instance)


def static_children(pdir) -> tuple[list, bool]:
    """The projects a project's assembly.py links, read from its source (nothing is run), and whether that list is
    all of them. False means the declaration is written in a way that only running it would settle (a name that
    is computed, an entry added later): verify then refuses to call the tree covered."""
    path = Path(pdir) / "assembly.py"
    try:
        stat = path.stat()
    except OSError:
        return [], True
    names, whole = _scan(str(path), stat.st_mtime_ns, stat.st_size)
    return list(names), whole


def tree_projects(pdir) -> tuple[list, bool]:
    """Every project below `pdir`'s (its sub-assemblies, theirs, ...), each once, found without running anything,
    and whether the list is whole. A repeat or a cycle is left to load_machine, which reports it."""
    pdir = Path(pdir)
    base, root = pdir.parent, pdir.name
    seen, out, whole = {root}, [], True

    def walk(name: str, depth: int) -> None:
        nonlocal whole
        names, ok = static_children(base / name)
        whole &= ok
        for child in names:
            if not st._is_name(child):
                whole = False
            elif child not in seen:
                seen.add(child)
                out.append(child)
                if depth <= MAX_DEPTH:
                    walk(child, depth + 1)
    walk(root, 1)
    return out, whole


def tree_dirs(pdir) -> list:
    """[(project, folder)] of the tree below `pdir`, by name: what verify hashes and asks git about."""
    base = Path(pdir).parent
    return [(name, base / name) for name in sorted(tree_projects(pdir)[0])]
