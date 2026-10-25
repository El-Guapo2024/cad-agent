// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/EditModeCoinManager.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditModeCoinManagerParameters.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditModeGeometryCoinManager.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditModeConstraintCoinManager.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SoZoomTranslation.cpp: 2011 Werner Mayer
//   src/Mod/Sketcher/Gui/ViewProviderSketch.cpp: 2009 Juergen Riegel
//   src/Mod/Part/Gui/ViewProviderGridExtension.cpp: 2023 Abdullah Tahiri
//   src/Gui/SoDatumLabel.cpp: 2011-2012 Luke Parry; 2026 Joao Matos
// What a sketch in edit mode looks like (EditModeCoinManager and its geometry and constraint managers, SoDatumLabel,
// the sketch grid), drawn on a 2D canvas laid over the 3D view and redrawn with every frame of it. Coin draws these
// as screen-sized nodes in the sketch's plane; here every point is projected to the screen and drawn there, in the same
// pixel sizes, so the look holds however the view turns. Colours are FreeCAD's "FreeCAD Light" preference pack (what
// a new FreeCAD 26 profile starts with, as the rest of this UI); the code defaults are in the comments.
import type { Geo, XY } from './solver'
import { type Constraint, type PointPos, GEO_UNDEF, NONE, START, END, MID, H_AXIS, V_AXIS, getPoint, isLine, isCircle, isArc, isCircular,
  polyline, presentationValue, isDimensional, vertices } from './sketch'

// ── DrawingParameters (EditModeCoinManagerParameters.cpp) as the FreeCAD Light pack sets them ───────────────────────
const hex = (n: number) => '#' + n.toString(16).padStart(6, '0')
export const COLORS = {
  /** EditedEdgeColor (code default #FFFFFF). */
  curve: hex(0x495057),
  /** ConstructionColor (#0000DC). */
  construction: hex(0x3b5bdb),
  /** InternalAlignedGeoColor (#B2B27F). */
  internal: hex(0x3b5bdb),
  /** FullyConstraintElementColor (#80D0A0). */
  fullyElement: hex(0x2f9e44),
  /** FullyConstraintConstructionElementColor (#8FA9FD). */
  fullyConstruction: hex(0x91a7ff),
  /** FullyConstrainedColor (#00FF00). */
  fully: hex(0x2f9e44),
  /** InvalidSketchColor (#FF6D00). */
  invalid: hex(0xff6d00),
  /** ConstrainedDimColor and ConstrainedIcoColor (#FF2600). */
  constrDim: hex(0xe03131), constrIco: hex(0xe03131),
  /** NonDrivingConstrDimColor (#0026FF), DeactivatedConstrDimColor (#7F7F7F), ExprBasedConstrDimColor (#FF7F26). */
  nonDriving: hex(0x868e96), deactivated: hex(0x868e96), exprBased: hex(0xe03131),
  /** ExternalColor (#CC3399). */
  external: hex(0xae3ec9),
  /** HighlightColor and SelectionColor (View), PreselectSelectedColor (#05BAFF, not a preference). */
  preselect: hex(0x0ac8ff), select: hex(0x00abff), preselectSelected: hex(0x05baff),
  /** CursorTextColor (#0000FF) and CursorCrosshairColor (#FFFFFF). */
  cursorText: hex(0x212529), crosshair: hex(0x212529),
  /** AxisXColor / AxisYColor (View3DSettings: #CC3333, #33CC33). */
  axisH: hex(0xcc3333), axisV: hex(0x33cc33),
  /** Sketcher/General GridLineColor and GridDivLineColor (#B2B2B2). */
  grid: hex(0xb7bfcc), gridDiv: hex(0xb7bfcc),
}
export const SIZES = {
  /** MarkerSize (View, 7): the points' CIRCLE_FILLED marker. */
  marker: 7,
  /** The point set's pointSize, 8 × pixelScalingFactor (the hit radius takes the larger of the two). */
  pointSize: 8,
  /** EdgeWidth, ConstructionWidth, InternalWidth, ExternalWidth (Sketcher/View, 2). */
  curve: 2, construction: 2, internal: 2, external: 2,
  /** AxisLineWidth (2), DimensionalConstraintLineWidth (2), the edit curve (3). */
  axis: 2, dimension: 2, editCurve: 3,
  /** ConstraintSymbolSize and EditSketcherFontSize: the application font's height in pixels (QFontMetricsF::height). */
  icon: 16, font: 16,
  /** Grid: GridLineWidth 1, GridDivLineWidth 2, GridSizePixelThreshold 15, GridNumberSubdivision 10, GridTransparency 60. */
  gridLine: 1, gridDivLine: 2, gridPixels: 15, gridSubdiv: 10, gridAlpha: 0.4,
  /** AxisTransparency (30). */
  axisAlpha: 0.7,
}
/** ConstructionPattern 0b1111110011111100 (InternalPattern and ExternalPattern the same): six pixels on, two off. */
const DASH = [6, 2]

export type Screen = {
  w: number; h: number
  /** Sketch coordinates to CSS pixels from the canvas's top left. */
  toScreen(p: XY): [number, number]
  /** World units (mm) per screen pixel at the focal plane (SoDatumLabel::getScaleFactor). */
  worldPerPx: number
  /** The view's visible height in mm (an orthographic camera's height). */
  visibleHeight: number
  /** The NaviCube's square, which the overlay leaves clear. */
  hole?: { x: number; y: number; w: number; h: number } | null
}
/** ViewProviderSketch::getScaleFactor: getWorldToScreenScale(origin, 0.1) / 3 of the camera's own view volume (aspect 1). */
export const scaleFactor = (s: Screen) => (0.1 * s.visibleHeight) / 3
/** SoZoomTranslation::calculateScaleFactor: getWorldToScreenScale(0, 0.1) / (5 × aspect) of the rendered view volume. */
const zoomScale = (s: Screen) => (0.1 * s.visibleHeight) / 5

export type DrawState = {
  /** The geometry, its external geometry reachable at GeoIds -3, -4, … (sketch.ts withExternal). */
  geometry: Geo[]
  /** The external geometry (ExternalGeo after the axes), GeoId -3 first. */
  external?: Geo[]
  constraints: Constraint[]
  /** Solver result: the sketch is fully constrained (dof 0, no conflicts), or invalid. */
  fully: boolean
  /** Geometry the solver leaves no freedom (SolverGeometryExtension::FullyConstraint). */
  fullyElements: Set<number>
  invalid: boolean
  /** Coincident points (coloured as constraint icons when not fully constrained). */
  preselect: { point: number; curve: number | null; cross: number | null; constraints: number[] }
  selection: { points: Set<number>; curves: Set<number>; constraints: Set<number> }
  /** The handler's edit curves (drawEdit) and markers, in sketch coordinates. */
  editCurves: XY[][]
  editConstruction: boolean
  editMarkers: XY[]
  /** The auto-constraint hints: a line's extension, and the parallel/perpendicular/tangent guide lines (the active one
   *  drawn solid). */
  extensionHint: XY[] | null
  directionHints: { lines: XY[][]; active: number }
  /** The cursor's text (setPositionText): where and what. */
  positionText: { at: XY; text: string } | null
  /** The on-view parameters: datum labels the tool shows while it draws. */
  ovps: { kind: 'DISTANCE' | 'DISTANCEX' | 'DISTANCEY' | 'RADIUS' | 'DIAMETER' | 'ANGLE'; pts: XY[]; text: string; param1: number; param2?: number; param3?: number; focus: boolean; locked: boolean }[]
  /** The rubber band of a box selection, in canvas pixels. */
  rubber: { a: [number, number]; b: [number, number] } | null
  showGrid: boolean
  gridSize: number
  /** Constraints the view leaves out (TaskSketcherConstraints' visibility check boxes, the virtual space). */
  hiddenConstraints: Set<number>
}

/** What the last draw put where, for the constraint preselection (EditModeConstraintCoinManager's combined icon boxes
 *  and the datum labels' text). */
export type HitRegions = {
  icons: { x: number; y: number; w: number; h: number; ids: number[] }[]
  labels: { x: number; y: number; w: number; h: number; angle: number; id: number }[]
  /** Each datum's lines, in screen pixels (DatumAnnotation hits). */
  datumLines: { pts: [number, number][]; id: number }[]
}

// ── icons ───────────────────────────────────────────────────────────────────────────────────────────────────────
const images = new Map<string, HTMLImageElement>()
let onIconLoad: () => void = () => {}
export function iconsLoaded(f: () => void) { onIconLoad = f }
/** Sketcher icon file (public/freecad-icons/sketcher). */
export const sketcherIcon = (name: string) => (name.startsWith('edit-') ? `./freecad-icons/${name}.svg` : `./freecad-icons/sketcher/${name}.svg`) // edit-copy …: Gui's icons
export function iconImage(name: string): HTMLImageElement | null {
  let img = images.get(name)
  if (!img) {
    img = new Image()
    img.onload = () => onIconLoad()
    img.src = sketcherIcon(name)
    images.set(name, img)
  }
  return img.complete && img.naturalWidth ? img : null
}
const tinted = new Map<string, HTMLCanvasElement>()
/** renderConstrIcon: the icon drawn at ConstraintSymbolSize and filled with its colour (QPainter's SourceIn). */
function tintedIcon(name: string, color: string, size: number, rotation: number): HTMLCanvasElement | null {
  const key = `${name}|${color}|${size}|${rotation.toFixed(3)}`
  const hit = tinted.get(key)
  if (hit) return hit
  const img = iconImage(name)
  if (!img) return null
  const c = document.createElement('canvas')
  const dpr = devicePixelRatio || 1
  c.width = c.height = Math.ceil(size * dpr)
  const g = c.getContext('2d')!
  g.scale(dpr, dpr)
  if (rotation) { g.translate(size / 2, size / 2); g.rotate((rotation * Math.PI) / 180); g.translate(-size / 2, -size / 2) }
  g.drawImage(img, 0, 0, size, size)
  g.globalCompositeOperation = 'source-in'
  g.fillStyle = color
  g.fillRect(0, 0, size, size)
  tinted.set(key, c)
  return c
}

// ── colours of the elements (EditModeGeometryCoinManager::updateGeometryColor) ──────────────────────────────────
function isCoincident(cons: Constraint[], g: number, pos: PointPos) {
  return cons.some((c) => (c.type === 'Coincident' || (c.type === 'Tangent' && c.firstPos !== NONE)
    || (c.type === 'Perpendicular' && c.firstPos !== NONE && c.secondPos !== NONE))
    && ((c.first === g && c.firstPos === pos) || (c.second === g && c.secondPos === pos)))
}
function pointColor(st: DrawState, vertex: number, g: number, pos: PointPos): string {
  const sel = st.selection.points.has(vertex), pre = st.preselect.point === vertex
  if (sel) return pre ? COLORS.preselectSelected : COLORS.select
  if (pre) return COLORS.preselect
  // an external point: ConstrIcoColor when coincident with something (and the sketch valid), else ExternalColor
  if (g <= -3) return isCoincident(st.constraints, g, pos) && !st.invalid ? COLORS.constrIco : COLORS.external
  if (st.invalid) return COLORS.invalid
  if (st.fully) return COLORS.fully
  const geo = st.geometry[g]
  const defined = (pos === START || pos === END) && !geo.construction
  if (st.fullyElements.has(g)) return defined ? COLORS.fullyElement : COLORS.fullyConstruction
  if (isCoincident(st.constraints, g, pos)) return COLORS.constrIco
  return defined ? COLORS.curve : COLORS.construction
}
function curveColor(st: DrawState, g: number): string {
  const sel = st.selection.curves.has(g), pre = st.preselect.curve === g
  if (sel || pre) return sel ? (pre ? COLORS.preselectSelected : COLORS.select) : COLORS.preselect
  if (g <= -3) return COLORS.external // CurveExternalColor (a reference external; a defining one has its own)
  if (st.invalid) return COLORS.invalid
  if (st.geometry[g].construction) return st.fullyElements.has(g) ? COLORS.fullyConstruction : COLORS.construction
  return st.fully ? COLORS.fully : st.fullyElements.has(g) ? COLORS.fullyElement : COLORS.curve
}
/** EditModeConstraintCoinManager::constrColor. */
function constrColor(st: DrawState, i: number): string {
  const c = st.constraints[i]
  if (st.preselect.constraints.includes(i)) return COLORS.preselect
  if (st.selection.constraints.has(i)) return COLORS.select
  if (!c.active) return COLORS.deactivated
  if (!c.driving) return COLORS.nonDriving
  return COLORS.constrIco
}

type Ctx = CanvasRenderingContext2D
function strokePoly(ctx: Ctx, s: Screen, pts: XY[], color: string, width: number, dash: number[] = [], alpha = 1) {
  if (pts.length < 2) return
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.setLineDash(dash)
  ctx.lineJoin = 'round'
  ctx.beginPath()
  pts.forEach((p, i) => { const [x, y] = s.toScreen(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y) })
  ctx.stroke()
  ctx.restore()
}
function fillTri(ctx: Ctx, s: Screen, a: XY, b: XY, c: XY, color: string) {
  ctx.fillStyle = color
  ctx.beginPath()
  for (const [i, p] of [a, b, c].entries()) { const [x, y] = s.toScreen(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y) }
  ctx.closePath()
  ctx.fill()
}
function dot(ctx: Ctx, x: number, y: number, size: number, color: string, hollow = false) {
  ctx.beginPath()
  ctx.arc(x, y, size / 2, 0, 2 * Math.PI)
  if (hollow) { ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke() } else { ctx.fillStyle = color; ctx.fill() }
}

// ── the grid (ViewProviderGridExtension: GridExtensionP::computeGridSize / createGridPart) ──────────────────────
export function gridSpacing(s: Screen, gridSize: number) {
  const maxDim = Math.max(s.w, s.h) * s.worldPerPx
  const lines = Math.max(s.w, s.h) / SIZES.gridPixels
  const n = SIZES.gridSubdiv
  return gridSize * Math.pow(n, 1 + Math.floor(Math.log(maxDim / lines / gridSize) / Math.log(n)))
}
function drawGrid(ctx: Ctx, s: Screen, st: DrawState, center: XY) {
  const spacing = gridSpacing(s, st.gridSize), dim = 1.5 * Math.max(s.w, s.h) * s.worldPerPx
  if (!Number.isFinite(spacing) || (2 * dim) / spacing > 2000) return
  const x0 = center[0] - dim / 2, y0 = center[1] - dim / 2, n = SIZES.gridSubdiv
  for (const div of [false, true]) {
    const pts: [XY, XY][] = []
    for (let k = Math.trunc(x0 / spacing); k * spacing < x0 + dim; k++) {
      if (k === 0 || (k % n === 0) !== div) continue
      pts.push([[k * spacing, y0], [k * spacing, y0 + dim]])
    }
    for (let k = Math.trunc(y0 / spacing); k * spacing < y0 + dim; k++) {
      if (k === 0 || (k % n === 0) !== div) continue
      pts.push([[x0, k * spacing], [x0 + dim, k * spacing]])
    }
    ctx.save()
    ctx.globalAlpha = SIZES.gridAlpha
    ctx.strokeStyle = div ? COLORS.gridDiv : COLORS.grid
    ctx.lineWidth = div ? SIZES.gridDivLine : SIZES.gridLine
    ctx.beginPath()
    for (const [a, b] of pts) { const p = s.toScreen(a), q = s.toScreen(b); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]) }
    ctx.stroke()
    ctx.restore()
  }
}

// ── constraint icons (processConstraints' icon positions, drawConstraintIcons, combineConstraintIcons) ──────────
type IconItem = { type: string; id: number; pos: XY; label: string; rotation: number }
const ICON: Partial<Record<Constraint['type'], string>> = {
  Horizontal: 'Constraint_Horizontal', Vertical: 'Constraint_Vertical', PointOnObject: 'Constraint_PointOnObject',
  Tangent: 'Constraint_Tangent', Parallel: 'Constraint_Parallel', Perpendicular: 'Constraint_Perpendicular',
  Equal: 'Constraint_EqualLength', Symmetric: 'Constraint_Symmetric', SnellsLaw: 'Constraint_SnellsLaw', Block: 'Constraint_Block',
}
const norm2 = (v: XY): XY => { const l = Math.hypot(v[0], v[1]) || 1; return [v[0] / l, v[1] / l] }
/** Where a curve's icon anchors and which way is "out" (midpoint and normal of a line, 45° on a circle, the middle of
 *  an arc). */
function anchorOf(g: Geo): { mid: XY; norm: XY } | null {
  if (isLine(g)) { const d = norm2([g.end[0] - g.start[0], g.end[1] - g.start[1]]); return { mid: [(g.start[0] + g.end[0]) / 2, (g.start[1] + g.end[1]) / 2], norm: [-d[1], d[0]] } }
  if (isCircle(g)) { const a = Math.PI / 4, n: XY = [Math.cos(a), Math.sin(a)]; return { mid: [g.center[0] + g.radius * n[0], g.center[1] + g.radius * n[1]], norm: n } }
  if (isArc(g)) { const a = (g.start_angle + g.end_angle) / 2, n: XY = [Math.cos(a), Math.sin(a)]; return { mid: [g.center[0] + g.radius * n[0], g.center[1] + g.radius * n[1]], norm: n } }
  return null
}
/** The normal of a curve at a point on it (getNormal in processConstraints). */
function normalAt(geo: Geo[], g: number, p: XY): XY {
  if (g === H_AXIS) return [0, 1]
  if (g === V_AXIS) return [-1, 0]
  const e = geo[g]
  if (isLine(e)) { const d = [e.end[0] - e.start[0], e.end[1] - e.start[1]]; return norm2([-d[1], d[0]]) }
  if (isCircular(e)) { const c = (e as { center: XY }).center; return norm2([p[0] - c[0], p[1] - c[1]]) }
  return [1, 0]
}
function iconItems(st: DrawState, s: Screen): IconItem[] {
  const out: IconItem[] = [], geo = st.geometry, sf = zoomScale(s)
  const seek = (n: XY, step: number): XY => [n[0] * 0.5 * step * sf, n[1] * 0.5 * step * sf]
  const at = (p: XY, rel: XY): XY => [p[0] + rel[0], p[1] + rel[1]]
  st.constraints.forEach((c, id) => {
    const type = ICON[c.type]
    if (!type || st.hiddenConstraints.has(id)) return
    const two = (p1: XY, p2: XY) => {
      const label = c.name || String(id + 1)
      out.push({ type, id, pos: p1, label, rotation: 0 }, { type, id, pos: p2, label, rotation: 0 })
    }
    const one = (p: XY, rotation = 0) => out.push({ type, id, pos: p, label: c.name, rotation })
    switch (c.type) {
      case 'Block': case 'Horizontal': case 'Vertical': {
        if (c.type !== 'Block' && c.second !== GEO_UNDEF) { // point alignment: an icon by each point
          const p1 = getPoint(geo, c.first, c.firstPos), p2 = getPoint(geo, c.second, c.secondPos)
          if (!p1 || !p2) return
          const d = norm2([p2[0] - p1[0], p2[1] - p1[1]]), n: XY = [-d[1], d[0]]
          two(at(p1, seek(n, 4)), at(p2, seek(n, 4)))
          return
        }
        const g = geo[c.first]
        if (!g) return
        if (g.type === 'Point') { one(at(g.at, seek([0, 1], 2.5))); return }
        const a = anchorOf(g)
        if (a) one(at(a.mid, seek(a.norm, 2.5)))
        return
      }
      case 'Perpendicular': {
        if (c.third !== GEO_UNDEF || c.firstPos !== NONE) {
          const [g, pos] = c.firstPos !== NONE ? [c.first, c.firstPos] : c.secondPos !== NONE ? [c.second, c.secondPos] : [c.third, c.thirdPos]
          const p = getPoint(geo, g, pos)
          if (!p) return
          one(at(p, seek(normalAt(geo, c.second, p), 4)))
          return
        }
        const a1 = anchorOf(geo[c.first]), a2 = anchorOf(geo[c.second])
        if (a1 && a2) two(at(a1.mid, seek(a1.norm, 4)), at(a2.mid, seek(a2.norm, 4)))
        return
      }
      case 'Parallel': case 'Equal': {
        const a1 = geo[c.first] && anchorOf(geo[c.first]), a2 = geo[c.second] && anchorOf(geo[c.second])
        if (a1 && a2) two(at(a1.mid, seek(a1.norm, 4)), at(a2.mid, seek(a2.norm, 4)))
        return
      }
      case 'PointOnObject': case 'Tangent': case 'SnellsLaw': {
        if (c.type !== 'Tangent' || c.third !== GEO_UNDEF || c.firstPos !== NONE) {
          const [g, pos] = c.firstPos !== NONE ? [c.first, c.firstPos] : c.secondPos !== NONE ? [c.second, c.secondPos] : [c.third, c.thirdPos]
          const p = getPoint(geo, g, pos)
          if (!p) return
          one(at(p, seek(normalAt(geo, c.second, p), 2.5)))
          return
        }
        let g1 = geo[c.first], g2 = geo[c.second]
        if (isLine(g1) && isLine(g2)) {
          const a1 = anchorOf(g1)!, a2 = anchorOf(g2)!
          two(at(a1.mid, seek(a1.norm, 4)), at(a2.mid, seek(a2.norm, 4)))
          return
        }
        if (isLine(g2)) [g1, g2] = [g2, g1]
        if (isLine(g1) && isCircular(g2)) { // the foot of the circle's centre on the line, one unit out (TODO Huh? in FreeCAD)
          const d = norm2([g1.end[0] - g1.start[0], g1.end[1] - g1.start[1]]), cc = (g2 as { center: XY }).center
          const t = (cc[0] - g1.start[0]) * d[0] + (cc[1] - g1.start[1]) * d[1]
          const pos: XY = [g1.start[0] + d[0] * t, g1.start[1] + d[1] * t]
          one(at(pos, [-d[1] * sf, d[0] * sf]))
          return
        }
        if (isCircular(g1) && isCircular(g2)) {
          const a = g1 as { center: XY; radius: number }, b = g2 as { center: XY }
          const d = norm2([b.center[0] - a.center[0], b.center[1] - a.center[1]])
          one(at([a.center[0] + d[0] * a.radius, a.center[1] + d[1] * a.radius], [d[0] * sf, d[1] * sf]))
        }
        return
      }
      case 'Symmetric': {
        const p1 = getPoint(geo, c.first, c.firstPos), p2 = getPoint(geo, c.second, c.secondPos)
        if (!p1 || !p2) return
        const a = s.toScreen(p1), b = s.toScreen(p2)
        // ViewProviderSketch::getRotation: the screen angle from the first point to the second, in degrees, y down
        one([(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2], (-Math.atan2(-(b[1] - a[1]), b[0] - a[0]) * 180) / Math.PI)
        return
      }
    }
  })
  return out
}
/** renderConstrIcon + drawMergedConstraintIcons: icons nearer each other than getScaleFactor go into one, the same
 *  types side by side with their numbers, other types stacked under. */
function drawIcons(ctx: Ctx, s: Screen, st: DrawState, hits: HitRegions) {
  const items = iconItems(st, s), scale = scaleFactor(s), size = SIZES.icon
  const groups: IconItem[][] = []
  const done = new Set<number>()
  const valid = items.map((_, i) => i).filter((i) => items[i].type !== 'Constraint_Symmetric')
  for (const i of items.keys()) if (items[i].type === 'Constraint_Symmetric') groups.push([items[i]])
  for (const start of [...valid].reverse()) {
    if (done.has(start)) continue
    const group: IconItem[] = [], stack = [start]
    done.add(start)
    while (stack.length) {
      const k = stack.pop()!
      group.push(items[k])
      for (const j of valid) {
        if (done.has(j)) continue
        if ((items[k].pos[0] - items[j].pos[0]) ** 2 + (items[k].pos[1] - items[j].pos[1]) ** 2 <= scale * scale) { done.add(j); stack.push(j) }
      }
    }
    groups.push(group)
  }
  ctx.save()
  const font = `bold ${size}px ${getComputedStyle(document.body).fontFamily || 'sans-serif'}`
  ctx.font = font
  ctx.textBaseline = 'alphabetic'
  for (const group of groups) {
    // rows: one per icon type, in the order they first appear
    const rows: IconItem[][] = []
    for (const it of group) { const r = rows.find((x) => x[0].type === it.type); if (r) r.push(it); else rows.push([it]) }
    const rowBoxes: { w: number; h: number; row: IconItem[] }[] = rows.map((row) => {
      const labels = group.length === 1 ? row.map((r) => r.label) : row.map((r) => r.label || String(r.id + 1))
      const text = labels.filter(Boolean).join(', ')
      const w = size + (text ? ctx.measureText(text).width + 1 : 0)
      return { w, h: size + (text ? 3 : 0), row }
    })
    const W = Math.max(...rowBoxes.map((r) => r.w)), H = rowBoxes.reduce((a, r) => a + r.h, 0)
    const [cx, cy] = s.toScreen(group[0].pos)
    let y = cy - H / 2
    for (const { row, h } of rowBoxes) {
      const x = cx - W / 2, ids = row.map((r) => r.id)
      const color = constrColor(st, row.reduce((best, r) => (prio(st, r.id) > prio(st, best) ? r.id : best), row[0].id))
      const img = tintedIcon(row[0].type, color, size, row[0].rotation)
      if (img) ctx.drawImage(img, x, y, size, size)
      hits.icons.push({ x, y, w: size, h: size, ids })
      const labels = group.length === 1 ? row.map((r) => r.label) : row.map((r) => r.label || String(r.id + 1))
      let lx = x + size
      labels.forEach((l, i) => {
        if (!l) return
        const t = i + 1 < labels.length ? l + ', ' : l
        ctx.fillStyle = constrColor(st, row[i].id)
        ctx.fillText(t, lx, y + size)
        const tw = ctx.measureText(t).width
        hits.icons.push({ x: lx, y, w: tw, h: size, ids: [row[i].id] })
        lx += tw
      })
      y += h
    }
  }
  ctx.restore()
}
const prio = (st: DrawState, id: number) => (st.preselect.constraints.includes(id) ? 3 : st.selection.constraints.has(id) ? 2 : 1)

// ── datum labels (SoDatumLabel) ──────────────────────────────────────────────────────────────────────────────────
type Datum = { kind: 'DISTANCE' | 'DISTANCEX' | 'DISTANCEY' | 'RADIUS' | 'DIAMETER' | 'ANGLE' | 'SYMMETRIC'; pts: XY[]; text: string;
  param1: number; param2: number; param3?: number; param4?: number; param5?: number; param6?: number; ext?: XY[] }
const add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]], sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], dotp = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1]
const lenv = (a: XY) => Math.hypot(a[0], a[1])
/** findHelperAngles: the arc a radius/diameter or distance label needs drawn on beyond the arc's own ends. */
function helperAngles(angle: number, start: number, end: number): [number, number] {
  const margin = 0.2
  if (angle < 0) angle += 2 * Math.PI
  if (end > 2 * Math.PI && angle < end - 2 * Math.PI) angle += 2 * Math.PI
  if (angle <= start || angle >= end) {
    if ((angle < start && start - angle < angle + 2 * Math.PI - end) || (angle > end && start + 2 * Math.PI - angle < angle - end)) {
      if (angle > start) angle -= 2 * Math.PI
      return [angle - margin, start - angle + margin]
    }
    if (angle < end) angle += 2 * Math.PI
    return [end, angle - end + margin]
  }
  return [0, 0]
}
/** The 0..2π range Part::GeomArcOfCircle::getRange(emulateCCW) gives. */
function arcRange(g: Extract<Geo, { type: 'ArcOfCircle' }>): [number, number] {
  let s = g.start_angle % (2 * Math.PI)
  if (s < 0) s += 2 * Math.PI
  return [s, s + (g.end_angle - g.start_angle)]
}
/** processConstraints' datum cases: what each dimension's SoDatumLabel gets. */
function datumOf(geo: Geo[], c: Constraint): Datum | null {
  const P = (g: number, p: PointPos) => getPoint(geo, g, p)
  const label = (prefix = '') => {
    // getPresentationString: " (ƒ𝑥)" after a value bound to an expression
    const v = prefix + presentationValue(c) + (c.expr ? ' (ƒ𝑥)' : '')
    return c.driving ? v : `(${v})`
  }
  if (c.type === 'Distance' || c.type === 'DistanceX' || c.type === 'DistanceY') {
    const kind = c.type === 'Distance' ? 'DISTANCE' : c.type === 'DistanceX' ? 'DISTANCEX' : 'DISTANCEY'
    let p1: XY = P(c.first, c.firstPos) ?? [0, 0], p2: XY = [0, 0], ext: XY[] | undefined
    if (c.secondPos !== NONE) p2 = P(c.second, c.secondPos)!
    else if (c.second !== GEO_UNDEF) {
      const g1 = geo[c.first], g2 = geo[c.second]
      const lineHelper = (proj: XY, l: { start: XY; end: XY }) => {
        const d = sub(l.end, l.start), t = dotp(sub(proj, l.start), d) / dotp(d, d)
        if (t < -1e-12) ext = [l.start, proj]
        else if (t > 1 + 1e-12) ext = [l.end, proj]
      }
      if (isLine(g2)) {
        if (c.firstPos !== NONE) {
          const d = sub(g2.end, g2.start), t = dotp(sub(p1, g2.start), d) / dotp(d, d)
          p2 = add(g2.start, mul(d, t)); lineHelper(p2, g2)
        } else if (isCircular(g1)) {
          const cc = (g1 as { center: XY; radius: number }), d = sub(g2.end, g2.start), t = dotp(sub(cc.center, g2.start), d) / dotp(d, d)
          p1 = add(g2.start, mul(d, t)); lineHelper(p1, g2)
          p2 = add(cc.center, mul(norm2(sub(p1, cc.center)), cc.radius))
        }
      } else if (isCircular(g2)) {
        const cc = g2 as { center: XY; radius: number }
        if (c.firstPos !== NONE) p2 = add(cc.center, mul(norm2(sub(p1, cc.center)), cc.radius))
        else if (isCircular(g1)) {
          const a = g1 as { center: XY; radius: number }, d = norm2(sub(cc.center, a.center))
          p1 = add(a.center, mul(d, a.radius)); p2 = add(cc.center, mul(d, -cc.radius))
        }
      } else return null
    } else if (c.firstPos !== NONE) { p1 = [0, 0]; p2 = P(c.first, c.firstPos)! }
    else {
      const g = geo[c.first]
      if (!isLine(g)) return null
      p1 = g.start; p2 = g.end
    }
    return { kind, pts: [p1, p2], text: label(), param1: c.labelDistance, param2: c.labelPosition, ext }
  }
  if (c.type === 'Radius' || c.type === 'Diameter') {
    const g = geo[c.first]
    if (!isCircular(g)) return null
    const r = (g as { radius: number }).radius, ctr = (g as { center: XY }).center
    let angle = c.labelPosition, h1: [number, number] = [0, 0], h2: [number, number] = [0, 0]
    if (isArc(g)) {
      const [s0, e0] = arcRange(g)
      if (angle === 10) angle = (s0 + e0) / 2
      h1 = helperAngles(angle, s0, e0)
      if (c.type === 'Diameter') h2 = helperAngles(angle + Math.PI, s0, e0)
    } else if (angle === 10) angle = 0
    const u: XY = [Math.cos(angle), Math.sin(angle)]
    const p1 = c.type === 'Diameter' ? sub(ctr, mul(u, r)) : ctr, p2 = add(ctr, mul(u, r))
    return { kind: c.type === 'Diameter' ? 'DIAMETER' : 'RADIUS', pts: [p1, p2], text: label(c.type === 'Diameter' ? '⌀' : 'R'),
      param1: c.labelDistance, param2: c.labelPosition, param3: h1[0], param4: h1[1], param5: h2[0], param6: h2[1] }
  }
  if (c.type === 'Angle') {
    const distance = c.labelDistance
    let p0: XY, start: number, range: number, end1 = 0, end2 = 0
    if (c.second !== GEO_UNDEF) {
      const g1 = geo[c.first], g2 = geo[c.second]
      const L = (g: Geo | undefined, id: number): { start: XY; end: XY } | null => (id === H_AXIS ? { start: [0, 0], end: [1, 0] } : id === V_AXIS ? { start: [0, 0], end: [0, 1] } : isLine(g) ? g : null)
      const l1 = L(g1, c.first), l2 = L(g2, c.second)
      if (!l1 || !l2) return null
      const f1 = c.firstPos === END, f2 = c.secondPos === END
      const dir1 = mul(norm2(sub(l1.end, l1.start)), f1 ? -1 : 1), dir2 = mul(norm2(sub(l2.end, l2.start)), f2 ? -1 : 1)
      const pnt1 = f1 ? l1.end : l1.start, pnt2 = f2 ? l2.end : l2.start, pnt12 = f1 ? l1.start : l1.end, pnt22 = f2 ? l2.start : l2.end
      const det = dir1[0] * dir2[1] - dir1[1] * dir2[0]
      let inter: XY
      if (Math.abs(det) < 1e-10) {
        let best = Infinity; inter = [0, 0]
        for (const a of [l1.start, l1.end]) for (const b of [l2.start, l2.end]) { const d = lenv(sub(b, a)); if (d < best) { best = d; inter = mul(add(a, b), 0.5) } }
      } else {
        const c1 = dir1[1] * pnt1[0] - dir1[0] * pnt1[1], c2 = dir2[1] * pnt2[0] - dir2[0] * pnt2[1]
        inter = [(dir1[0] * c2 - dir2[0] * c1) / det, (dir1[1] * c2 - dir2[1] * c1) / det]
      }
      p0 = inter
      range = c.value
      start = Math.atan2(dir1[1], dir1[0])
      const vl1 = sub(mul(dir1, 2 * distance), sub(pnt1, inter)), vl2 = sub(mul(dir2, 2 * distance), sub(pnt2, inter))
      const vl12 = sub(mul(dir1, 2 * distance), sub(pnt12, inter)), vl22 = sub(mul(dir2, 2 * distance), sub(pnt22, inter))
      end1 = dotp(vl12, dir1) > 0 ? lenv(vl12) : dotp(vl1, dir1) < 0 ? -lenv(vl1) : 0
      end2 = dotp(vl22, dir2) > 0 ? lenv(vl22) : dotp(vl2, dir2) < 0 ? -lenv(vl2) : 0
    } else {
      const g = geo[c.first]
      if (isLine(g)) {
        p0 = mul(add(g.start, g.end), 0.5)
        const l1 = 2 * distance - lenv(sub(g.end, g.start)) / 2
        end1 = 2 * distance; end2 = l1 > 0 ? l1 : 0
        start = 0; range = Math.atan2(g.end[1] - g.start[1], g.end[0] - g.start[0])
      } else if (isArc(g)) {
        p0 = g.center
        end1 = end2 = 2 * distance - g.radius
        const [s0, e0] = arcRange(g); start = s0; range = e0 - s0
      } else return null
    }
    return { kind: 'ANGLE', pts: [p0], text: label(), param1: distance, param2: start, param3: range, param4: end1, param5: end2 }
  }
  if (c.type === 'Symmetric') {
    const p1 = P(c.first, c.firstPos), p2 = P(c.second, c.secondPos)
    if (!p1 || !p2) return null
    return { kind: 'SYMMETRIC', pts: [p1, p2], text: '', param1: 0, param2: 0 }
  }
  return null
}

/** SoDatumLabel::GLRender: the lines, arrowheads and text of one label. Returns what to hit-test. */
function drawDatum(ctx: Ctx, s: Screen, d: Datum, color: string, lineWidth: number, font: string, hits: HitRegions | null, id: number, opts: { strike?: boolean; box?: boolean } = {}) {
  ctx.save()
  ctx.font = font
  const textW = d.text ? ctx.measureText(d.text).width : 0
  const textH = SIZES.font * 1.17 // QFontMetrics::height at the label's pixel size
  const k = s.worldPerPx
  let imgWidth = textW * k, imgHeight = textH * k
  if (d.kind === 'SYMMETRIC') { imgWidth = imgHeight = 25 * k }
  const lines: XY[][] = [], tris: [XY, XY, XY][] = []
  let textAt: XY | null = null, textAngle = 0
  const arc = (c: XY, r: number, a0: number, a1: number) => {
    const n = Math.max(6, Math.abs(Math.trunc((25 * (a1 - a0)) / Math.PI)))
    lines.push(Array.from({ length: n }, (_, i) => { const t = a0 + ((a1 - a0) * i) / (n - 1); return add(c, [r * Math.cos(t), r * Math.sin(t)]) }))
  }
  const fixAngle = (a: number) => (a > Math.PI / 2 + Math.PI / 12 ? a - Math.PI : a <= -Math.PI / 2 + Math.PI / 12 ? a + Math.PI : a)
  if (d.kind === 'DISTANCE' || d.kind === 'DISTANCEX' || d.kind === 'DISTANCEY') {
    const [p1, p2] = d.pts, length = d.param1, length2 = d.param2
    let dir: XY = d.kind === 'DISTANCE' ? sub(p2, p1) : d.kind === 'DISTANCEX' ? [p2[0] - p1[0] >= 1.19e-7 ? 1 : -1, 0] : [0, p2[1] - p1[1] >= 1.19e-7 ? 1 : -1]
    dir = norm2(dir)
    const normal: XY = [-dir[1], dir[0]]
    const normproj = dotp(sub(p2, p1), normal), p1_ = add(p1, mul(normal, normproj))
    const midpos = mul(add(p1_, p2), 0.5)
    textAngle = fixAngle(Math.atan2(dir[1], dir[0]))
    textAt = add(add(midpos, mul(normal, length)), mul(dir, length2))
    const margin = imgHeight / 3
    const off1 = (length + normproj < 0 ? -1 : 1) * margin, off2 = (length < 0 ? -1 : 1) * margin
    const perp1 = add(p1_, mul(normal, length + off1)), perp2 = add(p2, mul(normal, length + off2))
    const par1 = add(p1_, mul(normal, length))
    let par2 = add(add(midpos, mul(normal, length)), mul(dir, length2 - imgWidth / 2 - margin))
    let par3 = add(add(midpos, mul(normal, length)), mul(dir, length2 + imgWidth / 2 + margin))
    const par4 = add(p2, mul(normal, length))
    let flip = false
    if (dotp(sub(par3, par1), dir) > lenv(sub(par4, par1))) {
      const tmp = imgHeight / 0.75
      par3 = par4
      if (dotp(sub(par2, par1), dir) > lenv(sub(par4, par1))) { par3 = par2; par2 = sub(par1, mul(dir, tmp)); flip = true }
    } else if (dotp(sub(par2, par1), dir) < 0) {
      const tmp = imgHeight / 0.75
      par2 = par1
      if (dotp(sub(par3, par1), dir) < 0) { par2 = par3; par3 = add(par4, mul(dir, tmp)); flip = true }
    }
    const aw = margin * 0.5
    let ar1 = add(par1, mul(dir, (flip ? -1 : 1) * 0.866 * 2 * margin)), ar2 = add(ar1, mul(normal, aw)); ar1 = sub(ar1, mul(normal, aw))
    let ar3 = sub(par4, mul(dir, (flip ? -1 : 1) * 0.866 * 2 * margin)), ar4 = add(ar3, mul(normal, aw)); ar3 = sub(ar3, mul(normal, aw))
    if (length !== 0) { lines.push([p1, perp1], [p2, perp2]) }
    lines.push([par1, par2], [par3, par4])
    tris.push([par1, ar1, ar2], [par4, ar3, ar4])
    if (d.ext) lines.push(d.ext)
  } else if (d.kind === 'RADIUS' || d.kind === 'DIAMETER') {
    let [p1, p2] = d.pts
    const dia = d.kind === 'DIAMETER', dir = norm2(sub(p2, p1)), normal: XY = [-dir[1], dir[0]]
    const radius = lenv(sub(p2, p1)) / (dia ? 2 : 1), center = dia ? mul(add(p1, p2), 0.5) : p1
    const pos = add(p2, mul(dir, d.param1))
    textAngle = fixAngle(Math.atan2(dir[1], dir[0]))
    textAt = pos
    const margin = imgHeight / 3, aw = margin * 0.5
    const ar0 = p2
    let ar1 = sub(p2, mul(dir, 0.866 * 2 * margin)); const ar2 = add(ar1, mul(normal, aw)); ar1 = sub(ar1, mul(normal, aw))
    const p3 = add(pos, mul(dir, imgWidth / 2 + margin))
    if (lenv(sub(p3, p1)) > lenv(sub(p2, p1))) p2 = p3
    const pnt1 = sub(pos, mul(dir, margin + imgWidth / 2)), pnt2 = add(pos, mul(dir, margin + imgWidth / 2))
    lines.push([p1, pnt1], [pnt2, p2])
    tris.push([ar0, ar1, ar2])
    if (dia) { let b1 = add(p1, mul(dir, 0.866 * 2 * margin)); const b2 = add(b1, mul(normal, aw)); b1 = sub(b1, mul(normal, aw)); tris.push([p1, b1, b2]) }
    if (d.param4) arc(center, radius, d.param3!, d.param3! + d.param4)
    if (d.param6) arc(center, radius, d.param5!, d.param5! + d.param6)
  } else if (d.kind === 'ANGLE') {
    const p0 = d.pts[0], margin = imgHeight / 3, length = d.param1, start = d.param2, range = d.param3!
    const end = start + range
    const el1 = Math.max(d.param4!, margin), el2 = Math.max(d.param5!, margin), el12 = Math.max(-d.param4!, margin), el22 = Math.max(-d.param5!, margin)
    const r = 2 * length
    let textMargin = Math.min(0.2 * Math.abs(range), imgWidth / (2 * r))
    const mid = start + 0.5 * range
    textAt = add(p0, mul([Math.cos(mid), Math.sin(mid)], r))
    textAngle = 0
    let v1: XY = [Math.cos(start), Math.sin(start)], v2: XY = [Math.cos(end), Math.sin(end)]
    if (range < 0 || length < 0) { [v1, v2] = [v2, v1]; textMargin = -textMargin }
    arc(p0, r, start, start + range / 2 - textMargin)
    arc(p0, r, start + range / 2 + textMargin, end)
    lines.push([add(p0, mul(v1, r - el1)), add(p0, mul(v1, r + el12))], [add(p0, mul(v2, r - el2)), add(p0, mul(v2, r + el22))])
    const al = margin * 2, aw = margin * 0.5
    const arrow = (base: XY, dirv: XY) => { const u = norm2(dirv), n: XY = [u[1], -u[0]]; tris.push([base, add(sub(base, mul(u, al)), mul(n, aw)), sub(sub(base, mul(u, al)), mul(n, aw))]) }
    arrow(add(p0, mul(v1, r)), [v1[1], -v1[0]])
    arrow(add(p0, mul(v2, r)), [-v2[1], v2[0]])
  } else if (d.kind === 'SYMMETRIC') {
    const [p1, p2] = d.pts, dir = norm2(sub(p2, p1)), normal: XY = [-dir[1], dir[0]], margin = imgHeight / 4
    const ar0 = add(p1, mul(dir, 4 * margin)); let ar1 = sub(ar0, mul(dir, 0.866 * 2 * margin)); const ar2 = add(ar1, mul(normal, margin)); ar1 = sub(ar1, mul(normal, margin))
    const ar3 = sub(p2, mul(dir, 4 * margin)); let ar4 = add(ar3, mul(dir, 0.866 * 2 * margin)); const ar5 = add(ar4, mul(normal, margin)); ar4 = sub(ar4, mul(normal, margin))
    lines.push([p1, ar0], [p2, ar3], [ar0, ar1], [ar0, ar2], [ar3, ar4], [ar3, ar5])
  }
  for (const l of lines) strokePoly(ctx, s, l, color, lineWidth)
  for (const t of tris) fillTri(ctx, s, t[0], t[1], t[2], color)
  if (hits) hits.datumLines.push(...lines.map((l) => ({ pts: l.map((p) => s.toScreen(p)), id })))
  if (textAt && d.text) {
    const [x, y] = s.toScreen(textAt)
    // the text's direction on the screen, kept upright (SoDatumLabel::ensureCoinText flips past 105°)
    const e = s.toScreen(add(textAt, [Math.cos(textAngle), Math.sin(textAngle)]))
    let a = Math.atan2(e[1] - y, e[0] - x)
    if (Math.abs(a) > (105 * Math.PI) / 180) a += Math.PI
    ctx.translate(x, y)
    ctx.rotate(a)
    if (opts.box) { ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fillRect(-textW / 2 - 2, -textH / 2, textW + 4, textH) }
    ctx.fillStyle = color
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(d.text, 0, 0)
    if (opts.strike) { ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(-textW / 2, 0); ctx.lineTo(textW / 2, 0); ctx.stroke() }
    if (hits) hits.labels.push({ x, y, w: textW, h: textH, angle: a, id })
  }
  ctx.restore()
}
export const labelFont = () => `${SIZES.font}px ${getComputedStyle(document.body).fontFamily || 'sans-serif'}`

/** The whole edit mode drawing, in Coin's layer order: grid, axes, curves, points, constraints, edit curves, text. */
/** What draws over the curves, in the information layer's place (sketchbsplineinfo.ts registers here). */
export const overlays: ((ctx: Ctx, s: Screen, st: DrawState) => void)[] = []
export function drawSketch(ctx: Ctx, s: Screen, st: DrawState, camCenter: XY): HitRegions {
  const hits: HitRegions = { icons: [], labels: [], datumLines: [] }
  ctx.clearRect(0, 0, s.w, s.h)
  ctx.save()
  if (s.hole) { // leave the NaviCube's square alone
    ctx.beginPath(); ctx.rect(0, 0, s.w, s.h); ctx.rect(s.hole.x + s.hole.w, s.hole.y, -s.hole.w, s.hole.h); ctx.clip('evenodd')
  }
  if (st.showGrid) drawGrid(ctx, s, st, camCenter)
  // the axes across the whole viewport (ViewProviderSketch::onCameraChanged / updateAxesLength)
  const span = 2 * Math.max(s.w, s.h) * s.worldPerPx
  const axis = (g: number, a: XY, b: XY, base: string) => {
    const color = st.selection.curves.has(g) ? COLORS.select : st.preselect.cross === (g === H_AXIS ? 1 : 2) ? COLORS.preselect : base
    strokePoly(ctx, s, [a, b], color, SIZES.axis, [], SIZES.axisAlpha)
  }
  axis(H_AXIS, [camCenter[0] - span, 0], [camCenter[0] + span, 0], COLORS.axisH)
  axis(V_AXIS, [0, camCenter[1] - span], [0, camCenter[1] + span], COLORS.axisV)
  // curves
  st.geometry.forEach((g, i) => {
    if (g.type === 'Point' || (g.layer ?? 0) === 2) return   // a Hidden layer's geometry is not drawn
    const color = curveColor(st, i), cons = g.construction
    strokePoly(ctx, s, polyline(g), color, cons ? SIZES.construction : SIZES.curve, cons ? DASH : [])
  })
  // the information layer (EditModeInformationOverlayCoinConverter: a B-spline's degree, control polygon, comb, ...)
  for (const o of overlays) o(ctx, s, st)
  // the external geometry: ExternalWidth, ExternalPattern (CurvesExternalDrawStyle)
  ;(st.external ?? []).forEach((g, k) => {
    if (g.type === 'Point') return
    strokePoly(ctx, s, polyline(g), curveColor(st, -3 - k), SIZES.external, DASH)
  })
  // constraints: datum labels, then icons over them
  const font = labelFont()
  st.constraints.forEach((c, i) => {
    if (st.hiddenConstraints.has(i)) return
    if (!isDimensional(c) && c.type !== 'Symmetric') return
    const d = datumOf(st.geometry, c)
    if (!d) return
    const color = st.preselect.constraints.includes(i) ? COLORS.preselect : st.selection.constraints.has(i) ? COLORS.select
      : !c.active ? COLORS.deactivated : c.expr ? COLORS.exprBased : !c.driving ? COLORS.nonDriving : COLORS.constrDim
    drawDatum(ctx, s, d, color, c.type === 'Symmetric' ? 1 : SIZES.dimension, font, hits, i, { strike: !c.active })
  })
  drawIcons(ctx, s, st, hits)
  // points, over the curves (zHighPoints)
  const verts = vertices(st.geometry)
  verts.forEach(([g, pos], v) => {
    if ((st.geometry[g]?.layer ?? 0) === 2) return           // nor are its points
    const p = getPoint(st.geometry, g, pos)
    if (!p) return
    const [x, y] = s.toScreen(p)
    dot(ctx, x, y, SIZES.marker, pointColor(st, v, g, pos))
  })
  // the root point (OriginPointMaterial: FullyConstraintElementColor, preselected or selected)
  {
    const [x, y] = s.toScreen([0, 0])
    const color = st.selection.points.has(-1) ? COLORS.select : st.preselect.cross === 0 ? COLORS.preselect : COLORS.fullyElement
    dot(ctx, x, y, SIZES.marker, color)
  }
  // the tool's edit curves and hints
  for (const c of st.editCurves) strokePoly(ctx, s, c, st.editConstruction ? COLORS.construction : COLORS.curve, SIZES.editCurve, st.editConstruction ? DASH : [])
  for (const m of st.editMarkers) { const [x, y] = s.toScreen(m); dot(ctx, x, y, SIZES.pointSize, COLORS.curve, true) }
  if (st.extensionHint) strokePoly(ctx, s, st.extensionHint, COLORS.curve, 1, [4, 4])
  st.directionHints.lines.forEach((l, i) => strokePoly(ctx, s, l, COLORS.curve, 1, i === st.directionHints.active ? [] : [4, 4], 0.6))
  for (const o of st.ovps) {
    const d: Datum = { kind: o.kind, pts: o.pts, text: o.text, param1: o.param1, param2: o.param2 ?? 0, param3: o.param3 }
    drawDatum(ctx, s, d, o.focus ? COLORS.constrDim : COLORS.deactivated, SIZES.dimension, font, null, -1, { box: true })
  }
  if (st.positionText) { // SoText2 at the cursor, CursorTextColor, coinFontSize pixels
    const [x, y] = s.toScreen(st.positionText.at)
    ctx.font = `${SIZES.font}px ${getComputedStyle(document.body).fontFamily || 'sans-serif'}`
    ctx.fillStyle = COLORS.cursorText
    ctx.textBaseline = 'bottom'
    ctx.fillText(st.positionText.text, x + 2, y - 2)
  }
  if (st.rubber) { // Gui::Rubberband::paintGL: white at half opacity, a 4 px outline, dashed (0xAAAA × 3) right to left
    const { a, b } = st.rubber, touch = b[0] < a[0]
    const x = Math.min(a[0], b[0]), y = Math.min(a[1], b[1]), w = Math.abs(b[0] - a[0]), h = Math.abs(b[1] - a[1])
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)'
    ctx.fillRect(x, y, w, h)
    // StyleParameters.h: SketcherRubberbandTouchSelectionColor (0, 1, 0), SketcherRubberbandWindowSelectionColor (0, 0.4, 1)
    ctx.strokeStyle = touch ? 'rgb(0, 255, 0)' : 'rgb(0, 102, 255)'
    ctx.setLineDash(touch ? [3, 3] : [])
    ctx.lineWidth = 4
    ctx.strokeRect(x, y, w, h)
  }
  ctx.restore()
  return hits
}
