// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/SketchObjectOperations.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectGeometry.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/CommandSketcherBSpline.cpp: 2017 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerBSpline.h: 2022 Abdullah Tahiri
// SketchObject's B-spline operations on a sketch, as the B-spline tools call them from Python: convertToNURBS,
// increaseBSplineDegree, decreaseBSplineDegree, modifyBSplineKnotMultiplicity, insertBSplineKnot, join, and the
// exposeInternalGeometry each tool calls after; the B-spline by knots (interpolation) as DrawSketchHandlerBSpline's
// executeCommands builds it. The new curves' numbers are OCCT's, through the sketch kernel (sketchkernel.ts); the
// rest (which constraints and internal geometry follow, which go) is FreeCAD's code here.
import type { Geo, XY } from './solver'
import { type Constraint, type PointPos, NONE, START, END, MID, GEO_UNDEF, constraint, alignmentConstraint } from './sketch'
import * as CV from './sketchcurves'
import * as OPS from './sketchops'
import type { Kernel } from './sketchkernel'

export type Doc = OPS.Doc
type BSpline = CV.BSpline

/** The geometry as the kernel takes it: the curve alone (no construction flag, no cached end points). */
export function plain(g: Geo): Geo {
  const { construction: _c, start_point: _s, end_point: _e, ...rest } = g as Geo & { construction?: boolean; start_point?: XY; end_point?: XY }
  void _c; void _s; void _e
  return rest as Geo
}
const withConstruction = (g: Geo, c: boolean): Geo => (c ? { ...plain(g), construction: true } : plain(g))
const isBSpline = (g: Geo | undefined): g is BSpline => g?.type === 'BSplineCurve'
/** SketchObject::getHighestCurveIndex. */
const highest = (d: Doc) => d.geometry.length - 1

// ── exposeInternalGeometry (SketchObjectGeometry.cpp) ───────────────────────────────────────────────────────────
/** SketchObject::exposeInternalGeometry(GeoId) on a sketch: the internal geometry the constraints do not already give
 *  the conic or B-spline, as construction geometry, then its InternalAlignment (a B-spline's Weight and Equal too)
 *  constraints. The number of elements added, -1 for a curve that has none. */
export function exposeInternalGeometry(d: Doc, geoId: number): number {
  const refs: CV.AlignmentRef[] = d.constraints.filter((c) => c.type === 'InternalAlignment' && c.alignment)
    .map((c) => ({ first: c.first, second: c.second, alignment: c.alignment!, index: c.alignmentIndex ?? -1 }))
  const weighted = (circle: number) => d.constraints.some((c) => c.type === 'Weight' && c.first === circle)
  const ex = CV.exposeInternalGeometry(d.geometry, refs, geoId, weighted)
  if (!ex) return -1
  d.geometry = [...d.geometry, ...ex.geometry]
  const list: Constraint[] = ex.order.map((k) => {
    if (k >= 0) { const a = ex.alignments[k]; return alignmentConstraint(a.alignment, a.first, a.firstPos, a.second, a.index) }
    const o = ex.others[-1 - k]
    return o.type === 'Weight' ? constraint('Weight', o.first, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, o.value ?? 1) : constraint('Equal', o.first, NONE, o.second!)
  })
  d.constraints = [...d.constraints, ...list]
  return ex.geometry.length
}

/** SketchObject::replaceGeometries(oldGeoIds, newGeos): the new curves in place of the old ones, the extra new ones at
 *  the end, the extra old ones deleted (with their internal geometry). */
export function replaceGeometries(d: Doc, oldIds: number[], newGeos: Geo[]) {
  d.geometry = [...d.geometry]
  let i = 0
  for (; i < oldIds.length && i < newGeos.length; i++) d.geometry[oldIds[i]] = newGeos[i]
  for (let j = i; j < newGeos.length; j++) d.geometry.push(newGeos[j])
  if (i < oldIds.length) OPS.delGeometries(d, oldIds.slice(i))
}

// ── convertToNURBS ───────────────────────────────────────────────────────────────────────────────────────────────
/** SketchObject::convertToNURBS(GeoId): the curve replaced by its B-spline (a new geometry: not construction), its
 *  constraints other than coincidences gone, and the coincidences on its centre. */
export function convertToNURBS(d: Doc, geoId: number, k: Kernel): boolean {
  if (geoId > highest(d) || geoId < 0) return false
  const geo = d.geometry[geoId]
  if (!geo || geo.type === 'Point') return false
  const bsp = k({ op: 'nurbs', geo: plain(geo) }).geo!
  d.geometry = [...d.geometry]
  d.geometry[geoId] = bsp
  d.constraints = d.constraints.filter((c) => !((c.type !== 'Coincident' && OPS.involvesGeoId(c, geoId))
    || (c.type === 'Coincident' && OPS.involvesGeoIdAndPosId(c, geoId, MID))))
  return true
}

// ── degree ──────────────────────────────────────────────────────────────────────────────────────────────────────
/** SketchObject::increaseBSplineDegree(GeoId, degreeincrement). */
export function increaseBSplineDegree(d: Doc, geoId: number, k: Kernel, increment = 1): boolean {
  if (geoId < 0 || geoId > highest(d)) return false
  const geo = d.geometry[geoId]
  if (!isBSpline(geo)) return false
  const a = k({ op: 'degree', geo: plain(geo), degree: geo.degree + increment })
  d.geometry = [...d.geometry]
  d.geometry[geoId] = a.geo!
  return true
}
/** SketchObject::decreaseBSplineDegree(GeoId, degreedecrement): the B-spline approximated at the lower degree (OCCT's
 *  Approx_Curve3d), the old one deleted with its internal geometry and the new one added at the end with its own. The
 *  new curve's GeoId, or -1. */
export function decreaseBSplineDegree(d: Doc, geoId: number, k: Kernel, decrement = 1): number {
  if (geoId < 0 || geoId > highest(d)) return -1
  const geo = d.geometry[geoId]
  if (!isBSpline(geo)) return -1
  const max = geo.degree - decrement
  if (max === 0) return -1
  const a = k({ op: 'approximate', geo: plain(geo), degree: max })
  OPS.delGeometry(d, geoId, true)
  d.geometry = [...d.geometry, a.geo!]
  const newId = d.geometry.length - 1
  exposeInternalGeometry(d, newId)
  return newId
}

// ── knots ───────────────────────────────────────────────────────────────────────────────────────────────────────
/** What FreeCAD throws (Base::ValueError, TypeError, CADKernelError): the message the command reports. */
export class SketchError extends Error {}
const sameXY = (a: XY, b: XY) => Math.abs(a[0] - b[0]) <= Number.EPSILON && Math.abs(a[1] - b[1]) <= Number.EPSILON
/** The pole and knot constraints of the B-spline geoId moved to the new B-spline's indices (std::ranges::find of the
 *  old pole, Base::Vector3d's ==, and of the old knot, exact), the internal geometry of the ones it no longer has
 *  deleted; the B-spline's GeoId after it. */
function reindexInternal(d: Doc, geoId: number, old: BSpline, neu: BSpline): number {
  const poleIn = old.poles.map((p) => { const i = neu.poles.findIndex((q) => sameXY(p, q)); return i })
  const knotIn = old.knots.map((u) => neu.knots.indexOf(u))
  const del: number[] = []
  const cons: Constraint[] = []
  for (const c of d.constraints) {
    if (!(c.type === 'InternalAlignment' && c.second === geoId)) { cons.push(c); continue }
    const map = c.alignment === 'BSplineControlPoint' ? poleIn : c.alignment === 'BSplineKnotPoint' ? knotIn : null
    if (!map) { cons.push(c); continue }
    const index = map[c.alignmentIndex ?? -1] ?? -1
    if (index === -1) { del.push(c.first); continue }
    cons.push({ ...c, alignmentIndex: index })
  }
  d.geometry = [...d.geometry]
  d.geometry[geoId] = withConstruction(neu, !!old.construction) // a clone of the old one: its extensions stay
  d.constraints = cons
  if (del.length) OPS.delGeometriesExclusive(d, del)
  // the B-spline's GeoId after the deletion (the command finds it again by its tag)
  return geoId - [...new Set(del)].filter((g) => g < geoId).length
}
/** SketchObject::modifyBSplineKnotMultiplicity(GeoId, knotIndex (OCC's, from 1), multiplicityincr); throws
 *  SketchError with FreeCAD's message. The B-spline's GeoId after it. */
export function modifyBSplineKnotMultiplicity(d: Doc, geoId: number, knotIndex: number, incr: number, k: Kernel): number {
  if (geoId < 0 || geoId > highest(d)) throw new SketchError('B-spline Geometry Index (GeoID) is out of bounds.')
  if (incr === 0) throw new SketchError('You are requesting no change in knot multiplicity.')
  const geo = d.geometry[geoId]
  if (!isBSpline(geo)) throw new SketchError('The Geometry Index (GeoId) provided is not a B-spline.')
  if (knotIndex > geo.knots.length || knotIndex < 1) {
    throw new SketchError('The knot index is out of bounds. Note that in accordance with OCC notation, the first knot has index 1 and not zero.')
  }
  const cur = geo.mults[knotIndex - 1]
  if (cur + incr > geo.degree) throw new SketchError('The multiplicity cannot be increased beyond the degree of the B-spline.')
  if (cur + incr < 0) throw new SketchError('The multiplicity cannot be decreased beyond zero.')
  const a = k({ op: 'multiplicity', geo: plain(geo), index: knotIndex, mult: cur + incr })
  return reindexInternal(d, geoId, geo, a.geo as BSpline)
}
/** SketchObject::insertBSplineKnot(GeoId, param, multiplicity); throws SketchError. The B-spline's GeoId after it. */
export function insertBSplineKnot(d: Doc, geoId: number, param: number, mult: number, k: Kernel): number {
  if (geoId < 0 || geoId > highest(d)) throw new SketchError('B-spline Geometry Index (GeoID) is out of bounds.')
  if (mult === 0) throw new SketchError('Knot cannot have zero multiplicity.')
  const geo = d.geometry[geoId]
  if (!isBSpline(geo)) throw new SketchError('The Geometry Index (GeoId) provided is not a B-spline.')
  const [first, last] = CV.bsplineRange(geo)
  if (mult > geo.degree) throw new SketchError('Knot multiplicity cannot be higher than the degree of the B-spline.')
  if (param > last || param < first) throw new SketchError('Knot cannot be inserted outside the B-spline parameter range.')
  const a = k({ op: 'insert_knot', geo: plain(geo), u: param, mult })
  return reindexInternal(d, geoId, geo, a.geo as BSpline)
}

// ── join ────────────────────────────────────────────────────────────────────────────────────────────────────────
/** SketchObject::join(geoId1, posId1, geoId2, posId2, continuity): the two curves made one B-spline in geoId1's place;
 *  throws SketchError with FreeCAD's message. */
export function join(d: Doc, g1: number, p1: PointPos, g2: number, p2: PointPos, continuity: number, k: Kernel): boolean {
  if (p1 !== START && p1 !== END && p2 !== START && p2 !== END) throw new SketchError('Invalid positions: points must be start or end points of a curve.')
  if (g1 === g2) throw new SketchError('Connecting the end points of the same curve is not yet supported.')
  if (g1 < 0 || g1 > highest(d) || g2 < 0 || g2 > highest(d)) return false
  const geo1 = d.geometry[g1], geo2 = d.geometry[g2]
  if (geo1.type === 'Point' || geo2.type === 'Point') return false
  const c1 = !!geo1.construction, c2 = !!geo2.construction
  if (c1 !== c2) throw new SketchError('Cannot join construction and non-construction geometries.')
  const a = k({ op: 'join', geo1: plain(geo1), pos1: p1, geo2: plain(geo2), pos2: p2, continuity })
  replaceGeometries(d, [g1, g2], [a.geo!])
  exposeInternalGeometry(d, g1)
  d.geometry[g1] = withConstruction(d.geometry[g1], c1)
  const other1: PointPos = p1 === START ? END : START, other2: PointPos = p2 === START ? END : START
  OPS.transferConstraints(d, g1, other1, g1, START, true)
  OPS.transferConstraints(d, g2, other2, g1, END, true)
  return true
}

// ── B-spline by knots (DrawSketchHandlerBSpline's executeCommands, Knots method) ────────────────────────────────
/** The knot points of the tool: Part.Point construction geometry, one per click (the handler's addGeometry). */
export function knotPoint(p: XY): Geo { return { type: 'Point', at: [Number(p[0].toFixed(6)), Number(p[1].toFixed(6))], construction: true } }
/** C++'s default stream output of a double (6 significant digits), as the handler writes App.Vector(x, y). */
const g6 = (v: number) => Number(v.toPrecision(6))
/** The B-spline the handler makes through points (the knot points at firstPointId...): the curve interpolated in pieces
 *  between C0 knots (multiplicity >= 3), raised to degree 3, added after the points; the ends' autoconstraints moved to
 *  the curve's ends, each point tied to the curve (InternalAlignment BSplineKnotPoint, or PointOnObject between two
 *  C0 knots), the knot multiplicities asked for set, then exposeInternalGeometry. The new curve's GeoId. */
export function bsplineByKnots(d: Doc, firstPointId: number, points: XY[], multiplicities: number[], periodic: boolean, construction: boolean, k: Kernel): number {
  const degree = 3
  const mults = [...multiplicities]
  if (!periodic) { mults[0] = degree + 1; mults[mults.length - 1] = degree + 1 }
  const pts = points.map((p): XY => [g6(p[0]), g6(p[1])])
  const pieces: XY[][] = [[pts[0]]]
  for (let i = 1; i < pts.length - 1; i++) {
    pieces[pieces.length - 1].push(pts[i])
    if (mults[i] >= degree) pieces.push([pts[i]])
  }
  pieces[pieces.length - 1].push(pts[pts.length - 1])
  const between = pts.map((_, i) => i > 0 && i < pts.length - 1 && mults[i - 1] >= degree && mults[i + 1] >= degree)
  let poles: XY[] = [], knots: number[] = [], ms: number[] = []
  pieces.forEach((piece, n) => {
    const b = k({ op: 'interpolate', points: piece, periodic, degree }).geo as BSpline
    if (n === 0) { poles = [...b.poles]; knots = [...b.knots]; ms = [...b.mults] }
    else {
      poles.push(...b.poles.slice(1))
      const last = knots[knots.length - 1]
      knots.push(...b.knots.slice(1).map((u) => last + u))
      ms[ms.length - 1] = 3
      ms.push(...b.mults.slice(1))
    }
  })
  // Part.BSplineCurve(poles, mults, knots, periodic, degree, None, False): weights all 1
  const bsp: Geo = { type: 'BSplineCurve', poles, weights: poles.map(() => 1), knots, mults: ms, degree, periodic, ...(construction ? { construction: true } : {}) }
  d.geometry = [...d.geometry, bsp]
  let id = d.geometry.length - 1
  if (!periodic) {
    const ids = points.map((_, i) => firstPointId + i)
    d.constraints = d.constraints.map((c) => {
      if (c.first === ids[0] && c.firstPos === START) return { ...c, first: id, firstPos: START }
      if (c.first === ids[ids.length - 1] && c.firstPos === START) return { ...c, first: id, firstPos: END }
      return c
    })
  }
  const list: Constraint[] = []
  let knot = 0
  for (let i = 0; i < points.length; i++) {
    if (between[i]) { list.push(constraint('PointOnObject', firstPointId + i, START, id)); continue }
    list.push(alignmentConstraint('BSplineKnotPoint', firstPointId + i, START, id, knot))
    if (mults[i] > 1 && mults[i] < degree) id = modifyBSplineKnotMultiplicity(d, id, knot + 1, mults[i] - 1, k)
    knot++
  }
  d.constraints = [...d.constraints, ...list]
  exposeInternalGeometry(d, id)
  return id
}

// ── which knot a selected point is (CommandSketcherBSpline.cpp) ─────────────────────────────────────────────────
/** findBSplineAndKnotIndex: the B-spline and the OCC index (from 1) of the knot at (GeoId, PosId): a knot point's
 *  alignment, or a B-spline's start (1) or end (the last knot). */
export function findBSplineAndKnotIndex(d: Doc, geoId: number, pos: PointPos): { spline: number; knot: number } | null {
  for (const c of d.constraints) {
    if (c.type === 'InternalAlignment' && c.first === geoId && c.alignment === 'BSplineKnotPoint') return { spline: c.second, knot: (c.alignmentIndex ?? -1) + 1 }
  }
  const g = d.geometry[geoId]
  if (isBSpline(g)) {
    if (pos === START) return { spline: geoId, knot: 1 }
    if (pos === END) return { spline: geoId, knot: g.knots.length }
  }
  return null
}
/** isBsplineKnotOrEndPoint (Utils.cpp): a knot point, or a B-spline's start or end. */
export function isBsplineKnotOrEndPoint(d: Doc, geoId: number, pos: PointPos): boolean {
  const g = d.geometry[geoId]
  // isBsplineKnot: the geometry's internal type (its InternalAlignment)
  if (d.constraints.some((c) => c.type === 'InternalAlignment' && c.first === geoId && c.alignment === 'BSplineKnotPoint')) return true
  return isBSpline(g) && (pos === START || pos === END)
}
