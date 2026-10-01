// Std_Measure (Measure/Gui/TaskMeasure.cpp) and Std_MeasureMassProperties
// (Measure/Gui/TaskMassProperties.cpp) at FreeCAD main 3160daf1e2b6 (LGPL-2.1-or-later).
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { Vec3 } from './api'
import { getState, report, saved, setState, useStore } from './store'
import { DIM_GAP_PX, measurePair, subInfo } from './viewer'
import { closeTask, getView } from './actions'
import { api, resultText } from './api'
import { TaskBox, TaskButtons, vec } from './panels'
import { QComboBox } from './combo'
import * as quantity from './quantity'
import { toUnicodeSuperscript } from './superscript'

/** Std_Measure for two placed parts, through `cad measure --posed`. */
/** Measure/App's measure types, in MeasureManager's order (AppMeasure.cpp). */
const MEASURE_TYPES = ['Distance', 'Distance Free', 'Angle', 'Length', 'Position', 'Area', 'Diameter', 'Radius', 'Geometric Center'] as const
type MeasureType = (typeof MEASURE_TYPES)[number]
/** TaskMeasure's unit lists by quantity. */
const MEASURE_UNITS: Record<string, string[]> = {
  Length: ['nm', 'µm', 'mm', 'cm', 'dm', 'm', 'km', 'in', 'ft', 'thou', 'yd', 'mi'], Angle: ['deg', 'rad', 'gon'],
  Area: ['mm^2', 'cm^2', 'm^2', 'km^2', 'in^2', 'ft^2', 'yd^2', 'mi^2'],
}
/** Each measure type's quantity dimensions ([length, mass, time, current, temp, amount,
 *  intensity, angle]), for unit conversion and the unit combo's default (TaskMeasure's
 *  unitForMeasureType + preferredUnitForMeasureType, via Base::UnitsApi::schemaTranslate). */
const QD = { Length: [1, 0, 0, 0, 0, 0, 0, 0], Angle: [0, 0, 0, 0, 0, 0, 0, 1], Area: [2, 0, 0, 0, 0, 0, 0, 0] } as const
type Elem = { ref: string; kind: string; info: ReturnType<typeof subInfo> | null; point: THREE.Vector3 | null }
/** MeasureManager::getMeasureElementType, from the displayed geometry. */
function elemType(e: Elem): string {
  if (!e.info) return 'VOLUME'
  const i = e.info
  if (i.kind === 'Vertex') return 'POINT'
  if (i.kind === 'Line') return 'LINESEGMENT'
  if (i.kind === 'Circle') return i.radius !== undefined && i.length !== undefined && Math.abs(i.length - 2 * Math.PI * i.radius) < 0.02 * i.length ? 'CIRCLE' : 'ARC'
  if (i.kind === 'Curve') return 'CURVE'
  if (i.kind === 'Plane') return 'PLANE'
  if (i.kind === 'Disc') return 'DISC'
  if (i.kind === 'Cylinder' || i.kind === 'CylinderSection') return 'CYLINDER'
  if (i.kind === 'Sphere') return 'SPHERE'
  return 'SURFACE'
}
const EDGE_TYPES = ['LINESEGMENT', 'CIRCLE', 'ARC', 'CURVE'], FACE_TYPES = ['PLANE', 'SURFACE', 'DISC', 'CYLINDER', 'SPHERE']
/** Each type's isValidSelection and isPrioritizedSelection. */
function measureRules(els: Elem[]): { valid: MeasureType[]; prioritized: MeasureType[] } {
  const t = els.map(elemType), n = els.length
  const valid: MeasureType[] = [], prioritized: MeasureType[] = []
  const vec = (e: Elem) => e.info?.normal ?? e.info?.dir
  // Distance takes points, curves and surfaces (whole parts too, measured exactly by cad measure).
  if (n === 2) valid.push('Distance')
  if (n === 2) valid.push('Distance Free')
  if (n === 2 && els.every((e) => !!vec(e))) {
    valid.push('Angle')
    const c = Math.abs(vec(els[0])!.clone().normalize().dot(vec(els[1])!.clone().normalize()))
    if (Math.acos(Math.min(1, c)) > 1e-9) prioritized.push('Angle')
  }
  if (n > 0 && t.every((x) => EDGE_TYPES.includes(x))) valid.push('Length')
  if (n === 1 && t[0] === 'POINT') valid.push('Position')
  if (n > 0 && t.every((x) => FACE_TYPES.includes(x))) valid.push('Area')
  // MeasureDiameter / MeasureRadius::isValidSelection: a circle or arc, or a cylinder, disc,
  // torus or sphere face.
  if (n === 1 && ['CIRCLE', 'ARC', 'CYLINDER', 'DISC', 'TORUS', 'SPHERE'].includes(t[0])) {
    valid.push('Diameter', 'Radius')
    // AppMeasure.cpp registers DIAMETER then RADIUS with byte-identical isPrioritizedSelection;
    // MeasureManager::getValidMeasureTypes inserts each new prioritized type at the front, so
    // the later-registered one (Radius) always wins the tie, for both a circle and an arc.
    prioritized.push('Radius')
  }
  if (n === 1 && t[0] === 'VOLUME') valid.push('Geometric Center')
  return { valid, prioritized }
}

/** Std_Measure (Measure/Gui/TaskMeasure.cpp): the measurement follows the selection while the
 *  task is open. Mode picks the type (Auto: a prioritized type, else the first valid one);
 *  the result shows in a chosen unit. Save (Enter) keeps it in the view; Esc clears the
 *  selection, or closes. Two whole parts are measured exactly by `cad measure`. */
export function MeasureTask() {
  // TaskMeasure::updateHints: Shift auto-saves, Ctrl adds to the measurement (GreedySelection
  // would make it "start new measurement"; this UI selects additively by default).
  useEffect(() => {
    setState({ hints: [{ message: '%1 auto-save', keys: ['⇧'] }, { message: '%1 add to measurement', keys: ['⌘'] }] })
    return () => setState({ hints: [] }) // MainWindow::hideHints when the task closes
  }, [])
  useStore((s) => s.units) // written again in a new unit system
  const selected = useStore((s) => s.selected), subSel = useStore((s) => s.subSel), subPts = useStore((s) => s.subPts)
  const hash = useStore((s) => s.scene?.source_hash), slug = useStore((s) => s.slug)
  const [mode, setMode] = useState<'Auto' | MeasureType>('Auto')
  const [unit, setUnit] = useState('-')
  const [keep, setKeep] = useState<{ text: string; line: THREE.Vector3[] | null; at: THREE.Vector3 }[]>([])
  const [autoSave, setAutoSave] = useState(() => saved.get('measure.autoSave', false))
  // TaskMeasure.cpp's "Additive Selection" setting (newMeasurementBehaviourAction): off (the
  // default) means Ctrl must be held to add a pick to the running measurement, otherwise a new
  // one starts (autosaving the old one when Auto Save applies); on, a plain pick adds and Ctrl
  // starts fresh. FreeCAD implements this by swapping the whole app's click-selection style
  // (Gui::Selection().setSelectionStyle); we can't touch that here (it lives in viewer.ts and
  // actions.ts, owned by others this session), so instead we watch Ctrl/Shift ourselves and
  // keep our own accumulated element list built from the store's selection changes.
  const [additiveSel, setAdditiveSel] = useState(() => saved.get('measure.additiveSelection', false))
  const [showDelta, setShowDelta] = useState(() => saved.get('measure.showDelta', true))
  const [remote, setRemote] = useState<{ key: string; value: number | null; line: THREE.Vector3[] | null; text?: string; vec?: THREE.Vector3 } | null>(null)
  const ctrlRef = useRef(false), shiftRef = useRef(false)
  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') ctrlRef.current = true; if (e.key === 'Shift') shiftRef.current = true }
    const up = (e: KeyboardEvent) => { if (e.key === 'Control' || e.key === 'Meta') ctrlRef.current = false; if (e.key === 'Shift') shiftRef.current = false }
    const clear = () => { ctrlRef.current = false; shiftRef.current = false }
    addEventListener('keydown', down, true); addEventListener('keyup', up, true); addEventListener('blur', clear)
    return () => { removeEventListener('keydown', down, true); removeEventListener('keyup', up, true); removeEventListener('blur', clear) }
  }, [])
  // The store's raw selection (Ctrl always adds/toggles there, a plain pick always replaces:
  // that's FreeCAD's Normal selection style, i.e. Additive Selection off) versus the measurement's
  // own accumulated selection, which behaves like Normal style when Additive Selection is off and
  // like Greedy style (a plain pick adds, Ctrl starts fresh) when it's on.
  const rawRefs = subSel.length ? subSel : selected
  const rawKey = rawRefs.join('\u0000')
  const prevRaw = useRef<string[]>([])
  const [accum, setAccum] = useState<string[]>([])
  const lastMeasurement = useRef<{ label: string; line: THREE.Vector3[] | null; at: THREE.Vector3 | null }>({ label: '', line: null, at: null })
  useEffect(() => {
    const raw = rawRefs, prev = prevRaw.current
    prevRaw.current = raw
    if (!raw.length) { setAccum([]); return }
    // TaskMeasure::onSelectionChanged: (!ctrl && Normal) || (ctrl && Greedy) starts a new
    // measurement (autosaving the old one, Shift inverting Auto Save for this pick); the other
    // combination extends the running one. That's exactly ctrlHeld === additiveSel.
    const startNew = ctrlRef.current === additiveSel
    if (startNew) {
      const effectiveAutoSave = autoSave !== shiftRef.current, m = lastMeasurement.current
      if (effectiveAutoSave && m.label && m.at) setKeep((k) => [...k, { text: m.label, line: m.line, at: m.at! }])
      const added = raw.filter((r) => !prev.includes(r))
      setAccum(added.length ? added : raw)
    } else setAccum((a) => [...a, ...raw.filter((r) => !a.includes(r))])
  }, [rawKey, additiveSel])
  const els: Elem[] = useMemo(() => {
    const v = getView()
    return accum.map((ref) => {
      const dot = ref.lastIndexOf('.'), isSub = dot >= 0 && /^(Face|Edge|Vertex)\d+$/.test(ref.slice(dot + 1))
      if (!isSub) return { ref, kind: 'body', info: null, point: null }
      const info = subInfo(v?.subGeometry(ref) ?? null), p = subPts[ref]
      return { ref, kind: 'sub', info, point: p ? new THREE.Vector3(...p) : info?.center ?? null }
    })
  }, [accum, subPts, hash])
  const rules = measureRules(els)
  const type: MeasureType | null = mode !== 'Auto' ? (rules.valid.includes(mode) ? mode : null)
    : rules.prioritized[0] ?? rules.valid[0] ?? null
  // Whole parts: Distance through cad measure, Geometric Center through cad mass.
  const bodies = els.every((e) => e.kind === 'body') ? els.map((e) => e.ref) : []
  const key = `${type}|${bodies.join(',')}|${hash}`
  useEffect(() => {
    if (!slug || !bodies.length || (type !== 'Distance' && type !== 'Geometric Center')) return
    let live = true
    setRemote(null)
    const run = type === 'Distance' ? api.measure(slug, bodies[0], bodies[1]).then((r) => {
      const d = r.data ?? {}
      if (d.interferes) return { key, value: 0, line: null, text: `They interfere: overlap ${quantity.userString({ value: d.overlap_mm3, dims: [3, 0, 0, 0, 0, 0, 0, 0] }).text}` }
      if (typeof d.min_distance_mm === 'number') return { key, value: d.min_distance_mm as number, line: (d.points ?? []).map((p: number[]) => new THREE.Vector3(...p)) }
      return { key, value: null, line: null, text: resultText(r) }
    }) : api.mass(slug, bodies).then((r) => r.data ? { key, value: null, line: null, vec: new THREE.Vector3(...(r.data.cov as Vec3)) } : { key, value: null, line: null, text: resultText(r) })
    run.then((x) => live && setRemote(x)).catch((e) => live && setRemote({ key, value: null, line: null, text: String(e) }))
    return () => { live = false }
  }, [key])
  // The measurement: a value (and its quantity), or a position; where to draw it.
  let value: number | null = null, dims: 'Length' | 'Angle' | 'Area' = 'Length', pos: THREE.Vector3 | null = null
  let line: THREE.Vector3[] | null = null, at: THREE.Vector3 | null = null, note = ''
  if (type && bodies.length && (type === 'Distance' || type === 'Geometric Center')) {
    if (remote?.key === key) {
      value = remote.value; line = remote.line; pos = remote.vec ?? null; note = remote.text ?? ''
      at = line ? line[0].clone().lerp(line[1], 0.5) : pos
      // ViewProviderMeasureBase.cpp:679-718 (ViewProviderMeasure, the generic view provider):
      // Geometric Center has no specialised one, so it gets the single leader-line+CROSS look.
      if (!line && at && type === 'Geometric Center') line = [at]
    }
    else note = 'Measuring…'
  } else if (type) {
    const [a, b] = els, ia = a?.info, ib = b?.info
    if (type === 'Distance' && ia && ib) { const m = measurePair(ia, ib); line = m.line; value = line ? line[0].distanceTo(line[1]) : null
      if (ia.normal && ib.normal && Math.abs(ia.normal.dot(ib.normal)) > 0.9999) value = Math.abs(ib.center.clone().sub(ia.center).dot(ia.normal))
      else if (ia.kind === 'Vertex' && ib.normal) value = Math.abs(ia.center.clone().sub(ib.center).dot(ib.normal))
      else if (ib.kind === 'Vertex' && ia.normal) value = Math.abs(ib.center.clone().sub(ia.center).dot(ia.normal)) }
    else if (type === 'Distance Free' && a?.point && b?.point) { line = [a.point, b.point]; value = a.point.distanceTo(b.point) }
    else if (type === 'Angle' && ia && ib) {
      const u = (ia.normal ?? ia.dir)!.clone().normalize(), w = (ib.normal ?? ib.dir)!.clone().normalize()
      value = THREE.MathUtils.radToDeg(u.angleTo(w)); dims = 'Angle'; at = ia.center.clone().lerp(ib.center, 0.5)
      // ViewProviderMeasureAngle: an arc between the two directions, about the point between them.
      const axis = u.clone().cross(w), theta = u.angleTo(w)
      if (axis.lengthSq() > 1e-12) {
        // ViewProviderMeasureAngle.cpp:306-309,644: the radius is the length of the (undragged)
        // label translation, which positionAnno defaults to 0.1*getViewScale() — the same
        // view-scale constant as Distance's DIM_GAP_PX (not the gap between the two elements).
        const r = (getView()?.viewScalePerPixel() ?? 0.01) * DIM_GAP_PX, perp = axis.normalize().clone().cross(u)
        line = Array.from({ length: 25 }, (_, k) => { const t = (theta * k) / 24; return at!.clone().add(u.clone().multiplyScalar(r * Math.cos(t))).add(perp.clone().multiplyScalar(r * Math.sin(t))) })
      }
    }
    else if (type === 'Length') value = els.reduce((t, e) => t + (e.info?.length ?? 0), 0)
    else if (type === 'Position' && ia) pos = ia.center
    else if (type === 'Area') { value = els.reduce((t, e) => t + (e.info?.area ?? 0), 0); dims = 'Area' }
    else if ((type === 'Diameter' || type === 'Radius') && ia?.radius !== undefined) { value = type === 'Diameter' ? 2 * ia.radius : ia.radius; at = ia.center }
    at = at ?? (line ? line[0].clone().lerp(line[1], 0.5) : pos ?? ia?.center ?? null)
    // ViewProviderMeasureBase.cpp:679-718 (ViewProviderMeasure, the generic view provider used
    // by every measure kind without one of its own — Length/Position/Diameter/Radius/Area here,
    // Geometric Center above): a single leader line from the anchor to the label plus one CROSS
    // marker at the anchor (drawMeasure's 1-point branch) — Distance/Distance Free/Angle differ.
    if (!line && at && type !== 'Distance' && type !== 'Distance Free' && type !== 'Angle') line = [at]
  }
  const show = (v: number, d: keyof typeof QD) => {
    if (unit === '-' || !MEASURE_UNITS[d].includes(unit)) return quantity.userString({ value: v, dims: [...QD[d]] as quantity.Quantity['dims'] }).text
    // MeasureBase::formatQuantity: the value in the display unit, as Quantity::toNumber writes it
    // at the user's decimals — Default (%g) between -1 and 1, else Fixed.
    const converted = v / quantity.parseQuantity('1 ' + unit).value
    return `${quantity.toNumber(converted, Math.abs(converted) < 1.0 && converted !== 0.0 ? 'Default' : 'Fixed', quantity.unitPrefs.decimals)} ${unit}`
  }
  const showXYZ = (p: THREE.Vector3) => `X: ${show(p.x, 'Length')}, Y: ${show(p.y, 'Length')}, Z: ${show(p.z, 'Length')}`
  // MeasurePosition::getResultString ("X: {}\nY: {}\nZ: {}") and MeasureCOM::getResultString
  // ("Geometric Center\nX: {}\nY: {}\nZ: {}"); both target a single-line result field here.
  const result = toUnicodeSuperscript(pos ? `${type === 'Geometric Center' ? 'Geometric Center ' : ''}${showXYZ(pos)}` : value != null ? show(value, dims) : '-')
  const label = type ? `${type}: ${result}` : ''
  // TaskMeasure::updateUnitDropdown: show the unit system's preferred unit for the measured
  // quantity, and keep the user's own choice as long as it still fits that quantity's units.
  const dimsKey: keyof typeof QD | null = !type ? null : type === 'Angle' ? 'Angle' : type === 'Area' ? 'Area' : 'Length'
  useEffect(() => {
    if (!dimsKey || MEASURE_UNITS[dimsKey].includes(unit)) return
    const pref = quantity.userString({ value: 1, dims: [...QD[dimsKey]] as quantity.Quantity['dims'] }).unit
    setUnit(MEASURE_UNITS[dimsKey].includes(pref) ? pref : MEASURE_UNITS[dimsKey].includes('mm') ? 'mm' : MEASURE_UNITS[dimsKey][0])
  }, [dimsKey])
  // Draw it: the line, the label, and the saved ones.
  useEffect(() => {
    const v = getView()
    // regress3-viewer.md #2: every saved ("kept") measurement keeps its own full geometry
    // (line/cross/arc), not just the newest one; #5 hands Angle's vertex along too, so
    // drawMeasure can add its spokes (only an Angle's polyline is ever >2 points).
    const vertexOf = (l: THREE.Vector3[], vertexAt: THREE.Vector3 | null) => (l.length > 2 && vertexAt ? vertexAt.toArray() : undefined)
    v?.showKeptMeasures(keep.flatMap((k) => (k.line ? [{ pts: k.line.map((p) => p.toArray()), vertex: vertexOf(k.line, k.at) }] : [])))
    v?.showMeasure(line ? line.map((p) => p.toArray()) : null, line ? vertexOf(line, at) : undefined)
    // regress3-viewer.md #1/#6: the label sits where drawMeasure actually draws the leader
    // line's/dimension line's far end, not back on the raw anchor; Angle's own label position
    // (getLabelAnchor returns null there) is untouched.
    const liveAt = v?.getLabelAnchor() ?? at
    v?.showLabels([...keep.map((k) => ({ text: k.text, at: k.at })), ...(liveAt && label && result !== '-' ? [{ text: label, at: liveAt }] : [])])
  }, [label, keep, at?.x, at?.y, at?.z])
  useEffect(() => () => { getView()?.showMeasure(null); getView()?.showKeptMeasures([]); getView()?.showLabels([]) }, [])
  const doSave = () => { if (at && result !== '-') { const anchor = getView()?.getLabelAnchor() ?? at; setKeep((k) => [...k, { text: label, line, at: anchor! }]); report('msg', `Measurement: ${label}`) } }
  // Tracks the latest valid measurement, so a later "start a new measurement" transition (above)
  // can autosave it even though its own effect runs a render before `label` catches up.
  useEffect(() => { lastMeasurement.current = { label: result !== '-' ? label : '', line, at: getView()?.getLabelAnchor() ?? at } }, [label])
  const doReset = () => setState({ selected: [], subSel: [] }) // TaskMeasure::reset: clearSelection + update
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest?.('input, select, textarea')) return
      if (e.key === 'Enter') { e.preventDefault(); doSave() }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (getState().selected.length) doReset(); else closeTask() }
    }
    addEventListener('keydown', key, true)
    return () => removeEventListener('keydown', key, true)
  })
  const units = dimsKey ? MEASURE_UNITS[dimsKey] : []
  return (
    <div className="tasks">
      <div className="tbuttons">
        <button className="qbtn default" disabled={!at || result === '-'} title="Saves the measurement in the active document" onClick={doSave}>Save</button>
        <button className="qbtn" title="Resets the tool" onClick={doReset}>Reset</button>
        <button className="qbtn" title="Close the measurement task." onClick={closeTask}>Close</button>
      </div>
      <TaskBox title="Measurement" icon="measure">
        <label className="tcheck" title="Auto saving of the last measurement when starting a new measurement. Use the Shift key to temporarily invert the behaviour."><input type="checkbox" checked={autoSave} onChange={(e) => { setAutoSave(e.target.checked); saved.set('measure.autoSave', e.target.checked) }} /> Auto save</label>
        <label className="tcheck" title="If checked, new selection will be added to the measurement. If unchecked, the Ctrl key must be pressed to add a selection to the current measurement otherwise a new measurement will be started"><input type="checkbox" checked={additiveSel} onChange={(e) => { setAdditiveSel(e.target.checked); saved.set('measure.additiveSelection', e.target.checked) }} /> Additive Selection</label>
        <label className="tfield"><span>Mode</span><QComboBox className="qselect-field" value={mode} onChange={(e) => setMode(e.target.value as 'Auto')}>
          <option>Auto</option>{MEASURE_TYPES.map((t) => <option key={t}>{t}</option>)}</QComboBox></label>
        <label className="tfield"><span>Result</span><input readOnly value={note && result === '-' ? note : result} />
          <QComboBox className="qselect-field" value={unit} onChange={(e) => setUnit(e.target.value)}><option>-</option>{units.map((u) => <option key={u} value={u}>{toUnicodeSuperscript(u)}</option>)}</QComboBox></label>
        {(type === 'Distance' || type === 'Distance Free') && <>
          <label className="tcheck"><input type="checkbox" checked={showDelta} onChange={(e) => { setShowDelta(e.target.checked); saved.set('measure.showDelta', e.target.checked) }} /> Show Delta</label>
          {showDelta && <div className="tform">
            <label className="tfield"><span>Δx</span><input readOnly value={line ? show(Math.abs(line[1].x - line[0].x), 'Length') : '-'} /></label>
            <label className="tfield"><span>Δy</span><input readOnly value={line ? show(Math.abs(line[1].y - line[0].y), 'Length') : '-'} /></label>
            <label className="tfield"><span>Δz</span><input readOnly value={line ? show(Math.abs(line[1].z - line[0].z), 'Length') : '-'} /></label>
          </div>}
        </>}
        <p className="hint">{additiveSel ? 'Ctrl starts a new measurement. Shift toggles auto save.' : 'Ctrl adds to the measurement. Shift toggles auto save.'}</p>
        {!els.length && <p className="hint">Select faces, edges or vertices in the 3D view (Ctrl adds), or parts.</p>}
        {els.length > 0 && <p className="hint">{els.map((e) => e.ref).join(', ')}{type ? ` (${type})` : ' (no measure type fits this selection)'}</p>}
      </TaskBox>
      {keep.length > 0 && <TaskBox title="Saved measurements" icon="measure">
        {keep.map((k, i) => <div key={i} className="align-pt">{k.text}</div>)}
        <div className="tbuttons"><button className="qbtn" onClick={() => setKeep([])}>Clear</button></div>
      </TaskBox>}
    </div>
  )
}

/** Std_MassProperties for the selected parts. */
type MassData = {
  volume_mm3: number; mass_kg: number; surface_area_mm2: number; density_kg_mm3: number | null
  cog: Vec3; cov: Vec3; inertia_kg_mm2: number[][]; principal_moments: Vec3; principal_axes: Vec3[]
  bodies: { body: string; material: string | null; mass_kg: number }[]; default_density: string[]
}
/** TaskMassProperties' unit systems: length, mass, and what one mm and one kg are in them. */
const MASS_UNITS = [
  { label: 'mm, kg, kg*mm^2', l: 'mm', m: 'kg', perMm: 1, perKg: 1 },
  { label: 'm, kg, kg*m^2', l: 'm', m: 'kg', perMm: 1e-3, perKg: 1 },
  { label: 'in, lb, lb*in^2', l: 'in', m: 'lb', perMm: 1 / 25.4, perKg: 2.20462262185 },
  { label: 'ft, lb, lb*ft^2', l: 'ft', m: 'lb', perMm: 1 / 304.8, perKg: 2.20462262185 },
]
/** math_Jacobi for a symmetric 3x3 matrix: eigenvalues and unit eigenvectors. */
function jacobi3(a0: number[][]): { values: number[]; vectors: number[][] } {
  const a = a0.map((r) => [...r]), v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
  for (let sweep = 0; sweep < 50; sweep++) {
    const off = Math.abs(a[0][1]) + Math.abs(a[0][2]) + Math.abs(a[1][2])
    if (off < 1e-12) break
    for (const [p, q] of [[0, 1], [0, 2], [1, 2]]) {
      if (Math.abs(a[p][q]) < 1e-15) continue
      const th = (a[q][q] - a[p][p]) / (2 * a[p][q]), t = Math.sign(th || 1) / (Math.abs(th) + Math.sqrt(th * th + 1))
      const c = 1 / Math.sqrt(t * t + 1), s = t * c
      for (let k = 0; k < 3; k++) { const akp = a[k][p], akq = a[k][q]; a[k][p] = c * akp - s * akq; a[k][q] = s * akp + c * akq }
      for (let k = 0; k < 3; k++) { const apk = a[p][k], aqk = a[q][k]; a[p][k] = c * apk - s * aqk; a[q][k] = s * apk + c * aqk }
      for (let k = 0; k < 3; k++) { const vkp = v[k][p], vkq = v[k][q]; v[k][p] = c * vkp - s * vkq; v[k][q] = s * vkp + c * vkq }
    }
  }
  return { values: [a[0][0], a[1][1], a[2][2]], vectors: [0, 1, 2].map((j) => [v[0][j], v[1][j], v[2][j]]) }
}

/** Part::Tools::fromPlacement(...).Transformation().VectorialPart(), and its use in
 *  MassPropertiesResult.cpp:318,344-346 (I_custom = Rᵀ·I_translated·R): plain 3x3 helpers,
 *  since this app has no matrix type. */
function mat3T(m: number[][]): number[][] {
  return [[m[0][0], m[1][0], m[2][0]], [m[0][1], m[1][1], m[2][1]], [m[0][2], m[1][2], m[2][2]]]
}
function mat3Mul(a: number[][], b: number[][]): number[][] {
  const r = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) for (let k = 0; k < 3; k++) r[i][j] += a[i][k] * b[k][j]
  return r
}
/** A picked face gives only a normal (one axis). FreeCAD's oriented custom reference is a
 *  selected Datum LCS/Origin/PartDesign::CoordinateSystem object's own Placement rotation
 *  (`isReferenceObject`, TaskMassProperties.cpp:793-812) — no such objects exist in this app
 *  (measure-mass-units.md #7), so a face is our substitute for "pick something with an
 *  orientation", completing the frame with a deterministic in-plane X/Y. Not ported from
 *  FreeCAD: nothing there builds a frame from a bare face. Returns Rᵀ (rows = the frame's
 *  X/Y/Z axes, in world coordinates). */
function frameFromNormal(n: THREE.Vector3): number[][] {
  const z = n.clone().normalize()
  const up = Math.abs(z.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0)
  const x = up.clone().cross(z).normalize(), y = z.clone().cross(x)
  return [[x.x, x.y, x.z], [y.x, y.y, y.z], [z.x, z.y, z.z]]
}

/** Std_MassProperties (Measure/Gui/TaskMassProperties.cpp): the selected objects' volume,
 *  mass, density, surface area, centres of gravity and volume, inertia matrix and
 *  principal moments, about the centre of gravity or a custom reference, in four unit
 *  systems. A custom reference with an orientation re-expresses the tensor in its own
 *  frame (CalculateMassProperties, Measure/App/MassPropertiesResult.cpp:308-372). The
 *  numbers come from OpenCASCADE through `cad mass`. */
export function MassTask() {
  const slug = useStore((s) => s.slug), selected = useStore((s) => s.selected), subSel = useStore((s) => s.subSel), hash = useStore((s) => s.scene?.source_hash)
  const [data, setData] = useState<MassData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [units, setUnits] = useState(0)
  const [ref, setRef] = useState<'cog' | 'custom'>('cog')
  const [origin, setOrigin] = useState<Vec3>([0, 0, 0])
  // The custom reference, when it's a straight edge rather than a point: Axis Inertia only,
  // no matrix/principal moments (MassPropertiesResult.cpp:277-306, see pickReference).
  const [axisRef, setAxisRef] = useState<string | null>(null)
  // The custom reference, when it's a planar face instead: our substitute for picking an
  // oriented Datum LCS/Origin (see frameFromNormal and pickReference below).
  const [planeRef, setPlaneRef] = useState<string | null>(null)
  // TaskMassProperties::tryUpdate promotes any sub-element pick up to its owning body (through
  // Body tips and groups). The store already does this for a fresh pick (select() in actions.ts
  // adds the owning body to `selected` whenever a sub-element is added to `subSel`), but fall
  // back to deriving it from subSel directly in case `selected` is ever left empty.
  const derivedSelected = selected.length ? selected : [...new Set(subSel.map((r) => r.split('.')[0]))]
  useEffect(() => {
    if (!slug || !derivedSelected.length) { setData(null); return }
    let live = true
    setBusy(true)
    const t = setTimeout(() => api.mass(slug, derivedSelected).then((r) => {
      if (!live) return
      if (r.exit === 0 && r.data) { setData(r.data as MassData); setErr(null) } else setErr(resultText(r))
    }).catch((e) => live && setErr(String(e))).finally(() => live && setBusy(false)), 150)
    return () => { live = false; clearTimeout(t) }
  }, [slug, derivedSelected.join(','), hash])
  // TaskMassProperties.cpp:160-205 (getUnitsSchemaIndex): map MASS_UNITS to schema indices
  const schemaIndices = [0, 1, 2, 7] // Internal, MKS, Imperial, ImperialCivil
  const unitsSchemaIndex = schemaIndices[units] ?? 0
  // The custom reference: the inertia moved to the point (parallel axes), then — when the
  // reference has an orientation (a picked face, see frameFromNormal) — rotated into its
  // frame: I_custom = Rᵀ·I_translated·R, and Jo/Jcross/principal all read from I_custom,
  // exactly MassPropertiesResult.cpp:308-372's non-axis Custom branch. A plain point has no
  // frame (R = identity), leaving J exactly as before.
  let J = data?.inertia_kg_mm2, principal = data ? { values: data.principal_moments as number[], vectors: data.principal_axes as number[][] } : null
  const planeInfo = planeRef ? subInfo(getView()?.subGeometry(planeRef) ?? null) : null
  if (data && ref === 'custom' && !axisRef) {
    const [dx, dy, dz] = [0, 1, 2].map((i) => data.cog[i] - origin[i]), m = data.mass_kg, rr = dx * dx + dy * dy + dz * dz
    const P = [[m * (rr - dx * dx), -m * dx * dy, -m * dx * dz], [-m * dx * dy, m * (rr - dy * dy), -m * dy * dz], [-m * dx * dz, -m * dy * dz, m * (rr - dz * dz)]]
    J = data.inertia_kg_mm2.map((row, i) => row.map((x, j) => x + P[i][j]))
    if (planeInfo?.normal) { const Rt = frameFromNormal(planeInfo.normal); J = mat3Mul(mat3Mul(Rt, J), mat3T(Rt)) }
    principal = jacobi3(J)
  }
  // Inertia around the axis of the custom reference, when it's a straight edge
  // (TaskMassProperties::updateInertiaVisibility: an axis reference replaces the whole
  // inertia-matrix/principal-moments section with just this row).
  const hasAxis = ref === 'custom' && !!axisRef
  const axisInfo = axisRef ? subInfo(getView()?.subGeometry(axisRef) ?? null) : null
  let axisInertia: number | null = null
  if (data && hasAxis && axisInfo?.dir) {
    const d = axisInfo.dir.clone().normalize(), o = axisInfo.center, J0 = data.inertia_kg_mm2
    const r = [data.cog[0] - o.x, data.cog[1] - o.y, data.cog[2] - o.z], proj = r[0] * d.x + r[1] * d.y + r[2] * d.z
    const perp = [r[0] - d.x * proj, r[1] - d.y * proj, r[2] - d.z * proj], dist2 = perp[0] ** 2 + perp[1] ** 2 + perp[2] ** 2
    const Icog = J0[0][0] * d.x * d.x + J0[1][1] * d.y * d.y + J0[2][2] * d.z * d.z + 2 * J0[0][1] * d.x * d.y + 2 * J0[0][2] * d.x * d.z + 2 * J0[1][2] * d.y * d.z
    axisInertia = Icog + data.mass_kg * dist2
  }
  // TaskMassProperties::tryUpdate's applyOriginOffset (~1182-1204): a non-axis Custom
  // reference also re-origins the displayed Center of gravity/volume to that point — still in
  // world-axis components (FreeCAD subtracts the origin but never rotates these two). The
  // axis reference and Center-of-gravity mode never apply this.
  const atCustomPoint = ref === 'custom' && !hasAxis
  const cog: Vec3 = data ? (atCustomPoint ? ([0, 1, 2].map((i) => data.cog[i] - origin[i]) as Vec3) : data.cog) : [0, 0, 0]
  const cov: Vec3 = data ? (atCustomPoint ? ([0, 1, 2].map((i) => data.cov[i] - origin[i]) as Vec3) : data.cov) : [0, 0, 0]
  // TaskMassProperties.cpp:1243-1248 (setText for cog/cov): centre values with Length dims
  const vec = (label: string, v: Vec3) => (
    <div className="mass-row"><span className="mass-l">{label}</span>{v.map((x, i) => <span key={i} className="mass-v">{'XYZ'[i]}: {quantity.formatMassProperty(x, [1, 0, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span>)}</div>)
  /** The "Select…" button (onSelectCustomCoordinateSystem/getAxisReferenceFromSelection): a
   *  straight edge becomes the axis reference (Axis Inertia only, no matrix/principal moments).
   *  A planar face becomes an oriented reference (frameFromNormal above): FreeCAD's actual
   *  oriented reference is a selected Datum LCS/Origin/PartDesign::CoordinateSystem object's
   *  Placement (`isReferenceObject`, TaskMassProperties.cpp:793-812) — no such objects exist in
   *  this app, so a face substitutes for "pick something with an orientation". A vertex sets a
   *  plain custom point (no orientation, R = identity). */
  const pickReference = () => {
    const sub = getState().subSel
    const edgeRef = sub.find((r) => /\.Edge\d+$/.test(r))
    const edgeInfo = edgeRef ? subInfo(getView()?.subGeometry(edgeRef) ?? null) : null
    if (edgeRef && edgeInfo?.kind === 'Line') { setAxisRef(edgeRef); setPlaneRef(null); setRef('custom'); return }
    const faceRef = sub.find((r) => /\.Face\d+$/.test(r))
    const faceInfo = faceRef ? subInfo(getView()?.subGeometry(faceRef) ?? null) : null
    if (faceRef && faceInfo?.kind === 'Plane' && faceInfo.normal) {
      setOrigin([faceInfo.center.x, faceInfo.center.y, faceInfo.center.z]); setAxisRef(null); setPlaneRef(faceRef); setRef('custom'); return
    }
    const vtx = sub.find((r) => /\.Vertex\d+$/.test(r))
    const g = vtx ? getView()?.subGeometry(vtx) : null
    if (g && g.kind === 'Vertex') { setOrigin([g.point.x, g.point.y, g.point.z]); setAxisRef(null); setPlaneRef(null); setRef('custom') }
    else report('warn', 'Mass properties: select a vertex for the reference point, a planar face for an oriented reference, or a straight edge for an axis')
  }
  // TaskMassProperties.cpp:450-461 (Reset button): clears the selection and the datum/axis
  // reference along with the UI fields — it does not change the Center of gravity/Custom mode.
  const resetTask = () => { setState({ selected: [], subSel: [] }); setOrigin([0, 0, 0]); setAxisRef(null); setPlaneRef(null) }
  return (
    <div className="tasks">
      <TaskButtons onOk={closeTask} />
      <div className="tbuttons"><button className="qbtn" title="Resets the tool" onClick={resetTask}>Reset</button></div>
      {/* TaskMassProperties.cpp:348-363 (addTaskBox): Parameters / Physical Properties /
       *  Center of Gravity / Center of Volume / Inertia are five separate panel sections,
       *  in this order (we previously folded these into three boxes — not what FreeCAD does). */}
      <TaskBox title="Parameters" icon="mass">
        <div className="mass-l mass-h">Objects to measure</div>
        {!derivedSelected.length && <p className="hint">Select one or more parts.</p>}
        <table className="ctable"><tbody>
          {(data?.bodies ?? []).map((x) => <tr key={x.body}><td>{x.body}</td><td>{x.material ?? 'no material'}</td><td>{quantity.formatMassProperty(x.mass_kg, [0, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</td></tr>)}
        </tbody></table>
        {!!data?.default_density.length && <p className="hint">No density for {data.default_density.join(', ')}: 1000 kg/m³ is used, as FreeCAD does.</p>}
        <div className="mass-l mass-h">Reference</div>
        <label className="tcheck"><input type="radio" checked={ref === 'cog'} onChange={() => { setRef('cog'); setAxisRef(null); setPlaneRef(null) }} /> Center of gravity</label>
        <label className="tcheck"><input type="radio" checked={ref === 'custom'} onChange={() => setRef('custom')} /> Custom</label>
        {ref === 'custom' && <div className="tform">
          {hasAxis ? <p className="hint">Axis: {axisRef}</p>
            : planeRef ? <p className="hint">Plane: {planeRef}</p>
            : [0, 1, 2].map((i) => <label key={i} className="tfield"><span>{'XYZ'[i]}</span><input type="number" step={1} value={origin[i]}
              onChange={(e) => { const o = [...origin] as Vec3; o[i] = Number(e.target.value) || 0; setOrigin(o); setAxisRef(null); setPlaneRef(null) }} /><span className="unit">mm</span></label>)}
          <button className="qbtn" onClick={pickReference}>Select…</button>
        </div>}
        <label className="tfield"><span>Units</span><QComboBox className="qselect-field" value={units} onChange={(e) => setUnits(Number(e.target.value))}>
          {MASS_UNITS.map((x, i) => <option key={i} value={i}>{x.label}</option>)}</QComboBox></label>
      </TaskBox>
      <TaskBox title="Physical Properties" icon="mass">
        {busy && <p className="hint">Computing…</p>}
        {err && <p className="hint err">{err}</p>}
        {data && <>
          {/* TaskMassProperties.cpp:1235,1240: Volume, Mass, Surface area with no suffix */}
          <div className="mass-row"><span className="mass-l">Volume</span><span className="mass-v">{quantity.formatMassProperty(data.volume_mm3, [3, 0, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span></div>
          <div className="mass-row"><span className="mass-l">Mass</span><span className="mass-v">{quantity.formatMassProperty(data.mass_kg, [0, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span></div>
          {/* TaskMassProperties.cpp:1232,1237: only Density gets " (Average)" suffix, only when > 1 object */}
          <div className="mass-row"><span className="mass-l">Density</span><span className="mass-v">{data.density_kg_mm3 != null ? quantity.formatMassProperty(data.density_kg_mm3, [-3, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex) : '—'}{data.bodies.length > 1 ? ' (Average)' : ''}</span></div>
          <div className="mass-row"><span className="mass-l">Surface area</span><span className="mass-v">{quantity.formatMassProperty(data.surface_area_mm2, [2, 0, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span></div>
        </>}
      </TaskBox>
      <TaskBox title="Center of gravity" icon="mass">{data && vec('Center of gravity', cog)}</TaskBox>
      <TaskBox title="Center of Volume" icon="mass">{data && vec('Center of volume', cov)}</TaskBox>
      <TaskBox title="Inertia" icon="mass">
        {data && <>
          {!hasAxis && <>
            {/* TaskMassProperties.cpp:1249-1290: inertia matrix and principal moments in kg*mm² */}
            <div className="mass-l mass-h">Inertia matrix{ref === 'custom' ? (planeRef ? ', at the custom plane, in its own orientation' : ', at the custom point') : ', at the center of gravity'}</div>
            {J && <div className="mass-grid">
              <span>Jox: {quantity.formatMassProperty(J[0][0], [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span><span>Jxy: {quantity.formatMassProperty(J[0][1], [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span><span>Jzx: {quantity.formatMassProperty(J[0][2], [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span>
              <span /><span>Joy: {quantity.formatMassProperty(J[1][1], [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span><span>Jzy: {quantity.formatMassProperty(J[1][2], [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span>
              <span /><span /><span>Joz: {quantity.formatMassProperty(J[2][2], [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span>
            </div>}
            <div className="mass-l mass-h">Principal moments of inertia</div>
            {principal && <div className="mass-grid">{principal.values.map((x, i) => <span key={i}>J{i + 1}: {quantity.formatMassProperty(x, [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex)}</span>)}</div>}
          </>}
          {hasAxis && <div className="mass-row"><span className="mass-l">Inertia around axis</span><span className="mass-v">{axisInertia != null ? quantity.formatMassProperty(axisInertia, [2, 1, 0, 0, 0, 0, 0, 0], unitsSchemaIndex) : '—'}</span></div>}
        </>}
      </TaskBox>
    </div>
  )
}
