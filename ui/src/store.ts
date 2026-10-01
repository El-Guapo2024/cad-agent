// One store for the whole UI. Panels read slices with useStore(selector);
// selectors must return stored values, not build new objects.
import { useSyncExternalStore } from 'react'
import type { Checks, LogEntry, Project, Scene, Status } from './api'
import { NAV_DEFAULTS, type NavPrefs, type NavStyleId } from './nav'
import { unitPrefs } from './quantity'
import { BACKGROUND_DEFAULTS, type BackgroundPrefs } from './background'

/** The report view's message types (Base::LogStyle): Message, Log, Warning, Error, Critical. */
export type Level = 'msg' | 'log' | 'warn' | 'err' | 'critical'
export type Message = { t: number; level: Level; text: string }
/** NotificationArea.cpp's NotificationItem: one row kept for the notification button/list. */
export type Notification = {
  id: number; t: number; level: 'warn' | 'err' | 'critical'; notifier: string; text: string
  unread: boolean
  notifying: boolean // still queued to appear in the pop-up balloon
  shown: boolean // currently on screen in the pop-up balloon
  repetitions: number
}
/** Preferences > Notification Area (PreferencePages/DlgSettingsNotificationArea.ui), User
 *  parameter:BaseApp/Preferences/NotificationArea; defaults are its ParameterObserver's
 *  GetBool/GetInt fallbacks, which run once at construction and so are the real effective ones. */
export type NotifyPrefs = {
  areaEnabled: boolean; popupEnabled: boolean
  maxDuration: number; minDuration: number // NotificationTime / MinimumOnScreenTime, seconds
  maxOpenNotifications: number; maxWidgetMessages: number
  autoRemoveUserNotifications: boolean
  notificationWidth: number
  hideWhenDeactivated: boolean; preventWhenInactive: boolean
  developerErrors: boolean; developerWarnings: boolean
}
export const NOTIFY_DEFAULTS: NotifyPrefs = {
  areaEnabled: true, popupEnabled: true, maxDuration: 20, minDuration: 5, maxOpenNotifications: 15,
  maxWidgetMessages: 1000, autoRemoveUserNotifications: true, notificationWidth: 800,
  hideWhenDeactivated: true, preventWhenInactive: true, developerErrors: false, developerWarnings: false,
}
export type Task = { kind: 'params' | 'placement' | 'transform' | 'measure' | 'mass' | 'clip' | 'info' | 'prefs' | 'units' | 'turntable' | 'shot' | 'align'
  // CAD Agent workbench tasks (agentwb.tsx): the cad CLI commands that had no UI yet.
  | 'check' | 'verify' | 'done' | 'rules' | 'cutlist' | 'tables' | 'tool' | 'bought' | 'render'
  // Macro menu (macro.tsx): DlgMacroRecord, DlgMacroExecute, its Edit button, Windows' DlgActivateWindow.
  | 'macroRecord' | 'macros' | 'macroEdit' | 'windows'
  // File menu (filemenu.tsx): Std_New (ask a name first; there's no Save As here) and Std_Open
  // (our project picker standing in for FreeCAD's native file-open dialog).
  | 'newDocument' | 'openDocument' | 'export' | 'appearance'
  // Tools menu (tools.tsx): Std_DlgParameter, Std_SceneInspector, Std_DependencyGraph. All three
  // are QDialogs/an MDI view in FreeCAD; here, like Std_UnitsCalculator and Std_DlgPreferences
  // above, they go through the one Tasks panel this UI has.
  | 'parameterEditor' | 'sceneInspector' | 'dependencyGraph'; body: string; other?: string }
/** GET /api/history: one entry of the backend's Document undo/redo journal, shared with an
 *  agent in a terminal — replaces a UI-local undo stack (actions.ts no longer replays changes). */
export type HistoryEntry = { id: string; name: string; by: 'ui' | 'agent'; t: number }
export type Workbench = 'design' | 'assembly' | 'inspection' | 'agent'
/** FreeCAD's draw styles that the viewer can show faithfully. */
export type DrawStyle = 'asis' | 'points' | 'wireframe' | 'hiddenline' | 'noshading' | 'shaded' | 'flatlines'
export type ClipAxis = { on: boolean; offset: number; flip: boolean }
/** Clipping's custom plane: its offset, the Direction fields, the plane's normal (the fields,
 *  or the view direction after View), and whether it follows the view. */
export type ClipView = { on: boolean; offset: number; dir: [number, number, number]; normal: [number, number, number]; adjust: boolean }
export type Clip = { x: ClipAxis; y: ClipAxis; z: ClipAxis; view: ClipView }
/** FreeCAD's navigation styles (src/Gui/Navigation/*NavigationStyle.cpp), all ported in nav.ts. */
export type NavStyle = NavStyleId
/** Std_UserEditMode: what double-click and "Toggle edit mode" open. */
export type EditMode = 'default' | 'transform' | 'cutting' | 'color'
/** Std_DlgPreferences > Navigation: the default camera orientation, for new views and Home. */
/** View/CornerCoordSystem and CornerCoordSystemSize (Preferences > Display > 3D View). */
export type Corner = { show: boolean; size: number }
/** Units/UserSchema, Decimals and FracInch (Preferences > General > Units). */
export type Units = { schema: number; decimals: number; denominator: number }
/** Preferences > Navigation > Navigation Cube (NaviCube group): steps by turn, corner, rotate to
 *  nearest, font, size, opacity when inactive, base colour, the small corner coordinate system
 *  (SoNaviCube's ShowCS, View3DSettings.cpp ShowCS). */
export type NaviCubePrefs = { stepByTurn: number; corner: 0 | 1 | 2 | 3; toNearest: boolean; font: string; size: number; inactiveOpacity: number; color: string; showCS: boolean }
// BaseColor: FreeCAD Light's own value (light.cfg NaviCube/BaseColor 0xF2F2F2FF), not the code's fallback.
export const NAVICUBE_DEFAULTS: NaviCubePrefs = { stepByTurn: 8, corner: 1, toNearest: true, font: '', size: 132, inactiveOpacity: 50, color: '#f2f2f2', showCS: true }
/** Where the cube sits: the nearest of three-viewport-gizmo's nine placements to cubePos
 *  (the corner, or whichever zone a drag with Movable Navigation Cube is currently over). */
export type CubePlace = `${'top' | 'center' | 'bottom'}-${'left' | 'center' | 'right'}`
/** NaviCube.cpp's relPos: the cube's continuous position within its padded travel area, 0..1
 *  each axis (the MoveNaviCube drag branch in mouseMoved, NaviCube.cpp:1246-1262). Unlike Coin
 *  (y=0 at the bottom), y=0 is the top here, matching the rest of this CSS-based port. */
export type CubePos = { x: number; y: number }
/** CubePlace's four corners as a CubePos, for callers (e.g. the Preferences corner radio) that
 *  only pick a corner; cubeLayout (viewer.ts) turns any CubePos into the nearest CubePlace. */
export const CORNER_POS: Record<0 | 1 | 2 | 3, CubePos> = { 0: { x: 0, y: 0 }, 1: { x: 1, y: 0 }, 2: { x: 0, y: 1 }, 3: { x: 1, y: 1 } }
/** The cube's current on-screen offset in px from whichever of CubePlace's edges are active
 *  (viewer.ts's cubeLayout); mirrored into state only so navicube.tsx's button box can track
 *  the cube without redoing that layout math itself. */
export type CubeOffset = { left: number; right: number; top: number; bottom: number }
/** Rotation Center Indicator: sphere size and colour with transparency (View/RotationCenterSize, RotationCenterColor). */
export type RotationCenterPrefs = { size: number; color: string; alpha: number }
/** Preferences > Display > 3D View > General: AxisLetterColor (also the FPS counter's colour),
 *  AxisXColor, AxisYColor, AxisZColor; axiscross.ts's AXIS_COLORS are these same defaults. */
export type AxisColors = { letter: string; x: string; y: string; z: string }
export const AXIS_COLOR_DEFAULTS: AxisColors = { letter: '#000000', x: '#cc3333', y: '#33cc33', z: '#3333cc' }
export type HomeView = 'Isometric' | 'Dimetric' | 'Trimetric' | 'Top' | 'Front' | 'Left' | 'Right' | 'Rear' | 'Bottom'
export type ConsoleLine = { t: number; kind: 'in' | 'out' | 'err'; text: string }
/** A Part object's view properties (ViewProviderPartExt, ViewProviderGeometryObject and
 *  ViewProviderDocumentObject), besides Visibility and Selectable. Colours are 0xRRGGBB. */
export type ViewProps = {
  displayMode: 'Flat Lines' | 'Shaded' | 'Wireframe' | 'Points'
  boundingBox: boolean
  showInTree: boolean
  /** ViewProviderDragger::ShowPlacement: the object's placement drawn as an axis cross. */
  showPlacement: boolean
  drawStyle: 'Solid' | 'Dashed' | 'Dotted' | 'Dashdot'
  lighting: 'One side' | 'Two side'
  lineColor: number
  lineWidth: number
  pointColor: number
  pointSize: number
  /** ShapeAppearance's diffuse colour; null keeps the material's colour. */
  shapeColor: number | null
  transparency: number
  onTop: 'Disabled' | 'Enabled' | 'Object' | 'Element'
  selectionStyle: 'Shape' | 'BoundBox'
  /** Percent of the body's bounding-box size (PropertyFloatConstraint, 0.01-100, step 0.01).
   *  Re-tessellates the body when it changes, same as angularDeflection below. */
  deviation: number
  /** Degrees (PropertyAngle, 1-180, step 0.05): how finely curved faces and edges are meshed. */
  angularDeflection: number
}
/** FreeCAD's defaults: Flat Lines, two-side lighting, 2 px lines and points (ViewParams),
 *  FreeCAD Light's line (#000000) and vertex (#191919) colours, no transparency, not on top,
 *  shape selection, and the Part preferences' own tessellation fallback (ViewProviderPartExt::
 *  loadParameter: MeshDeviation / MeshAngularDeflection, 28.65 deg is ~0.5 rad). */
export const VIEW_DEFAULTS: ViewProps = {
  displayMode: 'Flat Lines', boundingBox: false, showInTree: true, showPlacement: false, drawStyle: 'Solid', lighting: 'Two side',
  lineColor: 0x000000, lineWidth: 2, pointColor: 0x191919, pointSize: 2, shapeColor: null, transparency: 0, onTop: 'Disabled', selectionStyle: 'Shape',
  deviation: 0.2, angularDeflection: 28.65,
}
export const viewOf = (s: { view: Record<string, Partial<ViewProps>> }, name: string): ViewProps => ({ ...VIEW_DEFAULTS, ...s.view[name] })

export type State = {
  projects: Project[]
  slug: string | null
  scene: Scene | null
  sceneError: string | null
  building: boolean
  checks: Checks | null
  status: Status | null
  log: LogEntry[]
  busy: string[]
  live: boolean
  /** cad serve can't be reached; the UI retries and keeps the last scene. */
  offline: boolean
  selected: string[]
  preselected: string | null
  prePoint: number[] | null
  /** FreeCAD sub-elements, as "body.Face3", "body.Edge7", "body.Vertex2". */
  preSub: string | null
  subSel: string[]
  /** Where each sub-element was clicked (SelectionChanges' picked point), for Distance Free. */
  subPts: Record<string, number[]>
  /** What three-cad-viewer says about the edge or face under the mouse. */
  viewInfo: string
  /** MainWindow::showHints: the open tool's input hints (InputHintWidget); `%1` is where the keys go. */
  hints: { message: string; keys: string[] }[]
  hidden: string[]
  task: Task | null
  /** General > Size of toolbar icons (ToolbarIconSize, ToolBarManager's default 24). */
  toolbarIconSize: number
  /** Std_DlgPreferences: the Preferences dialog is open. */
  prefsOpen: boolean
  /** The backend's Document undo/redo journal (GET /api/history), newest first. */
  undo: HistoryEntry[]
  redo: HistoryEntry[]
  messages: Message[]
  notifications: Notification[]
  notifyPrefs: NotifyPrefs
  /** NotificationArea's tray icon: a pop-up was suppressed (window inactive) and not yet seen. */
  notifyMissed: boolean
  /** More items were queued than MaxOpenNotifications when the balloon was last (re)built. */
  notifyOverflow: boolean
  ortho: boolean
  workbench: Workbench
  drawStyle: DrawStyle
  cube: boolean
  /** Std_ToggleSelectability: objects clicks go through (the Selectable view property). */
  unselectable: string[]
  /** Each object's other view properties, where they differ from the defaults (VIEW_DEFAULTS). */
  view: Record<string, Partial<ViewProps>>
  selBoxes: boolean
  axes: boolean
  /** The tree's search box; null when closed. */
  treeFilter: string | null
  reportShow: Record<Level, boolean>
  /** Preferences > Report View > Include a timecode for each entry (checkShowReportTimecode). */
  reportTimecode: boolean
  reportCleared: number
  /** Std_ToggleClipPlane: the clipping planes, or null when off. */
  clip: Clip | null
  /** The visible width and height of the view, in mm (FreeCAD's status bar dimension). */
  viewSize: [number, number] | null
  consoleLines: ConsoleLine[]
  consoleDraft: string
  /** FreeCAD animates view changes (NavigationAnimation). */
  animate: boolean
  nav: NavStyle
  navPrefs: NavPrefs
  homeView: HomeView
  /** View/NewDocumentCameraScale (Preferences > Navigation): sphere diameter (mm) the camera
   *  fits on screen for new documents and the Home view. */
  newDocCameraScale: number
  corner: Corner
  axisColors: AxisColors
  /** View/ShowFPS (Preferences > Display > 3D View): frame rate shown at the lower left. */
  showFPS: boolean
  naviCube: NaviCubePrefs
  cubePlace: CubePlace
  cubePos: CubePos
  cubeOffset: CubeOffset
  rotationCenter: RotationCenterPrefs
  disableTouchTilt: boolean
  /** Preferences > Display > Colors: the 3D view's background, and the tree's colour for the object being edited. */
  background: BackgroundPrefs
  treeEditColor: string
  units: Units
  editMode: EditMode
  /** The Selection view's "Picked object list": everything under the cursor at the last pick. */
  pickList: boolean
  picked: { body: string; sub: string | null }[]
  /** The tree's "Show hidden items": objects whose Show In Tree is false. */
  treeShowHidden: boolean
  /** View > Toolbars: which toolbars show. */
  toolbars: Record<string, boolean>
  /** Std_ToggleToolBarLock: toolbars fixed in place, their handles hidden. */
  toolbarLock: boolean
  /** View > Status bar. */
  statusBar: boolean
  /** View > Tree view actions (TreeParams): SyncView, SyncSelection, PreSelection, RecordSelection. */
  tree: { syncView: boolean; syncSelection: boolean; preSelection: boolean; recordSelection: boolean }
  /** Tree view actions > Collapse/Expand: the document's node folded. */
  treeCollapsed: boolean
  /** Std_SelBack / Std_SelForward: the recorded selections. */
  selHistory: { back: SelEntry[]; forward: SelEntry[] }
  /** The camera as View3DInventorViewer's "GetCamera" writes it, published for `cad gui state`. */
  cameraNode: string | null
  /** Part_SelectFilter: the selection gate (Vertex/Edge/Face Selection), or none. */
  selFilter: 'vertex' | 'edge' | 'face' | null
  /** SelectionSingleton's "Not allowed: …" when the gate refuses a preselection. */
  gateMsg: string | null
  /** Std_FreezeViews: the frozen cameras ("GetCamera" text), Restore View 1…50. */
  frozenViews: string[]
  /** The last named Std_View (or Home) direction shown (`iso`, `front`, `dimetric`, …), for
   *  `cad gui`'s camera field; null until one is chosen, or stale after a free orbit. */
  cameraPreset: string | null
  /** Std_DlgMacroRecord: the macro being recorded, or null (macro.tsx owns the line buffer). */
  recordingMacro: string | null
  /** Preferences > Macro > Gui Commands (DlgSettingsMacro.ui): Record GUI commands (RecordGui) and
   *  Record as comment (GuiAsComment), both on by default, so `cad gui …` lines go in as comments. */
  recordGuiCommands: boolean
  guiAsComment: boolean
}
export type SelEntry = { selected: string[]; subSel: string[] }

export const saved = {
  get<T>(k: string, d: T): T {
    try { const v = localStorage.getItem('cadui.' + k); return v === null ? d : JSON.parse(v) } catch { return d }
  },
  set(k: string, v: unknown) {
    try { localStorage.setItem('cadui.' + k, JSON.stringify(v)) } catch { /* private window */ }
  },
}

let state: State = {
  projects: [], slug: null, scene: null, sceneError: null, building: false, checks: null, status: null,
  log: [], busy: [], live: false, offline: false, selected: [], preselected: null, prePoint: null, preSub: null, subSel: [], subPts: {}, viewInfo: '', hints: [], hidden: [], task: null,
  undo: [], redo: [], messages: [], notifications: [], notifyPrefs: { ...NOTIFY_DEFAULTS, ...saved.get<Partial<NotifyPrefs>>('notifyPrefs', {}) }, notifyMissed: false, notifyOverflow: false,
  ortho: true, workbench: 'agent', drawStyle: 'asis', cube: true,
  unselectable: [], view: {}, selBoxes: false, axes: saved.get('axes', false), treeFilter: null,
  reportShow: { msg: true, log: true, warn: true, err: true, critical: true, ...saved.get<Partial<Record<Level, boolean>>>('reportShow', {}) },
  reportTimecode: saved.get('report.timecode', true), reportCleared: 0,
  clip: null, viewSize: null, consoleLines: [], consoleDraft: '', animate: saved.get('animate', true), nav: saved.get<NavStyle>('nav', 'cad'),
  navPrefs: { ...NAV_DEFAULTS, ...saved.get<Partial<NavPrefs>>('navPrefs', {}) }, homeView: saved.get<HomeView>('homeView', 'Trimetric'), newDocCameraScale: saved.get('newDocCameraScale', 100), corner: saved.get<Corner>('corner', { show: true, size: 10 }), axisColors: { ...AXIS_COLOR_DEFAULTS, ...saved.get<Partial<AxisColors>>('axisColors', {}) }, showFPS: saved.get('showFPS', false), naviCube: { ...NAVICUBE_DEFAULTS, ...saved.get<Partial<NaviCubePrefs>>('naviCube', {}) }, cubePlace: (['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const)[saved.get<Partial<NaviCubePrefs>>('naviCube', {}).corner ?? 1], cubePos: saved.get<CubePos>('cubePos', CORNER_POS[saved.get<Partial<NaviCubePrefs>>('naviCube', {}).corner ?? 1]), cubeOffset: { left: 10, right: 10, top: 10, bottom: 22 }, rotationCenter: saved.get<RotationCenterPrefs>('rotationCenter', { size: 5, color: '#ff0000', alpha: 0.2 }), disableTouchTilt: saved.get('disableTouchTilt', true), background: { ...BACKGROUND_DEFAULTS, ...saved.get<Partial<BackgroundPrefs>>('background', {}) }, treeEditColor: saved.get('treeEditColor', '#00abff'), units: saved.get<Units>('units', { schema: 0, decimals: 2, denominator: 8 }), editMode: saved.get<EditMode>('editMode', 'default'), pickList: false, picked: [], treeShowHidden: false,
  toolbars: saved.get('toolbars', {}), toolbarLock: saved.get('toolbarLock', false), statusBar: saved.get('statusBar', true),
  tree: { syncView: true, syncSelection: true, preSelection: true, recordSelection: true, ...saved.get('tree', {}) }, selHistory: { back: [], forward: [] }, toolbarIconSize: saved.get('toolbarIconSize', 24), prefsOpen: false, cameraNode: null, selFilter: null, gateMsg: null, frozenViews: [], treeCollapsed: false,
  cameraPreset: null,
  recordingMacro: null, recordGuiCommands: saved.get('recordGuiCommands', true), guiAsComment: saved.get('guiAsComment', true),
}
const subs = new Set<() => void>()
// Quantities are written in the user's unit system wherever they show (UnitsApi).
Object.assign(unitPrefs, state.units)

export const getState = () => state
export function setState(patch: Partial<State> | ((s: State) => Partial<State>)) {
  state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) }
  Object.assign(unitPrefs, state.units)
  subs.forEach((f) => f())
}
export function subscribe(f: () => void) {
  subs.add(f)
  return () => { subs.delete(f) }
}
export function useStore<T>(sel: (s: State) => T): T {
  return useSyncExternalStore(subscribe, () => sel(state))
}

// notifications.tsx registers its pushNotification hook here, the same callback pattern as
// actions.ts's onGuiEvent, so this file never imports notifications.tsx back.
let notifyHook: ((level: Level, text: string) => void) | null = null
export function onNotify(f: (level: Level, text: string) => void) { notifyHook = f }

/** A line in the report view. */
export function report(level: Level, text: string) {
  setState((s) => ({ messages: [...s.messages.slice(-499), { t: Date.now(), level, text }] }))
  notifyHook?.(level, text) // NotificationAreaObserver::sendLog
}

/** A line in the console (kind 'in' = a command; 'out'/'err' = its output): the typed
 *  commands and `cad serve`'s own log both use this, and so does a GUI action echoed as
 *  the `cad` command it's equivalent to (PythonConsole echoing a GUI action as Python). */
export function consoleLog(kind: ConsoleLine['kind'], text: string) {
  setState((s) => ({ consoleLines: [...s.consoleLines.slice(-300), { t: Date.now(), kind, text }] }))
}

