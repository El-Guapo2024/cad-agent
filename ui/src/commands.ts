// FreeCAD's view, visibility and selection commands, named after their FreeCAD ids.
import { consoleLog, getState, report, saved, setState, viewOf, type Corner, type EditMode, type HomeView, type NavStyle, type Units, type ViewProps } from './store'
import { getView, guiSynced, onGuiEvent, openTask, place, placementOf, recordGui, muteEcho, setOrtho, setParams, setViewProps, showPanel } from './actions'
import { api, resultText, type CadResult, type Vec3 } from './api'
// Type-only: cmdreg.ts imports this file for its commands' functions, so this stays a type import
// (erased at build) rather than a real one, the same way actions.ts avoids importing this file back.
import type { RegCommand } from './cmdreg'

const selected = () => getState().selected
const flip = (list: string[], items: string[]) => {
  const s = new Set(list)
  items.forEach((n) => (s.has(n) ? s.delete(n) : s.add(n)))
  return [...s]
}

const HOME: Record<HomeView, Parameters<NonNullable<ReturnType<typeof getView>>['viewDir']>[0]> = {
  Isometric: 'iso', Dimetric: 'dimetric', Trimetric: 'trimetric', Top: 'top', Front: 'front', Left: 'left', Right: 'right', Rear: 'rear', Bottom: 'bottom',
}
/** Std_ViewHome (View3DInventorViewer::viewHome): turn to the default camera orientation
 *  while moving to the middle of the model, then fit all. */
export const viewHome = () => getView()?.home(HOME[getState().homeView])
export function setHomeView(v: HomeView) {
  setState({ homeView: v })
  saved.set('homeView', v)
}
// Same quaternions as viewDir('dimetric'/'trimetric') (FreeCAD src/Gui/Camera.cpp); going
// through viewDir (not orient directly) is what lets attachView track the camera preset.
export const viewDimetric = () => getView()?.viewDir('dimetric')
export const viewTrimetric = () => getView()?.viewDir('trimetric')
/** Std_ViewRotateLeft / Right: a quarter turn about the view direction (View3DPy.cpp). */
export const rotateLeft = () => getView()?.turn('z', -90)
export const rotateRight = () => getView()?.turn('z', 90)
export const zoomIn = () => getView()?.zoomIn() // Std_ViewZoomIn
export const zoomOut = () => getView()?.zoomOut() // Std_ViewZoomOut
export function storeView() { // Std_StoreWorkingView
  getView()?.storeView()
  report('msg', 'Working view stored. End brings it back.')
}
export const recallView = () => getView()?.recallView() // Std_RecallWorkingView

/** "SetCamera" (View3DInventor::onMsg): switch to the node's projection, then take on its camera. */
export function applyCamera(text: string) {
  setOrtho(/\bOrthographicCamera\b/.test(text))
  getView()?.setCamera(text)
}
/** Std_ViewIvIssueCamPos: "GetCamera" without its #Inventor line, newlines as spaces, to the
 *  Report view; a recording macro gets the line that brings it back (FreeCAD adds
 *  Gui.SendMsgToActiveView("SetCamera …"); here `cad gui view PROJECT '<camera>'`). */
export function issueCameraPosition() {
  const cam = getView()?.getCamera()
  if (!cam) return
  const text = cam.slice(cam.indexOf('\n')).replace(/\n/g, ' ')
  report('msg', text)
  recordGui('view', `'${text.trim()}'`)
}
/** Std_FreezeViews (CommandView.cpp): Freeze View keeps the camera as "Restore View N" (Ctrl+N for
 *  the first nine), Clear Views drops them, at most 50 (maxViews); Save/Load Views write and read
 *  the .cam file onSaveViews/onRestoreViews do. */
export function freezeView() {
  const cam = getView()?.getCamera()
  if (cam) setState((s) => (s.frozenViews.length < 50 ? { frozenViews: [...s.frozenViews, cam] } : {}))
}
export const clearViews = () => setState({ frozenViews: [] })
export function restoreView(i: number) {
  const cam = getState().frozenViews[i]
  if (cam) applyCamera(cam)
}
const xmlAttr = (t: string) => t.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
export function saveViews() {
  const views = getState().frozenViews
  if (!views.length) return
  const lines = views.map((v) => `    <Camera settings="${xmlAttr(v.split('\n').slice(1).join(' '))}"/>`)
  const xml = `<?xml version='1.0' encoding='utf-8'?>\n<FrozenViews SchemaVersion="1">\n  <Views Count="${views.length}">\n${lines.join('\n')}\n  </Views>\n</FrozenViews>\n`
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([xml], { type: 'application/xml' })), download: 'views.cam' })
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}
export function loadViews() {
  if (getState().frozenViews.length && !confirm('Importing the restored views would clear the already stored views.\nContinue?')) return
  const input = Object.assign(document.createElement('input'), { type: 'file', accept: '.cam' })
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const doc = new DOMParser().parseFromString(await file.text(), 'application/xml')
    if (doc.querySelector('parsererror')) return report('err', `Cannot open file '${file.name}'.`)
    const views = [...doc.querySelectorAll('FrozenViews > Views > Camera')].map((c) => c.getAttribute('settings') ?? '').filter(Boolean).slice(0, 50)
    setState({ frozenViews: views })
  }
  input.click()
}
/** Std_Copy: FreeCAD copies the selected objects; here their names (object, or object.element,
 *  one per line) go to the clipboard as text, which a terminal (or the agent) can take. */
export function copySelection() {
  const s = getState()
  const names = [...s.subSel, ...s.selected.filter((b) => !s.subSel.some((x) => x.startsWith(b + '.')))]
  if (names.length) navigator.clipboard?.writeText(names.join('\n')).catch(() => report('warn', 'Copy: the clipboard is not available here'))
}
/** View > Document Window > Fullscreen (Std_ViewFullscreen, F11): the 3D view alone fills the
 *  screen; Docked (V, D) brings it back. */
export const viewIsFullscreen = () => !!document.fullscreenElement?.classList.contains('view3d')
export function viewFullscreen() {
  if (viewIsFullscreen()) void document.exitFullscreen()
  else void (document.querySelector('.view3d') as HTMLElement | null)?.requestFullscreen?.()
}
export function viewDocked() { if (viewIsFullscreen()) void document.exitFullscreen() }

/** The navigation cube's flat buttons (NaviCube.cpp): a step of 360°/NaviStepByTurn (clamped to
 *  4..36; 45° by default) about the screen axes, and a half turn for the backside button. */
const naviStep = () => 360 / Math.min(36, Math.max(4, getState().naviCube.stepByTurn))
export const navi = {
  north: () => getView()?.turn('x', naviStep()),
  south: () => getView()?.turn('x', -naviStep()),
  east: () => getView()?.turn('y', -naviStep()),
  west: () => getView()?.turn('y', naviStep()),
  rollLeft: () => getView()?.turn('z', -naviStep()),
  rollRight: () => getView()?.turn('z', naviStep()),
  backside: () => getView()?.turn('y', 180),
}

export const toggleAxisCross = () => setState((s) => ({ axes: !s.axes })) // Std_AxisCross
export const toggleBoundingBox = () => setState((s) => ({ selBoxes: !s.selBoxes })) // Std_SelBoundingBox
/** Std_ToggleTransparency: all to 0 if any is transparent, else all to ToggleTransparency (70). */
export function toggleTransparency() {
  const s = getState()
  if (!s.selected.length) return
  const one = s.selected.some((n) => viewOf(s, n).transparency > 0)
  setViewProps(s.selected, { transparency: one ? 0 : 70 })
}
export function toggleSelectability() { // Std_ToggleSelectability
  if (selected().length) setState((s) => ({ unselectable: flip(s.unselectable, s.selected), selected: [] }))
}
export function randomColor() { // Std_RandomColor
  if (!selected().length) return
  // Std_RandomColor: a new ShapeAppearance colour for each selected object.
  for (const n of selected()) setViewProps([n], { shapeColor: Math.floor(Math.random() * 0xffffff) })
}
/** Std_TreeSelectAllInstances: every body built from the same part file. */
export function selectInstances() {
  const s = getState()
  const parts = new Set(s.scene?.bodies.filter((b) => s.selected.includes(b.name)).map((b) => b.part))
  setState({ selected: s.scene?.bodies.filter((b) => b.part && parts.has(b.part)).map((b) => b.name) ?? [] })
}
/** Std_TreeSelection (T, G): bring the selection into view in the tree. */
export function gotoSelection() {
  showPanel('model')
  requestAnimationFrame(() => document.querySelector('.trow.sel')?.scrollIntoView({ block: 'nearest' }))
}
/** Std_BoxSelection (Shift+B): drag a rectangle; the parts inside it are selected. */
export const boxSelection = () => getView()?.boxSelect((found) => setState({ selected: found }))
export const properties = () => showPanel('model') // Std_Properties (Alt+Return)
export function fullscreen() { // Std_MainFullscreen (Alt+F11)
  if (document.fullscreenElement) document.exitFullscreen()
  else document.documentElement.requestFullscreen?.()
}
export const saveImage = () => openTask('shot', '') // Std_ViewScreenShot: FreeCAD's Save Image dialog
export function searchObjects() { // the tree's Search Objects
  showPanel('model')
  setState({ treeFilter: '' })
}
/** Std_Measure: the measurement task, which follows the selection (TaskMeasure). */
export const measure = () => openTask('measure', '')
export const canMeasure = () => !!getState().scene
/** Std_AlignToSelection: look straight at the selected planar face. */
export function alignToSelection() {
  const ref = getState().subSel.find((r) => /\.Face\d+$/.test(r))
  if (!ref || !getView()?.alignTo(ref)) report('warn', 'Align to selection: select a planar face')
}
/** Std_MassProperties, for the selected parts. */
export function massProperties() {
  if (selected().length) openTask('mass', selected()[0])
  else report('warn', 'Mass properties: select one or more parts')
}

export const boxZoom = () => getView()?.boxZoom() // Std_ViewBoxZoom (Ctrl+B)

/** Std_ToggleClipPlane: FreeCAD's Clipping dialog, as a task. Starts with a Z
 *  plane through the middle of the model. */
export function clipping() {
  const s = getState(), bb = s.scene?.bbox
  const mid = (i: number) => (bb ? Math.round(((bb[0][i] + bb[1][i]) / 2) * 100) / 100 : 0)
  // Clipping::Clipping: every plane off, the offsets at the middle of the scene's box, the
  // custom plane at the box's middle height looking along +Z.
  if (!s.clip) setState({ clip: { x: { on: false, offset: mid(0), flip: false }, y: { on: false, offset: mid(1), flip: false }, z: { on: false, offset: mid(2), flip: false },
    view: { on: false, offset: mid(2), dir: [0, 0, 1], normal: [0, 0, 1], adjust: false } } })
  openTask('clip', s.selected[0] ?? '')
}

// ── the console ──────────────────────────────────────────────────────────────
const say = consoleLog
const value = (v: string): unknown =>
  /^-?\d+(\.\d+)?(e-?\d+)?$/i.test(v) ? Number(v) : v === 'true' ? true : v === 'false' ? false : v.replace(/^["']|["']$/g, '')
const triple = (v: string | undefined, d: Vec3): Vec3 => (v ? (v.split(',').map(Number) as Vec3) : d)

/** The console's commands: the same `cad` commands the agent runs, minus the slug. */
export async function runConsole(line: string) {
  // Only the line's own synchronous effects (select, view, fit) are muted; once it awaits the
  // server, whatever the person does meanwhile echoes as usual.
  muteEcho(true)
  let run: Promise<void>
  try { run = runConsoleLine(line) } finally { muteEcho(false) }
  await run
}
async function runConsoleLine(line: string) {
  const text = line.trim()
  if (!text) return
  say('in', text)
  const [cmd, ...args] = text.replace(/^cad\s+/, '').split(/\s+/)
  const s = getState(), slug = s.slug
  if (!slug) return say('err', 'no project open')
  try {
    if (cmd === 'help') say('out', 'check | verify | set PART k=v ... | place BODY --move=x,y,z [--turn=a,b,c] [--about=x,y,z] | place BODY --reset | measure A B | select NAME ... | view iso|front|top|right|rear|bottom|left | fit'
      + ' | anything else (mass, status, export, cutlist, render, …) runs as that cad subcommand, e.g. mass PART or export PART --format step')
    else if (cmd === 'check') { await api.check(slug); say('out', 'checking…') }
    else if (cmd === 'verify') { await api.verify(slug); say('out', 'verifying with a fresh rebuild…') }
    else if (cmd === 'set') {
      const [part, ...kv] = args
      const body = s.scene?.bodies.find((b) => b.part === part)
      const after = Object.fromEntries(kv.map((a) => [a.slice(0, a.indexOf('=')), value(a.slice(a.indexOf('=') + 1))]))
      const before = Object.fromEntries(Object.keys(after).map((k) => [k, body?.params?.[k]?.value]))
      // echo=false: the typed line above already shows as a command (`say('in', text)`).
      say((await setParams(part, before, after, true, false)) ? 'out' : 'err', `set ${part} ${kv.join(' ')}`)
    } else if (cmd === 'place') {
      const [name, ...opts] = args
      const b = s.scene?.bodies.find((x) => x.name === name)
      if (!b) return say('err', `no body ${name}`)
      const o = Object.fromEntries(opts.map((a) => a.replace(/^--/, '').split('=')))
      const cur = placementOf(b)
      const after = 'reset' in o ? null : { move: triple(o.move, cur.move), turn: triple(o.turn, cur.turn), about: triple(o.about, cur.about) }
      say((await place(name, b.placement ? cur : null, after, true, false)) ? 'out' : 'err', `place ${text.slice(text.indexOf(name))}`)
    } else if (cmd === 'measure') {
      const r = await api.measure(slug, args[0], args[1]), d = r.data ?? {}
      if (typeof d.min_distance_mm === 'number' || d.interferes) {
        say('out', d.interferes ? `interfere: ${d.overlap_mm3} mm³ overlap` : `minimum distance ${d.min_distance_mm} mm`)
        getView()?.showMeasure(d.points ?? null)
      } else say('err', resultText(r))
    } else if (cmd === 'select') setState({ selected: args.filter((n) => s.scene?.bodies.some((b) => b.name === n)) })
    else if (cmd === 'view') getView()?.viewDir(args[0] as never)
    else if (cmd === 'fit') getView()?.fitAll()
    // Anything else: the same cad subcommand through POST /api/cad, with the open project put
    // in when the command takes one and it wasn't typed (`mass post` → `cad mass SLUG post`).
    else printCadResult(await api.cad(slug, NO_PROJECT.has(cmd) || args[0] === slug || cmd.startsWith('-') ? [cmd, ...args] : [cmd, slug, ...args]))
  } catch (e) {
    say('err', String(e))
  }
}

/** cad commands that take no project argument (`cad tables`, `cad rules`, …). */
const NO_PROJECT = new Set(['ls', 'init', 'tables', 'rules', 'tool', 'help'])

/** FreeCAD's console prints what the command prints; here, the same text `cad` prints in a
 *  terminal (the server asks for it with --with-text), so the person sees what the agent sees.
 *  Without it: the JSON result's summary, or its other top-level fields. */
function printCadResult(r: CadResult) {
  if (r.text?.trim()) { for (const line of r.text.trimEnd().split('\n')) say(r.exit === 0 ? 'out' : 'err', line); return }
  if (r.exit !== 0) return say('err', resultText(r))
  const d = r.data ?? {}
  const fields = Object.entries(d).filter(([k]) => k !== 'error').map(([k, v]) => `${k}=${typeof v === 'object' && v !== null ? JSON.stringify(v) : v}`).join(' ')
  say('out', typeof d.summary === 'string' ? d.summary : fields || 'ok')
}

/** Std_SendToPythonConsole (Ctrl+Shift+P): the selected names go into the console line. */
export function sendToConsole() {
  setState((s) => ({ consoleDraft: [s.consoleDraft, ...s.selected].filter(Boolean).join(' ') }))
  showPanel('console')
}

/** File > Export: the selected part as STEP or STL, through `cad export`. */
export async function exportPart(format: 'step' | 'stl') {
  const s = getState(), b = s.scene?.bodies.find((x) => x.name === s.selected[0])
  if (!s.slug || !b?.part) return report('warn', 'Export: select one made part (bought parts come as vendor files)')
  report('msg', `Exporting ${b.part} as ${format.toUpperCase()}…`)
  try {
    const r = await api.export(s.slug, b.part, format)
    if (r.exit !== 0 || !r.data?.path) return report('err', `Export failed: ${resultText(r)}`)
    const a = document.createElement('a')
    a.href = api.fileUrl(s.slug, r.data.path)
    a.download = String(r.data.path).split('/').pop() ?? `${b.part}.${format}`
    a.click()
    report('msg', `Exported ${r.data.path}`)
  } catch (e) {
    report('err', `Export failed: ${e}`)
  }
}
export const documentInfo = () => openTask('info', '') // Std_ProjectInfo
export const unitsCalculator = () => openTask('units', '') // Std_UnitsCalculator
/** Std_Alignment: two objects selected, the first stays, the second is moved onto it. */
export function alignment() {
  const sel = selected()
  if (sel.length !== 2) return report('warn', 'Align: select exactly two objects, the fixed one first, then the one to move')
  openTask('align', sel[1], sel[0])
}
export const demoMode = () => openTask('turntable', '') // Std_DemoMode (View turntable)
export const preferences = () => setState({ prefsOpen: true }) // Std_DlgPreferences: the modal dialog (prefs.tsx)
/** Std_BoxElementSelection (Shift+E): the faces and edges wholly inside a rectangle. */
export const boxElementSelection = () => getView()?.boxElements((refs, whole) => setState({ subSel: refs, selected: [...new Set([...whole, ...refs.map((r) => r.split('.')[0])])] }))
export function setNav(nav: NavStyle) {
  setState({ nav })
  saved.set('nav', nav)
}
/** UnitsApi::setSchema / setDecimals / setDenominator, kept as FreeCAD keeps them in Units. */
export function setUnits(patch: Partial<Units>) {
  setState((s) => { const units = { ...s.units, ...patch }; saved.set('units', units); return { units } })
}
/** View/CornerCoordSystem and CornerCoordSystemSize. */
export function setCorner(patch: Partial<Corner>) {
  setState((s) => { const corner = { ...s.corner, ...patch }; saved.set('corner', corner); return { corner } })
}
/** Std_ClarifySelection (G, G): a menu of everything under the cursor. */
export const clarifySelection = () => getView()?.clarifyAtCursor()
/** Std_UserEditMode: what editing an object from the tree opens. */
export function setEditMode(editMode: EditMode) { setState({ editMode }); saved.set('editMode', editMode) }

// ── `cad gui …`: the agent's commands, applied exactly as the matching FreeCAD command
// would be, each also logged to the Report view like the activity feed logs other cad commands.
type GuiEvent = { slug: string; cmd: 'select' | 'show' | 'hide' | 'view' | 'fit' | 'say' | 'clear' | 'set' | 'run'; args: string[]; props?: Record<string, unknown> }
const guiLog = (line: string) => report('log', `cad gui ${line}`)

// cmdreg.ts (which imports this file for its commands' functions) registers the command registry
// here, the same callback pattern as actions.ts's onGuiEvent below, so this file never imports
// cmdreg.ts back.
let commandRegistry: ((name: string) => RegCommand | undefined) | null = null
export function onCommandRegistry(f: (name: string) => RegCommand | undefined) { commandRegistry = f }

/** view args: front, rear, top, bottom, left, right, iso, dimetric, trimetric, home, ortho,
 *  persp; reuses the same calls as the View menu/toolbar/keys (Std_View*, Std_ViewHome). */
function applyView(name: string) {
  if (/\b(Orthographic|Perspective)Camera\b/.test(name)) return applyCamera(name)
  if (name === 'home') return viewHome()
  if (name === 'ortho') return setOrtho(true)
  if (name === 'persp') return setOrtho(false)
  getView()?.viewDir(name as Parameters<NonNullable<ReturnType<typeof getView>>['viewDir']>[0])
}

// ViewProps' camelCase keys as FreeCAD names them on the object's ViewObject, plus the two
// object properties (Visibility, Selectable) that live outside ViewProps here.
const FREECAD_PROP: Record<string, string> = {
  displayMode: 'DisplayMode', boundingBox: 'BoundingBox', showInTree: 'ShowInTree', showPlacement: 'ShowPlacement', drawStyle: 'DrawStyle',
  lighting: 'Lighting', lineColor: 'LineColor', lineWidth: 'LineWidth', pointColor: 'PointColor', pointSize: 'PointSize',
  shapeColor: 'ShapeColor', transparency: 'Transparency', onTop: 'OnTopWhenSelected', selectionStyle: 'SelectionStyle',
  deviation: 'Deviation', angularDeflection: 'AngularDeflection', visibility: 'Visibility', selectable: 'Selectable',
}
const hexColor = (n: number) => '#' + n.toString(16).padStart(6, '0')
const fmtProp = ([k, v]: [string, unknown]) => {
  const name = FREECAD_PROP[k] ?? k
  return `${name}=${typeof v === 'number' && name.endsWith('Color') ? hexColor(v) : v}`
}

/** `cad gui set PROJECT BODY ShapeColor=#rrggbb Transparency=50 DisplayMode=Wireframe …`
 *  (FreeCAD ViewObject names); `props` arrives already as this app's Partial<ViewProps>, plus
 *  optionally `visibility`/`selectable` (not part of ViewProps, so handled separately here). */
function applySet(body: string, props: Record<string, unknown>) {
  const p = props as Partial<ViewProps> & { visibility?: boolean; selectable?: boolean }
  const { visibility, selectable, ...rest } = p
  if (Object.keys(rest).length) setViewProps([body], rest) // ShapeAppearance etc.: the View tab
  if (visibility !== undefined) setState((s) => ({ hidden: visibility ? s.hidden.filter((n) => n !== body) : [...new Set([...s.hidden, body])] }))
  if (selectable !== undefined) setState((s) => ({ unselectable: selectable ? s.unselectable.filter((n) => n !== body) : [...new Set([...s.unselectable, body])] }))
  guiLog(`set ${body} ${Object.entries(props).map(fmtProp).join(' ')}`)
}

function applyGuiEvent(ev: GuiEvent) {
  const { cmd, args } = ev
  if (cmd === 'select') {
    // Gui.Selection.addSelection: adds whole objects, or "body.Face3"-style sub-elements.
    setState((s) => {
      const subAdd = args.filter((a) => a.includes('.'))
      const subSel = [...new Set([...s.subSel, ...subAdd])]
      const selected = [...new Set([...s.selected, ...args.filter((a) => !a.includes('.')), ...subAdd.map((a) => a.split('.')[0])])]
      return { selected, subSel }
    })
    guiLog(`select ${args.join(' ')}`)
  } else if (cmd === 'clear') {
    setState({ selected: [], subSel: [] }) // Gui.Selection.clearSelection()
    guiLog('clear')
  } else if (cmd === 'show' || cmd === 'hide') {
    setState((s) => ({ hidden: cmd === 'hide' ? [...new Set([...s.hidden, ...args])] : s.hidden.filter((n) => !args.includes(n)) }))
    guiSynced()
    guiLog(`${cmd} ${args.join(' ')}`)
  } else if (cmd === 'view') {
    applyView(args[0])
    guiLog(`view ${args[0]}`)
  } else if (cmd === 'fit') {
    getView()?.fitAll(args[0] === 'selection' ? getState().selected : undefined) // Std_ViewFitAll / Std_ViewFitSelection
    guiLog(args.length ? `fit ${args.join(' ')}` : 'fit')
  } else if (cmd === 'say') {
    report('msg', args.join(' ')) // Console.PrintMessage: the text itself is the line
  } else if (cmd === 'set') {
    applySet(args[0], ev.props ?? {})
    guiSynced()
  } else if (cmd === 'run') {
    // `cad gui run PROJECT COMMAND [ARGS…]`: Gui.runCommand(COMMAND, 0) by another name —
    // CommandManager::runCommandByName looks the command up and calls invoke(0), which silently
    // no-ops when isActive() is false; here that's said in the Report view instead, since an
    // agent can't see a greyed-out menu entry.
    const [name, ...rest] = args
    const found = commandRegistry?.(name)
    if (!found) report('warn', `cad gui run: unknown command '${name}'`)
    else if (!found.isEnabled()) guiLog(`run ${name}: disabled, not run`)
    else { found.run(rest); guiLog(`run ${args.join(' ')}`) }
  }
}
// actions.ts owns the EventSource; it calls back in here so it doesn't have to import this
// file (which already imports actions.ts) just for Std_View*/Selection logic.
onGuiEvent(applyGuiEvent)
