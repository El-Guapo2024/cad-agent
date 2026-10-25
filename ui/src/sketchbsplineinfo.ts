// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/EditModeInformationOverlayCoinConverter.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditModeGeometryCoinConverter.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditModeCoinManager.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/CommandSketcherOverlay.cpp: 2023 Florian Foinant-Willig
// The edit mode's information layer: for each B-spline its degree (at the poles' centre of mass), its control polygon,
// its curvature comb, the multiplicity of each knot ("(4)") and the weight of each pole ("[1.00]", a line below), in
// InformationColor; for each arc of circle its whole circle (the circular helper). Sketcher_BSplineDegree,
// _BSplinePolygon, _BSplineComb, _BSplineKnotMultiplicity, _BSplinePoleWeight and Sketcher_ArcOverlay toggle them
// (ShowRestoreInformationLayer: Mod/Sketcher/General's BSplineDegreeVisible ... on by default, ArcCircleHelperVisible
// off).
import type { XY } from './solver'
import * as CV from './sketchcurves'
import { overlays, SIZES, labelFont, type Screen, type DrawState } from './sketchdraw'
import { saved } from './store'

/** Mod/Sketcher/General's overlay parameters and their defaults (updateOverlayVisibilityParameter). */
export const LAYERS = {
  Sketcher_BSplineDegree: ['BSplineDegreeVisible', true],
  Sketcher_BSplinePolygon: ['BSplineControlPolygonVisible', true],
  Sketcher_BSplineComb: ['BSplineCombVisible', true],
  Sketcher_BSplineKnotMultiplicity: ['BSplineKnotMultiplicityVisible', true],
  Sketcher_BSplinePoleWeight: ['BSplinePoleWeightVisible', true],
  Sketcher_ArcOverlay: ['ArcCircleHelperVisible', false],
} as const
export type LayerCommand = keyof typeof LAYERS
const key = (c: LayerCommand) => `sketcher.${LAYERS[c][0]}`
export const isLayerVisible = (c: LayerCommand): boolean => saved.get(key(c), LAYERS[c][1] as boolean)
let redraw: () => void = () => {}
/** The edit mode's redraw, for a toggle (sketcher.ts's changed). */
export function onLayerToggled(f: () => void) { redraw = f }
/** ShowRestoreInformationLayer: the parameter flipped (GetBool with true as the default, as the command reads it). */
export function toggleLayer(c: LayerCommand) {
  saved.set(key(c), !saved.get(key(c), true))
  redraw()
}

/** DrawingParameters::InformationColor (#00FF00; the View preference InformationColor). */
export const INFORMATION_COLOR = '#00ff00'
const APPROXIMATION = 1e-6
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]]
const len = (a: XY) => Math.hypot(a[0], a[1])

/** GeomCurve::curvatureAt and normalAt (GeomLProp_CLProps, 2nd order): the curvature and the unit normal towards the
 *  centre of curvature ([0, 0] where there is none). */
function curvature(b: CV.BSpline, u: number): { k: number; n: XY } {
  const { d } = CV.bsplineD1(b, u)
  const [lo, hi] = CV.bsplineRange(b)
  const h = Math.max(1e-7, (hi - lo) * 1e-6)
  const a = CV.bsplineD1(b, Math.max(lo, u - h)).d, c = CV.bsplineD1(b, Math.min(hi, u + h)).d
  const dt = Math.min(hi, u + h) - Math.max(lo, u - h)
  const d2: XY = [(c[0] - a[0]) / dt, (c[1] - a[1]) / dt]
  const l = len(d)
  if (l < 1e-12) return { k: 0, n: [0, 0] }
  const cr = d[0] * d2[1] - d[1] * d2[0]
  const k = Math.abs(cr) / (l * l * l)
  if (k < 1e-12) return { k: 0, n: [0, 0] }
  const t: XY = [d[0] / l, d[1] / l]
  return { k, n: cr > 0 ? [-t[1], t[0]] : [t[1], -t[0]] }
}
/** EditModeGeometryCoinConverter's combrepscale: 0.5 × the farthest point from the poles' centre over the highest
 *  curvature, the largest over the B-splines. */
function combScale(splines: CV.BSpline[]): number {
  let scale = 0
  for (const b of splines) {
    const mid = centre(b.poles)
    const [first, last] = CV.bsplineRange(b)
    const ndiv = b.poles.length > 4 ? b.poles.length * 16 : 64
    const step = (last - first) / (ndiv - 1)
    let maxk = 0, maxd = 0
    for (let i = 0; i < ndiv; i++) {
      const u = first + i * step
      const k = curvature(b, u).k
      if (k > maxk) maxk = k
      maxd = Math.max(maxd, len(sub(CV.bsplineValue(b, u), mid)))
    }
    const rep = maxk > 0 ? (0.5 * maxd) / maxk : 0
    if (rep > scale) scale = rep
  }
  return scale
}
const centre = (ps: XY[]): XY => { let x = 0, y = 0; for (const p of ps) { x += p[0]; y += p[1] } return [x / ps.length, y / ps.length] }
/** overlayParameters.currentBSplineCombRepresentationScale: kept until the new one is more than twice or less than half
 *  of it (updateOverlayParameters). */
let currentScale = 0

function polyline(ctx: CanvasRenderingContext2D, s: Screen, pts: XY[]) {
  ctx.beginPath()
  pts.forEach((p, i) => { const [x, y] = s.toScreen(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y) })
  ctx.stroke()
}
/** SoText2 at a point: the text from there, in the information colour; line 2 one line below. */
function text(ctx: CanvasRenderingContext2D, s: Screen, at: XY, str: string, line = 1) {
  const [x, y] = s.toScreen(at)
  ctx.fillText(str, x, y + (line - 1) * SIZES.font)
}

function drawLayer(ctx: CanvasRenderingContext2D, s: Screen, st: DrawState) {
  const splines = st.geometry.filter((g): g is CV.BSpline => g.type === 'BSplineCurve')
  const arcs = st.geometry.filter((g) => g.type === 'ArcOfCircle')
  if (!splines.length && !arcs.length) return
  const scale = combScale(splines)
  if (scale > 2 * currentScale || scale < currentScale / 2) currentScale = scale
  ctx.save()
  ctx.strokeStyle = ctx.fillStyle = INFORMATION_COLOR
  ctx.lineWidth = 1
  ctx.font = labelFont()
  ctx.textBaseline = 'alphabetic'
  ctx.setLineDash([])
  for (const b of splines) {
    if (isLayerVisible('Sketcher_BSplineDegree')) text(ctx, s, centre(b.poles), String(b.degree))
    if (isLayerVisible('Sketcher_BSplinePolygon')) polyline(ctx, s, b.periodic ? [...b.poles, b.poles[0]] : b.poles)
    if (isLayerVisible('Sketcher_BSplineComb')) {
      // the curvature graph: 64 radials a knot span, from the curve to curve - scale × curvature × normal, and the line
      // through their ends
      const ends: XY[] = []
      for (let k = 0; k < b.knots.length - 1; k++) {
        const f = b.knots[k] + APPROXIMATION * (b.knots[k + 1] - b.knots[k])
        const l = b.knots[k + 1] - APPROXIMATION * (b.knots[k + 1] - b.knots[k])
        const step = (l - f) / 63
        for (let i = 0; i < 64; i++) {
          const u = f + i * step, p = CV.bsplineValue(b, u), { k: kk, n } = curvature(b, u)
          const e: XY = [p[0] - currentScale * kk * n[0], p[1] - currentScale * kk * n[1]]
          polyline(ctx, s, [p, e])
          ends.push(e)
        }
      }
      if (ends.length) polyline(ctx, s, ends)
    }
    if (isLayerVisible('Sketcher_BSplineKnotMultiplicity')) b.knots.forEach((u, i) => text(ctx, s, CV.bsplineValue(b, u), `(${b.mults[i]})`))
    if (isLayerVisible('Sketcher_BSplinePoleWeight')) {
      const w = b.weights && b.weights.length === b.poles.length ? b.weights : b.poles.map(() => 1)
      b.poles.forEach((p, i) => text(ctx, s, p, `[${w[i].toFixed(2)}]`, 2))
    }
  }
  if (isLayerVisible('Sketcher_ArcOverlay')) {
    for (const a of arcs) {
      if (a.type !== 'ArcOfCircle') continue
      const n = 50, pts: XY[] = []
      for (let i = 0; i <= n; i++) { const t = (i % n) * (2 * Math.PI) / n; pts.push([a.center[0] + a.radius * Math.cos(t), a.center[1] + a.radius * Math.sin(t)]) }
      polyline(ctx, s, pts)
    }
  }
  ctx.restore()
}
overlays.push(drawLayer)
