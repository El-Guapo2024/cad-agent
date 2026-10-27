// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Assembly/CommandInsertLink.py: 2023 Ondsel
//   src/Mod/Assembly/CommandCreateView.py: 2023 Ondsel
//   src/Mod/Assembly/UtilsAssembly.py: 2023 Ondsel
//   No copyright line in the file: src/Mod/Assembly/Gui/Resources/panels/TaskAssemblyInsertLink.ui,
//       src/Mod/Assembly/Gui/Resources/panels/TaskAssemblyCreateView.ui
// The Assembly workbench's panels for components and views: TaskAssemblyInsertLink (the project's parts and the other
// projects' Assemblies, inserted as App::Links and AssemblyLinks) and TaskAssemblyCreateView (an exploded view's moves,
// made by dragging the selected parts with the transform dragger, listed with their distance or angle).
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { getState, report, useStore } from './store'
import { closeTask, getView } from './actions'
import { Icon } from './icons'
import { TaskBox } from './panels'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { quatOfYpr, yprOfQuat } from './rotation'
import type { Plc } from './ondsel'
import {
  applyAssembly, asmObject, isComponent, leaves, movingOf, OffsetDialog, showExploded, showPlacements,
  type AsmObj, type Off, type V3,
} from './assembly_wb'

/** TaskAssemblyInsertLink: the documents' parts, this project's (its part files) first, then each project with an
 *  Assembly, which goes in as a sub-assembly (Assembly::AssemblyLink, rigid when "Rigid sub-assemblies" is checked). Each
 *  item clicked goes in; OK inserts them, the first of an ungrounded Assembly grounded (GroundFirstPart). */
export function InsertTask() {
  const features = useStore((s) => s.features), scene = useStore((s) => s.scene), projects = useStore((s) => s.projects), slug = useStore((s) => s.slug)
  const [filter, setFilter] = useState('')
  const [picked, setPicked] = useState<{ part?: string; assembly?: string }[]>([])
  const [rigid, setRigid] = useState(true)
  const parts = useMemo(() => [...new Set([...Object.keys(features), ...(scene?.bodies.map((b) => b.part).filter((p): p is string => !!p) ?? [])])].sort(), [features, scene])
  const assemblies = projects.filter((p) => p.assembly && p.slug !== slug).map((p) => p.slug).sort()
  const match = (t: string) => !filter || t.toLowerCase().includes(filter.toLowerCase())
  const counts = (k: 'part' | 'assembly', p: string) => picked.filter((x) => x[k] === p).length
  const ok = async () => {
    closeTask()
    if (!picked.length) return
    await applyAssembly(picked.map((x) => (x.part ? { op: 'insert', part: x.part } : { op: 'insert', assembly: x.assembly, rigid })), 'Insert Component')
  }
  return <div className="tasks as-task" data-task="insert">
    <TaskBox title="Insert" icon="as-insert">
      <input className="qline" data-qf="filterPartList" placeholder="Search parts..." value={filter} onChange={(e) => setFilter(e.target.value)} />
      <div className="as-list" data-qf="partList">
        {slug && <div className="as-item as-doc"><Icon name="document" size={16} /> {slug}</div>}
        {parts.filter(match).map((p) => <div key={p} className="as-item as-sub" onClick={() => setPicked((x) => [...x, { part: p }])}>
          <Icon name="part" size={16} /> {p}{counts('part', p) ? ` : ${counts('part', p)} inserted` : ''}</div>)}
        {assemblies.filter(match).map((a) => <div key={a}>
          <div className="as-item as-doc"><Icon name="document" size={16} /> {a}</div>
          <div className="as-item as-sub" data-assembly={a} onClick={() => setPicked((x) => [...x, { assembly: a }])}>
            <Icon name="as-assembly" size={16} /> Assembly{counts('assembly', a) ? ` : ${counts('assembly', a)} inserted` : ''}</div>
        </div>)}
      </div>
      <div className="tfield"><span>Cannot find the part?</span><button className="qbtn" disabled title="n/a: a component is a part file of this project, or another project's Assembly">Open File</button></div>
      <label className="tcheck" data-qf="CheckBox_ShowOnlyParts"><input type="checkbox" disabled /> Show only parts</label>
      <label className="tcheck" data-qf="CheckBox_RigidSubAsm"><input type="checkbox" checked={rigid} onChange={(e) => setRigid(e.target.checked)} /> Rigid sub-assemblies</label>
    </TaskBox>
    <div className="tbuttons pd-buttons">
      <button className="qbtn default" onClick={() => void ok()}>OK</button>
      <button className="qbtn" onClick={() => closeTask()}>Cancel</button>
    </div>
  </div>
}

// ── exploded views (CommandCreateView.py) ────────────────────────────────────────────────────────────────────────
type Q4 = [number, number, number, number]
interface Move { name?: string; references: string[]; t: { pos: V3; rot: Q4 }; type: 'Normal' | 'Radial'; label: string }
const CONFUSION = 1e-7, ANGULAR = 1e-12, SINGLE = 2 ** -23
const vlen = (a: number[]) => Math.hypot(a[0], a[1], a[2])
const angleOf = (q: Q4) => { const w = Math.max(-1, Math.min(1, q[3])); return w > -1 && w < 1 ? 2 * Math.acos(w) : 0 }
const axisOf = (q: Q4): V3 => { const s = Math.sqrt(Math.max(0, 1 - q[3] * q[3])); return s > 0 ? [q[0] / s, q[1] / s, q[2] / s] : [0, 0, 1] }
const qOf = (q: THREE.Quaternion): Q4 => [q.x, q.y, q.z, q.w]
const toM = (t: Move['t']) => new THREE.Matrix4().compose(new THREE.Vector3(...t.pos), new THREE.Quaternion(...t.rot), new THREE.Vector3(1, 1, 1))
const ofM = (m: THREE.Matrix4): Move['t'] => { const p = new THREE.Vector3(), q = new THREE.Quaternion(); m.decompose(p, q, new THREE.Vector3()); return { pos: p.toArray() as V3, rot: qOf(q) } }
/** isPureRotationMovement */
function pureRotation(t: Move['t']) {
  if (angleOf(t.rot) <= ANGULAR) return false
  const a = axisOf(t.rot), n = vlen(a)
  if (n <= CONFUSION) return false
  return Math.abs((t.pos[0] * a[0] + t.pos[1] * a[1] + t.pos[2] * a[2]) / n) <= CONFUSION
}
/** movementEditMode */
const editMode = (m: Move) => (m.type === 'Radial' ? 'Distance' : pureRotation(m.t) ? 'Angle' : 'Distance')
/** movementLabel */
function movementLabel(m: Move) {
  if (m.type === 'Radial') return 'Radial Translation'
  const rot = pureRotation(m.t), v = rot ? axisOf(m.t.rot) : m.t.pos
  const tol = Math.max(CONFUSION, 4 * SINGLE * vlen(v))
  return (rot ? 'Rotation' : 'Translation') + 'XYZ'.split('').filter((_, i) => Math.abs(v[i]) > tol).join('')
}
/** rotationCenterFromTransform */
function rotationCenter(t: Move['t']): V3 {
  const angle = angleOf(t.rot)
  if (angle <= ANGULAR) return [0, 0, 0]
  const a = new THREE.Vector3(...axisOf(t.rot)).normalize(), tr = new THREE.Vector3(...t.pos)
  const perp = tr.clone().sub(a.clone().multiplyScalar(tr.dot(a)))
  return perp.clone().add(a.clone().cross(perp).multiplyScalar(1 / Math.tan(angle / 2))).multiplyScalar(0.5).toArray() as V3
}
const plcM = (p: Plc) => new THREE.Matrix4().compose(new THREE.Vector3(...p.base), new THREE.Quaternion(...p.rotation), new THREE.Vector3(1, 1, 1))
const plcOf = (m: THREE.Matrix4): Plc => { const t = ofM(m); return { base: t.pos, rotation: t.rot } }
/** The world centre of a component's bounding box at a placement (getCenterOfBoundingBox; the scene's box moved). */
function centerAt(comp: string, plc: THREE.Matrix4, solved: Record<string, Plc>): THREE.Vector3 {
  const sc = getState().scene
  const bodies = leaves(getState().assembly).filter((l) => l.moving === comp)
  const c = new THREE.Vector3()
  let n = 0
  for (const l of bodies) {
    const b = sc?.bodies.find((x) => x.name === l.name)
    if (!b?.bbox || !solved[comp]) continue
    const mid = new THREE.Vector3(...b.bbox[0]).add(new THREE.Vector3(...b.bbox[1])).multiplyScalar(0.5)
    c.add(mid.applyMatrix4(plc.clone().multiply(plcM(solved[comp]).invert())))
    n++
  }
  return n ? c.multiplyScalar(1 / n) : new THREE.Vector3().setFromMatrixPosition(plc)
}
/** getComAndSize(assembly): the centre and diagonal of the Assembly's bounding box. */
function comAndSize(): { com: THREE.Vector3; size: number } {
  const bb = getState().scene?.bbox
  if (!bb) return { com: new THREE.Vector3(), size: 100 }
  const lo = new THREE.Vector3(...bb[0]), hi = new THREE.Vector3(...bb[1])
  return { com: lo.clone().add(hi).multiplyScalar(0.5), size: lo.distanceTo(hi) || 100 }
}
/** ExplodedView.applyMoves: the moves one after the other on the parts, from where they are. */
function applyMoves(moves: Move[], solved: Record<string, Plc>): Record<string, Plc> {
  const out: Record<string, THREE.Matrix4> = Object.fromEntries(Object.entries(solved).map(([n, p]) => [n, plcM(p)]))
  const { com, size } = comAndSize()
  for (const m of moves) {
    const factor = m.type === 'Radial' ? (4 * vlen(m.t.pos)) / size : 1
    for (const r of m.references) {
      if (!out[r]) continue
      if (m.type === 'Radial') {
        const init = centerAt(r, out[r], solved).sub(com).multiplyScalar(factor)
        out[r] = out[r].clone().premultiply(new THREE.Matrix4().makeTranslation(init.x, init.y, init.z))
      } else out[r] = toM(m.t).multiply(out[r])
    }
  }
  return Object.fromEntries(Object.entries(out).map(([n, m]) => [n, plcOf(m)]))
}
/** TaskAssemblyCreateView.adjustDependentMoves: a move changed, each later Normal move of the same parts turned into
 *  their new frame (delta * T * delta^-1), so it keeps acting on them as it did. */
function adjustDependentMoves(ms: Move[], k: number, oldT: Move['t'], solved: Record<string, Plc>): Move[] {
  const out = ms.map((m) => ({ ...m }))
  const oldP: Record<string, THREE.Matrix4> = Object.fromEntries(Object.entries(solved).map(([n, p]) => [n, plcM(p)]))
  const newP: Record<string, THREE.Matrix4> = Object.fromEntries(Object.entries(oldP).map(([n, m]) => [n, m.clone()]))
  out.forEach((m, i) => {
    const names = m.references.filter((n) => oldP[n])
    const before = toM(m.t)
    if (i > k && m.type === 'Normal') {
      for (const n of names) {
        const delta = newP[n].clone().multiply(oldP[n].clone().invert())
        const d = ofM(delta)
        if (vlen(d.pos) <= CONFUSION && angleOf(d.rot) <= ANGULAR) continue
        m.t = ofM(delta.clone().multiply(toM(m.t)).multiply(delta.clone().invert()))
        break
      }
    }
    const tOld = i === k ? toM(oldT) : before, tNew = toM(m.t)
    for (const n of names) { oldP[n] = tOld.clone().multiply(oldP[n]); newP[n] = tNew.clone().multiply(newP[n]) }
  })
  return out
}
const moveOf = (o: AsmObj): Move => {
  const t = Array.isArray(o.movement_transform) ? o.movement_transform as [number[], number[]] : [[0, 0, 0], [0, 0, 0, 1]]
  const rot = t[1].length === 4 ? t[1] as Q4 : qOf(quatOfYpr(t[1][0], t[1][1], t[1][2]))
  return { name: o.name, references: [...((o.references as string[]) ?? [])], t: { pos: [...t[0]] as V3, rot }, type: o.move_type === 'Radial' ? 'Radial' : 'Normal', label: o.label ? String(o.label) : o.name }
}

/** TaskAssemblyCreateView: Parts as single solid, the moves (label and distance or angle; right click Edit placement,
 *  Delete removes), Align dragger to... (Align to part center, Align to part origin), Radial explosion. Clicks in the 3D
 *  view toggle the components selected; dragging the dragger makes a move of them: a translation (or a rotation about
 *  the dragger's centre, when there is no translation) from where the dragger was. OK writes the view's moves. */
export function ExplodedViewTask({ edit }: { edit?: string }) {
  const v = useStore((s) => s.assembly)
  const solved = useMemo(() => Object.fromEntries((v?.solver?.parts ?? []).map((p) => [p.name, p.placement])) as Record<string, Plc>, [])
  const [moves, setMoves] = useState<Move[]>(() => {
    const view = edit ? asmObject(v, edit) : undefined
    return ((view?.group as string[]) ?? []).map((n) => asmObject(v, n)).filter((o): o is AsmObj => !!o).map(moveOf)
  })
  const [single, setSingle] = useState(true)
  const [sel, setSel] = useState<string[]>([])
  const [radial, setRadial] = useState(false)
  const [align, setAlign] = useState<'Center' | 'PartOrigin'>('Center')
  const [menu, setMenu] = useState(false)
  const [placing, setPlacing] = useState<number | null>(null)
  const [stepSel, setStepSel] = useState(-1)
  const movesRef = useRef(moves); movesRef.current = moves
  const selRef = useRef(sel); selRef.current = sel
  const radialRef = useRef(radial); radialRef.current = radial
  const current = useRef<number | null>(null)              // TaskAssemblyCreateView.currentStep: the move a drag makes
  const initial = useRef<THREE.Matrix4 | null>(null)      // the dragger's placement when the move began
  const before = useRef<Record<string, Plc>>({})          // where the moves before the current one leave the parts
  // the moves shown: the parts where applyMoves puts them, with the lines
  const shown = (ms: Move[]) => {
    const placements = applyMoves(ms, solved)
    showPlacements(placements)
    return placements
  }
  useEffect(() => { shown(moves) }, [JSON.stringify(moves)])
  useEffect(() => () => { getView()?.stopTransform(true); showPlacements(null); showExploded(null) }, [])
  /** setDragger / findDraggerInitialPlc: the dragger on the selected parts, at their bounding box's centre (or the first
   *  one's origin), turned as the first one is. */
  const placeDragger = () => {
    const view = getView()
    view?.stopTransform(true)
    initial.current = null
    if (!view || !sel.length) return
    const placements = applyMoves(movesRef.current, solved)
    before.current = placements
    const first = plcM(placements[sel[0]])
    const pivot = first.clone()
    if (align === 'Center') {
      const c = new THREE.Vector3()
      for (const n of sel) c.add(centerAt(n, plcM(placements[n]), solved))
      c.multiplyScalar(1 / sel.length)
      pivot.setPosition(c)
    }
    const body = leaves(getState().assembly).find((l) => l.moving === sel[0])?.name
    if (!body) return
    initial.current = pivot.clone()
    view.startTransform({ body, pivot, snap: { mm: 0, deg: 0 }, onChange: (dragger, _delta, phase) => onDrag(dragger, phase) })
  }
  useEffect(() => { placeDragger() }, [sel.join('\n'), align])
  /** draggerMoved / draggerFinished: the move made on the first motion, its MovementTransform the dragger's move (a pure
   *  translation, or a rotation about the dragger's centre when it has not moved), its Label movementLabel's. */
  const onDrag = (dragger: THREE.Matrix4, phase: string) => {
    const init = initial.current
    if (!init || phase === 'set') return
    if (phase === 'finish') {
      const wasRadial = current.current !== null && movesRef.current[current.current]?.type === 'Radial'
      current.current = null
      if (wasRadial) { setSel([]); setRadial(false) } else placeDragger()       // draggerFinished
      return
    }
    const d = ofM(dragger.clone().multiply(init.clone().invert()))
    const ip = new THREE.Vector3().setFromMatrixPosition(init), dp = new THREE.Vector3().setFromMatrixPosition(dragger)
    const translation = dp.distanceTo(ip)
    const tol = Math.max(CONFUSION, 4 * SINGLE * Math.max(...ip.toArray().map(Math.abs), ...dp.toArray().map(Math.abs), 1))
    let t = d
    if (!radialRef.current && angleOf(d.rot) > ANGULAR && translation <= tol) {
      // a rotation about the dragger's centre: Base = c - R c
      const c = ip.clone(), rc = c.clone().applyQuaternion(new THREE.Quaternion(...d.rot))
      t = { pos: c.sub(rc).toArray() as V3, rot: d.rot }
    } else if (translation > tol) t = { pos: dp.clone().sub(ip).toArray() as V3, rot: [0, 0, 0, 1] }
    const ms = movesRef.current
    const k = current.current ?? ms.length
    current.current = k
    const m: Move = { ...(ms[k] ?? { references: [...selRef.current], type: radialRef.current ? 'Radial' : 'Normal', label: '' }), t }
    m.label = movementLabel(m)
    const out = [...ms]
    out[k] = m
    movesRef.current = out
    setMoves(out)
  }
  // clicks in the 3D view: a component selected or deselected (ExplodedViewSelGate: within the assembly; addSelection:
  // an element picked selects its part, as "Parts as single solid" makes it the component)
  useEffect(() => {
    const view = getView()
    if (!view) return
    view.pointPicker = (body) => {
      if (!body || !isComponent(body)) return
      const part = movingOf(body)               // a component is one solid here: single or not, the pick is its part
      setRadial(false)
      setSel((x) => (x.includes(part) ? x.filter((p) => p !== part) : [...x, part]))
    }
    return () => { view.pointPicker = null }
  }, [single])
  /** onRadialClicked: every movable part selected; the next drag makes a Radial move. */
  const radialClicked = () => {
    setSel([...new Set(leaves(getState().assembly).map((l) => l.moving))])
    setRadial(true)
  }
  /** onMoveValueChanged: the distance (setMovementDistance: the direction kept) or the angle (setMovementAngle: the
   *  axis and centre kept) of a move. */
  const setValue = (k: number, x: number) => setMoves((ms) => {
    const m = { ...ms[k] }
    const oldT = ms[k].t
    if (editMode(m) === 'Angle') {
      const a = new THREE.Vector3(...axisOf(m.t.rot)).normalize(), c = new THREE.Vector3(...rotationCenter(m.t))
      const q = new THREE.Quaternion().setFromAxisAngle(a, (x * Math.PI) / 180)
      m.t = { pos: c.clone().sub(c.clone().applyQuaternion(q)).toArray() as V3, rot: qOf(q) }
    } else {
      const dir = vlen(m.t.pos) > 0 ? m.t.pos : m.type === 'Radial' ? [1, 0, 0] : null
      if (!dir) return ms
      const n = vlen(dir)
      m.t = { pos: dir.map((c) => (c / n) * Math.max(0, x)) as V3, rot: m.t.rot }
    }
    const out = [...ms]
    out[k] = m
    return adjustDependentMoves(out, k, oldT, solved)
  })
  const ok = async () => {
    getView()?.stopTransform(true)
    closeTask()
    showPlacements(null)
    await applyAssembly([{ op: 'exploded_view', ...(edit ? { name: edit } : {}), moves: moves.map((m) => ({ ...(m.name ? { name: m.name } : {}),
      references: m.references, movement_transform: [m.t.pos, m.t.rot], move_type: m.type, label: m.label })) }], edit ? 'Edit Exploded View' : 'Create Exploded View')
  }
  const cancel = () => { getView()?.stopTransform(true); closeTask(); showPlacements(null) }
  const offOfMove = (m: Move): Off => ({ pos: m.t.pos, ypr: yprOfQuat(new THREE.Quaternion(...m.t.rot)) })
  return <div className="tasks as-task" data-task="explode">
    <TaskBox title="Exploded View" icon="as-exploded">
      <label className="tcheck" data-qf="CheckBox_PartsAsSingleSolid" title="Treat parts as single solids: a pick moves its whole component">
        <input type="checkbox" checked={single} onChange={(e) => setSingle(e.target.checked)} /> Parts as single solid</label>
      <div className="as-list" data-qf="stepList" tabIndex={0} onKeyDown={(e) => {
        // eventFilter: Delete removes the selected moves
        if (e.key === 'Delete' && current.current === null && placing === null && stepSel >= 0) { setMoves((ms) => ms.filter((_, i) => i !== stepSel)); setStepSel(-1) }
      }}>
        {moves.map((m, k) => <div key={k} className={`as-item as-step${k === stepSel ? ' sel' : ''}`} data-step={m.name ?? `new${k}`} onClick={() => setStepSel(k)}
          onContextMenu={(e) => { e.preventDefault(); setStepSel(k); setPlacing(k) }} title="Right click: Edit placement">
          <span>{m.label}</span>
          <QuantityBox key={`${k}:${JSON.stringify(m.t)}`} value={editMode(m) === 'Angle' ? (angleOf(m.t.rot) * 180) / Math.PI : vlen(m.t.pos)}
            dims={editMode(m) === 'Angle' ? ANGLE : LENGTH} min={editMode(m) === 'Angle' ? -360 : 0} max={editMode(m) === 'Angle' ? 360 : 1e9}
            title={editMode(m) === 'Angle' ? 'Angle of this exploded-view move' : 'Distance of this exploded-view move'} onChange={(x) => setValue(k, x)} />
        </div>)}
      </div>
      <div className="as-align">
        <button className="qbtn" data-qf="btnAlignDragger" disabled={!sel.length} onClick={() => setMenu((x) => !x)}>{sel.length ? 'Align dragger to...' : 'Select a part'}</button>
        {menu && sel.length > 0 && <div className="as-menu">
          <button className="qbtn" disabled title="n/a: aligning the dragger to a hovered feature is not ported">Align to...</button>
          <button className="qbtn" onClick={() => { setAlign('Center'); setMenu(false) }}>Align to part center</button>
          <button className="qbtn" onClick={() => { setAlign('PartOrigin'); setMenu(false) }}>Align to part origin</button>
        </div>}
      </div>
      <button className="qbtn" data-qf="btnRadialExplosion" onClick={radialClicked}>Explode Radially</button>
      {sel.length > 0 && <p className="hint">{sel.join(', ')}{radial ? ' (radial)' : ''}: drag the dragger to make a move</p>}
    </TaskBox>
    <div className="tbuttons pd-buttons">
      <button className="qbtn default" onClick={() => void ok()}>OK</button>
      <button className="qbtn" onClick={cancel}>Cancel</button>
    </div>
    {placing !== null && moves[placing] && <OffsetDialog title="MovementTransform" value={offOfMove(moves[placing])}
      onApply={(o) => setMoves((ms) => {
        const out = [...ms]
        out[placing] = { ...ms[placing], t: { pos: o.pos, rot: qOf(quatOfYpr(...o.ypr)) } }
        return adjustDependentMoves(out, placing, ms[placing].t, solved)              // onMovePlacementChanged
      })}
      onClose={() => setPlacing(null)} />}
  </div>
}
