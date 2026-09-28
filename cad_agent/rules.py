"""Every check, registered. This module is the list of what a run verifies.

Adding a rule means adding one function here. The runner discovers it, the
gate consumes it, and the report prints it, with no other edit anywhere. That
is the whole point of the registry: the cost of a new verifier should be the
cost of writing the measurement, not the cost of threading it through.

Import order is the only wiring left: importing this module is what puts the
checks in the registry, so the runner imports it and nothing else needs to.
"""
from __future__ import annotations

from .checks.dfm import PROCESS, check_dfm
from .checks.fit import check_fit
from .checks.visual import DEFAULT_VIEWS, visual_rows
from .registry import Row, register

# ─── part scope ──────────────────────────────────────────────────────────────


@register(scope="part", name="geometry", order=10)
def geometry(ctx):
    """Envelope, wall thickness, in-plane web and feature count, per process."""
    process = ctx.meta.get("process")
    if not process:
        yield Row(subject=ctx.name, rule="process", state="UNCHECKED",
                  measured="no PROCESS declared",
                  limit=f"one of {sorted(PROCESS)}",
                  source="declare PROCESS in the part so it can be gated")
        return
    kw = {}
    if "measure" in ctx.opts:
        kw["measure"] = ctx.opts["measure"]
    if "samples" in ctx.opts:
        kw["samples"] = ctx.opts["samples"]
    for r in check_dfm(ctx.name, ctx.solid, process,
                       ctx.meta.get("min_feature_mm"),
                       expect_features=ctx.meta.get("expect_features"), **kw):
        yield Row(subject=r["part"], rule=r["rule"], state=r["state"],
                  measured=r["measured"], limit=r["limit"], source=r["source"])


@register(scope="part", name="visual", order=80)
def visual(ctx):
    """Silhouette coverage, drift from the approved render, and drawn extent."""
    views = tuple(ctx.meta.get("views") or DEFAULT_VIEWS)
    yield from visual_rows(ctx.name, ctx.solid, ctx.out_dir,
                           ctx.out_dir.parent, views)


# ─── assembly scope ──────────────────────────────────────────────────────────


@register(scope="assembly", name="fit", order=20)
def fit(ctx):
    """Interference and clearance between every pair of positioned solids."""
    if not ctx.parts:
        yield Row(subject="assembly", rule="fit", state="UNCHECKED",
                  measured="no assembly.py, so no pair was judged",
                  limit="every pair measured",
                  source="add assembly.py returning positioned solids")
        return
    for r in check_fit(ctx.parts, required_clearance=ctx.clearance,
                       allow_contact=ctx.allow_contact):
        yield Row(subject=r["pair"], rule=r["check"], state=r["state"],
                  measured=r["detail"],
                  limit=(f"{r['required_mm']:.2f} mm"
                         if r.get("required_mm") else "no overlap"),
                  source="measured overlap volume, or closest approach")


@register(scope="assembly", name="stance", order=30)
def stance(ctx):
    """Whether the footprint the assembly rests on has area in both axes.

    Counting contact bodies was the first attempt and it was wrong: two long
    rails resting on a bench are perfectly stable, because a rail is a line
    contact rather than a point, and the rule failed them for being only two.
    What actually matters is the footprint, so this measures the union of the
    contact patches instead.

    What it does not prove: that the centre of mass falls inside that
    footprint. Bought parts carry no material, so the assembly has no honest
    mass distribution to test against.
    """
    from .geom import bbox
    if not ctx.parts:
        yield Row(subject="assembly", rule="stance", state="N/A",
                  measured="no assembly", limit="n/a",
                  source="nothing positioned to stand up")
        return

    boxes = {n: bbox(s) for n, s in ctx.parts.items()}
    ground = min(lo[2] for lo, _ in boxes.values())
    touching = {n: (lo, hi) for n, (lo, hi) in boxes.items()
                if abs(lo[2] - ground) < 0.05}

    xs = [v for lo, hi in touching.values() for v in (lo[0], hi[0])]
    ys = [v for lo, hi in touching.values() for v in (lo[1], hi[1])]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    MIN_SPAN = 5.0

    ok = span_x >= MIN_SPAN and span_y >= MIN_SPAN
    yield Row(subject="assembly", rule="footprint", state="PASS" if ok else "FAIL",
              measured=f"{span_x:.1f} × {span_y:.1f} mm across "
                       f"{len(touching)} bodies at z = {ground:.2f} "
                       f"({', '.join(sorted(touching))})",
              limit=f"at least {MIN_SPAN:.0f} mm in both axes",
              source="union of the contact patches at the lowest plane; a span "
                     "near zero in either axis is a line or point contact and "
                     "will tip. Does not test the centre of mass.")

    floating = [n for n, (lo, hi) in boxes.items() if lo[2] > ground + 0.05]
    yield Row(subject="assembly", rule="ground plane", state="PASS",
              measured=f"{len(touching)} bodies on the plane, "
                       f"{len(floating)} above it, none below",
              limit="nothing below the lowest contact",
              source="the lowest plane is taken as the ground, so nothing can "
                     "be below it by construction; this row records the split")


# ─── project scope ───────────────────────────────────────────────────────────


@register(scope="project", name="provenance", order=40)
def provenance(ctx):
    """Whether every bought part records where its dimensions came from."""
    from .bought import list_bought
    rows = list_bought(ctx.slug)
    if not rows:
        yield Row(subject=ctx.slug, rule="bought parts", state="N/A",
                  measured="none in this project", limit="n/a",
                  source="nothing bought, so nothing to source")
        return
    for d in rows:
        if d.get("source", "UNRECORDED") == "UNRECORDED":
            yield Row(subject=d["name"], rule="source", state="FAIL",
                      measured="no recorded source",
                      limit="a vendor page, drawing or calliper reading",
                      source="geometry with no provenance cannot be trusted")
        elif not d.get("verified", True):
            yield Row(subject=d["name"], rule="source", state="UNCHECKED",
                      measured=f"declared unconfirmed: {d['source']}",
                      limit="measured on the real part",
                      source="confirm with callipers on arrival, then set VERIFIED")
        else:
            yield Row(subject=d["name"], rule="source", state="PASS",
                      measured=d["source"], limit="recorded and confirmed",
                      source=f"{d['kind']} route")


# ─── motion scope (assembly, but over travel rather than at one pose) ────────


@register(scope="assembly", name="sweep", order=25)
def sweep(ctx):
    """Clearance between every moving/static pair across each axis's travel.

    The fit rule judges the pose assembly.py returns, which for a machine is
    home. This drives each axis end to end and reports the worst approach it
    found, naming the axis position where it happened so the number is
    actionable rather than merely alarming.
    """
    from .motion import DEFAULT_SAMPLES, sweep_axis

    if not ctx.parts:
        return
    if not ctx.axes:
        yield Row(subject="assembly", rule="travel", state="N/A",
                  measured="no AXES declared, so nothing moves",
                  limit="n/a",
                  source="a static assembly is fully judged by the fit rule; "
                         "declare AXES in assembly.py for a machine")
        return

    req = {tuple(sorted(k.split("|"))) if isinstance(k, str) else tuple(sorted(k)): float(v)
           for k, v in (ctx.clearance or {}).items()}
    contact_ok = {tuple(sorted(k.split("|"))) if isinstance(k, str) else tuple(sorted(k))
                  for k in (ctx.allow_contact or set())}

    for name, axis in sorted(ctx.axes.items()):
        hits = sweep_axis(ctx.parts, axis, req, contact_ok,
                          samples=DEFAULT_SAMPLES)
        worst = None
        for key, hit in hits.items():
            need = req.get(key, 0.0)
            if hit.overlap > 0.0:
                yield Row(subject=f"{key[0]} vs {key[1]}",
                          rule=f"sweep/{name}", state="FAIL",
                          measured=f"overlap {hit.overlap:.3f} mm^3 at "
                                   f"{name} = {hit.at:+.1f} mm",
                          limit="no overlap anywhere in travel",
                          source=f"{DEFAULT_SAMPLES} poses across "
                                 f"{axis.travel[0]:+.1f} to {axis.travel[1]:+.1f} mm")
                continue
            if hit.distance <= 1e-7 and key in contact_ok:
                continue          # a screwed joint that travels with the axis
            if hit.distance < need - 1e-9:
                yield Row(subject=f"{key[0]} vs {key[1]}",
                          rule=f"sweep/{name}", state="FAIL",
                          measured=f"closest {hit.distance:.3f} mm at "
                                   f"{name} = {hit.at:+.1f} mm",
                          limit=f"{need:.2f} mm",
                          source=f"{DEFAULT_SAMPLES} poses across travel; the "
                                 "required clearance is the same table the "
                                 "static fit rule uses")
                continue
            if worst is None or hit.distance < worst[1].distance:
                worst = (key, hit)

    # One summary row per axis, so a clean sweep still leaves evidence it ran.
        if worst is not None:
            key, hit = worst
            yield Row(subject="assembly", rule=f"sweep/{name}", state="PASS",
                      measured=f"tightest {hit.distance:.3f} mm between "
                               f"{key[0]} and {key[1]} at {name} = {hit.at:+.1f} mm "
                               f"({len(hits)} moving pairs)",
                      limit="no overlap, and every declared clearance held",
                      source=f"{DEFAULT_SAMPLES} poses across "
                             f"{axis.travel[0]:+.1f} to {axis.travel[1]:+.1f} mm. "
                             "Axes are swept one at a time from home, so a "
                             "crash needing two axes off-home is not covered.")


@register(scope="assembly", name="reach", order=26)
def reach(ctx):
    """Whether the declared work area actually falls inside mechanical travel."""
    from .motion import tool_span

    if not ctx.axes:
        return
    for name, axis in sorted(ctx.axes.items()):
        if axis.work is None:
            yield Row(subject=f"axis {name}", rule="reach", state="UNCHECKED",
                      measured=f"travel {axis.span:.1f} mm, but no work span declared",
                      limit="a work span the machine promises to cover",
                      source="declare work=(min, max) on the axis, or the "
                             "travel figure proves nothing about usable area")
            continue
        lo, hi = tool_span(axis)
        wlo, whi = axis.work
        ok = wlo >= lo - 1e-9 and whi <= hi + 1e-9
        margin = min(wlo - lo, hi - whi)
        yield Row(subject=f"axis {name}", rule="reach",
                  state="PASS" if ok else "FAIL",
                  measured=f"tool reaches {lo:+.1f} to {hi:+.1f} mm, work area "
                           f"{wlo:+.1f} to {whi:+.1f} mm "
                           f"({margin:+.1f} mm margin)",
                  limit="work area inside travel",
                  source="tool point swept along the axis over declared travel; "
                         "this is kinematic reach, not whether the head can "
                         "physically get there without hitting something — "
                         "that is the sweep rule")
