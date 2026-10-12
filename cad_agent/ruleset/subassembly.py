"""Rules for a machine made of sub-assemblies, and for the poses it can be put in (cad_agent/subassembly.py).

    subassembly  A PASS row for each sub-assembly, saying what was linked and where; and a FAIL row for a body
                 whose name has a "/" that no sub-assembly explains. A declaration that cannot be flattened in
                 never gets here: there is no machine to judge, so the runner reports each of its faults as a
                 `subassembly/<kind>` FAIL row (cycle, depth, name, project, build, declaration, moves)
    poses        Every pose in POSES: the axes it drives are declared, each position is inside the axis's travel,
                 and the bodies the axis moves exist. And every spec entry that names a pose is of a kind that
                 judges at one: [[clearance]], [[keepout]] and [[position]] do, and any other section that says
                 `pose` would be judged at home without a word, which is UNCHECKED

A project with no sub-assemblies and no POSES gets no row from either, so the verdicts of every design that
existed before are the ones they were.
"""
from __future__ import annotations

import math
import tomllib

from ..registry import TOL_MM, Row, register

POSE_KINDS = ("clearance", "keepout", "position")       # the sections that read `pose`


@register(scope="assembly", name="subassembly", order=12)
def subassembly(ctx):
    """Whether each sub-assembly is linked as declared, and no body name has a "/" that is not one's prefix."""
    from ..subassembly import MAX_DEPTH, Child, name_rule
    children = {k: c for k, c in (getattr(ctx.machine, "children", None) or {}).items() if isinstance(c, Child)}
    for name, c in children.items():
        under = f", with {', '.join(c.projects[1:])} under it" if len(c.projects) > 1 else ""
        yield Row(subject=name, rule="linked", state="PASS",
                  measured=(f"project {c.project} at ({c.at[0]:g}, {c.at[1]:g}, {c.at[2]:g}) mm, turned "
                            f"({c.turn[0]:g}, {c.turn[1]:g}, {c.turn[2]:g}) deg: {len(c.bodies)} bodies, "
                            f"{len(c.axes)} axes{under}"),
                  limit=f"a project next to this one that builds, no cycle, at most {MAX_DEPTH} levels",
                  source="SUBASSEMBLIES in assembly.py; the project's own gates follow as <project>:<check>/<rule>")
    for body in sorted(ctx.parts or {}):
        if "/" in body and body.split("/", 1)[0] not in children:
            yield Row(subject=body, rule="name", state="FAIL", measured=name_rule(body),
                      limit="no \"/\" in a body's name unless a sub-assembly of that name owns it",
                      source="cad_agent/subassembly.py: a \"/\" is how a sub-assembly's bodies are named")


@register(scope="assembly", name="poses", order=27)
def poses(ctx):
    """Whether every pose in POSES drives declared axes inside their travel, and no spec entry names a pose it ignores."""
    machine = ctx.machine
    for name, pose in sorted((getattr(machine, "poses", None) or {}).items()):
        faults = _faults(machine, ctx.parts or {}, name, pose)
        if faults:
            yield Row(subject=f"pose {name}", rule="pose", state="FAIL", measured="; ".join(faults),
                      limit="every axis declared in AXES, each position inside its travel",
                      source="POSES and AXES in assembly.py")
            continue
        driven = ", ".join(f"{axis} = {position:g} mm" for axis, position in sorted(pose.items())) or "no axis driven"
        yield Row(subject=f"pose {name}", rule="pose", state="PASS", measured=f"{driven}; inside travel",
                  limit="every axis declared in AXES, each position inside its travel",
                  source="POSES and AXES in assembly.py")
    yield from _ignored(ctx)


def _faults(machine, parts: dict, name: str, pose: dict) -> list:
    axes = getattr(machine, "axes", None) or {}
    out = []
    for axis_name, position in sorted(pose.items()):
        axis = axes.get(axis_name)
        if axis is None:
            have = ", ".join(sorted(axes)) or "none declared"
            out.append(f"{axis_name!r} is not an axis of AXES (axes: {have})")
            continue
        if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position):
            out.append(f"{axis_name} is at {position!r}, which is not a number of mm")
            continue
        lo, hi = axis.travel
        if not lo - TOL_MM <= position <= hi + TOL_MM:
            out.append(f"{axis_name} is at {position:g} mm, outside its travel {lo:g} to {hi:g} mm")
        missing = [b for b in axis.moves if b not in parts]
        if missing:
            out.append(f"{axis_name} moves {', '.join(missing)}, which the assembly does not return")
    return out


def _ignored(ctx):
    """A spec entry that names a pose in a section that does not read one."""
    from ..state import project_dir
    try:
        spec = tomllib.loads((project_dir(ctx.slug) / "spec.toml").read_text())
    except (OSError, ValueError):
        return                                  # the spec rule says so
    for kind, value in spec.items():
        if kind in POSE_KINDS:
            continue
        for i, entry in enumerate(value if isinstance(value, list) else [value], 1):
            if isinstance(entry, dict) and "pose" in entry:
                where = f"[[{kind}]] #{i}" if isinstance(value, list) else f"[{kind}]"
                yield Row(subject=where, rule="pose", state="UNCHECKED",
                          measured=(f"{where} names the pose {entry['pose']!r}, but a [{kind}] section is judged at "
                                    "home and ignores it"),
                          limit=f"`pose` on {', '.join(f'[[{k}]]' for k in POSE_KINDS)}",
                          source="spec.toml; only those sections judge a machine at a pose")
