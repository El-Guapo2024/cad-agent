// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/SketchObjectExternal.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/DrawSketchHandlerCarbonCopy.h: 2022 Abdullah Tahiri
//   src/Mod/Part/App/Geometry.cpp: 2008 Werner Mayer
// Sketcher_CarbonCopy: another sketch of the Body copied into the one in edit, as SketchObject::carbonCopy does it: its
// geometry (construction in construction mode), its constraints with their GeoIds moved past this sketch's, its external
// references added to this sketch's (projected again onto it), and, when the other sketch's X or Y axis runs the other
// way (isCarbonCopyAllowed's xinv, yinv), the geometry mirrored and the constraints that measure a direction corrected.
// The tool is sketchcarbontool.ts.
import type { Geo, XY } from './solver'
import { type Constraint, GEO_UNDEF } from './sketch'
import type * as OPS from './sketchops'

const CONFUSION = 1e-7
type V3 = [number, number, number]
export type Placement = { base: V3; rotation: [number, number, number, number] }
const dot3 = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const sub3 = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
/** Base::Rotation::multVec (the quaternion x, y, z, w). */
export function multVec(q: Placement['rotation'], v: V3): V3 {
  const [x, y, z, w] = q
  const x2 = x * x, y2 = y * y, z2 = z * z, w2 = w * w
  const dx = (x2 + w2 - y2 - z2) * v[0] + 2 * (x * y - z * w) * v[1] + 2 * (x * z + y * w) * v[2]
  const dy = 2 * (x * y + z * w) * v[0] + (w2 - x2 + y2 - z2) * v[1] + 2 * (y * z - x * w) * v[2]
  const dz = 2 * (x * z - y * w) * v[0] + 2 * (x * w + y * z) * v[1] + (w2 - x2 - y2 + z2) * v[2]
  return [dx, dy, dz]
}
const normalize3 = (v: V3): V3 => { const l = Math.hypot(...v); return l ? [v[0] / l, v[1] / l, v[2] / l] : v }

export type Reason = 'rlNonParallel' | 'rlAxesMisaligned' | 'rlOriginsMisaligned'
/** isCarbonCopyAllowed's placement checks (the sketch of the source, `src`, onto this one): the planes parallel, the
 *  axes aligned, the origins on one normal; xinv / yinv when the X / Y axes run opposite. */
export function carbonCopyAllowed(self: Placement, src: Placement, allowUnaligned = false): { xinv: boolean; yinv: boolean } | { reason: Reason } {
  const sn = multVec(src.rotation, [0, 0, 1]), sx = multVec(src.rotation, [1, 0, 0]), sy = multVec(src.rotation, [0, 1, 0])
  const ln = multVec(self.rotation, [0, 0, 1]), lx = multVec(self.rotation, [1, 0, 0]), ly = multVec(self.rotation, [0, 1, 0])
  const d = dot3(sn, ln), dx = dot3(sx, lx), dy = dot3(sy, ly)
  if (!allowUnaligned && Math.abs(Math.abs(d) - 1) > CONFUSION) return { reason: 'rlNonParallel' }
  if (!allowUnaligned && (Math.abs(Math.abs(dx) - 1) > CONFUSION || Math.abs(Math.abs(dy) - 1) > CONFUSION)) return { reason: 'rlAxesMisaligned' }
  const same = src.base[0] === self.base[0] && src.base[1] === self.base[1] && src.base[2] === self.base[2]
  const ddir = normalize3(sub3(src.base, self.base))
  if (!allowUnaligned && Math.abs(Math.abs(dot3(ddir, ln)) - 1) > CONFUSION && !same) return { reason: 'rlOriginsMisaligned' }
  return { xinv: allowUnaligned ? false : Math.abs(dx - 1) > CONFUSION, yinv: allowUnaligned ? false : Math.abs(dy - 1) > CONFUSION }
}
export const REASONS: Record<string, string> = {
  rlCircularReference: 'Carbon copy would cause a circular dependency.',
  rlOtherDoc: 'This object is in another document.',
  rlOtherBody: 'This object belongs to another body. Hold Ctrl to allow cross-references.',
  rlOtherBodyWithLinks: 'This object belongs to another body and it contains external geometry. Cross-reference not allowed.',
  rlOtherPart: 'This object belongs to another part.',
  rlNonParallel: 'The selected sketch is not parallel to this sketch. Hold Ctrl+Alt to allow non-parallel sketches.',
  rlAxesMisaligned: 'The XY axes of the selected sketch do not have the same direction as this sketch. Hold Ctrl+Alt to disregard it.',
  rlOriginsMisaligned: 'The origin of the selected sketch is not aligned with the origin of this sketch. Hold Ctrl+Alt to disregard it.',
}

// ── the geometry mirrored (Part::Geometry::mirror(point, dir): an axial symmetry about the axis, in 3D) ──────────
/** gp_Pnt::Mirror(gp_Ax1): the point turned half a turn about the axis through o along d; the sketch keeps x and y. */
function mirrorPoint(p: XY, o: V3, d: V3): XY {
  const v: V3 = [p[0] - o[0], p[1] - o[1], -o[2]]
  const t = dot3(v, d)
  return [2 * (o[0] + d[0] * t) - p[0], 2 * (o[1] + d[1] * t) - p[1]]
}
/** gp_Dir::Mirror(gp_Ax1) of a direction in the plane. */
function mirrorDir(v: XY, d: V3): XY { const t = v[0] * d[0] + v[1] * d[1]; return [2 * d[0] * t - v[0], 2 * d[1] * t - v[1]] }
const TWO_PI = 2 * Math.PI
const norm0 = (a: number) => a - Math.floor(a / TWO_PI) * TWO_PI
/** A sketch curve turned half a turn about an axis (Part::Geometry::mirror(point, dir), the axis in global terms as
 *  carbonCopy gives it): about an axis in the plane it is mirrored, its normal goes to -Z and the Sketcher reads an arc
 *  counter-clockwise from its other end; about an axis along the normal it is only turned in the plane. */
function mirrorGeo(g: Geo, o: V3, d: V3): Geo {
  const P = (p: XY) => mirrorPoint(p, o, d)
  const reversed = 2 * d[2] * d[2] - 1 < 0 // the normal +Z, mirrored: 2 (Z·d) d - Z
  switch (g.type) {
    case 'Point': return { ...g, at: P(g.at) }
    case 'LineSegment': return { ...g, start: P(g.start), end: P(g.end) }
    case 'Circle': return { ...g, center: P(g.center) }
    case 'ArcOfCircle': {
      const ang = reversed ? g.end_angle : g.start_angle
      const c = P(g.center), e = P([g.center[0] + g.radius * Math.cos(ang), g.center[1] + g.radius * Math.sin(ang)])
      const a1 = norm0(Math.atan2(e[1] - c[1], e[0] - c[0]))
      return { ...g, center: c, start_angle: a1, end_angle: a1 + (g.end_angle - g.start_angle) }
    }
    case 'Ellipse': return { ...g, center: P(g.center), x_axis: mirrorDir(g.x_axis, d) }
    case 'ArcOfEllipse': case 'ArcOfHyperbola': case 'ArcOfParabola': {
      // mirrored, the frame flips Y against X: the point at u is the mirrored conic's at -u
      const { start_point: _s, end_point: _e, ...rest } = g
      void _s; void _e
      const [u1, u2] = reversed ? [-g.end_angle, -g.start_angle] : [g.start_angle, g.end_angle]
      return { ...rest, center: P(g.center), x_axis: mirrorDir(g.x_axis, d), start_angle: u1, end_angle: u2 } as Geo
    }
    case 'BSplineCurve': return { ...g, poles: g.poles.map(P) }
  }
}

/** The constraint corrections for flipped geometry (applyConstraintFlipCorrection). */
function flipConstraint(c: Constraint, xinv: boolean, yinv: boolean): Constraint {
  if (!xinv && !yinv) return c
  const n = { ...c }
  if ((xinv && n.type === 'DistanceX') || (yinv && n.type === 'DistanceY')) {
    if (n.first === n.second) [n.firstPos, n.secondPos] = [n.secondPos, n.firstPos]
    else n.value = -n.value
  }
  if (n.type === 'Angle') {
    const na = (a: number) => { while (a > Math.PI) a -= Math.PI * 2; while (a <= -Math.PI) a += Math.PI * 2; return a }
    if (xinv && yinv) {
      if (n.first === -1 || n.second === -1 || n.first === -2 || n.second === -2 || n.second === GEO_UNDEF) n.value = na(n.value + Math.PI)
    } else if (xinv) {
      if (n.first === -1 || n.second === -1 || n.second === GEO_UNDEF) n.value = na(Math.PI - n.value)
      else n.value = na(-n.value)
    } else if (yinv) {
      if (n.first === -2 || n.second === -2) n.value = na(Math.PI - n.value)
      else n.value = na(-n.value)
    }
  }
  return n
}

/** SketchObject::carbonCopy's geometry and constraints: src's geometry after this sketch's (mirrored for xinv / yinv about
 *  this sketch's own axes through its origin, as FreeCAD gives Part::Geometry::mirror this Placement's position and
 *  axes), construction when asked (but points), src's constraints with their GeoIds moved (its own past ours, its
 *  external ones past our externalCount, axes included as getExternalGeometryCount counts them). */
export function carbonCopy(d: OPS.Doc, src: OPS.Doc, self: Placement, xinv: boolean, yinv: boolean, construction: boolean, externalCount: number) {
  const next = d.geometry.length
  const o = self.base, axisH = multVec(self.rotation, [1, 0, 0]), axisV = multVec(self.rotation, [0, 1, 0])
  const geos = src.geometry.map((g0) => {
    let g = { ...g0 } as Geo
    if (xinv) g = mirrorGeo(g, o, axisV)
    if (yinv) g = mirrorGeo(g, o, axisH)
    if (construction && g.type !== 'Point') g = { ...g, construction: true }
    return g
  })
  const cons = src.constraints.map((c0) => {
    const c = { ...c0 }
    for (const k of ['first', 'second', 'third'] as const) {
      if (c0[k] >= 0) c[k] = c0[k] + next
      else if (c0[k] < -2 && c0[k] !== GEO_UNDEF) c[k] = c0[k] - (externalCount - 2)
    }
    return flipConstraint(c, xinv, yinv)
  })
  d.geometry = [...d.geometry, ...geos]
  d.constraints = [...d.constraints, ...cons]
  return src.geometry.length
}

