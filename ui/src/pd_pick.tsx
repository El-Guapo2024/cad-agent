// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/ReferenceSelection.cpp: 2012 Konstantinos Poulios (allow, allowOrigin, allowDatum,
//     allowPartFeature, getReferencedSelection, getRefStr)
//   src/Mod/PartDesign/Gui/TaskSketchBasedParameters.cpp: 2013 Jan Rheinländer (onSelectReference, startReferenceSelection,
//     finishReferenceSelection, onAddSelection, updateReferenceName)
//   src/Mod/PartDesign/Gui/TaskTransformedParameters.cpp: 2012 Jan Rheinländer (showBase, hideObject, originalSelected)
//   src/Gui/Selection/Selection.cpp: 2011 Jürgen Riegel (setPreselect's "Not allowed:", addSelection's "Selection not
//     allowed by filter" and the forbidden cursor)
//   src/Gui/ViewProviderLine.cpp: 2012 Jürgen Riegel; 2015 Alexander Golubev (Fat-Zer); 2026 Joao Matos (the Origin's axes)
// A pick in the 3D view while a task panel asks for a reference, as FreeCAD's PartDesign panels take one: the shown feature
// hides and the solid the feature goes on (getBaseObject) shows in its place, its faces and edges named as FreeCAD names
// them (`cad feature shape`); the Body's datums, an LCS's features and the Origin's planes or axes the panel shows are
// picked too; the panel's selection gate (ReferenceSelection's AllowSelection flags) decides what may be preselected and
// picked, a refused element showing FreeCAD's "Not allowed:" and the forbidden cursor. The reference comes back as the
// part file writes it: ("Pad", "Face6"), "DatumPlane", ("LCS", "XY_Plane"), "XY_Plane".
// Also here: a click on a datum shown in the 3D view selects it, as it does in FreeCAD (outside any panel).
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api, type Body } from './api'
import { getState, setState, subscribe, type Feature, type FeatureDoc } from './store'
import { getView } from './actions'
import { attachedOf, DATUM_TYPES, placementMatrix, ROLES } from './attached'
import { isSolid, originPlanes, setAttachPicker, tempHidden } from './partdesign'

/** ReferenceSelection's AllowSelection flags (ReferenceSelection.h). */
export type Allow = { face?: boolean; edge?: boolean; point?: boolean; planar?: boolean; circle?: boolean; whole?: boolean; solid?: boolean; otherBody?: boolean }
/** A reference as the part file writes it: an Origin feature or a datum by name, or (object, sub-element). */
export type Ref = string | [string, string]
/** What a pick names: an element of the base solid shown, a datum (or an LCS's feature), an Origin feature. */
export type Picked = { obj: string; sub: string; kind: 'element' | 'datum' | 'origin'; type: string; ref: Ref; dir?: [number, number, number] }
type Mesh = { faces: { name: string; points: number[]; index: number[]; kind?: string }[]; edges: { name: string; points: number[]; kind?: string | null }[] }

const SHAPE = new THREE.Color(0xcccccc), LINE = new THREE.Color(0x1a1a1a)
const ELEMENT = '@'                                  // a pickName of the base's element: "@Pad.Face6"
const ORIGIN_TYPE: Record<string, string> = { X_Axis: 'App::Line', Y_Axis: 'App::Line', Z_Axis: 'App::Line', XY_Plane: 'App::Plane',
  XZ_Plane: 'App::Plane', YZ_Plane: 'App::Plane', Origin: 'App::Point', Origin001: 'App::Point' }
/** What a datum is to the gate: Part's are App datum elements (App::Plane, App::Line, App::Point), PartDesign's Part::Datum. */
const DATUM_CLASS: Record<string, string> = { 'Part::DatumPlane': 'App::Plane', 'Part::DatumLine': 'App::Line', 'Part::DatumPoint': 'App::Point',
  'Part::LocalCoordinateSystem': 'App::LocalCoordinateSystem', 'PartDesign::Plane': 'PartDesign::Plane', 'PartDesign::Line': 'PartDesign::Line',
  'PartDesign::Point': 'PartDesign::Point', 'PartDesign::CoordinateSystem': 'PartDesign::CoordinateSystem' }

/** A helper's pickName as a reference of the Body `part`, or null when it is not one of its objects: "@Pad.Face6" (an element of
 *  the base shown), "Body/DatumPlane" or "Body/LCS/XY_Plane" (pd_attach.tsx's datums), "XY_Plane" (the Origin shown). */
export function parsePick(part: string, name: string, elementKinds?: Record<string, string | null | undefined>): Picked | null {
  if (name.startsWith(ELEMENT)) {
    const i = name.lastIndexOf('.')
    const obj = name.slice(1, i), sub = name.slice(i + 1)
    return { obj, sub, kind: 'element', type: elementKinds?.[sub] ?? '', ref: [obj, sub] }
  }
  if (ORIGIN_TYPE[name]) return { obj: name, sub: '', kind: 'origin', type: ORIGIN_TYPE[name], ref: name }
  const parts = name.split('/')
  if (parts.length < 2 || parts[0] !== part) return null
  const doc = getState().features[part]
  const f = doc?.features.find((x) => x.name === parts[1])
  if (!f || !DATUM_TYPES[f.type]) return null
  if (parts.length === 3) {
    const role = parts[2]
    return { obj: f.name, sub: role, kind: 'datum', type: ORIGIN_TYPE[role] ?? '', ref: [f.name, role] }
  }
  return { obj: f.name, sub: '', kind: 'datum', type: DATUM_CLASS[f.type] ?? f.type, ref: f.name }
}

/** A row of the tree picked while a panel asks for a reference ("Body/Pad", "Body/XY_Plane", "Body/LCS/XY_Plane"): the whole
 *  object, as a click on its row selects it. */
export function parseRow(part: string, row: string): Picked | null {
  const [p, obj, role] = row.split('/')
  if (p !== part || !obj) return null
  if (ORIGIN_TYPE[obj]) return { obj: obj === 'Origin001' ? 'Origin' : obj, sub: '', kind: 'origin', type: ORIGIN_TYPE[obj], ref: obj === 'Origin001' ? 'Origin' : obj }
  const f = getState().features[part]?.features.find((x) => x.name === obj)
  if (!f) return obj === 'BaseFeature' ? { obj, sub: '', kind: 'element', type: 'Part::Feature', ref: obj } : null
  if (DATUM_TYPES[f.type]) return parsePick(part, role ? `${part}/${obj}/${role}` : `${part}/${obj}`)
  return { obj, sub: '', kind: 'element', type: f.type, ref: obj }
}

/** ReferenceSelection::allow: an Origin feature or a Part datum (App::DatumElement) through allowOrigin, a PartDesign datum
 *  (Part::Datum) through allowDatum, an element of the solid through allowPartFeature. */
export function allows(p: Picked, allow: Allow): boolean {
  if (p.kind === 'element' && !p.sub && p.type === 'Sketcher::SketchObject') return !!allow.face   // a Part2DObject, whole
  if (p.kind !== 'element') {
    if (p.type === 'App::Plane') return !!allow.face                         // allowOrigin
    if (p.type === 'App::Line') return !!allow.edge
    if (p.type.startsWith('App::')) return false                             // App::Point, an LCS whole
    if (p.type === 'PartDesign::Plane') return !!allow.face                  // allowDatum
    if (p.type === 'PartDesign::Line') return !!allow.edge
    if (p.type === 'PartDesign::Point') return !!allow.point
    return false
  }
  if (!p.sub) return !!allow.whole
  if (p.sub.startsWith('Vertex')) return !!allow.point
  if (p.sub.startsWith('Edge')) {
    if (allow.edge && (!allow.planar || p.type === 'Line')) return true      // isEdge: PLANAR asks for a line
    if (allow.circle && p.type === 'Circle') return true
  }
  if (p.sub.startsWith('Face') && allow.face && (!allow.planar || p.type === 'Plane')) return true
  if (allow.solid && (p.sub.startsWith('Face') || p.sub.startsWith('Edge'))) return true
  return false
}

/** getRefStr / TaskSketchBasedParameters::onAddSelection's text: "Pad:Face6", a datum's name, an LCS's feature as "LCS:XY_Plane001". */
export function refText(doc: FeatureDoc | undefined, r: Ref | null | undefined): string {
  if (r == null) return ''
  if (typeof r === 'string') return ORIGIN_TYPE[r] ? `Origin:${r}` : r     // the Origin is an LCS: (Origin, XY_Plane)
  const [o, s] = r
  const f = doc?.features.find((x) => x.name === o)
  if (f?.type === 'Part::LocalCoordinateSystem' && ROLES.some((role) => s.startsWith(role))) return `${o}:${lcsFeatureName(doc!, o, s)}`
  return s ? `${o}:${s}` : o
}
/** getRefStr, for a link FreeCAD keeps as the picked object itself (an axis, a mirror plane, a pattern's direction, a Draft's
 *  references): a datum or an Origin feature by its name, an LCS's feature by its own (Z_Axis001), else "Pad:Edge9". */
export function axisRefText(doc: FeatureDoc | undefined, r: Ref | null | undefined): string {
  if (r == null) return ''
  if (typeof r === 'string') return r
  const [o, s] = r
  const f = doc?.features.find((x) => x.name === o)
  if (f?.type === 'Part::LocalCoordinateSystem' && ROLES.some((role) => s.startsWith(role))) return lcsFeatureName(doc!, o, s)
  return s ? `${o}:${s}` : o
}
/** PatternReferenceWidget's text for a pattern's direction or axis: the object and the sub-element ("DatumLine:",
 *  "Pocket:Edge7"; an LCS's feature by its own name). */
export function patternRefText(doc: FeatureDoc | undefined, r: Ref | null | undefined): string {
  if (r == null) return ''
  if (typeof r === 'string') return `${r}:`
  const [o, s] = r
  const f = doc?.features.find((x) => x.name === o)
  if (f?.type === 'Part::LocalCoordinateSystem' && ROLES.some((role) => s.startsWith(role))) return `${lcsFeatureName(doc!, o, s)}:`
  return `${o}:${s}`
}
/** FreeCAD's name for an LCS's feature: its role and the LCS's number (XY_Plane001 for the first LCS), as the tree shows it. */
export function lcsFeatureName(doc: FeatureDoc, lcs: string, role: string): string {
  const k = doc.features.filter((x) => x.type === 'Part::LocalCoordinateSystem').findIndex((x) => x.name === lcs) + 1
  const r = ROLES.find((x) => role.startsWith(x)) ?? role
  return `${r}${String(k + (r === 'Origin' ? 1 : 0)).padStart(3, '0')}`
}

/** The solid a feature goes on: the solid feature before it (getBaseObject), the BaseFeature, or for a new one the Tip's
 *  solid; null when there is none (the Body's first solid). */
export function baseOf(doc: FeatureDoc, feature: string | null): string | null {
  const names = doc.features.map((f) => f.name)
  const solid = (f: Feature) => isSolid(f.type)
  const upto = feature && names.includes(feature) ? names.indexOf(feature) - 1 : doc.tip ? names.indexOf(doc.tip) : names.length - 1
  for (let i = upto; i >= 0; i--) if (solid(doc.features[i])) return doc.features[i].name
  return doc.base ? 'BaseFeature' : null
}

/** The base's mesh from the server (`cad feature shape`): the shape of the solid named, by FreeCAD's element names. */
export async function baseMesh(part: string, base: string): Promise<Mesh | null> {
  const slug = getState().slug, doc = getState().features[part]
  if (!slug || !doc) return null
  const names = doc.features.map((f) => f.name)
  // a feature's own shape, or for the BaseFeature the base of the first feature
  const feature = base === 'BaseFeature' ? names[0] : base
  if (!feature) return null
  try {
    const r = await api.featureShape(slug, part, [], feature)
    const d = r.data ?? {}
    return ((base === 'BaseFeature' ? d.base : d.shape ?? d.base) as Mesh) ?? null
  } catch { return null }
}

const partMatrix = (b: Body | undefined) => { const m = new THREE.Matrix4(); if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose(); return m }
/** The base solid, its faces and edges named "@Pad.Face6" for the view's helper picking (an edge over its face). */
export function baseObject(base: string, m: Mesh, body: Body | undefined): THREE.Object3D {
  const g = new THREE.Group()
  for (const f of m.faces) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    const mesh = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: SHAPE, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 }))
    mesh.userData.pickName = `${ELEMENT}${base}.${f.name}`
    g.add(mesh)
  }
  for (const e of m.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: LINE, linewidth: 2 }))
    line.userData.pickName = `${ELEMENT}${base}.${e.name}`
    line.userData.pickPriority = 1
    g.add(line)
  }
  g.applyMatrix4(partMatrix(body))
  return g
}

/** The Origin's axes while a panel shows them (setTemporaryVisibility(Axes), ViewProviderLine): each from 0.2 to 1 of
 *  DatumLineSize (70 px) along its axis, in the axis colours, screen-sized; each can be clicked. */
export function originAxes(body: Body | undefined): THREE.Object3D {
  const g = new THREE.Group(), size = 70, ac = getState().axisColors
  const scaled = new THREE.Group()
  scaled.userData.shapeScale = 1
  for (const [name, dir, color] of [['X_Axis', new THREE.Vector3(1, 0, 0), ac.x], ['Y_Axis', new THREE.Vector3(0, 1, 0), ac.y], ['Z_Axis', new THREE.Vector3(0, 0, 1), ac.z]] as const) {
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([dir.clone().multiplyScalar(0.2 * size), dir.clone().multiplyScalar(size)]),
      new THREE.LineBasicMaterial({ color, linewidth: 2 }))
    line.userData.pickName = name
    line.userData.pickPriority = 1
    scaled.add(line)
  }
  g.add(scaled)
  g.applyMatrix4(partMatrix(body))
  return g
}

/** Which of the Origin's features a panel shows for its whole life (TaskMirroredParameters: Planes; TaskRevolutionParameters,
 *  TaskPatternParameters: Axes): drawn while it is mounted, clickable while it picks. */
export function useOriginShown(part: string, what: 'planes' | 'axes' | null) {
  useEffect(() => {
    const view = getView()
    if (!view || !what) return
    const body = getState().scene?.bodies.find((b) => b.part === part)
    if (what === 'axes') view.setHelper('pd-pick-origin', originAxes(body))
    else view.setHelper('pd-pick-origin', originPlanes(body))
    view.rescaleHelpers()
    return () => { getView()?.setHelper('pd-pick-origin', null) }
  }, [part, what])
}

/** A datum's or an Origin feature's direction in the Body (getDirection: an axis's, a plane's normal), or null. */
export function datumDirection(doc: FeatureDoc | undefined, p: Picked): [number, number, number] | null {
  const role = p.kind === 'origin' ? p.obj : p.sub
  const roleDir: Record<string, [number, number, number]> = { X_Axis: [1, 0, 0], Y_Axis: [0, 1, 0], Z_Axis: [0, 0, 1], XY_Plane: [0, 0, 1], XZ_Plane: [0, -1, 0], YZ_Plane: [1, 0, 0] }
  if (p.kind === 'origin') return roleDir[role] ?? null
  if (p.kind !== 'datum') return null
  const f = doc?.features.find((x) => x.name === p.obj)
  const pl = f ? attachedOf(f)?.placement : null
  if (!pl) return null
  const d = new THREE.Vector3(...(p.sub ? roleDir[role] ?? [0, 0, 1] : [0, 0, 1])).transformDirection(placementMatrix(pl))
  return d.toArray().map((x) => Math.round(x * 1e12) / 1e12 + 0) as [number, number, number]
}

export type PickOptions = {
  part: string
  /** The feature the panel edits (left out of what can be picked; its base is the solid before it), or null for a new one. */
  feature: string | null
  /** The gate (ReferenceSelection's flags), 'any' for a panel that takes whatever is clicked (Add Feature), or a test of
   *  its own (a SelectionFilterGate such as "SELECT Part::Feature COUNT 1"). */
  allow: Allow | 'any' | ((p: Picked) => boolean)
  /** The status bar's message while picking (Gui::getMainWindow()->showMessage). */
  message?: string
  /** A pick the gate took; return false to stay in selection mode. */
  onPick(p: Picked): void
}
/** While `on`: the panel's reference selection mode (onSelectReference with a gate): the Body hidden and its base solid shown
 *  and pickable, the gate on the view, preselection under the pointer, and the picks handed to onPick. Off again, all back. */
export function useRefPick(on: boolean, opts: PickOptions) {
  const optsRef = useRef(opts)
  optsRef.current = opts
  const [mesh, setMesh] = useState<{ base: string; mesh: Mesh } | null>(null)
  const doc = getState().features[opts.part]
  const base = doc ? baseOf(doc, opts.feature) : null
  // the base's shape, asked for when picking first starts and kept while the panel is open (a mode armed again shows it
  // at once, as FreeCAD's showBase does)
  useEffect(() => {
    if (!on || !base || mesh?.base === base) return
    let live = true
    void baseMesh(opts.part, base).then((m) => { if (live && m) setMesh({ base, mesh: m }) })
    return () => { live = false }
  }, [on, base, opts.part])
  // startReferenceSelection: the shown feature hides, the base shows
  useEffect(() => {
    if (!on) return
    const b = getState().scene?.bodies.find((x) => x.part === opts.part)?.name
    if (!b) return
    const was = getState().hidden.includes(b)
    if (!was) { tempHidden.add(b); setState((x) => ({ hidden: [...x.hidden, b] })) }
    return () => { if (!was) { setState((x) => ({ hidden: x.hidden.filter((n) => n !== b) })); tempHidden.delete(b) } }
  }, [on, opts.part])
  useEffect(() => {
    const view = getView()
    if (!view) return
    if (!on || !mesh) { view.setHelper('pd-pick', null); return }
    view.setHelper('pd-pick', baseObject(mesh.base, mesh.mesh, getState().scene?.bodies.find((x) => x.part === opts.part)))
    return () => { getView()?.setHelper('pd-pick', null) }
  }, [on, mesh])
  // the gate, the preselection's status message and the picks
  useEffect(() => {
    const view = getView()
    if (!view || !on) return
    const kinds: Record<string, string | null | undefined> = {}
    const ends: Record<string, number[]> = {}
    for (const f of mesh?.mesh.faces ?? []) kinds[f.name] = f.kind
    for (const e of mesh?.mesh.edges ?? []) { kinds[e.name] = e.kind; ends[e.name] = e.points }
    const parse = (name: string): Picked | null => {
      const p = parsePick(optsRef.current.part, name, kinds)
      if (!p) return null
      // the direction a straight edge or a datum gives (FeatureExtrude's Direction after the pick)
      const pts = p.kind === 'element' ? ends[p.sub] : undefined
      if (pts && pts.length >= 6 && p.type === 'Line') {
        const n = pts.length
        const d = new THREE.Vector3(pts[n - 3] - pts[0], pts[n - 2] - pts[1], pts[n - 1] - pts[2]).normalize()
        p.dir = d.toArray().map((x) => Math.round(x * 1e12) / 1e12 + 0) as [number, number, number]
      } else p.dir = datumDirection(getState().features[optsRef.current.part], p) ?? undefined
      return p
    }
    const slug = getState().slug ?? 'Unnamed'
    const own = (p: Picked) => p.obj !== optsRef.current.feature
    const gate = (p: Picked) => { const a = optsRef.current.allow; return a === 'any' ? true : typeof a === 'function' ? a(p) : allows(p, a) }
    view.helperGate = (name) => {
      const p = parse(name)
      if (p && own(p) && gate(p)) return true
      return `Not allowed: ${slug}.${optsRef.current.part}.${p ? (p.sub ? `${p.obj}.${p.sub}` : p.obj) : name} `
    }
    view.helperHover = (name, refused) => {
      const p = name ? parse(name) : null
      setState({ gateMsg: refused, preselected: p ? optsRef.current.part : null, preSub: p ? `${optsRef.current.part}.${p.sub ? `${p.obj}.${p.sub}` : p.obj}` : null, prePoint: null })
    }
    view.helperPicker = (name) => { const p = parse(name); if (p) optsRef.current.onPick(p) }
    if (optsRef.current.message) setState({ gateMsg: optsRef.current.message })
    // the tree's rows are picked through the same gate (a refused one is not taken)
    setAttachPicker((row) => {
      const p = parseRow(optsRef.current.part, row)
      if (p) p.dir = datumDirection(getState().features[optsRef.current.part], p) ?? undefined
      if (p && p.obj !== optsRef.current.feature && gate(p)) optsRef.current.onPick(p)
      else setState({ gateMsg: 'Selection not allowed by filter' })
    })
    return () => {
      setAttachPicker(null)
      const w = getView()
      if (w) { w.helperGate = null; w.helperHover = datumHover; w.helperPicker = null }
      setState({ gateMsg: null, preselected: null, preSub: null })
    }
  }, [on, mesh])
}

// ── a datum in the 3D view is selected by a click on it (outside the panels that pick) ──
/** The status bar's "Preselected: …" for a datum under the pointer. */
export function datumHover(name: string | null) {
  const [part, obj, role] = (name ?? '').split('/')
  setState({ preselected: name ? part : null, preSub: name ? `${part}.${obj}${role ? `.${role}` : ''}` : null, prePoint: null })
}
function datumSelect(name: string, additive: boolean) {
  const [part, obj, role] = name.split('/')
  const doc = getState().features[part]
  if (!doc || !obj || !doc.features.some((f) => f.name === obj)) return
  const ref = role ? `${part}/${obj}/${role}` : `${part}/${obj}`
  const s = getState()
  const featSel = additive ? (s.featSel.includes(ref) ? s.featSel.filter((r) => r !== ref) : [...s.featSel, ref]) : [ref]
  setState({ featSel, selected: [], subSel: [] })
}
subscribe(() => {
  const v = getView()
  if (!v || v.helperSelect) return
  v.helperSelect = datumSelect
  if (!v.helperHover) v.helperHover = datumHover
})
