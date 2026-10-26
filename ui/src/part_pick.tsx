// SPDX-License-Identifier: LGPL-2.1-or-later
// Part objects in the 3D view, for the task panels that ask for a face, an edge or a vertex: their shapes as the server
// builds them (`cad feature shape`, cad_agent/feature_shape.py), each face and edge named as FreeCAD names it (Face1,
// Edge1), drawn as helpers the view can pick. While such a panel picks, the document's objects are drawn this way in
// place of the scene's one body per part, so the click comes back as the part file writes it: ("Base", "Face6"). The
// Attachment editor (pd_attach.tsx) draws the object it moves from this module too, at the Placement the panel's
// attacher gives it.
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api, type Body, type FeatureOp } from './api'
import { getState, type Feature, type FeatureDoc } from './store'
import { getView } from './actions'
import { isBinder, isDatum, placementMatrix, type PlacementData } from './attached'

/** The mesh `cad feature shape` gives a shape: faces as triangles, edges as polylines, by FreeCAD's element names. */
export type Mesh = {
  faces: { name: string; points: number[]; index: number[]; kind?: string }[]
  edges: { name: string; points: number[]; kind?: string | null }[]
}
export type MeshStyle = { face?: THREE.ColorRepresentation; edge?: THREE.ColorRepresentation; opacity?: number }
const SKETCH = 'Sketcher::SketchObject'
const STYLE: MeshStyle = { face: 0xcccccc, edge: 0x1a1a1a }

const bodyOfPart = (part: string, s = getState()): Body | undefined => s.scene?.bodies.find((b) => b.part === part)
export function partMatrix(body: Body | undefined): THREE.Matrix4 {
  const m = new THREE.Matrix4()
  if (body?.matrix?.length === 16) m.fromArray(body.matrix).transpose()
  return m
}

/** The solid the 3D view shows for a Body: the last solid feature up to its Tip (a sketch, a datum or a binder as the
 *  Tip leaves the one before it), whose elements a click in the 3D view names. */
export function tipFeature(doc: FeatureDoc): string | null {
  const solidOf = (f: Feature) => f.type !== SKETCH && !isDatum(f.type) && !isBinder(f.type)
  const upto = doc.tip ? doc.features.findIndex((f) => f.name === doc.tip) : doc.features.length - 1
  const solids = doc.features.slice(0, upto + 1).filter(solidOf)
  return solids.length ? solids[solids.length - 1].name : doc.base ? 'BaseFeature' : null
}

/** What the document shows, as FreeCAD does: every object its visibility says so for (Part.visible), the Body's sketches
 *  until an object that uses one hides it, and the Body's Tip solid. */
export function shownNames(doc: FeatureDoc | undefined): string[] {
  if (!doc) return []
  const tree = doc.object_tree
  const out: string[] = []
  for (const o of doc.objects ?? []) {
    if (o.type === SKETCH) { if (tree ? (tree.sketches_shown ?? []).includes(o.name) : true) out.push(o.name); continue }
    if (tree ? tree.shown.includes(o.name) : true) out.push(o.name)
  }
  const tip = doc.body ? tipFeature(doc) : null
  if (tip && !out.includes(tip)) out.push(tip)
  return out
}

/** One object's shape in the part's frame, from the server: its own solid for a feature (or the BaseFeature's base of the
 *  first feature), a Part object's as Part.evaluate placed it. Null when it fails (FreeCAD leaves a failed object with no
 *  shape). */
export async function partMesh(part: string, name: string, ops: FeatureOp[] = []): Promise<Mesh | null> {
  const slug = getState().slug, doc = getState().features[part]
  if (!slug || !doc) return null
  const feature = name === 'BaseFeature' ? doc.features[0]?.name : name
  if (!feature) return null
  try {
    const r = await api.featureShape(slug, part, ops, feature)
    if (r.exit > 2) return null
    const d = r.data ?? {}
    if (d.error) return null
    return ((name === 'BaseFeature' ? d.base : d.shape ?? d.base) as Mesh) ?? null
  } catch { return null }
}

/** One object's faces and edges, named "@Base.Face6" for the view's helper picking (an edge over the face it lies on). The
 *  faces may be left out (an edge picker does not draw them over the shape already in the scene); nothing is pickable
 *  without a pickName, which the view skips in its raycast. */
export function meshObject(name: string, mesh: Mesh, opts: { matrix?: THREE.Matrix4; style?: MeshStyle; faces?: boolean
  pick?: (element: string, face: boolean) => boolean } = {}): THREE.Group {
  const style = opts.style ?? STYLE
  const opacity = style.opacity ?? 1
  const g = new THREE.Group()
  if (opts.faces !== false) for (const f of mesh.faces) {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3))
    geo.setIndex(f.index)
    geo.computeVertexNormals()
    // a transparent face is a tint over the shape already drawn (Thickness' faces), pulled in front of it; an opaque one
    // gives way to it, so a picker that draws the whole document over the scene's body does not z-fight with it
    const off = opacity < 1 ? -1 : 1
    const mesh3 = new THREE.Mesh(geo, new THREE.MeshPhongMaterial({ color: style.face ?? STYLE.face, side: THREE.DoubleSide,
      transparent: opacity < 1, opacity, depthWrite: opacity >= 1, polygonOffset: true, polygonOffsetFactor: off, polygonOffsetUnits: off }))
    if (opts.pick?.(f.name, true)) mesh3.userData.pickName = `@${name}.${f.name}`
    g.add(mesh3)
  }
  for (const e of mesh.edges) {
    if (e.points.length < 6) continue
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: style.edge ?? STYLE.edge, linewidth: 2 }))
    if (opts.pick?.(e.name, false)) { line.userData.pickName = `@${name}.${e.name}`; line.userData.pickPriority = 1 }
    g.add(line)
  }
  if (opts.matrix) g.applyMatrix4(opts.matrix)
  return g
}

/** "Base.Face6" back from a helper's pickName: the object and its element. */
export function parsePartPick(name: string): [string, string] | null {
  if (!name.startsWith('@')) return null
  const i = name.lastIndexOf('.')
  return i > 1 ? [name.slice(1, i), name.slice(i + 1)] : null
}

/** An object drawn at a Placement instead of where the document has it (the Attachment editor's live preview). */
export type SceneTarget = { name: string; mesh: Mesh; placement: PlacementData | null }
const TARGET: MeshStyle = { face: '#ffaa00', edge: '#b26b00', opacity: 0.55 }

/**
 * While `active`, the document's shown objects as helpers with their faces and edges named for picking, and the Body's
 * Tip (the solid a Body shows) with it; the scene's own body stays where it is, so a panel that overlays one shape (Fillet's
 * edges) draws over it. `allow` says which element of which object a click takes (nothing when it is left out) and
 * `onPick` gets the helper's name, which may also be a datum's ("part/DatumPlane", pd_attach.tsx's) or an Origin plane's
 * ("XY_Plane") when such a helper is shown: the panel reads it as it reads its own. `only` draws those objects alone (a
 * panel that picks the elements of one shape, Fillet's). `target` is drawn, not picked. Returns the meshes, by object
 * name, for the panel's counts.
 */
export function usePartScene(opts: { part: string; active: boolean; extra?: string[]; only?: string[]; allow?: (obj: string, element: string, face: boolean) => boolean
  onPick?: (name: string) => void; target?: SceneTarget | null; style?: MeshStyle; helperKey?: string }): Record<string, Mesh> {
  const [meshes, setMeshes] = useState<Record<string, Mesh>>({})
  const allow = useRef(opts.allow), pick = useRef(opts.onPick)
  allow.current = opts.allow
  pick.current = opts.onPick
  const key = opts.helperKey ?? 'part-pick'
  const extra = JSON.stringify(opts.extra ?? []), only = JSON.stringify(opts.only ?? null)
  useEffect(() => {
    if (!opts.active) { setMeshes({}); return }
    const doc = getState().features[opts.part]
    const o = JSON.parse(only) as string[] | null
    const names = o ?? [...new Set([...shownNames(doc), ...(JSON.parse(extra) as string[])])]
    let live = true
    void Promise.all(names.map(async (n) => [n, await partMesh(opts.part, n)] as const)).then((pairs) => {
      if (live) setMeshes(Object.fromEntries(pairs.filter((p): p is [string, Mesh] => !!p[1])))
    })
    return () => { live = false }
  }, [opts.active, opts.part, extra, only])
  const styleKey = JSON.stringify(opts.style ?? {}), targetKey = JSON.stringify([opts.target?.name, opts.target?.placement])
  useEffect(() => {
    const view = getView()
    if (!view) return
    if (!opts.active) { view.setHelper(key, null); view.rescaleHelpers(); return }
    const m = partMatrix(bodyOfPart(opts.part))
    const g = new THREE.Group()
    const anyFace = Object.entries(meshes).some(([n, mesh]) => mesh.faces.some((f) => allow.current?.(n, f.name, true)))
    for (const [name, mesh] of Object.entries(meshes)) {
      if (opts.target?.name === name) continue
      g.add(meshObject(name, mesh, { matrix: m, style: opts.style, faces: anyFace, pick: (el, face) => !!allow.current?.(name, el, face) }))
    }
    if (opts.target) {
      const local = opts.target.placement ? placementMatrix(opts.target.placement) : new THREE.Matrix4()
      g.add(meshObject(opts.target.name, opts.target.mesh, { matrix: m.clone().multiply(local), style: TARGET }))
    }
    view.setHelper(key, g.children.length ? g : null)
    const mine = (name: string) => pick.current?.(name)
    view.helperPicker = mine
    view.rescaleHelpers()
    return () => {
      const w = getView()
      // another panel's picker may have taken over meanwhile: only this one's is cleared
      if (w) { w.setHelper(key, null); if (w.helperPicker === mine) w.helperPicker = null }
    }
  }, [opts.active, meshes, styleKey, targetKey, key])
  return meshes
}
