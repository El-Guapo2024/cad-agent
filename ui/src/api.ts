// The `cad serve` API. Every POST carries X-CAD, which the server requires, so
// other pages open in the browser can't drive it.
import type { HistoryEntry, ViewProps } from './store'

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
}
export type Scene = {
  project: string
  source_hash: string
  written_utc?: string
  bodies: Body[]
  bbox: [Vec3, Vec3] | null
  units: string
  triangles: number
  unknown_placements?: string[]
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
export type Checks = { rows?: CheckRow[]; summary?: Record<string, number>; written_utc?: string }
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
/** `cad gui`: the person's current selection/visibility/view, so an agent (`cad gui …`) and
 *  the person stay in sync. `view` carries the camera/projection plus one Partial<ViewProps>
 *  entry per body (same keys as the store's `view` record), keyed by body name. */
export type GuiView = { camera: string | null; projection: 'ortho' | 'persp' | null }
/** `view` is the camera; `view_props` the per-body ViewProvider properties (FreeCAD's GuiDocument). */
export type GuiState = { selected: string[]; preselected: string | null; hidden: string[]; task: string | null; view: GuiView; view_props: Record<string, Partial<ViewProps>>; unselectable: string[] }
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
  projects: () => http<{ projects: Project[] }>('GET', '/api/projects'),
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
  /** Minimum distance between two placed parts, and the closest points (`cad measure --posed`). */
  measure: (slug: string, a: string, b: string) => http<CadResult>('POST', '/api/measure', { slug, a, b }),
  mass: (slug: string, bodies: string[]) => http<CadResult>('POST', '/api/mass', { slug, bodies }),
  reveal: (slug: string, part?: string) => http<{ revealed: string }>('POST', '/api/reveal', { slug, part }),
  /** `cad export`: a part as STEP or STL under out/, for a shop or a printer. */
  export: (slug: string, part: string, format: 'step' | 'stl') => http<CadResult>('POST', '/api/export', { slug, part, format }),
  fileUrl: (slug: string, path: string) => `/api/file?${new URLSearchParams({ slug, path })}`,
  // ── File menu (filemenu.tsx): Std_New. Contract per the lead (not yet built server-side):
  // {"name"} -> {"exit", "data": {"slug", "root"}, "stderr", "text"}, same CadResult envelope
  // as every other cad subcommand (it's `cad init` underneath). ──
  init: (name: string) => http<CadResult>('POST', '/api/init', { name }),
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

/** What a cad call said when it didn't pass, for the report view. */
export function resultText(r: CadResult): string {
  return r.data?.error || r.data?.summary || (r.stderr || '').trim().split('\n').pop() || `exit ${r.exit}`
}
