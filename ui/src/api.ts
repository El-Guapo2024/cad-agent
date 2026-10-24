// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/Dialogs/DlgUndoRedo.cpp: 2004 Werner Mayer
// The `cad serve` API. Every POST carries X-CAD, which the server requires, so
// other pages open in the browser can't drive it.
import type { FeatureDoc, HistoryEntry, ViewProps } from './store'

export type Param = { value: unknown; type: string; editable: boolean }
export type Vec3 = [number, number, number]
export type Placement = { move: Vec3; turn: Vec3; about: Vec3 }
export type Body = {
  name: string
  path: string
  part: string | null
  kind: string
  params: Record<string, Param> | null
  material: string | null
  color: string | null
  mass_g: number | null
  bbox: [Vec3, Vec3] | null
  center: Vec3 | null
  placement: Partial<Placement> | null
  about: Vec3 | null
  used_by: string[] | null
  /** The faces that are not flat, by number: the normal at the middle of the face's (u, v) range and the direction of its longest
   *  straight edge (scene.py curved_faces, Part::Feature::getCameraAlignmentDirection), for Align to Selection. */
  curved?: Record<string, [Vec3, Vec3 | null]>
  /** Where the part's own coordinates are drawn, row-major 4x4 (scene.py _matrix): for a PartDesign sketch or a Pad's preview. */
  matrix?: number[] | null
}
/** An axis of assembly.py's AXES (motion.Axis): the bodies it carries slide along `direction` by its position. */
export type Axis = { name: string; moves: string[]; direction: Vec3; travel: [number, number]; work: [number, number] | null }
export type Scene = {
  project: string
  source_hash: string
  written_utc?: string
  bodies: Body[]
  bbox: [Vec3, Vec3] | null
  units: string
  triangles: number
  unknown_placements?: string[]
  /** AXES and POSES of assembly.py (cad-scene/3): a pose is a position in mm for each of some axes. */
  axes?: Axis[]
  poses?: Record<string, Record<string, number>>
  viewer: unknown
}
export type CheckRow = {
  subject: string
  rule: string
  state: string
  measured?: string
  limit?: string
  source?: string
  check?: string
  artifacts?: string[]
}
/** checks.json: the rows, and what each part module said of itself when it was built (its PROCESS and MATERIAL, the docstring). */
export type PartMeta = { state?: string; doc?: string; material?: string | null; process?: string | null; mass_g?: number | null }
export type Checks = { rows?: CheckRow[]; summary?: Record<string, number>; written_utc?: string; parts?: Record<string, PartMeta> }
export type Status = { project: string; done: boolean; verdict: string | null; reasons: string[] }
export type LogEntry = { t: string; cmd: string; argv: string[]; exit: number; summary: string; files: string[]; ms: number }
export type Project = { slug: string; root: string; assembly: boolean; verdict: string | null; done: boolean
  /** The Start page's file card: the newest render (out/…png) and the project's own bytes. */
  thumb?: string | null; size?: number }
export type CacheInfo = { dir: string; bytes: number; text: string; limit: number; limitText: string; due: boolean }
/** GET /api/macros: one row per macro file in the macros dir. */
export type MacroInfo = { name: string; lines: number; modified: string }
export type MacroText = { name: string; text: string }
/** POST /api/macro/run: each line run, in order, as the console shows a `cad` command's result. */
export type MacroRunResult = { exit: number; ran: { line: string; exit: number; text: string }[] }
/** What `cad serve` returns for a cad command: the exit code and the command's JSON data. */
export type CadResult = { exit: number; data?: Record<string, any>; stderr?: string; text?: string }
/** What `cad export --format` writes (export.FORMATS). */
export type ExportFormat = 'step' | 'stl' | '3mf' | 'dxf'
/** `cad gui`: the person's current selection/visibility/view, so an agent (`cad gui …`) and
 *  the person stay in sync. `view` carries the camera/projection plus one Partial<ViewProps>
 *  entry per body (same keys as the store's `view` record), keyed by body name. */
export type GuiView = { camera: string | null; projection: 'ortho' | 'persp' | null }
/** `view` is the camera; `view_props` the per-body ViewProvider properties (FreeCAD's GuiDocument). */
/** The sketch in edit (sketcher.ts publishSketch): its geometry and its constraints as Sketcher.Constraint's arguments. */
export type GuiSketch = { name: string; part: string | null; geometry: unknown[]; constraints: { type: string; args: number[]; value?: number; driving?: boolean; name?: string }[]
  message: { state: string; status: string; link: string } }
export type GuiState = { selected: string[]; preselected: string | null; hidden: string[]; task: string | null; view: GuiView; view_props: Record<string, Partial<ViewProps>>; unselectable: string[]; sketch?: GuiSketch | null }
export type GuiStatus = GuiState & { slug: string; connected: boolean; updated: string }

async function http<T>(method: 'GET' | 'POST', path: string, body?: unknown, params?: Record<string, string | number>): Promise<T> {
  const url = params ? `${path}?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))}` : path
  const init: RequestInit = method === 'GET' ? {}
    : { method, headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body ?? {}) }
  const r = await fetch(url, init)
  const text = await r.text()
  let j: any
  try { j = text ? JSON.parse(text) : {} } catch { j = { error: text.slice(0, 300) } }
  if (!r.ok) throw new Error(j.error || r.statusText)
  return j as T
}

export const api = {
  /** `roots`: the folders `cad serve` watches, empty or not. */
  projects: () => http<{ projects: Project[]; roots: string[] }>('GET', '/api/projects'),
  scene: (slug: string) => http<Scene>('GET', '/api/scene', undefined, { slug }),
  checks: (slug: string) => http<Checks>('GET', '/api/checks', undefined, { slug }),
  status: (slug: string) => http<Status>('GET', '/api/status', undefined, { slug }),
  log: (slug: string, limit = 300) => http<{ entries: LogEntry[] }>('GET', '/api/log', undefined, { slug, limit }),
  /** GET /api/history: the Document's undo/redo journal, shared with an agent in a terminal —
   *  newest first, capped at FreeCAD's default stack depth (20). */
  history: (slug: string) => http<{ undo: HistoryEntry[]; redo: HistoryEntry[] }>('GET', '/api/history', undefined, { slug }),
  /** Std_Undo/Std_Redo against that journal; `steps` > 1 is the toolbar dropdown walking back/
   *  forward several entries at once (UndoDialog/RedoDialog, DlgUndoRedo.cpp). Exit 1: the
   *  project's files changed by hand since. */
  undo: (slug: string, steps?: number) => http<CadResult>('POST', '/api/undo', steps ? { slug, steps } : { slug }),
  redo: (slug: string, steps?: number) => http<CadResult>('POST', '/api/redo', steps ? { slug, steps } : { slug }),
  /** A rigid move on top of assembly.py (placements.toml); null resets it. */
  place: (slug: string, body: string, p: Placement | null) =>
    http<CadResult>('POST', '/api/place', p ? { slug, body, ...p } : { slug, body, reset: true }),
  /** Rewrites PARAMS literals in the part file (`cad set`). */
  set: (slug: string, part: string, values: Record<string, unknown>) => http<CadResult>('POST', '/api/set', { slug, part, values }),
  /** `cad feature list`: every part's PartDesign feature list (GET /api/<slug>/features), data.parts by part. */
  features: (slug: string) => http<CadResult & { data?: { parts?: Record<string, FeatureDoc>; errors?: Record<string, string> } }>('GET', `/api/${encodeURIComponent(slug)}/features`),
  /** `cad feature apply`: ops on one part's feature list as one undo step (POST /api/<slug>/features/<part>); `name` is the
   *  step's name when the ops are a task panel's (FreeCAD's "Edit Pad"). data.doc is the list after. */
  applyFeatures: (slug: string, part: string, ops: FeatureOp[], name?: string) =>
    http<CadResult>('POST', `/api/${encodeURIComponent(slug)}/features/${encodeURIComponent(part)}`, name ? { ops, name } : { ops }),
  /** Minimum distance between two placed parts, and the closest points (`cad measure --posed`). */
  measure: (slug: string, a: string, b: string) => http<CadResult>('POST', '/api/measure', { slug, a, b }),
  mass: (slug: string, bodies: string[]) => http<CadResult>('POST', '/api/mass', { slug, bodies }),
  reveal: (slug: string, part?: string) => http<{ revealed: string }>('POST', '/api/reveal', { slug, part }),
  /** `cad export`: a part as STEP or STL under out/, for a shop or a printer. */
  export: (slug: string, part: string, format: ExportFormat) => http<CadResult>('POST', '/api/export', { slug, part, format }),
  /** A file the commands wrote under out/ or baseline/. `inline` asks to see an svg or a pdf (a drawing's tab, a new
   *  browser tab) instead of saving it. */
  fileUrl: (slug: string, path: string, inline = false) => `/api/file?${new URLSearchParams({ slug, path, ...(inline ? { inline: '1' } : {}) })}`,
  /** POST /api/upload: a file the person picked, kept by the server, which answers where. A page is given a file's
   *  bytes and never its path, and `cad lib add` and `cad bought add-step` want a path. */
  upload: async (file: File): Promise<{ path: string; name: string; bytes: number; sha256: string }> => {
    const r = await fetch(`/api/upload?${new URLSearchParams({ name: file.name })}`,
      { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-CAD': '1' }, body: file })
    const text = await r.text()
    let j: any
    try { j = text ? JSON.parse(text) : {} } catch { j = { error: text.slice(0, 300) } }
    if (!r.ok) throw new Error(j.error || r.statusText)
    return j
  },
  // ── File menu (filemenu.tsx): Std_New. {"name", "brief"?} -> {"exit", "data": {"slug", "root"}, "stderr", "text"},
  // the same CadResult envelope as every other cad subcommand (it's `cad init` underneath). ──
  init: (name: string, brief?: string) => http<CadResult>('POST', '/api/init', brief ? { name, brief } : { name }),
  check: (slug: string) => http<{ started: boolean }>('POST', '/api/check', { slug }),
  verify: (slug: string) => http<{ started: boolean }>('POST', '/api/verify', { slug }),
  /** What the person's UI currently shows (persisted server-side like `hidden`). */
  gui: (slug: string) => http<GuiStatus>('GET', '/api/gui', undefined, { slug }),
  /** Partial updates merge server-side; send only the top-level fields that changed. */
  setGui: (slug: string, state: Partial<GuiState>) => http<Record<string, unknown>>('POST', '/api/gui', { slug, state }),
  /** Any cad subcommand (not serve/service), exactly as the CLI would run it. */
  cad: (slug: string, argv: string[]) => http<CadResult>('POST', '/api/cad', { slug, argv }),
  // ── Macro menu (macro.tsx): Std_DlgMacroRecord/Execute, DlgMacroExecuteImp's Create/Edit/… ──
  /** `cad pref`'s store (userprefs.py): the preferences the commands act on, e.g. MaxUndoSize. */
  prefs: () => http<{ prefs: Record<string, number> }>('GET', '/api/prefs'),
  /** `cad cache` (appcache.py): the user cache's location and size; startup also runs the periodic check. */
  cache: (startup = false) => http<CacheInfo>('GET', '/api/cache', undefined, startup ? { startup: '1' } : {}),
  clearCache: () => http<{ freed: number; bytes: number; text: string }>('POST', '/api/cache/clear', {}),
  setPref: (key: string, value: number) => http<{ prefs: Record<string, number> }>('POST', '/api/pref', { key, value }),
  macros: () => http<{ dir: string; macros: MacroInfo[] }>('GET', '/api/macros'),
  macro: (name: string) => http<MacroText>('GET', '/api/macro', undefined, { name }),
  saveMacro: (name: string, text: string) => http<{ ok?: boolean }>('POST', '/api/macro', { name, text }),
  deleteMacro: (name: string) => http<{ ok?: boolean }>('POST', '/api/macro/delete', { name }),
  renameMacro: (name: string, to: string) => http<{ ok?: boolean }>('POST', '/api/macro/rename', { name, to }),
  duplicateMacro: (name: string, to: string) => http<{ ok?: boolean }>('POST', '/api/macro/duplicate', { name, to }),
  runMacro: (name: string, slug: string) => http<MacroRunResult>('POST', '/api/macro/run', { name, slug }),
}

/** One edit of a feature list (cad_agent/feature_edit.py's apply): all of a POST's ops are one undo step. */
export type FeatureOp =
  /** after: the feature it goes after; null puts it first; left out, it goes at the end */
  | { op: 'add'; feature: Record<string, unknown>; after?: string | null }
  | { op: 'set'; name: string; props: Record<string, unknown> }
  | { op: 'delete'; name: string }
  | { op: 'rename'; name: string; to: string }
  | { op: 'move'; name: string; after: string | null }
  | { op: 'tip'; name: string }

/** What a cad call said when it didn't pass, for the report view. A verdict (exit 1 or 2) has no
 *  error: the answer is the command's own text, whose first line says it ("arduino_car  NOT DONE"). */
export function resultText(r: CadResult): string {
  const first = (r.text || '').split('\n').find((l) => l.trim())
  const summary = r.data?.summary // check and verify put their counts here, not a sentence
  return r.data?.error || (typeof summary === 'string' ? summary : '') || first?.trim() || (r.stderr || '').trim().split('\n').pop() || `exit ${r.exit}`
}
