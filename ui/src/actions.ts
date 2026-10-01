import type { DockviewApi } from 'dockview-react'
import { api, resultText, type Body, type GuiState, type Placement, type Vec3 } from './api'
import { consoleLog, getState, report, saved, setState, subscribe, type DrawStyle, type SelEntry, type State, type Task, type ViewProps } from './store'
import type { CadView } from './viewer'
// Type-only: cmdreg.ts imports this file for its commands' functions, so this stays a type import
// (erased at build), the same way commands.ts avoids importing cmdreg.ts back.
import type { CommandInfo } from './cmdreg'

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
// fetch() rejects with a TypeError when it can't reach the server at all.
const unreachable = (e: unknown) => e instanceof TypeError

// ── the 3D view and the dock ────────────────────────────────────────────────
let view: CadView | null = null
let dock: DockviewApi | null = null

export const getView = () => view
export function attachView(v: CadView | null) {
  if (v) {
    // Track the last named Std_View*/Home direction shown, for `cad gui`'s camera field —
    // every caller (toolbar, menu, keyboard shortcuts, or an incoming `cad gui view`) goes
    // through one of these two, so wrapping them here needs no changes to those call sites.
    const viewDir = v.viewDir.bind(v)
    v.viewDir = (d) => { viewDir(d); setState({ cameraPreset: d }); recordGui('view', d) }
    const home = v.home.bind(v)
    v.home = (d) => { home(d); setState({ cameraPreset: d }); recordGui('view', 'home') }
    // Std_ViewFitAll / Std_ViewFitSelection: same wrapping trick, for the macro recorder.
    const fitAll = v.fitAll.bind(v)
    v.fitAll = (names, instant) => { fitAll(names, instant); recordGui('fit', ...(names?.length ? ['selection'] : [])) }
  }
  view = v
  const sc = getState().scene
  if (v && sc) v.show(sc, false)
}
/** The dock, for debugging from the console (cadui.getDock()). */
export const getDock = () => dock
export function setDock(d: DockviewApi) {
  dock = d
  titleView()
}
/** Set view properties on objects (the property view's View tab and the display commands). */
export function setViewProps(names: string[], patch: Partial<ViewProps>) {
  setState((s) => ({ view: { ...s.view, ...Object.fromEntries(names.map((n) => [n, { ...s.view[n], ...patch }])) } }))
  if (isRecording()) { const kv = Object.entries(patch).map(fmtViewProp); for (const n of names) recordGui('set', n, ...kv) }
}

// ── Std_DlgMacroRecord: the macro recorder. macro.tsx owns the dialogs, the api calls and the
// "Record GUI commands" preference's checkbox; this keeps the line buffer and the hooks below
// (setParams, place, setViewProps above, select, toggleVisibility, attachView's viewDir/home/
// fitAll, setOrtho) each a FreeCAD command class would record from individually
// (MacroManager::addLine). ──
let recording: { name: string; lines: string[] } | null = null
export const isRecording = () => !!recording
/** Std_DlgMacroRecord, "not recording" branch, once macro.tsx's dialog gets a name:
 *  DlgMacroRecordImp::onButtonStartClicked. */
export function startRecording(name: string) {
  recording = { name, lines: [] }
  setState({ recordingMacro: name })
  report('msg', `Recording macro "${name}". Macro recording (now "Stop macro recording") ends and saves it.`)
}
/** DlgMacroRecordImp::onButtonCloseClicked, before Record is clicked: MacroManager::cancel(). */
export function cancelRecording() {
  recording = null
  setState({ recordingMacro: null })
}
/** Std_DlgMacroRecord, "recording" branch (commits directly, no dialog): MacroManager::commit(),
 *  MacroFile::commit's header/body (here: a `# cad macro:`/`# recorded` header, no FreeCAD import). */
export async function stopRecording() {
  if (!recording) return
  const { name, lines } = recording
  recording = null
  setState({ recordingMacro: null })
  const text = [`# cad macro: ${name}`, `# recorded ${new Date().toISOString()}`, ...lines].join('\n') + '\n'
  try {
    await api.saveMacro(name, text)
    report('msg', `Macro "${name}" saved, ${lines.length} line${lines.length === 1 ? '' : 's'}.`)
  } catch (e) {
    report('err', `Could not save macro "${name}": ${msg(e)}`)
  }
}
/** A model-changing line: the same text setParams/place echo to the console, but with the
 *  project slug made explicit, as a real `cad` CLI invocation needs (the console's own echo
 *  omits it there: the project is already open). */
const recordLine = (line: string) => recording?.lines.push(line)
// Same ViewObject names as commands.ts's private FREECAD_PROP/fmtProp (`cad gui set`'s
// vocabulary); kept separately here so this file doesn't import commands.ts (which imports
// this one, for its own Std_View*/Selection handling).
const GUI_PROP: Record<string, string> = {
  displayMode: 'DisplayMode', boundingBox: 'BoundingBox', showInTree: 'ShowInTree', showPlacement: 'ShowPlacement', drawStyle: 'DrawStyle',
  lighting: 'Lighting', lineColor: 'LineColor', lineWidth: 'LineWidth', pointColor: 'PointColor', pointSize: 'PointSize',
  shapeColor: 'ShapeColor', transparency: 'Transparency', onTop: 'OnTopWhenSelected', selectionStyle: 'SelectionStyle',
  deviation: 'Deviation', angularDeflection: 'AngularDeflection',
}
const fmtViewProp = ([k, v]: [string, unknown]) => {
  const name = GUI_PROP[k] ?? k
  return `${name}=${typeof v === 'number' && name.endsWith('Color') ? '#' + v.toString(16).padStart(6, '0') : v}`
}
/** A GUI-only line (selection, show/hide, view, fit, view props): Macro.cpp's MacroOutputOption,
 *  its two checkboxes (RecordGui, GuiAsComment) collapsed to macro.tsx's one "Record GUI
 *  commands" preference: live when on, `# ` commented when off, same as
 *  MacroManager::makeComment prepending to a line that isn't already a comment. */
export function recordGui(cmd: string, ...parts: string[]) {
  if (!recording) return
  // MacroOutputOption::values: RecordGui off → not recorded; on with GuiAsComment → a comment.
  const { recordGuiCommands, guiAsComment, slug } = getState()
  if (!recordGuiCommands) return
  const line = ['cad gui', cmd, slug ?? '', ...parts].filter(Boolean).join(' ')
  recording.lines.push(guiAsComment ? `# ${line}` : line)
}
/** cmdreg.ts's registered commands, triggered from a menu, toolbar or key (chrome.tsx/App.tsx)
 *  while recording: mirrors Command::_invoke's own fallback (src/Gui/Command.cpp) of auto-logging
 *  `Gui.runCommand(name,0)` only when the command didn't already record its own line(s) — our
 *  `name`'s functions that already call recordGui/recordLine themselves (place/setParams/
 *  setViewProps/select/attachView's viewDir·home·fitAll/setOrtho/toggleVisibility/…) aren't
 *  double-recorded; everything else gets a `cad gui run SLUG name` fallback line. */
export function recordAndRun(name: string, run: () => void, args: string[] = []) {
  if (!isRecording()) { run(); return }
  const before = recording!.lines.length
  run()
  if (recording && recording.lines.length === before) recordGui('run', name, ...args)
}
// ── Std_DockOverlay: FreeCAD's overlay panels ─────────────────────────────────
export type Side = 'left' | 'bottom'
const SIDE_PANEL: Record<Side, string> = { left: 'model', bottom: 'report' }
const groupOf = (id: string) => dock?.getPanel(id)?.group as any
const floating = (g: any) => g?.api?.location?.type === 'floating'
const sideBox = (side: Side) => (groupOf(SIDE_PANEL[side])?.element as HTMLElement | undefined)?.closest('.dv-resize-container') as HTMLElement | null
/** Map a dockview group (as handed to a rightHeaderActionsComponent) back to its overlay side. */
export function sideOfGroup(g: unknown): Side | null {
  return (['left', 'bottom'] as Side[]).find((s) => groupOf(SIDE_PANEL[s]) === g) ?? null
}
/** Float a side's panels over the 3D view (overlay), or dock them back beside it. */
export function overlaySide(side: Side, on: boolean) {
  const g = groupOf(SIDE_PANEL[side]), view = groupOf('view3d')
  if (!dock || !g || !view || floating(g) === on) return
  if (on) {
    const W = dock.width, H = dock.height, left = Math.round(Math.min(340, W * 0.3))
    dock.addFloatingGroup(g, side === 'left' ? { x: 4, y: 4, width: left, height: H - 8 } : { x: left + 12, y: H - 184, width: W - left - 20, height: 180 })
    requestAnimationFrame(() => armAutoHide(side))
  } else {
    disarmAutoHide(side)
    g.api.moveTo({ group: view, position: side })
    // Back in the layout at the default sizes (App.tsx onReady).
    requestAnimationFrame(() => groupOf(SIDE_PANEL[side])?.api?.setSize(side === 'left' ? { width: 330 } : { height: 170 }))
  }
}
/** Toggle Overlay for All Panels. */
export function overlayAll() {
  const on = !(['left', 'bottom'] as Side[]).every((s) => floating(groupOf(SIDE_PANEL[s])))
  overlaySide('left', on)
  overlaySide('bottom', on)
}
/** Toggle Overlay: the panel under the cursor (here, the active one). */
export function overlayActive() {
  const g = (dock as any)?.activeGroup
  if (!g || g === groupOf('view3d')) return
  const side: Side = g === groupOf(SIDE_PANEL.bottom) ? 'bottom' : 'left'
  overlaySide(side, !floating(g))
}
/** Toggle Left / Right / Top / Bottom: show or hide an overlay panel. */
export function overlayToggle(side: 'left' | 'right' | 'top' | 'bottom') {
  if (side !== 'left' && side !== 'bottom') return
  if (!floating(groupOf(SIDE_PANEL[side]))) return
  const box = sideBox(side)
  if (box) box.style.display = box.style.display === 'none' ? '' : 'none'
}
/** Toggle Transparent Panels / Toggle Transparent Mode (the active panel's). */
export function overlayTransparent(all: boolean) {
  if (all) {
    document.querySelector('.dock')?.classList.toggle('ovl-transparent')
  } else {
    const g = (dock as any)?.activeGroup
    ;(g?.element as HTMLElement | undefined)?.closest('.dv-resize-container')?.classList.toggle('ovl-transparent-one')
  }
  // A TaskShow panel never auto-hides while transparent (checkAutoHide, OverlayWidgets.cpp:1292-1294).
  evaluate('left'); evaluate('bottom')
}
/** Bypass Mouse Events in Overlay Panels (T, T). */
export const overlayBypass = () => document.querySelector('.dock')?.classList.toggle('ovl-bypass')

// ── OverlayWidgets.cpp: auto hide/show modes, hover reveal, animation ─────────
// No preferences dialog here, so OverlayParams.py's defaults are hardcoded, not user-editable.
const HINT_TRIGGER = 16 // DockOverlayHintTriggerSize: hover hit zone at the edge, px
const HINT_SIZE = 8 // DockOverlayHintSize: the painted hint strip inside that zone, px (see css-overlay.css)
const HINT_DELAY = 200 // DockOverlayHintDelay: ms hover dwell before the hint reveals (OverlayProxyWidget::hitTest)
const REVEAL_GRACE = 2000 // DockOverlayRevealDelay: ms a just-revealed panel stays up even if the mouse leaves
export const OVERLAY_ANIM_MS = 200 // DockOverlayAnimationDuration (0 would disable it; FreeCAD's default is on)
// DockOverlayAnimationCurve default (7) is QEasingCurve::InOutCubic; closest standard CSS easing.
export const OVERLAY_ANIM_CURVE = 'cubic-bezier(.645,.045,.355,1)'

/** OverlayTabWidget::AutoMode (OverlayWidgets.h 139-151); 'none' is NoAutoMode. */
export type OverlayAutoMode = 'none' | 'autohide' | 'editshow' | 'edithide' | 'taskshow'
/** The auto mode menu, in its OverlayTabWidget ctor order (OverlayWidgets.cpp 441-445),
 *  with its OverlayTabWidget::retranslate() text (989-1006). */
export const AUTO_MODES: [OverlayAutoMode, string, string][] = [
  ['none', 'None', 'Turn off auto hide/show'],
  ['autohide', 'Auto hide', 'Auto hide docked widgets on leave'],
  ['editshow', 'Show on edit', 'Auto show docked widgets on editing'],
  ['edithide', 'Hide on edit', 'Auto hide docked widgets on editing'],
  ['taskshow', 'Auto task', 'Auto show task view for any current task, and hide the view when there is no task.'],
]
let autoMode: Record<Side, OverlayAutoMode> = saved.get('overlayAutoMode', { left: 'none', bottom: 'none' } as Record<Side, OverlayAutoMode>)
const hovered: Record<Side, boolean> = { left: false, bottom: false }
const focused: Record<Side, boolean> = { left: false, bottom: false }
const revealUntil: Record<Side, number> = { left: 0, bottom: 0 }
const hintTimer: Record<Side, number> = { left: 0, bottom: 0 }
const leaveTimer: Record<Side, number> = { left: 0, bottom: 0 }
const graceTimer: Record<Side, number> = { left: 0, bottom: 0 }
const unarm: Partial<Record<Side, () => void>> = {}

const overlaySubs = new Set<() => void>()
const overlayChanged = () => overlaySubs.forEach((f) => f())
/** For a title bar button (useSyncExternalStore): re-render on auto mode or transparency changes. */
export function subscribeOverlay(f: () => void) { overlaySubs.add(f); return () => overlaySubs.delete(f) }
export const getAutoMode = (side: Side) => autoMode[side]
export const isTransparentSide = (side: Side) =>
  !!document.querySelector('.dock')?.classList.contains('ovl-transparent') || !!sideBox(side)?.classList.contains('ovl-transparent-one')
/** OBTN Transparent (OverlayTabWidget::onAction 1180-1185), for one specific side's title bar button. */
export function toggleTransparentSide(side: Side) {
  sideBox(side)?.classList.toggle('ovl-transparent-one')
  evaluate(side)
}

/** OverlayTabWidget::checkAutoHide (OverlayWidgets.cpp 1264-1303): whether this side should
 *  currently be collapsed, absent the DockOverlayAutoView non-3D-view case (we only have the
 *  3D view, which always "AllowsOverlayOnHover") and the maximized-view case (no MDI here). */
function autoHideWanted(side: Side): boolean {
  const mode = autoMode[side]
  if (mode === 'none') return false
  if (mode === 'autohide') return true
  const editing = !!getState().task // stand-in for isInEdit(): the Tasks panel open
  if (mode === 'editshow') return !editing
  if (mode === 'taskshow') return isTransparentSide(side) ? false : !editing
  return editing // edithide
}
/** OverlayManager::Private::onTimer's per-widget decision (OverlayManager.cpp 630-709), without
 *  its 200 ms poll: hover/focus/task changes call this directly instead. */
function evaluate(side: Side) {
  if (!floating(groupOf(SIDE_PANEL[side]))) return
  const box = sideBox(side)
  if (!box) return
  const hot = hovered[side] || focused[side] || Date.now() < revealUntil[side]
  box.classList.toggle('ovl-collapsed', autoHideWanted(side) && !hot)
  overlayChanged()
}
/** OverlayManager.cpp:1031 (setRevealTime): keep a just-revealed panel up for a bit even if the
 *  mouse isn't over it, and re-evaluate right as the grace period lapses (there's no poll to catch it). */
function grace(side: Side) {
  revealUntil[side] = Date.now() + REVEAL_GRACE
  clearTimeout(graceTimer[side])
  graceTimer[side] = window.setTimeout(() => evaluate(side), REVEAL_GRACE + 20)
}
/** The title bar's auto mode menu (OverlayTabWidget::onAction's "OBTN AutoMode" case, 1157-1174). */
export function setOverlayAutoMode(side: Side, mode: OverlayAutoMode) {
  if (autoMode[side] === mode) return
  autoMode = { ...autoMode, [side]: mode }
  saved.set('overlayAutoMode', autoMode)
  grace(side)
  evaluate(side)
}
// EditShow/EditHide/TaskShow react to the Tasks panel opening or closing.
let lastTask: Task | null = null
subscribe(() => {
  const t = getState().task
  if (t === lastTask) return
  lastTask = t
  evaluate('left')
  evaluate('bottom')
})

/** OverlayProxyWidget::hitTest (OverlayWidgets.cpp 107-227), simplified: hovering the collapsed
 *  hint strip for DockOverlayHintDelay reveals it (DockOverlayActivateOnHover's default is on;
 *  there's no preference here to turn that off and fall back to click-to-reveal). */
function onHintHover(side: Side) {
  clearTimeout(hintTimer[side])
  hintTimer[side] = window.setTimeout(() => { grace(side); evaluate(side) }, HINT_DELAY)
}
/** Wire up one overlaid side's auto-hide: hover/focus collapse state (OverlayTabWidget::enterEvent/
 *  leaveEvent, 1305-1317), armed only while that side is actually floating. */
function armAutoHide(side: Side) {
  if (!floating(groupOf(SIDE_PANEL[side]))) return // overlay was toggled off again before this rAF ran
  const box = sideBox(side)
  if (!box || unarm[side]) return
  box.classList.add('ovl-auto')
  box.dataset.ovlSide = side
  const onEnter = () => {
    hovered[side] = true
    clearTimeout(leaveTimer[side])
    if (box.classList.contains('ovl-collapsed')) onHintHover(side)
    else evaluate(side)
  }
  const onLeave = () => {
    hovered[side] = false
    clearTimeout(hintTimer[side])
    leaveTimer[side] = window.setTimeout(() => evaluate(side), HINT_DELAY)
  }
  const onFocusIn = () => { focused[side] = true; evaluate(side) }
  const onFocusOut = () => { focused[side] = false; leaveTimer[side] = window.setTimeout(() => evaluate(side), HINT_DELAY) }
  box.addEventListener('mouseenter', onEnter)
  box.addEventListener('mouseleave', onLeave)
  box.addEventListener('focusin', onFocusIn)
  box.addEventListener('focusout', onFocusOut)
  unarm[side] = () => {
    box.removeEventListener('mouseenter', onEnter)
    box.removeEventListener('mouseleave', onLeave)
    box.removeEventListener('focusin', onFocusIn)
    box.removeEventListener('focusout', onFocusOut)
    box.classList.remove('ovl-auto', 'ovl-collapsed')
    delete box.dataset.ovlSide
  }
  grace(side) // OverlayManager.cpp:1031: a freshly-overlaid panel starts revealed, not collapsed
  evaluate(side)
}
function disarmAutoHide(side: Side) {
  unarm[side]?.()
  delete unarm[side]
  clearTimeout(hintTimer[side]); clearTimeout(leaveTimer[side]); clearTimeout(graceTimer[side])
  hovered[side] = false; focused[side] = false
}
/** The hint strip's CSS geometry (css-overlay.css), exported so chrome.tsx cites the same numbers. */
export const OVERLAY_HINT = { trigger: HINT_TRIGGER, size: HINT_SIZE }

/** Std_ToggleBottomPanels (Ctrl+0): hide or show the bottom dock area. */
export function toggleBottomPanels() {
  const g = dock?.getPanel('report')?.group as any
  if (g?.api?.setVisible) g.api.setVisible(!g.api.isVisible)
}
/** Show a panel; a hidden dock window (the Selection view) joins the left group first. */
export function showPanel(id: string) {
  if (dock && !dock.getPanel(id) && id === 'selection') {
    dock.addPanel({ id, component: id, title: 'Selection View', position: { referencePanel: 'model', direction: 'within' } })
  }
  // The Tasks dock shows while a task dialog is open (Control().showDialog), tabbed with Model.
  if (dock && !dock.getPanel(id) && id === 'tasks') {
    dock.addPanel({ id, component: id, title: 'Tasks', position: { referencePanel: 'model', direction: 'within' } })
  }
  // A dock closed from its title bar comes back where MainWindow first put it (View > Panels).
  const HOME: Record<string, [string, string]> = { model: ['Model', 'left'], report: ['Report View', 'below'], checks: ['Checks', 'below'], console: ['Console', 'below'] }
  if (dock && !dock.getPanel(id) && HOME[id]) {
    const [title, dir] = HOME[id]
    const near = dir === 'below' ? ['report', 'checks', 'console'].map((p) => dock!.getPanel(p)).find(Boolean) : undefined
    dock.addPanel({ id, component: id, title, position: near ? { referencePanel: near.id, direction: 'within' } : { referencePanel: 'view3d', direction: dir as 'left' | 'below' } })
  }
  dock?.getPanel(id)?.api.setActive()
}
function titleView() {
  // Closing the window (below) removes this panel; the next opened project brings it back,
  // as FreeCAD's own MDI area sits empty with no document open until one is opened again.
  if (dock && !dock.getPanel('view3d')) { dock.addPanel({ id: 'view3d', component: 'view3d', title: '3D view' }); windowChanged() }
  const slug = getState().slug
  dock?.getPanel('view3d')?.api.setTitle(slug ? `${slug} : 1` : '3D view')
}
/** Windows menu (Workbench.cpp's "&Windows"): this UI has exactly one document window, the 3D
 *  view tab, so Std_ActivateNextWindow/PrevWindow/TileWindows/CascadeWindows (which need two or
 *  more) stay disabled; Close and Close All both just close that one tab, as FreeCAD closes the
 *  (only) document window. Std_Windows (DlgActivateWindow) lists it; macro.tsx's WindowsTask.
 *  A tiny pub-sub (as overlayChanged/subscribeOverlay above) so chrome.tsx's menu re-renders
 *  when the tab opens or closes, which isn't itself part of the zustand store. */
const windowSubs = new Set<() => void>()
const windowChanged = () => windowSubs.forEach((f) => f())
export function subscribeWindow(f: () => void) { windowSubs.add(f); return () => windowSubs.delete(f) }
export const hasOpenWindow = () => !!dock?.getPanel('view3d')
export function closeActiveWindow() { dock?.getPanel('view3d')?.api.close(); windowChanged() } // Std_CloseActiveWindow
export const closeAllWindows = closeActiveWindow // Std_CloseAllWindows

// ── Std_RecentFiles (File menu): recently opened projects, newest first — the same `saved`-backed
// pattern as macro.tsx's recentMacros, for Recent Macros. DlgSettingsGeneral.ui's "Recent File List
// Size" default is 4 (WindowParameter RecentFiles, GetInt("RecentFiles", 4)), not Recent Macros' 12. ──
/** RecentFilesAction's visibleItems: General > Size of recent file list (RecentFiles, 4). */
const recentFilesMax = () => saved.get('recentFilesSize', 4)
export const recentFiles = () => saved.get<string[]>('recentFiles', [])
/** RecentFilesAction's Clear Recent Files: asks first ("Clear the list of recent files?", No by default). */
export function clearRecentFiles() {
  if (confirm('Clear the list of recent files?')) saved.set('recentFiles', [])
}
function pushRecentFile(slug: string) {
  saved.set('recentFiles', [slug, ...recentFiles().filter((n) => n !== slug)].slice(0, recentFilesMax()))
}

// ── loading ──────────────────────────────────────────────────────────────────
export async function start() {
  await loadProjects()
  connect()
}

export async function loadProjects() {
  try {
    const { projects } = await api.projects()
    setState({ projects })
    const s = getState()
    const want = [decodeURIComponent(location.hash.slice(1)), s.slug, saved.get<string | null>('slug', null),
      (projects.find((p) => p.assembly) ?? projects[0])?.slug].find((x) => x && projects.some((p) => p.slug === x))
    if (want && want !== s.slug) await openProject(want)
    if (!projects.length) report('warn', 'No projects yet. Add a projects folder with `cad serve DIR`.')
  } catch (e) {
    lostServer(() => loadProjects())
  }
}

// ── the connection to cad serve ──────────────────────────────────────────────
let retry = 0
/** cad serve went away (restarting, or stopped): say so, keep what's shown, try again. */
function lostServer(again: () => void) {
  if (!getState().offline) report('warn', `Can't reach cad serve at ${location.host}; retrying…`)
  setState({ offline: true })
  clearTimeout(retry)
  retry = window.setTimeout(again, 2000)
}
function foundServer() {
  if (!getState().offline) return
  setState({ offline: false })
  report('msg', 'Connected to cad serve again')
}
/** After a reconnect: everything may have changed while we weren't listening. */
function refreshAll() {
  loadProjects()
  if (getState().slug) { loadScene(); loadChecks(); loadStatus(); loadLog(); loadHistory() }
}

export async function openProject(slug: string) {
  setState({ slug, scene: null, sceneError: null, checks: null, status: null, log: [], selected: [], preselected: null,
    prePoint: null, hidden: [], task: null, undo: [], redo: [], unselectable: [], view: {}, treeFilter: null })
  saved.set('slug', slug)
  pushRecentFile(slug)
  history.replaceState(null, '', '#' + encodeURIComponent(slug))
  document.title = `${slug} - cad-agent`
  titleView()
  report('msg', `Opened ${slug}`)
  lastGui = {}
  guiReady = false
  await Promise.all([loadScene(true), loadChecks(), loadStatus(), loadLog(), loadGui(), loadHistory()])
  publishGui() // also once on open, even if nothing above changed from the defaults
}

let loading = false, pending = false
export async function loadScene(fresh = false) {
  if (loading) { pending = true; return }
  const slug = getState().slug
  if (!slug) return
  loading = true
  setState({ building: true })
  const t0 = performance.now()
  try {
    const sc = await api.scene(slug)
    foundServer()
    if (slug !== getState().slug) return
    const prev = getState().scene
    // A new source, or the same source tessellated again (Deviation / AngularDeflection changed).
    if (fresh || !prev || sc.source_hash !== prev.source_hash || sc.written_utc !== prev.written_utc) {
      const names = new Set(sc.bodies.map((b) => b.name))
      setState((s) => ({ scene: sc, sceneError: null, selected: s.selected.filter((n) => names.has(n)),
        hidden: s.hidden.filter((n) => names.has(n)) }))
      view?.show(sc, !fresh && !!prev)
      report('log', `Scene: ${sc.bodies.length} bodies, ${sc.triangles} triangles (${((performance.now() - t0) / 1000).toFixed(1)} s)`)
    } else if (getState().sceneError) {
      setState({ sceneError: null })
    }
  } catch (e) {
    if (slug !== getState().slug) return
    if (unreachable(e)) { lostServer(() => refreshAll()); return }
    setState({ sceneError: msg(e) })
    report('err', getState().scene ? `Rebuild failed, showing the last good scene: ${msg(e)}` : `${slug} did not build: ${msg(e)}`)
  } finally {
    loading = false
    setState({ building: false })
    if (pending) { pending = false; loadScene() }
  }
}

async function loadInto<K extends 'checks' | 'status'>(key: K, get: (slug: string) => Promise<any>) {
  const slug = getState().slug
  if (!slug) return
  let v = null
  try { v = await get(slug) } catch { v = null }
  if (slug === getState().slug) setState({ [key]: v } as any)
}
export const loadChecks = () => loadInto('checks', api.checks)
export const loadStatus = () => loadInto('status', api.status)
export async function loadLog() {
  const slug = getState().slug
  if (!slug) return
  try {
    const { entries } = await api.log(slug, 300)
    if (slug === getState().slug) setState({ log: entries })
  } catch { /* no log yet */ }
}
/** GET /api/history: the Document's undo/redo journal — the one source for Edit > Undo/Redo and
 *  the toolbar's dropdowns, shared with an agent in a terminal (DlgUndoRedo.cpp). */
export async function loadHistory() {
  const slug = getState().slug
  if (!slug) return
  try {
    const { undo, redo } = await api.history(slug)
    if (slug === getState().slug) setState({ undo, redo })
  } catch { /* no history yet */ }
}

// ── live updates ─────────────────────────────────────────────────────────────
let designTimer = 0
function connect() {
  const es = new EventSource('/api/events')
  let opened = false
  es.onopen = () => {
    setState({ live: true })
    // `cad gui` changes made before this stream was listening (while loading or away): take
    // the server's copy again; guiSynced keeps it from being echoed back.
    void loadGui()
    if (opened || getState().offline) { // the stream came back: catch up
      foundServer(); refreshAll()
      // and republish the session-only state in full (the server may have missed what we sent
      // while away); hidden/unselectable/view_props stay marked, as loadGui above takes the
      // server's copy of those: the agent may have changed them while we weren't listening.
      lastGui = { hidden: lastGui.hidden, unselectable: lastGui.unselectable, view: lastGui.view }
      publishGui()
    }
    opened = true
  }
  es.onerror = () => setState({ live: false })
  es.onmessage = (m) => {
    let ev: any
    try { ev = JSON.parse(m.data) } catch { return }
    if (ev.type === 'projects') { loadProjects(); return }
    if (ev.slug !== getState().slug) return
    switch (ev.type) {
      case 'design':
        clearTimeout(designTimer)
        designTimer = window.setTimeout(() => { loadScene(); loadStatus() }, 250)
        break
      case 'scene': loadScene(); break
      case 'checks': loadChecks(); break
      case 'verify': loadStatus(); break
      // The journal changed: our own undo/redo, the agent's `cad undo`/`cad redo`, or a new change.
      case 'history': loadHistory(); break
      case 'log': setState((s) => ({ log: [...s.log, ...ev.entries].slice(-500) })); break
      case 'busy': setState({ busy: ev.busy ?? [] }); break
      case 'checked':
        loadChecks(); loadStatus()
        if (ev.exit > 2) report('err', `Check could not run: ${ev.error ?? `exit ${ev.exit}`}`)
        break
      case 'verifyed':
        loadStatus(); loadChecks()
        report(ev.exit === 0 ? 'msg' : 'warn', ev.exit === 0 ? 'Verify: PASS' : `Verify: exit ${ev.exit}`)
        break
      case 'gui': guiEventHandler?.(ev); break // `cad gui …`: commands.ts registers the handler
    }
  }
}

// ── `cad gui`: publish our state for the agent, and apply the agent's `cad gui` commands ──
// commands.ts (which imports this file) registers the Std_View*/Selection handler here,
// rather than this file importing commands.ts back for it.
let guiEventHandler: ((ev: any) => void) | null = null
export function onGuiEvent(f: (ev: any) => void) { guiEventHandler = f }
// cmdreg.ts registers its listCommands snapshot here, the same pattern as onGuiEvent above, so
// this file never imports cmdreg.ts back (it already imports this file for actions like getView).
let commandList: (() => CommandInfo[]) | null = null
export function onCommandList(f: () => CommandInfo[]) { commandList = f }

/** On open: `hidden`, the per-body view overrides (`view_props`) and `unselectable` are persisted
 *  server-side (like a FreeCAD document's ViewProvider state); selection, preselection and
 *  the open task aren't, so those start empty regardless (see openProject, above). */
async function loadGui() {
  const slug = getState().slug
  if (!slug) return
  try {
    const g = await api.gui(slug)
    if (slug !== getState().slug) return
    // The camera (`view`) is the agent's or a prior tab's, not ours to adopt.
    setState({ hidden: g.hidden ?? [], unselectable: g.unselectable ?? [], view: (g.view_props ?? {}) as Record<string, Partial<ViewProps>> })
    guiSynced()
    guiReady = true
  } catch { /* /api/gui not up yet, or nothing saved for this project: start empty, as already set */ }
}

// What we last told the server, by field, so a debounced publish only sends what changed.
// Reference/value equality is enough to detect that: setState always gives a touched field
// a new array/object (or primitive value), and leaves an untouched one exactly as it was.
let lastGui: Partial<{ selected: string[]; subSel: string[]; preselected: string | null; hidden: string[]; unselectable: string[];
  task: string | null; view: State['view']; cameraPreset: string | null; ortho: boolean; commands: CommandInfo[]; cameraNode: string | null }> = {}
let guiTimer = 0
/** loadGui has read this project's saved hidden/unselectable/view_props. Until it has, publishing
 *  those would write openProject's empty defaults over what was saved (out/gui.json). */
let guiReady = false
/** Visibility, selectability and view properties that came from the server (loaded, or a
 *  `cad gui` show/hide/set applied here) are already there: mark them sent, so a publish never
 *  echoes a stale copy over a change the agent made in between. */
export function guiSynced() { const s = getState(); lastGui.hidden = s.hidden; lastGui.unselectable = s.unselectable; lastGui.view = s.view }
subscribe(() => { clearTimeout(guiTimer); guiTimer = window.setTimeout(publishGui, 150) })

const taskLabel = (t: Task | null) => t && (t.body ? `${t.kind}:${t.body}` : t.kind)
function publishGui() {
  const slug = getState().slug
  if (!slug) return
  const s = getState()
  // `commands` isn't part of GuiState (api.ts) yet; a non-literal value with extra fields still
  // satisfies api.setGui's Partial<GuiState> parameter structurally, so this needs no api.ts edit.
  const patch: Partial<GuiState> & { commands?: CommandInfo[] } = {}
  // Gui::Selection: (object, subname) pairs — a body picked whole by name, else its elements.
  if (s.selected !== lastGui.selected || s.subSel !== lastGui.subSel) {
    lastGui.selected = s.selected; lastGui.subSel = s.subSel
    patch.selected = [...s.subSel, ...s.selected.filter((b) => !s.subSel.some((x) => x.startsWith(b + '.')))]
  }
  if (s.preselected !== lastGui.preselected) patch.preselected = lastGui.preselected = s.preselected
  if (guiReady && s.hidden !== lastGui.hidden) patch.hidden = lastGui.hidden = s.hidden
  if (guiReady && s.unselectable !== lastGui.unselectable) patch.unselectable = lastGui.unselectable = s.unselectable
  const task = taskLabel(s.task)
  if (task !== lastGui.task) patch.task = lastGui.task = task
  // The per-body overrides go whole (view_props), the camera on its own (view).
  if (guiReady && s.view !== lastGui.view) patch.view_props = lastGui.view = s.view
  if (s.cameraPreset !== lastGui.cameraPreset || s.ortho !== lastGui.ortho) {
    lastGui.cameraPreset = s.cameraPreset; lastGui.ortho = s.ortho
    patch.view = { camera: s.cameraPreset, projection: s.ortho ? 'ortho' : 'persp' }
  }
  // cmdreg.ts's registry (name/label/enabled per command): selection etc. change `enabled`, so
  // this is computed fresh on every publish and only sent when the JSON actually differs.
  const commands = commandList?.()
  if (commands && JSON.stringify(commands) !== JSON.stringify(lastGui.commands)) patch.commands = lastGui.commands = commands
  if (s.cameraNode !== lastGui.cameraNode) (patch as Record<string, unknown>).camera_node = lastGui.cameraNode = s.cameraNode
  if (Object.keys(patch).length) api.setGui(slug, patch).catch(() => { /* best effort; the next change retries */ })
}

// ── selection and visibility ─────────────────────────────────────────────────
let anchor: string | null = null
const allNames = () => getState().scene?.bodies.map((b) => b.name) ?? []

/** Select an object, or one of its faces, edges or vertices (`sub`), as FreeCAD does:
 *  a click replaces the selection, Cmd/Ctrl-click adds or removes. */
/** Part's selection gates (CommandFilter.cpp): with Vertex/Edge/Face Selection on, only that kind
 *  of element may be preselected or selected; anything else is refused (SelectionSingleton). */
const gateAllows = (name: string, sub: string | null) => {
  const gate = getState().selFilter
  return !gate || !!sub?.toLowerCase().startsWith(gate)
}
export function select(name: string | null, additive = false, sub: string | null = null, point: number[] | null = null) {
  if (name && !gateAllows(name, sub)) return
  if (name) anchor = name
  if (name && sub && point) setState((s) => ({ subPts: { ...s.subPts, [`${name}.${sub}`]: point } }))
  const before = getState()
  setState((s) => {
    if (!name) return s.selected.length || s.subSel.length ? { selected: [], subSel: [] } : {}
    if (sub) {
      const ref = `${name}.${sub}`
      if (!additive) return { selected: [name], subSel: [ref] }
      const subSel = s.subSel.includes(ref) ? s.subSel.filter((r) => r !== ref) : [...s.subSel, ref]
      const selected = [...new Set([...s.selected.filter((n) => n !== name || subSel.some((r) => r.startsWith(n + '.'))), ...subSel.map((r) => r.split('.')[0])])]
      return { selected, subSel }
    }
    const others = s.subSel.filter((r) => !r.startsWith(name + '.')) // a whole object, not its parts
    if (additive) return { selected: s.selected.includes(name) ? s.selected.filter((n) => n !== name) : [...s.selected, name], subSel: others }
    return s.selected.length === 1 && s.selected[0] === name && !s.subSel.length ? {} : { selected: [name], subSel: [] }
  })
  if (isRecording()) recordSelectChange(before, name, sub, additive)
}
/** Gui.Selection.addSelection/clearSelection, as `select()` above would record them: a plain
 *  click replaces (clear, then select), Cmd/Ctrl-click adds. An additive click that *removes*
 *  from the selection has no `cad gui` line (the vocabulary only adds or clears); skipped. */
function recordSelectChange(before: State, name: string | null, sub: string | null, additive: boolean) {
  if (!name) { if (before.selected.length || before.subSel.length) recordGui('clear'); return }
  const ref = sub ? `${name}.${sub}` : name
  if (!additive) { recordGui('clear'); recordGui('select', ref); return }
  const already = sub ? before.subSel.includes(ref) : before.selected.includes(name)
  if (!already) recordGui('select', ref)
}
export function preselect(name: string | null, point: number[] | null, sub: string | null = null) {
  // SelectionSingleton::setPreselect: a refused element shows "Not allowed: doc.obj.sub " and the
  // 3D view's ForbiddenCursor instead of being preselected.
  const view = document.querySelector('.view3d') as HTMLElement | null
  if (name && !gateAllows(name, sub)) {
    if (view) view.style.cursor = 'not-allowed'
    const msg = `Not allowed: ${getState().slug}.${name}.${sub ?? ''} `
    if (getState().gateMsg !== msg || getState().preselected) setState({ gateMsg: msg, preselected: null, prePoint: null, preSub: null })
    return
  }
  if (view?.style.cursor === 'not-allowed') view.style.cursor = ''
  if (getState().gateMsg) setState({ gateMsg: null })
  const s = getState(), preSub = name && sub ? `${name}.${sub}` : null
  if (s.preselected !== name || s.prePoint !== point || s.preSub !== preSub) setState({ preselected: name, prePoint: point, preSub })
}
/** Std_ToggleVisibility: flips each listed object (default: the selection). Also Std_ToggleObjects
 *  (commands.ts's toggleAll passes every name); either way, split into Show/Hide `cad gui` lines. */
export function toggleVisibility(names?: string[]) {
  const s = getState()
  const list = names ?? s.selected
  if (!list.length) return
  const hidden = new Set(s.hidden)
  const shown: string[] = [], hiddenNow: string[] = []
  list.forEach((n) => (hidden.has(n) ? (hidden.delete(n), shown.push(n)) : (hidden.add(n), hiddenNow.push(n))))
  setState({ hidden: [...hidden] })
  if (shown.length) recordGui('show', ...shown)
  if (hiddenNow.length) recordGui('hide', ...hiddenNow)
}
/** Shift-click in the tree: everything from the last clicked row to this one. */
export function selectRange(name: string) {
  const names = allNames(), b = names.indexOf(name)
  const a = anchor && names.includes(anchor) ? names.indexOf(anchor) : b
  setState({ selected: names.slice(Math.min(a, b), Math.max(a, b) + 1) })
}
export function selectAll() { // Std_SelectAll
  const names = allNames()
  setState({ selected: names })
  if (names.length) { recordGui('clear'); recordGui('select', ...names) }
}
export function selectVisible() { // Std_SelectVisibleObjects
  const names = allNames().filter((n) => !getState().hidden.includes(n))
  setState({ selected: names })
  if (names.length) { recordGui('clear'); recordGui('select', ...names) }
}
export function showSelection() { // Std_ShowSelection
  const names = getState().selected
  setState((s) => ({ hidden: s.hidden.filter((n) => !s.selected.includes(n)) }))
  if (names.length) recordGui('show', ...names)
}
export function hideSelection() { // Std_HideSelection
  const names = getState().selected
  setState((s) => ({ hidden: [...new Set([...s.hidden, ...s.selected])] }))
  if (names.length) recordGui('hide', ...names)
}
export function showAll() { // Std_ShowObjects
  const names = allNames()
  setState({ hidden: [] })
  if (names.length) recordGui('show', ...names)
}
export function hideAll() { // Std_HideObjects
  const names = allNames()
  setState({ hidden: names })
  if (names.length) recordGui('hide', ...names)
}
export const toggleAll = () => toggleVisibility(allNames()) // Std_ToggleObjects
export const setDrawStyle = (drawStyle: DrawStyle) => setState({ drawStyle })
export const toggleCube = () => setState((s) => ({ cube: !s.cube })) // Std_ViewNavigationCube
export function setOrtho(flag: boolean) {
  setState({ ortho: flag })
  view?.setOrtho(flag)
  recordGui('view', flag ? 'ortho' : 'persp')
}

// ── tasks ────────────────────────────────────────────────────────────────────
export function openTask(kind: Task['kind'], body: string, other?: string) {
  // Editing tasks are about one part; the rest use the selection as it is.
  setState((s) => ({ task: { kind, body, other }, ...(kind === 'params' || kind === 'placement' || kind === 'transform' ? { selected: [body], subSel: [] } : {}) }))
  showPanel('tasks')
}
/** Double-click: the object's edit mode. A part with parameters edits those; a
 *  plain shape gets FreeCAD's default edit mode for one, Transform. */
/** Std_Edit with the user edit mode (Std_UserEditMode): Default opens the part's own
 *  editor (its parameters, or Transform for a plain shape); Transform opens Transform.
 *  Cutting and Color have no editor here, as for many FreeCAD objects. */
export function editDefault(name: string) {
  const s = getState(), b = s.scene?.bodies.find((x) => x.name === name)
  if (s.editMode === 'transform') return openTask('transform', name)
  if (s.editMode === 'cutting' || s.editMode === 'color') {
    return report('warn', `${name} has no ${s.editMode === 'cutting' ? 'Cutting' : 'Color'} edit mode; switch Edit > Edit mode to Default or Transform`)
  }
  openTask(b?.part && Object.values(b.params ?? {}).some((p) => p.editable) ? 'params' : 'transform', name)
}
export function closeTask() {
  setState({ task: null })
  showPanel('model')
  const tasks = dock?.getPanel('tasks') // and the Tasks dock goes again (no dialog to show)
  if (tasks) dock?.removePanel(tasks)
}

// ── edits: each is one cad command; the backend journals it for undo/redo ────
export function placementOf(b: Body): Placement {
  const p = b.placement ?? {}
  return { move: (p.move ?? [0, 0, 0]) as Vec3, turn: (p.turn ?? [0, 0, 0]) as Vec3, about: (p.about ?? b.about ?? [0, 0, 0]) as Vec3 }
}

export async function setParams(part: string, before: Record<string, unknown>, after: Record<string, unknown>, record = true, echo = true) {
  const slug = getState().slug
  if (!slug) return false
  const what = Object.entries(after).map(([k, v]) => `${k}=${v}`).join(' ')
  // PythonConsole echoing a GUI action (the Property editor here) as the Python it's
  // equivalent to; the console's own `set` command passes echo=false, having shown its own line.
  if (echo) consoleLog('in', `cad set ${part} ${what}`)
  try {
    const r = await api.set(slug, part, after)
    const d = r.data ?? {}
    // A value that breaks the build is not written; `changed` says it was.
    if (!d.changed) { report('err', `Not saved: cad set ${part} ${what}: ${resultText(r)}`); return false }
    const fails: unknown[] = d.failing ?? []
    report(fails.length ? 'warn' : 'msg', `${part}: ${what}${typeof d.mass_g === 'number' ? `, ${d.mass_g.toFixed(1)} g` : ''}, `
      + (fails.length ? `${fails.length} part gate${fails.length > 1 ? 's' : ''} not passing` : 'part gates pass'))
    if (record) recordLine(`cad set ${slug} ${part} ${what}`)
    return true
  } catch (e) {
    report('err', `cad set ${part} ${what}: ${msg(e)}`)
    return false
  }
}

// cad place's own --move=x,y,z syntax (console help: `place BODY --move=x,y,z [--turn=a,b,c] [--about=x,y,z]`).
const vec = (v: Vec3) => v.map((n) => Number(n.toPrecision(6))).join(',')

export async function place(body: string, before: Placement | null, after: Placement | null, record = true, echo = true) {
  const slug = getState().slug
  if (!slug) return false
  const argsText = after ? `--move=${vec(after.move)} --turn=${vec(after.turn)} --about=${vec(after.about)}` : '--reset'
  if (echo) consoleLog('in', `cad place ${body} ${argsText}`)
  try {
    const r = await api.place(slug, body, after)
    if (r.exit > 2) { report('err', `Not placed: cad place ${body}: ${resultText(r)}`); return false }
    if (r.exit === 1) report('warn', `${body} was placed, but a fit check fails: ${resultText(r)}`)
    if (record) recordLine(`cad place ${slug} ${body} ${argsText}`)
    return true
  } catch (e) {
    report('err', `cad place ${body}: ${msg(e)}`)
    return false
  }
}

/** Std_Undo: the backend's Document journal is the one undo stack, shared with an agent in a
 *  terminal — this UI no longer replays changes itself, just asks the server to step the journal
 *  and waits for the `history` SSE event (and `design`/`scene`) to show the result. `steps` > 1 is
 *  the toolbar dropdown (UndoAction, DlgUndoRedo.cpp): picking an entry walks back to it. */
export async function doUndo(steps?: number) {
  const slug = getState().slug
  if (!slug || !getState().undo.length) return
  try {
    const r = await api.undo(slug, steps)
    if (r.exit === 1) report('warn', `Can't undo: ${resultText(r)}`)
    else if (r.exit > 1) report('err', `Undo failed: ${resultText(r)}`)
  } catch (e) { report('err', `Undo: ${msg(e)}`) }
}
/** Std_Redo: see doUndo above (RedoAction/RedoDialog is its mirror). */
export async function doRedo(steps?: number) {
  const slug = getState().slug
  if (!slug || !getState().redo.length) return
  try {
    const r = await api.redo(slug, steps)
    if (r.exit === 1) report('warn', `Can't redo: ${resultText(r)}`)
    else if (r.exit > 1) report('err', `Redo failed: ${resultText(r)}`)
  } catch (e) { report('err', `Redo: ${msg(e)}`) }
}

export async function runCheck() {
  const slug = getState().slug
  if (!slug) return
  try { await api.check(slug); report('msg', 'Recomputing checks…') } catch (e) { report('err', `check: ${msg(e)}`) }
}
export async function runVerify() {
  const slug = getState().slug
  if (!slug) return
  try { await api.verify(slug); report('msg', 'Verifying (fresh rebuild)…') } catch (e) { report('err', `verify: ${msg(e)}`) }
}

// ── Std_SelBack / Std_SelForward: the selection history (Record Selection) ──────
let lastSel: SelEntry = { selected: [], subSel: [] }, stepping = false
subscribe(() => {
  const s = getState()
  if (s.selected === lastSel.selected && s.subSel === lastSel.subSel) return
  const prev = lastSel
  lastSel = { selected: s.selected, subSel: s.subSel }
  if (stepping || !s.tree.recordSelection || (!prev.selected.length && !prev.subSel.length)) return
  setState({ selHistory: { back: [...s.selHistory.back.slice(-49), prev], forward: [] } })
})
function stepSelection(from: 'back' | 'forward') {
  const s = getState(), list = s.selHistory[from]
  if (!list.length) return
  const target = list[list.length - 1], here = { selected: s.selected, subSel: s.subSel }
  const other = from === 'back' ? 'forward' : 'back'
  stepping = true
  setState({ selected: target.selected, subSel: target.subSel, selHistory: { [from]: list.slice(0, -1), [other]: [...s.selHistory[other], here] } as State['selHistory'] })
  stepping = false
}
export const selBack = () => stepSelection('back')
export const selForward = () => stepSelection('forward')
/** A Tree view action switch (TreeParams), kept between sessions. */
/** TreeParams set from Preferences > UI or the tree's Tree Settings menu. */
export function setTreeUI(patch: Partial<State['treeUI']>) {
  setState((s) => { const treeUI = { ...s.treeUI, ...patch }; saved.set('treeUI', treeUI); return { treeUI } })
}
export function setTreeOption(k: keyof State['tree'], on: boolean) {
  setState((s) => { const tree = { ...s.tree, [k]: on }; saved.set('tree', tree); return { tree } })
}
