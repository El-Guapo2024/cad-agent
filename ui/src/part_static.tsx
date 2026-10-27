// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/Gui/CommandSimple.cpp: 2002 Jürgen Riegel (Part_SimpleCopy, Part_TransformedCopy, Part_ElementCopy)
//   src/Mod/Part/Gui/Command.cpp: 2002 Jürgen Riegel (Part_MakeSolid, Part_CrossSections, Part_Builder)
//   src/Mod/Part/Gui/CrossSections.cpp: 2012 Werner Mayer (the dialog and its planes)
//   src/Mod/Part/Gui/TaskShapeBuilder.cpp: 2011 Werner Mayer
//   src/Mod/Part/BOPTools/ToleranceFeatures.py: 2024 Eric Price (CorvusCorax) (Part_ToleranceSet)
//   No copyright line in the file: src/Mod/Part/Gui/CrossSections.ui, src/Mod/Part/Gui/TaskShapeBuilder.ui
// The Part commands that make a Part::Feature holding a shape (cad_agent/feature_part_static.py): Simple, Transformed and
// Element copy, Convert to solid, Set tolerance, and the two with a panel, Cross-sections and the Shape builder. FreeCAD
// runs Python that sets the new object's Shape; the part file holds the recipe (docs/EDITING_PLAN.md, "Static objects in a
// part file"), so each command writes that object in the transaction FreeCAD opens for it.
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api, type FeatureOp } from './api'
import { getState, report, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, getView } from './actions'
import { TaskBox } from './panels'
import { messageBox } from './msgbox'
import { applyOps, bodyOfPart } from './partdesign'
import { activeDoc, labelOf, objectOf, openPart, selectedObjects, uniqueLabel, uniqueName } from './part_wb'
import { parsePartPick, partMatrix, usePartScene, type Mesh } from './part_pick'
import { Buttons, Check, Field, Q, Radio } from './part_tasks'
import { LENGTH } from './qsb'

// ── what the server says of an object's shape ────────────────────────────────────────────────────────────────────────
export type ShapeInfo = { type: string | null; bbox: number[] | null; error?: string | null }
/** An object's ShapeType and bounding box, from the server's build of it (`cad feature shape`). */
export async function shapeInfo(part: string, name: string): Promise<ShapeInfo> {
  const s = getState()
  if (!s.slug) return { type: null, bbox: null }
  const doc = s.features[part]
  try {
    const r = await api.featureShape(s.slug, part, [], name === 'Body' ? doc?.tip ?? undefined : name)
    const d = r.data ?? {}
    return { type: (d.shape_type as string | null) ?? null, bbox: (d.bbox as number[] | null) ?? null, error: d.error as string | null }
  } catch { return { type: null, bbox: null } }
}
const sourceOf = (doc: FeatureDoc | undefined, name: string) => objectOf(doc, name) ?? doc?.features?.find((f) => f.name === name)

// ── Part_SimpleCopy, Part_TransformedCopy, Part_ElementCopy (CommandSimple.cpp's _copyShape) ─────────────────────────────
/** A Part::Feature for each selected object: `Part.getShape(obj, '')` set as the Shape of an object named after it and
 *  labelled with its Label, in "Simple copy" / "Transformed copy" / "Element copy". The page's selection is whole objects, so
 *  the three make the same copy; a part file's ("Box", "Face3") source is the element copy of a picked element. */
export async function copyShapes(cmd: 'Part_SimpleCopy' | 'Part_TransformedCopy' | 'Part_ElementCopy') {
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  if (!part || !sel.length) return
  const tx = cmd === 'Part_SimpleCopy' ? 'Simple copy' : cmd === 'Part_TransformedCopy' ? 'Transformed copy' : 'Element copy'
  let d = getState().features[part]
  const ops: FeatureOp[] = []
  for (const s of sel) {
    const src = sourceOf(d, s)
    const name = uniqueName(d, s)
    const label = uniqueLabel(d, src ? labelOf(src) : s)
    ops.push({ op: 'add', feature: { name, type: 'Part::Feature', source: s, ...(label !== name ? { label } : {}) } })
    d = { ...d, objects: [...(d.objects ?? []), { name, type: 'Part::Feature', label }] }
  }
  await applyOps(part, ops, { name: tx })
}

// ── Part_MakeSolid (CmdPartMakeSolid::activated) ────────────────────────────────────────────────────────────────────────
/** A solid from each selected shell, compound or compsolid, "<name>_solid" labelled "<Label> (Solid)"; a solid, and a shape
 *  of another type, is left out with the message the Report view gets. One "Make solid" step. */
export async function convertToSolid() {
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  if (!part || !sel.length) return
  let d = getState().features[part]
  const ops: FeatureOp[] = []
  for (const s of sel) {
    const info = await shapeInfo(part, s)
    if (!info.type) continue
    const src = sourceOf(d, s)
    const label = src ? labelOf(src) : s
    if (info.type === 'Solid') { report('msg', `${label} is ignored because it is already a solid.`); continue }
    if (!['Compound', 'CompSolid', 'Shell'].includes(info.type)) { report('msg', `${label} is ignored because it is neither a shell nor a compound.`); continue }
    const name = uniqueName(d, `${s}_solid`)
    const lab = uniqueLabel(d, `${label} (Solid)`)
    ops.push({ op: 'add', feature: { name, type: 'Part::MakeSolid', source: s, ...(lab !== name ? { label: lab } : {}) } })
    d = { ...d, objects: [...(d.objects ?? []), { name, type: 'Part::MakeSolid', label: lab }] }
  }
  if (ops.length) await applyOps(part, ops, { name: 'Make solid' })
}

// ── Part_ToleranceSet (ToleranceFeatures.cmdCreateToleranceSetFeature) ───────────────────────────────────────────────────
/** One "Tolerance" (a FeaturePython) with minTolerance 1e-7 and maxTolerance 0 over the selected objects, which it hides;
 *  "Create ToleranceSet". With nothing selected FreeCAD's message box. */
export async function setTolerance() {
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  if (!part) return
  if (!sel.length) { await messageBox('warning', 'Bad Selection', 'Select at least one object or compounds'); return }
  const name = uniqueName(getState().features[part], 'Tolerance')
  await applyOps(part, [{ op: 'add', feature: { name, type: 'Part::ToleranceSet', objects: sel, min_tolerance: 1e-7 } }], { name: 'Create ToleranceSet' })
}

// ── Part_CrossSections (CrossSections.cpp) ───────────────────────────────────────────────────────────────────────────────
type Box = [number, number, number, number, number, number]       // xmin ymin zmin xmax ymax zmax
let crossBox: Box = [0, 0, 0, 0, 0, 0]
/** CmdPartCrossSections::activated: the panel over the bounding box of the shapes selected. */
export async function openCrossSections() {
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  if (!part || !sel.length) return
  let box: Box | null = null
  for (const s of sel) {
    const b = (await shapeInfo(part, s)).bbox
    if (!b) continue
    box = box ? [Math.min(box[0], b[0]), Math.min(box[1], b[1]), Math.min(box[2], b[2]), Math.max(box[3], b[3]), Math.max(box[4], b[4]), Math.max(box[5], b[5])] : b as Box
  }
  crossBox = box ?? [0, 0, 0, 0, 0, 0]
  openPart('crosssections')
}
const AXES = { XY: 2, XZ: 1, YZ: 0 } as const
type Plane = keyof typeof AXES
const g6 = (x: number) => Number(x.toPrecision(6))              // QString::arg(double) with its 'g' and precision -1: six digits
/** The corners of the guiding plane's rectangle at one position (CrossSections::makePlanes), closed. */
function planeLoop(plane: Plane, box: Box, at: number): THREE.Vector3[] {
  const [x0, y0, z0, x1, y1, z1] = box
  const v = plane === 'XY' ? [[x0, y0, at], [x1, y0, at], [x1, y1, at], [x0, y1, at]]
    : plane === 'XZ' ? [[x0, at, z0], [x1, at, z0], [x1, at, z1], [x0, at, z1]]
      : [[at, y0, z0], [at, y1, z0], [at, y1, z1], [at, y0, z1]]
  return [...v, v[0]].map(([x, y, z]) => new THREE.Vector3(x, y, z))
}
export function CrossSectionsTask({ part }: { part: string }) {
  const box = crossBox
  const centre = (p: Plane) => (box[AXES[p]] + box[AXES[p] + 3]) / 2
  const length = (p: Plane) => box[AXES[p] + 3] - box[AXES[p]]
  const [plane, setPlane] = useState<Plane>('XY')
  const [position, setPosition] = useState(centre('XY'))
  const [sections, setSections] = useState(false)
  const [both, setBoth] = useState(false)
  const [count, setCount] = useState(1)
  const [distance, setDistance] = useState(0)
  const spacing = (p: Plane, n: number, b: boolean) => (length(p) / n) * (b ? 1 : 0.5)
  const planes = (): number[] => {
    if (!sections) return [position]
    const start = both ? position - 0.5 * (count - 1) * distance : position
    return Array.from({ length: count }, (_, i) => start + i * distance)
  }
  // the dialog's own handlers: a plane, the Sections box, On both sides and Count move Position and Distance as they do
  const pickPlane = (p: Plane) => { setPlane(p); setPosition(centre(p)); if (sections) setDistance(spacing(p, count, both)) }
  const toggleSections = (on: boolean) => {
    setSections(on)
    if (on) setDistance(spacing(plane, count, both)); else setPosition(centre(plane))
  }
  const toggleBoth = (on: boolean) => { setBoth(on); setDistance(on ? 2 * distance : 0.5 * distance) }
  const changeCount = (n: number) => { const c = Math.max(1, Math.min(2000000, Math.round(n) || 1)); setCount(c); setDistance(spacing(plane, c, both)) }
  // the planes drawn in the 3D view (ViewProviderCrossSections: 2 px lines, rgb 1.0 0.447 0.337)
  const shown = JSON.stringify(planes())
  const view = getView()
  useEffect(() => {
    const v = getView()
    if (!v) return
    const g = new THREE.Group()
    for (const at of JSON.parse(shown) as number[]) {
      const geo = new THREE.BufferGeometry().setFromPoints(planeLoop(plane, box, at))
      g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: new THREE.Color(1.0, 0.447059, 0.337255) })))
    }
    g.applyMatrix4(partMatrix(bodyOfPart(getState(), part)))
    v.setHelper('pt-cross-sections', g)
    return () => getView()?.setHelper('pt-cross-sections', null)
  }, [shown, plane, view, part])
  const apply = async (close: boolean) => {
    const sel = selectedObjects(part)
    const ds = planes().map(g6)
    let doc = getState().features[part]
    const ops: FeatureOp[] = []
    for (const n of sel) {
      if (!(await shapeInfo(part, n)).type) continue
      const name = uniqueName(doc, `${n}_cs`)
      ops.push({ op: 'add', feature: { name, type: 'Part::CrossSections', base: n, plane, positions: ds } })
      doc = { ...doc, objects: [...(doc.objects ?? []), { name, type: 'Part::CrossSections' }] }
    }
    if (close) closeTask()
    if (ops.length) await applyOps(part, ops, { name: 'Cross-sections' })
  }
  return (
    <div className="tasks pt-task" data-task="crosssections">
      <Buttons items={[['OK', () => void apply(true), true], ['Cancel', closeTask], ['Apply', () => void apply(false)]]} />
      <TaskBox title="Cross Sections" icon="pt-cross-sections">
        <fieldset className="tgroup" data-qf="planeBox"><legend>Guiding Plane</legend>
          <div className="trow">{(['XY', 'XZ', 'YZ'] as Plane[]).map((p) => <Radio key={p} name={`${p.toLowerCase()}Plane`} label={p} checked={plane === p} onChange={() => pickPlane(p)} />)}</div>
          <Q label="Position" name="position" value={position} min={-1.7e308} max={1.7e308} onChange={setPosition} />
        </fieldset>
        <fieldset className="tgroup" data-qf="sectionsBox">
          <legend><label className="tcheck"><input type="checkbox" checked={sections} onChange={(e) => toggleSections(e.target.checked)} /> Sections</label></legend>
          <Check name="checkBothSides" label="On both sides" checked={both} disabled={!sections} onChange={toggleBoth} />
          <Field label="Count"><span data-qf="countSections"><input type="number" min={1} max={2000000} step={1} value={count} disabled={!sections}
            onChange={(e) => changeCount(Number(e.target.value))} /></span></Field>
          <Q label="Distance" name="distance" value={distance} min={0} max={1.7e308} disabled={!sections} onChange={setDistance} dims={LENGTH} />
        </fieldset>
      </TaskBox>
    </div>
  )
}

// ── Part_Builder (TaskShapeBuilder.cpp) ───────────────────────────────────────────────────────────────────────────────────
const MODES = ['Edge from vertices', 'Wire from edges', 'Face from vertices', 'Face from edges', 'Shell from faces', 'Solid from shell'] as const
type Mode = (typeof MODES)[number]
const RADIO = ['radioButtonEdgeFromVertex', 'radioButtonWireFromEdge', 'radioButtonFaceFromVertex', 'radioButtonFaceFromEdge', 'radioButtonShellFromFace', 'radioButtonSolidFromShell']
const HINT: Record<Mode, string> = { 'Edge from vertices': 'Select two vertices to create an edge', 'Wire from edges': 'Select adjacent edges',
  'Face from vertices': 'Select vertices', 'Face from edges': 'Select a closed loop of edges', 'Shell from faces': 'Select adjacent faces',
  'Solid from shell': 'All shape types can be selected' }
const KIND: Record<Mode, 'Vertex' | 'Edge' | 'Face' | null> = { 'Edge from vertices': 'Vertex', 'Wire from edges': 'Edge', 'Face from vertices': 'Vertex',
  'Face from edges': 'Edge', 'Shell from faces': 'Face', 'Solid from shell': null }
const BASE: Record<Mode, string> = { 'Edge from vertices': 'Edge', 'Wire from edges': 'Wire', 'Face from vertices': 'Face', 'Face from edges': 'Face',
  'Shell from faces': 'Shell', 'Solid from shell': 'Solid' }
const NEED: Record<Mode, [number, number | null, string]> = { 'Edge from vertices': [2, 2, 'Select two vertices'], 'Wire from edges': [1, null, 'Select at least 1 edge'],
  'Face from vertices': [3, null, 'Select three or more vertices'], 'Face from edges': [1, null, 'Select at least 1 edge'],
  'Shell from faces': [2, null, 'Select at least 2 faces'], 'Solid from shell': [1, 1, 'Select only 1 shape object'] }
type Pick = [string, string]                                       // object, element
export function ShapeBuilderTask({ part }: { part: string }) {
  const doc = useStore((s) => s.features[part])
  const [mode, setMode] = useState<Mode>(MODES[0])
  const [planar, setPlanar] = useState(false)
  const [refine, setRefine] = useState(true)
  const [allFaces, setAllFaces] = useState(false)
  const [picks, setPicks] = useState<Pick[]>([])
  const kind = KIND[mode]
  const switchMode = (m: Mode) => { setMode(m); setPicks([]) }                // switchMode clears the selection
  const planarOn = mode === 'Wire from edges' || mode === 'Face from vertices' || mode === 'Face from edges'
  const refineOn = mode === 'Shell from faces' || mode === 'Solid from shell'
  const facesOn = mode === 'Shell from faces'
  const meshes_ = useRef<Record<string, Mesh>>({})
  // ShapeSelection's gate: the kind the mode asks for; the last mode takes anything, a whole object included (the tree)
  const meshes = usePartScene({ part, active: !!doc, vertices: true, helperKey: 'pt-builder', gateKey: mode,
    allow: (_o, el) => (kind ? el.startsWith(kind) : true),
    onPick: (name) => {
      const p = parsePartPick(name)
      if (!p) return
      setPicks((cur) => (cur.some((x) => x[0] === p[0] && x[1] === p[1]) ? cur.filter((x) => !(x[0] === p[0] && x[1] === p[1])) : [...cur, p]))
      // Shell from faces with All faces: the shape's every face joins the selection (onSelectionChanged)
      if (facesOn && allFaces) setPicks((cur) => { const m = meshes_.current[p[0]]; return m ? [...cur, ...m.faces.map((f): Pick => [p[0], f.name]).filter(([o, e]) => !cur.some((x) => x[0] === o && x[1] === e))] : cur })
    } })
  meshes_.current = meshes
  // the elements picked, drawn in the selection colour over the shapes
  const key = JSON.stringify(picks)
  useEffect(() => {
    const v = getView()
    if (!v) return
    const g = new THREE.Group()
    const color = new THREE.Color(getState().selPrefs.color)
    for (const [o, el] of JSON.parse(key) as Pick[]) {
      const m = meshes[o]
      if (!m) continue
      if (el.startsWith('Vertex')) {
        const vx = m.vertices?.find((x) => x.name === el)
        if (!vx) continue
        const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(vx.point, 3))
        g.add(new THREE.Points(geo, new THREE.PointsMaterial({ color, size: 9, sizeAttenuation: false })))
      } else if (el.startsWith('Edge')) {
        const e = m.edges.find((x) => x.name === el)
        if (!e) continue
        const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(e.points, 3))
        g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color, linewidth: 3 })))
      } else {
        const f = m.faces.find((x) => x.name === el)
        if (!f) continue
        const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(f.points, 3)); geo.setIndex(f.index)
        g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, transparent: true, opacity: 0.6, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })))
      }
    }
    g.applyMatrix4(partMatrix(bodyOfPart(getState(), part)))
    v.setHelper('pt-builder-sel', g.children.length ? g : null)
    return () => getView()?.setHelper('pt-builder-sel', null)
  }, [key, meshes, part])
  const create = async () => {
    const [min, max, text] = NEED[mode]
    // the picks grouped by object in the order the objects were first picked (Gui::SelectionObject), each object's elements in pick order
    const order = [...new Set(picks.map((p) => p[0]))]
    let elements: (string | Pick)[] = order.flatMap((o) => picks.filter((p) => p[0] === o))
    if (mode === 'Solid from shell') {
      const objs = [...new Set([...selectedObjects(part), ...order])]
      if (objs.length !== 1) { await messageBox('critical', 'Wrong Selection', text); return }
      elements = [objs[0]]
    } else if (elements.length < min || (max !== null && elements.length !== max)) { await messageBox('critical', 'Wrong Selection', text); return }
    const d = getState().features[part]
    const name = uniqueName(d, BASE[mode])
    const props: Record<string, unknown> = { mode, elements }
    if (planarOn && planar) props.planar = true
    if (refineOn && !refine) props.refine = false
    if (facesOn && allFaces) props.all_faces = true
    setPicks([])
    await applyOps(part, [{ op: 'add', feature: { name, type: 'Part::ShapeBuilder', ...props } as Feature }], { name: BASE[mode] })
  }
  if (!doc) return null
  return (
    <div className="tasks pt-task" data-task="builder">
      <Buttons items={[['Close', closeTask]]} />
      <TaskBox title="Create Shape" icon="pt-builder">
        <fieldset className="tgroup" data-qf="groupBox"><legend>Create Shape</legend>
          {MODES.map((m, i) => <Radio key={m} name={RADIO[i]} label={m} checked={mode === m} onChange={() => switchMode(m)} />)}
          <hr />
          <Check name="checkPlanar" label="Planar" checked={planar} disabled={!planarOn} onChange={setPlanar} />
          <Check name="checkRefine" label="Refine shape" checked={refine} disabled={!refineOn} onChange={setRefine} />
          <Check name="checkFaces" label="All faces" checked={allFaces} disabled={!facesOn} onChange={setAllFaces} />
          <div className="trow">
            <button className="qbtn" data-qf="selectButton" disabled title="A box dragged over the 3D view picks the faces of the scene's one merged body, not an object's: pick in the view one by one">Box Selection</button>
            <button className="qbtn" data-qf="createButton" onClick={() => void create()}>Create</button>
          </div>
        </fieldset>
        <label className="tlabel" data-qf="label">{HINT[mode]}</label>
      </TaskBox>
    </div>
  )
}
