import * as M from '@radix-ui/react-menubar'
import { menuKbd } from './keymap'
import { getCommand } from './cmdreg'
import { cmdIcon } from './cmdicons'
import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { IDockviewHeaderActionsProps } from 'dockview-react'
import { getState, report, saved, setState, useStore, viewOf, type DrawStyle, type EditMode, type NavStyle, type Workbench } from './store'
import { NAV_STYLES, type OrbitStyle } from './nav'
import { Icon, type IconName } from './icons'
import { api, type Body } from './api'
import { cls } from './panels'
import { NotificationArea } from './notifications'
import { QComboBox } from './combo'
import { quickMeasure, subInfo, type ViewDir } from './viewer'
import {
  doRedo, doUndo, removePanel, editDefault, getView, hasOpenWindow, hideAll, hideSelection, loadScene, openTask, place, placementOf, runCheck,
  runVerify, selectAll, selectVisible, setDrawStyle, setOrtho, showAll, showPanel, showSelection, subscribeWindow, toggleAll, toggleCube,
  toggleVisibility, toggleBottomPanels, setTreeOption, selBack, selForward, overlayAll, overlayActive, overlayToggle, overlayTransparent, overlayBypass,
  setViewProps, AUTO_MODES, getAutoMode, isTransparentSide, overlaySide, setOverlayAutoMode, sideOfGroup, subscribeOverlay, toggleTransparentSide,
  recordAndRun, type OverlayAutoMode, type Side,
  getDock,
} from './actions'
import { macroEntries, windowsEntries } from './macro'
import { startPage } from './start'
import { fileEntries } from './filemenu'
import { dependencyGraph, editParameters, exportDependencyGraph, loadImage, sceneInspector } from './tools'
import {
  alignToSelection, boxElementSelection, boxSelection, boxZoom, canMeasure, clipping, fullscreen, preferences,
  sendToConsole, setNav, gotoSelection, massProperties, measure, properties, randomColor, recallView, rotateLeft, rotateRight,
  saveImage, searchObjects, selectInstances, storeView, toggleAxisCross, toggleBoundingBox, toggleSelectability, toggleTransparency,
  viewDimetric, viewHome, viewTrimetric, zoomIn, zoomOut, unitsCalculator, demoMode, clarifySelection, setEditMode, alignment, setUnits,
  copySelection, issueCameraPosition, freezeView, clearViews, restoreView, saveViews, loadViews, viewFullscreen, viewDocked, viewIsFullscreen,
} from './commands'
import { SCHEMAS, userString } from './quantity'
import { approveRenders } from './agentwb'

/** FreeCAD's standard views and their keys (CommandView.cpp), plus each one's own command id
 *  (StdCmdViewFront etc. are separate commands, not one parameterised command) for cmdreg.ts and
 *  the macro recorder (sixViews/ToolBar's Individual Views/App.tsx's number keys all read it). */
export const VIEWS: [ViewDir, string, string, string][] = [
  ['iso', 'Isometric', '0', 'Std_ViewIsometric'], ['front', 'Front', '1', 'Std_ViewFront'], ['top', 'Top', '2', 'Std_ViewTop'], ['right', 'Right', '3', 'Std_ViewRight'],
  ['rear', 'Rear', '4', 'Std_ViewRear'], ['bottom', 'Bottom', '5', 'Std_ViewBottom'], ['left', 'Left', '6', 'Std_ViewLeft'],
]
/** FreeCAD's seven draw styles (Std_DrawStyle group; each style is also its own command,
 *  Std_DrawStyleAsIs etc.) and their keys, V, 1 to V, 7. */
export const DRAW_STYLES: [DrawStyle, string, string, IconName, string][] = [
  ['asis', 'As Is', 'V, 1', 'ds-asis', 'Std_DrawStyleAsIs'], ['points', 'Points', 'V, 2', 'ds-points', 'Std_DrawStylePoints'], ['wireframe', 'Wireframe', 'V, 3', 'ds-wireframe', 'Std_DrawStyleWireframe'],
  ['hiddenline', 'Hidden Line', 'V, 4', 'ds-hiddenline', 'Std_DrawStyleHiddenLine'], ['noshading', 'No Shading', 'V, 5', 'ds-noshading', 'Std_DrawStyleNoShading'],
  ['shaded', 'Shaded', 'V, 6', 'ds-shaded', 'Std_DrawStyleShaded'], ['flatlines', 'Flat Lines', 'V, 7', 'ds-flatlines', 'Std_DrawStyleFlatLines'],
]
/** Application::listUserEditModes, plus each mode's own Std_UserEditModeX command id. */
export const EDIT_MODES: [EditMode, string, IconName, string, string][] = [
  ['default', 'Default', 'edit-default', 'The object will be edited using the mode defined internally to be the most appropriate for the object type', 'Std_UserEditModeDefault'],
  ['transform', 'Transform', 'edit-transform', 'The object will have its placement editable with the Std TransformManip command', 'Std_UserEditModeTransform'],
  ['cutting', 'Cutting', 'edit-cutting', 'This edit mode is implemented as available but currently does not seem to be used by any object', 'Std_UserEditModeCutting'],
  ['color', 'Color', 'edit-color', 'The object will have the color of its individual faces editable with the Part FaceAppearances command', 'Std_UserEditModeColor'],
]
const PANELS: [string, string][] = [['tasks', 'Tasks'], ['selection', 'Selection View'], ['model', 'Model'], ['console', 'Console'], ['report', 'Report View'], ['checks', 'Checks']]
const WORKBENCHES: Record<Workbench, { label: string; icon: IconName; name: string }> = {
  agent: { label: 'CAD Agent', icon: 'console', name: 'CADAgentWorkbench' },
  design: { label: 'Part Design', icon: 'wb-design', name: 'PartDesignWorkbench' },
  assembly: { label: 'Assembly', icon: 'wb-assembly', name: 'AssemblyWorkbench' },
  inspection: { label: 'Inspection', icon: 'wb-inspection', name: 'InspectionWorkbench' },
}
/** WorkbenchGroup::refreshWorkbenchList: the workbenches in the order of their internal names
 *  (Gui.listWorkbenches()), the first nine on W, 1 … W, 9. */
export const allWorkbenches = () => (Object.entries(WORKBENCHES) as [Workbench, (typeof WORKBENCHES)[Workbench]][])
  .sort((a, b) => (a[1].name < b[1].name ? -1 : 1))
/** Preferences > Workbenches: the enabled ones in the user's order (Ordered; others after, by name). */
export const workbenchList = () => {
  const { order, disabled, startup } = getState().wbPrefs
  const at = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length)
  return allWorkbenches().filter(([k]) => k === startup || !disabled.includes(k)).sort((a, b) => at(a[0]) - at(b[0]))
}
/** The CAD Agent workbench's own menu (Gui::MenuManager: an addon workbench's menu, inserted right
 *  before Windows — after Macro, see the menu bar below) and toolbar: the cad CLI commands with no
 *  UI of their own yet, status-tip text straight from
 *  `cad <command> --help`. Both show only while the workbench is active, like any FreeCAD addon's. */
const agentEntries = (slug: string | null): Entry[] => [
  { label: 'Check', icon: 'recompute', cmd: 'CADAgent_Check', disabled: !slug, title: 'run every gate and write checks.json (or, with --part, the fast part-only rules)', onSelect: () => openTask('check', '') },
  { label: 'Verify', icon: 'pass', cmd: 'CADAgent_Verify', disabled: !slug, title: 'the verifier: rebuild from source in a fresh process, run every gate, record the verdict with hashes and git commit', onSelect: () => openTask('verify', '') },
  { label: 'Done Gate', icon: 'pending', cmd: 'CADAgent_Done', disabled: !slug, title: 'the gate: exit 0 only if the last verify passed, still matches the files, ran fresh, and (in a repo) verified committed work', onSelect: () => openTask('done', '') },
  'sep',
  { label: 'Cut List…', cmd: 'CADAgent_CutList', disabled: !slug, title: 'stock to order and cut, roughly priced', onSelect: () => openTask('cutlist', '') },
  { label: 'Tables…', icon: 'report', cmd: 'CADAgent_Tables', title: 'hole sizes, tap drills, insert bores, extrusions, densities', onSelect: () => openTask('tables', '') },
  { label: 'Tool Envelope…', icon: 'body', cmd: 'CADAgent_ToolEnvelope', title: 'generate a tool envelope and measure it', onSelect: () => openTask('tool', '') },
  { label: 'Bought Parts…', icon: 'bought', cmd: 'CADAgent_Bought', disabled: !slug, title: 'bought parts: vendor STEP or measured, always with a source', onSelect: () => openTask('bought', '') },
  'sep',
  { label: 'Render…', icon: 'shot', cmd: 'CADAgent_Render', disabled: !slug, title: 'render a part, or the assembly, to a PNG', onSelect: () => openTask('render', '') },
  { label: 'Approve Renders…', cmd: 'CADAgent_ApproveRenders', disabled: !slug, title: 'promote current renders to approved baselines (your call: look at the diff first)', onSelect: approveRenders },
  'sep',
  { label: 'Rules…', icon: 'help', cmd: 'CADAgent_Rules', title: 'every registered check and what it verifies', onSelect: () => openTask('rules', '') },
]

// ── one description of each menu, used by the menu bar and the right-click menus ──
export type Entry = { label: string; kbd?: string; icon?: IconName; /** an icon outside icons.tsx (a URL) */ img?: string; checked?: boolean; disabled?: boolean; onSelect?: () => void; sub?: Entry[]
  /** The menu's default action, drawn bold (QMenu::setDefaultAction). */
  bold?: boolean
  /** Hovering the entry (SelectionMenu::onHover preselects). */
  onHover?: () => void
  title?: string
  /** This entry's FreeCAD command id (cmdreg.ts), if it's a registered one: fireEntry below uses
   *  it to record `cad gui run SLUG <cmd>` while a macro is recording, the way Command::invoke
   *  auto-logs Gui.runCommand(...) for a command that doesn't already record its own line. Left
   *  unset for entries with no single FreeCAD identity (dynamic lists, submenu containers, …). */
  cmd?: string } | 'sep'

const axonometric = (): Entry[] => [
  { label: 'Isometric', kbd: '0', icon: 'iso', cmd: 'Std_ViewIsometric', onSelect: () => getView()?.viewDir('iso') },
  { label: 'Dimetric', icon: 'dimetric', cmd: 'Std_ViewDimetric', onSelect: viewDimetric },
  { label: 'Trimetric', icon: 'trimetric', cmd: 'Std_ViewTrimetric', onSelect: viewTrimetric },
]
const sixViews = (): Entry[] => VIEWS.slice(1).map(([d, label, key, cmd]): Entry => ({ label, kbd: key, icon: d, cmd, onSelect: () => getView()?.viewDir(d) }))
const viewsSub = (): Entry[] => {
  const sel = getState().selected
  return [
    { label: 'Fit All', kbd: 'V, F', icon: 'fit-all', cmd: 'Std_ViewFitAll', onSelect: () => getView()?.fitAll() },
    { label: 'Fit Selection', kbd: 'V, S', icon: 'fit-sel', cmd: 'Std_ViewFitSelection', disabled: !sel.length, onSelect: () => getView()?.fitAll(sel) },
    { label: 'Align to Selection', icon: 'align', cmd: 'Std_AlignToSelection', disabled: !getState().subSel.some((r) => /\.Face\d+$/.test(r)), onSelect: alignToSelection },
    { label: 'Axonometric', icon: 'iso', sub: axonometric() },
    'sep',
    { label: 'Home', kbd: '↖', icon: 'home', cmd: 'Std_ViewHome', onSelect: viewHome },
    ...sixViews(),
    'sep',
    { label: 'Rotate Left', kbd: '⇧←', icon: 'rot-left', cmd: 'Std_ViewRotateLeft', onSelect: rotateLeft },
    { label: 'Rotates Right', kbd: '⇧→', icon: 'rot-right', cmd: 'Std_ViewRotateRight', onSelect: rotateRight },
    'sep',
    { label: 'Store Working View', kbd: '⇧↘', cmd: 'Std_StoreWorkingView', onSelect: storeView },
    { label: 'Recall Working View', kbd: '↘', cmd: 'Std_RecallWorkingView', onSelect: recallView },
  ]
}
const styleSub = (): Entry[] => DRAW_STYLES.map(([s, label, key, icon, cmd]): Entry =>
  ({ label, kbd: key, icon, cmd, checked: getState().drawStyle === s, onSelect: () => setDrawStyle(s) }))
const visibilitySub = (): Entry[] => {
  const any = getState().selected.length > 0
  return [
    { label: 'Toggle Visibility', kbd: 'Space', icon: 'visibility', cmd: 'Std_ToggleVisibility', disabled: !any, onSelect: () => toggleVisibility() },
    { label: 'Show Selection', icon: 'show-sel', cmd: 'Std_ShowSelection', disabled: !any, onSelect: showSelection },
    { label: 'Hide Selection', icon: 'hide', cmd: 'Std_HideSelection', disabled: !any, onSelect: hideSelection },
    { label: 'Select Visible Objects', cmd: 'Std_SelectVisibleObjects', onSelect: selectVisible },
    'sep',
    { label: 'Toggle All Objects', cmd: 'Std_ToggleObjects', onSelect: toggleAll },
    { label: 'Show All Objects', icon: 'show', cmd: 'Std_ShowObjects', onSelect: showAll },
    { label: 'Hide All Objects', cmd: 'Std_HideObjects', onSelect: hideAll },
    'sep',
    { label: 'Toggle Selectability', icon: 'unselectable', cmd: 'Std_ToggleSelectability', disabled: !any, onSelect: toggleSelectability },
  ]
}
/** What FreeCAD offers for selected objects (tree and 3D view context menus). */
export function objectEntries(): Entry[] {
  const s = getState(), one = s.selected.length === 1 ? s.scene?.bodies.find((b) => b.name === s.selected[0]) : undefined
  const params = !!one?.part && Object.values(one.params ?? {}).some((p) => p.editable)
  const any = s.selected.length > 0
  return [
    { label: 'Toggle Visibility', kbd: 'Space', icon: 'visibility', disabled: !any, onSelect: () => toggleVisibility() },
    { label: 'Show Selection', icon: 'show-sel', disabled: !any, onSelect: showSelection },
    { label: 'Hide Selection', icon: 'hide', disabled: !any, onSelect: hideSelection },
    { label: 'Toggle Selectability', icon: 'unselectable', disabled: !any, onSelect: toggleSelectability },
    { label: 'Select All Instances', disabled: !any, onSelect: selectInstances },
    { label: 'Go to Selection', kbd: 'T, G', icon: 'goto-sel', disabled: !any, onSelect: gotoSelection },
    'sep',
    { label: 'Random Color', icon: 'random-color', disabled: !any, onSelect: randomColor },
    { label: 'Toggle Transparency', kbd: 'V, T', icon: 'transparency', disabled: !any, onSelect: toggleTransparency },
    'sep',
    ...(one ? [
      ...(params ? [{ label: 'Edit parameters…', icon: 'body', onSelect: () => editDefault(one.name) } as Entry] : []),
      { label: 'Transform', icon: 'transform', onSelect: () => openTask('transform', one.name) } as Entry,
      { label: 'Placement', icon: 'placement', onSelect: () => openTask('placement', one.name) } as Entry,
      ...(one.placement ? [{ label: "Reset to the code's position", onSelect: () => place(one.name, placementOf(one), null) } as Entry] : []),
      'sep' as const,
    ] : []),
    { label: 'Measure', icon: 'measure', disabled: !canMeasure(), onSelect: measure },
    { label: 'Mass Properties', disabled: !any, onSelect: massProperties },
    { label: 'Send to Console', kbd: '⇧⌘P', icon: 'console', disabled: !any, onSelect: sendToConsole },
  ]
}
/** The tree's menu (TreeWidget::contextMenuEvent): on an object, its own action first, the
 *  selection's commands (StdWorkbench::setupContextMenu "Tree"), Properties, then the tree's
 *  own; on the document, the document's actions. */
export function treeEntries(on: 'object' | 'document' = 'object'): Entry[] {
  const s = getState(), any = s.selected.length > 0
  const one = s.selected.length === 1 ? s.scene?.bodies.find((b) => b.name === s.selected[0]) : undefined
  const showHidden: Entry = { label: 'Show Items Hidden in Tree View', checked: s.treeShowHidden, onSelect: () => setState((x) => ({ treeShowHidden: !x.treeShowHidden })) }
  if (on === 'document') {
    return [showHidden,
      { label: 'Open File Location', icon: 'open', onSelect: openFileLocation },
      { label: 'Search Objects', onSelect: searchObjects },
      { label: 'Mark to Recompute', icon: 'recompute', onSelect: runCheck },
      ...(any ? ['sep' as const, ...selectionTreeEntries(one)] : [])]
  }
  const own: Entry[] = one ? [{ label: one.part && Object.values(one.params ?? {}).some((p) => p.editable) ? `Edit ${one.name}` : `Transform ${one.name}`, bold: true, onSelect: () => editDefault(one.name) }, 'sep'] : []
  return [...own, ...selectionTreeEntries(one),
    'sep', showHidden,
    { label: 'Toggle Visibility in Tree View', disabled: !any, onSelect: () => setViewProps(s.selected, { showInTree: !viewOf(s, s.selected[0]).showInTree }) },
    'sep',
    { label: 'Mark to Recompute', icon: 'recompute', onSelect: runCheck },
    { label: 'Recompute Object', kbd: '⇧⌘R', icon: 'recompute', onSelect: runCheck },
    'sep', { label: 'Open File Location', icon: 'open', onSelect: openFileLocation }]
}
function selectionTreeEntries(one: Body | undefined): Entry[] {
  return [
    { label: 'Toggle Freeze', disabled: true, title: 'n/a: parts rebuild from source; there is no recompute to freeze' },
    'sep',
    { label: 'Toggle Visibility', kbd: 'Space', icon: 'visibility', onSelect: () => toggleVisibility() },
    { label: 'Show Selection', icon: 'show-sel', onSelect: showSelection },
    { label: 'Hide Selection', icon: 'hide', onSelect: hideSelection },
    { label: 'Toggle Selectability', icon: 'unselectable', onSelect: toggleSelectability },
    { label: 'Select All Instances', onSelect: selectInstances },
    'sep',
    { label: 'Random Color', icon: 'random-color', onSelect: randomColor },
    { label: 'Toggle Transparency', kbd: 'V, T', icon: 'transparency', onSelect: toggleTransparency },
    'sep',
    { label: 'Cut', kbd: '⌘X', icon: 'edit-cut', disabled: true },
    { label: 'Copy', kbd: '⌘C', icon: 'edit-copy', onSelect: copySelection },
    { label: 'Paste', kbd: '⌘V', icon: 'edit-paste', disabled: true },
    { label: 'Delete', kbd: '⌦', icon: 'edit-delete', disabled: true },
    { label: 'Send to Console', kbd: '⇧⌘P', icon: 'console', onSelect: sendToConsole },
    ...(one ? [{ label: 'Transform', icon: 'transform', onSelect: () => openTask('transform', one.name) } as Entry,
      { label: 'Placement', icon: 'placement', onSelect: () => openTask('placement', one.name) } as Entry] : []),
    { label: 'Properties', kbd: '⌥↵', onSelect: properties },
  ]
}
/** The tree's Open file location: the selected part's file, or the project folder, in the file manager. */
function openFileLocation() {
  const s = getState(), b = s.selected.length === 1 ? s.scene?.bodies.find((x) => x.name === s.selected[0]) : undefined
  if (!s.slug) return
  api.reveal(s.slug, b?.part ?? undefined).then((r) => report('msg', `Opened ${r.revealed}`)).catch((e) => report('err', `Open file location: ${e}`))
}
/** The 3D view's own menu (right-click on empty space, and under the object entries). */
export function viewEntries(): Entry[] {
  const s = getState(), sel = s.selected
  // StdWorkbench::setupContextMenu, "View" (FreeCAD main): fit, align, draw style,
  // the standard views, the document window; with a selection its commands; with
  // one object, Transform and Placement.
  const one = sel.length === 1 ? s.scene?.bodies.find((b) => b.name === sel[0]) : undefined
  return [
    // StdWorkbench::createLinkMenu: "Link Actions" (Std_LinkMakeGroup, Std_LinkMake) — no App::Links here.
    { label: 'Link Actions', sub: [{ label: 'Make Link Group', disabled: true }, { label: 'Make Link', icon: 'link', disabled: true }] },
    'sep',
    { label: 'Fit All', kbd: 'V, F', icon: 'fit-all', onSelect: () => getView()?.fitAll() },
    { label: 'Fit Selection', kbd: 'V, S', icon: 'fit-sel', disabled: !sel.length, onSelect: () => getView()?.fitAll(sel) },
    { label: 'Align to Selection', icon: 'align', disabled: !s.subSel.some((r) => /\.Face\d+$/.test(r)), onSelect: alignToSelection },
    { label: 'Draw Style', icon: 'ds-asis', sub: styleSub() },
    { label: 'Standard Views', icon: 'views', sub: [...axonometric().slice(0, 1), 'sep', { label: 'Home', kbd: '↖', icon: 'home', onSelect: viewHome },
      ...sixViews(), 'sep', { label: 'Rotate Left', kbd: '⇧←', icon: 'rot-left', onSelect: rotateLeft },
      { label: 'Rotates Right', kbd: '⇧→', icon: 'rot-right', onSelect: rotateRight }] },
    'sep',
    { label: 'Document Window', sub: [
      { label: 'Docked', kbd: 'V, D', checked: !viewIsFullscreen(), onSelect: viewDocked },
      { label: 'Undocked', kbd: 'V, U', disabled: true },
      { label: 'Fullscreen', kbd: 'F11', icon: 'fullscreen', checked: viewIsFullscreen(), onSelect: viewFullscreen }] },
    ...(sel.length ? ['sep' as const,
      { label: 'Toggle Visibility', kbd: 'Space', icon: 'visibility', onSelect: () => toggleVisibility() } as Entry,
      { label: 'Toggle Selectability', icon: 'unselectable', onSelect: toggleSelectability } as Entry,
      { label: 'Go to Selection', kbd: 'T, G', icon: 'goto-sel', onSelect: gotoSelection } as Entry,
      { label: 'Random Color', icon: 'random-color', onSelect: randomColor } as Entry,
      { label: 'Toggle Transparency', kbd: 'V, T', icon: 'transparency', onSelect: toggleTransparency } as Entry,
      'sep' as const,
      { label: 'Delete', kbd: '⌦', icon: 'edit-delete', disabled: true } as Entry,
      { label: 'Send to Console', kbd: '⇧⌘P', icon: 'console', onSelect: sendToConsole } as Entry] : []),
    ...(one ? [{ label: 'Transform', icon: 'transform', onSelect: () => openTask('transform', one.name) } as Entry,
      { label: 'Placement', icon: 'placement', onSelect: () => openTask('placement', one.name) } as Entry] : []),
  ]
}

/** The 3D view's right-click menu (NavigationStyle::openPopupMenu): the object under
 *  the pointer (or the one selected) gives its own actions first, then Clarify
 *  Selection when anything is under the pointer, then the view's menu. */
export function popupEntries(body: string | null, clarify: (() => void) | null): Entry[] {
  const s = getState(), ctx = body ?? (s.selected.length === 1 ? s.selected[0] : null)
  const b = ctx ? s.scene?.bodies.find((x) => x.name === ctx) : undefined
  const own: Entry[] = []
  if (b) {
    const params = !!b.part && Object.values(b.params ?? {}).some((p) => p.editable)
    own.push({ label: params ? `Edit ${b.name}` : `Transform ${b.name}`, bold: true, icon: params ? 'body' : 'transform', onSelect: () => editDefault(b.name) })
    if (b.placement) own.push({ label: "Reset to the code's position", onSelect: () => place(b.name, placementOf(b), null) })
    own.push({ label: 'Measure', icon: 'measure', disabled: !canMeasure(), onSelect: measure },
      { label: 'Mass Properties', disabled: !s.selected.length, onSelect: massProperties })
  }
  return [
    ...(own.length ? [...own, 'sep' as const] : []),
    ...(clarify ? [{ label: 'Clarify Selection', kbd: 'G, G', icon: 'clarify', onSelect: clarify } as Entry, 'sep' as const] : []),
    ...viewEntries(),
  ]
}

/** Std_ClarifySelection's menu (SelectionMenu): what lies under the pointer, by
 *  kind (Object, Face, Edge, Vertex); hovering one preselects it, choosing adds it. */
export function clarifyEntries(picks: { body: string; sub: string | null }[], hover: (p: { body: string; sub: string | null } | null) => void,
  choose: (p: { body: string; sub: string | null }) => void): Entry[] {
  const kinds = ['Object', 'Face', 'Edge', 'Vertex'] as const
  const byKind = new Map<string, { body: string; sub: string | null }[]>()
  const bodies = [...new Set(picks.map((p) => p.body))]
  for (const body of bodies) byKind.set('Object', [...(byKind.get('Object') ?? []), { body, sub: null }]) // addWholeObjectSelection
  for (const p of picks) if (p.sub) { const k = /^[A-Za-z]+/.exec(p.sub)![0]; byKind.set(k, [...(byKind.get(k) ?? []), p]) }
  const item = (p: { body: string; sub: string | null }, text: string): Entry => ({ label: text, onHover: () => hover(p), onSelect: () => choose(p) })
  const out: Entry[] = []
  for (const k of kinds) {
    const list = byKind.get(k)
    if (!list?.length) continue
    // shouldGroupMenu: more than five picks over several objects go in a submenu per object.
    const group = k !== 'Object' && list.length > 5 && new Set(list.map((p) => p.body)).size > 1
    const sub: Entry[] = group
      ? [...new Set(list.map((p) => p.body))].map((body): Entry => ({ label: body, icon: 'part', sub: list.filter((p) => p.body === body).map((p) => item(p, p.sub!)) }))
      : list.map((p) => item(p, p.sub ? `${p.body} (${p.sub})` : p.body))
    out.push({ label: k, sub })
  }
  return out
}

// ── menu bar (QMenuBar) ──────────────────────────────────────────────────────
/** Fires an entry's action, recording it as `cad gui run SLUG <cmd>` while a macro is recording
 *  when the entry names its FreeCAD command (Entry.cmd) — chrome.tsx's one choke point for the
 *  menu/toolbar side of macro recording (App.tsx's key handler calls recordAndRun directly). */
function fireEntry(e: Entry) {
  if (e === 'sep' || e.disabled || !e.onSelect) return
  if (e.cmd) recordAndRun(e.cmd, e.onSelect)
  else e.onSelect()
}
function BarEntry({ e }: { e: Entry }) {
  if (e === 'sep') return <M.Separator className="mb-sep" />
  const lead = <span className="mb-ico">{e.checked ? <span className="mb-check">✓</span> : e.icon ? <Icon name={e.icon} /> : e.img && <img src={e.img} width={16} height={16} alt="" draggable={false} />}</span>
  if (e.sub) {
    return (
      <M.Sub>
        <M.SubTrigger className="mb-item">{lead}{e.label}<span className="mb-kbd">▸</span></M.SubTrigger>
        <M.Portal><M.SubContent className="mb-content" sideOffset={2} alignOffset={-3}>
          {e.sub.map((s, i) => <BarEntry key={i} e={s} />)}</M.SubContent></M.Portal>
      </M.Sub>
    )
  }
  return <M.Item className="mb-item" data-cmd={e.cmd} disabled={e.disabled} onSelect={() => fireEntry(e)} title={e.title}>{lead}{e.label}{menuKbd(e.cmd, e.kbd) && <span className="mb-kbd">{menuKbd(e.cmd, e.kbd)}</span>}</M.Item>
}
function Menu({ label, entries }: { label: string; entries: Entry[] }) {
  return (
    <M.Menu>
      <M.Trigger className="mb-trigger">{label}</M.Trigger>
      <M.Portal><M.Content className="mb-content" align="start" sideOffset={1}>{entries.map((e, i) => <BarEntry key={i} e={e} />)}</M.Content></M.Portal>
    </M.Menu>
  )
}

export function MenuBar() {
  // Re-render when anything the menus show changes.
  const slug = useStore((s) => s.slug), selected = useStore((s) => s.selected)
  const undo = useStore((s) => s.undo), redo = useStore((s) => s.redo)
  useStore((s) => s.ortho); useStore((s) => s.drawStyle); useStore((s) => s.cube); useStore((s) => s.hidden)
  useStore((s) => s.selBoxes); useStore((s) => s.axes); useStore((s) => s.clip); useStore((s) => s.subSel)
  useStore((s) => s.recordingMacro); useStore((s) => s.task)
  useSyncExternalStore(subscribeWindow, hasOpenWindow) // File (Close/Print…) and Windows: the 3D view tab isn't in the store
  const wb = useStore((s) => s.workbench), wbPrefsMenu = useStore((s) => s.wbPrefs), editMode = useStore((s) => s.editMode), toolbars = useStore((s) => s.toolbars), statusBar = useStore((s) => s.statusBar)
  void wbPrefsMenu // the View > Workbench submenu follows Preferences > Workbenches
  const tree = useStore((s) => s.tree), history = useStore((s) => s.selHistory), frozen = useStore((s) => s.frozenViews)
  const setToolbar = (t: string, on: boolean) => setState((s) => { const toolbars = { ...s.toolbars, [t]: on }; saved.set('toolbars', toolbars); return { toolbars } })
  const one = selected.length === 1 ? selected[0] : null
  return (
    <M.Root className="menubar">
      <Menu label="File" entries={fileEntries()} />
      <Menu label="Edit" entries={[
        // Std_Undo / Std_Redo keep their own text ("&Undo"); the steps' names are in the toolbar dropdown.
        { label: 'Undo', kbd: '⌘Z', icon: 'undo', cmd: 'Std_Undo', disabled: !undo.length,
          title: undo[0] ? `Undoes the previous action (${undo[0].name}${undo[0].by === 'agent' ? ', by the agent' : ''})` : 'Undoes the previous action', onSelect: () => doUndo() },
        { label: 'Redo', kbd: '⇧⌘Z', icon: 'redo', cmd: 'Std_Redo', disabled: !redo.length,
          title: redo[0] ? `Redoes a previously undone action (${redo[0].name}${redo[0].by === 'agent' ? ', by the agent' : ''})` : 'Redoes a previously undone action', onSelect: () => doRedo() },
        'sep',
        // The clipboard group. The model is source code, so only Copy has a meaning here: the
        // selection's names, as text (commands.ts copySelection).
        { label: 'Cut', kbd: '⌘X', icon: 'edit-cut', disabled: true, title: 'n/a: parts are source code; removing one is an edit to it' },
        { label: 'Copy', kbd: '⌘C', icon: 'edit-copy', cmd: 'Std_Copy', disabled: !selected.length, onSelect: copySelection, title: 'Copies the selection to the clipboard' },
        { label: 'Paste', kbd: '⌘V', icon: 'edit-paste', disabled: true, title: 'n/a: parts are source code; adding one is an edit to it' },
        { label: 'Duplicate Selection', icon: 'duplicate', disabled: true, title: 'n/a: parts are source code; duplicating one is an edit to it' },
        { label: 'Delete', kbd: '⌦', icon: 'edit-delete', disabled: true, title: 'n/a: parts are source code; deleting one is an edit to it' },
        'sep',
        { label: 'Recompute', kbd: 'F5', icon: 'recompute', cmd: 'Std_Refresh', onSelect: runCheck },
        { label: 'Box Selection', kbd: '⇧B', icon: 'box-select', cmd: 'Std_BoxSelection', onSelect: boxSelection },
        { label: 'Box Element Selection', kbd: '⇧E', icon: 'box-select', cmd: 'Std_BoxElementSelection', onSelect: boxElementSelection },
        { label: 'Select All', kbd: '⌘A', icon: 'select-all', cmd: 'Std_SelectAll', onSelect: selectAll },
        'sep',
        { label: 'Transform', icon: 'transform', cmd: 'Std_TransformManip', disabled: !one, onSelect: () => one && openTask('transform', one) },
        { label: 'Placement', icon: 'placement', cmd: 'Std_Placement', disabled: !one, onSelect: () => one && openTask('placement', one) },
        // Std_Alignment, CommandDoc.cpp: isActive() only with exactly two objects selected.
        { label: 'Align To…', icon: 'align-obj', cmd: 'Std_Alignment', disabled: selected.length !== 2, onSelect: alignment },
        { label: 'Send to Console', kbd: '⇧⌘P', icon: 'console', cmd: 'Std_SendToPythonConsole', disabled: !selected.length, onSelect: sendToConsole },
        { label: 'Properties', kbd: '⌥↵', icon: 'report', cmd: 'Std_Properties', onSelect: properties },
        'sep',
        { label: 'Toggle Edit Mode', icon: 'body', cmd: 'Std_Edit', disabled: !one, onSelect: () => one && editDefault(one) },
        { label: 'Edit Mode', icon: EDIT_MODES.find((m) => m[0] === editMode)![2], sub: EDIT_MODES.map(([m, label, icon, tip, cmd]): Entry => ({ label, icon, cmd, checked: editMode === m, onSelect: () => setEditMode(m), title: tip })) },
        'sep',
        { label: 'Preferences', kbd: '⌘,', cmd: 'Std_DlgPreferences', onSelect: preferences },
      ]} />
      <Menu label="View" entries={[
        { label: 'New 3D View', icon: 'window-new', disabled: true, title: 'n/a: one 3D view per project here' },
        { label: 'Orthographic View', kbd: 'V, O', icon: 'ortho', cmd: 'Std_OrthographicCamera', checked: getState().ortho, onSelect: () => setOrtho(true) },
        { label: 'Perspective View', kbd: 'V, P', icon: 'perspective', cmd: 'Std_PerspectiveCamera', checked: !getState().ortho, onSelect: () => setOrtho(false) },
        { label: 'Fullscreen', kbd: '⌥F11', icon: 'fullscreen', cmd: 'Std_MainFullscreen', onSelect: fullscreen },
        'sep',
        { label: 'Standard Views', icon: 'views', sub: viewsSub() },
        { label: 'Freeze Display', sub: [
          { label: 'Save Views…', disabled: !frozen.length, onSelect: saveViews },
          { label: 'Load Views…', onSelect: loadViews },
          'sep',
          { label: 'Freeze View', kbd: '⇧F', onSelect: freezeView },
          { label: 'Clear Views', disabled: !frozen.length, onSelect: clearViews },
          ...(frozen.length ? ['sep' as const, ...frozen.map((_, i): Entry => ({ label: `Restore View ${i + 1}`, kbd: i < 9 ? `⌘${i + 1}` : undefined, onSelect: () => restoreView(i) }))] : []),
        ] },
        { label: 'Draw Style', icon: 'ds-asis', sub: styleSub() },
        { label: 'Bounding Box', cmd: 'Std_SelBoundingBox', checked: getState().selBoxes, onSelect: toggleBoundingBox },
        'sep',
        { label: 'Zoom', icon: 'zoom-in', sub: [{ label: 'Zoom In', kbd: '⌘+', icon: 'zoom-in', cmd: 'Std_ViewZoomIn', onSelect: zoomIn }, { label: 'Zoom Out', kbd: '⌘-', icon: 'zoom-out', cmd: 'Std_ViewZoomOut', onSelect: zoomOut }, 'sep', { label: 'Box Zoom', kbd: '⌘B', icon: 'zoom-box', cmd: 'Std_ViewBoxZoom', onSelect: boxZoom }] },
        { label: 'Document Window', sub: [
          { label: 'Docked', kbd: 'V, D', cmd: 'Std_ViewDock', checked: !viewIsFullscreen(), onSelect: viewDocked },
          { label: 'Undocked', kbd: 'V, U', disabled: true, title: "n/a: a browser tab can't float the 3D view in its own window" },
          { label: 'Fullscreen', kbd: 'F11', icon: 'fullscreen', cmd: 'Std_ViewFullscreen', checked: viewIsFullscreen(), onSelect: viewFullscreen },
        ] },
        { label: 'Issue Camera Position', icon: 'issue-cam', cmd: 'Std_ViewIvIssueCamPos', disabled: !slug, onSelect: issueCameraPosition },
        { label: 'Toggle Axis Cross', kbd: 'A, C', icon: 'axis-cross', cmd: 'Std_AxisCross', checked: getState().axes, onSelect: toggleAxisCross },
        { label: 'Clipping View', icon: 'clip', cmd: 'Std_ToggleClipPlane', checked: !!getState().clip, onSelect: clipping },
        { label: 'Texture Mapping', icon: 'texture', disabled: true, title: 'n/a: no textures here' },
        'sep',
        { label: 'Visibility', icon: 'visibility', sub: visibilitySub() },
        { label: 'Toggle Navigation/Edit Mode', kbd: '⎋', icon: 'toggle-nav', disabled: true, title: 'Toggles between navigation and edit mode (only while an object is in edit mode)' },
        { label: 'Material', icon: 'material', disabled: true, title: "n/a: materials are set in the part's source" },
        { label: 'Appearance', kbd: '⌘D', icon: 'appearance', cmd: 'Std_SetAppearance', disabled: !selected.length, onSelect: () => openTask('appearance', ''), title: 'Sets the display properties of the selected object' },
        { label: 'Random Color', icon: 'random-color', cmd: 'Std_RandomColor', disabled: !selected.length, onSelect: randomColor },
        { label: 'Toggle Transparency', kbd: 'V, T', icon: 'transparency', cmd: 'Std_ToggleTransparency', disabled: !selected.length, onSelect: toggleTransparency },
        'sep',
        // StdCmdWorkbench: the enabled workbenches by menu text, W, 1 … W, 9 for the first nine.
        { label: 'Workbench', sub: workbenchList().map(([k, w], i): Entry => ({ label: w.label, icon: w.icon, kbd: i < 9 ? `W, ${i + 1}` : undefined, checked: wb === k, onSelect: () => setState({ workbench: k }) })) },
        { label: 'Toolbars', sub: [...TOOLBARS.filter((t) => t !== 'CAD Agent' || wb === 'agent').map((t): Entry => ({ label: t, checked: toolbarOn(toolbars, t), onSelect: () => setToolbar(t, !toolbarOn(toolbars, t)) })),
          ...getState().customToolbars.map((t, k) => [t, k] as const).filter(([t]) => t.wb === 'Global' || t.wb === wb).map(([t, k]): Entry => ({ label: t.name, checked: t.active, onSelect: () => { const customToolbars = getState().customToolbars.map((x, j) => (j === k ? { ...x, active: !x.active } : x)); saved.set('customToolbars', customToolbars); setState({ customToolbars }) } })),
          'sep', { label: 'Lock Toolbars', cmd: 'Std_ToggleToolBarLock', checked: getState().toolbarLock, onSelect: () => { const v = !getState().toolbarLock; setState({ toolbarLock: v }); saved.set('toolbarLock', v) } }] },
        { label: 'Panels', sub: PANELS.map(([id, label]): Entry => ({ label, onSelect: () => showPanel(id) })) },
        { label: 'Overlay Docked Panel', sub: [
          { label: 'Toggle Overlay for All Panels', cmd: 'Std_DockOverlayAll', onSelect: overlayAll, title: 'Toggles overlay mode for all docked panels' },
          { label: 'Toggle Transparent Panels', cmd: 'Std_DockOverlayTransparentAll', onSelect: () => overlayTransparent(true), title: 'Toggles transparent mode for all docked overlay panels' },
          'sep',
          { label: 'Toggle Overlay', cmd: 'Std_DockOverlayToggle', onSelect: overlayActive, title: 'Toggles overlay mode for the docked window under the cursor' },
          { label: 'Toggle Transparent Mode', cmd: 'Std_DockOverlayToggleTransparent', onSelect: () => overlayTransparent(false), title: 'Toggles transparent mode for the docked window under the cursor' },
          'sep',
          { label: 'Bypass Mouse Events in Overlay Panels', kbd: 'T, T', cmd: 'Std_DockOverlayMouseTransparent', onSelect: overlayBypass, title: 'Bypasses all mouse events in docked overlay panels' },
          'sep',
          { label: 'Toggle Left', kbd: '⌘←', cmd: 'Std_DockOverlayToggleLeft', onSelect: () => overlayToggle('left'), title: 'Toggles the visibility of the left overlay panel' },
          { label: 'Toggle Right', kbd: '⌘→', cmd: 'Std_DockOverlayToggleRight', onSelect: () => overlayToggle('right'), title: 'Toggles the visibility of the right overlay panel' },
          { label: 'Toggle Top', kbd: '⌘↑', cmd: 'Std_DockOverlayToggleTop', onSelect: () => overlayToggle('top'), title: 'Toggles the visibility of the top overlay panel' },
          { label: 'Toggle Bottom', kbd: '⌘↓', cmd: 'Std_DockOverlayToggleBottom', onSelect: () => overlayToggle('bottom'), title: 'Toggles the visibility of the bottom overlay panel' },
        ] },
        { label: 'Toggle Bottom Panels', kbd: '⌘0', cmd: 'Std_ToggleBottomPanels', onSelect: toggleBottomPanels },
        'sep',
        { label: 'Link Navigation', sub: [
          { label: 'Go to Linked Object', kbd: 'S, G', icon: 'link-select', disabled: true, title: 'n/a: no App::Link objects here' },
          { label: 'Go to Deepest Linked Object', kbd: 'S, D', icon: 'link-select-final', disabled: true, title: 'n/a: no App::Link objects here' },
          { label: 'Select All Links', icon: 'link-select-all', disabled: true, title: 'n/a: no App::Link objects here' },
        ] },
        { label: 'Tree View Actions', sub: [
          { label: 'Sync View', kbd: 'T, 1', cmd: 'Std_TreeSyncView', checked: tree.syncView, onSelect: () => setTreeOption('syncView', !tree.syncView), title: 'Switches to the 3D view containing the selected item' },
          { label: 'Sync Selection', kbd: 'T, 2', cmd: 'Std_TreeSyncSelection', checked: tree.syncSelection, onSelect: () => setTreeOption('syncSelection', !tree.syncSelection), title: 'Auto expands the tree item when the corresponding object is selected in the 3D view' },
          { label: 'Sync Placement', kbd: 'T, 3', disabled: true, title: 'Adjusts the placement on drag-and-drop of objects across coordinate systems (e.g. in part containers)' },
          { label: 'Preselection', kbd: 'T, 4', cmd: 'Std_TreePreSelection', checked: tree.preSelection, onSelect: () => setTreeOption('preSelection', !tree.preSelection), title: 'Preselects the object in the 3D view when hovering the cursor over the tree item' },
          { label: 'Record Selection', kbd: 'T, 5', cmd: 'Std_TreeRecordSelection', checked: tree.recordSelection, onSelect: () => setTreeOption('recordSelection', !tree.recordSelection), title: 'Records the selection in the tree view in order to go back/forward using the navigation buttons' },
          'sep',
          { label: 'Single Document', checked: true, disabled: true },
          { label: 'Multi Document', disabled: true },
          { label: 'Collapse/Expand', icon: 'tree-collapse', cmd: 'Std_TreeCollapseDocument', onSelect: () => setState((s) => ({ treeCollapsed: !s.treeCollapsed })) },
          'sep',
          { label: 'Initiate Dragging', kbd: 'T, D', icon: 'tree-drag', disabled: true, title: 'n/a: the tree is the assembly, ordered by its source' },
          { label: 'Go to Selection', kbd: 'T, G', icon: 'goto-sel', cmd: 'Std_TreeSelection', disabled: !selected.length, onSelect: gotoSelection },
          'sep',
          { label: 'Selection Back', kbd: 'S, B', cmd: 'Std_SelBack', disabled: !history.back.length, onSelect: selBack },
          { label: 'Selection Forward', kbd: 'S, F', cmd: 'Std_SelForward', disabled: !history.forward.length, onSelect: selForward },
        ] },
        { label: 'Status Bar', checked: statusBar, onSelect: () => { setState({ statusBar: !statusBar }); saved.set('statusBar', !statusBar) } },
      ]} />
      <Menu label="Tools" entries={[
        { label: 'Addon Manager', icon: 'addon', disabled: true, title: 'n/a: no addons here' },
        { label: 'Python Package Manager', icon: 'console', disabled: true, title: 'n/a: no Python environment here' },
        'sep',
        { label: 'Measure', icon: 'measure', cmd: 'Std_Measure', disabled: !canMeasure(), onSelect: measure },
        { label: 'Mass Properties', cmd: 'Std_MassProperties', disabled: !selected.length, onSelect: massProperties },
        { label: 'Units Converter', icon: 'units', cmd: 'Std_UnitsCalculator', onSelect: unitsCalculator },
        { label: 'Clarify Selection', kbd: 'G, G', icon: 'clarify', cmd: 'Std_ClarifySelection', onSelect: clarifySelection },
        'sep',
        { label: 'Load Image…', icon: 'load-image', cmd: 'Std_ViewLoadImage', onSelect: loadImage },
        { label: 'Save Image…', icon: 'shot', cmd: 'Std_ViewScreenShot', onSelect: saveImage },
        { label: 'View Turntable', icon: 'turntable', cmd: 'Std_DemoMode', onSelect: demoMode },
        'sep',
        { label: 'Scene Inspector', icon: 'scene-inspector', cmd: 'Std_SceneInspector', disabled: !slug, onSelect: sceneInspector },
        { label: 'Dependency Graph', icon: 'dependency-graph', cmd: 'Std_DependencyGraph', disabled: !slug, onSelect: dependencyGraph },
        { label: 'Export Dependency Graph…', cmd: 'Std_ExportDependencyGraph', disabled: !slug, onSelect: exportDependencyGraph },
        'sep',
        { label: 'Document Utility', disabled: true, title: 'n/a: no FCStd files here for it to check or recover' },
        { label: 'Edit Parameters', icon: 'dlg-parameter', cmd: 'Std_DlgParameter', onSelect: editParameters },
        { label: 'Customize', icon: 'customize', cmd: 'Std_DlgCustomize', title: 'Customize toolbars and macros', onSelect: () => setState({ customizeOpen: true }) },
      ]} />
      <Menu label="Macro" entries={macroEntries()} />
      {/* Gui::MenuManager: a workbench inserts its own menu(s) with root->insertItem(root->
          findItem("&Windows"), …) — i.e. right before Windows, so after Macro, not before it
          (confirmed in both PartDesign/Gui/Workbench.cpp and Sketcher/Gui/Workbench.cpp at this
          commit). Shown only while CAD Agent is the active workbench, like any FreeCAD addon's. */}
      {wb === 'agent' && <Menu label="CAD Agent" entries={agentEntries(slug)} />}
      <Menu label="Windows" entries={windowsEntries()} />
      <Menu label="Help" entries={[
        { label: "What's This?", kbd: '⇧F1', icon: 'whats-this', onSelect: whatsThis },
        'sep',
        { label: 'Start Page', icon: 'start', cmd: 'Start_Start', onSelect: startPage, title: 'Displays the start page' },
        'sep',
        { label: 'User Documentation', icon: 'web', onSelect: () => openUrl('https://wiki.freecad.org/User_hub') },
        { label: 'FreeCAD Forum', icon: 'web', onSelect: () => openUrl('https://forum.freecad.org') },
        { label: 'Report an Issue', icon: 'web', onSelect: () => openUrl('https://github.com/FreeCAD/FreeCAD/issues') },
        'sep',
        { label: 'Restart in Safe Mode', icon: 'safe-mode', disabled: true, title: "n/a: a browser tab can't restart the app's own process" },
        'sep',
        { label: 'Developers Handbook', icon: 'web', onSelect: () => openUrl('https://freecad.github.io/DevelopersHandbook/') },
        // Std_PythonHelp ("Opens the Python Modules documentation", a local pydoc server of
        // FreeCAD's modules there): the scripting docs here.
        { label: 'Python Modules Documentation', icon: 'console', onSelect: () => openUrl('https://wiki.freecad.org/Power_users_hub') },
        'sep',
        { label: 'FreeCAD Website', icon: 'web', onSelect: () => openUrl('https://www.freecad.org') },
        { label: 'Donate to FreeCAD', icon: 'web', onSelect: () => openUrl('https://www.freecad.org/sponsor') },
        { label: 'About cad-agent', icon: 'help', onSelect: () => report('msg',
          "cad-agent UI, laid out after FreeCAD's development version (main, 2026-09-29). Icons and theme colours are FreeCAD's (LGPL), see ui/public/freecad-icons/README.md.") },
      ]} />
    </M.Root>
  )
}
/** CommandStd.cpp's website commands (Std_FreeCADWebsite etc.): open in a new tab, same as the
 *  user's own browser following a link — never the one this UI runs in. */
const openUrl = (url: string) => { window.open(url, '_blank', 'noopener') }
/** Std_WhatsThis: QWhatsThis::enterWhatsThisMode(), simplified. FreeCAD looks up each widget's
 *  own What's This text (sWhatsThis, usually a help-page id); there's no such page here, so the
 *  next click shows that element's tooltip (`title`) instead, near the pointer, as FreeCAD's
 *  balloon would — close enough to be useful, without a docs backend to back a truer version. */
export function whatsThis() {
  document.body.classList.add('whats-this-cursor')
  const cleanup = () => {
    document.body.classList.remove('whats-this-cursor')
    removeEventListener('click', onPick, true)
    removeEventListener('keydown', onKey, true)
  }
  const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') cleanup() }
  const onPick = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    cleanup()
    const el = (e.target as HTMLElement).closest?.('[title]') as HTMLElement | null
    const box = document.createElement('div')
    box.className = 'whats-this-box'
    box.textContent = el?.getAttribute('title') || 'No description available.'
    box.style.left = `${Math.max(4, Math.min(e.clientX + 8, innerWidth - 260))}px`
    box.style.top = `${Math.max(4, Math.min(e.clientY + 8, innerHeight - 80))}px`
    document.body.appendChild(box)
    const remove = () => { box.remove(); removeEventListener('pointerdown', remove, true); removeEventListener('keydown', removeKey, true) }
    const removeKey = (ke: KeyboardEvent) => { if (ke.key === 'Escape') remove() }
    setTimeout(() => { addEventListener('pointerdown', remove, true); addEventListener('keydown', removeKey, true) })
  }
  addEventListener('click', onPick, true)
  addEventListener('keydown', onKey, true)
}

// ── right-click menu ─────────────────────────────────────────────────────────
function CtxEntry({ e, close }: { e: Entry; close(): void }) {
  const [open, setOpen] = useState(false)
  if (e === 'sep') return <div className="mb-sep" />
  return (
    <div className={cls('mb-item ctx-item', open && 'hl', e.bold && 'bold')} data-disabled={e.disabled || undefined} title={e.title}
      onMouseEnter={() => { setOpen(true); e.onHover?.() }} onMouseLeave={() => setOpen(false)}
      onClick={() => { if (e.disabled || e.sub) return; close(); fireEntry(e) }}>
      <span className="mb-ico">{e.checked ? <span className="mb-check">✓</span> : e.icon ? <Icon name={e.icon} /> : e.img && <img src={e.img} width={16} height={16} alt="" draggable={false} />}</span>
      {e.label}{menuKbd(e.cmd, e.kbd) && <span className="mb-kbd">{menuKbd(e.cmd, e.kbd)}</span>}{e.sub && <span className="mb-kbd">▸</span>}
      {e.sub && open && <div className="mb-content ctx-sub">{e.sub.map((s, i) => <CtxEntry key={i} e={s} close={close} />)}</div>}
    </div>
  )
}
export function ContextMenu({ at, entries, onClose, onLeave }: { at: { x: number; y: number }; entries: Entry[]; onClose(): void; onLeave?: () => void }) {
  useEffect(() => {
    const away = (e: Event) => { if (!(e.target as HTMLElement).closest?.('.ctx')) onClose() }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    addEventListener('pointerdown', away, true)
    addEventListener('keydown', key, true)
    addEventListener('blur', onClose)
    return () => { removeEventListener('pointerdown', away, true); removeEventListener('keydown', key, true); removeEventListener('blur', onClose) }
  }, [onClose])
  const h = entries.length * 25 + 8
  const style = { left: Math.max(0, Math.min(at.x, innerWidth - 250)), top: Math.max(0, Math.min(at.y, innerHeight - h)) }
  return createPortal(
    <div className="mb-content ctx" style={style} onContextMenu={(e) => e.preventDefault()} onMouseLeave={onLeave}>
      {entries.map((e, i) => <CtxEntry key={i} e={e} close={onClose} />)}
    </div>, document.body)
}

// ── toolbar (QToolBar) ───────────────────────────────────────────────────────
/** `cmd`: this button's FreeCAD command id, for the same macro-recording hook as fireEntry (the
 *  toolbar's one choke point for it; most Btns here duplicate an already-tagged menu entry). */
/** ToolBarManager::setToolBarIconSize: every toolbar's icons at General > Size of toolbar icons; the
 *  buttons keep FreeCAD.qss's padding around them (32x31 at 24px). */
const useIconSize = () => useStore((s) => s.toolbarIconSize)
const btnStyle = (n: number) => ({ width: n + 8, height: n + 7 })
function Btn({ icon, title, onClick, disabled, active, cmd }: { icon: IconName; title: string; onClick(): void; disabled?: boolean; active?: boolean; cmd?: string }) {
  const n = useIconSize()
  return <button className={cls('tb-btn', active && 'on')} style={btnStyle(n)} title={title} disabled={disabled} onClick={() => (cmd ? recordAndRun(cmd, onClick) : onClick())}><Icon name={icon} size={n} /></button>
}
const TSep = () => <span className="tb-sep" />

/** A FreeCAD tool button with a drop-down list (Draw style, Standard views). */
function DropButton({ icon, title, entries }: { icon: IconName; title: string; entries: () => Entry[] }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  return (
    <>
      <button className="tb-btn tb-drop" title={title} onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        setAt(at ? null : { x: r.left, y: r.bottom + 1 })
      }}><Icon name={icon} size={useIconSize()} /><span className="tb-caret">▾</span></button>
      {at && <ContextMenu at={at} entries={entries()} onClose={() => setAt(null)} />}
    </>
  )
}
/** Part_SelectFilter (CommandFilter.cpp): a drop-down of the selection gates, showing the active one. */
const SELECT_FILTERS: [Exclude<import('./store').State['selFilter'], null> | null, string, string, string, string][] = [
  ['vertex', 'Vertex Selection', 'vertex-selection', 'Part_VertexSelection', 'Only allows the selection of vertices'],
  ['edge', 'Edge Selection', 'edge-selection', 'Part_EdgeSelection', 'Only allows the selection of edges'],
  ['face', 'Face Selection', 'face-selection', 'Part_FaceSelection', 'Only allows the selection of faces'],
  [null, 'No Selection Filters', 'clear-selection', 'Part_RemoveSelectionGate', 'Clears all selection filters'],
]
export const setSelFilter = (f: import('./store').State['selFilter']) => setState({ selFilter: f, gateMsg: null })
function SelectFilterButton() {
  const f = useStore((s) => s.selFilter)
  const cur = SELECT_FILTERS.find(([k]) => k === f)!
  return <DropButton icon={cur[2] as IconName} title="Selection Filter: changes the selection filter"
    entries={() => SELECT_FILTERS.map(([k, label, icon, cmd, tip]): Entry => ({ label, icon: icon as IconName, cmd, checked: k !== null && f === k, title: tip, onSelect: () => setSelFilter(k) }))} />
}
function DrawStyleButton() {
  const style = useStore((s) => s.drawStyle)
  return <DropButton icon={DRAW_STYLES.find((d) => d[0] === style)![3]} title="Draw Style" entries={styleSub} />
}

/** UndoAction / RedoAction (Action.cpp): a split tool button (QToolButton::MenuButtonPopup) —
 *  unlike DropButton above, the icon itself performs the default action (undo/redo one step) and
 *  only the caret opens the stack (UndoDialog/RedoDialog, DlgUndoRedo.cpp); picking an entry there
 *  walks back/forward to it, `steps` being its 1-based depth in the newest-first list. */
function UndoRedoButton({ kind }: { kind: 'undo' | 'redo' }) {
  const list = useStore((s) => s[kind])
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const top = list[0], label = kind === 'undo' ? 'Undo' : 'Redo', kbd = kind === 'undo' ? '⌘Z' : '⇧⌘Z'
  const run = kind === 'undo' ? doUndo : doRedo
  const tip = `${top ? `${label} ${top.name}` : label} (${kbd})` + (top?.by === 'agent' ? ' — made by the agent' : '')
  return (
    <span className="tb-split">
      <Btn icon={kind} title={tip} cmd={kind === 'undo' ? 'Std_Undo' : 'Std_Redo'} disabled={!list.length} onClick={() => run()} />
      <button className="tb-btn tb-drop" title={`${label} to…`} disabled={!list.length} onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        setAt(at ? null : { x: r.left, y: r.bottom + 1 })
      }}><span className="tb-caret">▾</span></button>
      {at && <ContextMenu at={at} onClose={() => setAt(null)} entries={list.map((h, i): Entry =>
        ({ label: h.name, title: h.by === 'agent' ? 'Made by the agent' : undefined, onSelect: () => run(i + 1) }))} />}
    </span>
  )
}

/** The toolbars (StdWorkbench::setupToolBars, FreeCAD main: File, Edit, Workbench, View,
 *  Individual Views, Structure, Help), each shown per View > Toolbars. */
/** StdWorkbench::setupToolBars, then the workbench's own (Workbench.cpp; the dump in
 *  scripts/fcgui.py): Clipboard, Macro and Individual Views start hidden (DefaultVisibility::Hidden). */
export const TOOLBARS = ['File', 'Edit', 'Clipboard', 'Workbench', 'Macro', 'View', 'Individual Views', 'Structure', 'Help', 'CAD Agent', 'Part Tools'] as const
const HIDDEN_TOOLBARS: readonly string[] = ['Clipboard', 'Macro', 'Individual Views']
const toolbarOn = (shown: Record<string, boolean>, name: string) => shown[name] ?? !HIDDEN_TOOLBARS.includes(name)
/** QToolBar::handle: the 8px grip each toolbar starts with (FreeCAD.qss), gone when locked. */
const TGrip = () => <span className="tb-grip" />
/** A toolbar button for a menu Entry (same icon, text, command and state). */
const EntryBtn = ({ e }: { e: Entry }) => e === 'sep' ? <TSep /> : <Btn icon={e.icon ?? 'help'} title={e.title ?? e.label} cmd={e.cmd} disabled={e.disabled} onClick={() => e.onSelect?.()} />
export function ToolBar() {
  const wb = useStore((s) => s.workbench), wbPrefs = useStore((s) => s.wbPrefs), slug = useStore((s) => s.slug), lock = useStore((s) => s.toolbarLock)
  const selected = useStore((s) => s.selected), busy = useStore((s) => s.busy), subSel = useStore((s) => s.subSel), shown = useStore((s) => s.toolbars)
  useStore((s) => s.recordingMacro)
  const customToolbars = useStore((s) => s.customToolbars), macroCommands = useStore((s) => s.macroCommands)
  const one = selected.length === 1 ? selected[0] : null
  const on = (name: (typeof TOOLBARS)[number]) => toolbarOn(shown, name)
  const na = 'n/a: the assembly\'s structure comes from its source'
  return (
    <div className={cls('toolbar', lock && 'locked')}>
      {on('File') && <><TGrip />
        <Btn icon="new" title="Creates a new empty document" cmd="Std_New" onClick={() => openTask('newDocument', '')} />
        <Btn icon="open" title="Opens a document or imports files" cmd="Std_Open" onClick={() => openTask('openDocument', '')} />
        <Btn icon="save" title="Saves the active document" cmd="Std_Save" disabled onClick={() => {}} /></>}
      {on('Edit') && <><TGrip />
        <UndoRedoButton kind="undo" />
        <UndoRedoButton kind="redo" />
        <TSep />
        <Btn icon="recompute" title="Refresh: re-run the checks" cmd="Std_Refresh" active={busy.includes('check')} onClick={runCheck} /></>}
      {on('Clipboard') && <><TGrip />
        <Btn icon="edit-cut" title="Removes the selection and copies it to the clipboard" disabled onClick={() => {}} />
        <Btn icon="edit-copy" title="Copies the selection to the clipboard" cmd="Std_Copy" disabled={!selected.length} onClick={copySelection} />
        <Btn icon="edit-paste" title="Pastes the contents of the clipboard" disabled onClick={() => {}} /></>}
      {on('Workbench') && <><TGrip />{wbPrefs.selector === 'TabBar' ? (
        // WorkbenchTabWidget: one tab per workbench, styled by WorkbenchSelectorItem.
        <span className="wb-tabs" role="tablist">{workbenchList().map(([k, w], i) => (
          <button key={k} role="tab" className={cls('wb-tab', wb === k && 'sel')} title={`${w.label} (W, ${i + 1})`} onClick={() => setState({ workbench: k })}>
            {wbPrefs.itemStyle !== 2 && <Icon name={w.icon} size={16} />}{wbPrefs.itemStyle !== 1 && w.label}</button>))}</span>
      ) : <label className="wb" title="Switch workbench">
        {wbPrefs.itemStyle !== 2 && <Icon name={WORKBENCHES[wb].icon} size={20} />}
        <QComboBox value={wb} onChange={(e) => setState({ workbench: e.target.value as Workbench })}>
          {workbenchList().map(([k, w]) => <option key={k} value={k}>{w.label}</option>)}
        </QComboBox>
      </label>}</>}
      {on('Macro') && <><TGrip />
        {macroEntries().filter((e) => e !== 'sep' && /^(Record Macro|Stop Macro Recording|Macros|Execute Macro)/.test(e.label)).map((e, i) => <EntryBtn key={i} e={e} />)}</>}
      {on('View') && <><TGrip />
        <Btn icon="fit-all" title="Fit all (V, F)" cmd="Std_ViewFitAll" onClick={() => getView()?.fitAll()} />
        <Btn icon="fit-sel" title="Fit selection (V, S)" cmd="Std_ViewFitSelection" disabled={!selected.length} onClick={() => getView()?.fitAll(selected)} />
        <DropButton icon="views" title="Standard Views" entries={() => [...axonometric(), 'sep', { label: 'Home', kbd: '↖', icon: 'home', cmd: 'Std_ViewHome', onSelect: viewHome }, ...sixViews()]} />
        <Btn icon="align" title="Align to selection: look at the selected face" cmd="Std_AlignToSelection" disabled={!subSel.some((r) => /\.Face\d+$/.test(r))} onClick={alignToSelection} />
        <TSep />
        <DrawStyleButton />
        <SelectFilterButton />
        <TSep />
        <Btn icon="measure" title="Measure: faces, edges, vertices, or two parts" cmd="Std_Measure" disabled={!canMeasure()} onClick={measure} />
        <Btn icon="mass" title="Mass Properties" cmd="Std_MassProperties" disabled={!selected.length} onClick={massProperties} /></>}
      {on('Individual Views') && <><TGrip />
        {VIEWS.map(([d, label, key, cmd]) => <Btn key={d} icon={d} title={`${label} (${key})`} cmd={cmd} onClick={() => getView()?.viewDir(d)} />)}</>}
      {on('Structure') && <><TGrip />
        <Btn icon="std-part" title={`New Part — ${na}`} disabled onClick={() => {}} />
        <Btn icon="std-group" title={`New Group — ${na}`} disabled onClick={() => {}} />
        <Btn icon="link" title={`Link Actions — ${na}`} disabled onClick={() => {}} />
        <Btn icon="varset" title={`Variable Set — ${na}`} disabled onClick={() => {}} /></>}
      {on('Help') && <><TGrip />
        <Btn icon="whats-this" title="What's This?" cmd="Std_WhatsThis" onClick={whatsThis} /></>}
      {/* ToolBarManager: the workbench's own toolbars start a new row (QMainWindow::addToolBarBreak). */}
      <span className="tb-break" />
      {wb === 'agent' && on('CAD Agent') && <><TGrip />
        <Btn icon="recompute" title="Check: run every gate and write checks.json" cmd="CADAgent_Check" disabled={!slug} onClick={() => openTask('check', '')} />
        <Btn icon="pass" title="Verify: rebuild from source in a fresh process and run every gate" cmd="CADAgent_Verify" disabled={!slug} onClick={() => openTask('verify', '')} />
        <Btn icon="pending" title="Done gate: whether the last verify still stands" cmd="CADAgent_Done" disabled={!slug} onClick={() => openTask('done', '')} />
        <TSep />
        <Btn icon="report" title="Tables: hole sizes, tap drills, insert bores, extrusions, densities" cmd="CADAgent_Tables" onClick={() => openTask('tables', '')} />
        <Btn icon="body" title="Tool envelope: generate a tool envelope and measure it" cmd="CADAgent_ToolEnvelope" onClick={() => openTask('tool', '')} />
        <Btn icon="bought" title="Bought parts: vendor STEP or measured, always with a source" cmd="CADAgent_Bought" disabled={!slug} onClick={() => openTask('bought', '')} />
        <TSep />
        <Btn icon="shot" title="Render a part, or the assembly, to a PNG" cmd="CADAgent_Render" disabled={!slug} onClick={() => openTask('render', '')} />
        <TSep />
        <Btn icon="help" title="Rules: every registered check and what it verifies" cmd="CADAgent_Rules" onClick={() => openTask('rules', '')} />
      </>}
      {on('Part Tools') && <><TGrip />
        <Btn icon="visibility" title="Toggle visibility (Space)" cmd="Std_ToggleVisibility" disabled={!selected.length} onClick={() => toggleVisibility()} />
        {wb === 'design' && <Btn icon="body" title="Toggle edit mode: the part's parameters" cmd="Std_Edit" disabled={!one} onClick={() => one && editDefault(one)} />}
        {wb !== 'inspection' && <Btn icon="transform" title="Transform: drag the part" cmd="Std_TransformManip" disabled={!one} onClick={() => one && openTask('transform', one)} />}
        {wb !== 'inspection' && <Btn icon="placement" title="Placement: type the move" cmd="Std_Placement" disabled={!one} onClick={() => one && openTask('placement', one)} />}
        {wb === 'inspection' && <Btn icon="pass" title="Verify (fresh rebuild)" cmd="CADAgent_Verify" active={busy.includes('verify')} onClick={runVerify} />}
      </>}
      {/* Tools > Customize > Toolbars: the user's toolbars for this workbench and the Global ones. */}
      {customToolbars.filter((t) => t.active && (t.wb === 'Global' || t.wb === wb)).map((t, k) => (
        <span key={k} className="tb-group" title={t.name}><TGrip />{t.cmds.map((c, i) => {
          if (c === 'Separator') return <TSep key={i} />
          const cmd = getCommand(c)
          if (!cmd) return null
          const m = macroCommands.find((x) => x.name === c)
          const icon = m ? (m.pixmap as IconName) || null : cmdIcon(c)
          const tip = m?.toolTip || cmd.label()
          return icon ? <Btn key={i} icon={icon} title={tip} cmd={c} disabled={!cmd.isEnabled()} onClick={() => cmd.run([])} />
            : <button key={i} className="tb-btn tb-text" title={tip} disabled={!cmd.isEnabled()} onClick={() => recordAndRun(c, () => cmd.run([]))}>{cmd.label()}</button>
        })}</span>))}
    </div>
  )
}

// ── overlay panel title bar (OverlayWidgets.cpp's OverlayTabWidget) ───────────
/** OverlayToolButton (OverlayWidgets.h 584-589): one action button on an overlay panel's title bar. */
function OvlBtn({ icon, title, onClick, active, rotate }: { icon: IconName; title: string; onClick(): void; active?: boolean; rotate?: boolean }) {
  return <button className={cls('ovl-tbtn', active && 'on')} title={title} onClick={onClick}>
    <Icon name={icon} size={14} className={rotate ? 'ovl-rot' : undefined} /></button>
}
/** refreshIcons/syncAutoMode's per-mode icon (OverlayWidgets.cpp 518-548, 1008-1153), light-theme set. */
const AUTO_MODE_ICONS: Record<OverlayAutoMode, IconName> = {
  none: 'ovl-mode', autohide: 'ovl-autohide', editshow: 'ovl-editshow', edithide: 'ovl-edithide', taskshow: 'ovl-taskshow',
}
/** actAutoMode and its autoModeMenu (OverlayWidgets.cpp 437-446 ctor, 1008-1174 onAction/syncAutoMode):
 *  a DropButton-like button showing the current mode, opening a checkable list of all five. */
function OvlAutoModeBtn({ side, rotate }: { side: Side; rotate: boolean }) {
  const mode = useSyncExternalStore(subscribeOverlay, () => getAutoMode(side))
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const cur = AUTO_MODES.find((m) => m[0] === mode)!
  return (
    <>
      <button className="ovl-tbtn" title={mode === 'none' ? 'Select auto show/hide mode' : cur[2]}
        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt(at ? null : { x: r.left, y: r.bottom + 1 }) }}>
        <Icon name={AUTO_MODE_ICONS[mode]} size={14} className={rotate && mode === 'autohide' ? 'ovl-rot' : undefined} />
      </button>
      {at && <ContextMenu at={at} onClose={() => setAt(null)} entries={AUTO_MODES.map(([m, label, title]): Entry =>
        ({ label, title, checked: mode === m, onSelect: () => setOverlayAutoMode(side, m) }))} />}
    </>
  )
}
/** OverlayManager::createTitleBar (OverlayManager.cpp 1052-1078): Transparent, auto mode, Overlay
 *  and the Std_DockOverlayToggle* command, in that order (the ctor's addAction calls, 422-453).
 *  Passed to DockviewReact as rightHeaderActionsComponent, so it renders once per group; only an
 *  overlaid (floating) model/report group gets buttons, everything else (incl. the 3D view) none. */
export function OverlayTitleActions({ group, location }: IDockviewHeaderActionsProps) {
  const side = sideOfGroup(group)
  const transparent = useSyncExternalStore(subscribeOverlay, () => side !== null && isTransparentSide(side))
  if (!side) return null
  // A docked panel's title bar (OverlayManager::createTitleBar): Toggle overlay, Toggle floating
  // window, Close dock window.
  if (location?.type !== 'floating') return (
    <div className="ovl-titlebtns">
      <OvlBtn icon="ovl-overlay" title="Toggle overlay" onClick={() => overlaySide(side, true)} />
      <OvlBtn icon="ovl-float" title="Toggle floating window (n/a here: panels stay in the window)" onClick={() => {}} />
      <OvlBtn icon="ovl-close" title="Close dock window" onClick={() => { const p = group.activePanel; if (p) removePanel(p) }} />
    </div>
  )
  const rotate = side === 'bottom' // rotateAutoHideIcon, OverlayWidgets.cpp 2161-2180 (no right/top side here)
  return (
    <div className="ovl-titlebtns">
      <OvlBtn icon="ovl-transparent" title="Toggle transparent mode" active={transparent} onClick={() => toggleTransparentSide(side)} />
      <OvlAutoModeBtn side={side} rotate={rotate} />
      <OvlBtn icon="ovl-overlay" title="Toggle overlay" onClick={() => overlaySide(side, false)} />
      <OvlBtn icon={side === 'left' ? 'ovl-toggle-left' : 'ovl-toggle-bottom'}
        title={`Toggles the visibility of the ${side} overlay panel`} onClick={() => overlayToggle(side)} />
    </div>
  )
}

/** Tux's NavigationIndicatorGui.py: a flat button with the style's mouse icon and name (two
 *  trailing spaces, or none when Compact), its menu: Settings (Orbit style, Compact, Tooltip),
 *  then every style. Tooltip on (the default) gives the Mouse Configuration hints. */
const navIcon = (name: string) => `./freecad-icons/Navigation${name.replace(/[- ]/g, '')}_light.svg`
const navLabel = (name: string) => name.replace('Maya-Gesture', 'MayaGesture')
const ORBIT_STYLES: [string, OrbitStyle][] = [['Rounded Arcball', 4], ['Trackball', 1], ['Trackball Classic', 3], ['Free Turntable', 2], ['Turntable', 0]]
function NavButton() {
  const nav = useStore((s) => s.nav), orbit = useStore((s) => s.navPrefs.orbit)
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const [compact, setCompact] = useState(() => saved.get('navIndicator.compact', false))
  const [tip, setTip] = useState(() => saved.get('navIndicator.tooltip', true))
  const cur = NAV_STYLES.find((n) => n.id === nav) ?? NAV_STYLES[1]
  const setOrbit = (o: OrbitStyle) => setState((s) => { const navPrefs = { ...s.navPrefs, orbit: o }; saved.set('navPrefs', navPrefs); return { navPrefs } })
  const entries: Entry[] = [
    { label: 'Settings', sub: [
      { label: 'Orbit style', sub: ORBIT_STYLES.map(([label, o]): Entry => ({ label, checked: orbit === o, onSelect: () => setOrbit(o) })) },
      'sep',
      { label: 'Compact', checked: compact, onSelect: () => { saved.set('navIndicator.compact', !compact); setCompact(!compact) } },
      { label: 'Tooltip', checked: tip, onSelect: () => { saved.set('navIndicator.tooltip', !tip); setTip(!tip) } },
    ] },
    'sep',
    ...NAV_STYLES.map((n): Entry => ({ label: navLabel(n.name), img: navIcon(n.name), checked: nav === n.id, onSelect: () => setNav(n.id) })),
  ]
  return (
    <>
      <button className="sb-ind sb-nav" title={tip ? navHint(nav) : `${cur.name} Navigation style`}
        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt({ x: r.left, y: r.top - (NAV_STYLES.length + 2) * 25 - 12 }) }}>
        <img src={navIcon(cur.name)} width={16} height={16} alt="" />{compact ? '' : `${navLabel(cur.name)}  `}<span className="sb-menu-ind" /></button>
      {at && <ContextMenu at={at} onClose={() => setAt(null)} entries={entries} />}
    </>
  )
}
/** MainWindow's DimensionWidget: what the view spans, in the user's unit system
 *  (dimensionText); its menu picks the unit system. */
function DimensionButton({ size }: { size: [number, number] | null }) {
  const units = useStore((s) => s.units)
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const len = (v: number) => userString({ value: v, dims: [1, 0, 0, 0, 0, 0, 0, 0] }).text
  return (
    <>
      <button className="sb-ind sb-dim" title="Unit System" onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt({ x: r.left, y: r.top - SCHEMAS.length * 25 - 12 }) }}>
        {size ? `${len(size[0])} x ${len(size[1])}` : 'Dimension'}<span className="sb-menu-ind" /></button>
      {at && <ContextMenu at={at} onClose={() => setAt(null)} entries={SCHEMAS.map((x): Entry => ({ label: x.description, checked: units.schema === x.num, onSelect: () => setUnits({ schema: x.num }) }))} />}
    </>
  )
}
/** getPreselectionInfo: each coordinate in the unit system's unit for its size. */
function prePoint(pt: number[], decimals: number) {
  return pt.map((v) => {
    const { factor, unit } = userString({ value: Math.abs(v) > 1e-7 ? v : 0, dims: [1, 0, 0, 0, 0, 0, 0, 0] })
    return `${((Math.abs(v) > 1e-7 ? v : 0) / factor).toFixed(Math.min(6, decimals))} ${unit}`
  }).join(', ')
}
/** DlgSettingsNavigation's Mouse Configuration: how the style selects, pans, rotates and zooms. */
export function navHint(id: NavStyle) {
  const n = NAV_STYLES.find((x) => x.id === id)!
  return `${n.name}\nSelection: ${n.hints[0]}\nPanning: ${n.hints[1]}\nRotation: ${n.hints[2]}\nZooming: ${n.hints[3]}`
}

// ── status bar (QStatusBar) ──────────────────────────────────────────────────
export function StatusBar() {
  const slug = useStore((s) => s.slug), pre = useStore((s) => s.preselected), pt = useStore((s) => s.prePoint)
  const busy = useStore((s) => s.busy), status = useStore((s) => s.status), live = useStore((s) => s.live)
  const building = useStore((s) => s.building), checks = useStore((s) => s.checks)
  const offline = useStore((s) => s.offline), size = useStore((s) => s.viewSize), preSub = useStore((s) => s.preSub)
  const units = useStore((s) => s.units), hints = useStore((s) => s.hints)
  const gateMsg = useStore((s) => s.gateMsg)
  const msg = offline ? `Can't reach cad serve; retrying…`
    : gateMsg ? gateMsg
    : pre ? `Preselected: ${slug}.${preSub ?? pre}${pt ? ` (${prePoint(pt, units.decimals)})` : ''}` // Selection.cpp getPreselectionInfo
    : busy.length ? `Running ${busy.join(', ')}…` : building ? 'Rebuilding…' : 'Ready'
  const fails = (checks?.rows ?? []).filter((r) => r.state === 'FAIL').length
  const open = (checks?.rows ?? []).filter((r) => r.state === 'UNCHECKED').length
  const verdict = status?.done ? 'DONE' : status?.verdict ?? 'NOT VERIFIED'
  // QuickMeasure: the selected elements measured, on the right (not while a task is open).
  const subSel = useStore((s) => s.subSel), task = useStore((s) => s.task)
  const quick = useMemo(() => {
    if (task || !subSel.length || subSel.length > 100) return ''
    const infos = subSel.map((r) => subInfo(getView()?.subGeometry(r) ?? null))
    return infos.every(Boolean) ? quickMeasure(infos as NonNullable<(typeof infos)[number]>[]) : ''
  }, [subSel, task, units])
  // MainWindow::buildStatusBarContextMenu: right-click lists every item by its title, in bar
  // order, checkable; setStatusBarItemEnabled keeps the choice (hStatusBar, one bool per id).
  const [off, setOff] = useState<string[]>(() => saved.get<string[]>('statusbar.off', []))
  const toggleItem = (id: string) => { const next = off.includes(id) ? off.filter((x) => x !== id) : [...off, id]; setOff(next); saved.set('statusbar.off', next) }
  const on = (id: string) => !off.includes(id)
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null)
  // toggleBottomPanelsButton starts checked, and like FreeCAD's only approximates the panels' state.
  const [bottomOn, setBottomOn] = useState(true)
  const items: [string, string][] = [['actionLabel', 'Preselection'], ['hintLabel', 'Input Hints'], ['rightSideLabel', 'Quick Measure'], ['checks', 'Checks'],
    ['verdict', 'Verification'], ['live', 'Live'], ['toggleBottomPanelsButton', 'Bottom Panel Toggle'], ['notificationArea', 'Notifications'], ['navigation', 'Navigation Styles'], ['sizeLabel', 'Unit System']]
  return (
    <div className="statusbar" onContextMenu={(e) => { e.preventDefault(); setMenuAt({ x: e.clientX, y: e.clientY }) }}>
      <span className="sb-msg">{on('actionLabel') ? msg : ''}
        {/* SequencerBar (progressBar, Left slot, order 50): only while something runs; no known
            total, so Qt's busy indicator (range 0..0) */}
        {(building || busy.length > 0) && <span className="sb-progress" role="progressbar" aria-busy="true"><span /></span>}</span>
      {on('hintLabel') && hints.length > 0 && <span className="sb-hints">{hints.map((h, i) => {
        const [before, after = ''] = h.message.split('%1')
        return <span key={i} className="sb-hint">{before}{h.keys.map((k) => <kbd key={k} className="sb-key">{k}</kbd>)}{after}</span>
      })}</span>}
      {on('rightSideLabel') && quick && <span className="sb-item sb-quick" title="Quick measurement of the selection">{quick}</span>}
      {on('checks') && checks?.rows && <span className={cls('sb-item', fails > 0 ? 'fail' : open > 0 && 'open')} onClick={() => showPanel('checks')}>
        {fails ? `${fails} failing` : open ? `${open} unchecked` : 'checks pass'}</span>}
      {on('verdict') && <span className={cls('sb-item verdict', verdict.split(' ')[0].toLowerCase())} title={status?.reasons?.join('\n')} onClick={() => showPanel('checks')}>{verdict}</span>}
      {on('live') && <span className={cls('sb-item live', live && !offline && 'on', offline && 'off')} title={offline ? 'cad serve is not answering' : live ? 'Live: follows file changes' : 'Connecting…'}>●</span>}
      {/* MainWindow.cpp: Bottom Panel Toggle(700), Notifications(800), Navigation Styles(900), Unit System(1000, rightmost). */}
      {on('toggleBottomPanelsButton') && <button className={cls('sb-btn', bottomOn && 'on')} title="Toggles the bottom dock panels"
        onClick={() => { setBottomOn(!bottomOn); toggleBottomPanels() }}><Icon name="toggle-bottom" size={16} /></button>}
      {on('notificationArea') && <NotificationArea />}
      {on('navigation') && <NavButton />}
      {on('sizeLabel') && <DimensionButton size={size} />}
      <span className="sb-grip" aria-hidden />
      {menuAt && <ContextMenu at={menuAt} onClose={() => setMenuAt(null)} entries={items.map(([id, title]): Entry => ({ label: title, checked: on(id), onSelect: () => toggleItem(id) }))} />}
    </div>
  )
}
