// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/TechDraw/Gui/CommandAnnotate.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/CommandHelpers.cpp: 2022 Wanderer Fan
//   src/Mod/TechDraw/Gui/CommandExtensionPack.cpp: 2022 Wanderer Fan
//   src/Mod/TechDraw/Gui/TaskCosVertex.cpp, TaskCosmeticLine.cpp, TaskCosmeticCircle.cpp, TaskCenterLine.cpp, TaskLineDecor.cpp: 2019 Wanderer Fan
//   No copyright line in the file: the .ui files of those task panels (uiforms-techdraw.ts)
// TechDraw's annotation tools: the commands of the Add Vertices, Add Lines and Centerlines menus and the cosmetic eraser, and the
// task panels of TaskCosVertex, TaskCosmeticLine, TaskCosmeticCircle, TaskCenterLine and TaskLineDecor (with its Restore Invisible
// Lines box). Each is one `cad techdraw apply` of the ops of cad_agent/techdraw_annot.py: one undo step named as FreeCAD's
// transaction. A centreline is made when its panel opens (TaskCenterLine's createCenterLine) and changed live; OK folds the changes
// into that step (the server's `amend`), Cancel takes the step back. Line Decoration and the eraser make no transaction in FreeCAD:
// here each is a step of its own (ui/PARITY.md, "TechDraw annotations").
import { useEffect, useState, type ReactNode } from 'react'
import { closeTask, doUndo, openTask } from './actions'
import { QtForm, type Bindings } from './qtform'
import { TECHDRAW_FORMS } from './uiforms-techdraw'
import { TaskBox } from './panels'
import { report } from './store'
import { messageBox } from './msgbox'
import type { IconName } from './icons'
import { applyTd, clearPreview, objOf, setTd, splitRef, tdState, isView, activePage, type TdEdge, type TdObj } from './techdraw'

const warn = (title: string, text: string) => void messageBox('warning', title, text)

// ── the selection (Gui::Selection: a view's object and the sub-elements picked on it) ───────────────────────────────
type Sel = { page: string; view: string; subs: string[] }
/** The first selected view with the sub-elements selected on it (CommandHelpers::getSelectedSubElements, the commands' own loops). */
function selection(): Sel | null {
  const st = tdState()
  const refs = st.sel.map(splitRef)
  const first = refs.find(([p, v]) => isView(objOf(p, v)))
  if (!first) return null
  const [page, view] = first
  return { page, view, subs: refs.filter(([p, v, s]) => p === page && v === view && !!s).map(([, , s]) => s!) }
}
const kindOf = (sub: string) => sub.replace(/[0-9]+$/, '')
const geo = (page: string, view: string) => tdState().docs[page]?.result?.views[view]
const edgeOf = (page: string, view: string, sub: string): (TdEdge & { cls?: string; tag?: string; format?: Fmt }) | undefined =>
  geo(page, view)?.edges?.[Number(sub.slice(4))] as never
const needPage = () => {
  const p = activePage()
  if (!p) warn('No page found', 'No Drawing Pages in document.')
  return p
}
type Fmt = { style: number; weight: number; color: number[]; visible: boolean; line_number: number }
const DEFAULT_FMT: Fmt = { style: 2, weight: 0.5, color: [0, 0, 0, 1], visible: true, line_number: 2 }
const fmtOf = (o: { format?: Partial<Fmt> } | undefined): Fmt => ({ ...DEFAULT_FMT, ...(o?.format ?? {}) })
/** loadLineStyleChoices: the line standard's lines (Preferences > Standards > Line Standard: ASME Y14.2-2008). */
export const LINE_NAMES = ['Visible', 'Hidden', 'Section', 'Center', 'Symmetry', 'Dimension', 'Extension', 'Leader', 'Cutting-plane', 'Viewing-plane', 'Other plane',
  'Break 1', 'Break 2', 'Phantom', 'Stitch 1', 'Stitch 2', 'Chain']
const hex = (c: number[]) => '#' + c.slice(0, 3).map((x) => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, '0')).join('')
const unhex = (s: string) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16) / 255).concat([1])

/** A page point (mm, y up) as the panels show it: about the view's centre, unrotated and unscaled (CosmeticVertex::makeCanonicalPoint). */
export function userFromPage(page: string, view: string, p: [number, number]): [number, number] {
  const g = geo(page, view)
  if (!g) return [0, 0]
  const dx = p[0] - g.x, dy = p[1] - g.y, a = ((g.rotation ?? 0) * Math.PI) / 180
  return [(dx * Math.cos(a) + dy * Math.sin(a)) / g.scale, (-dx * Math.sin(a) + dy * Math.cos(a)) / g.scale]
}
/** A vertex of the view's geometry as the panels show it (paper coordinates, y down, to the same). */
function vertexUser(page: string, view: string, sub: string): [number, number] | null {
  const g = geo(page, view)
  const v = g?.vertices?.[Number(sub.slice(6))] as { x: number; y: number } | undefined
  if (!g || !v) return null
  const a = ((g.rotation ?? 0) * Math.PI) / 180, px = v.x, py = -v.y
  return [(px * Math.cos(a) + py * Math.sin(a)) / g.scale, (-px * Math.sin(a) + py * Math.cos(a)) / g.scale]
}

// ── what a task is given to open with (a panel gets its page and one string) ───────────────────────────────────────
const pending: Record<string, Record<string, unknown>> = {}
function openAnnotTask(kind: string, page: string, view: string, mode: string, data: Record<string, unknown> = {}) {
  const key = `${kind}:${view}:${mode}`
  pending[key] = data
  openTask('techdraw', page, key)
}

// ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────────────
function clearSelection() { setTd({ sel: [] }) }

/** TechDraw_CosmeticVertex (execCosmeticVertex): TaskDlgCosVertex for the selected view. */
function cosmeticVertex() {
  const page = needPage()
  if (!page) return
  const s = selection()
  if (!s) { warn('Wrong selection', 'No DrawViewPart objects in this selection'); return }
  openAnnotTask('cosvertex', s.page, s.view, 'create')
  clearSelection()
}
/** getSelectedSubElements, for the commands that need the edges (or vertices) of one view. */
function subsOf(type: string): Sel | null {
  const s = selection()
  if (!s) { warn('Wrong selection', 'No part view in selection'); return null }
  const subs = s.subs.filter((x) => kindOf(x) === type)
  if (!subs.length) { warn('Wrong selection', `No ${type} in selection`); return null }
  return { ...s, subs }
}
/** TechDraw_Midpoints / TechDraw_Quadrants (execMidpoints, execQuadrants). */
async function edgePoints(op: 'midpoints' | 'quadrants') {
  if (!needPage()) return
  const s = subsOf('Edge')
  if (!s) return
  await applyTd(s.page, [{ op, view: s.view, edges: s.subs }], op === 'midpoints' ? 'Add midpoint vertices' : 'Add Quadrant vertices')
  clearSelection()
}
const cosmeticTag = (s: Sel, sub: string) => { const e = edgeOf(s.page, s.view, sub); return e?.cls === 'cosmetic' ? e.tag : undefined }
const cosmeticDef = (s: Sel, tag: string) => (objOf(s.page, s.view)?.cosmetic_edges as { tag: string; geom: string }[] | undefined)?.find((c) => c.tag === tag)

/** TechDraw_2PointCosmeticLine (execLine2Points). */
function cosmeticLine() {
  if (!needPage()) return
  const s = selection()
  if (!s) { warn('Wrong selection', 'You must select a base view for the line'); return }
  if (!s.subs.length) { warn('Wrong selection', 'Not enough points in the selection'); return }
  const edges = s.subs.filter((x) => kindOf(x) === 'Edge'), verts = s.subs.filter((x) => kindOf(x) === 'Vertex')
  if (edges.length === 1) {
    const tag = cosmeticTag(s, edges[0])
    const c = tag ? cosmeticDef(s, tag) as unknown as { start: number[]; end: number[]; geom: string } : undefined
    if (!tag || !c || c.geom !== 'line') { warn('Wrong selection', 'Selection is not a cosmetic line'); return }
    openAnnotTask('cosline', s.page, s.view, 'edit', { tag, p0: c.start, p1: c.end })
    clearSelection()
    return
  }
  const pts = verts.map((v) => vertexUser(s.page, s.view, v)).filter((p): p is [number, number] => !!p)
  if (pts.length !== 2) { warn('Wrong selection', 'You must select 2 vertices'); return }
  openAnnotTask('cosline', s.page, s.view, 'create', { p0: [...pts[0], 0], p1: [...pts[1], 0] })
  clearSelection()
}
/** TechDraw_CosmeticCircle (execCosmeticCircleCenter). */
function cosmeticCircle() {
  if (!needPage()) return
  const s = selection()
  if (!s) { warn('Wrong Selection', 'You must select a base View for the circle.'); return }
  const edges = s.subs.filter((x) => kindOf(x) === 'Edge'), verts = s.subs.filter((x) => kindOf(x) === 'Vertex')
  if (edges.length === 1) {
    const tag = cosmeticTag(s, edges[0])
    const c = tag ? cosmeticDef(s, tag) as unknown as { center: number[]; radius: number; geom: string; start_angle?: number; end_angle?: number } : undefined
    if (!tag || !c || (c.geom !== 'circle' && c.geom !== 'arc')) { warn('Wrong Selection', 'Selection is not a Cosmetic Circle or a Cosmetic Arc of Circle.'); return }
    openAnnotTask('coscircle', s.page, s.view, 'edit', { tag, center: c.center, radius: c.radius, arc: c.geom === 'arc', start: c.start_angle ?? 0, end: c.end_angle ?? 360 })
    clearSelection()
    return
  }
  const pts = verts.map((v) => vertexUser(s.page, s.view, v)).filter((p): p is [number, number] => !!p)
  if (!pts.length) { warn('Wrong Selection', 'Select a center for the circle.'); return }
  // TaskCosmeticCircle::setUiPrimary: the radius is the distance of the first two points (one point leaves it undefined: 0 here)
  const radius = pts.length > 1 ? Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) : 0
  openAnnotTask('coscircle', s.page, s.view, 'create', { center: [...pts[0], 0], radius, arc: false, start: 0, end: 360 })
  clearSelection()
}

/** The three centreline commands (execCenterLine, exec2LineCenterLine, exec2PointCenterLine): TaskDlgCenterLine, which makes the line. */
async function centerLine(type: 'Face' | 'Edge' | 'Vertex') {
  if (!needPage()) return
  const s = selection()
  if (!s) { warn('Wrong selection', type === 'Edge' ? 'Selection not understood' : 'You must select a base view for the line'); return }
  const subs = (t: string) => s.subs.filter((x) => kindOf(x) === t)
  const existing = (sub: string) => { const e = edgeOf(s.page, s.view, sub); return e?.cls === 'centerline' ? e.tag : undefined }
  if (type === 'Face') {
    const faces = subs('Face'), edges = subs('Edge')
    if (!faces.length && !edges.length) { warn('Wrong selection', 'You must select faces or an existing centerline'); return }
    if (faces.length) { await makeCenterLine(s, 'Face', faces); return }
    const tag = existing(edges[0])
    if (!tag) { warn('Wrong Selection', 'Selection is not a centerline'); return }
    openAnnotTask('centerline', s.page, s.view, 'edit', { tag })
    clearSelection()
    return
  }
  if (type === 'Edge') {
    const edges = subs('Edge')
    if (!edges.length) return
    if (edges.length === 2) { await makeCenterLine(s, 'Edge', edges); return }
    if (edges.length === 1) {
      const tag = existing(edges[0])
      if (!tag) { warn('Wrong selection', 'Selection is not a Centerline'); return }
      openAnnotTask('centerline', s.page, s.view, 'edit', { tag })
      clearSelection()
      return
    }
    warn('Wrong selection', 'Selection not understood')
    return
  }
  const verts = subs('Vertex'), edges = subs('Edge')
  if (!verts.length && !edges.length) { warn('Wrong selection', 'You must select 2 vertices or an existing centerline'); return }
  if (verts.length === 2) { await makeCenterLine(s, 'Vertex', verts); return }
  if (edges.length === 1) {
    const tag = existing(edges[0])
    if (!tag) { warn('Wrong selection', 'Selection is not a centerline'); return }
    openAnnotTask('centerline', s.page, s.view, 'edit', { tag })
    clearSelection()
    return
  }
  warn('Wrong selection', 'Select 2 vertices or 1 centerline')
}
/** TaskCenterLine's constructor: the centre line is made now ("Create Centerline") and the panel edits it. */
async function makeCenterLine(s: Sel, type: string, subs: string[]) {
  const before = new Set((objOf(s.page, s.view)?.center_lines as { tag: string }[] | undefined)?.map((c) => c.tag))
  const d = await applyTd(s.page, [{ op: 'centerline', view: s.view, subs, mode: 'Vertical' }], 'Create Centerline')
  const made = (d?.objects.find((o) => o.name === s.view)?.center_lines as { tag: string }[] | undefined)?.find((c) => !before.has(c.tag))
  if (!made) return
  openAnnotTask('centerline', s.page, s.view, 'create', { tag: made.tag, type, subs })
  clearSelection()
}

/** TechDraw_CosmeticEraser. */
async function eraser() {
  if (!needPage()) return
  const st = tdState()
  const refs = st.sel.map(splitRef).filter(([, , sub]) => !!sub)
  if (!st.sel.length) { warn('Wrong selection', 'Nothing selected'); return }
  if (!refs.length) { warn('Wrong selection', 'At least 1 object in selection is not a part view'); return }
  const [page, view] = refs[0]
  const subs = refs.filter(([p, v]) => p === page && v === view).map(([, , s]) => s!)
  if (subs.some((x) => kindOf(x) !== 'Edge' && kindOf(x) !== 'Vertex')) { warn('Wrong selection', 'Unknown object type in selection'); return }
  const cosmetic = subs.filter((x) => kindOf(x) === 'Vertex'
    ? !!(geo(page, view)?.vertices?.[Number(x.slice(6))] as { tag?: string } | undefined)?.tag
    : ['cosmetic', 'centerline'].includes(String(edgeOf(page, view, x)?.cls)))
  if (!cosmetic.length) return
  await applyTd(page, [{ op: 'erase', view, subs: cosmetic }], 'Remove Cosmetic Object')
  clearSelection()
}
/** TechDraw_DecorateLine: TaskDlgLineDecor for the selected view's edges. */
function decorateLine() {
  if (!needPage()) return
  const st = tdState()
  if (!st.sel.length) { warn('Wrong selection', 'You must select a view and/or lines'); return }
  const refs = st.sel.map(splitRef).filter(([p, v, s]) => !!s && isView(objOf(p, v)))
  if (!refs.length) { warn('Wrong selection', 'No view in selection'); return }
  const [page, view] = refs[0]
  const edges = refs.filter(([p, v, s]) => p === page && v === view && kindOf(s!) === 'Edge').map(([, , s]) => s!)
  openAnnotTask('linedecor', page, view, 'edit', { edges })
  clearSelection()
}

/** The commands of this file by FreeCAD's name: what they run, and whether they are active (needPage and needView). */
export function annotActions(on: boolean): Record<string, [() => void, boolean]> {
  return {
    TechDraw_CosmeticVertex: [cosmeticVertex, on],
    TechDraw_Midpoints: [() => void edgePoints('midpoints'), on],
    TechDraw_Quadrants: [() => void edgePoints('quadrants'), on],
    TechDraw_2PointCosmeticLine: [cosmeticLine, on],
    TechDraw_CosmeticCircle: [cosmeticCircle, on],
    TechDraw_FaceCenterLine: [() => void centerLine('Face'), on],
    TechDraw_2LineCenterLine: [() => void centerLine('Edge'), on],
    TechDraw_2PointCenterLine: [() => void centerLine('Vertex'), on],
    TechDraw_CosmeticEraser: [() => void eraser(), on],
    TechDraw_DecorateLine: [decorateLine, on],
  }
}

// ── the task panels ─────────────────────────────────────────────────────────────────────────────────────────────────
const icon = (file: string) => file as IconName

function Buttons({ ok, cancel, okOff, cancelOff }: { ok(): void; cancel(): void; okOff?: boolean; cancelOff?: boolean }) {
  return (
    <div className="tbuttons">
      <button className="qbtn default" disabled={okOff} onClick={ok}>OK</button>
      <button className="qbtn" disabled={cancelOff} onClick={cancel}>Cancel</button>
    </div>)
}

export function AnnotTask({ page, other }: { page: string; other: string }) {
  const [kind, view, mode] = other.split(':')
  const data = pending[other] ?? {}
  useEffect(() => () => clearPreview(page), [page])
  if (kind === 'cosvertex') return <CosVertexTask key={other} page={page} view={view} />
  if (kind === 'cosline') return <CosLineTask key={other} page={page} view={view} edit={mode === 'edit'} data={data} />
  if (kind === 'coscircle') return <CosCircleTask key={other} page={page} view={view} edit={mode === 'edit'} data={data} />
  if (kind === 'centerline') return <CenterLineTask key={other} page={page} view={view} create={mode === 'create'} data={data} />
  if (kind === 'linedecor') return <LineDecorTask key={other} page={page} view={view} data={data} />
  return null
}

const fixed = (v: number) => (Number.isFinite(v) ? v : 0)

/** TaskCosVertex: "Pick Point" waits for a click on the page; X and Y are the vertex's place about the view's centre. */
function CosVertexTask({ page, view }: { page: string; view: string }) {
  const [pt, setPt] = useState<[number, number]>([0, 0])
  const [picking, setPicking] = useState(false)
  useEffect(() => () => { if (tdState().mode?.kind === 'pick') setTd({ mode: null }) }, [])
  const pick = () => {
    if (picking) { setPicking(false); setTd({ mode: null }); return }
    setPicking(true)
    setTd({ mode: { kind: 'pick', page, view, onPick: (p: [number, number]) => { setPt(userFromPage(page, view, p)); setPicking(false); setTd({ mode: null }) } } })
    report('msg', 'Left click to set a point')
  }
  const bind: Bindings = {
    leBaseView: { value: view },
    pbTracker: { text: picking ? 'Escape Picking' : 'Pick Point', click: pick },
    dsbX: { value: pt[0], suffix: ' mm', dec: 2, min: -1e9, max: 1e9, set: (v: number) => setPt([v, pt[1]]) },
    dsbY: { value: pt[1], suffix: ' mm', dec: 2, min: -1e9, max: 1e9, set: (v: number) => setPt([pt[0], v]) },
    groupBox: {},
  }
  const ok = async () => {
    await applyTd(page, [{ op: 'cosmetic_vertex', view, point: [fixed(pt[0]), fixed(pt[1])] }], 'Add Cosmetic Vertex')
    closeTask()
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { setTd({ mode: null }); closeTask() }} okOff={picking} cancelOff={picking} />
      <TaskBox title="New Cosmetic Vertex" icon={icon('td-TechDraw_CosmeticVertex')}><QtForm form={TECHDRAW_FORMS.cosvertex} bind={bind} /></TaskBox>
    </div>)
}

/** TaskCosmeticLine: two points (2D; a 3D point is picked from the 3D view, not ported). */
function CosLineTask({ page, view, edit, data }: { page: string; view: string; edit: boolean; data: Record<string, unknown> }) {
  const [p0, setP0] = useState<number[]>((data.p0 as number[]) ?? [0, 0, 0])
  const [p1, setP1] = useState<number[]>((data.p1 as number[]) ?? [0, 0, 0])
  // setUiPrimary gives x and y a unit and z (of the first point) none; setUiEdit none at all
  const sfx = (z = false) => (edit || z ? '' : ' mm')
  const q = (a: number[], set: (v: number[]) => void, i: number, z = false) =>
    ({ value: a[i] ?? 0, suffix: sfx(z), dec: 2, min: -1e9, max: 1e9, set: (v: number) => set(a.map((x, k) => (k === i ? v : x)).concat(a.length < 3 ? [0] : [])) })
  const bind: Bindings = {
    le_View: { value: '' },
    rb2d1: { value: true, off: true, why: 'the point is the 2D one' }, rb3d1: { value: false, off: true, why: 'a 3D point is picked in the 3D view: not ported' },
    rb2d2: { value: true, off: true, why: 'the point is the 2D one' }, rb3d2: { value: false, off: true, why: 'a 3D point is picked in the 3D view: not ported' },
    qsbx1: q(p0, setP0, 0), qsby1: q(p0, setP0, 1), qsbz1: q(p0, setP0, 2, !edit),
    qsbx2: q(p1, setP1, 0), qsby2: q(p1, setP1, 1), qsbz2: q(p1, setP1, 2),
  }
  const ok = async () => {
    const op = edit ? { op: 'cosmetic_line_edit', view, tag: data.tag, p0, p1 } : { op: 'cosmetic_line', view, p0, p1 }
    await applyTd(page, [op], edit ? 'Update Cosmetic Line' : 'Create Cosmetic Line')
    closeTask()
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={closeTask} />
      <TaskBox title={edit ? 'Edit Cosmetic Line' : 'Create Cosmetic Line'} icon={icon('td-TechDraw_Line2Points')}><QtForm form={TECHDRAW_FORMS.cosline} bind={bind} /></TaskBox>
    </div>)
}

/** TaskCosmeticCircle: the centre, the radius, and an arc's angles. */
function CosCircleTask({ page, view, edit, data }: { page: string; view: string; edit: boolean; data: Record<string, unknown> }) {
  const [c, setC] = useState<number[]>((data.center as number[]) ?? [0, 0, 0])
  const [r, setR] = useState(Number(data.radius ?? 0))
  const [arc, setArc] = useState(!!data.arc)
  const [a0, setA0] = useState(Number(data.start ?? 0)), [a1, setA1] = useState(Number(data.end ?? 360))
  const [cw, setCw] = useState(false)
  const sfx = edit ? '' : ' mm'
  const q = (i: number, z = false) => ({ value: c[i] ?? 0, suffix: z ? '' : sfx, dec: 2, min: -1e9, max: 1e9, set: (v: number) => setC(c.map((x, k) => (k === i ? v : x))) })
  const bind: Bindings = {
    le_View: { value: '' }, label_8: {},
    rb2d1: { value: true, off: true, why: 'the point is the 2D one' }, rb3d1: { value: false, off: true, why: 'a 3D point is picked in the 3D view: not ported' },
    qsbCenterX: q(0), qsbCenterY: q(1), qsbCenterZ: q(2, true),
    qsbRadius: { value: r, suffix: '', dec: 2, min: 0, max: 1e9, set: (v: number) => { setR(v); if (v <= 0) void messageBox('critical', 'Parameter Error', 'Radius must be non-zero positive number') } },
    rbArc: { value: arc, set: (v: boolean) => setArc(v) },
    qsbStartAngle: { value: a0, suffix: edit && !arc ? '' : '', dec: 2, min: -1e9, max: 1e9, off: !arc, set: (v: number) => setA0(v) },
    qsbEndAngle: { value: a1, dec: 2, min: -1e9, max: 1e9, off: !arc, set: (v: number) => setA1(v) },
    cbClockwise: { value: cw, off: !arc, set: (v: boolean) => setCw(v) },
  }
  const ok = async () => {
    if (!(r > 0)) { report('err', `TaskCosmeticCircle - cannot create a circle with radius: ${r.toFixed(3)}`); return }
    const props = { center: c, radius: r, arc, ...(arc ? { start_angle: a0, end_angle: a1 } : {}) }
    const op = edit ? { op: 'cosmetic_circle_edit', view, tag: data.tag, ...props } : { op: 'cosmetic_circle', view, ...props }
    await applyTd(page, [op], edit ? 'Update Cosmetic Circle' : 'Create Cosmetic Circle')
    closeTask()
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={closeTask} />
      <TaskBox title={edit ? 'Edit Cosmetic Circle' : 'Create Cosmetic Circle'} icon={icon('td-TechDraw_CosmeticCircle')}><QtForm form={TECHDRAW_FORMS.coscircle} bind={bind} /></TaskBox>
    </div>)
}

type CL = { tag: string; type: string; mode: string; faces: string[]; edges: string[]; vertexes: string[]; h_shift: number; v_shift: number; rotate: number; extend: number; format?: Partial<Fmt> }
const centerLine_ = (page: string, view: string, tag: string) => (objOf(page, view)?.center_lines as CL[] | undefined)?.find((c) => c.tag === tag)

/** TaskCenterLine: the line made (Create Centerline) and then changed live: orientation, shifts, rotation, extension, style, colour, weight. */
function CenterLineTask({ page, view, create, data }: { page: string; view: string; create: boolean; data: Record<string, unknown> }) {
  const tag = String(data.tag)
  const cl = centerLine_(page, view, tag)
  const [v, setV] = useState<CL | undefined>(cl && { ...cl })
  if (!cl || !v) return <div className="tasks"><Buttons ok={closeTask} cancel={closeTask} /></div>
  const f = fmtOf(v)
  const type = cl.type
  const subs = type === 'Face' ? cl.faces : type === 'Edge' ? cl.edges : cl.vertexes
  const changed = (): Record<string, unknown> => {
    const o: Record<string, unknown> = {}
    for (const k of ['mode', 'h_shift', 'v_shift', 'rotate', 'extend'] as const) if (v[k] !== cl[k]) o[k] = v[k]
    const fo = fmtOf(cl)
    const fm: Record<string, unknown> = {}
    for (const k of ['weight', 'line_number'] as const) if (f[k] !== fo[k]) fm[k] = f[k]
    if (hex(f.color) !== hex(fo.color)) fm.color = f.color
    if (Object.keys(fm).length) o.format = fm
    return o
  }
  // the panel's changes, previewed (a dry run); a change of orientation first has to pass checkPathologicalEdges, so the server decides
  useEffect(() => {
    const ch = changed()
    if (Object.keys(ch).length) void applyTd(page, [{ op: 'centerline_edit', view, tag, ...ch }], undefined, true)
    else clearPreview(page)
  }, [JSON.stringify(v)]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof CL, x: unknown) => setV({ ...v, [k]: x } as CL)
  const setF = (k: keyof Fmt, x: unknown) => setV({ ...v, format: { ...v.format, [k]: x } })
  const mode = (m: string) => ({ value: v.mode === m, set: () => set('mode', m) })
  const bind: Bindings = {
    leBaseView: { value: view },
    lstSubList: { node: <div className="qf-list">{subs.map((s) => <div key={s}>{s}</div>)}</div> },
    rbVertical: mode('Vertical'), rbHorizontal: mode('Horizontal'), rbAligned: { ...mode('Aligned'), off: type === 'Face' },
    qsbHorizShift: { value: v.h_shift, suffix: ' mm', dec: 2, min: -1e9, max: 1e9, set: (x: number) => set('h_shift', x) },
    qsbVertShift: { value: v.v_shift, suffix: ' mm', dec: 2, min: -1e9, max: 1e9, set: (x: number) => set('v_shift', x) },
    qsbRotate: { value: v.rotate, suffix: '°', dec: 2, min: -360, max: 360, set: (x: number) => set('rotate', x) },
    qsbExtend: { value: v.extend, suffix: ' mm', dec: 2, min: -1e9, max: 1e9, set: (x: number) => set('extend', x) },
    cboxStyle: { value: f.line_number - 1, opts: LINE_NAMES.map((n, i) => [i, n] as const), set: (i: number) => setF('line_number', i + 1) },
    cpLineColor: { value: hex(f.color), set: (c: string) => setF('color', unhex(c)) },
    dsbWeight: { value: f.weight, dec: 2, min: 0, max: 1e3, set: (x: number) => setF('weight', x) },
    gbOrientation: {}, groupBox_2: {}, groupBox: {},
  }
  const ok = async () => {
    const ch = changed()
    if (Object.keys(ch).length) await applyTd(page, [{ op: 'centerline_edit', view, tag, ...ch }], create ? 'Create Centerline' : 'Edit Centerline', false, create)
    clearPreview(page)
    closeTask()
  }
  // Cancel of a new line undoes its creation (doc->undo(1)); of an existing one nothing was changed
  const cancel = () => { clearPreview(page); closeTask(); if (create) void doUndo() }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={cancel} />
      <TaskBox title={create ? 'Centerline' : 'Edit Centerline'} icon={icon('td-TechDraw_FaceCenterLine')}><QtForm form={TECHDRAW_FORMS.centerline} bind={bind} /></TaskBox>
    </div>)
}

/** TaskLineDecor and TaskRestoreLines: the style, colour, weight and visibility of the selected lines, live; and the
 *  buttons that make invisible lines visible again. */
function LineDecorTask({ page, view, data }: { page: string; view: string; data: Record<string, unknown> }) {
  const edges = (data.edges as string[]) ?? []
  const obj = objOf(page, view) as TdObj | undefined
  // getDefaults: the current line format, or the first selected line's when that differs from it
  const first = (() => {
    const sub = edges[0]
    if (!sub) return DEFAULT_FMT
    const e = edgeOf(page, view, sub)
    const fm = e?.format ? fmtOf(e) : (() => { const g = (obj?.geom_formats as (Fmt & { index: number })[] | undefined)?.find((x) => x.index === Number(sub.slice(4))); return g ? fmtOf({ format: g }) : DEFAULT_FMT })()
    const same = fm.weight === DEFAULT_FMT.weight && fm.visible === DEFAULT_FMT.visible && fm.line_number === DEFAULT_FMT.line_number && hex(fm.color) === hex(DEFAULT_FMT.color)
    return same ? DEFAULT_FMT : fm
  })()
  const [f, setF] = useState<Fmt>(first)
  const op = () => ({ op: 'format', view, subs: edges, style: f.style, weight: f.weight, color: f.color, visible: f.visible, line_number: f.line_number })
  const touched = JSON.stringify(f) !== JSON.stringify(first)
  useEffect(() => { if (edges.length && touched) void applyTd(page, [op()], undefined, true); else clearPreview(page) }, [JSON.stringify(f)]) // eslint-disable-line react-hooks/exhaustive-deps
  const count = (kind: 'geom_formats' | 'cosmetic_edges' | 'center_lines') =>
    ((obj?.[kind] as { visible?: boolean; format?: Partial<Fmt> }[] | undefined) ?? []).filter((x) => (kind === 'geom_formats' ? x.visible === false : x.format?.visible === false)).length
  const nGeom = count('geom_formats'), nCos = count('cosmetic_edges'), nCenter = count('center_lines')
  const restore = (kinds: string[]) => void applyTd(page, [{ op: 'restore_lines', view, kinds }], 'Restore Invisible Lines')
  const bind: Bindings = {
    le_View: { value: view }, le_Lines: { value: `${edges.length} line(s)` },
    cb_Style: { value: f.line_number - 1, opts: LINE_NAMES.map((n, i) => [i, n] as const), set: (i: number) => setF({ ...f, line_number: i + 1 }) },
    cc_Color: { value: hex(f.color), set: (c: string) => setF({ ...f, color: unhex(c) }) },
    dsb_Weight: { value: f.weight, dec: 2, step: 0.1, min: 0, max: 1e3, set: (x: number) => setF({ ...f, weight: x }) },
    cb_Visible: { value: f.visible, set: (x: boolean) => setF({ ...f, visible: x }) },
    groupBox: {},
  }
  const rbind: Bindings = {
    pb_All: { click: () => restore(['all']) }, pb_Geometry: { click: () => restore(['geometry']) },
    pb_Cosmetic: { click: () => restore(['cosmetic']) }, pb_Center: { click: () => restore(['center']) },
    l_All: { text: String(nGeom + nCos + nCenter) }, l_Geometry: { text: String(nGeom) }, l_Cosmetic: { text: String(nCos) }, l_Center: { text: String(nCenter) },
  }
  const ok = async () => {
    if (edges.length) await applyTd(page, [op()], 'Edit Line Appearance')
    clearPreview(page)
    closeTask()
  }
  const decor: ReactNode = <QtForm form={TECHDRAW_FORMS.linedecor} bind={bind} />
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { clearPreview(page); closeTask() }} />
      {edges.length > 0 && <TaskBox title="Line Decoration" icon={icon('td-TechDraw_DecorateLine')}>{decor}</TaskBox>}
      <TaskBox title="Restore Invisible Lines" icon={icon('td-TechDraw_DecorateLine')}><QtForm form={TECHDRAW_FORMS.restorelines} bind={rbind} /></TaskBox>
    </div>)
}

