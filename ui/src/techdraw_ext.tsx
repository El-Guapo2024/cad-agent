// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/TechDraw/Gui/CommandExtensionPack.cpp: 2021 edi
//   src/Mod/TechDraw/Gui/CommandExtensionDims.cpp: 2021 edi
//   src/Mod/TechDraw/Gui/CommandAnnotate.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/TaskSelectLineAttributes.cpp: 2021 edi
//   src/Mod/TechDraw/TechDrawTools/CommandPositionSectionView.py: 2021 edi
//   No copyright line in the file: src/Mod/TechDraw/Gui/TaskSelectLineAttributes.ui
// TechDraw's extension commands (the Attributes/Modifications, Centerlines/Threading and Format/Organize Dimensions menus),
// TechDraw_ShowAll and the Select Line Attributes panel. Each is one `cad techdraw apply` of the ops of
// cad_agent/techdraw_ext.py: one undo step named as FreeCAD's transaction. The session's line attributes (the panel's
// style, width, colour, cascade spacing and delta distance) are what FreeCAD keeps in LineFormat::getCurrentLineFormat and
// activeDimAttributes: they are sent with each op and last until the page is reloaded. The messages are the command's own
// QMessageBox warnings, with their titles.
import { useEffect, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { closeTask, openTask } from './actions'
import { QtForm, type Bindings } from './qtform'
import { TECHDRAW_FORMS } from './uiforms-techdraw'
import { TaskBox } from './panels'
import { messageBox } from './msgbox'
import type { IconName } from './icons'
import { LINE_NAMES } from './techdraw_annot'
import { applyTd, objOf, setTd, splitRef, tdState, isView, activePage, type TdEdge } from './techdraw'

const warn = (title: string, text: string) => void messageBox('warning', title, text)

// ── the session's attributes ────────────────────────────────────────────────────────────────────────────────────────
type Attrs = { line_number: number; weight: number; color: number[]; cascade: number; stretch: number }
const THIN = 0.35, GRAPHIC = 0.5, THICK = 0.7           // LineGroup::getDefaultWidth("Thin" | "Graphic" | "Thick")
const DEFAULT_ATTRS: Attrs = { line_number: 2, weight: GRAPHIC, color: [0, 0, 0, 1], cascade: 7, stretch: 2 }
let attrs: Attrs = { ...DEFAULT_ATTRS }
/** What every op carries: LineFormat::getCurrentLineFormat and activeDimAttributes (cad_agent/techdraw_ext.py reads them). */
const session = () => ({
  active: { style: attrs.line_number, line_number: attrs.line_number, weight: attrs.weight, color: attrs.color, visible: true },
  cascade_spacing: attrs.cascade, line_stretch: attrs.stretch,
})
const hex = (c: number[]) => '#' + c.slice(0, 3).map((x) => Math.round(Math.max(0, Math.min(1, x)) * 255).toString(16).padStart(2, '0')).join('')
const unhex = (s: string) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16) / 255).concat([1])

// ── the selection ───────────────────────────────────────────────────────────────────────────────────────────────────
type SelObj = { page: string; name: string; subs: string[] }
/** Gui::Selection::getSelectionEx: the selected objects in the order they were picked, each with its picked sub-elements. */
function selObjects(): SelObj[] {
  const out: SelObj[] = []
  for (const [page, name, sub] of tdState().sel.map(splitRef)) {
    let o = out.find((x) => x.page === page && x.name === name)
    if (!o) { o = { page, name, subs: [] }; out.push(o) }
    if (sub) o.subs.push(sub)
  }
  return out
}
const kindOf = (sub: string) => sub.replace(/[0-9]+$/, '')
const edgeOf = (page: string, view: string, sub: string): (TdEdge & { cls?: string }) | undefined =>
  tdState().docs[page]?.result?.views[view]?.edges?.[Number(sub.slice(4))] as never
const GEOM_NAMES: Record<string, string> = {
  GENERIC: 'Line', CIRCLE: 'Circle', ARCOFCIRCLE: 'Arc of Circle', ELLIPSE: 'Ellipse', ARCOFELLIPSE: 'Arc of Ellipse', BEZIER: 'Bezier Curve', BSPLINE: 'B-spline Curve',
}
const geomName = (page: string, view: string, sub: string) => GEOM_NAMES[edgeOf(page, view, sub)?.kind ?? ''] ?? 'Not Defined'
const clearSel = () => setTd({ sel: [] })
const needPage = () => {
  const p = activePage()
  if (!p) warn('No page found', 'No Drawing Pages in document.')
  return p
}
/** _checkSel: a selection whose first object is a part view. */
function checkSel(title: string, needSubs = false): SelObj | null {
  if (!needPage()) return null
  const sel = selObjects()
  if (!sel.length) { warn(title, 'Selection is empty'); return null }
  if (!isView(objOf(sel[0].page, sel[0].name))) { warn(title, 'No object selected'); return null }
  if (needSubs && !sel[0].subs.length) { warn(title, 'No sub-elements selected'); return null }
  return sel[0]
}
async function run(page: string, op: Record<string, unknown>, name?: string) {
  const doc = await applyTd(page, [{ ...session(), ...op }], name)
  return !!doc
}

// ── CommandExtensionPack.cpp ────────────────────────────────────────────────────────────────────────────────────────
function vertexCommand(title: string, op: string) {
  return async () => {
    const s = checkSel(title)
    if (!s) return
    await run(s.page, { op, view: s.name, vertices: s.subs.filter((x) => kindOf(x) === 'Vertex') })
    clearSel()
  }
}
/** execLineParallelPerpendicular: the first two selected sub-elements are an edge and a vertex. */
function lineCommand(parallel: boolean) {
  return async () => {
    const s = checkSel('TechDraw Cosmetic Line Parallel/Perpendicular')
    if (!s) return
    if (s.subs.length >= 2) {
      const ks = [kindOf(s.subs[0]), kindOf(s.subs[1])].sort().join()
      if (ks === 'Edge,Vertex') {
        const edge = s.subs.slice(0, 2).find((x) => kindOf(x) === 'Edge')!
        if (edgeOf(s.page, s.name, edge)?.kind !== 'GENERIC') { void messageBox('critical', 'Error', 'Bad Cast'); return }
        await run(s.page, { op: 'cosmetic_pline', view: s.name, subs: s.subs.slice(0, 2), parallel })
        clearSel()
      }
    }
  }
}
/** execExtendShortenLine: the first selected edge; a cosmetic line or centre line grows or shrinks by the delta distance. */
function extendCommand(extend: boolean) {
  return async () => {
    const s = checkSel('TechDraw Extend/Shorten Line')
    if (!s) return
    const sub = s.subs[0]
    if (sub && kindOf(sub) === 'Edge') {
      const e = edgeOf(s.page, s.name, sub)
      if (e && e.kind !== 'GENERIC') { warn('TechDraw extend/shorten line', `Can not make centerlines for ${geomName(s.page, s.name, sub)}`); return }
      if (e && (e.cls === 'cosmetic' || e.cls === 'centerline')) await run(s.page, { op: 'extend_line', view: s.name, sub, extend })
    }
  }
}
async function circleCenterLines() {
  const s = checkSel('TechDraw circle centerlines')
  if (!s) return
  const good: string[] = []
  for (const sub of s.subs.filter((x) => kindOf(x) === 'Edge')) {
    const e = edgeOf(s.page, s.name, sub)
    if (!e) continue
    if (e.kind === 'CIRCLE' || e.kind === 'ARCOFCIRCLE') good.push(sub)
    else warn('TechDraw circle centerlines', `Can not make centerlines for ${geomName(s.page, s.name, sub)}`)
  }
  if (good.length) await run(s.page, { op: 'circle_centerlines', view: s.name, edges: good })
  clearSel()
}
async function boltCircle() {
  const s = checkSel('TechDraw hole circle')
  if (!s) return
  const good: string[] = []
  for (const sub of s.subs.filter((x) => kindOf(x) === 'Edge')) {
    const e = edgeOf(s.page, s.name, sub)
    if (!e) continue
    if (e.kind === 'CIRCLE' || e.kind === 'ARCOFCIRCLE') good.push(sub)
    else warn('TechDraw hole circle', `Can not make hole circle for ${geomName(s.page, s.name, sub)}`)
  }
  if (good.length <= 2) { warn('TechDraw hole circle', 'Fewer than three circles selected'); return }
  await run(s.page, { op: 'bolt_circle', view: s.name, edges: good })
  clearSel()
}
function threadCommand(kind: 'hole_side' | 'bolt_side' | 'hole_bottom' | 'bolt_bottom') {
  const title = { hole_side: 'TechDraw Thread Hole Side', bolt_side: 'TechDraw Thread Bolt Side', hole_bottom: 'TechDraw Thread Hole Bottom', bolt_bottom: 'TechDraw Thread Bolt Bottom' }[kind]
  return async () => {
    const s = checkSel(title)
    if (!s) return
    if (kind.endsWith('side')) {
      if (s.subs.length >= 2 && kindOf(s.subs[0]) === 'Edge' && kindOf(s.subs[1]) === 'Edge') {
        if (edgeOf(s.page, s.name, s.subs[0])?.kind !== 'GENERIC' || edgeOf(s.page, s.name, s.subs[1])?.kind !== 'GENERIC') { warn('TechDraw thread hole side', 'Select 2 straight lines'); return }
        await run(s.page, { op: 'thread', view: s.name, kind, subs: s.subs.slice(0, 2) })
      }
    } else {
      const good: string[] = []
      for (const sub of s.subs) {
        if (kindOf(sub) !== 'Edge') continue
        const e = edgeOf(s.page, s.name, sub)
        if (e?.kind === 'CIRCLE') good.push(sub)
        else if (e) warn('TechDraw create thread circle', `Can not make thread circle for ${geomName(s.page, s.name, sub)}`)
      }
      if (good.length) await run(s.page, { op: 'thread', view: s.name, kind, subs: good })
    }
    clearSel()
  }
}
async function changeLineAttributes() {
  const s = checkSel('TechDraw change line attributes')
  if (!s) return
  await run(s.page, { op: 'line_attributes', view: s.name, subs: s.subs.filter((x) => kindOf(x) === 'Edge') })
  clearSel()
}
/** TechDraw_ExtensionLockUnlockView: LockPosition of each selected part view turned over. */
async function lockUnlock() {
  const sel = selObjects()
  if (!sel.length) return
  const names = sel.filter((x) => x.page === sel[0].page && isView(objOf(x.page, x.name))).map((x) => x.name)
  if (names.length) await run(sel[0].page, { op: 'lock_view', names })
}
/** TechDraw_ShowAll (Toggle Edge Visibility): the first selected view's ShowAllEdges turned over. */
async function showAllEdges() {
  if (!needPage()) return
  const sel = selObjects()
  if (!sel.length) { warn('Wrong selection', 'Nothing selected'); return }
  if (!isView(objOf(sel[0].page, sel[0].name))) { warn('Wrong selection', 'No part views in this selection'); return }
  await run(sel[0].page, { op: 'show_all_edges', view: sel[0].name }, 'Toggle Edge Visibility')
}
/** TechDrawTools/CommandPositionSectionView.py: one section view, or a section view's edge and a base view's vertex. */
async function positionSection() {
  if (!needPage()) return
  const sel = selObjects()
  if (!sel.length) return
  if (sel.length === 1) {
    const o = objOf(sel[0].page, sel[0].name)
    if (o?.kind === 'DrawViewSection') await run(sel[0].page, { op: 'position_section', section: o.name })
    return
  }
  if (sel.length === 2) {
    const edges = sel[0].subs.filter((x) => kindOf(x) === 'Edge'), verts = sel[1].subs.filter((x) => kindOf(x) === 'Vertex')
    if (!edges.length) { warn('TechDraw_Utils', 'Select at least 1 edges'); return }
    if (!verts.length) { warn('TechDraw_Utils', 'Select at least 1 vertexes'); return }
    await run(sel[0].page, { op: 'position_section', section: sel[0].name, edge: edges[0], base: sel[1].name, vertex: verts[0] })
    clearSel()
  }
}

// ── CommandExtensionDims.cpp ────────────────────────────────────────────────────────────────────────────────────────
function dimCommand(title: string, op: string, dir: string) {
  return async () => {
    const s = checkSel(title, true)
    if (!s) return
    await run(s.page, { op, view: s.name, vertices: s.subs.filter((x) => kindOf(x) === 'Vertex'), dir })
    clearSel()
  }
}
async function arcLengthDim() {
  const s = checkSel('TechDraw Create Arc Length Dimension', true)
  if (!s) return
  if (kindOf(s.subs[0]) === 'Edge') await run(s.page, { op: 'arc_length_dim', view: s.name, edge: s.subs[0] })
  clearSel()
}
const dimsOf = (type: string | null) => {
  const sel = selObjects()
  const names = sel.filter((x) => { const o = objOf(x.page, x.name); return o?.kind === 'DrawViewDimension' && (type === null || o.dim_type === type) }).map((x) => x.name)
  return { page: sel[0]?.page ?? '', names }
}
function positionCommand(title: string, dir: 'h' | 'v' | 'o', cascade: boolean) {
  const type = { h: 'DistanceX', v: 'DistanceY', o: 'Distance' }[dir]
  const what = { h: 'horizontal', v: 'vertical', o: 'oblique' }[dir]
  return async () => {
    if (!needPage()) return
    if (!selObjects().length) { warn(title, 'Selection is empty'); return }
    const { page, names } = dimsOf(type)
    if (!names.length) { warn(title, `No ${what} dimensions selected`); return }
    await run(page, { op: 'dim_position', names, dir, cascade })
  }
}
/** execInsertPrefixChar: the prefix goes in front of each selected dimension's FormatSpec; "n×" asks for the count first. */
function prefixCommand(prefix: string) {
  return async () => {
    if (!needPage()) return
    if (!selObjects().length) { warn('TechDraw Insert Prefix', 'Selection is empty'); return }
    const { page, names } = dimsOf(null)            // the selection as it was when the command was given
    let text: string | undefined
    if (prefix.startsWith('%s')) {
      const got = await askPrefix(prefix.slice(2))
      if (got === null) return
      text = got
    }
    if (names.length) await run(page, { op: 'dim_prefix', names, prefix, ...(text !== undefined ? { text } : {}) })
  }
}
async function removePrefix() {
  if (!needPage()) return
  if (!selObjects().length) { warn('TechDraw Remove Prefix', 'Selection is empty'); return }
  const { page, names } = dimsOf(null)
  if (names.length) await run(page, { op: 'dim_remove_prefix', names })
}
function decimalsCommand(delta: 1 | -1) {
  return async () => {
    if (!needPage()) return
    if (!selObjects().length) { warn('TechDraw Increase/Decrease Decimal', 'Selection is empty'); return }
    const { page, names } = dimsOf(null)
    if (names.length) await run(page, { op: 'dim_decimals', names, delta })
  }
}

// ── CommandExtensionPack.cpp: the annotations ───────────────────────────────────────────────────────────────────────
async function areaAnnotation() {
  const s = checkSel('TechDraw Calculate Selected Area')
  if (!s) return
  const faces = s.subs.filter((x) => kindOf(x) === 'Face')
  if (!faces.length) { warn('Incorrect Selection', 'No faces in selection'); return }
  await run(s.page, { op: 'area_annotation', view: s.name, faces })
}
async function arcLengthAnnotation() {
  const s = checkSel('TechDraw Calculate Selected Arc Length')
  if (!s) return
  const edges = s.subs.filter((x) => kindOf(x) === 'Edge')
  if (!edges.length) { warn('Incorrect Selection', 'No edges in selection'); return }
  await run(s.page, { op: 'arc_length_annotation', view: s.name, edges })
}

/** The commands of this file by FreeCAD's name: what they run, and whether they are active (needPage and needView). */
export function extActions(on: boolean): Record<string, [() => void, boolean]> {
  const go = (f: () => Promise<void>): [() => void, boolean] => [() => void f(), on]
  return {
    TechDraw_ExtensionDrawCosmCircle: go(vertexCommand('TechDraw cosmetic circle', 'cosmetic_circle2')),
    TechDraw_ExtensionDrawCosmCircle3Points: go(vertexCommand('TechDraw Cosmetic Circle 3 Points', 'cosmetic_circle3')),
    TechDraw_ExtensionDrawCosmArc: go(vertexCommand('TechDraw cosmetic arc', 'cosmetic_arc')),
    TechDraw_ExtensionLineParallel: go(lineCommand(true)), TechDraw_ExtensionLinePerpendicular: go(lineCommand(false)),
    TechDraw_ExtensionExtendLine: go(extendCommand(true)), TechDraw_ExtensionShortenLine: go(extendCommand(false)),
    TechDraw_ExtensionCircleCenterLines: go(circleCenterLines), TechDraw_ExtensionHoleCircle: go(boltCircle),
    TechDraw_ExtensionThreadHoleSide: go(threadCommand('hole_side')), TechDraw_ExtensionThreadBoltSide: go(threadCommand('bolt_side')),
    TechDraw_ExtensionThreadHoleBottom: go(threadCommand('hole_bottom')), TechDraw_ExtensionThreadBoltBottom: go(threadCommand('bolt_bottom')),
    TechDraw_ExtensionChangeLineAttributes: go(changeLineAttributes), TechDraw_ExtensionLockUnlockView: go(lockUnlock),
    TechDraw_ExtensionPositionSectionView: go(positionSection), TechDraw_ShowAll: go(showAllEdges),
    TechDraw_ExtensionSelectLineAttributes: [() => { const p = activePage(); if (p) openTask('techdraw', p, 'lineattrs') }, on],
    TechDraw_ExtensionCreateHorizChainDimension: go(dimCommand('TechDraw Create Horizontal Chain Dimension', 'chain_dim', 'h')),
    TechDraw_ExtensionCreateVertChainDimension: go(dimCommand('TechDraw Create Vertical Chain Dimension', 'chain_dim', 'v')),
    TechDraw_ExtensionCreateObliqueChainDimension: go(dimCommand('TechDraw Create Oblique Chain Dimension', 'chain_dim', 'o')),
    TechDraw_ExtensionCreateHorizCoordDimension: go(dimCommand('TechDraw Create Horizontal Coordinate Dimension', 'coord_dim', 'h')),
    TechDraw_ExtensionCreateVertCoordDimension: go(dimCommand('TechDraw Create Vertical Coord dimension', 'coord_dim', 'v')),
    TechDraw_ExtensionCreateObliqueCoordDimension: go(dimCommand('TechDraw Create Oblique Coord Dimension', 'coord_dim', 'o')),
    TechDraw_ExtensionCreateHorizChamferDimension: go(dimCommand('TechDraw Create Horizontal Chamfer Dimension', 'chamfer_dim', 'h')),
    TechDraw_ExtensionCreateVertChamferDimension: go(dimCommand('TechDraw Create Vertical Chamfer Dimension', 'chamfer_dim', 'v')),
    TechDraw_ExtensionCreateLengthArc: go(arcLengthDim),
    TechDraw_ExtensionPosHorizChainDimension: go(positionCommand('TechDraw PosHorizChainDimension', 'h', false)),
    TechDraw_ExtensionPosVertChainDimension: go(positionCommand('TechDraw PosVertChainDimension', 'v', false)),
    TechDraw_ExtensionPosObliqueChainDimension: go(positionCommand('TechDraw PosObliqueChainDimension', 'o', false)),
    TechDraw_ExtensionCascadeHorizDimension: go(positionCommand('TechDraw CascadeHorizDimension', 'h', true)),
    TechDraw_ExtensionCascadeVertDimension: go(positionCommand('TechDraw CascadeVertDimension', 'v', true)),
    TechDraw_ExtensionCascadeObliqueDimension: go(positionCommand('TechDraw CascadeObliqueDimension', 'o', true)),
    TechDraw_ExtensionInsertDiameter: go(prefixCommand('⌀')), TechDraw_ExtensionInsertSquare: go(prefixCommand('□')),
    TechDraw_ExtensionInsertRepetition: go(prefixCommand('%s× ')), TechDraw_ExtensionRemovePrefixChar: go(removePrefix),
    TechDraw_ExtensionIncreaseDecimal: go(decimalsCommand(1)), TechDraw_ExtensionDecreaseDecimal: go(decimalsCommand(-1)),
    TechDraw_ExtensionAreaAnnotation: go(areaAnnotation), TechDraw_ExtensionArcLengthAnnotation: go(arcLengthAnnotation),
  }
}

// ── the "Prefix Text" dialog (execInsertPrefixChar's QDialog) ───────────────────────────────────────────────────────
type Ask = { label: string; resolve(text: string | null): void }
let ask: Ask | null = null
const askSubs = new Set<() => void>()
const setAsk = (a: Ask | null) => { ask = a; askSubs.forEach((f) => f()) }
/** A line edit (right aligned) and the rest of the prefix as a label, an OK button; Esc closes it. null: closed without OK. */
let hosts = 0
const askPrefix = (label: string) => hosts
  ? new Promise<string | null>((resolve) => setAsk({ label, resolve }))
  : Promise.resolve(window.prompt(`Prefix Text (${label})`, ''))      // no page window to draw the dialog in
export function PrefixDialogHost() {
  const a = useSyncExternalStore((f) => { askSubs.add(f); return () => { askSubs.delete(f) } }, () => ask)
  const [v, setV] = useState('')
  useEffect(() => { hosts++; return () => { hosts-- } }, [])
  useEffect(() => { setV('') }, [a])
  if (!a) return null
  const done = (text: string | null) => { setAsk(null); a.resolve(text) }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') done(null); else if (e.key === 'Enter') done(v) }}>
      <div className="msgbox" role="dialog" aria-label="Prefix Text">
        <div className="msgbox-title">Prefix Text</div>
        <div className="msgbox-body" style={{ gap: 6 }}>
          <input autoFocus value={v} style={{ textAlign: 'right' }} onChange={(e) => setV(e.target.value)} />
          <span>{a.label}</span>
        </div>
        <div className="msgbox-buttons"><button className="qbtn default" onClick={() => done(v)}>OK</button></div>
      </div>
    </div>,
    document.body)
}

// ── TaskSelectLineAttributes ────────────────────────────────────────────────────────────────────────────────────────

/** Select Line Attributes, Cascade Spacing and Delta Distance: the style, width and colour new cosmetic lines take, and the
 *  spacing and distance the dimension and line commands use. OK keeps them for the session; they are not a document change. */
export function LineAttrsTask() {
  const [f, setF] = useState<Attrs>(attrs)
  const rb = f.weight <= THIN ? 'thin' : f.weight <= GRAPHIC ? 'middle' : f.weight <= THICK ? 'thick' : 'middle'
  const width = (w: number) => () => setF({ ...f, weight: w })
  const bind: Bindings = {
    cbLineStyle: { value: f.line_number - 1, opts: LINE_NAMES.map((n, i) => [i, n] as const), set: (i: number) => setF({ ...f, line_number: i + 1 }) },
    rbThin: { text: `Thin ${THIN}`, value: rb === 'thin', set: width(THIN) },
    rbMiddle: { text: `Middle ${GRAPHIC}`, value: rb === 'middle', set: width(GRAPHIC) },
    rbThick: { text: `Thick ${THICK}`, value: rb === 'thick', set: width(THICK) },
    cbColor: { value: hex(f.color), set: (c: string) => setF({ ...f, color: unhex(c) }) },
    sbSpacing: { value: f.cascade, dec: 2, min: -1e9, max: 1e9, step: 1, set: (x: number) => setF({ ...f, cascade: x }) },
    sbStretch: { value: f.stretch, dec: 2, min: -1e9, max: 1e9, step: 1, set: (x: number) => setF({ ...f, stretch: x }) },
  }
  const ok = () => {
    // accept(): the width is the group's: Thin, Middle (Graphic) or Thick, whichever button is on
    attrs = { ...f, weight: { thin: THIN, middle: GRAPHIC, thick: THICK }[rb] }
    closeTask()
  }
  return (
    <div className="tasks">
      <div className="tbuttons">
        <button className="qbtn default" onClick={ok}>OK</button>
        <button className="qbtn" onClick={closeTask}>Cancel</button>
      </div>
      <TaskBox title="Select Line Attributes" icon={'td-TechDraw_ExtensionSelectLineAttributes' as IconName}><QtForm form={TECHDRAW_FORMS.lineattrs} bind={bind} /></TaskBox>
    </div>)
}
/** For techdrawcheck.mjs: the session's attributes. */
export const extAttrs = () => attrs
