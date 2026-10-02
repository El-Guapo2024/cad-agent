// Std_DlgPreferences: DlgPreferences.ui / DlgPreferencesImp.cpp at FreeCAD main 3160daf1e2b6 — a
// modal "Preferences" window: the groups and their pages in a tree on the left (24px icons) with
// Reset under it, the page's title and "Search preferences…" over the page, OK / Apply / Cancel.
// The pages here are the ones that apply to these projects (resource.cpp registers FreeCAD's).
// Settings take effect as they change; Cancel puts back what was there when the dialog opened
// (or at the last Apply), which is what FreeCAD's deferred apply amounts to.
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { AXIS_COLOR_DEFAULTS, CORNER_POS, NAVICUBE_DEFAULTS, NOTIFY_DEFAULTS, SEL_DEFAULTS, TREE_UI_DEFAULTS, EDITOR_COLORS, OVERLAY_DEFAULTS, type OverlayPrefs, type SelPrefs, getState, saved, setState, useStore } from './store'
import { NAV_DEFAULTS } from './nav'
import { ContextMenu, type Entry } from './chrome'
import { messageBox } from './msgbox'
import { setTreeOption, setTreeUI, setEditorPrefs, editorStyle, setOverlayPrefs, ANIMATION_CURVES } from './actions'
import { api, type CacheInfo } from './api'
import { listCommands } from './cmdreg'
import { commandsByShortcut, defaultAccel, eventSeq, nativeText, resetAllShortcuts, setShortcut, shortcutOf } from './keymap'
import { setUnits } from './commands'
import { PrefsPage } from './panels'
import { BACKGROUND_DEFAULTS, type BackgroundMode, type BackgroundPrefs } from './background'
import { cls } from './panels'
import * as THREE from 'three'
import { QuantityBox, ANGLE } from './qsb'
import { gradientMesh } from './background'
import { LIGHT_DEFAULTS, LightRig, azimuthElevationToDirection, directionToAzimuthElevation, type Light, type LightPrefs } from './lights'

const GROUPS: [string, string, string[]][] = [
  ['General', 'preferences-general', ['General', 'Document', 'Selection', 'Keyboard', 'Cache', 'Notification Area', 'Report View']],
  ['Display', 'preferences-display', ['3D View', 'Light Sources', 'UI', 'Navigation', 'Colors', 'Advanced', 'Transform snap']],
  ['Python', 'preferences-python', ['Macro', 'Python General', 'Editor']],
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
/** The server-side preferences (`cad pref`, userprefs.py) as last read; the pages edit them
 *  through the API so the agent's commands see the same values. */
const SERVER_DEFAULTS: Record<string, number> = { MaxUndoSize: 20, CacheLimit: 500, CachePeriod: 2 }
let serverPrefs: Record<string, number> = { ...SERVER_DEFAULTS }
const serverSubs = new Set<() => void>()
function loadServerPrefs() { return api.prefs().then((r) => { serverPrefs = { ...SERVER_DEFAULTS, ...r.prefs }; serverSubs.forEach((f) => f()) }).catch(() => {}) }
function setServerPref(key: string, value: number) {
  serverPrefs = { ...serverPrefs, [key]: value }; serverSubs.forEach((f) => f())
  void api.setPref(key, value).then((r) => { serverPrefs = { ...SERVER_DEFAULTS, ...r.prefs }; serverSubs.forEach((f) => f()) }).catch(() => {})
}
function useServerPrefs() {
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); serverSubs.add(f); return () => { serverSubs.delete(f) } }, [])
  return serverPrefs
}
/** DlgSettingsDocument.ui: General, Storage, Document Objects, Authoring and License. Of these,
 *  Maximum undo/redo steps applies (the undo journal's cap, `cad pref MaxUndoSize`); the rest is
 *  about FCStd files, recompute and document objects, which projects here don't have. */
function DocumentPage() {
  const sp = useServerPrefs()
  const na = (why: string) => `n/a: ${why}`
  const fcstd = na('projects are folders of Python and TOML files, not FCStd documents')
  const dis = (label: string, on: boolean, tip: string) => <label className="tcheck" title={tip}><input type="checkbox" checked={on} disabled />{label}</label>
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>General</legend>
        <label className="sel-row"><span>Maximum undo/redo steps</span>
          <input type="number" className="qsb pick-radius" min={0} max={99} value={sp.MaxUndoSize} title="How many undo/redo steps should be recorded"
            onChange={(e) => setServerPref('MaxUndoSize', Math.min(99, Math.max(0, Math.round(Number(e.target.value)))))} /></label>
        {dis('Enables async document recomputation', false, na('a part rebuilds in the CAD worker, not the page'))}
        {dis('Allow aborting recomputation', false, na('a rebuild is one worker call'))}
        {dis('Create new document at start up', false, na('the workbench opens the projects in its folders'))}
        <label className="sel-row"><span className="disabled">Document save compression level<br />(0 = none, 9 = highest, 7 = default)</span><input className="qsb pick-radius" value={7} readOnly disabled title={fcstd} /></label>
      </fieldset>
      <fieldset className="tgroup"><legend>Storage</legend>
        {dis('Run AutoRecovery at startup', true, fcstd)}
        {dis('Saving transactions (Auto-save)', false, fcstd)}
        {dis('Discard saved transaction after saving document', false, fcstd)}
        {dis('Save auto-recovery information every 15 min', true, na('every change is written to the project as it is made'))}
        {dis('Add thumbnail to project file when saving', true, fcstd)}
        {dis('Add program icon to the generated thumbnail', false, fcstd)}
        {dis('Maximum number of backup files to keep when resaving document', true, na('the project is under git; undo keeps the journal'))}
        {dis('Use date and FCBak extension', true, fcstd)}
        {dis('Suppress older version warning on save', false, fcstd)}
      </fieldset>
      <fieldset className="tgroup"><legend>Document Objects</legend>
        {dis('Allow duplicate object labels in one document', false, na('a body is named by its key in the assembly, which is unique'))}
        {dis('Disable partial loading of external linked objects', false, na('no linked documents here'))}
      </fieldset>
      <fieldset className="tgroup"><legend>Authoring and License</legend>
        <div className="pref-grid">
          <span className="disabled">Author name</span><input disabled title={fcstd} />
          <span className="disabled">Company</span><input disabled title={fcstd} />
          <span className="disabled">Default license</span><select disabled title={fcstd}><option>All rights reserved</option></select>
          <span className="disabled">License URL</span><input disabled title={fcstd} />
        </div>
      </fieldset>
    </div>
  )
}
/** Page ids that FreeCAD shows under another name: DlgSettingsPythonConsole's title is "General". */
const LABEL: Record<string, string> = { 'Python General': 'General' }
const label = (p: string) => LABEL[p] ?? p
/** DlgSettingsPythonConsole.ui: Console (word wrap, block cursor, save history: the console here
 *  follows them, as its own menu's Word Wrap and Save History do) and Other (n/a). */
function PythonConsolePage() {
  const ed = useStore((s) => s.editorPrefs)
  const check = (lbl: string, on: boolean, f: ((v: boolean) => void) | undefined, tip: string) => (
    <label className="tcheck" title={tip}><input type="checkbox" checked={on} disabled={!f} onChange={(e) => f?.(e.target.checked)} />{lbl}</label>)
  const na = 'n/a: the console runs cad commands, not Python'
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Console</legend>
        {check('Enable word wrap', ed.wordWrap, (wordWrap) => setEditorPrefs({ wordWrap }), 'Words will be wrapped when they exceed available\nhorizontal space in Python console')}
        {check('Enable block cursor', ed.consoleBlock, (consoleBlock) => setEditorPrefs({ consoleBlock }), 'The cursor shape will be a block')}
        {check('Save history', ed.saveHistory, (saveHistory) => { setEditorPrefs({ saveHistory }); if (!saveHistory) saved.set('console.history', []) }, 'Saves Python history across sessions')}
        <label className="sel-row"><span className="disabled">Python profiler interval (ms)</span><input className="qsb pick-radius" value="200 ms" readOnly disabled title={na} /></label>
      </fieldset>
      <fieldset className="tgroup"><legend>Other</legend>
        <label className="sel-row"><span className="disabled">Path to external Python executable (optional)</span><input disabled title={na} /></label>
      </fieldset>
    </div>
  )
}
/** DlgSettingsEditor.ui: Options, Indentation, Display Items (the item list with its font family,
 *  size and colour, and a preview). The macro editor and the console follow the font, Text and
 *  Python output/error colours and indentation; the editor here is plain text, so line numbers,
 *  folding and the syntax colours don't show (n/a). */
const SYNTAX = new Set(['Text', 'Python output', 'Python error'])
const FONTS = ['ui-monospace', 'Menlo', 'Monaco', 'SF Mono', 'Courier New', 'Consolas', 'DejaVu Sans Mono']
function EditorPage() {
  const ed = useStore((s) => s.editorPrefs)
  const [item, setItem] = useState('Text')
  const radio = useId() // the search index renders a copy of every page; keep the groups apart
  const check = (lbl: string, on: boolean, f: ((v: boolean) => void) | undefined, tip: string) => (
    <label className="tcheck" title={tip}><input type="checkbox" checked={on} disabled={!f} onChange={(e) => f?.(e.target.checked)} />{lbl}</label>)
  const spin = (v: number, lo: number, hi: number, f: (v: number) => void, tip: string) => (
    <input type="number" className="qsb pick-radius" min={lo} max={hi} value={v} title={tip} onChange={(e) => f(Math.min(hi, Math.max(lo, Math.round(Number(e.target.value)))))} />)
  const plain = 'n/a: the macro editor here is plain text'
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Options</legend>
        {check('Enable line numbers', true, undefined, plain)}
        {check('Enable block cursor', ed.blockCursor, (blockCursor) => setEditorPrefs({ blockCursor }), 'The cursor shape will be a block')}
        {check('Enable folding', true, undefined, plain)}
      </fieldset>
      <fieldset className="tgroup"><legend>Indentation</legend>
        <label className="sel-row"><span>Tab size</span>{spin(ed.tabSize, 1, 99, (tabSize) => setEditorPrefs({ tabSize }), 'Tabulator raster (how many spaces)')}</label>
        <label className="sel-row"><span>Indent size</span>{spin(ed.indentSize, 1, 99, (indentSize) => setEditorPrefs({ indentSize }), 'How many spaces will be inserted when pressing <Tab>')}</label>
        <label className="tcheck" title="Pressing <Tab> will insert a tabulator with defined tab size"><input type="radio" name={radio} checked={!ed.spaces} onChange={() => setEditorPrefs({ spaces: false })} />Keep tabs</label>
        <label className="tcheck" title="Pressing <Tab> will insert amount of defined indent size"><input type="radio" name={radio} checked={ed.spaces} onChange={() => setEditorPrefs({ spaces: true })} />Insert spaces</label>
      </fieldset>
      <fieldset className="tgroup"><legend>Display Items</legend>
        <div className="ed-items">
          <div className="ed-list" title="Color and font settings will be applied to selected type">
            {Object.keys(EDITOR_COLORS).map((k) => (
              <div key={k} className={cls('ed-item', k === item && 'sel', !SYNTAX.has(k) && 'disabled')} onClick={() => setItem(k)}>{k}</div>))}
          </div>
          <div className="pref-grid">
            <span>Family</span><select value={ed.font} title="Font family to be used for selected code type" onChange={(e) => setEditorPrefs({ font: e.target.value })}>
              {FONTS.map((f) => <option key={f} value={f}>{f === 'ui-monospace' ? 'System fixed font' : f}</option>)}</select>
            <span>Size</span>{spin(ed.fontSize, 1, 99, (fontSize) => setEditorPrefs({ fontSize }), 'Font size to be used for selected code type')}
            <span>Color</span><ColorButton value={ed.colors[item]} set={SYNTAX.has(item) ? (c) => setEditorPrefs({ colors: { ...ed.colors, [item]: c } }) : undefined}
              tip={SYNTAX.has(item) ? undefined : plain} />
          </div>
        </div>
        <span>Preview:</span>
        <pre className="ed-preview" style={editorStyle(ed) as React.CSSProperties}>{'# A macro: one cad command per line\nset demo plate width=40\n'}<span style={{ color: ed.colors['Python output'] }}>{'demo: plate rebuilt (0.4 s)\n'}</span><span style={{ color: ed.colors['Python error'] }}>{'cad set: unknown parameter'}</span></pre>
      </fieldset>
    </div>
  )
}
/** DlgSettingsAdvanced.cpp (generated from OverlayParams.py): its one Overlay group, a grid of
 *  label and spin box per DockOverlay* setting with OverlayParams' ranges, steps, suffixes and
 *  docs. The hint, its delay, hover-or-click and the animation work; the right and top panels
 *  aren't overlaid here, and the pass-through, splitter and layout timings are fixed. */
function AdvancedPage() {
  const p = useStore((s) => s.overlayPrefs)
  type NumKey = { [K in keyof OverlayPrefs]: OverlayPrefs[K] extends number ? K : never }[keyof OverlayPrefs]
  const row = (lbl: string, k: NumKey, lo: number, hi: number, step: number, suffix: string, doc: string, na?: string) => (<>
    <span className={na ? 'disabled' : undefined} title={na ?? doc}>{lbl}</span>
    <span className="pct-box" title={na ?? doc}><input type="number" className="qsb" min={lo} max={hi} step={step} value={p[k]} disabled={!!na}
      onChange={(e) => setOverlayPrefs({ [k]: Math.min(hi, Math.max(lo, Math.round(Number(e.target.value)))) })} />{suffix}</span></>)
  const fixed = (doc: string) => `${doc}\n(fixed here)`
  const noSide = 'n/a: only the left and bottom panels are overlaid here'
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Overlay</legend>
        <div className="pref-grid">
          {row('Delay mouse wheel pass through', 'wheelDelay', 0, 99999, 1, 'ms', '', fixed('Delay capturing mouse wheel event for passing through if it is\npreviously handled by other widget.'))}
          {row('Alpha test radius', 'alphaRadius', 1, 100, 1, 'px', '', fixed('If auto mouse click through is enabled, then this radius\ndefines a region of alpha test under the mouse cursor.'))}
          <label className="tcheck" title={fixed('Leave space for Navigation Cube in dock overlay')}><input type="checkbox" checked={p.checkNaviCube} disabled />Check navigation cube</label><span />
          {row('Hint trigger size', 'hintTriggerSize', 1, 100, 1, 'px', 'Auto hide hint visual display triggering width')}
          {row('Hint width', 'hintSize', 1, 100, 1, 'px', 'Auto hide hint visual display width')}
          {row('Left panel hint offset', 'hintLeftOffset', 0, 10000, 10, 'px', 'Auto hide hint visual display offset for left panel')}
          {row('Left panel hint length', 'hintLeftLength', 0, 10000, 10, 'px', 'Auto hide hint visual display length for left panel. Set to zero to fill the space.')}
          {row('Right panel hint offset', 'hintRightOffset', 0, 10000, 10, 'px', '', noSide)}
          {row('Right panel hint length', 'hintRightLength', 0, 10000, 10, 'px', '', noSide)}
          {row('Top panel hint offset', 'hintTopOffset', 0, 10000, 10, 'px', '', noSide)}
          {row('Top panel hint length', 'hintTopLength', 0, 10000, 10, 'px', '', noSide)}
          {row('Bottom panel hint offset', 'hintBottomOffset', 0, 10000, 10, 'px', 'Auto hide hint visual display offset for bottom panel')}
          {row('Bottom panel hint length', 'hintBottomLength', 0, 10000, 10, 'px', 'Auto hide hint visual display length for bottom panel. Set to zero to fill the space.')}
          {row('Hint delay', 'hintDelay', 0, 1000, 100, 'ms', 'Delay before show hint visual')}
          {row('Splitter auto hide delay', 'splitterHandleTimeout', 0, 99999, 100, 'ms', '', fixed('Overlay splitter handle auto hide delay. Set zero to disable auto hiding.'))}
          <label className="tcheck" title={'Show auto hidden dock overlay on mouse over.\nIf disabled, then show on mouse click.'}><input type="checkbox" checked={p.activateOnHover} onChange={(e) => setOverlayPrefs({ activateOnHover: e.target.checked })} />Activate on hover</label><span />
          {row('Layout delay', 'delay', 0, 5000, 100, 'ms', '', fixed('Overlay layout delay'))}
          {row('Animation duration', 'animationDuration', 0, 5000, 100, 'ms', 'Auto hide animation duration, 0 to disable')}
          <span title="Auto hide animation curve type">Animation curve type</span>
          <select value={p.animationCurve} title="Auto hide animation curve type" onChange={(e) => setOverlayPrefs({ animationCurve: Number(e.target.value) })}>
            {ANIMATION_CURVES.map((c, i) => <option key={c} value={i}>{c}</option>)}</select>
        </div>
      </fieldset>
    </div>
  )
}
/** Gui::AccelLineEdit (Widgets.cpp): records the keys pressed, up to four chords of a sequence;
 *  Backspace or Delete alone clears it. Shows native text, holds portable text. */
function AccelEdit({ value, onChange, readOnly, title }: { value: string; onChange?: (v: string) => void; readOnly?: boolean; title?: string }) {
  return <input className="accel-edit" readOnly value={nativeText(value)} title={title} placeholder={readOnly ? '' : 'Press a shortcut'} disabled={readOnly && !value}
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
/** DlgKeyboard.ui / DlgKeyboardImp.cpp: General (Multi-key sequence delay) and Shortcuts: the
 *  search box, Category, the command list (Icon, Command, Shortcut, Default), Current shortcut,
 *  New shortcut with Assign / Clear / Reset / Reset All, and the Priority List of the commands
 *  that share the shortcut. Shortcuts take effect at once (keymap.ts). */
function KeyboardPage() {
  const user = useStore((s) => s.shortcuts), timeout = useStore((s) => s.shortcutTimeout)
  const [filter, setFilter] = useState('')
  const [cur, setCur] = useState<string | null>(null)
  const [edit, setEdit] = useState('')
  const cmds = useMemo(() => listCommands(), [])
  const names = cmds.map((c) => c.name)
  const q = filter.trim().toLowerCase()
  const shown = cmds.filter((c) => !q || c.name.toLowerCase().includes(q) || c.label.toLowerCase().includes(q))
  const current = cur ? shortcutOf(cur) : ''
  void user // re-render on change: shortcutOf reads the store
  const priority = commandsByShortcut(edit || current, names)
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>General</legend>
        <label className="sel-row"><span>Multi-key sequence delay</span>
          <span className="pct-box" title={'Time in milliseconds to wait for the next keystroke of the current key sequence.\nFor example, pressing F will wait for this time to see if F is part of a longer sequence like F,G.'}>
            <input type="number" className="qsb" min={0} max={10000} step={100} value={timeout}
              onChange={(e) => { const v = Math.min(10000, Math.max(0, Math.round(Number(e.target.value)))); saved.set('shortcutTimeout', v); setState({ shortcutTimeout: v }) }} />ms</span></label>
      </fieldset>
      <fieldset className="tgroup"><legend>Shortcuts</legend>
        <input type="search" placeholder="Type to search…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <label className="sel-row"><span>Category</span><select value="All" title="n/a: commands here aren't grouped into categories"><option value="All">All</option></select></label>
        <div className="kb-list">
          <div className="kb-row kb-head"><span>Command</span><span>Shortcut</span><span>Default</span></div>
          {shown.map((c) => (
            <div key={c.name} className={cls('kb-row', cur === c.name && 'sel')} title={c.name} onClick={() => { setCur(c.name); setEdit('') }}>
              <span>{c.label}</span><span>{nativeText(shortcutOf(c.name))}</span><span>{nativeText(defaultAccel()[c.name] ?? '')}</span></div>))}
        </div>
        <div className="kb-grid">
          <span>Current shortcut</span><AccelEdit value={current} readOnly title="To change a current shortcut enter the new shortcut in the field below and press 'Assign'." />
          <button className="qbtn" disabled={!cur || !edit || edit === current} onClick={() => { setShortcut(cur!, edit); setEdit('') }}>Assign</button>
          <span>New shortcut</span><AccelEdit value={edit} onChange={setEdit} />
          <button className="qbtn" disabled={!cur} onClick={() => { setShortcut(cur!, ''); setEdit('') }}>Clear</button>
          <span /><span />
          <button className="qbtn" disabled={!cur || !(cur in user)} onClick={() => setShortcut(cur!, null)}>Reset</button>
          <span /><span />
          <button className="qbtn" disabled={!Object.keys(user).length} onClick={resetAllShortcuts}>Reset All</button>
        </div>
        <fieldset className="tgroup"><legend>Priority List</legend>
          <div className="kb-list kb-prio">{priority.map((n) => <div key={n} className="kb-row"><span>{n}</span><span>{cmds.find((c) => c.name === n)?.label}</span></div>)}</div>
          <div><button className="qbtn" disabled title="n/a: a shortcut here runs the first command that has it">Move Up</button>
            <button className="qbtn" disabled title="n/a: a shortcut here runs the first command that has it">Move Down</button></div>
        </fieldset>
      </fieldset>
    </div>
  )
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
/** DlgSettingsCacheDirectory.ui: Location (read-only), Check periodically at program start,
 *  Cache size limit, Current cache size and Check Now; the cache is `cad cache`'s (appcache.py). */
function CachePage() {
  const sp = useServerPrefs()
  const [info, setInfo] = useState<CacheInfo | null>(null)
  useEffect(() => { void api.cache().then(setInfo).catch(() => {}) }, [])
  const limits: [string, number][] = [['100 MB', 100], ['300 MB', 300], ['500 MB', 500], ['1 GB', 1024], ['2 GB', 2048], ['3 GB', 3072]]
  if (!limits.some(([, v]) => v === sp.CacheLimit)) limits.push([`${sp.CacheLimit} MB`, sp.CacheLimit])
  return (
    <div className="pref-content">
      <fieldset className="tgroup"><legend>Cache Directory</legend>
        <label className="sel-row"><span>Location (read-only)</span><input readOnly value={info?.dir ?? ''} style={{ flex: 1 }} />
          <button className="qbtn" disabled title="n/a: a browser can't open a folder on this machine">Browse cache directory</button></label>
        <label className="sel-row"><span>Check periodically at program start</span>
          <select value={sp.CachePeriod} onChange={(e) => setServerPref('CachePeriod', Number(e.target.value))}>
            {['Always', 'Daily', 'Weekly', 'Monthly', 'Yearly', 'Never'].map((p, i) => <option key={p} value={i}>{p}</option>)}</select></label>
        <label className="sel-row"><span title="Notify the user if the cache size exceeds the specified limit">Cache size limit</span>
          <select value={sp.CacheLimit} title="Notify the user if the cache size exceeds the specified limit" onChange={(e) => setServerPref('CacheLimit', Number(e.target.value))}>
            {limits.map(([t, v]) => <option key={v} value={v}>{t}</option>)}</select></label>
        <div className="sel-row"><span>Current cache size: {info?.text ?? 'Unknown'}</span>
          <button className="qbtn" onClick={() => { void api.cache().then(checkCache).then(setInfo).catch(() => {}) }}>Check Now</button></div>
      </fieldset>
    </div>
  )
}
/** What each page's settings go back to (Reset Page / Group / All): the store's own defaults. */
const DEFAULTS: Record<string, Record<string, unknown>> = {
  General: { units: { schema: 0, decimals: 2, denominator: 8 }, toolbarIconSize: 24, recentFilesSize: 4 },
  Document: { 'server:MaxUndoSize': 20 },
  Keyboard: { shortcuts: {}, shortcutTimeout: 300 },
  Cache: { 'server:CacheLimit': 500, 'server:CachePeriod': 2 },
  Selection: { selPrefs: SEL_DEFAULTS, tree: { syncView: true, syncSelection: true, preSelection: true, recordSelection: true } },
  'Notification Area': { notifyPrefs: NOTIFY_DEFAULTS },
  '3D View': { corner: { show: true, size: 10 }, axes: false, axisColors: AXIS_COLOR_DEFAULTS, showFPS: false },
  'Light Sources': { lights: LIGHT_DEFAULTS },
  UI: { treeUI: TREE_UI_DEFAULTS },
  Navigation: { nav: 'cad', animate: true, cube: true, navPrefs: NAV_DEFAULTS, homeView: 'Trimetric', newDocCameraScale: 100,
    naviCube: NAVICUBE_DEFAULTS, cubePos: CORNER_POS[1], rotationCenter: { size: 5, color: '#ff0000', alpha: 0.2 }, disableTouchTilt: true },
  Colors: { background: BACKGROUND_DEFAULTS, treeEditColor: '#00abff' },
  Advanced: { overlayPrefs: OVERLAY_DEFAULTS },
  'Transform snap': { snap: { mm: 1, deg: 5 } },
  Macro: { recordGuiCommands: true, guiAsComment: true },
  'Python General': { 'editor:wordWrap': true, 'editor:consoleBlock': false, 'editor:saveHistory': false },
  Editor: { 'editor:blockCursor': false, 'editor:tabSize': 4, 'editor:indentSize': 4, 'editor:spaces': true, 'editor:font': 'ui-monospace', 'editor:fontSize': 10, 'editor:colors': EDITOR_COLORS },
  'Report View': { reportShow: { msg: true, log: true, warn: true, err: true, critical: true }, 'report.showOn': {}, 'report.timecode': true, reportTimecode: true, 'report.colors': {} },
}
function resetPages(pages: string[]) {
  for (const p of pages) for (const [k, v] of Object.entries(DEFAULTS[p] ?? {})) {
    if (k.startsWith('server:')) { setServerPref(k.slice(7), v as number); continue }
    if (k.startsWith('editor:')) { setEditorPrefs({ [k.slice(7)]: v }); continue } // the two pages share one setting
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
const page = (name: string): ReactNode => (name === 'Selection' ? <SelectionPage /> : name === 'Report View' ? <ReportViewPage /> : name === 'Colors' ? <ColorsPage /> : name === 'Light Sources' ? <LightSourcesPage /> : name === 'Document' ? <DocumentPage /> : name === 'Python General' ? <PythonConsolePage /> : name === 'Editor' ? <EditorPage /> : name === 'Advanced' ? <AdvancedPage /> : name === 'Keyboard' ? <KeyboardPage /> : name === 'Cache' ? <CachePage /> : name === 'UI' ? <UIPage /> : <PrefsPage page={name} />)

/** What Cancel puts back: the app's own saved settings and the store fields the pages edit. */
const PREF_KEYS = ['nav', 'animate', 'cube', 'navPrefs', 'homeView', 'newDocCameraScale', 'units', 'corner', 'axes', 'axisColors',
  'showFPS', 'naviCube', 'cubePos', 'rotationCenter', 'disableTouchTilt', 'recordGuiCommands', 'guiAsComment', 'notifyPrefs', 'tree',
  'background', 'treeEditColor', 'lights', 'selPrefs', 'treeUI', 'editorPrefs', 'overlayPrefs', 'shortcuts', 'shortcutTimeout'] as const
function snapshot() {
  const s = getState() as unknown as Record<string, unknown>
  const saved: Record<string, string | null> = {}
  try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i)!; if (k.startsWith('cadui.')) saved[k] = localStorage.getItem(k) } } catch { /* no storage */ }
  return { state: Object.fromEntries(PREF_KEYS.map((k) => [k, s[k]])), saved, server: { ...serverPrefs } }
}
function restore(snap: ReturnType<typeof snapshot>) {
  try {
    for (const k of Object.keys(localStorage)) if (k.startsWith('cadui.') && !(k in snap.saved)) localStorage.removeItem(k)
    for (const [k, v] of Object.entries(snap.saved)) if (v !== null) localStorage.setItem(k, v)
  } catch { /* no storage */ }
  for (const [k, v] of Object.entries(snap.server)) if (serverPrefs[k] !== v) setServerPref(k, v)
  const { units, ...rest } = snap.state as Record<string, unknown>
  setState(rest as never)
  setUnits(units as never)
}

/** DlgPreferencesImp::onButtonResetClicked: Reset Page '…', Reset Group '…', Reset All (asks first). */
function resetEntries(cur: string, done: () => void): Entry[] {
  const group = GROUPS.find(([, , ps]) => ps.includes(cur))!
  return [
    { label: `Reset Page '${label(cur)}'`, title: `Resets the user settings for the page '${label(cur)}'`, onSelect: () => { resetPages([cur]); done() } },
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
  useEffect(() => { if (open) { void loadServerPrefs().then(() => { snap.current = snapshot() }); snap.current = snapshot(); setQuery('') } }, [open])
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
                  {ps.map((p) => <div key={p} className={cur === p ? 'pref-item sel' : 'pref-item'} onClick={() => setCur(p)}>{label(p)}</div>)}
                </div>
              ))}
            </div>
            <button className="qbtn" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setResetAt({ x: r.left, y: r.top - 3 * 25 - 10 }) }}>Reset</button>
            {resetAt && <ContextMenu at={resetAt} onClose={() => setResetAt(null)} entries={resetEntries(cur, () => setGen((g) => g + 1))} />}
          </div>
          <div className="pref-main">
            <div className="pref-head">
              <span className="pref-header">{label(cur)}</span>
              <span className="pref-search">
                <input type="search" placeholder="Search preferences…" value={query} onChange={(e) => setQuery(e.target.value)} />
                {hits.length > 0 && <div className="pref-hits">{hits.map((h, i) => (
                  <div key={i} className="pref-hit" onClick={() => { setCur(h.page); setQuery('') }}><b>{label(h.page)}</b><span>{h.text}</span></div>))}</div>}
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
