// User shortcuts: Gui::ShortcutManager (src/Gui/ShortcutManager.cpp) and Preferences > General >
// Keyboard (Dialogs/DlgKeyboard.ui, DlgKeyboardImp.cpp) at FreeCAD main 3160daf1e2b6.
// A command's shortcut is its sAccel unless the user set one (ShortcutManager::setShortcut, stored
// in the Shortcut parameter group as portable text, "" for none). App.tsx's handler binds the
// defaults; `overrideKey` runs first and, for a command the user changed, runs it on its new keys
// and swallows its old ones.
import { getState, saved, setState } from './store'
import { getCommand } from './cmdreg'
import { recordAndRun } from './actions'
import { DRAW_STYLES, VIEWS } from './chrome'

/** The sAccel of each command App.tsx binds, as QKeySequence portable text ("Ctrl" is ⌘ on a Mac,
 *  as Qt maps it). */
const BASE_ACCEL: Record<string, string> = {
  Std_Copy: 'Ctrl+C', Std_Undo: 'Ctrl+Z', Std_Redo: 'Ctrl+Shift+Z', Std_SelectAll: 'Ctrl+A', Std_ToggleBottomPanels: 'Ctrl+0',
  Std_DockOverlayToggleLeft: 'Ctrl+Left', Std_DockOverlayToggleRight: 'Ctrl+Right', Std_DockOverlayToggleTop: 'Ctrl+Up',
  Std_DockOverlayToggleBottom: 'Ctrl+Down', Std_ViewBoxZoom: 'Ctrl+B', Std_Export: 'Ctrl+E', Std_SetAppearance: 'Ctrl+D',
  Std_Import: 'Ctrl+Shift+I', Std_WhatsThis: 'Shift+F1', Std_DlgPreferences: 'Ctrl+,', Std_SendToPythonConsole: 'Ctrl+Shift+P',
  Std_New: 'Ctrl+N', Std_Open: 'Ctrl+O', Std_Refresh: 'F5', Std_ViewZoomIn: 'Ctrl++', Std_ViewZoomOut: 'Ctrl+-',
  Std_Properties: 'Alt+Return', Std_MainFullscreen: 'Alt+F11', Std_ViewFullscreen: 'F11',
  Std_ViewFitAll: 'V, F', Std_ViewFitSelection: 'V, S', Std_OrthographicCamera: 'V, O', Std_PerspectiveCamera: 'V, P',
  Std_ToggleTransparency: 'V, T', Std_AxisCross: 'A, C', Std_TreeSelection: 'T, G', Std_ClarifySelection: 'G, G',
  Std_TreeSyncView: 'T, 1', Std_TreeSyncSelection: 'T, 2', Std_TreePreSelection: 'T, 4', Std_TreeRecordSelection: 'T, 5',
  Std_DockOverlayMouseTransparent: 'T, T', Std_SelBack: 'S, B', Std_SelForward: 'S, F', Std_ViewDock: 'V, D',
  Std_ViewHome: 'Home', Std_RecallWorkingView: 'End', Std_StoreWorkingView: 'Shift+End', Std_ViewRotateLeft: 'Shift+Left',
  Std_ViewRotateRight: 'Shift+Right', Std_BoxSelection: 'Shift+B', Std_BoxElementSelection: 'Shift+E', Std_ToggleVisibility: 'Space',
}
let accel: Record<string, string> | null = null
/** Built on first use: chrome.tsx (VIEWS, DRAW_STYLES) imports this module too. */
export function defaultAccel(): Record<string, string> {
  return accel ??= { ...BASE_ACCEL, ...Object.fromEntries(VIEWS.map(([, , k, cmd]) => [cmd, k])),
    ...Object.fromEntries(DRAW_STYLES.map(([, , k, , cmd]) => [cmd, k])) }
}

const NAMED: Record<string, string> = {
  ' ': 'Space', Enter: 'Return', Escape: 'Esc', ArrowLeft: 'Left', ArrowRight: 'Right', ArrowUp: 'Up', ArrowDown: 'Down',
  PageUp: 'PgUp', PageDown: 'PgDown', Delete: 'Del', Backspace: 'Backspace', Tab: 'Tab', Insert: 'Ins', Home: 'Home', End: 'End',
}
/** One key press as QKeySequence portable text (modifiers in Qt's order), or null for a lone modifier. */
export function eventSeq(e: KeyboardEvent): string | null {
  if (['Shift', 'Control', 'Meta', 'Alt', 'CapsLock'].includes(e.key)) return null
  const key = /^Key[A-Z]$/.test(e.code) ? e.code.slice(3) : /^Digit\d$/.test(e.code) ? e.code.slice(5)
    : NAMED[e.key] ?? (/^F\d{1,2}$/.test(e.key) ? e.key : e.key.length === 1 ? e.key.toUpperCase() : e.key)
  return [(e.metaKey || e.ctrlKey) && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', key].filter(Boolean).join('+')
}
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
/** QKeySequence::NativeText: ⌃⌥⇧⌘ glyphs on a Mac, the portable text elsewhere. */
export function nativeText(seq: string): string {
  if (!MAC) return seq
  return seq.split(', ').map((chord) => {
    const parts = chord.split('+').filter((p, i, a) => p || i === a.length - 1)
    const key = chord.endsWith('++') ? '+' : parts.pop()!
    const glyph = (m: string) => ({ Alt: '⌥', Shift: '⇧', Ctrl: '⌘', Meta: '⌃' } as Record<string, string>)[m] ?? m
    const order = ['Meta', 'Alt', 'Shift', 'Ctrl'].filter((m) => parts.includes(m))
    return order.map(glyph).join('') + (({ Left: '←', Right: '→', Up: '↑', Down: '↓', Return: '↩', Esc: '⎋' } as Record<string, string>)[key] ?? key)
  }).join(', ')
}
/** ShortcutManager::getShortcut: the user's shortcut, else the default. */
export const shortcutOf = (cmd: string): string => getState().shortcuts[cmd] ?? defaultAccel()[cmd] ?? ''
/** A menu entry's shortcut text, following the user's change when there is one. */
export const menuKbd = (cmd: string | undefined, kbd: string | undefined) =>
  cmd && cmd in getState().shortcuts ? (getState().shortcuts[cmd] ? nativeText(getState().shortcuts[cmd]) : undefined) : kbd
/** ShortcutManager::setShortcut ("" clears it) and reset (back to the default). */
export function setShortcut(cmd: string, seq: string | null) {
  const shortcuts = { ...getState().shortcuts }
  if (seq === null || seq === defaultAccel()[cmd]) delete shortcuts[cmd]
  else shortcuts[cmd] = seq
  saved.set('shortcuts', shortcuts); setState({ shortcuts })
}
export function resetAllShortcuts() { saved.set('shortcuts', {}); setState({ shortcuts: {} }) }
/** ShortcutManager::getActionsByShortcut: every command whose shortcut is `seq` now. */
export function commandsByShortcut(seq: string, all: string[]): string[] {
  return seq ? all.filter((c) => shortcutOf(c) === seq) : []
}

let pending = '', pendingAt = 0, ambiguous = 0
const PREFIX_WAIT = 1500 // App.tsx's two-key sequences wait this long for their second key
function runUser(cmd: string) {
  const c = getCommand(cmd)
  if (c?.isEnabled()) recordAndRun(cmd, () => c.run([]))
}
/** Runs before App.tsx's own bindings. Returns true when it handled the key (a user shortcut ran,
 *  or the key was a changed command's old shortcut, which no longer does anything). */
export function overrideKey(e: KeyboardEvent): boolean {
  const user = getState().shortcuts
  if (!Object.keys(user).length) return false
  const seq = eventSeq(e)
  if (!seq) return false
  clearTimeout(ambiguous)
  const full = pending && performance.now() - pendingAt < PREFIX_WAIT ? `${pending}, ${seq}` : seq
  const hadPending = full !== seq
  pending = ''
  const exact = Object.entries(user).find(([, s]) => s === full)?.[0]
  const prefix = !hadPending && Object.values(user).some((s) => s.startsWith(`${seq}, `))
  if (exact && prefix) {
    // ShortcutManager's ShortcutTimeout: a shortcut that also starts a longer one runs only if no
    // second key follows within the timeout.
    e.preventDefault(); e.stopImmediatePropagation()
    pending = seq; pendingAt = performance.now()
    ambiguous = window.setTimeout(() => { if (pending === seq) { pending = ''; runUser(exact) } }, getState().shortcutTimeout)
    return true
  }
  if (exact) { e.preventDefault(); e.stopImmediatePropagation(); runUser(exact); return true }
  // A changed command's default keys are free now (unless another command took them, above).
  if (Object.keys(user).some((c) => defaultAccel()[c] === full)) { e.preventDefault(); return true }
  // A changed command's two-key default ("V, F") needs its first key remembered too, so the
  // second one can be swallowed above rather than reach App.tsx's own binding.
  const freedPrefix = !hadPending && Object.keys(user).some((c) => defaultAccel()[c]?.startsWith(`${seq}, `))
  if (prefix || freedPrefix) {
    pending = seq; pendingAt = performance.now()
    // App.tsx's own two-key prefixes (V, A, T, G, S, W) still see the key; anything else waits here.
    if (!/^[VATGSW]$/.test(seq)) { e.preventDefault(); return true }
  }
  return false
}
