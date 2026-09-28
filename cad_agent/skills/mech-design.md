# Mechanical design — the contract

**One invocation, one autonomous run, one report.** A brief is not the opening
move in a conversation. Infer the rest from engineering norms, write the
assumptions down, and run.

## Do not interview

Ask only when proceeding would be unsafe or useless. Everything else has a
defensible default:

| Unknown | Default |
|---|---|
| Process | FDM for brackets, CNC for anything hot or load-bearing, laser cut for panels |
| Material | PETG printed, 6061 aluminium machined, 3 mm acrylic panels |
| Fastener | M3 unless load says otherwise |
| Clearance | 0.2 mm sliding, 0.0 mm bolted joints, 20 mm around anything over 100 °C |
| Quantity | 1 |

## The boundary

**The agent specifies. The kernel computes. The human fabricates.**

Your output is parametric Python and a spec. You never state a dimension a
tool could measure, and you never draw a diagram: the render is generated
from the same geometry the gates judged, so it cannot disagree with the
design. A picture you draw alongside it is a second account that nothing
checks.

## Two rules that carry the run

1. **No bought part modelled from memory.** A vendor STEP goes in
   `bought/`. If there is no STEP, measure the part or read the drawing, and
   write the source in the part's docstring. A remembered bolt circle is how
   an assembly passes every check and still does not fit.
2. **`check_all` is ground truth.** Quote its literal output. Never reason
   about whether a part fits.

Memory is for judgement, not for facts that drift: which process suits a
part, that a printed bracket creeps near a hot plate, that a 0.4 mm nozzle
cannot make a 0.3 mm wall. Not for dimensions, prices, or what a vendor
stocks.

## The loop

```
part_build(slug, name, overrides={...})   # measure, do not eyeball
part_render(slug, name, view="iso")       # look at it
check_all(slug)                           # gate everything, write checks.json
done_check(slug)                           # ok:false on any FAIL or UNCHECKED
```

Sweep a dimension with `overrides` rather than editing the file, then commit
the value you settled on into `PARAMS`.

## Writing a part module

`projects/<slug>/parts/<name>.py` exposes:

- a docstring whose first line says what the part is and whose body says why
  it is shaped that way, and where any bought-part dimension came from
- `PARAMS` — every dimension, named, no literals buried in `build`
- `MATERIAL`, `PROCESS`, `MIN_FEATURE_MM` — the gates need all three; leaving
  one out makes the run UNCHECKED, which fails `done_check`
- `build(**params)` returning one solid
- optional `CUTLIST` for stock the part consumes

Call `reference_tables()` for hole sizes and extrusion profiles instead of
recalling a drill diameter.

## Writing the assembly

`projects/<slug>/assembly.py` exposes `parts()` returning positioned solids,
`CLEARANCE` for required gaps, and `ALLOW_CONTACT` for joints meant to touch.
Contact is never allowed implicitly: a pair that touches without being listed
fails, because that is usually a collision rather than a joint.

## Finish on the gates

`done_check` fails on FAIL and on UNCHECKED both. An unmeasured wall is not a
thin wall, but it is not a pass either. Fix what it names, or say in the
report that the gap is unclosed and why.

## The report

Publish the artifact, then summarise under it. The page carries: the headline
numbers, a part table with measured mass and envelope, the full fit matrix
with measured and required values, the DFM rows with their limit sources,
every render, the assumptions you made because you did not ask, and what a
human still does. Every number comes from `checks.json`. A hand-typed figure
is a second account of the design that nothing reconciles.
