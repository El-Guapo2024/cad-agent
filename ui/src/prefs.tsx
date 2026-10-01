// Std_DlgPreferences: DlgPreferences.ui / DlgPreferencesImp.cpp at FreeCAD main 3160daf1e2b6 — a
// modal "Preferences" window: the groups and their pages in a tree on the left (24px icons) with
// Reset under it, the page's title and "Search preferences…" over the page, OK / Apply / Cancel.
// The pages here are the ones that apply to these projects (resource.cpp registers FreeCAD's).
// Settings take effect as they change; Cancel puts back what was there when the dialog opened
// (or at the last Apply), which is what FreeCAD's deferred apply amounts to.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AXIS_COLOR_DEFAULTS, CORNER_POS, NAVICUBE_DEFAULTS, NOTIFY_DEFAULTS, SEL_DEFAULTS, TREE_UI_DEFAULTS, type SelPrefs, getState, saved, setState, useStore } from './store'
import { NAV_DEFAULTS } from './nav'
import { ContextMenu, type Entry } from './chrome'
import { messageBox } from './msgbox'
import { setTreeOption, setTreeUI } from './actions'
import { setUnits } from './commands'
import { PrefsPage } from './panels'
import { BACKGROUND_DEFAULTS, type BackgroundMode, type BackgroundPrefs } from './background'
import { cls } from './panels'
import * as THREE from 'three'
import { QuantityBox, ANGLE } from './qsb'
import { gradientMesh } from './background'
import { LIGHT_DEFAULTS, LightRig, azimuthElevationToDirection, directionToAzimuthElevation, type Light, type LightPrefs } from './lights'

const GROUPS: [string, string, string[]][] = [
  ['General', 'preferences-general', ['General', 'Selection', 'Notification Area', 'Report View']],
  ['Display', 'preferences-display', ['3D View', 'Light Sources', 'UI', 'Navigation', 'Colors', 'Transform snap']],
  ['Python', 'preferences-python', ['Macro']],
]

/** DlgSettingsSelection.ui: Viewport Selection Behavior (each enable with its colour beside it,
 *  the pick radius) and Tree Selection Behavior. */
function SelectionPage() {
  const tree = useStore((s) => s.tree), sp = useStore((s) => s.selPrefs)
  const setSel = (patch: Partial<SelPrefs>) => { const selPrefs = { ...getState().selPrefs, ...patch }; saved.set('selPrefs', selPrefs); setState({ selPrefs }) }
  const check = (label: string, on: boolean, f?: (v: boolean) => void, tip?: string) => (
    <label className="tcheck" title={tip}><input type="checkbox" checked={on} disabled={!f} onChange={(e) => f?.(e.target.checked)} />{label}</label>)
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Viewport Selection Behavior</legend>
        <div className="sel-row">{check('Enable selection', sp.enable, (enable) => setSel({ enable }), 'Enable selection, highlighted with specified color')}
          <ColorButton value={sp.color} set={(color) => setSel({ color })} tip="The color used for highlighting selected objects in the 3D view" /></div>
        <label className="sel-row"><span className="disabled">Radius</span><input className="qsb pick-radius" value="5.0 px" readOnly disabled title="n/a: picking here is three-cad-viewer's ray cast, which has no pick radius" /></label>
        <div className="sel-row">{check('Enable preselection', sp.enablePre, (enablePre) => setSel({ enablePre }), 'Enable preselection, highlighted with specified color')}
          <ColorButton value={sp.preColor} set={(preColor) => setSel({ preColor })} tip="The color used for highlighting preselected objects in the 3D view" /></div>
        {check('Preselect the object in the 3D view when hovering the cursor over the tree item', tree.preSelection, (v) => setTreeOption('preSelection', v))}
      </fieldset>
      <fieldset className="tgroup"><legend>Tree Selection Behavior</legend>
        {check('Auto switch to the 3D view containing the selected item', tree.syncView, (v) => setTreeOption('syncView', v), 'Selecting an item in the Tree View automatically activates its document and switches to its 3D view.')}
        {check('Auto expand tree item when the corresponding object is selected in the 3D view', tree.syncSelection, (v) => setTreeOption('syncSelection', v), 'Locates and reveals the selected object within the tree hierarchy. Prevents manual scrolling in deep, complex document structures.')}
        {check('Record selection in tree view in order to go back/forward using navigation button', tree.recordSelection, (v) => setTreeOption('recordSelection', v), "Enables selection history. Use 'Back' and 'Forward' navigation to toggle between previously selected objects without re-searching the tree.")}
        {check('Add checkboxes for selection in document tree', false, undefined, 'Provides persistent selection toggles for each item. Simplifies batch operations and complex multi-selection without holding modifier keys (Ctrl/Shift).')}
      </fieldset>
    </div>
  )
}
/** A PrefColorButton: the colour, a native picker over it; disabled with no setter. */
function ColorButton({ value, set, tip }: { value: string; set?: (v: string) => void; tip?: string }) {
  return (
    <label className={cls('qbtn color-btn', !set && 'disabled')} title={tip}><span className="color-chip" style={{ background: value }} />
      <input type="color" value={value} disabled={!set} onChange={(e) => set?.(e.target.value)} /></label>)
}
/** DlgSettingsViewColor.ui: Background Color, Tree View, Color Bar. The radios swap the simple
 *  colour for the gradient's (setGradientColorVisibility), the labels follow the gradient's kind,
 *  Switch swaps the first and last colours, Middle color enables the middle one. */
function ColorsPage() {
  const bg = useStore((s) => s.background), editColor = useStore((s) => s.treeEditColor)
  const set = (v: Partial<BackgroundPrefs>) => { const background = { ...getState().background, ...v }; saved.set('background', background); setState({ background }) }
  const gradient = bg.mode !== 'simple'
  const [l1, l2, l3] = bg.mode === 'radial' ? ['Central', 'Midway', 'End'] : ['Top', 'Middle', 'Bottom']
  const radio = (label: string, mode: BackgroundMode, tip: string) => (
    <label className="tcheck" title={tip}><input type="radio" checked={bg.mode === mode} onChange={() => set({ mode })} />{label}</label>)
  const na = (what: string) => `n/a: ${what}`
  return (
    <div className="pref-content">
      <fieldset className="tgroup" title="Background color for the model view"><legend>Background Color</legend>
        <div className="bg-modes">
          {radio('Simple color', 'simple', 'Background will have the selected color')}
          {radio('Linear gradient', 'linear', 'Background will have the selected color gradient')}
          {radio('Radial gradient', 'radial', 'Background will have the selected color gradient')}
          {!gradient && <ColorButton value={bg.color} set={(color) => set({ color })} tip="Background will have the selected color" />}
        </div>
        {gradient && (
          <div className="bg-grid">
            <span /><span>{l1}</span><ColorButton value={bg.top} set={(top) => set({ top })} /><span />
            <button className="qbtn" title="Switches the colors of the gradient" onClick={() => set({ top: bg.bottom, bottom: bg.top })}>Switch</button>
            <span className={cls(!bg.useMid && 'disabled')}>{l2}</span><ColorButton value={bg.mid} set={bg.useMid ? (mid) => set({ mid }) : undefined} />
            <label className="tcheck" title="Color gradient will get the selected color as middle color"><input type="checkbox" checked={bg.useMid} onChange={(e) => set({ useMid: e.target.checked })} />Middle color</label>
            <span /><span>{l3}</span><ColorButton value={bg.bottom} set={(bottom) => set({ bottom })} /><span />
          </div>)}
      </fieldset>
      <fieldset className="tgroup"><legend>Tree View</legend>
        <div className="pref-grid">
          <span>Object being edited</span>
          <ColorButton value={editColor} set={(v) => { saved.set('treeEditColor', v); setState({ treeEditColor: v }) }} tip="Background color for objects in the tree view that are currently edited" />
          <span className="disabled">Active container object</span>
          <ColorButton value="#5bb413" tip={na('no active containers (a part or a body) here')} />
        </div>
      </fieldset>
      <fieldset className="tgroup"><legend>Color Bar</legend>
        <div className="pref-grid">
          <span className="disabled">Label text color</span><ColorButton value="#212529" tip={na('no colour bars here (Mesh and FEM results)')} />
          <span className="disabled">Label text size</span><input type="number" className="qsb" value={13} disabled title={na('no colour bars here (Mesh and FEM results)')} />
        </div>
      </fieldset>
    </div>
  )
}
/** DlgSettingsLightSources::configureViewer: a sphere (radius 3, SoComplexity 1) in createMaterial's
 *  material, seen through an orthographic camera along (0, 1, 0.3), twice as high as viewAll,
 *  lit by the view's own lights and over its background; zoomIn/zoomOut step a 14th of that. */
function LightPreview({ lights }: { lights: LightPrefs }) {
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
    const ro = new ResizeObserver(draw)
    ro.observe(el)
    return () => { ro.disconnect(); rig.dispose(); sphere.geometry.dispose(); renderer.dispose(); renderer.domElement.remove(); ref.current = null }
  }, [bg]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { ref.current?.render(lights) }, [lights])
  return (
    <div className="light-preview">
      <div ref={host} className="light-view" />
      <div className="light-zoom">
        <button className="qbtn" title="Pushes in" onClick={() => ref.current?.zoom(-1)}><img src="./freecad-icons/zoom-in.svg" width={32} height={32} alt="" /></button>
        <button className="qbtn" title="Pulls out" onClick={() => ref.current?.zoom(1)}><img src="./freecad-icons/zoom-out.svg" width={32} height={32} alt="" /></button>
      </div>
    </div>)
}
/** DlgSettingsLightSources.ui: Light Sources (a row per light: enable, horizontal and vertical
 *  angle, colour, intensity; then the ambient light's colour and intensity) over Preview. The
 *  angles are the light's direction as azimuth/elevation (loadSettings/saveSettings convert). */
function LightSourcesPage() {
  const lights = useStore((s) => s.lights)
  const set = (patch: Partial<LightPrefs>) => { const v = { ...getState().lights, ...patch }; saved.set('lights', v); setState({ lights: v }) }
  // The boxes keep what was typed; the stored direction is derived from it (round trips would drift).
  const [angles, setAngles] = useState(() => ({ head: directionToAzimuthElevation(lights.head.dir), back: directionToAzimuthElevation(lights.back.dir), fill: directionToAzimuthElevation(lights.fill.dir) }))
  const pct = (v: number, f: (v: number) => void) => (
    <span className="pct-box"><input type="number" className="qsb" min={0} max={100} value={v} onChange={(e) => f(Math.min(100, Math.max(0, Math.round(Number(e.target.value)))))} />%</span>)
  const row = (k: 'head' | 'back' | 'fill', label: string) => {
    const l = lights[k], [az, el] = angles[k]
    const upd = (p: Partial<Light>) => set({ [k]: { ...l, ...p } })
    const angle = (i: 0 | 1) => (v: number) => {
      const a: [number, number] = i ? [az, v] : [v, el]
      setAngles((x) => ({ ...x, [k]: a }))
      upd({ dir: azimuthElevationToDirection(...a) })
    }
    return (<>
      <label className="tcheck"><input type="checkbox" checked={l.on} onChange={(e) => upd({ on: e.target.checked })} />{label}</label>
      <QuantityBox value={az} dims={ANGLE} onChange={angle(0)} />
      <QuantityBox value={el} dims={ANGLE} onChange={angle(1)} />
      <ColorButton value={l.color} set={(color) => upd({ color })} />
      {pct(l.intensity, (intensity) => upd({ intensity }))}
    </>)
  }
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Light Sources</legend>
        <div className="light-grid">
          <span /><span>Horizontal angle</span><span>Vertical angle</span><span>Color</span><span>Intensity</span>
          {row('head', 'Main light')}
          {row('back', 'Backlight')}
          {row('fill', 'Fill light')}
          <span>Ambient light</span><span /><span />
          <ColorButton value={lights.ambient.color} set={(color) => set({ ambient: { ...lights.ambient, color } })} />
          {pct(lights.ambient.intensity, (intensity) => set({ ambient: { ...lights.ambient, intensity } }))}
        </div>
      </fieldset>
      <fieldset className="tgroup"><legend>Preview</legend><LightPreview lights={lights} /></fieldset>
    </div>
  )
}
/** DlgSettingsUI.ui: Theme Customization (one theme here, so n/a), Tree View (TreeParams, all
 *  live in the tree), Overlay (the property view's scroll bar works; the rest is fixed) and
 *  Suggested Actions (n/a: no task watcher). */
function UIPage() {
  const t = useStore((s) => s.treeUI)
  const check = (label: string, on: boolean, f: ((v: boolean) => void) | undefined, tip: string) => (
    <label className="tcheck" title={tip}><input type="checkbox" checked={on} disabled={!f} onChange={(e) => f?.(e.target.checked)} />{label}</label>)
  const spin = (v: number, lo: number, hi: number, suffix: string, f: (v: number) => void, tip: string) => (
    <span className="pct-box" title={tip}><input type="number" className="qsb" min={lo} max={hi} value={v} onChange={(e) => f(Math.min(hi, Math.max(lo, Math.round(Number(e.target.value)))))} />{suffix}</span>)
  const theme = 'n/a: there is one theme here (FreeCAD Light)'
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Theme Customization</legend>
        <span className="disabled">Customize the current theme. The offered settings are optional for theme developers so they may or may not have an effect in the current theme.</span>
        <div className="pref-grid">
          <span className="disabled">Accent color 1</span><ColorButton value="#00abff" tip={theme} />
          <span className="disabled">Accent color 2</span><ColorButton value="#b477ff" tip={theme} />
          <span className="disabled">Accent color 3</span><ColorButton value="#557bb6" tip={theme} />
          <span className="disabled">Style sheet (advanced)</span><select disabled title={theme}><option>FreeCAD.qss</option></select>
          <span className="disabled">Overlay style sheet</span><select disabled title={theme}><option>Freecad Overlay.qss</option></select>
        </div>
        <div><button className="qbtn" disabled title={theme}>Open Theme Editor</button></div>
      </fieldset>
      <fieldset className="tgroup"><legend>Tree View</legend>
        <div className="pref-grid">
          <span>Font size</span>{spin(t.fontSize, 0, 100, 'pt', (fontSize) => setTreeUI({ fontSize }), 'Font size override, set to 0 for the default value.')}
          <span>Icon size</span>{spin(t.iconSize, 0, 99, '', (iconSize) => setTreeUI({ iconSize }), 'Icon size override, set to 0 for the default value.')}
        </div>
        {check('Show visibility icon', t.visibilityIcon, (visibilityIcon) => setTreeUI({ visibilityIcon }), 'Displays an eye icon in front of the tree view items, showing their visibility status. When clicked the visibility is toggled.')}
        {check('Resizable columns', t.resizableColumn, (resizableColumn) => setTreeUI({ resizableColumn }), 'Allow tree view columns to be manually resized.')}
        {check('Hide description', t.hideColumn, (hideColumn) => setTreeUI({ hideColumn }), 'Hide column with object description in tree view.')}
        {check('Hide internal names', t.hideInternalNames, (hideInternalNames) => setTreeUI({ hideInternalNames }), 'Hide extra tree view column for internal names')}
        {check('Hide scroll bar', t.hideScrollBar, (hideScrollBar) => setTreeUI({ hideScrollBar }), 'Hide scroll bar from the tree view, scrolling will still be possible using mouse wheel.')}
        {check('Hide header', t.hideHeader, (hideHeader) => setTreeUI({ hideHeader }), 'Hide header with column names from the tree view.')}
      </fieldset>
      <fieldset className="tgroup"><legend>Overlay</legend>
        {check('Hide tab bar', true, undefined, 'Hide tab bar in dock overlay (fixed here)')}
        {check('Hint show tab bar', false, undefined, 'Show tab bar on mouse over when auto hide (fixed here)')}
        {check('Hide property view scroll bar', t.hidePropScrollBar, (hidePropScrollBar) => setTreeUI({ hidePropScrollBar }), 'Hide property view scroll bar in dock overlay')}
        {check('Automatically hide in non-3D view', true, undefined, 'n/a: the only view here is the 3D view')}
        {check('Automatically pass through of the mouse cursor', true, undefined, 'Auto mouse click through transparent part of dock overlay. (fixed here)')}
        {check('Automatically pass through of the mouse wheel', true, undefined, 'Automatically passes mouse wheel events through the transparent areas of an overlay panel (fixed here)')}
      </fieldset>
      <fieldset className="tgroup"><legend>Suggested Actions</legend>
        {check('Suggest actions in the task view based on the selection', true, undefined, 'n/a: there is no task watcher here')}
      </fieldset>
    </div>
  )
}
/** What each page's settings go back to (Reset Page / Group / All): the store's own defaults. */
const DEFAULTS: Record<string, Record<string, unknown>> = {
  General: { units: { schema: 0, decimals: 2, denominator: 8 }, toolbarIconSize: 24, recentFilesSize: 4 },
  Selection: { selPrefs: SEL_DEFAULTS, tree: { syncView: true, syncSelection: true, preSelection: true, recordSelection: true } },
  'Notification Area': { notifyPrefs: NOTIFY_DEFAULTS },
  '3D View': { corner: { show: true, size: 10 }, axes: false, axisColors: AXIS_COLOR_DEFAULTS, showFPS: false },
  'Light Sources': { lights: LIGHT_DEFAULTS },
  UI: { treeUI: TREE_UI_DEFAULTS },
  Navigation: { nav: 'cad', animate: true, cube: true, navPrefs: NAV_DEFAULTS, homeView: 'Trimetric', newDocCameraScale: 100,
    naviCube: NAVICUBE_DEFAULTS, cubePos: CORNER_POS[1], rotationCenter: { size: 5, color: '#ff0000', alpha: 0.2 }, disableTouchTilt: true },
  Colors: { background: BACKGROUND_DEFAULTS, treeEditColor: '#00abff' },
  'Transform snap': { snap: { mm: 1, deg: 5 } },
  Macro: { recordGuiCommands: true, guiAsComment: true },
  'Report View': { reportShow: { msg: true, log: true, warn: true, err: true, critical: true }, 'report.showOn': {}, 'report.timecode': true, reportTimecode: true, 'report.colors': {} },
}
function resetPages(pages: string[]) {
  for (const p of pages) for (const [k, v] of Object.entries(DEFAULTS[p] ?? {})) {
    saved.set(k, v)
    if (k === 'units') setUnits(v as never)
    else if (k in getState()) setState({ [k]: v } as never) // the rest (snap, recentFilesSize) live in `saved` only
  }
  applyReportColors()
}
/** DlgSettingsReportView.ui: Output, Colors, Python Interpreter. */
const REPORT_COLORS = { msg: '#000000', log: '#0000ff', warn: '#ffaa00', err: '#ff0000' }
export function applyReportColors() {
  const c = { ...REPORT_COLORS, ...saved.get<Partial<typeof REPORT_COLORS>>('report.colors', {}) }
  for (const [k, v] of Object.entries(c)) document.documentElement.style.setProperty(`--r-${k}`, v)
}
function ReportViewPage() {
  const show = useStore((s) => s.reportShow), timecode = useStore((s) => s.reportTimecode)
  const [showOn, setShowOnRaw] = useState(() => ({ msg: false, log: false, warn: false, err: false, ...saved.get<Record<string, boolean>>('report.showOn', {}) }))
  const [colors, setColors] = useState(() => ({ ...REPORT_COLORS, ...saved.get<Partial<typeof REPORT_COLORS>>('report.colors', {}) }))
  const record = (l: 'msg' | 'log' | 'warn' | 'err', on: boolean) => { const reportShow = { ...getState().reportShow, [l]: on }; saved.set('reportShow', reportShow); setState({ reportShow }) }
  const showOnSet = (l: 'msg' | 'log' | 'warn' | 'err', on: boolean) => { const v = { ...showOn, [l]: on }; setShowOnRaw(v); saved.set('report.showOn', v) }
  const color = (l: keyof typeof REPORT_COLORS, v: string) => { const c = { ...colors, [l]: v }; setColors(c); saved.set('report.colors', c); applyReportColors() }
  const check = (label: string, on: boolean, f: (v: boolean) => void) => <label className="tcheck"><input type="checkbox" checked={on} onChange={(e) => f(e.target.checked)} />{label}</label>
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Output</legend>
        {check('Record normal messages', show.msg, (v) => record('msg', v))}
        {check('Record log messages', show.log, (v) => record('log', v))}
        {check('Record warnings', show.warn, (v) => record('warn', v))}
        {check('Record error messages', show.err, (v) => record('err', v))}
        {check('Show report view on error', showOn.err, (v) => showOnSet('err', v))}
        {check('Show report view on warning', showOn.warn, (v) => showOnSet('warn', v))}
        {check('Show report view on normal message', showOn.msg, (v) => showOnSet('msg', v))}
        {check('Show report view on log message', showOn.log, (v) => showOnSet('log', v))}
        {check('Include a timecode for each entry', timecode, (v) => { saved.set('report.timecode', v); setState({ reportTimecode: v }) })}
      </fieldset>
      <fieldset className="tgroup"><legend>Colors</legend>
        {([['Normal messages', 'msg'], ['Log messages', 'log'], ['Warnings', 'warn'], ['Errors', 'err']] as const).map(([label, l]) => (
          <label key={l} className="tfield"><span>{label}</span><label className="qbtn color-btn"><span className="color-chip" style={{ background: colors[l] }} />
            <input type="color" value={colors[l]} onChange={(e) => color(l, e.target.value)} /></label></label>))}
      </fieldset>
      <fieldset className="tgroup"><legend>Python Interpreter</legend>
        <label className="tcheck" title="n/a: there is no Python interpreter here"><input type="checkbox" checked disabled />Redirect internal Python output to report view</label>
        <label className="tcheck" title="n/a: there is no Python interpreter here"><input type="checkbox" checked disabled />Redirect internal Python errors to report view</label>
      </fieldset>
    </div>
  )
}
const page = (name: string): ReactNode => (name === 'Selection' ? <SelectionPage /> : name === 'Report View' ? <ReportViewPage /> : name === 'Colors' ? <ColorsPage /> : name === 'Light Sources' ? <LightSourcesPage /> : name === 'UI' ? <UIPage /> : <PrefsPage page={name} />)

/** What Cancel puts back: the app's own saved settings and the store fields the pages edit. */
const PREF_KEYS = ['nav', 'animate', 'cube', 'navPrefs', 'homeView', 'newDocCameraScale', 'units', 'corner', 'axes', 'axisColors',
  'showFPS', 'naviCube', 'cubePos', 'rotationCenter', 'disableTouchTilt', 'recordGuiCommands', 'guiAsComment', 'notifyPrefs', 'tree',
  'background', 'treeEditColor', 'lights', 'selPrefs', 'treeUI'] as const
function snapshot() {
  const s = getState() as unknown as Record<string, unknown>
  const saved: Record<string, string | null> = {}
  try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i)!; if (k.startsWith('cadui.')) saved[k] = localStorage.getItem(k) } } catch { /* no storage */ }
  return { state: Object.fromEntries(PREF_KEYS.map((k) => [k, s[k]])), saved }
}
function restore(snap: ReturnType<typeof snapshot>) {
  try {
    for (const k of Object.keys(localStorage)) if (k.startsWith('cadui.') && !(k in snap.saved)) localStorage.removeItem(k)
    for (const [k, v] of Object.entries(snap.saved)) if (v !== null) localStorage.setItem(k, v)
  } catch { /* no storage */ }
  const { units, ...rest } = snap.state as Record<string, unknown>
  setState(rest as never)
  setUnits(units as never)
}

/** DlgPreferencesImp::onButtonResetClicked: Reset Page '…', Reset Group '…', Reset All (asks first). */
function resetEntries(cur: string, done: () => void): Entry[] {
  const group = GROUPS.find(([, , ps]) => ps.includes(cur))!
  return [
    { label: `Reset Page '${cur}'`, title: `Resets the user settings for the page '${cur}'`, onSelect: () => { resetPages([cur]); done() } },
    { label: `Reset Group '${group[0]}'`, title: `Resets the user settings for the group '${group[0]}'`, onSelect: () => { resetPages(group[2]); done() } },
    { label: 'Reset All', title: 'Resets the user settings entirely', onSelect: () => {
      void messageBox('question', 'Clear User Settings', 'Clear all your user settings?\n\nAll settings will be cleared.', ['Yes', 'No'])
        .then((b) => { if (b === 'Yes') { resetPages(Object.keys(DEFAULTS)); done() } })
    } },
  ]
}

export function PreferencesDialog() {
  const open = useStore((s) => s.prefsOpen)
  const [cur, setCur] = useState('General')
  const [query, setQuery] = useState('')
  const snap = useRef<ReturnType<typeof snapshot> | null>(null)
  const index = useRef<HTMLDivElement>(null)
  const [hits, setHits] = useState<{ page: string; text: string }[]>([])
  const [resetAt, setResetAt] = useState<{ x: number; y: number } | null>(null)
  const [gen, setGen] = useState(0) // remounts the page after a reset (Transform snap keeps its own state)
  useEffect(() => { if (open) { snap.current = snapshot(); setQuery('') } }, [open])
  // DlgPreferencesImp's search: every label on every page, shown as "page" over the text.
  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q || !index.current) { setHits([]); return }
    const out: { page: string; text: string }[] = []
    index.current.querySelectorAll<HTMLElement>('[data-page]').forEach((p) => {
      p.querySelectorAll('label, legend, span').forEach((el) => {
        const t = (el.childNodes.length && [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim()) || ''
        if (t && t.toLowerCase().includes(q) && !out.some((h) => h.page === p.dataset.page && h.text === t)) out.push({ page: p.dataset.page!, text: t })
      })
    })
    setHits(out.slice(0, 30))
  }, [query])
  const pages = useMemo(() => GROUPS.flatMap(([, , ps]) => ps), [])
  if (!open) return null
  const close = () => setState({ prefsOpen: false })
  return (
    <div className="msgbox-back" onKeyDown={(e) => { if (e.key === 'Escape') { restore(snap.current!); close() } }}>
      <div className="pref-dlg" role="dialog" aria-label="Preferences">
        <div className="msgbox-title">Preferences</div>
        <div className="pref-body">
          <div className="pref-side">
            <div className="pref-tree">
              {GROUPS.map(([g, icon, ps]) => (
                <div key={g}>
                  <div className="pref-group"><img src={`./freecad-icons/${icon}.svg`} width={24} height={24} alt="" />{g}</div>
                  {ps.map((p) => <div key={p} className={cur === p ? 'pref-item sel' : 'pref-item'} onClick={() => setCur(p)}>{p}</div>)}
                </div>
              ))}
            </div>
            <button className="qbtn" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setResetAt({ x: r.left, y: r.top - 3 * 25 - 10 }) }}>Reset</button>
            {resetAt && <ContextMenu at={resetAt} onClose={() => setResetAt(null)} entries={resetEntries(cur, () => setGen((g) => g + 1))} />}
          </div>
          <div className="pref-main">
            <div className="pref-head">
              <span className="pref-header">{cur}</span>
              <span className="pref-search">
                <input type="search" placeholder="Search preferences…" value={query} onChange={(e) => setQuery(e.target.value)} />
                {hits.length > 0 && <div className="pref-hits">{hits.map((h, i) => (
                  <div key={i} className="pref-hit" onClick={() => { setCur(h.page); setQuery('') }}><b>{h.page}</b><span>{h.text}</span></div>))}</div>}
              </span>
            </div>
            <div className="pref-page" key={gen}>{page(cur)}</div>
          </div>
        </div>
        <div className="pref-buttons">
          <button className="qbtn default" onClick={close}>OK</button>
          <button className="qbtn" onClick={() => { snap.current = snapshot() }}>Apply</button>
          <button className="qbtn" onClick={() => { restore(snap.current!); close() }}>Cancel</button>
        </div>
        {/* The search index: every page rendered off screen. */}
        <div ref={index} className="pref-index" aria-hidden>{pages.map((p) => <div key={p} data-page={p}>{page(p)}</div>)}</div>
      </div>
    </div>
  )
}
