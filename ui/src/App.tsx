import { useEffect, type FC } from 'react'
import { DockviewReact, themeLight, type DockviewReadyEvent, type IDockviewPanelProps } from 'dockview-react'
import { DRAW_STYLES, MenuBar, OverlayTitleActions, StatusBar, ToolBar, VIEWS, whatsThis } from './chrome'
import { ChecksView, ConsoleView, ModelPanel, ReportView, SelectionView, TasksPanel, View3D } from './panels'
import { getState, saved, useStore } from './store'
import { closeTask, doRedo, doUndo, openTask, getView, overlayBypass, overlayToggle, recordAndRun, runCheck, select, selBack, selForward, selectAll, setDock, setDrawStyle, setOrtho, setTreeOption, toggleBottomPanels, toggleVisibility } from './actions'
import { boxElementSelection, boxSelection, boxZoom, clarifySelection, exportPart, preferences, searchObjects, sendToConsole, gotoSelection, properties, recallView, rotateLeft, rotateRight, storeView, toggleAxisCross, toggleTransparency, viewHome, zoomIn, zoomOut, copySelection, freezeView, restoreView, fullscreen, viewFullscreen, viewDocked } from './commands'
import { workbenchList } from './chrome'
import { setState } from './store'
import { MessageBoxHost } from './msgbox'
import { PreferencesDialog, applyReportColors, checkCache } from './prefs'
import { CustomizeDialog } from './customize'
import { api } from './api'
import { exportCommand, printView } from './filemenu'
import { executeMacroDirect } from './macro'
// Registers cmdreg.ts's command registry into commands.ts/actions.ts (onCommandRegistry/
// onCommandList, the same callback pattern as commands.ts's own onGuiEvent); no named import
// needed here, just the module's side effect, so this file is the one place that loads it.
import './cmdreg'
import { overrideKey } from './keymap'
import { StartPanel } from './start'

const components: Record<string, FC<IDockviewPanelProps>> = {
  view3d: View3D, model: ModelPanel, tasks: TasksPanel, report: ReportView, checks: ChecksView, console: ConsoleView, selection: SelectionView,
  start: StartPanel,
}

/** FreeCAD's default layout: the combo view (Model, Tasks) on the left, the 3D
 *  view in the middle, the report view and console under it. */
applyReportColors() // Preferences > Report View > Colors, from the last session
// MainWindow's start-up ApplicationCache check (Preferences > General > Cache's period and limit).
setTimeout(() => { void api.cache(true).then((c) => (c.due ? checkCache(c) : c)).catch(() => {}) }, 2000)

function onReady(e: DockviewReadyEvent) {
  const a = e.api
  // StartView: FreeCAD opens on its Start page (Mod/Start ShowOnStartup), the first tab.
  const start = saved.get('start.showOnStartup', true)
  if (start) a.addPanel({ id: 'start', component: 'start', title: 'Start' })
  a.addPanel({ id: 'view3d', component: 'view3d', title: '3D view', ...(start ? { position: { referencePanel: 'start', direction: 'within' as const } } : {}) })
  a.addPanel({ id: 'model', component: 'model', title: 'Model', position: { referencePanel: 'view3d', direction: 'left' }, initialWidth: 330 })
  a.addPanel({ id: 'report', component: 'report', title: 'Report View', position: { referencePanel: 'view3d', direction: 'below' }, initialHeight: 170 })
  a.addPanel({ id: 'checks', component: 'checks', title: 'Checks', position: { referencePanel: 'report', direction: 'within' }, inactive: true })
  a.addPanel({ id: 'console', component: 'console', title: 'Console', position: { referencePanel: 'report', direction: 'within' }, inactive: true })
  if (start) a.getPanel('start')?.api.setActive()
  // MainWindow's MDI area in tabbed mode puts the document tabs (Start, "name : 1") under the views.
  const mdi = a.getPanel('view3d')?.group
  mdi?.api.setHeaderPosition('bottom')
  mdi?.element.classList.add('mdi')
  // QMainWindow's docks: one alone shows its title bar; tabified ones keep a title bar (the current
  // dock's) on top and their tabs underneath.
  const syncDocks = () => {
    for (const g of a.groups) {
      if (g.element.classList.contains('mdi') || g.panels.some((p) => p.id === 'view3d' || p.id === 'start')) continue
      const many = g.panels.length > 1
      if (g.api.getHeaderPosition() !== (many ? 'bottom' : 'top')) g.api.setHeaderPosition(many ? 'bottom' : 'top')
      g.element.dataset.dockTitle = many ? g.activePanel?.title ?? '' : ''
    }
  }
  a.onDidAddPanel(syncDocks); a.onDidRemovePanel(syncDocks); a.onDidActivePanelChange(syncDocks)
  syncDocks()
  setDock(a)
}

/** FreeCAD's accelerators (CommandView.cpp, CommandStd.cpp): 0-6 views, Home, Shift+arrows,
 *  End / Shift+End, V F / V S / V O / V P / V T / V 1-7, A C, T G, T 5, S B / S F, Shift+B,
 *  Space, ⌘A, ⌘E, ⌘⇧R, ⌘+ / ⌘-, Alt+Return, Esc, undo/redo. */
// Std_DockOverlayToggleLeft/Right/Top/Bottom (Ctrl+arrows): cmdreg.ts's names, by side.
const OVERLAY_SIDE_CMD = { left: 'Std_DockOverlayToggleLeft', right: 'Std_DockOverlayToggleRight', top: 'Std_DockOverlayToggleTop', bottom: 'Std_DockOverlayToggleBottom' } as const

function useKeys() {
  useEffect(() => {
    const keyViews = Object.fromEntries(VIEWS.map(([d, , k]) => [k, d]))
    const keyCmds = Object.fromEntries(VIEWS.map(([, , k, cmd]) => [k, cmd]))
    let prefix = '', prefixAt = 0
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement | null)?.closest?.('input, textarea, select, [contenteditable="true"]')) return
      // The user's own shortcuts (Preferences > General > Keyboard) come first.
      if (overrideKey(e)) { prefix = ''; return }
      // The report view and console are text: Ctrl+A and Ctrl+C there act on the text (ReportOutput::event).
      const inText = !!(e.target as HTMLElement | null)?.closest?.('.report, .console')
      if (inText && (e.metaKey || e.ctrlKey) && (e.key.toLowerCase() === 'a' || e.key.toLowerCase() === 'c')) return
      const mod = e.metaKey || e.ctrlKey, k = e.key.toLowerCase()
      // Std_Copy (Ctrl+C) unless there's text selected to copy; Std_FreezeViews' Restore View N (Ctrl+N).
      if (mod && !e.shiftKey && k === 'c' && !getSelection()?.toString() && getState().selected.length) { e.preventDefault(); recordAndRun('Std_Copy', copySelection); return }
      if (mod && !e.shiftKey && /^[1-9]$/.test(e.key) && getState().frozenViews.length >= Number(e.key)) { e.preventDefault(); restoreView(Number(e.key) - 1); return }
      if (e.shiftKey && !mod && k === 'f') { e.preventDefault(); freezeView(); return } // Freeze View (Shift+F)
      if (!mod && !e.shiftKey && !e.altKey && e.key === 'F5') { e.preventDefault(); recordAndRun('Std_Refresh', runCheck); return }
      if (!mod && !e.shiftKey && !e.altKey && e.key === 'F11') { e.preventDefault(); recordAndRun('Std_ViewFullscreen', viewFullscreen); return }
      if (mod && k === 'z') { e.preventDefault(); recordAndRun(e.shiftKey ? 'Std_Redo' : 'Std_Undo', e.shiftKey ? doRedo : doUndo); return }
      if (mod && k === 'y') { e.preventDefault(); recordAndRun('Std_Redo', doRedo); return } // not an sAccel FreeCAD defines; kept for Windows/Linux muscle memory
      if (mod && k === 'a') { e.preventDefault(); recordAndRun('Std_SelectAll', selectAll); return }
      if (mod && k === '0') { e.preventDefault(); recordAndRun('Std_ToggleBottomPanels', toggleBottomPanels); return }
      // Std_DockOverlayToggleLeft / Right / Top / Bottom (Ctrl+arrows).
      const side = ({ ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'top', ArrowDown: 'bottom' } as const)[e.key as 'ArrowLeft']
      if (mod && side) { e.preventDefault(); recordAndRun(OVERLAY_SIDE_CMD[side], () => overlayToggle(side)); return }
      if (mod && k === 'b') { e.preventDefault(); recordAndRun('Std_ViewBoxZoom', boxZoom); return }
      // TreeWidget::keyPressEvent: Find (Ctrl+F) in the tree opens its search (no fixed FreeCAD
      // command id for this one — it's TreeWidget's own search bar, not a Gui.runCommand target).
      if (mod && k === 'f' && (e.target as HTMLElement | null)?.closest?.('.tree')) { e.preventDefault(); searchObjects(); return }
      if (mod && k === 'e') { e.preventDefault(); recordAndRun('Std_Export', exportCommand); return }
      if (mod && !e.shiftKey && k === 'd') { e.preventDefault(); if (getState().selected.length) recordAndRun('Std_SetAppearance', () => openTask('appearance', '')); return } // Ctrl+D
      if (mod && e.shiftKey && k === 'i') { e.preventDefault(); if (getState().slug) recordAndRun('Std_Import', () => openTask('bought', '', 'import')); return } // Ctrl+Shift+I
      if (e.shiftKey && !mod && e.key === 'F1') { e.preventDefault(); recordAndRun('Std_WhatsThis', whatsThis); return } // Shift+F1
      if (mod && k === ',') { e.preventDefault(); recordAndRun('Std_DlgPreferences', preferences); return }
      if (mod && e.shiftKey && k === 'p') { e.preventDefault(); recordAndRun('Std_SendToPythonConsole', sendToConsole); return }
      // Std_New / Std_Open / Std_Print (QKeySequence::New/Open/Print); Std_Save/SaveAs do nothing with no
      // unsaved changes (every edit is already in the files), but still keep the browser's Save Page away.
      if (mod && !e.shiftKey && k === 'n') { e.preventDefault(); openTask('newDocument', ''); return }
      if (mod && !e.shiftKey && k === 'o') { e.preventDefault(); openTask('openDocument', ''); return }
      if (mod && !e.shiftKey && k === 'p') { e.preventDefault(); if (getState().slug) printView(); return }
      if (mod && !e.shiftKey && e.key === 'F6') { e.preventDefault(); recordAndRun('Std_DlgMacroExecuteDirect', executeMacroDirect); return }
      if (mod && k === 's') { e.preventDefault(); return }
      if (mod && e.shiftKey && k === 'r') { e.preventDefault(); recordAndRun('Std_Refresh', runCheck); return } // Tree.cpp's "Recompute object"
      if (mod && (k === '=' || k === '+')) { e.preventDefault(); recordAndRun('Std_ViewZoomIn', zoomIn); return }
      if (mod && k === '-') { e.preventDefault(); recordAndRun('Std_ViewZoomOut', zoomOut); return }
      if (e.altKey && e.key === 'Enter') { e.preventDefault(); recordAndRun('Std_Properties', properties); return }
      if (e.altKey && e.key === 'F11') {
        e.preventDefault()
        recordAndRun('Std_MainFullscreen', fullscreen)
        return
      }
      if (mod || e.altKey) return
      const v = getView()
      // Two-key sequences: V (view), A (axis cross), T (tree).
      if (prefix && performance.now() - prefixAt < 1500) {
        const seq = `${prefix}, ${k}`
        prefix = ''
        if (seq === 'v, f') recordAndRun('Std_ViewFitAll', () => v?.fitAll())
        else if (seq === 'v, s') recordAndRun('Std_ViewFitSelection', () => v?.fitAll(getState().selected))
        else if (seq === 'v, o') recordAndRun('Std_OrthographicCamera', () => setOrtho(true))
        else if (seq === 'v, p') recordAndRun('Std_PerspectiveCamera', () => setOrtho(false))
        else if (seq === 'v, t') recordAndRun('Std_ToggleTransparency', toggleTransparency)
        else if (seq === 'a, c') recordAndRun('Std_AxisCross', toggleAxisCross)
        else if (seq === 't, g') recordAndRun('Std_TreeSelection', gotoSelection)
        else if (seq === 'g, g') recordAndRun('Std_ClarifySelection', clarifySelection)
        else if (seq === 't, 1') recordAndRun('Std_TreeSyncView', () => setTreeOption('syncView', !getState().tree.syncView))
        else if (seq === 't, 2') recordAndRun('Std_TreeSyncSelection', () => setTreeOption('syncSelection', !getState().tree.syncSelection))
        else if (seq === 't, 4') recordAndRun('Std_TreePreSelection', () => setTreeOption('preSelection', !getState().tree.preSelection))
        else if (seq === 't, 5') recordAndRun('Std_TreeRecordSelection', () => setTreeOption('recordSelection', !getState().tree.recordSelection))
        else if (seq === 't, t') recordAndRun('Std_DockOverlayMouseTransparent', overlayBypass)
        else if (seq === 's, b') recordAndRun('Std_SelBack', selBack)
        else if (seq === 's, f') recordAndRun('Std_SelForward', selForward)
        else if (seq === 'v, d') recordAndRun('Std_ViewDock', viewDocked)
        else if (/^w, [1-9]$/.test(seq)) { const w = workbenchList()[Number(seq[3]) - 1]; if (w) setState({ workbench: w[0] }) }
        else { const ds = DRAW_STYLES.find(([, , key]) => key.toLowerCase() === seq); if (ds) recordAndRun(ds[4], () => setDrawStyle(ds[0])) }
        e.preventDefault()
        return
      }
      if (!e.shiftKey && (k === 'v' || k === 'a' || k === 't' || k === 'g' || k === 's' || k === 'w')) { prefix = k; prefixAt = performance.now(); return }
      if (e.key === 'Home') { e.preventDefault(); recordAndRun('Std_ViewHome', viewHome); return }
      if (e.key === 'End') { e.preventDefault(); recordAndRun(e.shiftKey ? 'Std_StoreWorkingView' : 'Std_RecallWorkingView', e.shiftKey ? storeView : recallView); return }
      if (e.shiftKey && e.key === 'ArrowLeft') { e.preventDefault(); recordAndRun('Std_ViewRotateLeft', rotateLeft); return }
      if (e.shiftKey && e.key === 'ArrowRight') { e.preventDefault(); recordAndRun('Std_ViewRotateRight', rotateRight); return }
      if (e.shiftKey && k === 'b') { e.preventDefault(); recordAndRun('Std_BoxSelection', boxSelection); return }
      if (e.shiftKey && k === 'e') { e.preventDefault(); recordAndRun('Std_BoxElementSelection', boxElementSelection); return }
      if (keyViews[e.key]) { recordAndRun(keyCmds[e.key], () => v?.viewDir(keyViews[e.key])); e.preventDefault(); return }
      if (e.key === ' ') { e.preventDefault(); recordAndRun('Std_ToggleVisibility', () => toggleVisibility()); return }
      if (e.key === 'Escape') { if (getState().task) closeTask(); else if (getState().treeFilter !== null) setState({ treeFilter: null }); else select(null) }
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])
}

export function App() {
  useKeys()
  const statusBar = useStore((s) => s.statusBar)
  return (
    <div className="app">
      <MenuBar />
      <ToolBar />
      <div className="dock"><DockviewReact components={components} onReady={onReady} theme={themeLight} rightHeaderActionsComponent={OverlayTitleActions} /></div>
      {statusBar && <StatusBar />}
      <PreferencesDialog />
      <CustomizeDialog />
      <MessageBoxHost />
    </div>
  )
}
