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
import { onDatumDialog, constraintCreationMode } from './sketchcons'
import { ConstraintsList, ElementsList, onOpenDatum, resolveExpressions, evaluateExpression, paramVars, checkConstraintName, renameConstraint } from './sketchpanels'
import { ExpressionDialog } from './exprdialog'
import { CONSTR_ICONS } from './sketchcmdinfo'
import { getState, report, useStore } from './store'
import { getView, onEditSketch } from './actions'
import { onSketchSelection } from './commands'
import { bodyOfPart, sketchMatrix } from './partdesign'
import { attachedOf } from './attached'
import { ExternalHandler, projectRefs } from './sketchexternal'
import { CarbonCopyHandler, setCarbonSources } from './sketchcarbontool'
import * as THREE from 'three'
import { ContextMenu, tipAttrs, type Entry } from './chrome'
import { QuantityBox } from './qsb'
import { cls } from './panels'
import { ArrayDialog } from './sketchxformtools'
import { ToolParametersBox } from './sketchtoolbox'
import { RegularPolygonDialog } from './sketchpolydlg'
import { SketchObjHost } from './sketchobjcmds'   // Map, Reorient, Validate, Merge, Mirror Sketch

const useSketch = () => useSyncExternalStore(S.subscribeSketch, S.sketchVersion)
/** The commands of the ToggleDrivingConstraint mode (CmdSketcherToggleDrivingConstraint's addCommandMode): their
 *  updateAction shows the icon's _Driven variant while new dimensions are reference ones. */
const DRIVEN_ICONS = new Set(['Constraint_Lock', 'Constraint_Length', 'Constraint_HorizontalDistance', 'Constraint_VerticalDistance', 'Constraint_Radius',
  'Constraint_Diameter', 'Constraint_Radiam', 'Constraint_InternalAngle', 'Constraint_Dimension', 'Sketcher_ToggleConstraint'])
/** A command's icon file; geometry tools show their construction variant in construction mode. */
function pixmapOf(name: string) {
  const p = iconOf(name)
  if (p && constraintCreationMode() === 'Reference' && DRIVEN_ICONS.has(p)) return `${p}_Driven`
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
const LINK_CMD: Record<string, string> = { '#conflicting': 'Sketcher_SelectConflictingConstraints', '#redundant': 'Sketcher_SelectRedundantConstraints', '#dofs': 'Sketcher_SelectElementsWithDoFs',
  '#malformed': 'Sketcher_SelectMalformedConstraints', '#partiallyredundant': 'Sketcher_SelectPartiallyRedundantConstraints' }
function Messages() {
  const m = S.getMessage()
  const grid = S.showGrid()
  if (!m) return null
  return (
    <Box title="Sketch Edit" icon="Sketcher_Sketch" id="messages">
      <div className="sk-msg">
        <span className="sk-status" data-state={m.state} style={{ color: STATE_COLOR[m.state] }}>{m.text}</span>
        {m.link && <a href={m.link} className="sk-link" title={LINK_TIP[m.link]} onClick={(e) => { e.preventDefault(); const c = LINK_CMD[m.link]; if (c) runSketchCommand(c) }}>{m.linkText}</a>}
      </div>
      <label className="tcheck"><input type="checkbox" checked={grid} onChange={(e) => S.setShowGrid(e.target.checked)} /> Display grid</label>
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
      <ToolParametersBox />
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
onOpenDatum((id) => openDatum(id, false))
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
  // labelEdit->bind(Constraints[i]): the expression the value is bound to, and the Expression Editor over the box
  const [expr, setExpr] = useState('')
  const [exprAt, setExprAt] = useState<{ x: number; y: number; text: string } | null>(null)
  const okRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!c0) return
    setVal(c0.type === 'Angle' ? (c0.value * 180) / Math.PI : c0.value); setName(c0.name ?? ''); setReference(!c0.driving); setRadius(c0.type !== 'Diameter')
    setExpr(c0.expr ?? ''); setExprAt(null)
  }, [d]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!d || !c0) return null
  const [title, label] = TITLES[c0.type] ?? ['Insert Length', 'Length']
  const part = S.getSession()?.ref.part ?? null
  const finish = (ok: boolean) => { setDatum(null); d.done?.(ok) }
  /** EditDatumDialog::accepted. */
  const accept = () => {
    const cs = S.getConstraints(), c = { ...cs[d.id] }
    if (c.type === 'Radius' && !radius) c.type = 'Diameter'
    else if (c.type === 'Diameter' && radius) c.type = 'Radius'
    if (!reference) {
      // labelEdit->apply() for a bound value (the expression's result), else setDatum
      if (expr) { const v = evaluateExpression(c, expr, part); c.expr = expr; if (v !== null) c.value = v }
      else { delete c.expr; c.value = c.type === 'Angle' ? (val * Math.PI) / 180 : val }
    }
    S.setConstraint(d.id, c)
    const nm = name.trim()
    if (nm !== (c.name ?? '') && checkConstraintName(nm)) {
      // renameConstraint raises on a name another constraint has: the whole edit is aborted (NotifyUserError)
      const err = renameConstraint(d.id, nm)
      if (err) { report('err', `Value Error: ${err}`); S.abortCommand(); finish(false); return }
    }
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
  /** drivingToggled: SketchObject::setDriving (a reference dimension loses its expression). */
  const toggleReference = (on: boolean) => {
    setReference(on)
    const cs = S.getConstraints(), next = { ...cs[d.id], driving: !on }
    if (on) { delete next.expr; setExpr('') }
    S.setConstraint(d.id, next)
    S.solve()
    if (on) setVal(c0.type === 'Angle' ? (S.getConstraints()[d.id].value * 180) / Math.PI : S.getConstraints()[d.id].value)
  }
  const dims = c0.type === 'Angle' ? DEG : LEN
  /** showFormulaDialog: the editor opens on the box; formEditorOpened unchecks Reference. */
  const openExpr = (at: { x: number; y: number }) => { if (reference) toggleReference(false); setExprAt({ ...at, text: expr || String(+val.toPrecision(10)) }) }
  const vars = Object.fromEntries(Object.entries(paramVars(part)).map(([k, v]) => [k, { value: v, dims: [0, 0, 0, 0, 0, 0, 0, 0] as typeof LEN }]))
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => {
      if (exprAt) return
      e.stopPropagation()
      if (e.key === 'Escape') { e.preventDefault(); reject() }
      if (e.key === 'Enter') { e.preventDefault(); accept() }
    }}>
      <div className="msgbox datum-dlg" role="dialog" aria-label={title}>
        <div className="msgbox-title">{title}</div>
        <div className="datum-body">
          <div className="hbox fill"><span>{label}</span>
            <QuantityBox value={val} dims={dims} disabled={reference || !!expr} autoFocus onChange={(v) => { setVal(v); setReference(false) }} onFinish={() => okRef.current?.focus()}
              onEquals={(_, at) => openExpr(at)} title={expr || undefined} />
            {/* ExpressionSpinBox: the bound-expression icon; a click opens the editor */}
            <button className="datum-fx" data-datum-fx title={expr || 'Enter an expression...'} onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); openExpr({ x: r.left - 250, y: r.top }) }}>
              <img src="./freecad-icons/bound-expression.svg" width={14} height={14} alt="" draggable={false} style={{ opacity: expr ? 1 : 0.35 }} /></button></div>
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
      {exprAt && <ExpressionDialog at={exprAt} text={exprAt.text} dims={dims} vars={vars} owner={part ?? undefined}
        onOk={(v, text) => { setExprAt(null); setExpr(text); setVal(v); setReference(false) }} onCancel={() => setExprAt(null)} />}
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
  const st = getState(), f = st.features[part]?.features.find((x) => x.name === name) ?? st.features[part]?.objects?.find((x) => x.name === name) // a document's sketch (part_wb.tsx)
  if (!f) { report('err', `Edit Sketch: ${part}/${name} is not in the part's feature list`); return }
  const m = new THREE.Matrix4(), b = bodyOfPart(st, part)
  if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose()
  m.multiply(sketchMatrix(f))
  const pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3()
  m.decompose(pos, q, sc)
  // a value bound to an expression (the part file's string value) is what the expression gives over the part's PARAMS
  const sketch = S.unsavedSketch(name) ?? { geometry: (f.geometry ?? []) as SK.Geo[], constraints: resolveExpressions((f.constraints ?? []) as import('./solver').Cons[], part) }
  void externalOf(f, part).then((external) => S.editSketch({ part, name, placement: { base: [pos.x, pos.y, pos.z], rotation: [q.x, q.y, q.z, q.w] }, sketch, external }))
})
// Carbon Copy's sources: a Body's sketch as the Sketcher would open it, and the projection onto the sketch in edit
setCarbonSources((part, name) => {
  const st = getState(), f = st.features[part]?.features.find((x) => x.name === name)
  if (!f) return null
  const m = new THREE.Matrix4(), b = bodyOfPart(st, part)
  if (b?.matrix?.length === 16) m.fromArray(b.matrix).transpose()
  m.multiply(sketchMatrix(f))
  const pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3()
  m.decompose(pos, q, sc)
  const refs = ((f.external_geometry ?? []) as unknown[]).map((r) => (Array.isArray(r) ? [String(r[0]), String(r[1] ?? '')] : String(r).split('.', 2)) as [string, string])
  return { doc: { geometry: ((f.geometry ?? []) as SK.Geo[]).map((g) => ({ ...g })), constraints: ((f.constraints ?? []) as import('./solver').Cons[]).map(SK.fromCons) },
    refs, placement: { base: [pos.x, pos.y, pos.z], rotation: [q.x, q.y, q.z, q.w] } }
}, (refs) => projectRefs(refs))
/** The sketch's external geometry as the Body projected it (attached.external, after its build), and which of its
 *  references each came from: one geometry per edge or vertex; a face's are asked for again (`cad feature project`). */
async function externalOf(f: import('./store').Feature, part: string): Promise<S.External> {
  const refs = ((f.external_geometry ?? []) as unknown[]).map((r) => (Array.isArray(r) ? [String(r[0]), String(r[1] ?? '')] : String(r).split('.', 2)) as [string, string])
  const geometry = (attachedOf(f)?.external ?? []) as SK.Geo[]
  if (!refs.length) return { refs: [], geometry: [], owner: [] }
  if (geometry.length === refs.length && !refs.some((r) => r[1].startsWith('Face'))) return { refs, geometry, owner: refs.map((_, i) => i) }
  const p = await projectRefs(refs, part, f.name).catch(() => null)
  if (!p) return { refs, geometry, owner: geometry.map((_, i) => Math.min(i, refs.length - 1)) }
  return { refs, geometry: p.external.flat(), owner: p.external.flatMap((g, i) => g.map(() => i)) }
}

// `cad gui select PROJECT Edge1 Vertex2 …` and `cad gui clear` while the sketch is in edit: "Edge1", "Vertex2",
// "Constraint3", "RootPoint", "H_Axis", "V_Axis", with or without the sketch's name before them.
onSketchSelection((cmd, args) => {
  if (!S.isEditing()) return false
  if (cmd === 'clear') S.clearSelection()
  else for (const a of args) {
    // "Pad.Edge4" while External Projection is on: an element of the model, which the tool takes from the selection
    // (and a sketch while Carbon Copy is on: CarbonCopyHandler.pickNamed)
    const h = S.getHandler() as (S.Handler & { pickNamed?: (obj: string, sub: string) => boolean }) | null, dot = a.indexOf('.')
    const obj = dot > 0 ? a.slice(0, dot) : a, sub = dot > 0 ? a.slice(dot + 1) : ''
    if (h?.pickNamed && obj !== S.getSession()?.ref.name && (dot > 0 || h instanceof CarbonCopyHandler) && h.pickNamed(obj, sub)) continue
    S.addSelection(a.includes('.') ? a.slice(a.lastIndexOf('.') + 1) : a)
  }
  return true
})

/** The dialogs and the context menu, mounted once (App.tsx). */
export function SketchHost() {
  return <><DatumDialog /><OrientationDialog /><ArrayDialog /><RegularPolygonDialog /><SketchMenu /><SketchObjHost /></>
}
