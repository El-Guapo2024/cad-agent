// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/TechDraw/Gui/Workbench.cpp: 2005 Werner Mayer; 2013 Luke Parry
//   src/Mod/TechDraw/Gui/Command.cpp: 2002 Jürgen Riegel; 2014 Luke Parry
//   src/Mod/TechDraw/Gui/CommandCreateDims.cpp: 2014 Luke Parry; 2022 WandererFan
//   src/Mod/TechDraw/Gui/CommandAnnotate.cpp: 2019 WandererFan
//   src/Mod/TechDraw/Gui/DrawGuiUtil.cpp: 2016 WandererFan; 2024 Benjamin Bræstrup Sayoc
//   src/Mod/TechDraw/Gui/MDIViewPage.cpp: 2007 Jürgen Riegel; 2013 Luke Parry
//   src/Mod/TechDraw/Gui/QGVPage.cpp: 2013 Luke Parry
//   src/Mod/TechDraw/Gui/QGSPage.cpp: 2020 WandererFan
//   src/Mod/TechDraw/Gui/ViewProviderPage.cpp: 2004 Jürgen Riegel; 2012 Luke Parry
//   src/Mod/TechDraw/InitGui.py: 2002,2003 Jürgen Riegel
// The TechDraw workbench, for the project's pages (techdraw/<Page>.py: cad_agent/techdraw.py, docs/EDITING_PLAN.md
// "TechDraw pages in a project"): the TechDraw menu and its ten toolbars as Workbench.cpp sets them up, the commands that
// make pages, views, projection groups, sections, dimensions, balloons and annotations as FreeCAD's do (the same names,
// labels and undo steps), each page as an MDI view (MDIViewPage: the page drawn by cad_agent/techdraw_export.py's
// page_svg, panned and zoomed, its edges, vertices and views selected and its views and dimensions dragged), the
// pages in the tree (ViewProviderPage::claimChildren) and the property view of a page's objects. Every edit is
// `cad techdraw apply` on the server (POST /api/<slug>/techdraw/<page>), one undo step; the page is recomputed there.
// The task panels (TaskProjGroup, TaskSectionView, TaskDimension, TaskBalloon) are techdraw_tasks.tsx's.
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type FC, type ReactNode } from 'react'
import type { IDockviewPanelProps } from 'dockview'
import { api, resultText, type CadResult } from './api'
import { consoleLog, getState, report, setState, subscribe } from './store'
import { closeTask, getView, loadHistory, openPageWindow, openTask, pageWindows } from './actions'
import * as THREE from 'three'
import { Icon, type IconName } from './icons'
import { cls, EditRow, Group, Row } from './panels'
import { messageBox } from './msgbox'
import type { Entry } from './chrome'
import { TD_CMDS } from './techdraw_cmds'
import { annotActions } from './techdraw_annot'
import { TD_PROPS, type TdProp } from './techdraw_props'
import './techdraw.css'

// ── the model (cad_agent/techdraw_edit.py's read and techdraw.PageDocument.result) ──────────────────────────────────
export type TdObj = { name: string; kind: string; type_id: string; label?: string | null; [k: string]: unknown }
export type TdRow = { name: string; label: string; type: string; kind: string; depth: number; icon: string }
export type TdEdge = { kind: string; cls: string; visible: boolean; start: number[]; end: number[]; center?: number[]; radius?: number }
export type TdView = { x: number; y: number; scale: number; rotation?: number; edges?: TdEdge[]; vertices?: { x: number; y: number }[]; box?: number[]; group?: string | boolean }
export type TdDim = { kind: string; type: string; view: string; x: number; y: number; value: number; text: string; first?: number[]; second?: number[]; center?: number[]; radius?: number }
export type TdResult = { page: string | null; width: number; height: number; template: string | null; texts: Record<string, string>
  views: Record<string, TdView>; dimensions: Record<string, TdDim>; sections: Record<string, unknown>; errors: Record<string, string> }
export type TdDoc = { project: string; page: string; objects: TdObj[]; tree: TdRow[]; result?: TdResult; svg?: string }

type Mode = { kind: 'balloon'; page: string; view: string }
  /** TaskCosVertex's tracker: the next click on the page (mm from the lower left, y up) is handed to onPick */
  | { kind: 'pick'; page: string; view: string; onPick: (p: [number, number]) => void } | null
type TdState = { pages: string[]; docs: Record<string, TdDoc>; sel: string[]; pre: string | null; mode: Mode; frames: boolean
  /** a task panel's preview of a page (a dry run): the page drawn as the panel's values would leave it */
  preview: Record<string, TdDoc> }
let st: TdState = { pages: [], docs: {}, sel: [], pre: null, mode: null, frames: true, preview: {} }
const subs = new Set<() => void>()
export const tdState = () => st
export function setTd(p: Partial<TdState> | ((s: TdState) => Partial<TdState>)) {
  st = { ...st, ...(typeof p === 'function' ? p(st) : p) }
  subs.forEach((f) => f())
}
export function useTd<T>(sel: (s: TdState) => T): T {
  return useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => sel(st))
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const enc = encodeURIComponent
async function http(method: 'GET' | 'POST', path: string, body?: unknown): Promise<CadResult> {
  const r = await fetch(path, method === 'GET' ? {} : { method, headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body ?? {}) })
  const text = await r.text()
  let j: CadResult
  try { j = JSON.parse(text) } catch { throw new Error(text.slice(0, 300)) }
  if (!r.ok) throw new Error((j as unknown as { error?: string }).error || r.statusText)
  return j
}
export const labelOf = (o: TdObj | undefined) => (o ? (typeof o.label === 'string' && o.label ? o.label : o.name) : '')
export const objOf = (page: string, name: string) => st.docs[page]?.objects.find((o) => o.name === name)
/** A selection reference: "Page/View" or "Page/View.Edge3". */
export const refOf = (page: string, obj: string, sub?: string) => `${page}/${obj}${sub ? `.${sub}` : ''}`
export function splitRef(ref: string): [string, string, string | null] {
  const [page, rest = ''] = ref.split('/')
  const dot = rest.indexOf('.')
  return dot < 0 ? [page, rest, null] : [page, rest.slice(0, dot), rest.slice(dot + 1)]
}
const VIEW_KINDS = new Set(['DrawViewPart', 'DrawProjGroupItem', 'DrawViewSection'])
export const isView = (o: TdObj | undefined) => !!o && VIEW_KINDS.has(o.kind)

// ── loading and editing ─────────────────────────────────────────────────────────────────────────────────────────
let loading = 0
/** `cad techdraw ls`, then each page recomputed with its SVG (`cad techdraw show --svg`). */
export async function loadTechDraw() {
  const slug = getState().slug
  if (!slug) { setTd({ pages: [], docs: {}, sel: [], preview: {} }); return }
  const n = ++loading
  try {
    const r = await http('GET', `/api/${enc(slug)}/techdraw`)
    if (n !== loading || slug !== getState().slug) return
    const pages = ((r.data?.pages ?? []) as { page: string }[]).map((p) => p.page)
    const docs: Record<string, TdDoc> = {}
    await Promise.all(pages.map(async (p) => {
      try {
        const d = await http('GET', `/api/${enc(slug)}/techdraw/${enc(p)}`)
        if (d.exit === 0) docs[p] = d.data as unknown as TdDoc
        else report('warn', `${p}: ${resultText(d)}`)
      } catch (e) { report('err', `${p}: ${msg(e)}`) }
    }))
    if (n !== loading || slug !== getState().slug) return
    setTd((s) => ({ pages, docs, sel: s.sel.filter((ref) => !!docs[splitRef(ref)[0]]?.objects.some((o) => o.name === splitRef(ref)[1])) }))
    for (const d of Object.values(docs)) for (const [name, err] of Object.entries(d.result?.errors ?? {})) report('warn', `${d.page}: ${name}: ${err}`)
  } catch (e) { report('err', `TechDraw: ${msg(e)}`) }
}

/** `cad techdraw apply`: the ops as one undo step named as FreeCAD's transaction. With dryRun the page as the ops would
 *  leave it, nothing written (a task panel's preview, setTd preview). */
export async function applyTd(page: string, ops: Record<string, unknown>[], name?: string, dryRun = false, amend = false): Promise<TdDoc | null> {
  const s = getState()
  if (!s.slug) return null
  if (!dryRun && s.scriptToPyConsole) consoleLog('in', `cad techdraw apply ${s.slug} ${page} --ops '${JSON.stringify(ops)}'${name ? ` --name '${name}'` : ''}${amend ? ' --amend' : ''}`)
  try {
    const r = await http('POST', `/api/${enc(s.slug)}/techdraw/${enc(page)}`, { ops, ...(name ? { name } : {}), ...(dryRun ? { dry_run: true } : {}), ...(amend ? { amend: true } : {}) })
    if (r.exit !== 0) { if (!dryRun) report('err', `${name ?? 'TechDraw'}: ${resultText(r)}`); return null }
    const doc = (r.data?.doc ?? null) as unknown as TdDoc | null
    if (!doc) return null
    if (dryRun) { setTd((x) => ({ preview: { ...x.preview, [page]: doc } })); return doc }
    setTd((x) => {
      const preview = { ...x.preview }
      delete preview[page]
      return { docs: { ...x.docs, [page]: doc }, pages: x.pages.includes(page) ? x.pages : [...x.pages, page].sort(), preview }
    })
    for (const [n, err] of Object.entries(doc.result?.errors ?? {})) report('warn', `${page}: ${n}: ${err}`)
    loadHistory()
    return doc
  } catch (e) { report('err', `${name ?? 'TechDraw'}: ${msg(e)}`); return null }
}
export const clearPreview = (page: string) => setTd((x) => { const p = { ...x.preview }; delete p[page]; return { preview: p } })

// ── the active page (DrawGuiUtil::findPage) ─────────────────────────────────────────────────────────────────────
let lastPage: string | null = null
/** The page a command works on: the page window in front, else the page of what is selected, else the only one. */
export function activePage(): string | null {
  const front = pageWindows().find((w) => w.active)?.page
  if (front && st.docs[front]) return front
  const fromSel = st.sel.map((r) => splitRef(r)[0]).find((p) => st.docs[p])
  if (fromSel) return fromSel
  if (lastPage && st.docs[lastPage]) return lastPage
  return st.pages.length ? st.pages[0] : null
}
export function openPage(page: string) {
  const d = st.docs[page]
  const label = labelOf(d?.objects.find((o) => o.kind === 'DrawPage')) || page
  lastPage = page
  openPageWindow(page, label)
}
const allNames = () => new Set([...st.pages, ...Object.values(st.docs).flatMap((d) => d.objects.map((o) => o.name))])
/** Document::getUniqueObjectName over every page of the project (FreeCAD's one document). */
export function uniqueName(base: string): string {
  const taken = allNames()
  if (!taken.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!taken.has(n)) return n }
}

// ── the commands (Command.cpp, CommandCreateDims.cpp, CommandAnnotate.cpp) ────────────────────────────────────────
const warn = (title: string, text: string) => void messageBox('warning', title, text)
const parts = () => {
  const s = getState()
  const out: string[] = []
  for (const n of s.selected) { const b = s.scene?.bodies.find((x) => x.name === n); if (b?.part && !out.includes(b.part)) out.push(b.part) }
  for (const r of s.featSel) { const p = r.split('/')[0]; if (p && !out.includes(p)) out.push(p) }
  return out
}
/** TechDraw_PageDefault ("Drawing create page"): Page with a Template of the default template, then the page shown. */
export async function newPage(template?: string) {
  if (!getState().slug) { warn('No document', 'Make or open a document first'); return }
  const page = uniqueName('Page')
  const d = await applyTd(page, [{ op: 'new_page', ...(template ? { template } : {}) }], 'Drawing create page')
  if (d) { setTd({ sel: [] }); openPage(page) }
}
/** TechDraw_PageTemplate: the template picked (FreeCAD's file dialog on Preferences::defaultTemplateDir). */
async function newPageFromTemplate() {
  const names = ['Default_Template_A4_Landscape.svg', 'ISO/A4_Landscape_TD.svg', 'ISO/A3_Landscape_TD.svg',
    'ISO/A4_Landscape_ISO5457_minimal.svg', 'ISO/A3_Landscape_ISO5457_minimal.svg', 'ISO/A4_Portrait_ISO5457_minimal.svg']
  const pick = await messageBox('question', 'Select a template file', 'The templates the app has (FreeCAD\'s Mod/TechDraw/Templates):', [...names, 'Cancel'])
  if (pick && pick !== 'Cancel') await newPage(pick)
}
function needPage(): string | null {
  const p = activePage()
  if (!p) warn('No page found', 'No Drawing Pages in document.')
  return p
}
/** TechDraw_View ("Create view"): a DrawProjGroupItem "View" of the selected parts at the page's centre, looking from
 *  the front (Preferences::useCameraDirection is off in a fresh profile), then TaskProjGroup in create mode. */
async function newView(group = false) {
  const page = needPage()
  if (!page) return
  const src = parts()
  if (!src.length) {
    if (group) warn('Wrong selection', 'No shapes, groups, or links in this selection')
    else warn('Wrong selection', 'To insert a view from existing objects, select them before invoking this tool. Without a selection, a file browser will open to insert an SVG or image file.')
    return
  }
  const before = new Set(st.docs[page]?.objects.map((o) => o.name))
  // CmdTechDrawProjectionGroup: the anchor looks as the 3D view does (DrawGuiUtil::get3DDirAndRot); TechDraw_View from the
  // front (viewDirection, Preferences::useCameraDirection off)
  const dirs = group ? cameraDirs() : null
  const d = await applyTd(page, [{ op: group ? 'projgroup' : 'view', source: src, ...(dirs ? { direction: dirs[0], x_direction: dirs[1] } : {}) }],
    group ? 'Create projection group' : 'Create view')
  const made = d?.objects.find((o) => !before.has(o.name) && (group ? o.kind === 'DrawProjGroup' : o.kind === 'DrawProjGroupItem'))
  if (made) { setTd({ sel: [refOf(page, made.name)] }); openPage(page); openTask('techdraw', page, `projgroup:${made.name}:create`) }
}
/** get3DDirAndRot: the camera's view direction reversed (TechDraw looks towards the viewer) and up x direction for the right;
 *  rounded to the float SbVec3f holds, then snapped to a basis vector as checkDirectionVsBasis does when it is one. */
function cameraDirs(): [number[], number[]] | null {
  const q = getView()?.cameraOrientation()
  if (!q) return null
  const r = new THREE.Quaternion(q[0], q[1], q[2], q[3])
  const dir = new THREE.Vector3(0, 0, 1).applyQuaternion(r), up = new THREE.Vector3(0, 1, 0).applyQuaternion(r)
  const right = new THREE.Vector3().crossVectors(up, dir)
  const snap = (v: THREE.Vector3) => v.toArray().map((c) => { const f = Math.fround(c); return Math.abs(f) < 1e-6 ? 0 : Math.abs(Math.abs(f) - 1) < 1e-6 ? Math.sign(f) : f })
  return [snap(dir), snap(right)]
}
/** TechDraw_SectionView: TaskSectionView for the selected view (it makes the section when a direction is picked). */
function newSection() {
  const page = needPage()
  if (!page) return
  const v = st.sel.map(splitRef).find(([p, n, sub]) => p === page && !sub && isView(objOf(p, n)))
  if (!v) { warn('Wrong selection', 'Select at least 1 DrawViewPart object as Base.'); return }
  openTask('techdraw', page, `section:${v[1]}:create`)
}
/** The dimension commands: the selection's edges and vertices of one view, as dimMaker takes them. */
const DIMS: Record<string, [string, string]> = {
  TechDraw_LengthDimension: ['Distance', 'Length'], TechDraw_HorizontalDimension: ['DistanceX', 'Horizontal'],
  TechDraw_VerticalDimension: ['DistanceY', 'Vertical'], TechDraw_RadiusDimension: ['Radius', 'Radius'],
  TechDraw_DiameterDimension: ['Diameter', 'Diameter'], TechDraw_AngleDimension: ['Angle', 'Angle'],
  TechDraw_3PtAngleDimension: ['Angle3Pt', 'Angle3Pt'],
}
function selectedSubs(): { page: string; view: string; subs: string[] } | null {
  const refs = st.sel.map(splitRef).filter(([, , sub]) => !!sub)
  if (!refs.length) return null
  const [page, view] = refs[0]
  return { page, view, subs: refs.filter(([p, v]) => p === page && v === view).map(([, , s]) => s!) }
}
async function dimension(type: string) {
  const sel = selectedSubs()
  if (!sel) { warn('Incorrect Selection', 'Select an object first'); return }
  const edges = sel.subs.filter((s) => s.startsWith('Edge')), verts = sel.subs.filter((s) => s.startsWith('Vertex'))
  const geo = st.docs[sel.page]?.result?.views[sel.view]
  const kind = (s: string) => geo?.edges?.[Number(s.slice(4))]?.kind
  if (type === 'Radius' || type === 'Diameter') {
    if (edges.length !== 1 || !['CIRCLE', 'ARCOFCIRCLE', 'ELLIPSE', 'ARCOFELLIPSE'].includes(kind(edges[0]) ?? '')) {
      warn('Incorrect Selection', `Can not make a ${type} dimension from selection`); return }
  } else if (type === 'Angle') {
    if (edges.length !== 2 || verts.length) { warn('Incorrect Selection', 'Can not make 2D angle dimension from selection'); return }
  } else if (type === 'Angle3Pt') {
    if (verts.length !== 3) { warn('Incorrect Selection', 'Can not make 3-point angle dimension from selection'); return }
  } else if (!((edges.length === 1 && !verts.length) || (edges.length + verts.length === 2))) {
    warn('Incorrect Selection', `Can not make a ${type === 'Distance' ? '' : type === 'DistanceX' ? 'horizontal ' : 'vertical '}dimension from selection`); return }
  const before = new Set(st.docs[sel.page]?.objects.map((o) => o.name))
  const d = await applyTd(sel.page, [{ op: 'dimension', type, references: sel.subs.map((s) => [sel.view, s]) }], 'Create dimension')
  const made = d?.objects.find((o) => !before.has(o.name))
  if (made) setTd({ sel: [refOf(sel.page, made.name)] })        // dimensionMaker: the new dimension selected
}
/** TechDraw_Dimension, the smart tool: the type the selection makes (one straight edge: horizontal, vertical or
 *  aligned by its direction; a circle: diameter, an arc: radius; two edges: an angle unless parallel; vertices: a length). */
async function smartDimension() {
  const sel = selectedSubs()
  if (!sel) { warn('Incorrect Selection', 'Select an object first'); return }
  const geo = st.docs[sel.page]?.result?.views[sel.view]
  const edges = sel.subs.filter((s) => s.startsWith('Edge')).map((s) => geo?.edges?.[Number(s.slice(4))])
  const verts = sel.subs.filter((s) => s.startsWith('Vertex'))
  if (edges.length === 1 && !verts.length && edges[0]) {
    const e = edges[0]
    if (e.kind === 'CIRCLE' || e.kind === 'ELLIPSE') return dimension('Diameter')
    if (e.kind === 'ARCOFCIRCLE' || e.kind === 'ARCOFELLIPSE') return dimension('Radius')
    const dx = Math.abs(e.end[0] - e.start[0]), dy = Math.abs(e.end[1] - e.start[1])
    return dimension(dy < 1e-6 ? 'DistanceX' : dx < 1e-6 ? 'DistanceY' : 'Distance')
  }
  if (edges.length === 2 && !verts.length && edges.every((e) => e?.kind === 'GENERIC')) {
    const d = (e: TdEdge) => { const v = [e.end[0] - e.start[0], e.end[1] - e.start[1]]; const n = Math.hypot(v[0], v[1]) || 1; return [v[0] / n, v[1] / n] }
    const a = d(edges[0]!), b = d(edges[1]!)
    return dimension(Math.abs(a[0] * b[1] - a[1] * b[0]) < 1e-6 ? 'Distance' : 'Angle')
  }
  if (verts.length === 3 && !edges.length) return dimension('Angle3Pt')
  return dimension('Distance')
}
/** TechDraw_Annotation ("Create Annotation"): "Default Text" at the page's centre. */
async function annotation() {
  const page = needPage()
  if (!page) return
  const before = new Set(st.docs[page]?.objects.map((o) => o.name))
  const d = await applyTd(page, [{ op: 'annotation' }], 'Create Annotation')
  const made = d?.objects.find((o) => !before.has(o.name))
  if (made) setTd({ sel: [refOf(page, made.name)] })
}
/** TechDraw_Balloon: with a view selected, the page waits for a click on the view (QGVPage::startBalloonPlacing). */
function balloon() {
  const page = needPage()
  if (!page) return
  const v = st.sel.map(splitRef).find(([p, n]) => p === page && isView(objOf(p, n)))
  if (!v) { warn('Incorrect selection', 'Select a View'); return }
  openPage(page)
  setTd({ mode: { kind: 'balloon', page, view: v[1] } })
  report('msg', 'Click on the view where the balloon should point')
}
async function placeBalloon(page: string, view: string, origin: [number, number]) {
  setTd({ mode: null })
  const before = new Set(st.docs[page]?.objects.map((o) => o.name))
  const d = await applyTd(page, [{ op: 'balloon', view, origin, at: [origin[0], origin[1]] }], 'Create Balloon')
  const made = d?.objects.find((o) => !before.has(o.name))
  if (made) setTd({ sel: [refOf(page, made.name)] })
}
/** TechDraw_ExportPageSVG / DXF / PDF: `cad techdraw export`, the file saved from out/techdraw/. */
async function exportPage(fmt: 'svg' | 'dxf' | 'pdf') {
  const page = needPage()
  const slug = getState().slug
  if (!page || !slug) return
  try {
    const r = await api.cad(slug, ['techdraw', 'export', slug, page, '--format', fmt])
    if (r.exit !== 0) { report('err', `Export: ${resultText(r)}`); return }
    const a = document.createElement('a')
    a.href = api.fileUrl(slug, `out/techdraw/${page}.${fmt}`)
    a.download = `${page}.${fmt}`
    document.body.appendChild(a); a.click(); a.remove()
    report('msg', `Exported out/techdraw/${page}.${fmt}`)
  } catch (e) { report('err', `Export: ${msg(e)}`) }
}
/** TechDraw_FillTemplateFields: the template's fields from the document's information (DrawTemplate::getAutofillValue). */
async function fillTemplateFields() {
  const page = needPage()
  if (!page) return
  const tpl = st.docs[page]?.objects.find((o) => o.kind === 'DrawSVGTemplate')
  if (!tpl) return
  const texts = { ...(tpl.editable_texts as Record<string, string>) }
  const today = new Date()
  const date = `${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}/${String(today.getFullYear()).slice(2)}`
  for (const k of Object.keys(texts)) {
    if (k === 'FC-Date') texts[k] = date
    if (k === 'FC-Title') texts[k] = getState().slug ?? texts[k]
  }
  await applyTd(page, [{ op: 'set', name: tpl.name, props: { editable_texts: texts } }], 'Update Template Fields')
}

// ── the menu and toolbars (Workbench::setupMenuBar, setupToolBars) ─────────────────────────────────────────────────
const NOT_PORTED = 'not ported yet (docs/EDITING_PLAN.md, "TechDraw pages in a project"; ui/PARITY.md, "TechDraw")'
const WHY: Record<string, string> = {
  TechDraw_PrintAll: 'printing is the browser\'s: export the page as PDF', TechDraw_ActiveView: 'there is no image of the 3D view to insert',
  TechDraw_DraftView: 'there are no Draft objects', TechDraw_ArchView: 'there are no BIM section planes', TechDraw_SpreadsheetView: 'there are no spreadsheets',
  TechDraw_Image: 'pages hold no images', TechDraw_Symbol: 'pages hold no SVG symbols', TechDraw_ProjectShape: 'a shape projected in 3D is not a page object',
}
function cmdEntry(cmd: string, onSelect?: () => void, disabled = false): Exclude<Entry, 'sep'> {
  const c = TD_CMDS[cmd]
  const icon = (c?.icon ?? undefined) as IconName | undefined
  if (!onSelect) return { label: c?.text ?? cmd, icon, cmd, disabled: true, title: `${c?.tip ?? ''}\n(${WHY[cmd] ?? NOT_PORTED})`.trim() }
  return { label: c?.text ?? cmd, icon, cmd, disabled, title: c?.tip, onSelect }
}
function tdCtx() {
  const s = getState()
  const doc = !!s.slug
  const havePage = st.pages.length > 0
  const haveView = Object.values(st.docs).some((d) => d.objects.some((o) => isView(o)))
  // CommandFillTemplateFields.IsActive: a page whose template has fields to fill
  const fields = Object.values(st.docs).some((d) => d.objects.some((o) => o.kind === 'DrawSVGTemplate' && Object.keys((o.editable_texts as object) ?? {}).length > 0))
  return { doc, havePage, haveView, dim: havePage && haveView, fields }
}
/** Every ported command, by its FreeCAD name: what it runs and whether it is active (isActive). */
function actions(): Record<string, [() => void, boolean]> {
  const c = tdCtx()
  const dim = (t: string) => [() => void dimension(t), c.dim] as [() => void, boolean]
  return {
    TechDraw_PageDefault: [() => void newPage(), c.doc], TechDraw_PageTemplate: [() => void newPageFromTemplate(), c.doc],
    TechDraw_RedrawPage: [() => void loadTechDraw(), c.havePage && c.haveView], TechDraw_FillTemplateFields: [() => void fillTemplateFields(), c.fields],
    TechDraw_ExportPageSVG: [() => void exportPage('svg'), c.havePage], TechDraw_ExportPageDXF: [() => void exportPage('dxf'), c.havePage],
    TechDraw_ExportPagePDF: [() => void exportPage('pdf'), c.havePage],
    TechDraw_View: [() => void newView(false), c.havePage], TechDraw_ProjectionGroup: [() => void newView(true), c.havePage && !getState().task],
    TechDraw_SectionView: [() => newSection(), c.havePage && c.haveView], TechDraw_SectionGroup: [() => newSection(), c.havePage && c.haveView],
    TechDraw_Dimension: [() => void smartDimension(), c.dim], TechDraw_CompDimensionTools: [() => void smartDimension(), c.dim],
    TechDraw_LengthDimension: dim('Distance'), TechDraw_HorizontalDimension: dim('DistanceX'), TechDraw_VerticalDimension: dim('DistanceY'),
    TechDraw_RadiusDimension: dim('Radius'), TechDraw_DiameterDimension: dim('Diameter'), TechDraw_AngleDimension: dim('Angle'),
    TechDraw_3PtAngleDimension: dim('Angle3Pt'),
    ...annotActions(c.havePage && c.haveView),
    TechDraw_Balloon: [() => balloon(), c.havePage && c.haveView && !getState().task], TechDraw_Annotation: [() => void annotation(), c.havePage],
    // ToggleFrame's isActive: Preferences > TechDraw > View Frames set to Manual, which a fresh profile is not
    TechDraw_ToggleFrame: [() => setTd((s) => ({ frames: !s.frames })), false],
  }
}
const e = (cmd: string): Exclude<Entry, 'sep'> => { const a = actions()[cmd]; return a ? cmdEntry(cmd, a[0], !a[1]) : cmdEntry(cmd) }
const list = (cmds: string[]): Entry[] => cmds.map((c) => (c === 'Separator' || c === 'sep' ? 'sep' : e(c)))
const sub = (label: string, cmds: string[]): Exclude<Entry, 'sep'> => ({ label, sub: list(cmds) })

/** TechDraw's "Tech&Draw" menu, item by item as Workbench::setupMenuBar builds it. */
export function techdrawMenu(): Entry[] {
  return [
    sub('Page', ['TechDraw_PageDefault', 'TechDraw_PageTemplate', 'TechDraw_FillTemplateFields', 'TechDraw_RedrawPage', 'TechDraw_PrintAll',
      'Separator', 'TechDraw_ExportPageSVG', 'TechDraw_ExportPageDXF', 'TechDraw_ExportPagePDF']),
    'sep',
    sub('TechDraw Views', ['TechDraw_View', 'TechDraw_BrokenView', 'TechDraw_SectionView', 'TechDraw_ComplexSection', 'TechDraw_DetailView',
      'TechDraw_ProjectionGroup', 'TechDraw_ClipGroup', 'Separator', 'TechDraw_Symbol', 'TechDraw_Image', 'Separator', 'TechDraw_ShareView',
      'Separator', 'TechDraw_ToggleFrame', 'Separator', 'TechDraw_ProjectShape']),
    'sep',
    sub('Views From Other Workbenches', ['TechDraw_ActiveView', 'TechDraw_DraftView', 'TechDraw_ArchView', 'TechDraw_SpreadsheetView']),
    'sep',
    sub('Dimensions', ['TechDraw_Dimension', 'TechDraw_LengthDimension', 'TechDraw_HorizontalDimension', 'TechDraw_VerticalDimension',
      'TechDraw_RadiusDimension', 'TechDraw_DiameterDimension', 'TechDraw_AngleDimension', 'TechDraw_3PtAngleDimension', 'TechDraw_AreaDimension',
      'TechDraw_HorizontalExtentDimension', 'TechDraw_VerticalExtentDimension', 'TechDraw_DimensionRepair']),
    'sep',
    sub('Hatching', ['TechDraw_Hatch', 'TechDraw_GeometricHatch']),
    'sep',
    sub('Symbols', ['TechDraw_WeldSymbol', 'TechDraw_SurfaceFinishSymbols', 'TechDraw_HoleShaftFit']),
    'sep',
    sub('Stacking', ['TechDraw_StackTop', 'TechDraw_StackBottom', 'TechDraw_StackUp', 'TechDraw_StackDown']),
    sub('Aligning', ['TechDraw_AlignVertexesVertically', 'TechDraw_AlignVertexesHorizontally']),
    'sep',
    sub('Attributes/Modifications', ['TechDraw_ExtensionSelectLineAttributes', 'TechDraw_ExtensionChangeLineAttributes', 'Separator',
      'TechDraw_ExtensionExtendLine', 'TechDraw_ExtensionShortenLine', 'Separator', 'TechDraw_ExtensionLockUnlockView',
      'TechDraw_ExtensionPositionSectionView', 'Separator', 'TechDraw_ExtensionPosHorizChainDimension', 'TechDraw_ExtensionPosVertChainDimension',
      'TechDraw_ExtensionPosObliqueChainDimension', 'TechDraw_ExtensionCascadeHorizDimension', 'TechDraw_ExtensionCascadeVertDimension',
      'TechDraw_ExtensionCascadeObliqueDimension', 'Separator', 'TechDraw_ExtensionAreaAnnotation', 'TechDraw_ExtensionArcLengthAnnotation',
      'TechDraw_ExtensionCustomizeFormat']),
    sub('Centerlines/Threading', ['TechDraw_ExtensionCircleCenterLines', 'TechDraw_ExtensionHoleCircle', 'Separator',
      'TechDraw_ExtensionThreadHoleSide', 'TechDraw_ExtensionThreadHoleBottom', 'TechDraw_ExtensionThreadBoltSide', 'TechDraw_ExtensionThreadBoltBottom',
      'Separator', 'TechDraw_ExtensionVertexAtIntersection', 'TechDraw_CommandAddOffsetVertex', 'Separator', 'TechDraw_CosmeticCircle',
      'TechDraw_ExtensionDrawCosmCircle', 'TechDraw_ExtensionDrawCosmCircle3Points', 'TechDraw_ExtensionDrawCosmArc', 'TechDraw_ExtensionLineParallel',
      'TechDraw_ExtensionLinePerpendicular']),
    sub('Format/Organize Dimensions', ['TechDraw_ExtensionCreateHorizChainDimension', 'TechDraw_ExtensionCreateVertChainDimension',
      'TechDraw_ExtensionCreateObliqueChainDimension', 'TechDraw_ExtensionCreateHorizCoordDimension', 'TechDraw_ExtensionCreateVertCoordDimension',
      'TechDraw_ExtensionCreateObliqueCoordDimension', 'TechDraw_ExtensionCreateHorizChamferDimension', 'TechDraw_ExtensionCreateVertChamferDimension',
      'TechDraw_ExtensionCreateLengthArc', 'Separator', 'TechDraw_ExtensionInsertDiameter', 'TechDraw_ExtensionInsertSquare',
      'TechDraw_ExtensionInsertRepetition', 'TechDraw_ExtensionRemovePrefixChar', 'Separator', 'TechDraw_ExtensionIncreaseDecimal',
      'TechDraw_ExtensionDecreaseDecimal']),
    'sep',
    sub('Annotations', ['TechDraw_Annotation', 'TechDraw_RichTextAnnotation', 'TechDraw_Balloon', 'TechDraw_AxoLengthDimension']),
    sub('Add Lines', ['TechDraw_LeaderLine', 'TechDraw_FaceCenterLine', 'TechDraw_2LineCenterLine', 'TechDraw_2PointCenterLine',
      'TechDraw_2PointCosmeticLine', 'Separator', 'TechDraw_DecorateLine', 'TechDraw_ShowAll']),
    sub('Add Vertices', ['TechDraw_CosmeticVertex', 'TechDraw_Midpoints', 'TechDraw_Quadrants']),
    'sep',
    e('TechDraw_CosmeticEraser'),
  ]
}
/** A group command's tool button (Gui::GroupCommand): its first command's icon, the list in its menu. */
function group(cmd: string): Exclude<Entry, 'sep'> {
  const c = TD_CMDS[cmd]
  const items = list(c?.group ?? [])
  const first = items.find((x): x is Exclude<Entry, 'sep'> => x !== 'sep')
  return { label: c?.text ?? cmd, icon: first?.icon, cmd, sub: items, split: true, onSelect: first?.onSelect, disabled: !items.some((x) => x !== 'sep' && !x.disabled), title: c?.tip }
}
/** The workbench's toolbars, button by button (setupToolBars; dimensioning: SingleDimensioningTool on, SeparatedDimensioningTools off). */
export function techdrawToolbars(): [string, Entry[]][] {
  return [
    ['TechDraw Pages', list(['TechDraw_PageDefault', 'TechDraw_PageTemplate', 'TechDraw_FillTemplateFields', 'TechDraw_RedrawPage', 'TechDraw_PrintAll'])],
    ['TechDraw Views', [e('TechDraw_View'), e('TechDraw_BrokenView'), e('TechDraw_ActiveView'), group('TechDraw_SectionGroup'), e('TechDraw_DetailView'),
      e('TechDraw_DraftView'), e('TechDraw_SpreadsheetView'), e('TechDraw_ClipGroup')]],
    ['TechDraw Stacking', [group('TechDraw_StackGroup')]],
    ['TechDraw Dimensions', [group('TechDraw_CompDimensionTools'), e('TechDraw_Balloon'), e('TechDraw_AxoLengthDimension'), e('TechDraw_DimensionRepair')]],
    ['TechDraw Attributes', [e('TechDraw_ExtensionSelectLineAttributes'), e('TechDraw_ExtensionChangeLineAttributes'), group('TechDraw_ExtensionExtendShortenLineGroup'),
      e('TechDraw_ExtensionLockUnlockView'), e('TechDraw_ExtensionPositionSectionView'), e('TechDraw_ExtensionCustomizeFormat')]],
    ['TechDraw Centerlines', [group('TechDraw_ExtensionCircleCenterLinesGroup'), group('TechDraw_ExtensionThreadsGroup'), group('TechDraw_CommandVertexCreationGroup'),
      group('TechDraw_ExtensionDrawCirclesGroup'), group('TechDraw_ExtensionLinePPGroup')]],
    ['TechDraw Extend Dimensions', [group('TechDraw_ExtensionInsertPrefixGroup'), group('TechDraw_ExtensionIncreaseDecreaseGroup')]],
    ['TechDraw File Access', list(['TechDraw_ExportPageSVG', 'TechDraw_ExportPageDXF'])],
    ['TechDraw Decoration', list(['TechDraw_ToggleFrame', 'TechDraw_Hatch', 'TechDraw_GeometricHatch'])],
    ['TechDraw Annotation', [e('TechDraw_RichTextAnnotation'), e('TechDraw_LeaderLine'), group('TechDraw_CosmeticVertexGroup'), group('TechDraw_CenterLineGroup'),
      e('TechDraw_2PointCosmeticLine'), e('TechDraw_DecorateLine'), e('TechDraw_ShowAll'), e('TechDraw_WeldSymbol'), e('TechDraw_SurfaceFinishSymbols'),
      e('TechDraw_HoleShaftFit')]],
  ]
}
export const TECHDRAW_TOOLBARS = ['TechDraw Pages', 'TechDraw Views', 'TechDraw Stacking', 'TechDraw Dimensions', 'TechDraw Attributes',
  'TechDraw Centerlines', 'TechDraw Extend Dimensions', 'TechDraw File Access', 'TechDraw Decoration', 'TechDraw Annotation']
/** The menu and toolbars as plain data, for techdrawcheck.mjs (cadui.techdraw()). */
export function techdrawMenus() {
  const plain = (es: Entry[]): unknown[] => es.map((x) => (x === 'sep' ? { sep: true } : { text: x.label, cmd: x.cmd ?? null, enabled: !x.disabled, ...(x.sub ? { menu: plain(x.sub) } : {}) }))
  return { menu: plain(techdrawMenu()), toolbars: techdrawToolbars().map(([title, es]) => ({ title, buttons: plain(es) })) }
}
/** The registry's entries (cmdreg.ts): every TechDraw command by its FreeCAD name. */
export function techdrawCommands(): [string, Exclude<Entry, 'sep'>][] {
  const out: [string, Exclude<Entry, 'sep'>][] = []
  const walk = (es: Entry[]) => { for (const x of es) { if (x === 'sep') continue; if (x.cmd && x.onSelect && !out.some(([c]) => c === x.cmd)) out.push([x.cmd, x]); if (x.sub) walk(x.sub) } }
  walk(techdrawMenu())
  for (const [, es] of techdrawToolbars()) walk(es)
  return out
}
export const techdrawRun = (cmd: string) => { const a = actions()[cmd]; if (a && a[1]) a[0]() }
export const techdrawEnabled = (cmd: string) => !!actions()[cmd]?.[1]

// ── selection ────────────────────────────────────────────────────────────────────────────────────────────────────
/** Gui::Selection for a page's objects and their elements (ctrl adds and removes); the 3D selection is cleared, as one
 *  selection holds both in FreeCAD. */
export function tdSelect(ref: string | null, additive = false) {
  setTd((s) => {
    if (!ref) return { sel: [] }
    if (!additive) return { sel: [ref] }
    return { sel: s.sel.includes(ref) ? s.sel.filter((r) => r !== ref) : [...s.sel, ref] }
  })
  if (ref) setState({ selected: [], featSel: [], asmSel: [] })
}
// the 3D view's or the tree's selection of something else takes the page's away
let prevSel = getState().selected, prevFeat = getState().featSel
subscribe(() => {
  const s = getState()
  if ((s.selected !== prevSel && s.selected.length) || (s.featSel !== prevFeat && s.featSel.length)) { if (st.sel.length) setTd({ sel: [] }) }
  prevSel = s.selected; prevFeat = s.featSel
})
// a project opened or closed: its pages
let lastSlug: string | null = null
subscribe(() => { const s = getState(); if (s.slug !== lastSlug) { lastSlug = s.slug; setTd({ pages: [], docs: {}, sel: [], preview: {}, mode: null }); void loadTechDraw() } })

/** Delete on the page's selection (Std_Delete): the selected objects, their dimensions and balloons with them. */
export async function deleteTd(): Promise<boolean> {
  const objs = st.sel.map(splitRef).filter(([, , sub]) => !sub)
  if (!objs.length) return false
  const page = objs[0][0]
  const names = objs.filter(([p]) => p === page).map(([, n]) => n).filter((n) => {
    const o = objOf(page, n)
    return o && o.kind !== 'DrawPage' && o.kind !== 'DrawSVGTemplate'
  })
  if (!names.length) return false
  setTd({ sel: [] })
  await applyTd(page, names.map((n) => ({ op: 'delete', name: n })), 'Delete')
  return true
}

// ── the page's window (MDIViewPage, QGVPage) ─────────────────────────────────────────────────────────────────────
const PX = 10 // the SVG's units per millimetre (Rez::guiX)
type PageParams = { page: string }
/** One page in a tab: its SVG with the selection and preselection drawn, pan with the middle or right button and a
 *  drag on the paper, the wheel zooms about the pointer, a click selects an edge, a vertex or a view's object, a
 *  drag on a view or a dimension moves it (QGIView::mouseReleaseEvent sets X and Y), a double click edits it. */
export const TechDrawPage: FC<IDockviewPanelProps<PageParams>> = (props) => {
  const [p, setP] = useState<PageParams>(props.params)
  useEffect(() => { const d = props.api.onDidParametersChange((np) => setP(np as PageParams)); return () => d.dispose() }, [props.api])
  const page = p.page
  const doc = useTd((s) => s.preview[page] ?? s.docs[page])
  const sel = useTd((s) => s.sel), pre = useTd((s) => s.pre), mode = useTd((s) => s.mode)
  const box = useRef<HTMLDivElement>(null), host = useRef<HTMLDivElement>(null)
  const [view, setView] = useState({ k: 0, x: 0, y: 0 })
  const fitted = useRef(false)
  const w = doc?.result?.width ?? 297, h = doc?.result?.height ?? 210
  const fit = () => {
    const b = box.current
    if (!b) return
    const r = b.getBoundingClientRect()
    const k = Math.min((r.width - 40) / (w * PX), (r.height - 40) / (h * PX))
    setView({ k, x: (r.width - w * PX * k) / 2, y: (r.height - h * PX * k) / 2 })
  }
  useLayoutEffect(() => { if (doc && !fitted.current) { fit(); fitted.current = true } }, [doc]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = host.current
    if (!el || !doc?.svg) return
    el.innerHTML = doc.svg.replace(/^<\?xml[^>]*>\s*/, '')
    const svg = el.querySelector('svg')
    if (svg) { svg.setAttribute('width', String(w * PX)); svg.setAttribute('height', String(h * PX)) }
  }, [doc?.svg, w, h])
  // the selection and the preselection, drawn on the elements (QGIEdge/QGIVertex's colours: Preferences > Selection)
  useEffect(() => {
    const el = host.current
    if (!el) return
    el.querySelectorAll('.td-sel, .td-pre').forEach((x) => x.classList.remove('td-sel', 'td-pre'))
    const mark = (ref: string, c: string) => {
      const [pg, obj, subName] = splitRef(ref)
      if (pg !== page) return
      const q = subName ? `[data-view="${obj}"][data-sub="${subName}"]` : `[data-view="${obj}"], [data-dim="${obj}"], [data-name="${obj}"]`
      el.querySelectorAll(q).forEach((x) => x.classList.add(c))
    }
    sel.forEach((r) => mark(r, 'td-sel'))
    if (pre) mark(pre, 'td-pre')
  }, [sel, pre, doc?.svg, page])
  const target = (t: EventTarget | null): string | null => {
    const el = (t as Element | null)?.closest?.('[data-sub], [data-dim], [data-name], [data-view]')
    if (!el) return null
    const v = el.getAttribute('data-view'), subName = el.getAttribute('data-sub')
    if (v && subName) return refOf(page, v, subName)
    const n = el.getAttribute('data-dim') ?? el.getAttribute('data-name') ?? v
    return n ? refOf(page, n) : null
  }
  /** The page point (mm from the lower left, y up) under a client point. */
  const pagePoint = (cx: number, cy: number): [number, number] => {
    const r = box.current!.getBoundingClientRect()
    const sx = (cx - r.left - view.x) / view.k / PX, sy = (cy - r.top - view.y) / view.k / PX
    return [sx, h - sy]
  }
  const drag = useRef<{ x: number; y: number; ref: string | null; moved: boolean; pan: boolean; vx: number; vy: number; el: Element | null } | null>(null)
  const onDown = (ev: React.PointerEvent) => {
    const ref = ev.button === 0 ? target(ev.target) : null
    const pan = ev.button !== 0 || !ref
    const [, obj] = ref ? splitRef(ref) : [null, null]
    const o = obj ? objOf(page, obj) : undefined
    const movable = o && (isView(o) || o.kind === 'DrawProjGroup' || o.kind === 'DrawViewDimension' || o.kind === 'DrawViewBalloon' || o.kind === 'DrawViewAnnotation')
    drag.current = { x: ev.clientX, y: ev.clientY, ref, moved: false, pan, vx: view.x, vy: view.y, el: movable ? host.current : null }
    ;(ev.target as Element).setPointerCapture?.(ev.pointerId)
  }
  const onMove = (ev: React.PointerEvent) => {
    const d = drag.current
    if (!d) { setTd({ pre: target(ev.target) }); return }
    const dx = ev.clientX - d.x, dy = ev.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < 4) return
    d.moved = true
    if (d.pan) { setView((v) => ({ ...v, x: d.vx + dx, y: d.vy + dy })); return }
    if (d.ref && d.el) {
      const [, obj] = splitRef(d.ref)
      const o = objOf(page, obj)
      const owner = o?.kind === 'DrawProjGroupItem' ? groupOf(page, obj) ?? obj : obj
      host.current?.querySelectorAll(`[data-view="${owner}"], [data-dim="${obj}"], [data-name="${obj}"]`).forEach((x) =>
        (x as SVGElement).setAttribute('transform', `translate(${dx / view.k} ${dy / view.k})`))
      if (o && (isView(o) || o.kind === 'DrawProjGroup')) for (const item of itemsOf(page, owner))
        host.current?.querySelectorAll(`[data-view="${item}"]`).forEach((x) => (x as SVGElement).setAttribute('transform', `translate(${dx / view.k} ${dy / view.k})`))
    }
  }
  const onUp = async (ev: React.PointerEvent) => {
    const d = drag.current
    drag.current = null
    if (!d) return
    if (mode?.kind === 'pick' && mode.page === page && !d.moved) {
      const [px, py] = pagePoint(ev.clientX, ev.clientY)
      mode.onPick([px, py])
      return
    }
    if (mode?.kind === 'balloon' && mode.page === page && !d.moved) {
      // QGVPage's balloon placing: the click is where the balloon points, on the view the command was given
      const v = doc?.result?.views[mode.view]
      if (v) {
        const [px, py] = pagePoint(ev.clientX, ev.clientY)
        await placeBalloon(page, mode.view, [px - v.x, py - v.y])
      }
      return
    }
    if (!d.moved) { tdSelect(d.ref, ev.ctrlKey || ev.metaKey); return }
    if (d.pan || !d.ref || !d.el) return
    const [, obj] = splitRef(d.ref)
    const o = objOf(page, obj)
    if (!o) return
    const dmmx = (ev.clientX - d.x) / view.k / PX, dmmy = -(ev.clientY - d.y) / view.k / PX
    let name = obj
    if (o.kind === 'DrawProjGroupItem') {
      const g = groupOf(page, obj)
      if (g) {
        const go = objOf(page, g)
        if (o.item_type === 'Front' || go?.auto_distribute) name = g   // the Front (or an auto-distributed item) drags the group
      }
    }
    const t = objOf(page, name)!
    await applyTd(page, [{ op: 'move', name, x: Number(t.x) + dmmx, y: Number(t.y) + dmmy }], 'Drag view')
  }
  const onWheel = (ev: React.WheelEvent) => {
    const r = box.current!.getBoundingClientRect()
    const f = Math.exp(-ev.deltaY * 0.0015)
    setView((v) => { const k = Math.min(20, Math.max(0.02, v.k * f)); const px = ev.clientX - r.left, py = ev.clientY - r.top; return { k, x: px - (px - v.x) * (k / v.k), y: py - (py - v.y) * (k / v.k) } })
  }
  const onDouble = (ev: React.MouseEvent) => {
    const ref = target(ev.target)
    if (!ref) return
    const [, obj] = splitRef(ref)
    editObject(page, obj)
  }
  if (!doc) return <div className="td-page empty">Loading {page}…</div>
  return (
    <div className="td-page">
      <div ref={box} className={cls('td-scene', (mode?.kind === 'balloon' || mode?.kind === 'pick') && 'placing')} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={(ev) => void onUp(ev)}
        onPointerLeave={() => setTd({ pre: null })} onWheel={onWheel} onDoubleClick={onDouble} onContextMenu={(ev) => ev.preventDefault()}
        onKeyDown={(ev) => { if (ev.key === 'Escape') setTd({ mode: null }) }} tabIndex={0}>
        <div className="td-sheet" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})` }}>
          <div ref={host} className={cls('td-svg', !useTd((s) => s.frames) && 'noframes')} />
        </div>
      </div>
    </div>
  )
}
const groupOf = (page: string, item: string) => st.docs[page]?.objects.find((o) => o.kind === 'DrawProjGroup' && (o.views as string[]).includes(item))?.name ?? null
const itemsOf = (page: string, g: string) => (objOf(page, g)?.views as string[] | undefined) ?? []

/** A double click (ViewProvider::doubleClicked): a view's or a group's TaskProjGroup, a section's TaskSectionView, a
 *  dimension's TaskDimension, a balloon's TaskBalloon; a page opens its window. */
export function editObject(page: string, name: string) {
  const o = objOf(page, name)
  if (!o) return
  if (o.kind === 'DrawPage') { openPage(page); return }
  if (o.kind === 'DrawViewSection') { openTask('techdraw', page, `section:${name}:edit`); return }
  if (o.kind === 'DrawProjGroupItem') { const g = groupOf(page, name); openTask('techdraw', page, `projgroup:${g ?? name}:edit`); return }
  if (o.kind === 'DrawProjGroup' || o.kind === 'DrawViewPart') { openTask('techdraw', page, `projgroup:${name}:edit`); return }
  if (o.kind === 'DrawViewDimension') { openTask('techdraw', page, `dimension:${name}:edit`); return }
  if (o.kind === 'DrawViewBalloon') { openTask('techdraw', page, `balloon:${name}:edit`); return }
}
export const closeTd = closeTask

// ── the tree (ViewProviderPage and its views' claimChildren) ─────────────────────────────────────────────────────
export function TechDrawRows({ iconSize = 16 }: { iconSize?: number }) {
  const pages = useTd((s) => s.pages), docs = useTd((s) => s.docs), sel = useTd((s) => s.sel)
  const [closed, setClosed] = useState<Record<string, boolean>>({})
  const rows: ReactNode[] = []
  for (const page of pages) {
    const d = docs[page]
    if (!d) continue
    let hideBelow = Infinity
    for (const r of d.tree) {
      if (r.depth > hideBelow) continue
      hideBelow = Infinity
      const key = `${page}/${r.name}`
      const kids = d.tree.some((x, i) => i > d.tree.indexOf(r) && x.depth > r.depth && d.tree.slice(d.tree.indexOf(r) + 1, i).every((y) => y.depth > r.depth))
      const isOpen = !closed[key]
      if (kids && !isOpen) hideBelow = r.depth
      const icon = (`td-${r.icon}` in TD_ICON_KEYS ? `td-${r.icon}` : 'td-TechDraw_TreeView') as IconName
      rows.push(
        <div key={key} className={cls('trow', sel.includes(refOf(page, r.name)) && 'sel')} data-td={key}
          onClick={(ev) => tdSelect(refOf(page, r.name), ev.ctrlKey || ev.metaKey)} onDoubleClick={() => editObject(page, r.name)}>
          <span className="tlab">
            <span className="pdindent" style={{ width: 6 + 16 * (r.depth + 1) }} />
            {kids ? <span className={cls('twisty', isOpen && 'open')} onClick={(ev) => { ev.stopPropagation(); setClosed((c) => ({ ...c, [key]: isOpen })) }} /> : <span className="tindent" />}
            <span className="ticon"><Icon name={icon} size={iconSize} /></span>
            <span className="tname">{r.label}</span>
          </span>
        </div>)
    }
  }
  return <>{rows}</>
}
const TD_ICON_KEYS: Record<string, true> = Object.fromEntries(Object.values(TD_CMDS).map((c) => [c.icon ?? '', true as const]).concat(
  ['TechDraw_TreePage', 'TechDraw_TreePageTemplate', 'TechDraw_TreeView', 'TechDraw_TreeProjGroup', 'TechDraw_TreeSection', 'TechDraw_TreeAnnotation',
    'TechDraw_Dimension', 'TechDraw_Balloon', 'TechDraw_LengthDimension', 'TechDraw_HorizontalDimension', 'TechDraw_VerticalDimension', 'TechDraw_RadiusDimension',
    'TechDraw_DiameterDimension', 'TechDraw_AngleDimension', 'TechDraw_3PtAngleDimension'].map((n) => [`td-${n}`, true as const])))

// ── the property view (PropertyEditor over the object's properties: techdraw_props.ts, the real FreeCAD's rows) ───────
const NUMERIC = /Float|Distance|Length|Angle|Integer|Quantity|Percent/
/** What a row the page file does not hold shows: the template's size, a page's views. */
function derived(page: string, o: TdObj, p: string): unknown {
  const d = st.docs[page]
  if (o.kind === 'DrawSVGTemplate' && (p === 'Width' || p === 'Height')) return p === 'Width' ? d?.result?.width : d?.result?.height
  if (o.kind === 'DrawSVGTemplate' && p === 'Orientation') return (d?.result?.width ?? 0) >= (d?.result?.height ?? 0) ? 'Landscape' : 'Portrait'
  if (o.kind === 'DrawPage' && p === 'Views') return d?.objects.filter((x) => x.kind !== 'DrawPage' && x.kind !== 'DrawSVGTemplate' && !groupOf(page, x.name)).map((x) => x.name)
  return undefined
}
/** The selected page object's property view (Data tab): FreeCAD's groups and rows, the ones the page file holds editable. */
export function TechDrawProps() {
  const sel = useTd((s) => s.sel)
  const docs = useTd((s) => s.docs)
  const last = [...sel].reverse().map(splitRef).find(([, , sub]) => !sub)
  if (!last) return null
  const [page, name] = last
  const o = docs[page]?.objects.find((x) => x.name === name)
  if (!o) return null
  const rows = TD_PROPS[o.kind] ?? []
  const groups = [...new Set(rows.map((r) => r.g))]
  const commit = (r: TdProp, v: unknown) => {
    const key = r.k === 'dim_type' || r.k === 'item_type' ? 'type' : r.k!
    void applyTd(page, [{ op: 'set', name, props: { [key]: v } }], `Edit ${name}.${r.p.replace(/ /g, '')}`)
  }
  const show = (v: unknown) => Array.isArray(v) ? (v.length === 3 && v.every((x) => typeof x === 'number') ? `[${(v as number[]).map((x) => x.toFixed(2)).join(' ')}]`
    : (v as unknown[]).map((x) => (Array.isArray(x) ? `${x[0]}.${x[1]}` : String(x))).join(', '))
    : v && typeof v === 'object' ? `[${Object.keys(v).length} items]` : v === null || v === undefined ? '' : String(v)
  return (
    <>{groups.map((g) => (
      <Group key={g} title={g}>
        {rows.filter((r) => r.g === g).map((r) => {
          const v = r.k === 'label' ? labelOf(o) : r.k ? o[r.k] : derived(page, o, r.p)
          const ro = !r.k || (o.kind === 'DrawProjGroupItem' && r.k === 'item_type')
          if (!ro && r.t.endsWith('Bool')) return <EditRow key={r.p} k={r.p} value={v} type="bool" depth={1} onCommit={(nv) => commit(r, nv)} />
          if (!ro && NUMERIC.test(r.t)) return <EditRow key={r.p} k={r.p} value={v} type={/Integer/.test(r.t) ? 'int' : 'float'} depth={1} onCommit={(nv) => commit(r, nv)} />
          if (!ro && r.t.endsWith('PropertyString')) return <EditRow key={r.p} k={r.p} value={v} type="str" depth={1} onCommit={(nv) => commit(r, nv)} />
          if (!ro && r.e) {
            return <div key={r.p} className="prow" tabIndex={0}><span className="pk" style={{ paddingLeft: 16 }}>{r.p}</span>
              <span className="pv"><select className="pselect" value={String(v)} onChange={(ev) => commit(r, ev.target.value)}>
                {r.e.map((x) => <option key={x} value={x}>{x}</option>)}</select></span></div>
          }
          return <Row key={r.p} k={r.p} v={show(v)} depth={1} />
        })}
      </Group>))}</>
  )
}
