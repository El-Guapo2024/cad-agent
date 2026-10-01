// FreeCAD's command registry (Gui::CommandManager, src/Gui/Command.cpp): every Std_*/CADAgent_*
// command this UI implements, keyed by its FreeCAD id, so an agent can run any of them by name
// (`cad gui run PROJECT COMMAND`; api.ts's GuiState gains "commands", published below) the way
// Gui.runCommand(name,0) does. CommandManager::runCommandByName looks the command up and calls
// invoke(0), which silently no-ops when isActive() is false; commands.ts's applyGuiEvent instead
// says so in the Report view, since an agent can't see a greyed-out menu entry.
//
// Every entry reuses the exact function its menu/toolbar/key entry already calls (chrome.tsx,
// App.tsx, commands.ts, actions.ts, tools.tsx, agentwb.tsx) — nothing here reimplements behaviour,
// only looks it up by name. Left out: permanently disabled n/a placeholders with no onSelect
// (Save, Exit, Customize, Merge Document, …), dynamic list entries with no single identity (Open
// Recent, Recent Macros, Choose a specific window), Print/Print Preview/Export PDF and
// Std_DlgMacroExecuteDirect (their functions are private to filemenu.tsx/macro.tsx, not exported),
// and the Help menu's website openers whose exact FreeCAD id even chrome.tsx's own comment flags
// as unconfirmed, besides Std_WhatsThis and Std_FreeCADWebsite.
import { getState, setState } from './store'
import {
  getView, doUndo, doRedo, runCheck, selectAll, selectVisible, showAll, hideAll, toggleAll, toggleVisibility,
  showSelection, hideSelection, toggleCube, setDrawStyle, setOrtho, showPanel, openTask, closeActiveWindow,
  closeAllWindows, hasOpenWindow, stopRecording, selBack, selForward, setTreeOption, overlayAll, overlayActive,
  overlayToggle, overlayTransparent, overlayBypass, toggleBottomPanels, editDefault, onCommandList,
} from './actions'
import {
  viewHome, viewDimetric, viewTrimetric, rotateLeft, rotateRight, zoomIn, zoomOut, storeView, recallView, boxZoom,
  toggleAxisCross, toggleBoundingBox, toggleTransparency, toggleSelectability, randomColor, selectInstances, gotoSelection,
  alignToSelection, massProperties, measure, canMeasure, clipping, sendToConsole, exportPart, documentInfo, unitsCalculator,
  demoMode, preferences, boxSelection, boxElementSelection, clarifySelection, setEditMode, alignment, fullscreen, saveImage,
  onCommandRegistry, copySelection, issueCameraPosition, viewFullscreen, viewDocked,
} from './commands'
import { editParameters, sceneInspector, dependencyGraph, exportDependencyGraph, loadImage } from './tools'
import { approveRenders, exportPage } from './agentwb'
import { exportCommand } from './filemenu'
import { startPage } from './start'
import { setSelFilter, whatsThis } from './chrome'

export type RegCommand = { label(): string; run(args: string[]): void; isEnabled(): boolean }
export type CommandInfo = { name: string; label: string; enabled: boolean }

type LabelSrc = string | (() => string)
/** One registry entry: `label`/`isEnabled` are read fresh on every publish and every run (selection
 *  etc. change them), the same way a real Command's text()/isActive() are re-queried each time. */
const reg = (label: LabelSrc, run: (args: string[]) => void, isEnabled: () => boolean = () => true): RegCommand =>
  ({ label: typeof label === 'function' ? label : () => label, run, isEnabled })

const sel = () => getState().selected
/** Edit > Transform/Placement/Toggle Edit Mode all gate on "exactly one object selected". */
const oneSelected = () => (sel().length === 1 ? sel()[0] : null)

const COMMANDS: Record<string, RegCommand> = {
  // ── Standard Views (CommandView.cpp: one command per view, not a single parameterised one) ──
  Std_ViewIsometric: reg('Isometric', () => getView()?.viewDir('iso')),
  Std_ViewDimetric: reg('Dimetric', () => viewDimetric()),
  Std_ViewTrimetric: reg('Trimetric', () => viewTrimetric()),
  Std_ViewFront: reg('Front', () => getView()?.viewDir('front')),
  Std_ViewTop: reg('Top', () => getView()?.viewDir('top')),
  Std_ViewRight: reg('Right', () => getView()?.viewDir('right')),
  Std_ViewRear: reg('Rear', () => getView()?.viewDir('rear')),
  Std_ViewBottom: reg('Bottom', () => getView()?.viewDir('bottom')),
  Std_ViewLeft: reg('Left', () => getView()?.viewDir('left')),
  Std_ViewHome: reg('Home', () => viewHome()),
  Std_ViewFitAll: reg('Fit All', () => getView()?.fitAll()),
  Std_ViewFitSelection: reg('Fit Selection', () => getView()?.fitAll(sel()), () => sel().length > 0),
  Std_AlignToSelection: reg('Align to Selection', alignToSelection, () => getState().subSel.some((r) => /\.Face\d+$/.test(r))),
  Std_ViewRotateLeft: reg('Rotate Left', rotateLeft),
  Std_ViewRotateRight: reg('Rotates Right', rotateRight),
  Std_StoreWorkingView: reg('Store Working View', storeView),
  Std_RecallWorkingView: reg('Recall Working View', recallView),
  Std_ViewBoxZoom: reg('Box Zoom', boxZoom),
  Std_ViewZoomIn: reg('Zoom In', zoomIn),
  Std_ViewZoomOut: reg('Zoom Out', zoomOut),
  Std_OrthographicCamera: reg('Orthographic View', () => setOrtho(true)),
  Std_PerspectiveCamera: reg('Perspective View', () => setOrtho(false)),
  Std_MainFullscreen: reg('Fullscreen', fullscreen),
  // View > Document Window (Std_ViewDockUndockFullscreen's actions)
  Std_ViewDock: reg('Docked', viewDocked),
  Std_ViewFullscreen: reg('Fullscreen', viewFullscreen),
  Std_ViewIvIssueCamPos: reg('Issue Camera Position', issueCameraPosition),
  Std_ViewScreenShot: reg('Save Image…', saveImage),
  Std_ViewLoadImage: reg('Load Image…', loadImage),
  Std_ViewNavigationCube: reg('Navigation Cube', toggleCube),

  // ── Draw Style (CommandView.cpp's StdCmdViewGroup: each style is also its own command) ──
  Std_DrawStyleAsIs: reg('As is', () => setDrawStyle('asis')),
  Std_DrawStylePoints: reg('Points', () => setDrawStyle('points')),
  Std_DrawStyleWireframe: reg('Wireframe', () => setDrawStyle('wireframe')),
  Std_DrawStyleHiddenLine: reg('Hidden line', () => setDrawStyle('hiddenline')),
  Std_DrawStyleNoShading: reg('No shading', () => setDrawStyle('noshading')),
  Std_DrawStyleShaded: reg('Shaded', () => setDrawStyle('shaded')),
  Std_DrawStyleFlatLines: reg('Flat lines', () => setDrawStyle('flatlines')),

  // ── Selection / visibility ──
  Std_ToggleVisibility: reg('Toggle Visibility', () => toggleVisibility(), () => sel().length > 0),
  Std_ShowSelection: reg('Show Selection', showSelection, () => sel().length > 0),
  Std_HideSelection: reg('Hide Selection', hideSelection, () => sel().length > 0),
  Std_SelectVisibleObjects: reg('Select Visible Objects', selectVisible),
  Std_ToggleObjects: reg('Toggle All Objects', toggleAll),
  Std_ShowObjects: reg('Show All Objects', showAll),
  Std_HideObjects: reg('Hide All Objects', hideAll),
  Std_ToggleSelectability: reg('Toggle Selectability', toggleSelectability, () => sel().length > 0),
  Std_SelBoundingBox: reg('Bounding Box', toggleBoundingBox),
  Std_AxisCross: reg('Toggle Axis Cross', toggleAxisCross),
  Std_RandomColor: reg('Random Color', randomColor, () => sel().length > 0),
  Std_ToggleTransparency: reg('Toggle Transparency', toggleTransparency, () => sel().length > 0),
  Std_ToggleClipPlane: reg('Clipping View', clipping),
  Std_BoxSelection: reg('Box Selection', boxSelection),
  Std_BoxElementSelection: reg('Box Element Selection', boxElementSelection),
  Std_SelectAll: reg('Select All', selectAll),
  Std_ClarifySelection: reg('Clarify Selection', clarifySelection),
  Std_TreeSelectAllInstances: reg('Select All Instances', selectInstances, () => sel().length > 0),
  Std_TreeSelection: reg('Go to Selection', gotoSelection, () => sel().length > 0),
  Std_SelBack: reg('Selection Back', selBack, () => getState().selHistory.back.length > 0),
  Std_SelForward: reg('Selection Forward', selForward, () => getState().selHistory.forward.length > 0),
  Std_SendToPythonConsole: reg('Send to Console', sendToConsole, () => sel().length > 0),
  Std_MassProperties: reg('Mass Properties', massProperties, () => sel().length > 0),
  Std_Measure: reg('Measure', measure, canMeasure),
  Std_Properties: reg('Properties', () => showPanel('model')),
  Std_SetAppearance: reg('Appearance', () => openTask('appearance', ''), () => sel().length > 0),
  // Part_SelectFilter's gates (CommandFilter.cpp)
  Part_VertexSelection: reg('Vertex Selection', () => setSelFilter('vertex')),
  Part_EdgeSelection: reg('Edge Selection', () => setSelFilter('edge')),
  Part_FaceSelection: reg('Face Selection', () => setSelFilter('face')),
  Part_RemoveSelectionGate: reg('No Selection Filters', () => setSelFilter(null)),
  Start_Start: reg('Start Page', startPage),
  Std_Copy: reg('Copy', copySelection, () => sel().length > 0),

  // ── Edit ──
  Std_Undo: reg('Undo', () => doUndo(), () => getState().undo.length > 0),
  Std_Redo: reg('Redo', () => doRedo(), () => getState().redo.length > 0),
  Std_Refresh: reg('Recompute', runCheck),
  Std_TransformManip: reg('Transform', () => { const n = oneSelected(); if (n) openTask('transform', n) }, () => !!oneSelected()),
  Std_Placement: reg('Placement', () => { const n = oneSelected(); if (n) openTask('placement', n) }, () => !!oneSelected()),
  Std_Alignment: reg('Align To…', alignment, () => sel().length === 2),
  Std_Edit: reg('Toggle Edit Mode', () => { const n = oneSelected(); if (n) editDefault(n) }, () => !!oneSelected()),
  Std_UserEditModeDefault: reg('Default', () => setEditMode('default')),
  Std_UserEditModeTransform: reg('Transform', () => setEditMode('transform')),
  Std_UserEditModeCutting: reg('Cutting', () => setEditMode('cutting')),
  Std_UserEditModeColor: reg('Color', () => setEditMode('color')),
  Std_DlgPreferences: reg('Preferences', preferences),

  // ── Overlay (OverlayWidgets.cpp) ──
  Std_DockOverlayAll: reg('Toggle Overlay for All Panels', overlayAll),
  Std_DockOverlayTransparentAll: reg('Toggle Transparent Panels', () => overlayTransparent(true)),
  Std_DockOverlayToggle: reg('Toggle Overlay', overlayActive),
  Std_DockOverlayToggleTransparent: reg('Toggle Transparent Mode', () => overlayTransparent(false)),
  Std_DockOverlayMouseTransparent: reg('Bypass Mouse Events in Overlay Panels', overlayBypass),
  Std_DockOverlayToggleLeft: reg('Toggle Left', () => overlayToggle('left')),
  Std_DockOverlayToggleRight: reg('Toggle Right', () => overlayToggle('right')),
  Std_DockOverlayToggleTop: reg('Toggle Top', () => overlayToggle('top')),
  Std_DockOverlayToggleBottom: reg('Toggle Bottom', () => overlayToggle('bottom')),
  Std_ToggleBottomPanels: reg('Toggle Bottom Panels', toggleBottomPanels),

  // ── Tree view actions (TreeParams) ──
  Std_TreeSyncView: reg('Sync View', () => setTreeOption('syncView', !getState().tree.syncView)),
  Std_TreeSyncSelection: reg('Sync Selection', () => setTreeOption('syncSelection', !getState().tree.syncSelection)),
  Std_TreePreSelection: reg('Preselection', () => setTreeOption('preSelection', !getState().tree.preSelection)),
  Std_TreeRecordSelection: reg('Record Selection', () => setTreeOption('recordSelection', !getState().tree.recordSelection)),
  // FreeCAD keeps Collapse and Expand as two commands; this UI's "Collapse/Expand" is one toggle.
  Std_TreeCollapseDocument: reg('Collapse/Expand', () => setState((s) => ({ treeCollapsed: !s.treeCollapsed }))),

  // ── Macro (CommandMacro.cpp) ──
  Std_DlgMacroRecord: reg(
    () => (getState().recordingMacro ? 'Stop Macro Recording' : 'Record Macro'),
    () => (getState().recordingMacro ? stopRecording() : openTask('macroRecord', '')),
  ),
  Std_DlgMacroExecute: reg('Macros', () => openTask('macros', ''), () => !getState().recordingMacro),

  // ── Windows (Workbench.cpp's "&Windows"; File menu at this commit per filemenu.tsx) ──
  Std_Windows: reg('Choose Open Window', () => openTask('windows', '')),
  Std_CloseActiveWindow: reg('Close', closeActiveWindow, hasOpenWindow),
  Std_CloseAllWindows: reg('Close All', closeAllWindows, hasOpenWindow),

  // ── File (CommandDoc.cpp; New/Open/Export reinterpreted onto the cad CLI — see filemenu.tsx) ──
  Std_New: reg('New Document', () => openTask('newDocument', '')),
  Std_Open: reg('Open…', () => openTask('openDocument', '')),
  // With a format argument (`cad gui run P Std_Export stl`) straight to the file, else the dialog.
  Std_Export: reg('Export…', (args) => (args[0] ? exportPart(args[0] === 'stl' ? 'stl' : 'step') : exportCommand()), () => !!getState().slug),
  Std_Import: reg('Import…', () => openTask('bought', '', 'import'), () => !!getState().slug),
  Std_ProjectInfo: reg('Document Information', documentInfo, () => !!getState().slug),

  // ── Tools menu additions (tools.tsx) ──
  Std_UnitsCalculator: reg('Units Converter', unitsCalculator),
  Std_DemoMode: reg('View Turntable', demoMode),
  Std_SceneInspector: reg('Scene Inspector', sceneInspector, () => !!getState().slug),
  Std_DependencyGraph: reg('Dependency Graph', dependencyGraph, () => !!getState().slug),
  Std_ExportDependencyGraph: reg('Export Dependency Graph…', exportDependencyGraph, () => !!getState().slug),
  Std_DlgParameter: reg('Edit Parameters', editParameters),

  // ── Help (CommandStd.cpp; only the two confirmed ids — see file header) ──
  Std_WhatsThis: reg("What's This?", whatsThis),
  Std_FreeCADWebsite: reg('FreeCAD Website', () => { window.open('https://www.freecad.org', '_blank', 'noopener') }),

  // ── CAD Agent workbench (chrome.tsx's agentEntries/agentwb.tsx: no FreeCAD equivalent) ──
  CADAgent_Check: reg('Check', () => openTask('check', ''), () => !!getState().slug),
  CADAgent_Verify: reg('Verify', () => openTask('verify', ''), () => !!getState().slug),
  CADAgent_Done: reg('Done Gate', () => openTask('done', ''), () => !!getState().slug),
  CADAgent_CutList: reg('Cut List…', () => openTask('cutlist', ''), () => !!getState().slug),
  CADAgent_Tables: reg('Tables…', () => openTask('tables', '')),
  CADAgent_ToolEnvelope: reg('Tool Envelope…', () => openTask('tool', '')),
  CADAgent_Bought: reg('Bought Parts…', () => openTask('bought', ''), () => !!getState().slug),
  CADAgent_Render: reg('Render…', () => openTask('render', ''), () => !!getState().slug),
  CADAgent_ApproveRenders: reg('Approve Renders…', () => approveRenders(), () => !!getState().slug),
  CADAgent_Rules: reg('Rules…', () => openTask('rules', '')),
  CADAgent_ExportReviewPage: reg('Review page (*.html)', () => exportPage(), () => !!getState().slug),
}

export const getCommand = (name: string): RegCommand | undefined => COMMANDS[name]
/** publishGui's "commands" field: name/label/enabled for every registered command, sorted so a
 *  JSON diff (actions.ts) is stable when nothing actually changed. */
export function listCommands(): CommandInfo[] {
  return Object.keys(COMMANDS).sort().map((name) => {
    const c = COMMANDS[name]
    return { name, label: c.label(), enabled: c.isEnabled() }
  })
}

// actions.ts/commands.ts own the publish loop and the `cad gui` event switch; they call back in
// here (onGuiEvent's pattern, commands.ts/actions.ts) so neither has to import this file, which
// already imports both of them for their commands' functions.
onCommandRegistry(getCommand)
onCommandList(listCommands)
