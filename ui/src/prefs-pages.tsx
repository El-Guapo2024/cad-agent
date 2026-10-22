// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/CommandCompleter.cpp: 2022 Zheng Lei (realthunder)
//   src/Gui/Dialogs/DlgKeyboardImp.cpp: 2005 Werner Mayer
//   src/Gui/OverlayParams.py: 2022 Zheng Lei (realthunder)
//   src/Gui/PreferencePages/DlgSettings3DViewImp.cpp: 2002 Jürgen Riegel
//   src/Gui/PreferencePages/DlgSettingsAdvanced.cpp: 2020 Zheng Lei (realthunder)
//   src/Gui/PreferencePages/DlgSettingsCacheDirectory.cpp: 2021 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsDocumentImp.cpp: 2002 Jürgen Riegel
//   src/Gui/PreferencePages/DlgSettingsEditor.cpp: 2004 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsGeneral.cpp: 2004 Werner Mayer; 2023 FreeCAD Project Association
//   src/Gui/PreferencePages/DlgSettingsLightSources.cpp: 2023 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsMacroImp.cpp: 2002 Jürgen Riegel
//   src/Gui/PreferencePages/DlgSettingsNavigation.cpp: 2002 Jürgen Riegel
//   src/Gui/PreferencePages/DlgSettingsNotificationArea.cpp: 2023 Abdullah Tahiri
//   src/Gui/PreferencePages/DlgSettingsPythonConsole.cpp: 2022 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsReportView.cpp: 2004 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsSelection.cpp: 2021 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsUI.cpp: 2009 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsViewColor.cpp: 2009 Werner Mayer
//   src/Gui/PreferencePages/DlgSettingsWorkbenchesImp.cpp: 2020 Chris Hennes; 2023 FreeCAD Project Association
//   src/Gui/TreeParams.py: 2022 Zheng Lei (realthunder)
//   src/Gui/Widgets.cpp: 2004 Werner Mayer
//   No copyright line in the file: src/Gui/Dialogs/DlgKeyboard.ui, src/Gui/PreferencePages/DlgSettingsPDF.cpp,
//       src/Gui/PreferencePages/DlgSettings3DView.ui, src/Gui/PreferencePages/DlgSettingsCacheDirectory.ui,
//       src/Gui/PreferencePages/DlgSettingsDocument.ui, src/Gui/PreferencePages/DlgSettingsEditor.ui,
//       src/Gui/PreferencePages/DlgSettingsGeneral.ui, src/Gui/PreferencePages/DlgSettingsLightSources.ui,
//       src/Gui/PreferencePages/DlgSettingsMacro.ui, src/Gui/PreferencePages/DlgSettingsNavigation.ui,
//       src/Gui/PreferencePages/DlgSettingsNotificationArea.ui, src/Gui/PreferencePages/DlgSettingsPDF.ui,
//       src/Gui/PreferencePages/DlgSettingsPythonConsole.ui, src/Gui/PreferencePages/DlgSettingsReportView.ui,
//       src/Gui/PreferencePages/DlgSettingsSelection.ui, src/Gui/PreferencePages/DlgSettingsUI.ui,
//       src/Gui/PreferencePages/DlgSettingsViewColor.ui, src/Gui/PreferencePages/DlgSettingsWorkbenches.ui
// The Preferences pages, one component each: the form of the page's Qt Designer file (uiforms.ts, drawn by qtform.tsx) and, by the
// widgets' object names, what each one does here. A widget that is not bound shows what the real FreeCAD shows for it in a fresh
// profile, greyed out; one that is bound with a `why` says in its tool tip why it is greyed out. The Advanced page has no .ui in
// FreeCAD (DlgSettingsAdvanced.cpp makes it in code, from OverlayParams.py), so its form is made here the same way.
import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import * as THREE from 'three'
import { QtForm, cls, type Bindings } from './qtform'
import { COMMAND_CATEGORY, FORMS, KEYBOARD_CATEGORIES, type UiForm, type UiItem } from './uiforms'
import { NAV_STYLES, ORBIT_STYLES, type NavPrefs, type OrbitStyle } from './nav'
import { CORNER_POS, EDITOR_COLORS, getState, saved, saveNaviCube, setState, useStore, type AxisColors, type HomeView, type NaviCubePrefs, type NavStyle, type OverlayPrefs, type RotationCenterPrefs, type WbPrefs } from './store'
import { setCorner, setHomeView, setNav, setUnits } from './commands'
import { ANIMATION_CURVES, editorStyle, setEditorPrefs, setOrtho, setOverlayPrefs, setTreeOption, setTreeUI } from './actions'
import { setNotifyPrefs } from './notifications'
import { api, type CacheInfo } from './api'
import { gradientMesh, type BackgroundPrefs } from './background'
import { LightRig, azimuthElevationToDirection, directionToAzimuthElevation, type Light, type LightPrefs } from './lights'
import { allWorkbenches, ContextMenu } from './chrome'
import { Icon } from './icons'
import { cmdIcon } from './cmdicons'
import { listCommands } from './cmdreg'
import { commandsByShortcut, defaultAccel, eventSeq, nativeText, resetAllShortcuts, setShortcut, shortcutOf } from './keymap'
import { messageBox } from './msgbox'
import { ANGLE, LENGTH, QuantityBox } from './qsb'
import * as quantity from './quantity'

const na = (why: string) => ({ why })
/** DlgSettingsNavigation's Orbit style combo lists them as Rounded Arcball, Trackball, Trackball Classic, Free Turntable, Turntable. */
const ORBIT_ITEMS = [4, 1, 3, 2, 0] as const
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** DlgSettingsGeneral.ui: Language and Number Format, Application, Preference Packs. What applies here works (the unit system and its
 *  decimals, the toolbar icon size, the recent file list); the rest is shown as FreeCAD shows it in a fresh profile. */
export function GeneralPage() {
  const units = useStore((s) => s.units), toolbarIconSize = useStore((s) => s.toolbarIconSize)
  const [recent, setRecent] = useState<number>(() => saved.get('recentFilesSize', 4))
  const multLen = !!quantity.SCHEMAS.find((x) => x.num === units.schema)?.multLen
  const one = 'projects here are not FreeCAD documents: there is one language, one theme and no preference packs'
  const bind: Bindings = {
    Languages: na('the workbench has the one language'),
    comboBox_UnitSystem: { value: units.schema, opts: quantity.SCHEMAS.map((x) => [x.num, x.description] as const), set: (schema: number) => setUnits({ schema }) },
    spinBoxDecimals: { value: units.decimals, min: 1, max: 16, set: (decimals: number) => setUnits({ decimals }) },
    checkBox_projectUnitSystemIgnore: na('projects here carry no unit system of their own'),
    fractionalInchLabel: { hide: !multLen },
    comboBox_FracInch: { hide: !multLen, value: units.denominator, opts: [2, 4, 8, 16, 32, 64, 128].map((d) => [d, `1/${d}"`] as const), set: (denominator: number) => setUnits({ denominator }) },
    UseLocaleFormatting: na('numbers are written with the unit system, in the browser\'s way'),
    SubstituteDecimal: na('numbers are written with the unit system, in the browser\'s way'),
    themesCombobox: na('there is one theme here (FreeCAD Light)'),
    // DlgSettingsGeneral enables this label only where Std_AddonMgr exists, and it opens the Addon Manager
    moreThemesLabel: { off: true, why: 'there are no addons here (Tools > Addon Manager is n/a too)' },
    toolbarIconSize: { value: toolbarIconSize, opts: [[16, 'Small (16px)'], [24, 'Medium (24px)'], [32, 'Large (32px)'], [48, 'Extra large (48px)']], set: (v: number) => { setState({ toolbarIconSize: v }); saved.set('toolbarIconSize', v) } },
    treeMode: na('the tree and the property view are one panel here'),
    RecentFiles: { value: recent, set: (v: number) => { setRecent(v); saved.set('recentFilesSize', v) } },
    tiledBackground: na('there is no main window background to tile'),
    EnableCursorBlinking: na('the browser decides how the text cursor blinks'),
    SplashScreen: na('there is no splash screen'),
    ActivateOverlay: na('the overlay panels are always on'),
    ComboBoxWheelEventFilter: na('a browser has its own rules for the wheel over a field'),
    FineGrainedRecompute: na('a part is rebuilt as a whole by the CAD worker'),
    PreferencePacks: na(one), ImportConfig: na(one), SaveNewPreferencePack: na(one), ManagePreferencePacks: na(one), RevertToSavedConfig: na(one),
  }
  return <QtForm form={FORMS.general} bind={bind} />
}

/** DlgSettingsSelection.ui: Viewport Selection Behavior (each enable with its colour, the pick radius) and Tree Selection Behavior. */
export function SelectionPage() {
  const tree = useStore((s) => s.tree), sp = useStore((s) => s.selPrefs)
  const setSel = (patch: Partial<typeof sp>) => { const selPrefs = { ...getState().selPrefs, ...patch }; saved.set('selPrefs', selPrefs); setState({ selPrefs }) }
  const bind: Bindings = {
    checkBoxPreselection: { value: sp.enablePre, set: (enablePre: boolean) => setSel({ enablePre }) },
    HighlightColor: { value: sp.preColor, set: (preColor: string) => setSel({ preColor }) },
    checkBoxSelection: { value: sp.enable, set: (enable: boolean) => setSel({ enable }) },
    SelectionColor: { value: sp.color, set: (color: string) => setSel({ color }) },
    spinPickRadius: { value: sp.pickRadius, set: (pickRadius: number) => setSel({ pickRadius: clamp(Math.round(pickRadius * 10) / 10, 0.5, 200) }) },
    checkBoxPreselect: { value: tree.preSelection, set: (v: boolean) => setTreeOption('preSelection', v) },
    // FreeCAD's page shows these three unchecked in a fresh profile (the .ui gives them no `checked`), though TreeParams.py defaults them to true,
    // and the tree does what they say: here they show what the tree does.
    checkBoxAutoSwitch: { value: tree.syncView, set: (v: boolean) => setTreeOption('syncView', v) },
    checkBoxAutoExpand: { value: tree.syncSelection, set: (v: boolean) => setTreeOption('syncSelection', v) },
    checkBoxRecord: { value: tree.recordSelection, set: (v: boolean) => setTreeOption('recordSelection', v) },
    checkBoxSelectionCheckBoxes: { value: tree.checkBoxes, set: (v: boolean) => setTreeOption('checkBoxes', v) },
  }
  return <QtForm form={FORMS.selection} bind={bind} />
}

/** DlgSettingsNavigation.ui: Navigation Cube, Rotation Center Indicator, Navigation, Space Mouse, Animations, Clarify Selection. */
export function NavigationPage() {
  const nav = useStore((s) => s.nav), animate = useStore((s) => s.animate), cube = useStore((s) => s.cube)
  const p = useStore((s) => s.navPrefs), home = useStore((s) => s.homeView), newDocScale = useStore((s) => s.newDocCameraScale)
  const nc = useStore((s) => s.naviCube), rc = useStore((s) => s.rotationCenter), noTilt = useStore((s) => s.disableTouchTilt)
  const set = (k: 'animate' | 'disableTouchTilt', v: boolean) => { setState({ [k]: v }); saved.set(k, v) }
  const pref = (patch: Partial<NavPrefs>) => setState((s) => { const navPrefs = { ...s.navPrefs, ...patch }; saved.set('navPrefs', navPrefs); return { navPrefs } })
  // CornerNaviCube moves the cube to that corner (and wherever a drag had left it).
  const cubePref = (patch: Partial<NaviCubePrefs>) => setState((s) => {
    const naviCube = { ...s.naviCube, ...patch }
    saveNaviCube(naviCube)
    if (patch.corner === undefined) return { naviCube }
    saved.set('cubePos', CORNER_POS[patch.corner])
    return { naviCube, cubePlace: (['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const)[patch.corner], cubePos: CORNER_POS[patch.corner] }
  })
  const rcPref = (patch: Partial<RotationCenterPrefs>) => setState((s) => { const rotationCenter = { ...s.rotationCenter, ...patch }; saved.set('rotationCenter', rotationCenter); return { rotationCenter } })
  const hex2 = (a: number) => Math.round(clamp(a, 0, 1) * 255).toString(16).padStart(2, '0')
  const mouseButtons = () => {
    const n = NAV_STYLES.find((x) => x.id === nav)!
    void messageBox(null, 'Mouse Buttons', `Configuration ${n.name}\n\nSelection: ${n.hints[0]}\nPanning: ${n.hints[1]}\nRotation: ${n.hints[2]}\nZooming: ${n.hints[3]}`)
  }
  const bind: Bindings = {
    groupBoxNaviCube: { value: cube, set: (on: boolean) => setState({ cube: on }) },
    prefStepByTurn: { value: nc.stepByTurn, set: (v: number) => cubePref({ stepByTurn: v }) },
    naviCubeCorner: { value: nc.corner, set: (v: number) => cubePref({ corner: v as NaviCubePrefs['corner'] }) },
    // Deliberately different from FreeCAD, where it starts on (NaviCube.cpp:149): see PARITY.md, Mouse and navigation cube.
    naviCubeToNearest: { value: nc.toNearest, set: (v: boolean) => cubePref({ toNearest: v }) },
    naviCubeFontName: { value: nc.font, opts: [['', 'Default'], ...['Arial', 'Helvetica', 'Verdana', 'Tahoma', 'Trebuchet MS', 'Georgia', 'Times New Roman', 'Courier New'].map((f) => [f, f] as const)], set: (v: string) => cubePref({ font: v }) },
    prefCubeSize: { value: nc.size, set: (v: number) => cubePref({ size: v }) },
    naviCubeInactiveOpacity: { value: nc.inactiveOpacity, set: (v: number) => cubePref({ inactiveOpacity: v }) },
    naviCubeBaseColor: { value: nc.color, set: (v: string) => cubePref({ color: v }) },
    groupBoxRotationCenter: { value: p.showRotationCenter, set: (on: boolean) => pref({ showRotationCenter: on }) },
    rotationCenterSize: { value: rc.size, set: (v: number) => rcPref({ size: v }) },
    rotationCenterColor: { alpha: true, value: rc.color + hex2(rc.alpha), set: (v: string) => rcPref({ color: v.slice(0, 7), alpha: parseInt(v.slice(7, 9) || 'ff', 16) / 255 }) },
    comboNavigationStyle: { value: nav, opts: NAV_STYLES.map((n) => [n.id, n.name] as const), set: (v: string) => setNav(v as NavStyle) },
    mouseButton: { click: mouseButtons },
    comboOrbitStyle: { value: p.orbit, opts: ORBIT_ITEMS.map((o) => [o, ORBIT_STYLES[o]] as const), set: (v: number) => pref({ orbit: v as OrbitStyle }) },
    comboRotationMode: { value: p.rotationMode, opts: [[0, 'Window center'], [1, 'Drag at cursor'], [2, 'Object center']], set: (v: number) => pref({ rotationMode: v as 0 | 1 | 2 }) },
    comboNewDocView: { value: home ?? 'Trimetric', opts: ['Isometric', 'Dimetric', 'Trimetric', 'Top', 'Front', 'Left', 'Right', 'Rear', 'Bottom'].map((v) => [v, v] as const), set: (v: string) => setHomeView(v as HomeView) },
    qspinNewDocScale: { node: <QuantityBox value={newDocScale} dims={LENGTH} min={0.00001} max={10000000} onChange={(v) => { setState({ newDocCameraScale: v }); saved.set('newDocCameraScale', v) }} />, cls: 'qf-quantity' },
    checkBoxZoomAtCursor: { value: p.zoomAtCursor, set: (v: boolean) => pref({ zoomAtCursor: v }) },
    spinBoxZoomStep: { value: p.zoomStep, set: (v: number) => pref({ zoomStep: v }) },
    checkBoxInvertZoom: { value: p.invertZoom, set: (v: boolean) => pref({ invertZoom: v }) },
    checkBoxDisableTilt: { value: noTilt, set: (v: boolean) => set('disableTouchTilt', v) },
    checkBoxTouchpadScrollPans: { value: p.touchpadScrollPans, set: (v: boolean) => pref({ touchpadScrollPans: v }) },
    legacySpaceMouseDevices: na("a browser can't talk to a 3D mouse's driver"),
    groupBoxAnimations: { value: animate, set: (on: boolean) => set('animate', on) },
    spinBoxAnimationDuration: { value: p.duration, set: (v: number) => pref({ duration: v }) },
    checkBoxSpinningAnimations: { value: p.spinning, set: (v: boolean) => pref({ spinning: v }) },
    checkBoxEnableLongPressClarifySelection: { value: p.clarifyLongPress, set: (v: boolean) => pref({ clarifyLongPress: v }) },
    spinBoxLongPressTimeout: { value: p.longPressTimeout, set: (v: number) => pref({ longPressTimeout: v }) },
  }
  return <QtForm form={FORMS.navigation} bind={bind} />
}

// ── the server-side settings (`cad pref`, userprefs.py): the pages edit them through the API so the agent's commands see the same values ──
export const SERVER_DEFAULTS: Record<string, number> = { MaxUndoSize: 20, CacheLimit: 500, CachePeriod: 2 }
let serverPrefs: Record<string, number> = { ...SERVER_DEFAULTS }
const serverSubs = new Set<() => void>()
export const getServerPrefs = () => serverPrefs
export function loadServerPrefs(): Promise<Record<string, number> | null> {
  return api.prefs().then((r) => { serverPrefs = { ...SERVER_DEFAULTS, ...r.prefs }; serverSubs.forEach((f) => f()); return serverPrefs }).catch(() => null)
}
export function setServerPref(key: string, value: number) {
  serverPrefs = { ...serverPrefs, [key]: value }; serverSubs.forEach((f) => f())
  void api.setPref(key, value).then((r) => { serverPrefs = { ...SERVER_DEFAULTS, ...r.prefs }; serverSubs.forEach((f) => f()) }).catch(() => {})
}
function useServerPrefs() {
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); serverSubs.add(f); return () => { serverSubs.delete(f) } }, [])
  return serverPrefs
}

/** DlgSettingsDocument.ui: General, Storage, Document Objects, Authoring and License. Of these, Maximum undo/redo steps applies (the undo
 *  journal's cap, `cad pref MaxUndoSize`, set when typing ends: an emptied box goes back to the stored value rather than to 0, which would cut
 *  the shared undo journal at the next edit); the rest is about FCStd files, recompute and document objects, which projects here don't have. */
export function DocumentPage() {
  const sp = useServerPrefs()
  const fcstd = 'projects are folders of Python and TOML files, not FCStd documents'
  const saved_ = 'every change is written to the project as it is made'
  const git = 'the project is under git; undo keeps the journal'
  const bind: Bindings = {
    prefCheckNewDoc: na('the workbench opens the projects in its folders'),
    prefCompression: na(fcstd),
    prefUndoRedoSize: { value: sp.MaxUndoSize, min: 0, max: 99, lazy: true, set: (v: number) => setServerPref('MaxUndoSize', v) },
    prefCanAbortRecompute: na('a rebuild is one worker call'),
    prefEnableAsyncRecompute: na('a part rebuilds in the CAD worker, not the page'),
    prefRecovery: na(fcstd), prefAutoSaveEnabled: na(saved_), prefAutoSaveTimeout: na(saved_),
    prefSaveThumbnail: na(fcstd), prefThumbnailSize: na(fcstd), prefAddLogo: na(fcstd),
    prefSaveBackupFiles: na(git), prefCountBackupFiles: na(git), prefSaveBackupExtension: na(fcstd), prefSaveBackupDateFormat: na(fcstd),
    prefDisableVersionCheckOnSave: na(fcstd),
    prefDuplicateLabel: na('a body is named by its key in the assembly, which is unique'),
    prefPartialLoading: na('no linked documents here'),
    prefAuthor: na(fcstd), prefSetAuthorOnSave: na(fcstd), prefCompany: na(fcstd), prefLicenseType: na(fcstd), prefLicenseUrl: na(fcstd),
  }
  return <QtForm form={FORMS.document} bind={bind} />
}

/** DlgSettingsNotificationArea.ui: Enable Notification Area holds Additional Data Sources, Notifications List and Enable Pop-Up Notifications. */
export function NotificationAreaPage() {
  const np = useStore((s) => s.notifyPrefs)
  const bind: Bindings = {
    NotificationAreaEnabled: { value: np.areaEnabled, set: (areaEnabled: boolean) => setNotifyPrefs({ areaEnabled }) },
    developerErrorSubscriptionEnabled: { value: np.developerErrors, set: (developerErrors: boolean) => setNotifyPrefs({ developerErrors }) },
    developerWarningSubscriptionEnabled: { value: np.developerWarnings, set: (developerWarnings: boolean) => setNotifyPrefs({ developerWarnings }) },
    maxWidgetMessages: { value: np.maxWidgetMessages, set: (maxWidgetMessages: number) => setNotifyPrefs({ maxWidgetMessages }) },
    autoRemoveUserNotifications: { value: np.autoRemoveUserNotifications, set: (autoRemoveUserNotifications: boolean) => setNotifyPrefs({ autoRemoveUserNotifications }) },
    NonIntrusiveNotificationsEnabled: { value: np.popupEnabled, set: (popupEnabled: boolean) => setNotifyPrefs({ popupEnabled }) },
    maxDuration: { value: np.maxDuration, set: (maxDuration: number) => setNotifyPrefs({ maxDuration }) },
    minDuration: { value: np.minDuration, set: (minDuration: number) => setNotifyPrefs({ minDuration }) },
    maxNotifications: { value: np.maxOpenNotifications, set: (maxOpenNotifications: number) => setNotifyPrefs({ maxOpenNotifications }) },
    notificationWidth: { value: np.notificationWidth, set: (notificationWidth: number) => setNotifyPrefs({ notificationWidth }) },
    hideNonIntrusiveNotificationsWhenWindowDeactivated: { value: np.hideWhenDeactivated, set: (hideWhenDeactivated: boolean) => setNotifyPrefs({ hideWhenDeactivated }) },
    preventNonIntrusiveNotificationsWhenWindowNotActive: { value: np.preventWhenInactive, set: (preventWhenInactive: boolean) => setNotifyPrefs({ preventWhenInactive }) },
  }
  return <QtForm form={FORMS.notificationarea} bind={bind} />
}

/** DlgSettingsReportView.ui: Output, Colors, Python Interpreter. The colours start as FreeCAD Light's OutputWindow group (colorText 0x212529,
 *  colorLogging 0x55aaff, colorWarning 0xfd7c62, colorError 0xff0000: PreferencePacks/FreeCAD Light), which the Light theme's first start writes
 *  over ReportView.cpp's own black, blue, #ffaa00 and red. Same as freecad.css's --r-*. */
const REPORT_COLORS = { msg: '#212529', log: '#55aaff', warn: '#fd7c62', err: '#ff0000' }
export function applyReportColors() {
  const c = { ...REPORT_COLORS, ...saved.get<Partial<typeof REPORT_COLORS>>('report.colors', {}) }
  for (const [k, v] of Object.entries(c)) document.documentElement.style.setProperty(`--r-${k}`, v)
}
type ReportLevel = 'msg' | 'log' | 'warn' | 'err'
export function ReportViewPage() {
  const show = useStore((s) => s.reportShow), timecode = useStore((s) => s.reportTimecode)
  const [showOn, setShowOnRaw] = useState<Record<ReportLevel, boolean>>(() => ({ msg: false, log: false, warn: false, err: false, ...saved.get<Record<string, boolean>>('report.showOn', {}) }))
  const [colors, setColors] = useState(() => ({ ...REPORT_COLORS, ...saved.get<Partial<typeof REPORT_COLORS>>('report.colors', {}) }))
  const record = (l: ReportLevel) => (on: boolean) => { const reportShow = { ...getState().reportShow, [l]: on }; saved.set('reportShow', reportShow); setState({ reportShow }) }
  const showOnSet = (l: ReportLevel) => (on: boolean) => { const v = { ...showOn, [l]: on }; setShowOnRaw(v); saved.set('report.showOn', v) }
  const color = (l: ReportLevel) => (v: string) => { const c = { ...colors, [l]: v }; setColors(c); saved.set('report.colors', c); applyReportColors() }
  const python = 'there is no Python interpreter here'
  const bind: Bindings = {
    checkMessage: { value: show.msg, set: record('msg') },
    // Deliberately different from FreeCAD: log messages are recorded by default, since the agent's activity is logged at that level.
    checkLogging: { value: show.log, set: record('log') },
    checkWarning: { value: show.warn, set: record('warn') },
    checkError: { value: show.err, set: record('err') },
    checkShowReportViewOnError: { value: showOn.err, set: showOnSet('err') },
    checkShowReportViewOnWarning: { value: showOn.warn, set: showOnSet('warn') },
    checkShowReportViewOnNormalMessage: { value: showOn.msg, set: showOnSet('msg') },
    checkShowReportViewOnLogMessage: { value: showOn.log, set: showOnSet('log') },
    checkShowReportTimecode: { value: timecode, set: (v: boolean) => { saved.set('report.timecode', v); setState({ reportTimecode: v }) } },
    colorText: { value: colors.msg, set: color('msg') }, colorLogging: { value: colors.log, set: color('log') },
    colorWarning: { value: colors.warn, set: color('warn') }, colorError: { value: colors.err, set: color('err') },
    pythonOutput: na(python), pythonError: na(python),
  }
  return <QtForm form={FORMS.reportview} bind={bind} />
}

/** DlgSettings3DView.ui: General (the corner coordinate system, its size and the axis colours, the axis cross and the frame counter), Rendering
 *  (OpenGL settings, fixed by the browser's WebGL), Camera Type. */
export function View3DPage() {
  const corner = useStore((s) => s.corner), axisColors = useStore((s) => s.axisColors), axes = useStore((s) => s.axes), showFPS = useStore((s) => s.showFPS), ortho = useStore((s) => s.ortho)
  const set = (k: 'axes' | 'showFPS', v: boolean) => { setState({ [k]: v }); saved.set(k, v) }
  const setAxisColor = (k: keyof AxisColors) => (v: string) => setState((s) => { const axisColors = { ...s.axisColors, [k]: v }; saved.set('axisColors', axisColors); return { axisColors } })
  const gl = "set by the browser's WebGL"
  // FreeCAD's connections: the corner coordinate system's check box turns its size and the letter colour on and off.
  const bind: Bindings = {
    CheckBox_CornerCoordSystem: { value: corner.show, set: (show: boolean) => setCorner({ show }) },
    SpinBox_CornerCoordSystemSize: { value: corner.size, off: !corner.show, set: (size: number) => setCorner({ size }) },
    axisLetterColor: { value: axisColors.letter, off: !corner.show, set: setAxisColor('letter') },
    xAxisColor: { value: axisColors.x, set: setAxisColor('x') }, yAxisColor: { value: axisColors.y, set: setAxisColor('y') }, zAxisColor: { value: axisColors.z, set: setAxisColor('z') },
    CheckBox_ShowAxisCross: { value: axes, set: (v: boolean) => set('axes', v) },
    CheckBox_ShowFPS: { value: showFPS, set: (v: boolean) => set('showFPS', v) },
    CheckBox_use_SW_OpenGL: na(gl), CheckBox_useVBO: na(gl), renderCache: na(gl), comboAliasing: na(gl), comboTransparentRender: na(gl), boxMarkerSize: na(gl),
    FloatSpinBox_EyeDistance: na('there are no stereo modes here'), FloatSpinBox_DatumScale: na('there are no datum objects here'),
    SpinBox_MaxFrameRate: na('the browser redraws at the display\'s refresh rate'),
    radioPerspective: { value: !ortho, set: () => setOrtho(false) },
    radioOrthographic: { value: ortho, set: () => setOrtho(true) },
  }
  return <QtForm form={FORMS['3dview']} bind={bind} />
}

/** DlgSettingsUI.ui: Theme Customization (one theme here, so n/a), Tree View (TreeParams, all live in the tree), Overlay (the property view's scroll
 *  bar works; the rest is fixed) and Suggested Actions (n/a: no task watcher). */
export function UIPage() {
  const t = useStore((s) => s.treeUI)
  const theme = 'there is one theme here (FreeCAD Light)'
  const fixed = 'fixed here'
  const bind: Bindings = {
    ThemeAccentColor1: na(theme), ThemeAccentColor2: na(theme), ThemeAccentColor3: na(theme), StyleSheets: na(theme), OverlayStyleSheets: na(theme), themeEditorButton: na(theme),
    fontSizeSpinBox: { value: t.fontSize, set: (fontSize: number) => setTreeUI({ fontSize }) },
    iconSizeSpinBox: { value: t.iconSize, min: 0, max: 99, set: (iconSize: number) => setTreeUI({ iconSize }) },
    showVisibilityIconCheckBox: { value: t.visibilityIcon, set: (visibilityIcon: boolean) => setTreeUI({ visibilityIcon }) },
    resizableColumnsCheckBox: { value: t.resizableColumn, set: (resizableColumn: boolean) => setTreeUI({ resizableColumn }) },
    hideDescriptionCheckBox: { value: t.hideColumn, set: (hideColumn: boolean) => setTreeUI({ hideColumn }) },
    hideInternalNamesCheckBox: { value: t.hideInternalNames, set: (hideInternalNames: boolean) => setTreeUI({ hideInternalNames }) },
    hideTreeViewScrollBarCheckBox: { value: t.hideScrollBar, set: (hideScrollBar: boolean) => setTreeUI({ hideScrollBar }) },
    hideHeaderCheckBox: { value: t.hideHeader, set: (hideHeader: boolean) => setTreeUI({ hideHeader }) },
    hideTabBarCheckBox: na(fixed), hintShowTabBarCheckBox: na(fixed),
    hidePropertyViewScrollBarCheckBox: { value: t.hidePropScrollBar, set: (hidePropScrollBar: boolean) => setTreeUI({ hidePropScrollBar }) },
    overlayAutoHideCheckBox: na('the only view here is the 3D view'), mouseClickPassThroughCheckBox: na(fixed), mouseWheelPassThroughCheckBox: na(fixed),
    showTaskWatcherCheckBox: na('there is no task watcher here'),
  }
  return <QtForm form={FORMS.ui} bind={bind} />
}

/** DlgSettingsViewColor.ui: Background Color, Tree View, Color Bar. The radios swap the simple colour for the gradient's (setGradientColorVisibility),
 *  the labels follow the gradient's kind (Top, Middle, Bottom; Central, Midway, End for a radial one), Switch swaps the first and last colours,
 *  Middle color turns the middle one on. */
export function ColorsPage() {
  const bg = useStore((s) => s.background), editColor = useStore((s) => s.treeEditColor)
  const set = (v: Partial<BackgroundPrefs>) => { const background = { ...getState().background, ...v }; saved.set('background', background); setState({ background }) }
  const gradient = bg.mode !== 'simple'
  const [l1, l2, l3] = bg.mode === 'radial' ? ['Central', 'Midway', 'End'] : ['Top', 'Middle', 'Bottom']
  const noBars = 'there are no colour bars here (Mesh and FEM results)'
  const bind: Bindings = {
    radioButtonSimple: { value: bg.mode === 'simple', set: () => set({ mode: 'simple' }) },
    radioButtonGradient: { value: bg.mode === 'linear', set: () => set({ mode: 'linear' }) },
    rbRadialGradient: { value: bg.mode === 'radial', set: () => set({ mode: 'radial' }) },
    SelectionColor_Background: { value: bg.color, hide: gradient, set: (color: string) => set({ color }) },
    SwitchGradientColors: { hide: !gradient, click: () => set({ top: bg.bottom, bottom: bg.top }) },
    color1Label: { hide: !gradient, text: l1 }, color2Label: { hide: !gradient, text: l2, off: !bg.useMid }, color3Label: { hide: !gradient, text: l3 },
    backgroundColorFrom: { hide: !gradient, value: bg.top, set: (top: string) => set({ top }) },
    backgroundColorMid: { hide: !gradient, value: bg.mid, off: !bg.useMid, set: (mid: string) => set({ mid }) },
    backgroundColorTo: { hide: !gradient, value: bg.bottom, set: (bottom: string) => set({ bottom }) },
    checkMidColor: { hide: !gradient, value: bg.useMid, set: (useMid: boolean) => set({ useMid }) },
    TreeEditColor: { value: editColor, set: (v: string) => { saved.set('treeEditColor', v); setState({ treeEditColor: v }) } },
    TreeActiveColor: na('there are no active containers (a part or a body) here'),
    CbLabelColor: na(noBars), CbLabelTextSize: na(noBars),
  }
  return <QtForm form={FORMS.colors} bind={bind} />
}

/** DlgSettingsPDF.ui/.cpp: PDF Export's version and the warning under it (onComboBoxIndexChanged). Export PDF here is the browser's Save as PDF,
 *  which picks its own version (n/a). */
export function PdfPage() {
  const bind: Bindings = { comboBox: na("Export PDF uses the browser's Save as PDF, which sets the PDF version itself") }
  return <QtForm form={FORMS.pdf} bind={bind} />
}

/** DlgSettingsPythonConsole.ui: Console (word wrap, block cursor, save history: the console here follows them, as its own menu's Word Wrap and
 *  Save History do) and Other (n/a). */
export function PythonConsolePage() {
  const ed = useStore((s) => s.editorPrefs)
  const cad = 'the console runs cad commands, not Python'
  const bind: Bindings = {
    PythonWordWrap: { value: ed.wordWrap, set: (wordWrap: boolean) => setEditorPrefs({ wordWrap }) },
    PythonBlockCursor: { value: ed.consoleBlock, set: (consoleBlock: boolean) => setEditorPrefs({ consoleBlock }) },
    PythonSaveHistory: { value: ed.saveHistory, set: (saveHistory: boolean) => { setEditorPrefs({ saveHistory }); if (!saveHistory) saved.set('console.history', []) } },
    ProfilerInterval: na(cad), PathToPythonExecutable: na(cad),
  }
  return <QtForm form={FORMS.pythongeneral} bind={bind} />
}

/** DlgSettingsMacro.ui: General Macro Settings, Macro Recording Settings (Macro Path, Gui Commands), Logging Commands, Recent Macros Menu. */
export function MacroPage() {
  const recordGui = useStore((s) => s.recordGuiCommands), guiAsComment = useStore((s) => s.guiAsComment), scriptToConsole = useStore((s) => s.scriptToPyConsole)
  const [recent, setRecent] = useState<number>(() => saved.get('recentMacrosSize', 12))
  const [dir, setDir] = useState('')
  useEffect(() => { api.macros().then((r) => setDir(r.dir)).catch(() => {}) }, [])
  const set = (k: 'recordGuiCommands' | 'guiAsComment', v: boolean) => { setState({ [k]: v }); saved.set(k, v) }
  const bind: Bindings = {
    PrefCheckBox_LocalEnv: na('macros here are cad commands, each run in its own process'),
    MacroPath: { value: dir, why: 'a browser cannot pick a folder on this machine', tip: 'Where macros are kept (CAD_MACRO_DIR overrides it)' },
    PrefCheckBox_RecordGui: { value: recordGui, set: (v: boolean) => set('recordGuiCommands', v) },
    PrefCheckBox_GuiAsComment: { value: guiAsComment, off: !recordGui, set: (v: boolean) => set('guiAsComment', v) },
    PConsoleCheckBox: { value: scriptToConsole, set: (v: boolean) => { saved.set('scriptToPyConsole', v); setState({ scriptToPyConsole: v }) } },
    RecentMacros: { value: recent, set: (v: number) => { setRecent(v); saved.set('recentMacrosSize', v) } },
    ShortcutCount: na('the recent macros have no shortcuts here'), ShortcutModifiers: na('the recent macros have no shortcuts here'),
  }
  return <QtForm form={FORMS.macro} bind={bind} />
}

/** ApplicationCache::performAction: over the limit, ask to clear it (Open is n/a in a browser). */
export async function checkCache(info: CacheInfo): Promise<CacheInfo> {
  if (info.bytes <= info.limit) return info
  const b = await messageBox('warning', 'Cache Directory', `The cache directory ${info.dir} exceeds the size of ${info.limitText}. Clear it now?\n\n\n` +
    'Warning: Make sure that this is the only running cad-agent instance and that no documents are opened as this may result into data loss!', ['Yes', 'No'])
  if (b !== 'Yes') return info
  const r = await api.clearCache()
  return { ...info, bytes: r.bytes, text: r.text }
}
/** DlgSettingsCacheDirectory.ui: Location (read-only), Check periodically at program start, Cache size limit, Current cache size and Check Now; the cache is
 *  `cad cache`'s (appcache.py). */
let cacheSizeText = '' // DlgSettingsCacheDirectory::currentSize is a static: "Unknown" until Check Now measures it, and then what it measured for as long as the app runs
export function CachePage() {
  const sp = useServerPrefs()
  const [info, setInfo] = useState<CacheInfo | null>(null)
  const [size, setSize] = useState(cacheSizeText)
  useEffect(() => { void api.cache().then(setInfo).catch(() => {}) }, [])
  const limits: [number, string][] = [[100, '100 MB'], [300, '300 MB'], [500, '500 MB'], [1024, '1 GB'], [2048, '2 GB'], [3072, '3 GB']]
  if (!limits.some(([v]) => v === sp.CacheLimit)) limits.push([sp.CacheLimit, `${sp.CacheLimit} MB`])
  const bind: Bindings = {
    cacheLocation: { value: info?.dir ?? '' },
    openButton: na("a browser can't open a folder on this machine"),
    comboBoxPeriod: { value: sp.CachePeriod, opts: ['Always', 'Daily', 'Weekly', 'Monthly', 'Yearly', 'Never'].map((p, i) => [i, p] as const), set: (v: number) => setServerPref('CachePeriod', v) },
    comboBoxLimit: { value: sp.CacheLimit, opts: limits, set: (v: number) => setServerPref('CacheLimit', v) },
    labelCurrentCache: { text: `Current cache size: ${size || 'Unknown'}` },
    pushButtonCheck: { click: () => { void api.cache().then(checkCache).then((i) => { cacheSizeText = i.text; setSize(i.text); setInfo(i) }).catch(() => {}) } },
  }
  return <QtForm form={FORMS.cache} bind={bind} />
}

// ── Light Sources ────────────────────────────────────────────────────────────────────────────────────────────────
/** DlgSettingsLightSources::configureViewer: a sphere (radius 3, SoComplexity 1) in createMaterial's material, seen through an orthographic camera along
 *  (0, 1, 0.3), twice as high as viewAll, lit by the view's own lights and over its background; zoomIn/zoomOut step a 14th of that. */
function LightPreview({ lights, api: zoomApi }: { lights: LightPrefs; api: { current: { zoom(d: number): void } | null } }) {
  const host = useRef<HTMLDivElement>(null)
  const ref = useRef<{ render(p: LightPrefs): void; zoom(d: number): void } | null>(null)
  const bg = useStore((s) => s.background)
  useEffect(() => {
    const el = host.current
    if (!el || el.closest('.pref-index')) return // not in the search index's off-screen copy
    let renderer: THREE.WebGLRenderer
    try { renderer = new THREE.WebGLRenderer({ antialias: true }) } catch { return } // no WebGL: no preview
    const scene = new THREE.Scene()
    renderer.setClearColor(bg.color, 1)
    if (bg.mode !== 'simple') scene.add(gradientMesh(bg))
    // createMaterial: diffuse #d2d2ff, specular #cccccc, shininess 0.9 (× 128, Coin's GL exponent).
    const sphere = new THREE.Mesh(new THREE.SphereGeometry(3, 64, 48), new THREE.MeshPhongMaterial({ color: 0xd2d2ff, specular: 0xcccccc, shininess: 0.9 * 128 }))
    scene.add(sphere)
    const rig = new LightRig(scene, lights)
    let height = 6 * 2 // viewAll fits the sphere's diameter; configureViewer doubles it
    const zoomStep = height / 14
    const cam = new THREE.OrthographicCamera()
    const dir = new THREE.Vector3(0, 1, 0.3).normalize() // defaultViewDirection
    cam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), dir)
    cam.position.copy(dir).multiplyScalar(-20)
    const draw = () => {
      const w = el.clientWidth, h = el.clientHeight
      if (!w || !h) return
      renderer.setPixelRatio(window.devicePixelRatio)
      renderer.setSize(w, h)
      const a = w / h
      Object.assign(cam, { left: (-height / 2) * a, right: (height / 2) * a, top: height / 2, bottom: -height / 2, near: 0.1, far: 40 })
      cam.updateProjectionMatrix(); cam.updateMatrixWorld()
      rig.follow(cam)
      renderer.render(scene, cam)
    }
    el.appendChild(renderer.domElement)
    ref.current = { render: (p) => { rig.apply(p); draw() }, zoom: (d) => { height = Math.max(zoomStep, height + d * zoomStep); draw() } }
    zoomApi.current = ref.current
    const ro = new ResizeObserver(draw)
    ro.observe(el)
    return () => { ro.disconnect(); rig.dispose(); sphere.geometry.dispose(); renderer.dispose(); renderer.domElement.remove(); ref.current = null; zoomApi.current = null }
  }, [bg]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { ref.current?.render(lights) }, [lights])
  return <div ref={host} className="light-view" />
}
/** DlgSettingsLightSources.ui: Light Sources (a row per light: enable, horizontal and vertical angle, colour, intensity; then the ambient light's colour and
 *  intensity) over Preview. The angles are the light's direction as azimuth/elevation (loadSettings/saveSettings convert). */
export function LightSourcesPage() {
  const lights = useStore((s) => s.lights)
  const set = (patch: Partial<LightPrefs>) => { const v = { ...getState().lights, ...patch }; saved.set('lights', v); setState({ lights: v }) }
  // The boxes keep what was typed; the stored direction is derived from it (round trips would drift).
  const [angles, setAngles] = useState(() => ({ head: directionToAzimuthElevation(lights.head.dir), back: directionToAzimuthElevation(lights.back.dir), fill: directionToAzimuthElevation(lights.fill.dir) }))
  const zoom = useRef<{ zoom(d: number): void } | null>(null)
  const bind: Bindings = {
    viewer: { node: <LightPreview lights={lights} api={zoom} /> },
    zoomInButton: { click: () => zoom.current?.zoom(-1) },
    zoomOutButton: { click: () => zoom.current?.zoom(1) },
    ambientLightColor: { value: lights.ambient.color, set: (color: string) => set({ ambient: { ...lights.ambient, color } }) },
    ambientLightIntensitySpinBox: { value: lights.ambient.intensity, set: (intensity: number) => set({ ambient: { ...lights.ambient, intensity } }) },
  }
  for (const [k, p] of [['head', 'main'], ['back', 'back'], ['fill', 'fill']] as const) {
    const l = lights[k], [az, el] = angles[k]
    const upd = (v: Partial<Light>) => set({ [k]: { ...l, ...v } })
    const angle = (i: 0 | 1) => (v: number) => {
      const a: [number, number] = i ? [az, v] : [v, el]
      setAngles((x) => ({ ...x, [k]: a }))
      upd({ dir: azimuthElevationToDirection(...a) })
    }
    bind[`${p}LightEnable`] = { value: l.on, set: (on: boolean) => upd({ on }) }
    bind[`${p}LightHorizontalAngle`] = { value: az, min: -180, max: 180, dec: 2, set: angle(0) }
    bind[`${p}LightVerticalAngle`] = { value: el, min: -90, max: 90, dec: 2, set: angle(1) }
    bind[`${p}LightColor`] = { value: l.color, set: (color: string) => upd({ color }) }
    bind[`${p}LightIntensitySpinBox`] = { value: l.intensity, set: (intensity: number) => upd({ intensity }) }
  }
  return <QtForm form={FORMS.lightsources} bind={bind} />
}

// ── Editor ───────────────────────────────────────────────────────────────────────────────────────────────────────
/** DlgSettingsEditor.ui: Options, Indentation, Display Items (the item list with its font family, size and colour, and a preview). The macro editor and the
 *  console follow the font, Text and Python output/error colours and indentation; the editor here is plain text, so line numbers, folding and the syntax
 *  colours don't show (n/a). */
const SYNTAX = new Set(['Text', 'Python output', 'Python error']) // the colours the macro editor and the console show
/** The sample the page's preview shows (DlgSettingsEditor.cpp's), and the way PythonSyntaxHighlighter colours it: comments, strings, numbers, keywords
 *  (print among them), the name a def defines, operators. */
const PREVIEW = '# Short Python sample\nimport sys\n\ndef foo(begin, end):\n\ti = begin\n\twhile i < end:\n\t\tprint(i)\n\t\ti = i + 1\n\t\tprint("Text")\n\treturn None\n\nfoo(0, 20)\n'
const KEYWORDS = new Set(['and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except', 'exec', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
  'lambda', 'not', 'or', 'pass', 'print', 'raise', 'return', 'try', 'while', 'with', 'yield', 'None', 'True', 'False'])
function Highlighted({ colors }: { colors: Record<string, string> }) {
  const out: ReactNode[] = []
  PREVIEW.split('\n').forEach((line, ln) => {
    const hash = line.indexOf('#')
    const code = hash < 0 ? line : line.slice(0, hash)
    const parts = code.split(/("[^"]*"|\b\w+\b|[<>=+\-*/]+)/)
    let afterDef = false
    parts.forEach((t, i) => {
      if (!t) return
      let item = ''
      if (t.startsWith('"')) item = 'String'
      else if (/^\d+$/.test(t)) item = 'Number'
      else if (KEYWORDS.has(t)) { item = 'Keyword'; afterDef = t === 'def' }
      else if (afterDef && /^\w+$/.test(t)) { item = 'Define name'; afterDef = false }
      else if (/^[<>=+\-*/]+$/.test(t)) item = 'Operator'
      out.push(item ? <span key={`${ln}.${i}`} style={{ color: colors[item], fontWeight: item === 'Keyword' ? 700 : undefined }}>{t}</span> : t)
    })
    if (hash >= 0) out.push(<span key={`${ln}c`} style={{ color: colors.Comment }}>{line.slice(hash)}</span>)
    out.push('\n')
  })
  return <>{out}</>
}
export function EditorPage() {
  const ed = useStore((s) => s.editorPrefs)
  const [item, setItem] = useState('Text')
  const plain = 'the macro editor here is plain text'
  const bind: Bindings = {
    EnableLineNumber: na(plain),
    EnableBlockCursor: { value: ed.blockCursor, set: (blockCursor: boolean) => setEditorPrefs({ blockCursor }) },
    EnableFolding: na(plain),
    tabSize: { value: ed.tabSize, min: 0, max: 99, set: (tabSize: number) => setEditorPrefs({ tabSize }) },
    indentSize: { value: ed.indentSize, min: 0, max: 99, set: (indentSize: number) => setEditorPrefs({ indentSize }) },
    radioTabs: { value: !ed.spaces, set: () => setEditorPrefs({ spaces: false }) },
    radioSpaces: { value: ed.spaces, set: () => setEditorPrefs({ spaces: true }) },
    displayItems: { node: <div className="qf-tree" title="Color and font settings will be applied to selected type">{Object.keys(EDITOR_COLORS).map((k) => (
      <div key={k} className={cls('qf-tree-row', k === item && 'sel')} onClick={() => setItem(k)}><span>{k}</span></div>))}</div> },
    fontFamily: { value: ed.font, opts: FONTS.map((f) => [f, f === 'ui-monospace' ? 'Menlo' : f] as const), set: (font: string) => setEditorPrefs({ font }) },
    fontSize: { value: ed.fontSize, min: 1, max: 99, set: (fontSize: number) => setEditorPrefs({ fontSize }) },
    // every item's colour is live in the preview; the macro editor and the console show Text, Python output and Python error
    colorButton: { value: ed.colors[item], tip: SYNTAX.has(item) ? undefined : `The macro editor here is plain text: this colour shows in the preview`, set: (c: string) => setEditorPrefs({ colors: { ...ed.colors, [item]: c } }) },
    textEdit1: { node: <pre className="qf-preview" style={editorStyle(ed) as CSSProperties}><Highlighted colors={ed.colors} /></pre> },
  }
  return <QtForm form={FORMS.editor} bind={bind} />
}
const FONTS = ['ui-monospace', 'Monaco', 'Courier New', 'Andale Mono', 'SF Mono', 'Consolas', 'DejaVu Sans Mono']

// ── Workbenches ──────────────────────────────────────────────────────────────────────────────────────────────────
/** DlgSettingsWorkbenches.ui / DlgSettingsWorkbenchesImp.cpp: Workbenches (a row per workbench: enable, icon, name, its W, n shortcut, Auto-load, Loaded; drag
 *  to reorder, or Sort Alphabetically from the context menu; disabled ones after the enabled), Selectors (item style, selector type) and Startup (Default
 *  workbench; Remember active workbench by tab). */
export function WorkbenchesPage() {
  const p = useStore((s) => s.wbPrefs)
  const set = (patch: Partial<WbPrefs>) => { const wbPrefs = { ...getState().wbPrefs, ...patch }; saved.set('wbPrefs', wbPrefs); setState({ wbPrefs }) }
  const all = allWorkbenches()
  const at = (k: string) => (p.order.includes(k) ? p.order.indexOf(k) : p.order.length + all.findIndex(([x]) => x === k))
  const enabled = all.filter(([k]) => k === p.startup || !p.disabled.includes(k)).sort((a, b) => at(a[0]) - at(b[0]))
  const disabled = all.filter(([k]) => k !== p.startup && p.disabled.includes(k))
  const [drag, setDrag] = useState<string | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const move = (k: string, before: string) => { const o: string[] = enabled.map(([x]) => x as string).filter((x) => x !== k); o.splice(o.indexOf(before), 0, k); set({ order: o }) }
  const startup = (k: string) => k === p.startup
  const row = ([k, w]: (typeof all)[number], i: number | null) => (
    <div key={k} className={cls('wb-row', i === null && 'off')} draggable={i !== null} onDragStart={() => setDrag(k)}
      onDragOver={(e) => { if (drag && i !== null) e.preventDefault() }} onDrop={() => { if (drag && drag !== k) move(drag, k); setDrag(null) }}
      onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}>
      <label className="qf-check wb-on" title={startup(k) ? 'This is the current startup module, and must be enabled' : `Toggles the visibility of ${w.label} in the available workbenches`}>
        <input type="checkbox" checked={i !== null} disabled={startup(k)} onChange={(e) => set({ disabled: e.target.checked ? p.disabled.filter((x) => x !== k) : [...p.disabled, k] })} /><span />
      </label>
      <span className="wb-ico"><Icon name={w.icon} size={20} /></span>
      <span className="wb-text"><b>{w.label}</b><span title="Shortcut to activate this workbench">{i !== null && i < 9 ? `(W, ${i + 1})` : ''}</span></span>
      {/* the startup workbench is always auto-loaded; for the others FreeCAD starts the box off (a workbench here is part of the page, loaded with it) */}
      <label className="qf-check wb-auto off" title={startup(k) ? 'This is the current startup module, and must be autoloaded.' : `n/a: ${w.label} is part of the page, loaded with it`}>
        <input type="checkbox" checked={startup(k)} disabled /><span>Auto-load</span></label>
      <span className="wb-loaded">Loaded</span>
    </div>)
  const bind: Bindings = {
    wbList: { node: <div className="qf-wb">{enabled.map((w, i) => row(w, i))}{disabled.map((w) => row(w, null))}
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[{ label: 'Sort Alphabetically', onSelect: () => set({ order: [...enabled].sort((a, b) => a[1].label.localeCompare(b[1].label)).map(([k]) => k) }) }]} />}</div> },
    WorkbenchSelectorItem: { value: p.itemStyle, opts: [[0, 'Icon and text'], [1, 'Icon'], [2, 'Text']], set: (itemStyle: number) => set({ itemStyle: itemStyle as 0 | 1 | 2 }) },
    WorkbenchSelectorType: { value: p.selector, opts: [['ComboBox', 'ComboBox'], ['TabBar', 'TabBar']], set: (selector: string) => set({ selector: selector as WbPrefs['selector'] }) },
    AutoloadModuleCombo: { value: p.startup, opts: enabled.map(([k, w]) => [k, w.label] as const), set: (startup: string) => set({ startup, disabled: p.disabled.filter((x) => x !== startup) }) },
    CheckBox_WbByTab: na('there is one 3D view here'),
  }
  return <QtForm form={FORMS.workbenches} bind={bind} />
}

// ── Keyboard ─────────────────────────────────────────────────────────────────────────────────────────────────────
/** Gui::AccelLineEdit (Widgets.cpp): records the keys pressed, up to four chords of a sequence; Backspace or Delete alone clears it. Shows native text, holds
 *  portable text. */
export function AccelEdit({ value, onChange, readOnly, title, className }: { value: string; onChange?: (v: string) => void; readOnly?: boolean; title?: string; className?: string }) {
  // (a QKeySequenceEdit: its line edit says "Press shortcut" while it is empty, read-only or not)
  return <input className={cls('accel-edit', className)} readOnly value={nativeText(value)} title={title} placeholder="Press shortcut"
    onKeyDown={readOnly ? undefined : (e) => {
      if (e.key === 'Tab') return
      e.preventDefault(); e.stopPropagation()
      const k = eventSeq(e.nativeEvent)
      if (!k) return
      if ((k === 'Backspace' || k === 'Del')) { onChange?.(''); return }
      const chords = value ? value.split(', ') : []
      onChange?.((chords.length >= 4 ? [k] : [...chords, k]).join(', '))
    }} />
}
/** DlgKeyboard.ui / DlgKeyboardImp.cpp: General (Multi-key sequence delay) and Shortcuts: the search box, Category (FreeCAD's categories, the first one chosen),
 *  the command list (Icon, Command, Shortcut, Default), Current shortcut, New shortcut with Assign / Clear / Reset / Reset All, and the Priority List of the
 *  commands that share the shortcut. Shortcuts take effect at once (keymap.ts). */
const FC_ORDER = new Map(Object.keys(COMMAND_CATEGORY).map((n, i) => [n, i] as const)) // the order FreeCAD lists the commands of a category in

/** CommandCompleter (CommandCompleter.cpp): from three characters on, a popup under the field lists the commands whose "Name (Std_Command) (Shortcut)" holds the text
 *  (any case), at least 300 px wide; choosing one (a click, or Return on the highlighted one) goes to its category and selects it. Escape empties the field, Tab and
 *  Shift+Tab move through the list. */
function CommandSearch({ cmds, onPick }: { cmds: { name: string; label: string }[]; onPick: (name: string) => void }) {
  const [text, setText] = useState('')
  const [shown, setShown] = useState(false)
  const [hi, setHi] = useState(-1)
  const title = (c: { name: string; label: string }) => { const sc = shortcutOf(c.name); return `${c.label} (${c.name})${sc ? ` (${sc})` : ''}` }
  const q = text.toLowerCase()
  const hits = useMemo(() => (shown && text.length >= 3 ? cmds.filter((c) => title(c).toLowerCase().includes(q)) : []), [shown, text, cmds]) // eslint-disable-line react-hooks/exhaustive-deps
  const pick = (c: { name: string; label: string }) => { setText(title(c)); setShown(false); setHi(-1); onPick(c.name) }
  const move = (d: 1 | -1) => setHi((i) => (hits.length ? (i + d + hits.length) % hits.length : -1))
  return (
    <span className="qf-comp">
      <input className="qf-edit" type="text" spellCheck={false} placeholder="Type to search…" value={text}
        onChange={(e) => { setText(e.target.value); setShown(true); setHi(-1) }} onBlur={() => setShown(false)}
        onKeyDown={(e) => {
          if (e.key === 'Escape' && (text || hits.length)) { e.preventDefault(); e.stopPropagation(); setText(''); setShown(false); setHi(-1) }
          else if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey && hits.length)) { e.preventDefault(); move(1) }
          else if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey && hits.length)) { e.preventDefault(); move(-1) }
          else if (e.key === 'Enter') { e.preventDefault(); if (hi >= 0 && hits[hi]) pick(hits[hi]); else setShown(true) }
        }} />
      {hits.length > 0 && (
        <div className="qf-comp-pop" role="listbox" onMouseDown={(e) => e.preventDefault()}>
          {hits.map((c, i) => (
            <div key={c.name} role="option" aria-selected={i === hi} className={cls('qf-comp-item', i === hi && 'sel')} onMouseEnter={() => setHi(i)} onClick={() => pick(c)}>
              <span className="qf-comp-ico">{cmdIcon(c.name) ? <Icon name={cmdIcon(c.name)!} size={16} /> : null}</span>{title(c)}</div>))}
        </div>)}
    </span>)
}

/** DlgKeyboard.ui / DlgKeyboardImp.cpp: General (Multi-key sequence delay) and Shortcuts: the search field (a completer), Category (FreeCAD's categories, the first
 *  one chosen), the command list (Icon, Command, Shortcut, Default: the portable text, as FreeCAD writes it), Current shortcut, New shortcut with Assign / Clear /
 *  Reset / Reset All, and the Priority List of the commands that share the shortcut. Shortcuts take effect at once (keymap.ts). Assign is enabled once a new shortcut
 *  is typed that differs from the current one, Reset when the current one differs from the default; Clear and Reset All always are. */
export function KeyboardPage() {
  const user = useStore((s) => s.shortcuts), timeout = useStore((s) => s.shortcutTimeout)
  const [cur, setCur] = useState<string | null>(null)
  const [edit, setEdit] = useState('')
  const [cat, setCat] = useState(KEYBOARD_CATEGORIES[0])
  const [sort, setSort] = useState<[number, 1 | -1]>([0, 1]) // the Icon column, whose "order" is the one FreeCAD lists the commands in
  const tree = useRef<HTMLDivElement>(null)
  const cmds = useMemo(() => listCommands(), [])
  const names = cmds.map((c) => c.name)
  const categoryOf = (n: string) => COMMAND_CATEGORY[n] ?? 'CAD Agent'
  // FreeCAD's categories that hold a command here, in its order; ours (CAD Agent) before the tree's
  const cats = useMemo(() => {
    const have = new Set(cmds.map((c) => categoryOf(c.name)))
    const order = [...KEYBOARD_CATEGORIES.filter((c) => c && c !== 'All')]
    order.splice(Math.max(0, order.indexOf('TreeView')), 0, 'CAD Agent')
    return [...order.filter((c) => have.has(c)), 'All']
  }, [cmds])
  const first = cats.includes(cat) ? cat : cats[0]
  const rows = cmds.filter((c) => first === 'All' || categoryOf(c.name) === first)
  const cell = (c: { name: string; label: string }, i: number) => (i === 1 ? c.label : i === 2 ? shortcutOf(c.name) : defaultAccel()[c.name] ?? '')
  rows.sort((a, b) => sort[1] * (sort[0] === 0 ? (FC_ORDER.get(a.name) ?? 1e6) - (FC_ORDER.get(b.name) ?? 1e6) : cell(a, sort[0]).localeCompare(cell(b, sort[0]))))
  const current = cur ? shortcutOf(cur) : ''
  const priority = commandsByShortcut(edit || current, names)
  const head = ['Icon', 'Command', 'Shortcut', 'Default']
  useEffect(() => { tree.current?.querySelector('.qf-tree-row.sel > span')?.scrollIntoView({ block: 'nearest' }) }, [cur, first])
  const bind: Bindings = {
    shortcutTimeout: { value: timeout, min: 0, max: 10000, step: 100, set: (v: number) => { saved.set('shortcutTimeout', v); setState({ shortcutTimeout: v }) } },
    editCommand: { node: <CommandSearch cmds={cmds} onPick={(n) => { setCat(categoryOf(n)); setCur(n); setEdit('') }} /> },
    // onCategoryBoxActivated: the fields are emptied; the command stays selected if the new list has it
    categoryBox: { value: first, opts: cats.map((c) => [c, c] as const), set: (v: string) => { setCat(v); setEdit(''); if (cur && v !== 'All' && categoryOf(cur) !== v) setCur(null) } },
    commandTreeWidget: { node: (
      <div className="qf-tree kb" ref={tree}>
        <div className="qf-tree-head" role="row">{head.map((h, i) => <span key={h} role="columnheader" className={cls(sort[0] === i && 'sorted', sort[0] === i && sort[1] < 0 && 'up')}
          onClick={() => setSort(([c, d]) => [i, c === i ? (-d as 1 | -1) : 1])}>{h}</span>)}</div>
        {rows.map((c) => (
          <div key={c.name} className={cls('qf-tree-row', cur === c.name && 'sel')} title={c.name} onClick={() => { setCur(c.name); setEdit('') }}>
            <span className="kb-icon">{cmdIcon(c.name) ? <Icon name={cmdIcon(c.name)!} size={32} /> : null}</span><span>{c.label}</span>
            <span>{shortcutOf(c.name)}</span><span>{defaultAccel()[c.name] ?? ''}</span></div>))}
      </div>) },
    currentShortcut: { node: <AccelEdit className="qf-edit" value={current} readOnly title="To change a current shortcut enter the new shortcut in the field below and press 'Assign'." /> },
    editShortcut: { node: <AccelEdit className="qf-edit" value={edit} onChange={setEdit} /> },
    buttonAssign: { off: !cur || !edit || edit === current, click: () => { setShortcut(cur!, edit); setEdit('') } },
    buttonClear: { click: () => { if (cur) { setShortcut(cur, ''); setEdit('') } } },
    buttonReset: { off: !cur || !(cur in user), click: () => setShortcut(cur!, null) },
    buttonResetAll: { click: resetAllShortcuts },
    assignedTreeWidget: { node: <div className="qf-tree prio">{priority.map((n, i) => <div key={n} className={cls('qf-tree-row', i % 2 === 1 && 'alt')}><span>{n}</span><span>{cmds.find((c) => c.name === n)?.label}</span></div>)}</div> },
    buttonUp: { why: 'a shortcut here runs the first command that has it', off: true }, buttonDown: { why: 'a shortcut here runs the first command that has it', off: true },
  }
  return <QtForm form={FORMS.keyboard} bind={bind} />
}

// ── Advanced ─────────────────────────────────────────────────────────────────────────────────────────────────────
/** DlgSettingsAdvanced.cpp (generated from OverlayParams.py) builds its page in code, with no .ui: a QVBoxLayout of the Overlay group box (its grid of a label and
 *  a spin box per DockOverlay* setting, beside a stretch) and a spacer. The rows are OverlayParams' ranges, steps, suffixes and docs (the hints are the size
 *  hints the real FreeCAD measured), in the order the generated code adds them. */
type AdvRow = [name: string, key: keyof OverlayPrefs, label: string, kind: 'spin' | 'check' | 'combo', lo: number, hi: number, step: number, suffix: string, hint: number, doc: string]
const SIDE = 'Auto hide hint visual display '
const ADV: AdvRow[] = [
  ['DockOverlayWheelDelay', 'wheelDelay', 'Delay mouse wheel pass through', 'spin', 0, 99999, 1, ' ms', 115, 'Delay capturing mouse wheel event for passing through if it is\npreviously handled by other widget.'],
  ['DockOverlayAlphaRadius', 'alphaRadius', 'Alpha test radius', 'spin', 1, 100, 1, ' px', 93, 'If auto mouse click through is enabled, then this radius\ndefines a region of alpha test under the mouse cursor.'],
  ['DockOverlayCheckNaviCube', 'checkNaviCube', 'Check navigation cube', 'check', 0, 0, 0, '', 0, 'Leave space for Navigation Cube in dock overlay'],
  ['DockOverlayHintTriggerSize', 'hintTriggerSize', 'Hint trigger size', 'spin', 1, 100, 1, ' px', 93, SIDE + 'triggering width'],
  ['DockOverlayHintSize', 'hintSize', 'Hint width', 'spin', 1, 100, 1, ' px', 93, SIDE + 'width'],
  ['DockOverlayHintLeftOffset', 'hintLeftOffset', 'Left panel hint offset', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'offset for left panel'],
  ['DockOverlayHintLeftLength', 'hintLeftLength', 'Left panel hint length', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'length for left panel. Set to zero to fill the space.'],
  ['DockOverlayHintRightOffset', 'hintRightOffset', 'Right panel hint offset', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'offset for right panel'],
  ['DockOverlayHintRightLength', 'hintRightLength', 'Right panel hint length', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'length for right panel. Set to zero to fill the space.'],
  ['DockOverlayHintTopOffset', 'hintTopOffset', 'Top panel hint offset', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'offset for top panel'],
  ['DockOverlayHintTopLength', 'hintTopLength', 'Top panel hint length', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'length for top panel. Set to zero to fill the space.'],
  ['DockOverlayHintBottomOffset', 'hintBottomOffset', 'Bottom panel hint offset', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'offset for bottom panel'],
  ['DockOverlayHintBottomLength', 'hintBottomLength', 'Bottom panel hint length', 'spin', 0, 10000, 10, ' px', 109, SIDE + 'length for bottom panel. Set to zero to fill the space.'],
  ['DockOverlayHintDelay', 'hintDelay', 'Hint delay', 'spin', 0, 1000, 100, ' ms', 105, 'Delay before show hint visual'],
  ['DockOverlaySplitterHandleTimeout', 'splitterHandleTimeout', 'Splitter auto hide delay', 'spin', 0, 99999, 100, ' ms', 115, 'Overlay splitter handle auto hide delay. Set zero to disable auto hiding.'],
  ['DockOverlayActivateOnHover', 'activateOnHover', 'Activate on hover', 'check', 0, 0, 0, '', 0, 'Show auto hidden dock overlay on mouse over.\nIf disabled, then show on mouse click.'],
  ['DockOverlayDelay', 'delay', 'Layout delay', 'spin', 0, 5000, 100, ' ms', 107, 'Overlay layout delay'],
  ['DockOverlayAnimationDuration', 'animationDuration', 'Animation duration', 'spin', 0, 5000, 100, ' ms', 107, 'Auto hide animation duration, 0 to disable'],
  ['DockOverlayAnimationCurve', 'animationCurve', 'Animation curve type', 'combo', 0, 0, 0, '', 137, 'Auto hide animation curve type'],
]
const FIXED_HERE = new Set(['wheelDelay', 'alphaRadius', 'checkNaviCube', 'splitterHandleTimeout', 'delay', 'hintRightOffset', 'hintRightLength', 'hintTopOffset', 'hintTopLength'])
function advancedForm(): UiForm {
  const items: UiItem[] = []
  ADV.forEach(([name, , label, kind, lo, hi, step, suffix, hint, doc], r) => {
    if (kind === 'check') {
      items.push({ r, c: 0, w: { c: 'Gui::PrefCheckBox', n: name, p: { text: label, toolTip: doc }, fc: { h: [hint, 20], pol: 'mF' } } })
      return
    }
    items.push({ r, c: 0, w: { c: 'QLabel', n: `label${name}`, p: { text: label, toolTip: doc }, fc: { h: [0, 16], pol: 'PP' } } })
    items.push({ r, c: 1, w: kind === 'combo'
      ? { c: 'Gui::PrefComboBox', n: name, p: { toolTip: doc }, fc: { h: [hint, 24], pol: 'PF' } }
      : { c: 'Gui::PrefSpinBox', n: name, p: { toolTip: doc, minimum: lo, maximum: hi, singleStep: step, suffix }, fc: { h: [hint, 23], pol: 'mF' } } })
  })
  return { title: 'Advanced', root: { c: 'QWidget', n: 'DlgSettingsAdvanced', l: { t: 'V', i: [
    { w: { c: 'QGroupBox', n: 'groupOverlay', p: { title: 'Overlay' }, fc: { h: [0, 0], pol: 'PP' }, l: { t: 'H', m: [9, 9, 9, 9], i: [{ l: { t: 'G', i: items } }, { s: { o: 'h', t: 'Expanding', w: 0, h: 0 } }] } } },
    { s: { o: 'v', t: 'Expanding', w: 40, h: 20 } },
  ] } } }
}
const ADVANCED = advancedForm()
/** The Overlay group's grid of DockOverlay* settings. The hint, its delay, hover-or-click and the animation work; the right and top panels aren't overlaid here,
 *  and the pass-through, splitter and layout timings are fixed. (A fresh FreeCAD profile shows 99 for every value above 99, since the generated code sets a
 *  spin box's value before its range; these show the settings' real defaults, which the overlay uses.) */
export function AdvancedPage() {
  const p = useStore((s) => s.overlayPrefs)
  const bind: Bindings = {}
  for (const [name, key, , kind, lo, hi, step, suffix] of ADV) {
    const fixed = FIXED_HERE.has(key)
    const why = key.startsWith('hintRight') || key.startsWith('hintTop') ? 'only the left and bottom panels are overlaid here' : 'fixed here'
    if (kind === 'check') bind[name] = key === 'activateOnHover' ? { value: p.activateOnHover, set: (v: boolean) => setOverlayPrefs({ activateOnHover: v }) } : { value: p[key] as boolean, why }
    else if (kind === 'combo') bind[name] = { value: p.animationCurve, opts: ANIMATION_CURVES.map((c, i) => [i, c] as const), set: (v: number) => setOverlayPrefs({ animationCurve: v }) }
    else bind[name] = fixed ? { value: p[key] as number, min: lo, max: hi, step, suffix, why } : { value: p[key] as number, min: lo, max: hi, step, suffix, set: (v: number) => setOverlayPrefs({ [key]: v }) }
    bind[`label${name}`] = {}
  }
  return <QtForm form={ADVANCED} bind={bind} />
}

// ── Transform snap ───────────────────────────────────────────────────────────────────────────────────────────────
/** The Transform task's snap steps (Move, Rotate): not a FreeCAD page, but the setting of the Transform dragger's Dragger box, kept with the other Display pages. */
const SNAP: UiForm = { title: 'Transform snap', root: { c: 'QWidget', n: 'DlgSettingsTransformSnap', l: { t: 'V', i: [
  { w: { c: 'QGroupBox', n: 'groupSnap', p: { title: 'Snapping' }, fc: { h: [0, 0], pol: 'PP' }, l: { t: 'G', i: [
    { r: 0, c: 0, w: { c: 'QLabel', n: 'labelSnapMove', p: { text: 'Move', toolTip: 'The step of the Transform dragger when it moves a part' }, fc: { h: [0, 16], pol: 'PP' } } },
    { r: 0, c: 1, w: { c: 'QWidget', n: 'snapMove', fc: { h: [0, 27], pol: 'mF' } } },
    { r: 1, c: 0, w: { c: 'QLabel', n: 'labelSnapRotate', p: { text: 'Rotate', toolTip: 'The step of the Transform dragger when it turns a part' }, fc: { h: [0, 16], pol: 'PP' } } },
    { r: 1, c: 1, w: { c: 'QWidget', n: 'snapRotate', fc: { h: [0, 27], pol: 'mF' } } },
  ] } } },
  { s: { o: 'v', t: 'Expanding', w: 20, h: 40 } },
] } } }
export function TransformSnapPage() {
  const [snap, setSnap] = useState<{ mm: number; deg: number }>(() => saved.get('snap', { mm: 1, deg: 5 }))
  const put = (k: 'mm' | 'deg') => (v: number) => setSnap((x) => { const n = { ...x, [k]: v }; saved.set('snap', n); return n })
  const bind: Bindings = {
    snapMove: { node: <QuantityBox value={snap.mm} dims={LENGTH} min={0} max={2147483647} onChange={put('mm')} />, cls: 'qf-quantity' },
    snapRotate: { node: <QuantityBox value={snap.deg} dims={ANGLE} min={0} max={360} onChange={put('deg')} />, cls: 'qf-quantity' },
  }
  return <QtForm form={SNAP} bind={bind} />
}
