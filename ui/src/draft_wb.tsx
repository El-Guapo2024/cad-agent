// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Draft/InitGui.py: 2009 Yorik van Havre; draftutils/init_tools.py: 2020 Eliud Cabrera Castillo, 2021 FreeCAD Developers
//   src/Mod/Draft/draftguitools/gui_*.py (each command's GetResources), draftmake/make_*.py (the names they give): 2009-2025
//   Yorik van Havre, Ken Cline, Eliud Cabrera Castillo, Carlo Pavan, the FreeCAD Project Association and others
// The Draft workbench, for part files with Draft objects (cad_agent/feature_draft.py: Draft.Rectangle(...) in OBJECTS, beside
// Part's): its Drafting and Modification menus and the Draft Creation and Draft Modification toolbars, every command by
// FreeCAD's name, pixmap, menu text and tooltip (draft_cmds.ts). The commands this port runs make the object its draftmake
// maker makes, named as it names it; where FreeCAD asks for points in the 3D view (with snapping and the working plane)
// the panel here asks for them as numbers. The tree, the property view (draft_props.ts), Space, Delete and F2 are
// part_wb.tsx's, as for any object of the document.
import { useState, type ReactNode } from 'react'
import { consoleLog, getState, report, useStore, type Feature } from './store'
import { closeTask, loadFeatures, loadHistory, openTask } from './actions'
import { api, resultText } from './api'
import { TaskBox } from './panels'
import { QComboBox } from './combo'
import { LENGTH, ANGLE, NUMBER } from './qsb'
import { messageBox } from './msgbox'
import { applyOps } from './partdesign'
import type { Entry } from './chrome'
import type { IconName } from './icons'
import { activeDoc, addObject, ensureDoc, objectOf, selectedObjects, setEditDraft, uniqueName } from './part_wb'
import { Buttons, Check, Field, Legend, Q } from './part_widgets'
import { DRAFT_CMDS, DRAFT_LISTS } from './draft_cmds'
import { DRAFT_PROPS } from './draft_props'
import type { PartProp } from './part_props'

// ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────────
/** What a command makes: the Draft type, the name its maker gives (make_wire names a Draft_Line "Line"), the values the
 *  panel starts from (FreeCAD's come from the points clicked), and the keys the panel shows. */
type Make = { type: string; base: string; start: Record<string, unknown>; keys: string[]; panel: boolean; sel?: 'one' | 'two' | 'many' }
const P = (x: number, y: number, z = 0) => [x, y, z]
const MAKES: Record<string, Make> = {
  Draft_Line: { type: 'Draft::Wire', base: 'Line', start: { points: [P(0, 0), P(10, 0)] }, keys: ['points'], panel: true },
  Draft_Wire: { type: 'Draft::Wire', base: 'Wire', start: { points: [P(0, 0), P(10, 0), P(10, 10)] }, keys: ['points', 'closed', 'make_face'], panel: true },
  Draft_Arc: { type: 'Draft::Circle', base: 'Arc', start: { radius: 10, first_angle: 0, last_angle: 90 }, keys: ['radius', 'first_angle', 'last_angle'], panel: true },
  Draft_Circle: { type: 'Draft::Circle', base: 'Circle', start: { radius: 10 }, keys: ['radius', 'make_face'], panel: true },
  Draft_Ellipse: { type: 'Draft::Ellipse', base: 'Ellipse', start: { major_radius: 10, minor_radius: 5 }, keys: ['major_radius', 'minor_radius', 'make_face'], panel: true },
  Draft_Rectangle: { type: 'Draft::Rectangle', base: 'Rectangle', start: { length: 20, height: 10 }, keys: ['length', 'height', 'make_face'], panel: true },
  Draft_Polygon: { type: 'Draft::Polygon', base: 'Polygon', start: { faces_number: 6, radius: 10 }, keys: ['faces_number', 'radius', 'draw_mode', 'make_face'], panel: true },
  Draft_BSpline: { type: 'Draft::BSpline', base: 'BSpline', start: { points: [P(0, 0), P(5, 5), P(10, 0)] }, keys: ['points', 'closed', 'make_face'], panel: true },
  Draft_BezCurve: { type: 'Draft::BezCurve', base: 'BezCurve', start: { points: [P(0, 0), P(3, 6), P(7, 6), P(10, 0)] }, keys: ['points', 'degree', 'closed'], panel: true },
  Draft_Point: { type: 'Draft::Point', base: 'Point', start: {}, keys: ['x', 'y', 'z'], panel: true },
  Draft_OrthoArray: { type: 'Draft::Array', base: 'Array', start: { array_type: 'ortho', number_x: 2, number_y: 2, number_z: 1 }, keys: ['number_x', 'number_y', 'number_z', 'interval_x', 'interval_y', 'interval_z', 'fuse'], panel: true, sel: 'one' },
  Draft_PolarArray: { type: 'Draft::Array', base: 'Array', start: { array_type: 'polar', number_polar: 5, angle: 360 }, keys: ['number_polar', 'angle', 'center', 'axis', 'interval_axis', 'fuse'], panel: true, sel: 'one' },
  Draft_CircularArray: { type: 'Draft::Array', base: 'Array', start: { array_type: 'circular' }, keys: ['radial_distance', 'tangential_distance', 'number_circles', 'symmetry', 'center', 'axis', 'fuse'], panel: true, sel: 'one' },
  Draft_PathArray: { type: 'Draft::PathArray', base: 'PathArray', start: {}, keys: [], panel: false, sel: 'two' },
  Draft_PointArray: { type: 'Draft::PointArray', base: 'PointArray', start: {}, keys: [], panel: false, sel: 'two' },
  Draft_Clone: { type: 'Draft::Clone', base: 'Clone', start: {}, keys: [], panel: false, sel: 'many' },
}
/** The modifications: Draft's own move / rotate / scale / offset run on the server (`cad feature draft`, draft_modify.py),
 *  with the panel's values as the GUI command's Draft.move(...) line takes them. */
type Mod = { op: 'move' | 'rotate' | 'scale' | 'offset'; one?: boolean }
const MODS: Record<string, Mod> = {
  Draft_Move: { op: 'move' }, Draft_Rotate: { op: 'rotate' }, Draft_Scale: { op: 'scale' }, Draft_Offset: { op: 'offset', one: true },
}
/** Why a command of the workbench is not offered (it stays in its menu, greyed, as the port's other n/a commands do). */
const WHY: Record<string, string> = {
  Draft_Fillet: 'a Draft fillet joins two selected wires in the 3D view, which needs edge picking on Draft wires',
  Draft_Arc_3Points: 'an arc through three points clicked in the 3D view', Draft_CubicBezCurve: 'a curve dragged in the 3D view',
  Draft_Facebinder: 'faces picked on other objects', Draft_ShapeString: 'text needs a font file, which the page does not read',
  Draft_Hatch: 'a hatch needs a PAT file',
}
const NOT_YET = 'not ported yet: annotations, Trimex, Stretch, Upgrade, layers and the working plane need the 3D view\'s Draft tracker'

const cmdOf = (c: string) => DRAFT_CMDS[c] ?? { pixmap: null, menu: c, tip: null, accel: null }
const iconOf = (c: string) => (cmdOf(c).pixmap ? `df-${cmdOf(c).pixmap}` : undefined) as IconName | undefined
function entry(c: string): Entry {
  const r = cmdOf(c), mk = MAKES[c], label = r.menu ?? c
  if (r.group) return { label, icon: iconOf(c), cmd: c, title: r.tip ?? undefined, sub: r.group.map(entry) }
  const part = activeDoc(), n = part ? selectedObjects(part).length : 0
  const mod = MODS[c]
  if (mod) return { label, icon: iconOf(c), cmd: c, disabled: mod.one ? n !== 1 : n < 1, title: r.tip ?? undefined,
    onSelect: () => { if (part) openTask('draftwb', part, c) } }
  if (!mk) return { label, icon: iconOf(c), cmd: c, disabled: true, title: `n/a: ${WHY[c] ?? NOT_YET}` }
  const disabled = mk.sel === 'one' ? n !== 1 : mk.sel === 'two' ? n !== 2 : mk.sel === 'many' ? n < 1 : false
  return { label, icon: iconOf(c), cmd: c, disabled, title: r.tip ?? undefined, onSelect: () => void run(c) }
}
const entries = (list: string) => (DRAFT_LISTS[list] ?? []).map((c): Entry => (c === 'Separator' ? 'sep' : entry(c)))
export function draftMenus(): [string, Entry[]][] {
  return [['Drafting', entries('get_draft_drawing_commands')], ['Annotation', entries('get_draft_annotation_commands')],
    ['Modification', entries('get_draft_modification_commands')], ['Utilities', entries('get_draft_utility_commands_menu')]]
}
export function draftToolbars(): [string, Entry[]][] {
  return [['Draft Creation', entries('get_draft_drawing_commands')], ['Draft Annotation', entries('get_draft_annotation_commands')],
    ['Draft Modification', entries('get_draft_modification_commands')], ['Draft Utility', entries('get_draft_utility_commands_toolbar')]]
}
/** Every Draft command the port runs, by FreeCAD's name (cmdreg.ts, shortcuts). */
export function draftCommands(): [string, Exclude<Entry, 'sep'>][] {
  const out: [string, Exclude<Entry, 'sep'>][] = []
  const walk = (es: Entry[]) => { for (const e of es) { if (e === 'sep') continue; if (e.cmd && e.onSelect && !out.some(([c]) => c === e.cmd)) out.push([e.cmd, e]); if (e.sub) walk(e.sub) } }
  for (const [, es] of draftMenus()) walk(es)
  return out
}
export const draftRun = (cmd: string) => draftCommands().find(([c]) => c === cmd)?.[1].onSelect?.()
export const draftEnabled = (cmd: string) => { const e = draftCommands().find(([c]) => c === cmd)?.[1]; return !!e && !e.disabled }
/** The menus and toolbars as plain data, for draftcheck.mjs (cadui.draft()). */
export function draftData() {
  const plain = (es: Entry[]): unknown[] => es.map((e) => (e === 'sep' ? { sep: true } : { text: e.label, cmd: e.cmd ?? null, enabled: !e.disabled, ...(e.sub ? { menu: plain(e.sub) } : {}) }))
  return { menus: draftMenus().map(([t, es]) => ({ title: t, entries: plain(es) })), toolbars: draftToolbars().map(([t, es]) => ({ title: t, buttons: plain(es) })) }
}

async function run(c: string) {
  const mk = MAKES[c]
  if (mk.panel && !mk.sel) { const part = await ensureDoc(); if (part) openTask('draftwb', part, c); return }
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  if (!part || !sel.length) { void messageBox('warning', 'Wrong selection', 'Select an object first.'); return }
  if (mk.panel) { openTask('draftwb', part, c); return }
  const doc = getState().features[part]
  const links = mk.type === 'Draft::Clone' ? { objects: sel } : mk.type === 'Draft::PathArray' ? { base: sel[0], path_object: sel[1] }
    : { base: sel[0], point_object: sel[1] }
  await addObject(part, { name: uniqueName(doc, mk.base), type: mk.type, ...links } as Feature, cmdOf(c).menu ?? c)
}
/** Std_Edit on a Draft object: the panel of the command that makes it, its values loaded. */
export function editDraft(part: string, name: string): boolean {
  const o = objectOf(getState().features[part], name)
  if (!o || !String(o.type).startsWith('Draft::')) return false
  const c = Object.keys(MAKES).find((k) => MAKES[k].type === o.type && MAKES[k].panel
    && (o.type !== 'Draft::Array' || MAKES[k].start.array_type === (o.array_type ?? 'ortho'))
    && (o.type !== 'Draft::Circle' || (k === 'Draft_Arc') === (Number(o.first_angle ?? 0) !== Number(o.last_angle ?? 0))))
  if (!c) return false
  openTask('draftwb', part, `${c}:${name}`)
  return true
}

setEditDraft(editDraft)

// ── the panel ────────────────────────────────────────────────────────────────────────────────────────────────────
/** FreeCAD's defaults of the panels' check boxes (feature_draft.py's DEFAULTS), for an object that leaves them out */
const BOOLS: Record<string, boolean> = { make_face: true, closed: false, fuse: false }
const isVec = (t: string) => t === 'App::PropertyVector' || t === 'App::PropertyVectorDistance'
function dimsOf(r: PartProp) {
  if (/Angle/.test(r.t)) return ANGLE
  if (/Length|Distance/.test(r.t)) return LENGTH
  return NUMBER
}
const human = (p: string) => p.replace(/([a-z])([A-Z])/g, '$1 $2')
/** The command's values as numbers, and the object's placement position: OK adds the object (or sets an edited one's). */
export function DraftTask({ part, other }: { part: string; other: string }) {
  const c0 = other.includes(':') ? other.slice(0, other.indexOf(':')) : other
  if (MODS[c0]) return <ModifyTask key={other} part={part} c={c0} />
  return <MakeTask key={other} part={part} other={other} />
}
function MakeTask({ part, other }: { part: string; other: string }) {
  const [c, edit] = other.includes(':') ? [other.slice(0, other.indexOf(':')), other.slice(other.indexOf(':') + 1)] : [other, undefined]
  const doc = useStore((s) => s.features[part])
  const mk = MAKES[c]
  const existing = edit ? objectOf(doc, edit) : undefined
  const rows = DRAFT_PROPS[mk?.type ?? ''] ?? []
  const [sel] = useState(() => (existing ? [] : selectedObjects(part)))
  const [vals, setVals] = useState<Record<string, unknown>>(() => {
    const out: Record<string, unknown> = {}
    for (const k of mk?.keys ?? []) {
      const r = rows.find((x) => x.k === k)
      out[k] = existing?.[k] ?? mk.start[k] ?? (r && isVec(r.t) ? [0, 0, 0] : r?.t === 'App::PropertyBool' ? BOOLS[k] ?? false : undefined)
    }
    return out
  })
  const pl = (existing?.placement as number[][] | undefined) ?? [[0, 0, 0], [0, 0, 0]]
  const [pos, setPos] = useState<number[]>(pl[0])
  const [dirty, setDirty] = useState<Set<string>>(() => new Set())
  const [text, setText] = useState(() => ((vals.points as number[][] | undefined) ?? []).map((p) => p.join(', ')).join('\n'))
  if (!doc || !mk) return null
  const set = (k: string, v: unknown) => { setVals({ ...vals, [k]: v }); setDirty(new Set([...dirty, k])) }
  const rowOf = (k: string) => rows.find((x) => x.k === k)
  const field = (k: string): ReactNode => {
    const r = rowOf(k)
    if (!r) return null
    const label = human(r.p), v = vals[k]
    if (k === 'points') return <Field key={k} label="Points (x, y, z per line)">
      <textarea className="qline" data-qf="points" rows={5} value={text} onChange={(e) => { setText(e.target.value); setDirty(new Set([...dirty, 'points'])) }} /></Field>
    if (r.t === 'App::PropertyBool') return <Check key={k} label={label} name={k} checked={v === true} onChange={(x) => set(k, x)} />
    if (r.e) return <Field key={k} label={label}><QComboBox value={String(v ?? r.e[0])} onChange={(e) => set(k, e.target.value)}>
      {r.e.map((x) => <option key={x}>{x}</option>)}</QComboBox></Field>
    if (isVec(r.t)) {
      const vec = (v as number[] | undefined) ?? [0, 0, 0]
      return <Legend key={k} title={label}>{(['X', 'Y', 'Z'] as const).map((a, i) =>
        <Q key={a} label={a} name={`${k}${a}`} value={vec[i] ?? 0} dims={r.t === 'App::PropertyVector' ? NUMBER : LENGTH}
          onChange={(x) => { const w = [...vec]; w[i] = x; set(k, w) }} />)}</Legend>
    }
    const int = /Integer/.test(r.t)
    return <Q key={k} label={label} name={k} value={Number(v ?? 0)} dims={dimsOf(r)} step={int ? 1 : undefined} decimals={int ? 0 : undefined}
      min={int ? 0 : undefined} onChange={(x) => set(k, int ? Math.round(x) : x)} />
  }
  const ok = async () => {
    // a new object gets every value; an edited one only those changed here (the rest stay as its part file has them)
    const props: Record<string, unknown> = existing ? Object.fromEntries(Object.entries(vals).filter(([k]) => dirty.has(k))) : { ...mk.start, ...vals }
    if (mk.keys.includes('points') && (!existing || dirty.has('points'))) {
      const pts = text.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => l.split(/[,\s]+/).filter(Boolean).map(Number))
      if (pts.length < 2 || pts.some((p) => p.length < 2 || p.length > 3 || p.some((x) => !Number.isFinite(x)))) {
        await messageBox('critical', 'Points', 'Give two or more points, one per line, as x, y or x, y, z.'); return
      }
      props.points = pts.map((p) => [p[0], p[1], p[2] ?? 0])
    }
    if (existing ? dirty.has('placement') : pos.some((x) => x !== 0)) props.placement = [pos, pl[1]]
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props }], { name: `Edit ${existing.name}` }); return }
    if (mk.sel) props.base = sel[0]
    await addObject(part, { name: uniqueName(getState().features[part], mk.base), type: mk.type, ...props } as Feature, cmdOf(c).menu ?? c)
  }
  return (
    <div className="tasks pt-task" data-task={`draft-${c}`}>
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title={cmdOf(c).menu ?? c} icon={iconOf(c) ?? 'df-DraftWorkbench'}>
        {mk.sel && <Field label="Base">{existing ? String(existing.base ?? '') : sel[0] ?? ''}</Field>}
        {mk.keys.map(field)}
        {mk.type !== 'Draft::Point' && <Legend title="Placement">{(['X', 'Y', 'Z'] as const).map((a, i) =>
          <Q key={a} label={a} name={`pos${a}`} value={pos[i] ?? 0} onChange={(x) => { const w = [...pos]; w[i] = x; setPos(w); setDirty(new Set([...dirty, 'placement'])) }} />)}</Legend>}
      </TaskBox>
    </div>
  )
}

/** Move, Rotate, Scale, Offset: the values the command's Draft.<op>(...) line takes, then `cad feature draft`. */
function ModifyTask({ part, c }: { part: string; c: string }) {
  const doc = useStore((s) => s.features[part])
  const mod = MODS[c]
  const [sel] = useState(() => selectedObjects(part))
  const circle = mod.op === 'offset' && objectOf(doc, sel[0] ?? '')?.type === 'Draft::Circle'
  const [vec, setVec] = useState<number[]>(mod.op === 'scale' ? [1, 1, 1] : [0, 0, 0])
  const [center, setCenter] = useState<number[]>([0, 0, 0])
  const [axis, setAxis] = useState<number[]>([0, 0, 1])
  const [angle, setAngle] = useState(0)
  const [radius, setRadius] = useState(() => Number(objectOf(doc, sel[0] ?? '')?.radius ?? 1))
  const [copy, setCopy] = useState(false)
  if (!doc) return null
  const xyz = (title: string, name: string, v: number[], set: (v: number[]) => void, dims = LENGTH) =>
    <Legend title={title}>{(['X', 'Y', 'Z'] as const).map((a, i) =>
      <Q key={a} label={a} name={`${name}${a}`} value={v[i]} dims={dims} onChange={(x) => { const w = [...v]; w[i] = x; set(w) }} />)}</Legend>
  const ok = async () => {
    const s = getState()
    if (!s.slug) return
    const f = (v: number[]) => v.map((x) => String(x)).join(',')
    const flags = mod.op === 'move' ? [`--vector=${f(vec)}`]
      : mod.op === 'rotate' ? [`--angle=${angle}`, `--center=${f(center)}`, `--axis=${f(axis)}`]
      : mod.op === 'scale' ? [`--vector=${f(vec)}`, `--center=${f(center)}`]
      : circle ? [`--radius=${radius}`] : [`--vector=${f(vec)}`]
    const argv = ['feature', 'draft', s.slug, part, mod.op, ...sel, ...flags, ...(copy ? ['--copy'] : [])]
    closeTask()
    if (s.scriptToPyConsole) consoleLog('in', `cad ${argv.join(' ')}`)
    try {
      const r = await api.cad(s.slug, argv)
      if (r.exit > 2) { report('err', `${cmdOf(c).menu}: ${resultText(r)}`); return }
      report('msg', `${part}: ${cmdOf(c).menu}`)
      loadHistory()
      await loadFeatures()
    } catch (e) { report('err', `${cmdOf(c).menu}: ${e instanceof Error ? e.message : String(e)}`) }
  }
  return (
    <div className="tasks pt-task" data-task={`draft-${c}`}>
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title={cmdOf(c).menu ?? c} icon={iconOf(c) ?? 'df-DraftWorkbench'}>
        <Field label="Objects">{sel.join(', ')}</Field>
        {mod.op === 'move' && xyz('Displacement', 'vector', vec, setVec)}
        {mod.op === 'rotate' && <><Q label="Angle" name="angle" value={angle} dims={ANGLE} onChange={setAngle} />
          {xyz('Center', 'center', center, setCenter)}{xyz('Axis', 'axis', axis, setAxis, NUMBER)}</>}
        {mod.op === 'scale' && <>{xyz('Scale factors', 'vector', vec, setVec, NUMBER)}{xyz('Center', 'center', center, setCenter)}</>}
        {mod.op === 'offset' && (circle ? <Q label="Radius" name="radius" value={radius} onChange={setRadius} />
          : xyz('Offset of the first vertex', 'vector', vec, setVec))}
        <Check label="Copy" name="copy" checked={copy} onChange={setCopy} />
      </TaskBox>
    </div>
  )
}
