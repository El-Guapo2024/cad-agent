# PlaneGCS, FreeCAD's sketch solver, for the app

`freecad/Sketcher/App/planegcs/` is FreeCAD's solver copied unchanged from FreeCAD at 3160daf1e2b6
(`src/Mod/Sketcher/App/planegcs`, LGPL-2.1-or-later, (c) 2011 Konstantinos Poulios and FreeCAD's
contributors), with `freecad/Sketcher/SketcherGlobal.h`. `shim/` stands in for the few FreeCAD headers it
includes (FCGlobal.h, FCConfig.h, Base/Console.h, Base/Tools.h, the Boost graph wrapper): logging is
dropped and nothing else changes. `shim/deferred_async.h` is force-included into GCS.cpp in the wasm
build only: without pthreads std::async never returns, so its one use runs deferred.

`sketch.cpp`/`sketch.h` port the Sketcher's `Sketch.cpp` (the mapping of sketch geometry and constraints
onto `GCS::System`: setUpSketch, the DogLeg/LM/BFGS/SQP solve sequence, the diagnosis, initMove and
moveGeometries) and the parts of `SketchObject*.cpp` that drive it (solve(), moveGeometries(), the
temporary moves the view provider drags with, AutoLockTangencyAndPerpty, setOrientation, the Block
state). Part's OpenCascade curves are replaced by a small `Geometry` that keeps OpenCascade's numbers
(a line is a point, a unit direction and a trim range; an arc's range is normalised as
Geom_TrimmedCurve::SetTrim does; a negative radius or a zero-length line is an invalid solution).
Scope: Point, LineSegment, Circle, ArcOfCircle, Ellipse, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola
and BSplineCurve (clamped or periodic, rational or not; construction or not) and the axes; Coincident,
Horizontal, Vertical, Parallel, Perpendicular, Tangent (with a B-spline knot's), Distance, DistanceX,
DistanceY, Radius, Diameter, Weight, Angle, Equal, PointOnObject (on a B-spline too), Symmetric,
SnellsLaw, InternalAlignment (every alignment type: a conic's axes and foci, a B-spline's pole circles
and knot points), Block, reference constraints. For the conics `Geometry` keeps OpenCascade's gp_Ax2
(the X and Y directions come from cross products with the normal, as gp_Ax2::SetXDirection makes
them), ElCLib's values and Geom_TrimmedCurve's trims, including the reversal a hyperbola or a parabola
gets when its range comes out backwards; for a B-spline, Geom_BSplineCurve's poles and weights (the
weights fall back to 1 when they all become equal, as OpenCascade's rational flag does, and
GeomBSplineCurve::setPoles' workaround is kept), StartPoint/EndPoint, and GeomCurve::closestParameter
(the nearest orthogonal projection, else the nearer end, as GeomAPI_ProjectPointOnCurve and FreeCAD's
fallback give it). `api.cpp` is a flat C API over it that takes and returns JSON (its header has the
format); `cad_agent/planegcs.py` loads the native build with ctypes, `ui/src/planegcs.ts` the
WebAssembly one.

Build (`build.sh native`, `build.sh wasm`, `build.sh all`): it needs Eigen 5.0.0 (EIGEN_DIR), Boost's
headers (BOOST_DIR, or libboost-dev) and, for wasm, emsdk (EMSDK; 4.0.10 built `dist/`), or
PLANEGCS_TOOLCHAIN holding all three. The native library goes to `build/` (not committed); `dist/` is
committed. The wasm build is -O2 with wasm SIMD (Eigen's SSE kernels through Emscripten's SSE
headers), ES module, no pthreads: planegcs.wasm is about 680 KB.

Checked against FreeCAD: `tests/golden/sketcher/make.py` runs 971 sketches of lines, circles, arcs and
points (freecad.json) and, with `--set=conics`, 522 of conics and B-splines (freecad_conics.json; their
internal geometry is what FreeCAD's exposeInternalGeometry adds, read back from freecadcmd) through
freecadcmd, and tests/test_planegcs.py holds both builds to its answers. Two things matter for agreeing
to the bit:

- PlaneGCS orders a subsystem's unknowns by their addresses, and FreeCAD allocates each parameter with
  `new`, so FreeCAD's answer for an under-constrained sketch depends on its heap (two runs of the same
  script disagree on about 30 % of the cases). The port takes its parameters from one block in the
  order they are made; make.py runs FreeCAD on a malloc that never reuses memory, which gives FreeCAD
  that same order.
- FreeCAD 26.3 is built with Eigen 5.0.0. With it the native build agrees with FreeCAD bit for bit on
  every case of freecad.json and on 514 of the 522 of freecad_conics.json (519 to 1e-9; the other 3 are
  rounding-sensitive in FreeCAD itself); with Eigen 3.4.0 about 200 differ in the last bits and 50
  beyond 1e-9. A B-spline's points are GCS's de Boor evaluation here and OpenCascade's in FreeCAD, and
  a projection onto it is found by another method, which accounts for the last bits of the 8.

The wasm build differs from FreeCAD only where FreeCAD's own answer is sensitive to rounding (make.py
marks the cases whose answer moves beyond 1e-9 when the input moves by one ulp): its sin, cos and
atan2 are musl's, not glibc's (which on an FMA machine are the FMA variants), and a last-bit difference
there moves those answers. Elsewhere it agrees to 1e-9, mostly to the bit, but for 7 of the 522 conic
sketches: under-constrained ones (DoF 2 to 17), where the solver stops at another point of the free
motion than FreeCAD's because the conics' arithmetic calls sin, cos, sinh and cosh at every step; their
status, DoF and constraint lists are FreeCAD's. The test allows that for at most 2 % of that set.
