// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/TaskDlgEditSketch.cpp: 2009 Jürgen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherMessages.cpp: 2011 Jürgen Riegel
//   src/Gui/TaskView/TaskSolverMessages.cpp: 2011 Jürgen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherConstraints.cpp: 2009 Juergen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherElements.cpp: 2014 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditDatumDialog.cpp: 2011 Werner Mayer
//   src/Mod/Sketcher/Gui/SketchOrientationDialog.cpp: 2011 Jürgen Riegel
//   src/Mod/Sketcher/Gui/ViewProviderSketch.cpp: 2009 Juergen Riegel
//   src/Gui/Action.cpp: 2004 Werner Mayer
// The Sketcher's widgets: the edit mode's toolbars (group commands as split buttons, ActionGroup with its
// drop-down) and the Sketch menu; the task panel (TaskDlgEditSketch: the solver messages with their links, the
// constraints and the elements lists, OK and Cancel); the datum dialog (EditDatumDialog) for a new dimension and
// for a double-clicked one; the orientation dialog of Sketcher_NewSketch; the edit mode's context menu.
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import * as S from './sketcher'
import * as SK from './sketch'
import { sketcherIcon } from './sketchdraw'
import { EDIT_TOOLBARS, SKETCHER_TOOLBAR, SKETCH_MENU, cmdInfo, groupDefault, iconOf, isEnabled, isImplemented, runSketchCommand, onNewSketch, why, type MenuItem, type ToolItem } from './sketchcmds'
import { onDatumDialog } from './sketchcons'
import { CONSTR_ICONS } from './sketchcmdinfo'
import { getState, report, useStore } from './store'
import { getView, onEditSketch } from './actions'
import { onSketchSelection } from './commands'
import { bodyOfPart, sketchMatrix } from './partdesign'
import * as THREE from 'three'
import { ContextMenu, tipAttrs, type Entry } from './chrome'
import { QuantityBox } from './qsb'
import { cls } from './panels'

const useSketch = () => useSyncExternalStore(S.subscribeSketch, S.sketchVersion)
/** A command's icon file; geometry tools show their construction variant in construction mode. */
function pixmapOf(name: string) {
  const p = iconOf(name)
  return p && S.isConstructionMode() && CONSTR_ICONS.has(p) ? `${p}_Constr` : p
}
const keyText = (accel: string) => accel
function tip(name: string) {
  const i = cmdInfo(name), w = why(name)
  return tipAttrs(undefined, w ? `${i.tip} (${w})` : i.tip, { head: i.menu, shown: name, key: keyText(i.accel) })
}

// ── toolbars ─────────────────────────────────────────────────────────────────────────────────────────────────────
function Img({ name, size }: { name: string; size: number }) {
  return name ? <img src={sketcherIcon(name)} width={size} height={size} alt="" draggable={false} className="ico" /> : <span style={{ width: size, height: size, display: 'inline-block' }} />
}
function CmdButton({ name }: { name: string }) {
  const n = useStore((s) => s.toolbarIconSize)
  return <button className="tb-btn" style={{ width: n + 9, height: n + 9 }} {...tip(name)} data-cmd={name} disabled={!isEnabled(name)} onClick={() => runSketchCommand(name)}><Img name={pixmapOf(name)} size={n} /></button>
}
/** Gui::GroupCommand / ActionGroup with a drop-down: the button runs the command it shows (the last one picked), the
 *  arrow lists them all. */
function GroupButton({ group, items }: { group: string; items: string[] }) {
  const n = useStore((s) => s.toolbarIconSize)
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const cur = groupDefault(group, items)
  const entries = (): Entry[] => items.map((c) => (c === 'sep' ? 'sep' : cmdEntry(c)))
  return (
    <span className="tb-split">
      <button className="tb-btn" style={{ width: n + 9, height: n + 9 }} {...tip(cur)} data-cmd={cur} data-group={group} disabled={!isEnabled(cur)} onClick={() => runSketchCommand(cur)}><Img name={pixmapOf(cur)} size={n} /></button>
      <button className="tb-btn tb-drop" data-group-menu={group} title={cmdInfo(group).tip} onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt(at ? null : { x: r.left, y: r.bottom + 1 }) }}><span className="tb-caret">▾</span></button>
      {at && <ContextMenu at={at} entries={entries()} onClose={() => setAt(null)} />}
    </span>
  )
}
function Items({ items }: { items: ToolItem[] }) {
  return <>{items.map((it, i) => it === 'sep' ? <span key={i} className="tb-sep" /> : typeof it === 'string' ? <CmdButton key={i} name={it} /> : <GroupButton key={i} group={it.group} items={it.items} />)}</>
}
/** Workbench::setupToolBars: the Sketcher toolbar out of edit, the edit mode's toolbars while a sketch is in edit
 *  (Workbench::enterEditMode makes them ForceAvailable and hides the Sketcher one). */
export function SketchToolbars() {
  useSketch()
  useStore((s) => s.sketchEditing); useStore((s) => s.selected)
  if (!S.isEditing()) return <span className="tb-group" data-toolbar="Sketcher" title="Sketcher"><span className="tb-grip" /><Items items={SKETCHER_TOOLBAR} /></span>
  return <>{EDIT_TOOLBARS.map((tb) => <span key={tb.title} className="tb-group" data-toolbar={tb.title} title={tb.title}><span className="tb-grip" /><Items items={tb.items} /></span>)}</>
}

// ── the Sketch menu ──────────────────────────────────────────────────────────────────────────────────────────────
function cmdEntry(name: string): Entry {
  const i = cmdInfo(name)
  return { label: i.menu, cmd: name, img: pixmapOf(name) ? sketcherIcon(pixmapOf(name)) : undefined, kbd: i.accel || undefined, disabled: !isEnabled(name),
    title: why(name) ? `${i.tip} (${why(name)})` : i.tip, onSelect: () => runSketchCommand(name) }
}
const menuEntry = (m: MenuItem): Entry => (m === 'sep' ? 'sep' : typeof m === 'string' ? cmdEntry(m) : { label: m.menu, sub: m.items.map(menuEntry) })
/** Workbench::setupMenuBar's "S&ketch". */
export const sketchMenuEntries = (): Entry[] => SKETCH_MENU.map(menuEntry)

// ── the task panel (TaskDlgEditSketch) ───────────────────────────────────────────────────────────────────────────
function Box({ title, icon, children, id }: { title: string; icon: string; children: React.ReactNode; id: string }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="tbox" data-box={id}>
      <div className="tbox-head" onClick={() => setOpen(!open)}><Img name={icon} size={16} /><span>{title}</span><span className={cls('twisty', open && 'open')}>{open ? '▴' : '▾'}</span></div>
      {open && <div className="tbox-body">{children}</div>}
    </div>
  )
}
/** TaskSolverMessages' status colours (registerState): the window text, or Qt's named colours. */
const STATE_COLOR: Record<S.SolverMessage['state'], string> = {
  empty: 'inherit', under_constrained: 'inherit', malformed_constraints: 'red', conflicting_constraints: 'orangered', redundant_constraints: 'red',
  partially_redundant_constraints: 'royalblue', solver_failed: 'red', fully_constrained: 'green',
}
const LINK_TIP: Record<string, string> = {
  '#conflicting': 'Selects these conflicting constraints', '#redundant': 'Selects these redundant constraints',
  '#dofs': 'The sketch has unconstrained elements giving rise to those Degrees Of Freedom. Selects these unconstrained elements.',
  '#malformed': 'Selects these malformed constraints', '#partiallyredundant': 'Some constraints in combination are partially redundant. Selects these partially redundant constraints.',
}
const LINK_CMD: Record<string, string> = { '#conflicting': 'Sketcher_SelectConflictingConstraints', '#redundant': 'Sketcher_SelectRedundantConstraints', '#dofs': 'Sketcher_SelectElementsWithDoFs' }
function Messages() {
  const m = S.getMessage()
  const grid = S.showGrid()
  if (!m) return null
  return (
    <Box title="Sketch Edit" icon="Sketcher_Sketch" id="messages">
      <div className="sk-msg">
        <span className="sk-status" data-state={m.state} style={{ color: STATE_COLOR[m.state] }}>{m.text}</span>
        {m.link && <a href={m.link} className="sk-link" title={LINK_TIP[m.link]} onClick={(e) => { e.preventDefault(); const c = LINK_CMD[m.link]; if (c) runSketchCommand(c); else if (m.link === '#malformed') S.setSelection((S.getResult()?.malformed ?? []).map((i) => SK.constraintName(S.getConstraints()[i], i))) }}>{m.linkText}</a>}
      </div>
      <label className="tcheck"><input type="checkbox" checked={grid} onChange={(e) => S.setShowGrid(e.target.checked)} /> Display grid</label>
    </Box>
  )
}
function ConstraintsList() {
  const cs = S.getConstraints(), sel = new Set(S.getSelection()), hidden = S.hiddenConstraints()
  const r = S.getResult()
  const bad = new Set([...(r?.conflicting ?? []), ...(r?.redundant ?? [])])
  const pick = (i: number, e: React.MouseEvent) => {
    const name = SK.constraintName(cs[i], i)
    if (e.ctrlKey || e.metaKey) { if (sel.has(name)) S.rmvSelection(name); else S.addSelection(name) }
    else S.setSelection([name])
  }
  return (
    <Box title="Constraints" icon="Sketcher_ToggleConstraint" id="constraints">
      <ul className="sk-list" onMouseLeave={() => S.setPreselection(null)}>
        {cs.map((c, i) => (
          <li key={i} className={cls(sel.has(SK.constraintName(c, i)) && 'sel', bad.has(i) && 'bad', !c.active && 'off')} data-constraint={i}
            onMouseEnter={() => S.setPreselection({ constraints: [i] })} onClick={(e) => pick(i, e)}
            onDoubleClick={() => { if (SK.isDimensional(c)) openDatum(i, false) }}>
            <input type="checkbox" checked={!hidden.has(i)} title="Shows or hides the constraint in the 3D view" onClick={(e) => e.stopPropagation()} onChange={(e) => S.setConstraintHidden(i, !e.target.checked)} />
            <Img name={SK.listIcon(c)} size={16} />
            <span>{SK.listText(c, i)}</span>
          </li>
        ))}
      </ul>
    </Box>
  )
}
const ELEMENT_ICON: Record<string, string> = { Point: 'Sketcher_Element_Point_StartingPoint', LineSegment: 'Sketcher_Element_Line_Edge', Circle: 'Sketcher_Element_Circle_Edge', ArcOfCircle: 'Sketcher_Element_Arc_Edge' }
function ElementsList() {
  const geo = S.getGeometry(), sel = new Set(S.getSelection())
  const nameOf = (i: number) => (geo[i].type === 'Point' ? SK.vertexName(S.vertexIndexOf(i, SK.START)) : SK.edgeName(i))
  return (
    <Box title="Elements" icon="Sketcher_CreateLine" id="elements">
      <ul className="sk-list" onMouseLeave={() => S.setPreselection(null)}>
        {geo.map((g, i) => (
          <li key={i} className={cls(sel.has(nameOf(i)) && 'sel', g.construction && 'constr')} data-element={i}
            onMouseEnter={() => S.setPreselection(g.type === 'Point' ? { point: S.vertexIndexOf(i, SK.START) } : { curve: i })}
            onClick={(e) => { const n = nameOf(i); if (e.ctrlKey || e.metaKey) { if (sel.has(n)) S.rmvSelection(n); else S.addSelection(n) } else S.setSelection([n]) }}>
            <Img name={ELEMENT_ICON[g.type] ?? 'Sketcher_Element_SelectionTypeInvalid'} size={16} />
            <span>{SK.elementText(g, i)}</span>
          </li>
        ))}
      </ul>
    </Box>
  )
}
/** TaskDlgEditSketch: Messages, (Tool Parameters while a tool is on), Constraints, Elements; OK and Cancel. */
export function SketchTask() {
  useSketch()
  if (!S.isEditing()) return null
  return (
    <div className="tasks sketch-task">
      <div className="tbuttons">
        <button className="qbtn default" onClick={() => void S.closeEdit(true)}>OK</button>
        <button className="qbtn" onClick={() => void S.closeEdit(false)}>Cancel</button>
      </div>
      <Messages />
      <ConstraintsList />
      <ElementsList />
    </div>
  )
}

// ── the datum dialog (EditDatumDialog) ───────────────────────────────────────────────────────────────────────────
type DatumState = { id: number; isNew: boolean; done?: (ok: boolean) => void }
let datum: DatumState | null = null
const datumSubs = new Set<() => void>()
function setDatum(d: DatumState | null) { datum = d; datumSubs.forEach((f) => f()) }
/** EditDatumDialog::exec: refused while the sketch has conflicts; else the dialog, in a transaction of its own for a
 *  double-clicked dimension (a new one's command is still open). */
function openDatum(id: number, isNew: boolean, done?: (ok: boolean) => void) {
  const r = S.getResult()
  if (!isNew && r?.conflicting.length) { report('warn', 'Dimensional constraint: Not allowed to edit the datum because the sketch contains conflicting constraints'); return }
  if (!isNew) S.openCommand('Modify sketch constraints')
  setDatum({ id, isNew, done })
}
S.onEditDatum((id) => openDatum(id, false))
onDatumDialog((id, done) => openDatum(id, true, done))
const TITLES: Partial<Record<SK.ConstraintType, [string, string]>> = { Angle: ['Insert Angle', 'Angle'], Radius: ['Insert Radius', 'Radius'], Diameter: ['Insert Diameter', 'Diameter'] }
const LEN: [number, number, number, number, number, number, number, number] = [1, 0, 0, 0, 0, 0, 0, 0], DEG: typeof LEN = [0, 0, 0, 0, 0, 0, 0, 1]
function DatumDialog() {
  const d = useSyncExternalStore((f) => { datumSubs.add(f); return () => { datumSubs.delete(f) } }, () => datum)
  const c0 = d ? S.getConstraints()[d.id] : null
  const [val, setVal] = useState(0)
  const [name, setName] = useState('')
  const [reference, setReference] = useState(false)
  const [radius, setRadius] = useState(true)
  const okRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!c0) return
    setVal(c0.type === 'Angle' ? (c0.value * 180) / Math.PI : c0.value); setName(c0.name ?? ''); setReference(!c0.driving); setRadius(c0.type !== 'Diameter')
  }, [d]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!d || !c0) return null
  const [title, label] = TITLES[c0.type] ?? ['Insert Length', 'Length']
  const finish = (ok: boolean) => { setDatum(null); d.done?.(ok) }
  const accept = () => {
    const cs = S.getConstraints(), c = { ...cs[d.id] }
    if (c.type === 'Radius' && !radius) c.type = 'Diameter'
    else if (c.type === 'Diameter' && radius) c.type = 'Radius'
    if (!reference) c.value = c.type === 'Angle' ? (val * Math.PI) / 180 : val
    const nm = name.trim()
    if (nm !== (c.name ?? '')) {
      // SketcherGui::checkConstraintName: no clash with another, and a valid identifier
      if (nm && (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(nm) || cs.some((x, k) => k !== d.id && x.name === nm))) report('warn', `Value Error: the constraint name '${nm}' is not valid or is taken`)
      else c.name = nm
    }
    S.setConstraint(d.id, c)
    const r = S.solve()
    if (!r || r.status === 'failed' || r.conflicting.length) {
      report('err', `Value Error: the datum ${presentation(c)} cannot be set: the solver fails or finds conflicting constraints`)
      S.abortCommand()
      finish(false); return
    }
    S.commitCommand()
    finish(true)
  }
  const reject = () => { S.abortCommand(); finish(false) }
  const toggleReference = (on: boolean) => {
    setReference(on)
    const cs = S.getConstraints()
    S.setConstraint(d.id, { ...cs[d.id], driving: !on })
    S.solve()
    if (on) setVal(c0.type === 'Angle' ? (S.getConstraints()[d.id].value * 180) / Math.PI : S.getConstraints()[d.id].value)
  }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => {
      e.stopPropagation()
      if (e.key === 'Escape') { e.preventDefault(); reject() }
      if (e.key === 'Enter') { e.preventDefault(); accept() }
    }}>
      <div className="msgbox datum-dlg" role="dialog" aria-label={title}>
        <div className="msgbox-title">{title}</div>
        <div className="datum-body">
          <div className="hbox fill"><span>{label}</span>
            <QuantityBox value={val} dims={c0.type === 'Angle' ? DEG : LEN} disabled={reference} autoFocus onChange={(v) => { setVal(v); setReference(false) }} onFinish={() => okRef.current?.focus()} /></div>
          {(c0.type === 'Radius' || c0.type === 'Diameter') && <div className="hbox">
            <label className="tcheck"><input type="radio" checked={radius} onChange={() => setRadius(true)} /> Radius</label>
            <label className="tcheck"><input type="radio" checked={!radius} onChange={() => setRadius(false)} /> Diameter</label></div>}
          <div className="hbox fill"><span>Name</span><input className="qline" value={name} title="Constraint name (available for expressions)" onChange={(e) => setName(e.target.value)} /></div>
          <label className="tcheck" title="Reference (or constraint) dimension"><input type="checkbox" checked={reference} onChange={(e) => toggleReference(e.target.checked)} /> Reference</label>
        </div>
        <div className="msgbox-buttons">
          <button ref={okRef} className="qbtn default" onClick={accept}>OK</button>
          <button className="qbtn" onClick={reject}>Cancel</button>
        </div>
      </div>
    </div>, document.body)
}
const presentation = (c: SK.Constraint) => SK.presentationValue(c)

// ── Sketcher_NewSketch (SketchOrientationDialog) ─────────────────────────────────────────────────────────────────
let orientOpen = false
const orientSubs = new Set<() => void>()
const setOrient = (on: boolean) => { orientOpen = on; orientSubs.forEach((f) => f()) }
onNewSketch(() => setOrient(true))
/** SketchOrientationDialog::accept's placements (Base::Rotation(x, y, z, w), normalised). */
const ORIENT: Record<string, [S.Placement['rotation'], S.Placement['rotation'], 0 | 1 | 2]> = {
  XY: [[0, 0, 0, 1], [1, 0, 0, 0], 2],
  XZ: [[Math.SQRT1_2, 0, 0, Math.SQRT1_2], [0, Math.SQRT1_2, Math.SQRT1_2, 0], 1],
  YZ: [[0.5, 0.5, 0.5, 0.5], [-0.5, 0.5, 0.5, -0.5], 0],
}
const usedNames = new Set<string>()
/** getUniqueObjectName("Sketch"): Sketch, Sketch001, … */
function uniqueSketchName() {
  const taken = new Set([...usedNames, ...(getState().scene?.bodies ?? []).map((b) => b.name)])
  for (let i = 0; ; i++) { const n = i ? `Sketch${String(i).padStart(3, '0')}` : 'Sketch'; if (!taken.has(n)) { usedNames.add(n); return n } }
}
function OrientationDialog() {
  const open = useSyncExternalStore((f) => { orientSubs.add(f); return () => { orientSubs.delete(f) } }, () => orientOpen)
  const [plane, setPlane] = useState<'XY' | 'XZ' | 'YZ'>('XY')
  const [reverse, setReverse] = useState(false)
  const [offset, setOffset] = useState(0)
  if (!open) return null
  const accept = () => {
    setOrient(false)
    const [fwd, rev, axis] = ORIENT[plane], base: [number, number, number] = [0, 0, 0]
    base[axis] = offset
    const st = getState(), body = st.scene?.bodies.find((b) => st.selected.includes(b.name))
    void S.editSketch({ part: body?.part ?? null, name: uniqueSketchName(), placement: { base, rotation: reverse ? rev : fwd } })
  }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') setOrient(false); if (e.key === 'Enter') accept() }}>
      <div className="msgbox datum-dlg" role="dialog" aria-label="Choose Orientation">
        <div className="msgbox-title">Choose Orientation</div>
        <fieldset className="tgroup datum-body"><legend>Sketch Orientation</legend>
          {(['XY', 'XZ', 'YZ'] as const).map((p) => <label key={p} className="tcheck"><input type="radio" checked={plane === p} onChange={() => setPlane(p)} /> {p}-plane</label>)}
          <label className="tcheck"><input type="checkbox" checked={reverse} onChange={(e) => setReverse(e.target.checked)} /> Reverse direction</label>
          <div className="hbox fill"><span>Offset</span><QuantityBox value={offset} dims={LEN} onChange={setOffset} /></div>
        </fieldset>
        <div className="msgbox-buttons">
          <button className="qbtn default" onClick={accept}>OK</button>
          <button className="qbtn" onClick={() => setOrient(false)}>Cancel</button>
        </div>
      </div>
    </div>, document.body)
}

// ── the edit mode's context menu (ViewProviderSketch::generateContextMenu) ────────────────────────────────────────
function contextEntries(): Entry[] {
  const sel = S.getSelection()
  const cmds = sel.length
    ? ['Sketcher_ConstrainCoincidentUnified', 'Sketcher_ConstrainHorVer', 'Sketcher_ConstrainParallel', 'Sketcher_ConstrainPerpendicular', 'Sketcher_ConstrainTangent',
      'Sketcher_ConstrainEqual', 'Sketcher_ConstrainSymmetric', 'Sketcher_ConstrainBlock', 'sep', 'Sketcher_Dimension', 'Sketcher_ConstrainLock', 'sep',
      'Sketcher_ToggleConstruction', 'Sketcher_ToggleDrivingConstraint', 'sep', 'Sketcher_SelectConstraints', 'Sketcher_SelectElementsAssociatedWithConstraints']
    : ['Sketcher_CreatePoint', 'Sketcher_CreatePolyline', 'Sketcher_CreateLine', 'Sketcher_CreateArc', 'Sketcher_CreateCircle', 'Sketcher_CreateRectangle', 'sep',
      'Sketcher_SelectOrigin', 'Sketcher_SelectHorizontalAxis', 'Sketcher_SelectVerticalAxis', 'sep', 'Sketcher_LeaveSketch']
  const out: Entry[] = cmds.filter((c) => c === 'sep' || isImplemented(c)).map((c) => (c === 'sep' ? 'sep' : cmdEntry(c)))
  if (sel.length) out.push('sep', { label: 'Delete', kbd: 'Del', onSelect: S.deleteSelected })
  return out
}
function SketchMenu() {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  useStore((s) => s.sketchEditing)
  useEffect(() => {
    const v = getView()
    if (v) v.onSketchMenu = (x, y) => setAt({ x, y })
  })
  return at ? <ContextMenu at={at} entries={contextEntries()} onClose={() => setAt(null)} /> : null
}

// ── a Body's sketch opened from the tree (Std_Edit, a double-click: ViewProviderSketch::setEdit) ──────────────────
/** The sketch where its part sits: the part's matrix (scene.py) times the sketch's support and attachment offset. */
onEditSketch((part, name) => {
  const st = getState(), f = st.features[part]?.features.find((x) => x.name === name)
  if (!f) { report('err', `Edit Sketch: ${part}/${name} is not in the part's feature list`); return }
  const m = new THREE.Matrix4(), b = bodyOfPart(st, part)
  if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose()
  m.multiply(sketchMatrix(f))
  const pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3()
  m.decompose(pos, q, sc)
  const sketch = S.unsavedSketch(name) ?? { geometry: (f.geometry ?? []) as SK.Geo[], constraints: (f.constraints ?? []) as import('./solver').Cons[] }
  void S.editSketch({ part, name, placement: { base: [pos.x, pos.y, pos.z], rotation: [q.x, q.y, q.z, q.w] }, sketch })
})

// `cad gui select PROJECT Edge1 Vertex2 …` and `cad gui clear` while the sketch is in edit: "Edge1", "Vertex2",
// "Constraint3", "RootPoint", "H_Axis", "V_Axis", with or without the sketch's name before them.
onSketchSelection((cmd, args) => {
  if (!S.isEditing()) return false
  if (cmd === 'clear') S.clearSelection()
  else for (const a of args) S.addSelection(a.includes('.') ? a.slice(a.lastIndexOf('.') + 1) : a)
  return true
})

/** The dialogs and the context menu, mounted once (App.tsx). */
export function SketchHost() {
  return <><DatumDialog /><OrientationDialog /><SketchMenu /></>
}
