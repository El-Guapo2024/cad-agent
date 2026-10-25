// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/PartDesign/Gui/CommandPrimitive.cpp: 2015 Stefan Tröger
//   src/Mod/PartDesign/Gui/TaskTransformedParameters.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/Gui/TaskMirroredParameters.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/Gui/TaskPatternParameters.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/Gui/TaskMultiTransformParameters.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/Gui/TaskScaledParameters.cpp, ViewProviderScaled.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/App/FeatureScaled.cpp, FeatureMultiTransform.cpp: 2012 Jan Rheinländer (the preview's scalings)
//   src/Mod/PartDesign/Gui/ViewProviderTransformed.cpp: 2012 Jan Rheinländer
//   src/Mod/PartDesign/Gui/TaskPrimitiveParameters.cpp: 2015 Stefan Tröger
//   src/Mod/Part/Gui/PatternParametersWidget.cpp: 2025 AstoCAD
//   src/Mod/Part/Gui/DlgPrimitives.cpp: 2007 Werner Mayer
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskTransformedParameters.ui,
//       src/Mod/PartDesign/Gui/TaskMirroredParameters.ui, src/Mod/PartDesign/Gui/TaskMultiTransformParameters.ui,
//       src/Mod/Part/Gui/PatternParametersWidget.ui, src/Mod/Part/Gui/DlgPrimitives.ui
// PartDesign's transformed features (Mirror, Linear Pattern, Polar Pattern, Multi-Transform) and its additive and subtractive
// primitives, in a Body whose shape is a FEATURES list (cad_agent/feature_transform.py, feature_primitive.py): the commands as
// FreeCAD runs them, their task panels with the preview overlay, the property view, the tree's icons and the menu entries.
// partdesign.tsx calls in here for these types; every edit is `cad feature` on the server, one undo step, as Pad's are.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import type { FeatureOp } from './api'
import { getState, report, setState, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView, showPanel } from './actions'
import type { IconName } from './icons'
import { cls, EditRow, Group, Row, TaskBox, propPad } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import { ContextMenu, type Entry } from './chrome'
import * as quantity from './quantity'
import './pd_transform.css'
import { AttachTask } from './pd_attach'
import type { PlacementData } from './attached'
import { applyOps, bodyOfPart, createBody, isBodyDoc, numberOf, PAD, POCKET, previewObject, refOf, SKETCH, sketchMatrix, splitRef, targetBody,
  type ExtrudeSpec } from './partdesign'

// ── the types ────────────────────────────────────────────────────────────────
export const MIRRORED = 'PartDesign::Mirrored', LINEAR = 'PartDesign::LinearPattern', POLAR = 'PartDesign::PolarPattern', MULTI = 'PartDesign::MultiTransform'
/** PartDesign::Scaled (cad_agent/feature_scaled.py). FreeCAD 26.3 does not register PartDesign_Scaled (Command.cpp has it
 *  commented out): a Scaled comes from Multi-Transform's Add Scale Transformation, or from the code. */
export const SCALED = 'PartDesign::Scaled'
/** Each transformed feature: its kind (the part file's call), the command's menu text and pixmap, the name FreeCAD gives a new
 *  one (getUniqueObjectName(which)) and a MultiTransform's transformation of the kind (onTransformAdd…'s names). */
const TRANSFORMED: Record<string, { kind: string; label: string; icon: IconName; cmd: string; sub: string; panel: string }> = {
  [MIRRORED]: { kind: 'Mirrored', label: 'Mirror', icon: 'pd-mirrored', cmd: 'PartDesign_Mirrored', sub: 'Mirror', panel: 'Mirror Parameters' },
  [LINEAR]: { kind: 'LinearPattern', label: 'Linear Pattern', icon: 'pd-linear-pattern', cmd: 'PartDesign_LinearPattern', sub: 'Linear_Pattern', panel: 'Linear Pattern Parameters' },
  [POLAR]: { kind: 'PolarPattern', label: 'Polar Pattern', icon: 'pd-polar-pattern', cmd: 'PartDesign_PolarPattern', sub: 'Polar_Pattern', panel: 'Polar Pattern Parameters' },
  [MULTI]: { kind: 'MultiTransform', label: 'Multi-Transform', icon: 'pd-multi-transform', cmd: 'PartDesign_MultiTransform', sub: 'MultiTransform', panel: 'Multi-Transform Parameters' },
  [SCALED]: { kind: 'Scaled', label: 'Scale', icon: 'pd-scaled', cmd: 'PartDesign_Scaled', sub: 'Scale', panel: 'Scale Parameters' },
}
export const SHAPES = ['Box', 'Cylinder', 'Sphere', 'Cone', 'Ellipsoid', 'Torus', 'Prism', 'Wedge'] as const
type Shape = (typeof SHAPES)[number]
type Side = 'Additive' | 'Subtractive'
const PRIM = /^PartDesign::(Additive|Subtractive)(Box|Cylinder|Sphere|Cone|Ellipsoid|Torus|Prism|Wedge)$/
const primOf = (type: string): [Side, Shape] | null => { const m = PRIM.exec(type); return m ? [m[1] as Side, m[2] as Shape] : null }
export const isTransformed = (type: string) => type in TRANSFORMED
export const isPrimitive = (type: string) => PRIM.test(type)
/** Whether partdesign.tsx hands a feature of this type to this module. */
export const isPdx = (type: string) => isTransformed(type) || isPrimitive(type)
const primIcon = (side: Side, shape: Shape) => `pd-${side === 'Additive' ? 'add' : 'sub'}-${shape.toLowerCase()}` as IconName
/** The tree's icon (ViewProviderTransformed::featureIcon, ViewProviderPrimitive's PartDesign_<Additive|Subtractive><Shape>). */
export function pdxIcon(type: string): IconName | undefined {
  if (TRANSFORMED[type]) return TRANSFORMED[type].icon
  const p = primOf(type)
  return p ? primIcon(...p) : undefined
}
export function pdxKind(type: string): string | undefined {
  return TRANSFORMED[type]?.kind ?? (primOf(type) ? type.slice('PartDesign::'.length) : undefined)
}
/** ViewProviderMultiTransform::claimChildren: a MultiTransform shows its transformations under it. */
export function pdxChildren(f: Feature): Feature[] {
  return f.type === MULTI && Array.isArray(f.transformations) ? (f.transformations as Feature[]) : []
}
/** A feature of the Body by name, a MultiTransform's transformation too; with the MultiTransform that holds it. */
export function findFeature(doc: FeatureDoc | undefined, name: string): Feature | undefined {
  return doc ? (doc.features.find((f) => f.name === name) ?? holderOf(doc, name)?.[1]) : undefined
}
function holderOf(doc: FeatureDoc, name: string): [Feature, Feature] | undefined {
  for (const f of doc.features) { const t = pdxChildren(f).find((x) => x.name === name); if (t) return [f, t] }
  return undefined
}
const allNames = (doc: FeatureDoc) => new Set(doc.features.flatMap((f) => [f.name, ...pdxChildren(f).map((t) => t.name)]))
/** Document::getUniqueObjectName: the name, else with 001, 002, … */
function uniqueName(taken: Set<string>, base: string) {
  if (!taken.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!taken.has(n)) return n }
}
const NO_BODY = 'In order to use PartDesign you need an active Body object in the document. Please make one active (double click) '
  + 'or create one.\n\nIf you have a legacy document with PartDesign objects without Body, use the migrate function in PartDesign '
  + 'to put them into a Body.'
const lastSolid = (doc: FeatureDoc) => doc.tip ?? [...doc.features].reverse().find((f) => f.type !== SKETCH)?.name ?? doc.features[doc.features.length - 1]?.name ?? null
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x))

// ── references (PropertyLinkSub: a name, or [name, sub]) ──────────────────────
type Ref = string | [string, string] | null
const refName = (r: Ref | undefined) => (r == null ? null : typeof r === 'string' ? r : r[0])
const refSub = (r: Ref | undefined) => (r == null || typeof r === 'string' ? '' : r[1])
const sameRef = (a: Ref, b: Ref) => refName(a) === refName(b) && refSub(a) === refSub(b)
const refText = (r: Ref) => (r === null ? '' : refSub(r) ? `${refName(r)} [${refSub(r)}]` : `${refName(r)}`)
/** Transformed::getSketchObject: the first original's profile sketch; for a pattern of something else, its direction's sketch. */
function sketchOf(doc: FeatureDoc, f: Feature): Feature | undefined {
  const first = findFeature(doc, String((f.originals as string[] | undefined)?.[0] ?? ''))
  if (first && (first.type === PAD || first.type === POCKET)) return doc.features.find((x) => x.name === first.profile && x.type === SKETCH)
  if (first) return undefined
  const r = (f.type === LINEAR ? f.direction : f.type === POLAR ? f.axis : f.type === MIRRORED ? f.mirror_plane : null) as Ref
  const sk = refName(r) ? doc.features.find((x) => x.name === refName(r) && x.type === SKETCH) : undefined
  return sk
}
const constructionLines = (sk: Feature | undefined) => (sk?.geometry ?? []).filter((g: any) => g?.type === 'LineSegment' && g.construction)
type Item = { label: string; ref: Ref }
/** TaskTransformedParameters::fillAxisCombo: the sketch's axes and construction lines, the Origin's axes, Select reference…. */
function axisItems(sk: Feature | undefined): Item[] {
  const out: Item[] = []
  if (sk) {
    out.push({ label: 'Horizontal sketch axis', ref: [sk.name, 'H_Axis'] }, { label: 'Vertical sketch axis', ref: [sk.name, 'V_Axis'] }, { label: 'Normal sketch axis', ref: [sk.name, 'N_Axis'] })
    constructionLines(sk).forEach((_, i) => out.push({ label: `Construction line ${i + 1}`, ref: [sk.name, `Axis${i}`] }))
  }
  out.push({ label: 'Base X-axis', ref: 'X_Axis' }, { label: 'Base Y-axis', ref: 'Y_Axis' }, { label: 'Base Z-axis', ref: 'Z_Axis' })
  return out
}
/** TaskTransformedParameters::fillPlanesCombo: the sketch's V and H axes (the planes through them and its normal), its
 *  construction lines, the Origin's planes, Select reference…. */
function planeItems(sk: Feature | undefined): Item[] {
  const out: Item[] = []
  if (sk) {
    out.push({ label: 'Vertical sketch axis', ref: [sk.name, 'V_Axis'] }, { label: 'Horizontal sketch axis', ref: [sk.name, 'H_Axis'] })
    constructionLines(sk).forEach((_, i) => out.push({ label: `Construction line ${i + 1}`, ref: [sk.name, `Axis${i}`] }))
  }
  out.push({ label: 'Base XY-plane', ref: 'XY_Plane' }, { label: 'Base YZ-plane', ref: 'YZ_Plane' }, { label: 'Base XZ-plane', ref: 'XZ_Plane' })
  return out
}
const SELECT_REF = 'Select reference…'

// ── the commands (Command.cpp's prepareTransformed and workers, CommandPrimitive.cpp) ──
function bodyOrWarn(): string | null {
  const part = targetBody()
  if (!part) void messageBox('warning', 'No active body', NO_BODY)
  return part
}
/** What a new transformed feature starts with: FreeCAD's object defaults, the originals selected (none: Transform body,
 *  "TransformMode = Whole shape"), and what the command's worker sets (the plane, direction or axis from the first original's
 *  sketch, else the Origin's; LinearPattern Length 100, Occurrences 2; PolarPattern Angle 360, Occurrences 2). */
function newTransformed(doc: FeatureDoc, type: string, originals: string[]): Feature {
  const f: Feature = { name: '', type, originals, transform_mode: originals.length ? 'Features' : 'Whole shape', refine: true, suppressed_indices: [] }
  const sk = sketchOf(doc, f)
  if (type === MIRRORED) f.mirror_plane = sk ? [sk.name, 'V_Axis'] : 'XY_Plane'
  if (type === LINEAR) Object.assign(f, LINEAR_DEFAULTS, { direction: sk ? [sk.name, 'H_Axis'] : 'X_Axis', direction2: sk ? [sk.name, 'V_Axis'] : 'Y_Axis', length: 100, occurrences: 2 })
  if (type === POLAR) Object.assign(f, POLAR_DEFAULTS, { axis: sk ? [sk.name, 'N_Axis'] : 'Z_Axis', angle: 360, occurrences: 2 })
  if (type === MULTI) f.transformations = []
  if (type === SCALED) Object.assign(f, { factor: 2, occurrences: 2 })     // onTransformAddScaled: Factor = 2, Occurrences = 2
  return f
}
const LINEAR_DEFAULTS = { direction: null, reversed: false, mode: 'Extent', length: 100, offset: 10, spacings: [-1], spacing_pattern: [0], occurrences: 2,
  direction2: null, reversed2: false, mode2: 'Extent', length2: 100, offset2: 10, spacings2: [0], spacing_pattern2: [0], occurrences2: 1 }
const POLAR_DEFAULTS = { axis: null, reversed: false, mode: 'Extent', angle: 360, offset: 120, spacings: [-1, -1, -1], spacing_pattern: [0], occurrences: 3 }

/** PartDesign_Mirrored, _LinearPattern, _PolarPattern, _MultiTransform: the selected features of the active Body are the
 *  originals; the task panel opens on the new feature, which OK makes ("Make Mirrored"). Multi-Transform with a transformed
 *  feature selected converts it instead ("Convert to Multi-Transform feature"). */
export async function makeTransformed(type: string) {
  const s = getState()
  const part = bodyOrWarn()
  if (!part) return
  const doc = s.features[part]
  const sel = s.featSel.map(splitRef).filter(([, n]) => n)
  if (sel.some(([p]) => p !== part)) { await messageBox('warning', 'Selection is not in the active body', 'Select only one feature in an active body.'); return }
  const picked = sel.map(([, n]) => doc.features.find((f) => f.name === n)).filter((f): f is Feature => !!f && f.type !== SKETCH)
  if (type === MULTI) {
    const tr = picked.find((f) => isTransformed(f.type) && f.type !== MULTI)
    if (tr) return convertToMulti(part, doc, tr)
  }
  setState({ task: { kind: 'pdTransform', body: part, other: `${type}|${picked.map((f) => f.name).join(',')}` } })
  showPanel('tasks')
}
/** CmdPartDesignMultiTransform with a Mirrored, LinearPattern or PolarPattern selected: a MultiTransform in its place, with
 *  its originals and transform mode, holding it as its one transformation. Then its panel opens. */
async function convertToMulti(part: string, doc: FeatureDoc, tr: Feature) {
  const name = uniqueName(allNames(doc), 'MultiTransform')
  const i = doc.features.findIndex((f) => f.name === tr.name)
  const after = i > 0 ? doc.features[i - 1].name : null
  const sub: Feature = { ...clone(tr), originals: [], transform_mode: 'Features' }
  const mt: Feature = { name, type: MULTI, originals: tr.originals, transform_mode: tr.transform_mode, refine: tr.refine, suppressed_indices: [], transformations: [sub] }
  const ops: FeatureOp[] = [{ op: 'delete', name: tr.name }, { op: 'add', feature: mt, after }]
  if (doc.tip === tr.name) ops.push({ op: 'tip', name })
  const done = await applyOps(part, ops, { name: 'Convert to Multi-Transform feature' })
  if (!done) return
  setState({ featSel: [refOf(part, name)], selected: [], task: { kind: 'pdTransform', body: part, other: name, edit: true } })
  showPanel('tasks')
}
/** PartDesign_CompPrimitiveAdditive / _Subtractive's actions: a new primitive of the shape opens its panel; OK makes it
 *  ("Make additive Box"). An additive one in a document with no Body makes the Body first, as FreeCAD does. */
export async function makePrimitive(side: Side, shape: Shape) {
  const s = getState()
  let part = targetBody()
  if (!part) {
    const bodies = Object.keys(s.features).filter((p) => isBodyDoc(s.features[p]))
    if (side === 'Subtractive' || bodies.length) { await messageBox('warning', 'No active body', NO_BODY); return }
    await createBody()
    part = getState().activeBody
    if (!part) return
  }
  setState({ task: { kind: 'pdPrimitive', body: part, other: `PartDesign::${side}${shape}` } })
  showPanel('tasks')
}
/** Std_Edit / a double-click: the feature's panel ("Edit Mirrored"); a MultiTransform's transformation opens the
 *  MultiTransform's (ViewProviderTransformed::startEditing). */
export function editPdx(part: string, name: string) {
  const doc = getState().features[part]
  const holder = doc && holderOf(doc, name)
  const f = holder ? holder[0] : findFeature(doc, name)
  if (!f) return
  setState({ task: { kind: isPrimitive(f.type) ? 'pdPrimitive' : 'pdTransform', body: part, other: f.name, edit: true } })
  showPanel('tasks')
}

// ── the transformations, in the browser: the preview overlay (ViewProviderTransformed::updatePreview) ──
const ORIGIN_DIR: Record<string, [number, number, number]> = { X_Axis: [1, 0, 0], Y_Axis: [0, 1, 0], Z_Axis: [0, 0, 1], XY_Plane: [0, 0, 1], XZ_Plane: [0, -1, 0], YZ_Plane: [1, 0, 0] }
const V = (a: number[]) => new THREE.Vector3(a[0], a[1], a[2])
type Axis = { p: THREE.Vector3; d: THREE.Vector3 }
/** A sketch's axis in the Body's frame (Part2DObject::getAxis times its Placement); a construction line's from its start. */
function sketchAxis(sk: Feature, sub: string): Axis | null {
  const m = sketchMatrix(sk)
  const o = new THREE.Vector3().applyMatrix4(m)
  const dir = (v: THREE.Vector3) => v.clone().transformDirection(m)
  if (sub === 'H_Axis') return { p: o, d: dir(V([1, 0, 0])) }
  if (sub === 'V_Axis') return { p: o, d: dir(V([0, 1, 0])) }
  if (sub === 'N_Axis' || sub === '') return { p: o, d: dir(V([0, 0, 1])) }
  const k = /^Axis(\d+)$/.exec(sub)
  const g = k ? constructionLines(sk)[Number(k[1])] as any : null
  if (!g) return null
  const a = V([g.start[0], g.start[1], 0]).applyMatrix4(m), b = V([g.end[0], g.end[1], 0]).applyMatrix4(m)
  return { p: a, d: b.clone().sub(a) }
}
/** A face's plane or an edge's line of what the 3D view draws for the Tip, from its tessellation. */
function elementAxis(sub: string): Axis | null {
  const v = getView(), s = getState()
  const body = s.scene?.bodies.find((b) => b.part && s.features[b.part])
  const g = v && body ? v.subGeometry(`${body.name}.${sub}`) : null
  if (!g) return null
  if (g.kind === 'Face' && g.tris.length) {
    const [a, b, c] = g.tris[0]
    return { p: a.clone(), d: b.clone().sub(a).cross(c.clone().sub(a)).normalize() }
  }
  if (g.kind === 'Edge' && g.segs.length) { const seg = g.segs[0]; return { p: seg[0].clone(), d: seg[seg.length - 1].clone().sub(seg[0]).normalize() } }
  return null
}
function refAxis(doc: FeatureDoc, r: Ref, plane: boolean): Axis | null {
  const n = refName(r), sub = refSub(r)
  if (!n) return null
  if (ORIGIN_DIR[n]) return { p: new THREE.Vector3(), d: V(ORIGIN_DIR[n]) }
  const sk = doc.features.find((x) => x.name === n && x.type === SKETCH)
  if (sk) {
    if (!plane) return sketchAxis(sk, sub)
    // Mirrored's axisOfSketch: H_Axis mirrors in the plane normal to V, V_Axis in the one normal to H, a line in the plane through it
    if (sub === 'H_Axis') return sketchAxis(sk, 'V_Axis')
    if (sub === 'V_Axis') return sketchAxis(sk, 'H_Axis')
    if (sub === '') return sketchAxis(sk, 'N_Axis')
    const a = sketchAxis(sk, sub)
    if (!a) return null
    const n2 = V([0, 0, 1]).transformDirection(sketchMatrix(sk))
    return { p: a.p.clone().addScaledVector(a.d, 0.5), d: n2.cross(a.d).normalize() }
  }
  return n === doc.tip ? elementAxis(sub) : null
}
const num = (doc: FeatureDoc, v: unknown, d: number) => numberOf(v, doc.params) ?? d
/** Scaled::getTransformations: the identity, then the scalings about centre by 1 + i (Factor - 1) / (Occurrences - 1). */
function scalings(doc: FeatureDoc, f: Feature, centre: THREE.Vector3): THREE.Matrix4[] {
  const factor = num(doc, f.factor, 2), occ = Math.round(num(doc, f.occurrences, 2))
  if (factor < 1e-7 || occ < 2) return [new THREE.Matrix4()]
  const step = (factor - 1) / (occ - 1)
  return Array.from({ length: occ }, (_, i) => scaleAbout(centre, 1 + i * step))
}
const scaleAbout = (c: THREE.Vector3, k: number) => new THREE.Matrix4().makeTranslation(c.x, c.y, c.z)
  .multiply(new THREE.Matrix4().makeScale(k, k, k)).multiply(new THREE.Matrix4().makeTranslation(-c.x, -c.y, -c.z))
/** Transformed::getTransformations in the browser, for the preview: null when a reference cannot be resolved here. centre is
 *  the first original's centre (the centre of its tool's box here; FreeCAD takes its centre of mass), which a Scaled scales
 *  about. */
function transformsOf(doc: FeatureDoc, f: Feature, centre = new THREE.Vector3()): THREE.Matrix4[] | null {
  if (f.type === SCALED) return scalings(doc, f, centre)
  if (f.type === MIRRORED) {
    const a = refAxis(doc, f.mirror_plane as Ref, true)
    if (!a) return null
    const n = a.d.clone().normalize(), m = new THREE.Matrix4()
    const k = 2 * a.p.dot(n)
    m.set(1 - 2 * n.x * n.x, -2 * n.x * n.y, -2 * n.x * n.z, k * n.x, -2 * n.y * n.x, 1 - 2 * n.y * n.y, -2 * n.y * n.z, k * n.y,
      -2 * n.z * n.x, -2 * n.z * n.y, 1 - 2 * n.z * n.z, k * n.z, 0, 0, 0, 1)
    return [new THREE.Matrix4(), m]
  }
  if (f.type === LINEAR) {
    const steps = (s: '' | '2') => {
      const occ = Math.round(num(doc, f[`occurrences${s}`], s ? 1 : 2))
      if (occ <= 1) return [new THREE.Vector3()]
      const r = f[`direction${s}`] as Ref
      const off = num(doc, f[`offset${s}`], 10)
      const spacing = f[`mode${s}`] === 'Spacing'
      const a = r === null ? { p: new THREE.Vector3(), d: new THREE.Vector3() } : refAxis(doc, r, false)
      if (!a) return null
      let d = a.d.clone().normalize()
      if (f[`reversed${s}`]) d.negate()
      if (!spacing) d = d.multiplyScalar(num(doc, f[`length${s}`], 100) / (occ - 1))
      const sp = ((f[`spacings${s}`] as number[]) ?? []).map((x) => (x === off ? -1 : x))
      const pat = (f[`spacing_pattern${s}`] as number[]) ?? []
      const out = [new THREE.Vector3()]
      let total = 0
      for (let i = 1; i < occ; i++) {
        if (spacing) { total += sp[i - 1] !== undefined && sp[i - 1] !== -1 ? sp[i - 1] : pat.length > 1 ? pat[(i - 1) % pat.length] : off; out.push(d.clone().multiplyScalar(total)) }
        else out.push(d.clone().multiplyScalar(i))
      }
      return out
    }
    const a = steps(''), b = steps('2')
    if (!a || !b) return null
    return a.flatMap((x) => b.map((y) => new THREE.Matrix4().makeTranslation(x.x + y.x, x.y + y.y, x.z + y.z)))
  }
  if (f.type === POLAR) {
    const occ = Math.round(num(doc, f.occurrences, 3))
    if (occ <= 1) return [new THREE.Matrix4()]
    const a = f.axis === null || f.axis === undefined ? { p: new THREE.Vector3(), d: V([0, 0, 1]) } : refAxis(doc, f.axis as Ref, false)
    if (!a) return null
    const d = a.d.clone().normalize().multiplyScalar(f.reversed ? -1 : 1)
    const total = num(doc, f.angle, 360), off = num(doc, f.offset, 120)
    const step = Math.abs(total - 360) < 1e-7 ? total / occ : total / (occ - 1)
    const sp = ((f.spacings as number[]) ?? []).map((x) => (x === off ? -1 : x)), pat = (f.spacing_pattern as number[]) ?? []
    const out = [new THREE.Matrix4()]
    let acc = 0
    for (let i = 1; i < occ; i++) {
      acc = f.mode === 'Spacing' ? acc + (sp[i - 1] !== undefined && sp[i - 1] !== -1 ? sp[i - 1] : pat.length > 1 ? pat[(i - 1) % pat.length] : off) : step * i
      const r = new THREE.Matrix4().makeRotationAxis(d, THREE.MathUtils.degToRad(acc))
      out.push(new THREE.Matrix4().makeTranslation(a.p.x, a.p.y, a.p.z).multiply(r).multiply(new THREE.Matrix4().makeTranslation(-a.p.x, -a.p.y, -a.p.z)))
    }
    return out
  }
  if (f.type === MULTI) {
    // MultiTransform::getTransformations: each occurrence keeps its centre; a Scaled scales each slice of them about its own
    let inst: { m: THREE.Matrix4; c: THREE.Vector3 }[] | null = null
    for (const t of pdxChildren(f)) {
      const ts = transformsOf(doc, t, centre)
      if (!ts) return null
      if (inst === null) { inst = ts.map((m) => ({ m, c: centre.clone().applyMatrix4(m) })); continue }
      if (!inst.length) continue
      if (t.type === SCALED) {
        if (inst.length % ts.length) return null       // "Number of occurrences must be a divisor of previous number of occurrences"
        const step: number = inst.length / ts.length
        const old: { m: THREE.Matrix4; c: THREE.Vector3 }[] = inst
        inst = ts.flatMap((m, i) => old.slice(i * step, (i + 1) * step).map((o): { m: THREE.Matrix4; c: THREE.Vector3 } => {
          const k = new THREE.Vector3().setFromMatrixScale(m).x
          return { m: scaleAbout(o.c, k).multiply(o.m), c: o.c }
        }))
        continue
      }
      const old: { m: THREE.Matrix4; c: THREE.Vector3 }[] = inst
      inst = ts.flatMap((x) => old.map((o) => ({ m: x.clone().multiply(o.m), c: o.c.clone().applyMatrix4(x) })))
    }
    return inst ? inst.map((x) => x.m) : []
  }
  return null
}
const partMatrix = (doc: FeatureDoc) => { const b = bodyOfPart(getState(), doc.part), m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
/** A Pad's or Pocket's tool as partdesign.tsx previews it, or a primitive's shape: in the part's frame. */
function toolObject(doc: FeatureDoc, f: Feature): THREE.Object3D | null {
  if (f.type === PAD || f.type === POCKET) {
    const sk = doc.features.find((x) => x.name === f.profile && x.type === SKETCH)
    if (!sk) return null
    const spec: ExtrudeSpec = { kind: f.type === PAD ? 'pad' : 'pocket', side_type: String(f.side_type ?? 'One side'), type: String(f.type1 ?? 'Length'),
      length: num(doc, f.length, f.type === PAD ? 10 : 5), type2: String(f.type2 ?? 'Length'), length2: num(doc, f.length2, 10), reversed: f.reversed === true,
      offset: num(doc, f.offset, 0), start_type: String(f.start_type ?? 'Profile plane'), start_offset: num(doc, f.start_offset, 0) }
    const o = previewObject(spec, sk, bodyOfPart(getState(), doc.part))
    if (o) o.applyMatrix4(partMatrix(doc).invert())
    return o
  }
  if (isPrimitive(f.type)) return primitiveObject(doc, f)
  return null
}
const PREVIEW_ADD = new THREE.Color(0, 1, 0.6), PREVIEW_SUB = new THREE.Color(1, 0, 0)
function previewMesh(geo: THREE.BufferGeometry, additive: boolean) {
  const color = additive ? PREVIEW_ADD : PREVIEW_SUB
  const g = new THREE.Group()
  g.add(new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide })))
  g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 20), new THREE.LineBasicMaterial({ color })))
  return g
}
/** Placement ((x, y, z), (yaw, pitch, roll)) as App.Rotation(yaw, pitch, roll) reads it: Rz Ry Rx. */
function placementMatrix(p: unknown): THREE.Matrix4 {
  const m = new THREE.Matrix4()
  if (!Array.isArray(p) || p.length !== 2) return m
  const [pos, ypr] = p as number[][]
  m.makeRotationFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(ypr[2]), THREE.MathUtils.degToRad(ypr[1]), THREE.MathUtils.degToRad(ypr[0]), 'ZYX'))
  m.setPosition(pos[0], pos[1], pos[2])
  return m
}
/** A primitive's shape for the preview (FeaturePrimitive's AddSubShape, as three.js draws it: the skew angles and a
 *  torus's or sphere's V range are left out), placed. */
function primitiveObject(doc: FeatureDoc, f: Feature): THREE.Object3D | null {
  const p = primOf(f.type)
  if (!p) return null
  const n = (k: string) => num(doc, f[k], PRIM_DEFAULTS[p[1]][k] as number)
  const rad = THREE.MathUtils.degToRad
  const upZ = (g: THREE.BufferGeometry) => g.rotateX(Math.PI / 2)
  let geo: THREE.BufferGeometry
  switch (p[1]) {
    case 'Box': geo = new THREE.BoxGeometry(n('length'), n('width'), n('height')).translate(n('length') / 2, n('width') / 2, n('height') / 2); break
    case 'Cylinder': geo = upZ(new THREE.CylinderGeometry(n('radius'), n('radius'), n('height'), 48, 1, false, 0, rad(n('angle')))).translate(0, 0, n('height') / 2); break
    case 'Cone': geo = upZ(new THREE.CylinderGeometry(n('radius2'), n('radius1'), n('height'), 48, 1, false, 0, rad(n('angle')))).translate(0, 0, n('height') / 2); break
    case 'Sphere': geo = upZ(new THREE.SphereGeometry(n('radius'), 48, 24, 0, rad(n('angle3')), rad(90 - n('angle2')), rad(n('angle2') - n('angle1')))); break
    case 'Ellipsoid': {
      const r2 = n('radius2'), r3 = n('radius3') >= 1e-7 ? n('radius3') : r2
      geo = upZ(new THREE.SphereGeometry(1, 48, 24, 0, rad(n('angle3')), rad(90 - n('angle2')), rad(n('angle2') - n('angle1')))).scale(r2, r3, n('radius1')); break
    }
    case 'Torus': geo = new THREE.TorusGeometry(n('radius1'), n('radius2'), 24, 64, rad(n('angle3'))); break
    case 'Prism': geo = upZ(new THREE.CylinderGeometry(n('circumradius'), n('circumradius'), n('height'), Math.max(3, Math.round(n('polygon'))))).rotateZ(Math.PI / 2).translate(0, 0, n('height') / 2); break
    case 'Wedge': {
      const [x0, y0, z0, x20, z20, x1, y1, z1, x21, z21] = ['xmin', 'ymin', 'zmin', 'x2min', 'z2min', 'xmax', 'ymax', 'zmax', 'x2max', 'z2max'].map(n)
      const v = [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [x20, y1, z20], [x21, y1, z20], [x21, y1, z21], [x20, y1, z21]]
      const quads = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]]
      const pos: number[] = []
      for (const [a, b, c, d] of quads) for (const i of [a, b, c, a, c, d]) pos.push(...v[i])
      geo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
      geo.computeVertexNormals()
      break
    }
  }
  const o = previewMesh(geo, p[0] === 'Additive')
  o.applyMatrix4(placementMatrix(f.placement))
  return o
}
/** The overlay: the originals' tools (or, in Transform body mode, the Body as the 3D view draws it) under each of the
 *  feature's transformations but the suppressed ones, as ViewProviderTransformed::updatePreview places its preview shape. */
function transformedPreview(doc: FeatureDoc, f: Feature): THREE.Object3D | null {
  const first = findFeature(doc, String((f.originals as string[] | undefined)?.[0] ?? ''))
  const firstTool = first ? toolObject(doc, first) : null
  const centre = firstTool ? new THREE.Box3().setFromObject(firstTool).getCenter(new THREE.Vector3()) : new THREE.Vector3()
  const ts = transformsOf(doc, f, centre)
  if (!ts) return null
  const toPart = partMatrix(doc)
  const base = new THREE.Group()
  if (f.transform_mode === 'Whole shape') {
    const v = getView(), body = bodyOfPart(getState(), doc.part)
    for (const mesh of (v && body ? v.bodyMeshes(body.name) : [])) {
      mesh.updateWorldMatrix(true, false)
      const g = mesh.geometry.clone().applyMatrix4(mesh.matrixWorld).applyMatrix4(toPart.clone().invert())
      base.add(previewMesh(g, true))
    }
  } else {
    for (const o of (f.originals as string[]) ?? []) { const t = findFeature(doc, o); const obj = t && toolObject(doc, t); if (obj) base.add(obj) }
  }
  if (!base.children.length) return null
  const suppressed = new Set((f.suppressed_indices as number[]) ?? [])
  const g = new THREE.Group()
  ts.forEach((m, i) => { if (suppressed.has(i)) return; const c = base.clone(); c.applyMatrix4(m); g.add(c) })
  g.applyMatrix4(toPart)
  return g
}

// ── the task panels ──────────────────────────────────────────────────────────
function OkCancel({ onOk, onCancel }: { onOk(): void; onCancel(): void }) {
  return <div className="tbuttons pd-buttons"><button className="qbtn default" onClick={onOk}>OK</button><button className="qbtn" onClick={onCancel}>Cancel</button></div>
}
/** Gui::UIntSpinBox: a whole number from min. */
function IntBox({ value, min, onChange, disabled, name }: { value: number; min: number; onChange(v: number): void; disabled?: boolean; name?: string }) {
  return <input className="pdx-int" data-qf={name} type="number" min={min} step={1} value={value} disabled={disabled}
    onChange={(e) => { const n = Math.round(Number(e.target.value)); if (Number.isFinite(n) && n >= min) onChange(n) }} />
}
/** A reference combo (ComboLinks): its items, the current reference shown even when it is none of them (as "Pad:Face6"), and
 *  Select reference…, which waits for a click on an Origin axis or plane in the tree, or a face or edge in the 3D view. */
function RefCombo({ items, value, onChange, onPick, picking, name }: { items: Item[]; value: Ref; onChange(r: Ref): void; onPick(): void; picking: boolean; name: string }) {
  const list = [...items]
  if (value !== null && !list.some((i) => sameRef(i.ref, value))) list.push({ label: refSub(value) ? `${refName(value)}:${refSub(value)}` : String(refName(value)), ref: value })
  const cur = list.findIndex((i) => sameRef(i.ref, value))
  return <QComboBox data-qf={name} value={picking ? 'pick' : String(cur)} onChange={(e) => { const k = e.target.value; if (k === 'pick') onPick(); else onChange(list[Number(k)].ref) }}>
    {list.map((i, k) => <option key={k} value={String(k)}>{i.label}</option>)}
    <option value="pick">{SELECT_REF}</option>
  </QComboBox>
}

type Picking = { key: string; what: 'plane' | 'axis' | 'direction' } | null
/** The fields of one transformation: Mirror's Plane, a pattern's Direction(s) or Axis with Mode, Length/Spacing or Angle,
 *  Occurrences (TaskMirroredParameters.ui, PatternParametersWidget.ui as TaskPatternParameters lays it out). */
function TransformFields({ doc, f, sketch, set, picking, setPicking }: { doc: FeatureDoc; f: Feature; sketch: Feature | undefined; set(p: Partial<Feature>): void
  picking: Picking; setPicking(p: Picking): void }) {
  if (f.type === SCALED) {
    // TaskScaledParameters.ui: Factor (spinFactor, a plain number), Occurrences (spinOccurrences)
    return <>
      <label className="tfield"><span>Factor</span><input className="pdx-int" data-qf="spinFactor" type="number" step={0.1} value={num(doc, f.factor, 2)}
        onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) set({ factor: n }) }} /></label>
      <label className="tfield"><span>Occurrences</span><IntBox name="spinOccurrences" value={Math.round(num(doc, f.occurrences, 2))} min={0} onChange={(x) => set({ occurrences: x })} /></label>
    </>
  }
  if (f.type === MIRRORED) {
    return <label className="tfield"><span>Plane</span>
      <RefCombo name="comboPlane" items={planeItems(sketch)} value={(f.mirror_plane ?? null) as Ref} onChange={(r) => set({ mirror_plane: r })}
        picking={picking?.key === 'mirror_plane'} onPick={() => setPicking({ key: 'mirror_plane', what: 'plane' })} /></label>
  }
  const polar = f.type === POLAR
  const group = (s: '' | '2') => {
    const mode = String(f[`mode${s}`] ?? 'Extent')
    const refKey = polar ? 'axis' : `direction${s}`
    return <>
      <div className="tfield pdx-dir">
        <button className={cls('qbtn', 'pdx-rev', f[`reversed${s}`] === true && 'on')} title="Reverse the direction of the pattern." onClick={() => set({ [`reversed${s}`]: !f[`reversed${s}`] })}>⇄</button>
        <RefCombo name="comboDirection" items={axisItems(sketch)} value={(f[refKey] ?? null) as Ref} onChange={(r) => set({ [refKey]: r })}
          picking={picking?.key === refKey} onPick={() => setPicking({ key: refKey, what: polar ? 'axis' : 'direction' })} />
      </div>
      <label className="tfield"><span>Mode</span><QComboBox data-qf="comboMode" value={mode} onChange={(e) => set({ [`mode${s}`]: e.target.value })}>
        <option value="Extent">{polar ? 'Total Angle' : 'Extent'}</option><option value="Spacing">{polar ? 'Angular Spacing' : 'Spacing'}</option></QComboBox></label>
      {mode === 'Extent'
        ? <label className="tfield"><span>{polar ? 'Total Angle' : 'Length'}</span><QuantityBox value={num(doc, f[polar ? 'angle' : `length${s}`], polar ? 360 : 100)} dims={polar ? ANGLE : LENGTH}
          onChange={(x) => set({ [polar ? 'angle' : `length${s}`]: x })} /></label>
        : <label className="tfield"><span>{polar ? 'Angular Spacing' : 'Spacing'}</span><QuantityBox value={num(doc, f[`offset${s}`], polar ? 120 : 10)} dims={polar ? ANGLE : LENGTH}
          onChange={(x) => set({ [`offset${s}`]: x })} /></label>}
      <label className="tfield"><span>Occurrences</span><IntBox value={Math.round(num(doc, f[`occurrences${s}`], 2))} min={1} onChange={(x) => set({ [`occurrences${s}`]: x })} /></label>
    </>
  }
  if (polar) return <fieldset className="tgroup"><legend>Axis</legend>{group('')}</fieldset>
  const two = Math.round(num(doc, f.occurrences2, 1)) > 1
  return <>
    <fieldset className="tgroup"><legend>Direction</legend>{group('')}</fieldset>
    {two
      ? <fieldset className="tgroup"><legend><label className="tcheck"><input type="checkbox" checked onChange={() => set({ occurrences2: 1 })} /> Direction 2</label></legend>{group('2')}</fieldset>
      : <label className="tcheck"><input type="checkbox" checked={false} onChange={() => set({ occurrences2: 2 })} /> Direction 2</label>}
  </>
}

const PICK_HINT: Record<string, string> = { plane: 'Select a plane: an Origin plane, a sketch\'s axis, or a planar face', axis: 'Select an axis: an Origin axis, a sketch\'s axis, or a straight or circular edge',
  direction: 'Select a direction reference (edge, face, datum line)' }
/** A transformed feature's panel (TaskTransformedParameters with its subclass's fields, TaskMultiTransformParameters for a
 *  MultiTransform), then Preview. A new feature has what the command gives it; OK writes it ("Make Mirrored", or
 *  "Edit Mirrored" for one double-clicked) and makes it the Tip; Cancel writes nothing. */
function TransformedTask({ part, other, edit }: { part: string; other: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? findFeature(doc, other) : undefined
  const initial = useMemo<Feature | null>(() => {
    if (!doc) return null
    if (existing) return clone(existing)
    const [type, orig] = other.split('|')
    return newTransformed(doc, type, orig ? orig.split(',') : [])
  }, [part, other, edit])
  const [f, setF] = useState<Feature | null>(initial)
  const [update, setUpdate] = useState(true)
  const [overlay, setOverlay] = useState(true)
  const [mode, setMode] = useState<'add' | 'remove' | null>(null)
  const [picking, setPicking] = useState<Picking>(null)
  const [sub, setSub] = useState<number | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const set = (p: Partial<Feature>) => setF((x) => (x ? { ...x, ...p } : x))
  const setSubF = (i: number, p: Partial<Feature>) => setF((x) => (x ? { ...x, transformations: pdxChildren(x).map((t, k) => (k === i ? { ...t, ...p } : t)) } : x))
  // Add Feature / Remove Feature / Select reference…: the next pick in the tree or the 3D view (TaskTransformedParameters::onSelectionChanged)
  const seen = useRef({ feat: s.featSel.join(), sub: s.subSel.join() })
  useEffect(() => {
    const before = seen.current
    seen.current = { feat: s.featSel.join(), sub: s.subSel.join() }
    if (!f || !doc) return
    const featNew = s.featSel.join() !== before.feat ? s.featSel[s.featSel.length - 1] : null
    const subNew = s.subSel.join() !== before.sub ? s.subSel[s.subSel.length - 1] : null
    if (mode && featNew) {
      const [p, n] = splitRef(featNew)
      const g = p === part ? doc.features.find((x) => x.name === n) : undefined
      if (!g || g.type === SKETCH || g.name === (existing?.name ?? '')) return
      const orig = (f.originals as string[]) ?? []
      if (mode === 'add' && !orig.includes(n)) set({ originals: [...orig, n] })
      if (mode === 'remove') set({ originals: orig.filter((x) => x !== n) })
      return
    }
    if (!picking) return
    let r: Ref = null
    if (featNew) {
      const [p, n] = splitRef(featNew)
      if (p === part && ORIGIN_DIR[n] && (picking.what === 'plane' ? n.endsWith('_Plane') : picking.what === 'axis' ? n.endsWith('_Axis') : true)) r = n
    } else if (subNew) {
      const [, el] = [subNew.slice(0, subNew.lastIndexOf('.')), subNew.slice(subNew.lastIndexOf('.') + 1)]
      const tip = lastSolid(doc)
      if (tip && tip !== existing?.name && /^(Face|Edge)\d+$/.test(el)) r = [tip, el]
      else if (tip === existing?.name) report('warn', `${tip} is the Tip and the feature being edited: set the Tip before it to pick one of its faces or edges`)
    }
    if (r === null) return
    if (sub !== null) setSubF(sub, { [picking.key]: r }); else set({ [picking.key]: r })
    setPicking(null)
  }, [s.featSel, s.subSel])
  useEffect(() => { if (picking) report('msg', PICK_HINT[picking.what]) }, [picking])
  const drawn = useRef(false)
  useEffect(() => {
    if (!f || !doc || (!update && drawn.current)) return
    drawn.current = true
    getView()?.setHelper('pd-preview', overlay ? transformedPreview(doc, f) : null)
  }, [f, overlay, update])
  useEffect(() => () => { getView()?.setHelper('pd-preview', null) }, [])
  if (!doc || !f) return <div className="tasks"><p className="hint">{part}: no feature {other}</p></div>
  const info = TRANSFORMED[f.type]
  const whole = f.transform_mode === 'Whole shape'
  const sketch = sketchOf(doc, f)
  const originals = (f.originals as string[]) ?? []
  const ok = async () => {
    const out = whole ? { ...f, originals: [] } : f
    if (!whole && !originals.length) { await messageBox('warning', info.label, info.kind === 'Mirrored' ? 'No features selected to be mirrored.' : info.kind === 'Scaled' ? 'No features selected to be transformed.' : 'No features selected to be patterned.'); return }
    closeTask()
    if (existing) {
      const changed = Object.fromEntries(Object.entries(out).filter(([k, x]) => k !== 'name' && k !== 'type' && JSON.stringify(x) !== JSON.stringify(existing[k])))
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name: existing.name, props: changed }], { name: `Edit ${existing.name}` })
      return
    }
    const name = uniqueName(allNames(doc), info.kind)
    const done = await applyOps(part, [{ op: 'add', feature: { ...out, name }, after: lastSolid(doc) }, { op: 'tip', name }], { name: `Make ${info.kind}` })
    if (done) setState({ featSel: [refOf(part, name)], selected: [] })
  }
  const subs = pdxChildren(f)
  const addSub = (type: string) => {
    const taken = new Set([...allNames(doc), ...subs.map((t) => t.name)])
    const t = newTransformed(doc, type, [])
    t.originals = []
    t.transform_mode = 'Features'
    if (type === MIRRORED) t.mirror_plane = sketch ? [sketch.name, 'V_Axis'] : 'XY_Plane'
    if (type === LINEAR) Object.assign(t, { direction: sketch ? [sketch.name, 'H_Axis'] : 'X_Axis', direction2: null })
    if (type === POLAR) t.axis = sketch ? [sketch.name, 'N_Axis'] : 'Z_Axis'
    t.name = uniqueName(taken, TRANSFORMED[type].sub)
    set({ transformations: [...subs, t] })
    setSub(subs.length)
  }
  const move = (i: number, by: number) => { const j = i + by; if (j < 0 || j >= subs.length) return; const l = [...subs];[l[i], l[j]] = [l[j], l[i]]; set({ transformations: l }); setSub(j) }
  const subMenu = (): Entry[] => [
    { label: 'Edit', disabled: sub === null, onSelect: () => setSub(sub) },
    { label: 'Delete', disabled: sub === null, onSelect: () => { set({ transformations: subs.filter((_, k) => k !== sub) }); setSub(null) } },
    'sep',
    { label: 'Add Mirror Transformation', onSelect: () => addSub(MIRRORED) },
    { label: 'Add Linear Pattern', onSelect: () => addSub(LINEAR) },
    { label: 'Add Polar Pattern', onSelect: () => addSub(POLAR) },
    { label: 'Add Scale Transformation', onSelect: () => addSub(SCALED) },
    'sep',
    { label: 'Move Up', disabled: sub === null || sub === 0, onSelect: () => sub !== null && move(sub, -1) },
    { label: 'Move Down', disabled: sub === null || sub === subs.length - 1, onSelect: () => sub !== null && move(sub, 1) },
  ]
  return (
    <div className="tasks pdx-task">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskBox title={info.panel} icon={info.icon}>
        <div className="pd-form">
          <label className="tcheck"><input type="radio" name="pdx-mode" checked={whole} onChange={() => set({ transform_mode: 'Whole shape' })} /> Transform body</label>
          <label className="tcheck"><input type="radio" name="pdx-mode" checked={!whole} onChange={() => set({ transform_mode: 'Features' })} /> Transform tool shapes</label>
          <div className="pdx-buttons">
            <button className={cls('qbtn', mode === 'add' && 'on')} disabled={whole} onClick={() => setMode(mode === 'add' ? null : 'add')}>Add Feature</button>
            <button className={cls('qbtn', mode === 'remove' && 'on')} disabled={whole} onClick={() => setMode(mode === 'remove' ? null : 'remove')}>Remove Feature</button>
          </div>
          <div className={cls('pdx-list', whole && 'off')} data-qf="listWidgetFeatures">{(whole ? [] : originals).map((o) => <div key={o} className="pdx-item">{o}</div>)}</div>
          {mode && <p className="hint">{mode === 'add' ? 'Click a feature in the tree to add it' : 'Click a feature in the tree to remove it'}</p>}
          {f.type === MULTI ? <>
            <div className="tlabel">Transformations</div>
            <div className="pdx-list" data-qf="listTransformFeatures" onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}>
              {subs.length ? subs.map((t, i) => <div key={t.name} className={cls('pdx-item', sub === i && 'sel')} onClick={() => setSub(i)} onDoubleClick={() => setSub(i)}>{t.name}</div>)
                : <div className="pdx-item hint">Right-click to add a transformation</div>}
            </div>
            {menu && <ContextMenu at={menu} entries={subMenu()} onClose={() => setMenu(null)} />}
            {sub !== null && subs[sub] && <div className="pdx-sub">
              <TransformFields doc={doc} f={subs[sub]} sketch={sketch} set={(p) => setSubF(sub, p)} picking={picking} setPicking={setPicking} />
              <button className="qbtn" onClick={() => setSub(null)}>OK</button>
            </div>}
          </> : <TransformFields doc={doc} f={f} sketch={sketch} set={set} picking={picking} setPicking={setPicking} />}
          <label className="tcheck"><input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} /> Recompute on change</label>
        </div>
      </TaskBox>
      <TaskBox title="Preview" icon={info.icon}>
        <label className="tcheck" title="n/a: the result is built when OK writes it; the preview shows the tool shapes"><input type="checkbox" disabled /> Show final result</label>
        <label className="tcheck"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Show preview overlay</label>
      </TaskBox>
    </div>
  )
}

// ── the primitives' panel (TaskPrimitiveParameters: the shape's fields, then TaskDlgAttacher's, then Preview) ──
/** Each shape's fields, in DlgPrimitives.ui's order, with its labels; [label, key, kind] or a min/max pair. */
const PRIM_FIELDS: Record<Shape, ([string, string, 'length' | 'angle' | 'int'] | [string, string, string, 'length'])[]> = {
  Box: [['Length', 'length', 'length'], ['Width', 'width', 'length'], ['Height', 'height', 'length']],
  Cylinder: [['Radius', 'radius', 'length'], ['Height', 'height', 'length'], ['Angle in first direction', 'first_angle', 'angle'],
    ['Angle in second direction', 'second_angle', 'angle'], ['Rotation angle', 'angle', 'angle']],
  Sphere: [['Radius', 'radius', 'length'], ['U parameter', 'angle3', 'angle'], ['V parameters', 'angle1', 'angle'], ['', 'angle2', 'angle']],
  Cone: [['Radius 1', 'radius1', 'length'], ['Radius 2', 'radius2', 'length'], ['Height', 'height', 'length'], ['Angle', 'angle', 'angle']],
  Ellipsoid: [['Radius 1', 'radius1', 'length'], ['Radius 2', 'radius2', 'length'], ['Radius 3', 'radius3', 'length'], ['U parameter', 'angle3', 'angle'],
    ['V parameter', 'angle1', 'angle'], ['', 'angle2', 'angle']],
  Torus: [['Radius 1', 'radius1', 'length'], ['Radius 2', 'radius2', 'length'], ['U parameter', 'angle3', 'angle'], ['V parameter', 'angle1', 'angle'], ['', 'angle2', 'angle']],
  Prism: [['Polygon', 'polygon', 'int'], ['Circumradius', 'circumradius', 'length'], ['Height', 'height', 'length'], ['Angle in first direction', 'first_angle', 'angle'],
    ['Angle in second direction', 'second_angle', 'angle']],
  Wedge: [['X min/max', 'xmin', 'xmax', 'length'], ['Y min/max', 'ymin', 'ymax', 'length'], ['Z min/max', 'zmin', 'zmax', 'length'],
    ['X2 min/max', 'x2min', 'x2max', 'length'], ['Z2 min/max', 'z2min', 'z2max', 'length']],
}
/** FeaturePrimitive.cpp's defaults. */
const PRIM_DEFAULTS: Record<Shape, Record<string, unknown>> = {
  Box: { length: 10, width: 10, height: 10 }, Cylinder: { radius: 10, height: 10, angle: 360, first_angle: 0, second_angle: 0 },
  Sphere: { radius: 5, angle1: -90, angle2: 90, angle3: 360 }, Cone: { radius1: 2, radius2: 4, height: 10, angle: 360 },
  Ellipsoid: { radius1: 2, radius2: 4, radius3: 0, angle1: -90, angle2: 90, angle3: 360 }, Torus: { radius1: 10, radius2: 2, angle1: -180, angle2: 180, angle3: 360 },
  Prism: { polygon: 6, circumradius: 2, height: 10, first_angle: 0, second_angle: 0 },
  Wedge: { xmin: 0, ymin: 0, zmin: 0, x2min: 2, z2min: 2, xmax: 10, ymax: 10, zmax: 10, x2max: 8, z2max: 8 },
}
function PrimitiveTask({ part, other, edit }: { part: string; other: string; edit: boolean }) {
  const s = useStore((x) => x)
  const doc = s.features[part]
  const existing = edit ? findFeature(doc, other) : undefined
  const type = existing?.type ?? other
  const p = primOf(type)
  const initial = useMemo<Feature | null>(() => {
    if (!p) return null
    if (existing) return clone(existing)
    return { name: '', type, ...PRIM_DEFAULTS[p[1]], placement: null, refine: true, ...(p[0] === 'Subtractive' ? { operation: 'Subtraction' } : {}) }
  }, [part, other, edit])
  const [f, setF] = useState<Feature | null>(initial)
  const [overlay, setOverlay] = useState(true)
  const [attached, setAttached] = useState<PlacementData | null>(null)       // where the Attachment box puts it
  const set = (patch: Partial<Feature>) => setF((x) => (x ? { ...x, ...patch } : x))
  useEffect(() => {
    if (!doc || !f) return
    const at = attached ? { ...f, placement: [attached.position, attached.ypr] } : f
    getView()?.setHelper('pd-preview', overlay ? (() => { const o = primitiveObject(doc, at); if (o) o.applyMatrix4(partMatrix(doc)); return o })() : null)
  }, [f, overlay, attached])
  useEffect(() => () => { getView()?.setHelper('pd-preview', null) }, [])
  if (!doc || !f || !p) return <div className="tasks"><p className="hint">{part}: no feature {other}</p></div>
  const [side, shape] = p
  const ok = async () => {
    closeTask()
    if (existing) {
      const changed = Object.fromEntries(Object.entries(f).filter(([k, x]) => k !== 'name' && k !== 'type' && JSON.stringify(x) !== JSON.stringify(existing[k])))
      if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name: existing.name, props: changed }], { name: `Edit ${existing.name}` })
      return
    }
    const name = uniqueName(allNames(doc), shape)
    const done = await applyOps(part, [{ op: 'add', feature: { ...f, name }, after: lastSolid(doc) }, { op: 'tip', name }],
      { name: `Make ${side === 'Additive' ? 'additive' : 'subtractive'} ${shape}` })
    if (done) setState({ featSel: [refOf(part, name)], selected: [] })
  }
  const box = (key: string, kind: 'length' | 'angle' | 'int') => kind === 'int'
    ? <IntBox value={Math.round(num(doc, f[key], 6))} min={3} onChange={(x) => set({ [key]: x })} />
    : <QuantityBox value={num(doc, f[key], PRIM_DEFAULTS[shape][key] as number)} dims={kind === 'length' ? LENGTH : ANGLE} onChange={(x) => set({ [key]: x })} />
  return (
    <div className="tasks pdx-task">
      <OkCancel onOk={() => void ok()} onCancel={closeTask} />
      <TaskBox title={`${side} ${shape} Parameters`} icon={primIcon(side, shape)}>
        <div className="pd-form">
          {PRIM_FIELDS[shape].map((d) => d.length === 4
            ? <div key={d[1]} className="tfield pdx-pair"><span>{d[0]}</span>{box(d[1], 'length')}{box(d[2], 'length')}</div>
            : <label key={d[1]} className="tfield"><span>{d[0]}</span>{box(d[1], d[2])}</label>)}
          {side === 'Subtractive' && <label className="tfield"><span>Operation</span><QComboBox data-qf="comboOperation" value={String(f.operation ?? 'Subtraction')}
            onChange={(e) => set({ operation: e.target.value })}><option>Subtraction</option><option>Common</option></QComboBox></label>}
        </div>
      </TaskBox>
      {/* TaskFeaturePrimitive's TaskAttacher (pd_attach.tsx): references, mode, offset; OK writes them with the shape */}
      <AttachTask target={{ part, name: existing?.name ?? null, type }} embed={{ onChange: (props, pl) => {
        if (props) set(props)
        setAttached(pl)
      } }} />
      <TaskBox title="Preview" icon={primIcon(side, shape)}>
        <label className="tcheck" title="n/a: the result is built when OK writes it; the preview shows the primitive"><input type="checkbox" disabled /> Show final result</label>
        <label className="tcheck"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Show preview overlay</label>
      </TaskBox>
    </div>
  )
}
/** panels.tsx's Tasks panel hands these task kinds here. */
export function PdxTask({ kind, part, other, edit }: { kind: 'pdTransform' | 'pdPrimitive'; part: string; other: string; edit: boolean }) {
  return kind === 'pdPrimitive' ? <PrimitiveTask key={`${part}:${other}:${edit}`} part={part} other={other} edit={edit} />
    : <TransformedTask key={`${part}:${other}:${edit}`} part={part} other={other} edit={edit} />
}

// ── the property view (PropertyEditor: groups in name order, properties in the order FreeCAD adds them) ──
type PropDef = { key: string; name: string; kind: 'length' | 'angle' | 'bool' | 'enum' | 'int' | 'float' | 'text' | 'list' | 'ref'; items?: string[]; ro?: (f: Feature) => string | null }
const pick = 'picked in the task panel (Select reference…), or written in the code'
const baseGroup = (f: Feature): PropDef[] => [
  // Scaled's own, added with ADD_PROPERTY (no group: Base), which FreeCAD's property view lists first
  ...(f.type === SCALED ? [{ key: 'factor', name: 'Factor', kind: 'float' as const }, { key: 'occurrences', name: 'Occurrences', kind: 'int' as const }] : []),
  ...(f.type === MULTI ? [{ key: 'transformations', name: 'Transformations', kind: 'text' as const, ro: () => 'edited in the Multi-Transform panel' }] : []),
  ...(isTransformed(f.type) ? [{ key: 'originals', name: 'Originals', kind: 'text' as const, ro: () => 'Add Feature / Remove Feature in the task panel' },
    { key: 'transform_mode', name: 'Transform Mode', kind: 'enum' as const, items: ['Features', 'Whole shape'] }] : []),
  { key: 'name', name: 'Label', kind: 'text' },
  { key: 'suppressed', name: 'Suppressed', kind: 'bool', ro: () => 'FEATURES has no suppressed state' },
  ...(isPrimitive(f.type) ? [{ key: 'placement', name: 'Placement', kind: 'text' as const }] : []),
]
const partDesignGroup = (f: Feature): PropDef[] => [
  ...(primOf(f.type)?.[0] === 'Subtractive' ? [{ key: 'operation', name: 'Operation', kind: 'enum' as const, items: ['Subtraction', 'Common'] }] : []),
  { key: 'refine', name: 'Refine', kind: 'bool' }, { key: 'fuzzy_tolerance', name: 'Fuzzy Tolerance', kind: 'text', ro: () => 'the booleans run at OCCT\'s own tolerance' },
]
const patternDir = (s: '' | '2'): PropDef[] => [
  { key: `direction${s}`, name: `Direction${s}`, kind: 'ref', ro: () => pick },
  { key: `reversed${s}`, name: `Reversed${s}`, kind: 'bool' },
  { key: `mode${s}`, name: `Mode${s}`, kind: 'enum', items: ['Extent', 'Spacing'] },
  { key: `length${s}`, name: `Length${s}`, kind: 'length', ro: (f) => (f[`mode${s}`] === 'Spacing' ? 'Mode is Spacing: Length is Offset times the steps' : null) },
  { key: `offset${s}`, name: `Offset${s}`, kind: 'length', ro: (f) => (f[`mode${s}`] === 'Spacing' ? null : 'Mode is Extent: Offset is Length over the steps') },
  { key: `spacings${s}`, name: `Spacings${s}`, kind: 'list' }, { key: `spacing_pattern${s}`, name: `Spacing Pattern${s}`, kind: 'list' },
  { key: `occurrences${s}`, name: `Occurrences${s}`, kind: 'int' },
]
function propGroups(f: Feature): [string, PropDef[]][] {
  const out: [string, PropDef[]][] = [['Base', baseGroup(f)]]
  const supp: PropDef = { key: 'suppressed_indices', name: 'Suppressed Indices', kind: 'list' }
  if (f.type === MIRRORED) out.push(['Mirrored', [{ key: 'mirror_plane', name: 'Mirror Plane', kind: 'ref', ro: () => pick }]])
  if (f.type === LINEAR) out.push(['Direction 1', patternDir('')], ['Direction 2', patternDir('2')])
  if (f.type === POLAR) out.push(['Polar Pattern', [{ key: 'axis', name: 'Axis', kind: 'ref', ro: () => pick }, { key: 'reversed', name: 'Reversed', kind: 'bool' },
    { key: 'mode', name: 'Mode', kind: 'enum', items: ['Extent', 'Spacing'] },
    { key: 'angle', name: 'Angle', kind: 'angle', ro: (x) => (x.mode === 'Spacing' ? 'Mode is Spacing' : null) },
    { key: 'offset', name: 'Offset', kind: 'angle', ro: (x) => (x.mode === 'Spacing' ? null : 'Mode is Extent') },
    { key: 'spacings', name: 'Spacings', kind: 'list' }, { key: 'spacing_pattern', name: 'Spacing Pattern', kind: 'list' }, { key: 'occurrences', name: 'Occurrences', kind: 'int' }]])
  const p = primOf(f.type)
  if (p) {
    const dims = Object.keys(PRIM_DEFAULTS[p[1]])
    const skew = ['first_angle', 'second_angle']
    const def = (k: string): PropDef => ({ key: k, name: k.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(' '), kind: k === 'polygon' ? 'int' : /angle/.test(k) ? 'angle' : 'length' })
    const inPanel = () => 'set in the Attachment box of its task panel (double-click it)'
    const att: PropDef[] = [{ key: 'attacher_engine', name: 'Attacher Engine', kind: 'text', ro: () => 'Engine 3D' },
      { key: 'attachment_support', name: 'Attachment Support', kind: 'text', ro: inPanel },
      { key: 'map_mode', name: 'Map Mode', kind: 'text', ro: inPanel }]
    out.unshift(['Attachment', att])
    out.push([p[1], dims.filter((k) => p[1] !== 'Cylinder' || !skew.includes(k)).map(def)])
    if (p[1] === 'Cylinder') out.push(['Prism', skew.map(def)])
  }
  out.push(['Part Design', partDesignGroup(f)])
  if (f.type !== LINEAR && isTransformed(f.type)) out.push(['Transformation', [supp]])
  return out.sort((a, b) => a[0].localeCompare(b[0]))
}
const SHOWN_DEFAULT: Record<string, unknown> = { attacher_engine: 'Engine 3D', attachment_support: '', map_mode: 'Deactivated', suppressed: false, fuzzy_tolerance: 0 }
/** The Data tab for a transformed feature or a primitive (or a MultiTransform's transformation): editable properties write
 *  through `cad feature set` ("Edit LinearPattern.Occurrences"), the rest say why they are read-only here. */
export function PdxProps({ part, name }: { part: string; name: string }) {
  useStore((s) => s.units)
  const s = useStore((x) => x)
  const doc = s.features[part]
  const f = findFeature(doc, name)
  if (!doc || !f) return null
  const holder = holderOf(doc, name)
  const vars = Object.fromEntries(Object.entries(doc.params).filter(([, v]) => typeof v === 'number').map(([k, v]) => [k, { value: v as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const set = (props: Record<string, unknown>) => {
    const k = Object.keys(props)[0]
    const label = `Edit ${name}.${k.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join('')}`
    if (holder) {
      const [mt] = holder
      const transformations = pdxChildren(mt).map((t) => (t.name === name ? { ...t, ...props } : t))
      return void applyOps(part, [{ op: 'set', name: mt.name, props: { transformations } }], { name: label })
    }
    void applyOps(part, [{ op: 'set', name, props }], { name: label, line: `cad feature set ${s.slug} ${part} ${name} ${Object.entries(props).map(([a, b]) => `${a}=${typeof b === 'string' ? b : JSON.stringify(b)}`).join(' ')}` })
  }
  const shown = (d: PropDef, v: unknown): string => {
    if (d.kind === 'ref') return refText((v ?? null) as Ref)
    if (d.key === 'transformations') return `[${pdxChildren(f).map((t) => t.name).join(', ')}]`
    if (d.key === 'originals') return ((v as string[]) ?? []).join(', ')
    if (d.key === 'attachment_support') return ((v as [string, string][]) || []).map(([n, e]) => (e ? `${n}:${e}` : n)).join(', ')
    if (d.key === 'placement') { const m = placementMatrix(v); const p = new THREE.Vector3().setFromMatrixPosition(m); return Array.isArray(v) ? `[${JSON.stringify((v as number[][])[1])} ypr; (${p.x.toFixed(2)} mm  ${p.y.toFixed(2)} mm  ${p.z.toFixed(2)} mm)]` : '[(0.00 0.00 1.00); 0.00°; (0.00 mm  0.00 mm  0.00 mm)]' }
    if (d.kind === 'list') return `[${((v as number[]) ?? []).map((x) => Number(x).toFixed(2)).join(', ')}]`
    if (d.kind === 'length' || d.kind === 'angle') { const n = numberOf(v, doc.params); return n === null ? '?' : quantity.userString({ value: n, dims: d.kind === 'length' ? LENGTH : ANGLE }).text + (typeof v === 'string' ? `  (= ${v})` : '') }
    return String(v ?? '')
  }
  /** FreeCAD's synced value: a pattern's Offset is Length over the steps in Extent mode, its Length Offset times them in Spacing. */
  const value = (d: PropDef): unknown => {
    if (d.key === 'name') return f.name
    const v = f[d.key] ?? SHOWN_DEFAULT[d.key]
    const m = /^(offset|length)(2?)$/.exec(d.key)
    if (m && f.type === LINEAR) {
      const occ = Math.max(Math.round(num(doc, f[`occurrences${m[2]}`], 2)) - 1, 1)
      if (m[1] === 'offset' && f[`mode${m[2]}`] !== 'Spacing') return num(doc, f[`length${m[2]}`], 100) / occ
      if (m[1] === 'length' && f[`mode${m[2]}`] === 'Spacing') return num(doc, f[`offset${m[2]}`], 10) * occ
    }
    return v
  }
  const row = (d: PropDef): ReactNode => {
    const v = value(d), why = d.ro?.(f) ?? null
    if (why) return <Row key={d.key} k={<span title={`Read-only: ${why}`}>{d.name}</span>} v={shown(d, v)} />
    if (d.kind === 'bool') return <EditRow key={d.key} k={d.name} value={v === true} type="bool" onCommit={(x) => set({ [d.key]: x })} />
    if (d.kind === 'enum') return <div key={d.key} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{d.name}</span>
      <span className="pv"><QComboBox className="qselect-pv" value={String(v)} onChange={(e) => set({ [d.key]: e.target.value })}>{d.items!.map((o) => <option key={o}>{o}</option>)}</QComboBox></span></div>
    if (d.kind === 'length' || d.kind === 'angle') {
      return <EditRow key={d.key} k={d.name} value={numberOf(v, doc.params) ?? 0} type="float" kind={d.kind === 'length' ? 'Length' : 'Angle'} vars={vars} owner={f.name}
        onCommit={(x) => set({ [d.key]: x })} onExpr={(text) => set({ [d.key]: text })} note={typeof v === 'string' ? `= ${v}` : undefined} />
    }
    if (d.kind === 'int') return <EditRow key={d.key} k={d.name} value={Math.round(numberOf(v, doc.params) ?? 0)} type="int" onCommit={(x) => set({ [d.key]: x })} />
    if (d.kind === 'float') return <EditRow key={d.key} k={d.name} value={numberOf(v, doc.params) ?? 0} type="float" onCommit={(x) => set({ [d.key]: x })} />
    if (d.kind === 'list') return <EditRow key={d.key} k={d.name} value={JSON.stringify(v ?? [])} type="str" onCommit={(x) => { try { const l = JSON.parse(String(x)); if (Array.isArray(l)) set({ [d.key]: l }) } catch { report('err', `${d.name}: a list such as [5, -1, 10]`) } }} />
    if (d.key === 'name') return <EditRow key={d.key} k={d.name} value={f.name} type="str" onCommit={(x) => holder ? report('warn', 'a transformation is renamed in the code') : void applyOps(part, [{ op: 'rename', name, to: String(x) }], { name: `Rename ${name}.Label` })} />
    if (d.key === 'placement') return <EditRow key={d.key} k={d.name} value={JSON.stringify(v ?? [[0, 0, 0], [0, 0, 0]])} type="str"
      onCommit={(x) => { try { const l = JSON.parse(String(x)); if (Array.isArray(l)) set({ placement: l }) } catch { report('err', 'Placement: [[x, y, z], [yaw, pitch, roll]] in mm and degrees') } }} />
    return <Row key={d.key} k={d.name} v={shown(d, v)} />
  }
  return <>{propGroups(f).map(([g, defs]) => <Group key={g} title={g}>{defs.map(row)}</Group>)}</>
}

// ── menus (PartDesignGui::Workbench::setupMenuBar: Transformation Features, the primitives' groups) ──
const hasDoc = () => !!getState().slug
export function transformMenu(): Entry[] {
  return [MIRRORED, LINEAR, POLAR, MULTI].map((t) => ({ label: TRANSFORMED[t].label, icon: TRANSFORMED[t].icon, cmd: TRANSFORMED[t].cmd, disabled: !hasDoc(), onSelect: () => void makeTransformed(t) }))
}
/** CmdPrimtiveCompAdditive / CmdPrimtiveCompSubtractive's actions: "Additive Box" … "Additive Wedge". */
export function primitiveMenu(side: Side): Entry[] {
  return SHAPES.map((x) => ({ label: `${side} ${x}`, icon: primIcon(side, x), cmd: `PartDesign_${side}${x}`, disabled: !hasDoc(), onSelect: () => void makePrimitive(side, x) }))
}
/** The commands cmdreg.ts registers (Gui::Command names), with what runs them. */
export function pdxCommands(): [string, string, () => void][] {
  return [
    ...[MIRRORED, LINEAR, POLAR, MULTI].map((t): [string, string, () => void] => [TRANSFORMED[t].cmd, TRANSFORMED[t].label, () => void makeTransformed(t)]),
    ...(['Additive', 'Subtractive'] as Side[]).flatMap((side) => SHAPES.map((x): [string, string, () => void] => [`PartDesign_${side}${x}`, `${side} ${x}`, () => void makePrimitive(side, x)])),
    ['PartDesign_CompPrimitiveAdditive', 'Additive Primitive', () => void makePrimitive('Additive', 'Box')],
    ['PartDesign_CompPrimitiveSubtractive', 'Subtractive Primitive', () => void makePrimitive('Subtractive', 'Box')],
  ]
}

// ── Std_Delete (partdesign.tsx's deleteFeatures asks here) ────────────────────
/** Whether a feature references one of names: as an original, its plane, direction or axis, or in its transformations. */
export function pdxUses(f: Feature, names: string[]): boolean {
  if (!isPdx(f.type)) return false
  const refs = [...((f.originals as string[] | undefined) ?? []), ...['mirror_plane', 'direction', 'direction2', 'axis'].map((k) => refName(f[k] as Ref))]
  return refs.some((r) => !!r && names.includes(r)) || pdxChildren(f).some((t) => pdxUses(t, names))
}
/** The delete ops for names: a MultiTransform's transformation goes from its list (a set on the MultiTransform), the rest
 *  are deleted (a MultiTransform's transformations with it: ViewProviderMultiTransform::onDelete). */
export function pdxDeleteOps(doc: FeatureDoc, names: string[]): { top: string[]; ops: FeatureOp[] } {
  const top = names.filter((n) => doc.features.some((f) => f.name === n))
  const ops: FeatureOp[] = []
  for (const f of doc.features) {
    const gone = pdxChildren(f).filter((t) => names.includes(t.name))
    if (gone.length && !top.includes(f.name)) ops.push({ op: 'set', name: f.name, props: { transformations: pdxChildren(f).filter((t) => !names.includes(t.name)) } })
  }
  return { top, ops: [...ops, ...top.map((name): FeatureOp => ({ op: 'delete', name }))] }
}
