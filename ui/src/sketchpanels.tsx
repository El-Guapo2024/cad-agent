// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/TaskSketcherConstraints.cpp: 2009 Juergen Riegel
//   src/Mod/Sketcher/Gui/ConstraintFilters.h: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/TaskSketcherElements.cpp: 2014 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditDatumDialog.cpp: 2011 Werner Mayer
//   src/Mod/Sketcher/App/SketchObjectPyImp.cpp: 2010 Jürgen Riegel
//   src/Base/Tools.cpp: 2009 Werner Mayer
//   No copyright line in the file: src/Mod/Sketcher/Gui/TaskSketcherConstraints.ui,
//       src/Mod/Sketcher/Gui/TaskSketcherElements.ui
// The Sketcher task panel's Constraints and Elements boxes (TaskSketcherConstraints, TaskSketcherElements): the filter
// (the check list of ConstraintFilters / ElementFilterList, on or off with its check box), the settings menu, the rows
// with FreeCAD's texts and icons, the visibility check boxes (a constraint's virtual space), Show/Hide all listed
// constraints, selection with Ctrl and Shift as Qt's ExtendedSelection does and both ways with the 3D view, F2 and the
// double-click renaming a constraint in place (SketchObject.renameConstraint, checkConstraintName), the elements'
// sub-element picking (edge, start, end, mid) and preselection, and the context menus. Also the expression a datum is
// bound to: the part file's string value, evaluated over the part's PARAMS (resolveExpressions). A deactivated
// constraint's icon is drawn as Qt draws a disabled icon (QIcon::Disabled: grey shades over the window colour).
import './sketchpanels.css'
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import * as S from './sketcher'
import * as SK from './sketch'
import * as PC from './sketchpanelcmds'
import { cmdInfo, runSketchCommand } from './sketchcmds'
import { sketcherIcon } from './sketchdraw'
import { ContextMenu, type Entry } from './chrome'
import { getState, report, saved } from './store'
import { numberOf } from './partdesign'
import type { Cons } from './solver'

const useSketch = () => useSyncExternalStore(S.subscribeSketch, S.sketchVersion)
const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform)

// ── parameters (User parameter:BaseApp/Preferences/Mod/Sketcher…) ──────────────────────────────────────────────────
const NORMAL_FILTERS = 26
const PARAMS = {
  ConstraintFilterEnabled: ['General', true], SelectedConstraintFilters: ['General', (1 << NORMAL_FILTERS) - 1],
  ElementFilterEnabled: ['General', true], ElementFilterState: ['General', 0x7fffffff],
  VisualisationTrackingFilter: ['', false], ExtendedConstraintInformation: ['', false], HideInternalAlignment: ['', false],
  AutoRemoveRedundants: ['', false], ExtendedNaming: ['Elements', false],
} as const
type ParamName = keyof typeof PARAMS
const key = (n: ParamName) => `sketcher.param.${PARAMS[n][0] ? PARAMS[n][0] + '/' : ''}${n}`
function param<N extends ParamName>(n: N): (typeof PARAMS)[N][1] extends boolean ? boolean : number {
  return saved.get(key(n), PARAMS[n][1]) as never
}
function setParam(n: ParamName, v: boolean | number) { saved.set(key(n), v); bump() }
/** The panel's parameters back to FreeCAD's defaults (ui/scripts/sketchcheck.mjs between its cases, as fcsketch_dump.py
 *  removes them from FreeCAD's profile). */
export function resetPanelParams() { for (const n of Object.keys(PARAMS) as ParamName[]) saved.remove(key(n)); panel = null; bump() }

// ── the boxes' state, made anew for each edit (the task panel is built in setEdit) ─────────────────────────────────
type Check = 0 | 1 | 2 // Qt::Unchecked, PartiallyChecked, Checked
type Special = 'none' | 'selected' | 'associated'
type Panel = {
  session: unknown
  cFilter: Check[]; special: Special; selectionFilter: number[]; associatedFilter: number[]
  eFilter: Check[]
  current: number; anchor: number                                   // the constraints list's current item and anchor
  focusItem: number; previouslySelected: number                     // TaskSketcherElements' focusItemIndex, previouslySelectedItemIndex
  renaming: number | null
  lastSelection: string[]
  /** a change the lists make themselves (blockSelection): the selection observer leaves it */
  own: boolean
}
let panel: Panel | null = null
let panelVersion = 0
const panelSubs = new Set<() => void>()
function bump() { panelVersion++; panelSubs.forEach((f) => f()) }
const usePanel = () => useSyncExternalStore((f) => { panelSubs.add(f); return () => { panelSubs.delete(f) } }, () => panelVersion)
function bits(state: number, n: number): Check[] { return Array.from({ length: n }, (_, i) => ((state >> i) & 1 ? 2 : 0) as Check) }
function getPanel(): Panel {
  const s = S.getSession()
  if (!panel || panel.session !== s) {
    // ConstraintFilterList: SelectedConstraintFilters, one bit per item (the special ones after the normal ones)
    const cFilter = bits(param('SelectedConstraintFilters'), C_FILTERS.length)
    // ElementFilterList: ElementFilterState; "All types" partly checked when some types are
    const eFilter = bits(param('ElementFilterState'), E_FILTERS.length)
    if (eFilter[ALL_TYPES] === 0 && eFilter.slice(ALL_TYPES + 1).some((x) => x === 2)) eFilter[ALL_TYPES] = 1
    panel = { session: s, cFilter, special: 'none', selectionFilter: [], associatedFilter: [], eFilter, current: -1, anchor: -1, focusItem: -1,
      previouslySelected: -1, renaming: null, lastSelection: S.getSelection(), own: false }
    setPartiallyChecked(panel.cFilter)
    // the special filters as saved (TaskSketcherConstraints' constructor runs onFilterListItemChanged for them)
    if (panel.cFilter[SELECTED_FILTER] === 2) { panel.special = 'selected'; panel.cFilter[ASSOCIATED_FILTER] = 0; panel.selectionFilter = [...S.selectedConstraints()] }
    else if (panel.cFilter[ASSOCIATED_FILTER] === 2) { panel.special = 'associated'; panel.associatedFilter = associatedConstraints() }
    queueMicrotask(() => applyTracking())
  }
  return panel
}
/** Changes to the selection the lists did not make themselves: TaskSketcherConstraints::onSelectionChanged keeps its
 *  Selected / Associated filter up to date with them. */
S.subscribeSketch(() => {
  const p = panel
  if (!p || p.session !== S.getSession()) return
  const now = S.getSelection()
  const before = p.lastSelection
  if (now.length === before.length && now.every((x, i) => x === before[i])) return
  p.lastSelection = now
  if (p.own) return
  if (!param('ConstraintFilterEnabled')) return
  const cons = (l: string[]) => l.filter((n) => n.startsWith('Constraint')).join()
  if (p.special === 'selected' && (!now.length || cons(now) !== cons(before))) { p.selectionFilter = [...S.selectedConstraints()]; applyTracking(); bump() }
  else if (p.special === 'associated') {
    const edges = (l: string[]) => l.filter((n) => /^Edge\d+$/.test(n)).join()
    if (!now.length) { p.associatedFilter = []; applyTracking(); bump() }
    else if (edges(now) !== edges(before)) { p.associatedFilter = associatedConstraints(); applyTracking(); bump() }
  }
})
/** The lists change the selection: the observer is not told (blockSelection). */
function ownSelection(f: () => void) {
  const p = getPanel()
  p.own = true
  try { f() } finally { p.own = false; p.lastSelection = S.getSelection() }
}

// ── ConstraintFilters.h and the filter list (TaskSketcherConstraints.h's filterItems) ──────────────────────────────
const C_FILTERS: [string, number][] = [['All', 0], ['Geometric', 0], ['Coincident', 1], ['Point on Object', 1], ['Vertical', 1], ['Horizontal', 1],
  ['Parallel', 1], ['Perpendicular', 1], ['Tangent', 1], ['Equality', 1], ['Symmetric', 1], ['Block', 1], ['Group', 1], ['Text', 1],
  ['Internal Alignment', 1], ['Datums', 0], ['Horizontal Distance', 1], ['Vertical Distance', 1], ['Distance', 1], ['Radius', 1], ['Weight', 1],
  ['Diameter', 1], ['Angle', 1], ["Snell's Law", 1], ['Named', 0], ['Reference', 0], ['Selected constraints', 0], ['Associated constraints', 0]]
const FV = { All: 0, Geometric: 1, Coincident: 2, PointOnObject: 3, Vertical: 4, Horizontal: 5, Parallel: 6, Perpendicular: 7, Tangent: 8,
  Equality: 9, Symmetric: 10, Block: 11, Group: 12, Text: 13, InternalAlignment: 14, Datums: 15, HorizontalDistance: 16, VerticalDistance: 17,
  Distance: 18, Radius: 19, Weight: 20, Diameter: 21, Angle: 22, SnellsLaw: 23, Named: 24, NonDriving: 25 }
const SELECTED_FILTER = 26, ASSOCIATED_FILTER = 27
const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i)
/** filterAggregates: which filters each one takes in (itself too). */
const AGGREGATES: number[][] = [
  range(0, 25),
  [FV.Geometric, ...range(FV.Coincident, FV.InternalAlignment)],
  ...range(FV.Coincident, FV.InternalAlignment).map((i) => [i]),
  [FV.Datums, ...range(FV.HorizontalDistance, FV.SnellsLaw)],
  ...range(FV.HorizontalDistance, FV.NonDriving).map((i) => [i]),
]
/** ConstraintFilterList::setPartiallyChecked: a group is checked when all of its filters are, unchecked when none is,
 *  partly checked otherwise; from the last to the first, so that sub-groups are done first. */
function setPartiallyChecked(f: Check[]) {
  for (let i = NORMAL_FILTERS - 1; i >= 0; i--) {
    const members = AGGREGATES[i].filter((j) => j !== i)
    if (members.length <= 1) continue
    f[i] = members.every((j) => f[j] === 2) ? 2 : members.every((j) => f[j] === 0) ? 0 : 1
  }
}
const multiFilter = (f: Check[]) => f.slice(0, NORMAL_FILTERS).map((x) => x === 2)
/** The constraints of the selected edges (updateAssociatedConstraintsFilter). */
function associatedConstraints(): number[] {
  const out: number[] = []
  for (const n of S.getSelection()) {
    if (!(n.length > 4 && n.startsWith('Edge'))) continue
    const g = Number(n.slice(4)) - 1
    S.getConstraints().forEach((c, i) => { if (c.first === g || c.second === g || c.third === g) out.push(i) })
  }
  return out
}
const TYPE_FILTER: Partial<Record<SK.ConstraintType, number>> = { Horizontal: FV.Horizontal, Vertical: FV.Vertical, Coincident: FV.Coincident,
  PointOnObject: FV.PointOnObject, Group: FV.Group, Text: FV.Text, Parallel: FV.Parallel, Perpendicular: FV.Perpendicular, Tangent: FV.Tangent,
  Equal: FV.Equality, Symmetric: FV.Symmetric, Block: FV.Block, Distance: FV.Distance, DistanceX: FV.HorizontalDistance, DistanceY: FV.VerticalDistance,
  Radius: FV.Radius, Weight: FV.Weight, Diameter: FV.Diameter, Angle: FV.Angle, SnellsLaw: FV.SnellsLaw, InternalAlignment: FV.InternalAlignment }
/** TaskSketcherConstraints::isConstraintFiltered. */
function isConstraintFiltered(i: number): boolean {
  const c = S.getConstraints()[i], p = getPanel()
  if (c.type === 'Text') return true
  const hideInternal = param('HideInternalAlignment')
  let visible = true
  if (param('ConstraintFilterEnabled')) {
    const m = multiFilter(p.cFilter)
    const t = TYPE_FILTER[c.type]
    if (t !== undefined) visible = m[t] && (c.type !== 'InternalAlignment' || !hideInternal)
    visible ||= !!c.name && m[FV.Named]
    if (visible && p.special === 'selected') visible = p.selectionFilter.includes(i)
    else if (visible && p.special === 'associated') visible = p.associatedFilter.includes(i)
  } else if (c.type === 'InternalAlignment') visible = !hideInternal
  return !visible
}
/** change3DViewVisibilityToTrackFilter (updateList): with "Display only filtered constraints", what the list leaves
 *  out the view does too (SketchObject.setVisibility); without it, every constraint is visible. */
function applyTracking() {
  if (!S.isEditing()) return
  const on = param('VisualisationTrackingFilter')
  S.getConstraints().forEach((_, i) => S.setConstraintHidden(i, on && isConstraintFiltered(i)))
}
/** onFilterListItemChanged. */
function setConstraintFilter(index: number, state: Check) {
  const p = getPanel(), f = p.cFilter
  f[index] = state
  if (index < NORMAL_FILTERS) {
    for (let i = 0; i < NORMAL_FILTERS; i++) if (AGGREGATES[index].includes(i)) f[i] = state
    setPartiallyChecked(f)
  } else if (index === SELECTED_FILTER) {
    if (state === 2) { p.special = 'selected'; p.selectionFilter = [...S.selectedConstraints()] } else p.special = 'none'
    f[ASSOCIATED_FILTER] = 0
  } else {
    if (state === 2) { p.special = 'associated'; p.associatedFilter = associatedConstraints() } else p.special = 'none'
    f[SELECTED_FILTER] = 0
  }
  let st = 0
  for (let i = f.length - 1; i >= 0; i--) st = (st << 1) | (f[i] === 2 ? 1 : 0)
  setParam('SelectedConstraintFilters', st)
  applyTracking()
  bump()
}
/** A check box of a user-checkable item, clicked: Checked becomes Unchecked, anything else Checked. */
const clicked = (c: Check): Check => (c === 2 ? 0 : 2)

// ── a row's text and icon (ConstraintItem::data) ─────────────────────────────────────────────────────────────────
const NAMES: Partial<Record<SK.ConstraintType, string>> = { Horizontal: 'Horizontal', Vertical: 'Vertical', Coincident: 'Coincident',
  PointOnObject: 'PointOnObject', Parallel: 'Parallel', Perpendicular: 'Perpendicular', Tangent: 'Tangent', Equal: 'Equal', Symmetric: 'Symmetric',
  Block: 'Lock', Distance: 'Distance', DistanceX: 'DistanceX', DistanceY: 'DistanceY', Radius: 'Radius', Diameter: 'Diameter', Angle: 'Angle',
  Weight: 'Weight', SnellsLaw: 'Snell', InternalAlignment: 'Alignment' }
/** ConstraintItem::getName. */
const itemName = (c: SK.Constraint, i: number) => c.name || `${i + 1}-${NAMES[c.type] ?? 'Constraint'}`
/** QString::arg(double): %g with 6 significant digits. */
const argNumber = (v: number) => String(Number(v.toPrecision(6)))
/** ConstraintItem::data(Qt::DisplayRole). */
export function constraintText(c: SK.Constraint, i: number): string {
  let name = itemName(c, i)
  if (['Distance', 'DistanceX', 'DistanceY', 'Radius', 'Weight', 'Diameter', 'Angle'].includes(c.type)) name = `${name} (${SK.presentationValue(c)})`
  else if (c.type === 'SnellsLaw') {
    const v = c.value
    let n1 = 1, n2 = 1
    if (Math.abs(v) >= 1) n2 = v
    else n1 = 1 / v
    name = `${name} (${argNumber(n2)}/${argNumber(n1)})`
  }
  if (param('ExtendedConstraintInformation')) {
    if (c.second === SK.GEO_UNDEF) name = `${name} [(${c.first},${c.firstPos})]`
    else if (c.third === SK.GEO_UNDEF) name = `${name} [(${c.first},${c.firstPos}),(${c.second},${c.secondPos})]`
    else name = `${name} [(${c.first},${c.firstPos}),(${c.second},${c.secondPos}),(${c.third},${c.thirdPos})]`
  }
  return name
}
/** ConstraintItem::data(Qt::DecorationRole): the icon, its driven variant for a reference dimension. */
export function constraintIcon(c: SK.Constraint): string {
  if (c.type === 'InternalAlignment') {
    switch (c.alignment) {
      case 'EllipseMajorDiameter': return 'Constraint_InternalAlignment_Ellipse_MajorAxis'
      case 'EllipseMinorDiameter': return 'Constraint_InternalAlignment_Ellipse_MinorAxis'
      case 'EllipseFocus1': return 'Constraint_InternalAlignment_Ellipse_Focus1'
      case 'EllipseFocus2': return 'Constraint_InternalAlignment_Ellipse_Focus2'
      default: return 'Constraint_InternalAlignment'
    }
  }
  if (c.type === 'Group') return 'Constraint_Group'
  if (c.type === 'Text') return 'Constraint_Text'
  return SK.listIcon(c)
}
/** isEnforceable: a dimension needs one element that is not fixed geometry to be driving. */
const isEnforceable = (c: SK.Constraint) => !SK.isDimensional(c) || c.first >= 0 || c.second >= 0 || c.third >= 0

// ── icons: the disabled one of a deactivated constraint, the elements' construction/external/internal colours ────
const iconCache = new Map<string, string>()
const iconPending = new Set<string>()
function useIcon(name: string, variant: 'normal' | 'disabled' | 'construction' | 'external' | 'constructionExternal' | 'internal') {
  usePanel()
  if (variant === 'normal') return sketcherIcon(name)
  const k = `${name}|${variant}`
  const got = iconCache.get(k)
  if (got) return got
  if (!iconPending.has(k)) {
    iconPending.add(k)
    const img = new Image()
    img.onload = () => { iconCache.set(k, recolour(img, variant)); bump() }
    img.src = sketcherIcon(name)
  }
  return sketcherIcon(name)
}
/** Qt's colour model, as QColor::getHsv and setHsv give it (h 0..359 or -1 for a grey, s and v 0..255). */
function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
  const R = r / 255, G = g / 255, B = b / 255, max = Math.max(R, G, B), min = Math.min(R, G, B), d = max - min
  const v = Math.round(max * 255)
  if (d < 1e-12) return [-1, 0, v]
  let h = R === max ? (G - B) / d : G === max ? 2 + (B - R) / d : 4 + (R - G) / d
  h *= 60
  if (h < 0) h += 360
  return [Math.floor(Math.round(h * 100) / 100), Math.round((d / max) * 255), v]
}
function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  if (h < 0 || s === 0) return [v, v, v]
  const S_ = s / 255, V = v / 255, hh = (h % 360) / 60, i = Math.floor(hh), f = hh - i
  const p = V * (1 - S_), q = V * (1 - S_ * f), t = V * (1 - S_ * (1 - f))
  const [r, g, b] = [[V, t, p], [q, V, p], [p, V, t], [p, q, V], [t, p, V], [V, p, q]][i]
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)]
}
/** ElementWidgetIcons::getMultIcon's colour changes (red points and white edges turned blue for construction,
 *  magenta for external, pale for internal), and QCommonStyle::generatedIconPixmap(QIcon::Disabled). */
function recolour(img: HTMLImageElement, variant: string): string {
  const w = img.naturalWidth || 64, h = img.naturalHeight || 64
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d')!
  ctx.drawImage(img, 0, 0, w, h)
  const data = ctx.getImageData(0, 0, w, h), px = data.data
  // the window colour (FreeCAD Light's palette) for the disabled table
  const [br, bg, bb] = [239, 239, 239]
  const table = (x: number) => Array.from({ length: 256 }, (_, i) => (i < 128 ? (x * (i << 1)) >> 8 : Math.min(x + ((i - 128) << 1), 255)))
  const reds = table(br), greens = table(bg), blues = table(bb)
  let intensity = Math.floor((77 * br + 150 * bg + 28 * bb) / 255)
  const factor = 191
  if ((br - factor > bg && br - factor > bb) || (bg - factor > br && bg - factor > bb) || (bb - factor > br && bb - factor > bg)) intensity = Math.min(255, intensity + 91)
  else if (intensity <= 128) intensity -= 51
  for (let o = 0; o < px.length; o += 4) {
    const r = px[o], g = px[o + 1], b = px[o + 2], a = px[o + 3]
    if (variant === 'disabled') {
      const gray = (r * 11 + g * 16 + b * 5) >> 5
      const ci = Math.min(255, Math.max(0, Math.floor(gray / 3 + (130 - intensity / 3))))
      px[o] = reds[ci]; px[o + 1] = greens[ci]; px[o + 2] = blues[ci]
      continue
    }
    const [hue, sat, val] = rgbToHsv(r, g, b)
    if (!(a > 127 && hue >= 0)) continue
    let out: [number, number, number] | null = null
    if (sat > 127 && (hue > 330 || hue < 30)) {
      if (variant === 'construction' || variant === 'constructionExternal') out = hsvToRgb((hue + 240) % 360, sat, val)
      else if (variant === 'external') out = hsvToRgb((hue + 300) % 360, sat, val)
      else out = hsvToRgb((hue + 60) % 360, Math.floor(sat / 3), Math.min(Math.floor((val * 8) / 7), 255))
    } else if (sat < 64 && val > 192) {
      if (variant === 'construction') out = hsvToRgb(240, 255 - sat, val)
      else if (variant === 'external' || variant === 'constructionExternal') out = hsvToRgb(300, 255 - sat, val)
      else out = hsvToRgb(60, Math.floor((255 - sat) / 2), val)
    }
    if (out) { px[o] = out[0]; px[o + 1] = out[1]; px[o + 2] = out[2] }
  }
  ctx.putImageData(data, 0, 0)
  return c.toDataURL()
}

// ── renaming (TaskSketcherConstraints::onListWidgetConstraintsItemChanged) ──────────────────────────────────────────
/** SketcherGui::checkConstraintName: empty, or an identifier (Base::Tools::getIdentifier leaves it as it is). */
export function checkConstraintName(name: string): boolean {
  if (name && !/^[\p{ID_Start}_][\p{ID_Continue}]*$/u.test(name)) {
    report('err', 'Value Error: Invalid constraint name (must only contain alphanumericals and underscores, and must not start with digit)')
    return false
  }
  return true
}
/** SketchObjectPy::renameConstraint: an empty name takes the name away; a name another constraint has is refused. */
export function renameConstraint(i: number, name: string): string | null {
  const cs = S.getConstraints()
  if (i >= cs.length) return `Not able to rename a constraint with the given index: ${i}`
  if (name && cs.some((c, k) => k !== i && c.name === name)) return 'Duplicate constraint not allowed'
  if (cs[i].name !== name) S.setConstraint(i, { ...cs[i], name })
  return null
}
function commitRename(i: number, text: string) {
  const c = S.getConstraints()[i]
  if (!c) return
  const name = text.trim()
  if (name !== c.name && checkConstraintName(name)) {
    S.openCommand('Rename sketch constraint')
    const err = renameConstraint(i, name)
    if (err) { S.abortCommand(); report('err', `Value Error: ${err}`) }
    else S.commitCommand()
  }
  // doSetVirtualSpace with the item's check box as it is
  S.openCommand("Update constraint's virtual space")
  S.commitCommand()
  S.solve()
}
let datumHook: ((id: number) => void) | null = null
/** The datum dialog (EditDatumDialog, in sketchui.tsx) registers here. */
export function onOpenDatum(f: (id: number) => void) { datumHook = f }

// ── the boxes ────────────────────────────────────────────────────────────────────────────────────────────────────
function PanelBox({ title, icon, id, children }: { title: string; icon: string; id: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="tbox" data-box={id}>
      <div className="tbox-head" onClick={() => setOpen(!open)}><img src={sketcherIcon(icon)} width={16} height={16} alt="" draggable={false} className="ico" /><span>{title}</span><span className={open ? 'twisty open' : 'twisty'}>{open ? '▴' : '▾'}</span></div>
      {open && <div className="tbox-body">{children}</div>}
    </div>
  )
}
/** A QToolButton with a pop-up: the filter's check list, or the settings menu. */
function FilterPopup({ at, items, states, onToggle, onClose, which }: { at: { x: number; y: number }; items: [string, number][]; states: Check[];
  onToggle(i: number): void; onClose(): void; which: string }) {
  useEffect(() => {
    const away = (e: Event) => { if (!(e.target as HTMLElement).closest?.('.skp-popup')) onClose() }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    addEventListener('pointerdown', away, true); addEventListener('keydown', key, true)
    return () => { removeEventListener('pointerdown', away, true); removeEventListener('keydown', key, true) }
  }, [onClose])
  return createPortal(
    <div className="skp-popup mb-content" style={{ left: Math.min(at.x, innerWidth - 230), top: Math.min(at.y, innerHeight - items.length * 20 - 10) }} data-filter-popup={which}>
      {items.map(([text, level], i) => (which === 'constraints' && i === FV.Text) ? null : (
        <div key={i} className="skp-filter-item" data-filter-item={text}>
          <input type="checkbox" checked={states[i] === 2} ref={(el) => { if (el) el.indeterminate = states[i] === 1 }} onChange={() => onToggle(i)} />
          {/* ConstraintFilterList::languageChange: "- " before a filter of a group */}
          <span>{'  '.repeat(Math.max(0, level - 1)) + (level > 0 ? '- ' : '') + text}</span>
        </div>))}
    </div>, document.body)
}
function SettingsButton({ entries }: { entries: () => Entry[] }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  return <>
    <button className="tb-btn skp-tool" title="Settings" data-panel-settings onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setAt(at ? null : { x: r.left, y: r.bottom + 1 }) }}>
      <img src={sketcherIcon('Sketcher_Settings')} width={16} height={16} alt="" draggable={false} /><span className="tb-caret">▾</span></button>
    {at && <ContextMenu at={at} entries={entries()} onClose={() => setAt(null)} />}
  </>
}

// ── Constraints ──────────────────────────────────────────────────────────────────────────────────────────────────
/** One row of the list as the checks read it (sketchcheck.mjs, fcsketch_dump.py's panel record). */
export type ConstraintRow = { text: string; hidden: boolean; checked: boolean; selected: boolean; tip: string }
export function constraintRows(): ConstraintRow[] {
  const sel = S.selectedConstraints(), shown = S.isShownVirtualSpace()
  return S.getConstraints().map((c, i) => ({ text: constraintText(c, i), hidden: isConstraintFiltered(i), checked: c.virtual === shown, selected: sel.has(i), tip: c.expr ?? '' }))
}
/** TaskSketcherConstraints::onListWidgetConstraintsItemSelectionChanged: the list's selection becomes the selection
 *  (the 3D view's elements are deselected). */
function selectRows(rows: number[]) {
  ownSelection(() => S.setSelection(rows.map(SK.constraintSelName)))
}
/** changeFilteredVisibility: the listed (or the selected) constraints go to the virtual space that shows (show) or to
 *  the other one. */
function changeFilteredVisibility(show: boolean, target: 'all' | 'selected') {
  const shown = S.isShownVirtualSpace(), sel = S.selectedConstraints()
  const ids = S.getConstraints().flatMap((c, i) => {
    const process = target === 'all' ? !isConstraintFiltered(i) : sel.has(i)
    return process && ((c.virtual === shown && !show) || (c.virtual !== shown && show)) ? [i] : []
  })
  if (ids.length) doSetVirtualSpace(ids, !show)
}
function doSetVirtualSpace(ids: number[], on: boolean) {
  S.openCommand("Update constraint's virtual space")
  if (!PC.setVirtualSpace(ids, on)) { S.abortCommand(); report('err', 'Error: Impossible to update visibility tracking: Impossible to set virtual space!'); return }
  S.commitCommand()
  S.solve()
}
/** ConstraintView::contextMenuEvent. */
function constraintMenu(row: number | null): Entry[] {
  const p = getPanel()
  // Cancel any in-progress operation; then the list's selection is the selection again
  if (PC.releaseHandler() && row !== null) selectRows([...S.selectedConstraints()])
  const cs = S.getConstraints(), items = [...S.selectedConstraints()], it = row !== null ? cs[row] : null
  const isQuantity = !!it && SK.isDimensional(it), isToggleDriving = isQuantity && isEnforceable(it!), isActive = it ? it.active : true
  const cmdEntry = (icon: string, label: string, cmd: string, onSelection: boolean): Entry => ({ label, img: sketcherIcon(icon), kbd: cmdInfo(cmd).accel || undefined,
    disabled: onSelection && !items.length, onSelect: () => runSketchCommand(cmd) })
  return [
    { label: 'Edit Value', bold: true, disabled: !isQuantity, onSelect: () => { if (row !== null) activate(row) } },
    { label: 'Toggle Driving/Reference', disabled: !isToggleDriving, onSelect: () => runSketchCommand('Sketcher_ToggleDrivingConstraint') },
    { label: isActive ? 'Deactivate' : 'Activate', disabled: !items.length, onSelect: () => runSketchCommand('Sketcher_ToggleActiveConstraint') },
    'sep',
    { label: 'Show Constraints', disabled: !items.length, onSelect: () => changeFilteredVisibility(true, 'selected') },
    { label: 'Hide Constraints', disabled: !items.length, onSelect: () => changeFilteredVisibility(false, 'selected') },
    'sep',
    cmdEntry('Sketcher_SelectElementsAssociatedWithConstraints', 'Select Elements', 'Sketcher_SelectElementsAssociatedWithConstraints', true),
    // on a Mac Qt's F2 does not start the editor, so FreeCAD gives Rename no shortcut there
    { label: 'Rename', kbd: isMac ? undefined : 'F2', disabled: row === null, onSelect: () => { if (row !== null) { p.renaming = row; bump() } } },
    { label: 'Center Sketch', disabled: row === null, onSelect: PC.centerSelection },
    { label: 'Delete', kbd: isMac ? '⌫' : 'Del', disabled: !items.length, onSelect: () => { S.deleteSelected() } },
    { label: 'Delete All', onSelect: () => { S.openCommand('Delete all constraints'); S.setConstraints([]); S.commitCommand(); S.clearSelection(); S.solve() } },
    { label: 'Delete by Filter', onSelect: () => {
      const ids = cs.flatMap((_, i) => (isConstraintFiltered(i) ? [] : [i]))
      if (!ids.length) return
      // delConstraints: the selection keeps its names (ConstraintN now names what moved there), less those past the end
      const sel = S.getSelection()
      S.openCommand('Delete constraints'); S.delConstraints(ids); S.commitCommand()
      const n = S.getConstraints().length
      S.setSelection(sel.filter((x) => !x.startsWith('Constraint') || Number(x.slice(10)) <= n))
      S.solve()
    } },
    { label: 'Swap Constraint Names', disabled: items.length !== 2, onSelect: () => swapNames(items) },
  ]
}
/** ConstraintView::swapNamedOfSelectedItems. */
function swapNames(items: number[]) {
  if (items.length !== 2) return
  const cs = S.getConstraints(), [a, b] = items
  if (!cs[a].name || !cs[b].name) { report('warn', 'Unnamed constraint: Only the names of named constraints can be swapped.'); return }
  S.openCommand('Swap constraint names')
  const na = cs[a].name, nb = cs[b].name
  S.setConstraint(a, { ...S.getConstraints()[a], name: `DummyConstraint${Math.floor(Math.random() * 2147483647)}` })
  S.setConstraint(b, { ...S.getConstraints()[b], name: na })
  S.setConstraint(a, { ...S.getConstraints()[a], name: nb })
  S.commitCommand()
  S.solve()
}
/** onListWidgetConstraintsItemActivated (a double-click, Return): a dimension's datum dialog, any other constraint
 *  renamed in place. */
function activate(i: number) {
  const c = S.getConstraints()[i]
  if (!c) return
  if (SK.isDimensional(c)) datumHook?.(i)
  else { getPanel().renaming = i; bump() }
}
export function ConstraintsList() {
  useSketch(); usePanel()
  const p = getPanel()
  const cs = S.getConstraints()
  const rows = constraintRows()
  const [filterAt, setFilterAt] = useState<{ x: number; y: number } | null>(null)
  const [menuAt, setMenuAt] = useState<{ x: number; y: number; row: number | null } | null>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const filterOn = param('ConstraintFilterEnabled')
  /** Qt's ExtendedSelection: a click selects the row alone, Ctrl a row more or less, Shift the rows from the anchor. */
  const press = (i: number, e: React.MouseEvent) => {
    listRef.current?.focus()
    const ctrl = isMac ? e.metaKey : e.ctrlKey
    if (e.button === 2) {
      // a right press selects the row unless it is selected already
      if (!rows[i].selected) selectRows([i])
      p.current = i; bump(); return
    }
    let next: number[]
    if (ctrl) { next = rows[i].selected ? [...S.selectedConstraints()].filter((x) => x !== i) : [...S.selectedConstraints(), i]; p.anchor = i }
    else if (e.shiftKey && p.anchor >= 0) { const [a, b] = [Math.min(p.anchor, i), Math.max(p.anchor, i)]; next = range(a, b).filter((k) => !rows[k].hidden) }
    else { next = [i]; p.anchor = i }
    p.current = i
    const now = [...S.selectedConstraints()].sort((a, b) => a - b)
    if (now.join() !== [...next].sort((a, b) => a - b).join()) selectRows(next)
    bump()
  }
  const settings = (): Entry[] => [
    { label: 'Auto constraints', checked: true, disabled: true, title: 'The tools look for auto-constraints always here (ViewProviderSketch::Autoconstraints is not a setting yet)' },
    { label: 'Auto remove redundant constraints', checked: param('AutoRemoveRedundants'), disabled: true, title: 'The tools do not remove redundant constraints here yet' },
    { label: 'Display only filtered constraints', checked: param('VisualisationTrackingFilter'), onSelect: () => { setParam('VisualisationTrackingFilter', !param('VisualisationTrackingFilter')); applyTracking() } },
    { label: 'Extended information (in widget)', checked: param('ExtendedConstraintInformation'), onSelect: () => setParam('ExtendedConstraintInformation', !param('ExtendedConstraintInformation')) },
    { label: 'Hide internal alignment (in widget)', checked: param('HideInternalAlignment'), onSelect: () => setParam('HideInternalAlignment', !param('HideInternalAlignment')) },
  ]
  /** onShowHideButtonClicked: all listed shown → hide them all; else show them all. */
  const showHide = () => changeFilteredVisibility(!rows.every((r) => r.hidden || r.checked), 'all')
  return (
    <PanelBox title="Constraints" icon="Sketcher_CreateLineAngleLength" id="constraints">
      <div className="skp-bar">
        <input type="checkbox" className="skp-filterbox" data-panel-filterbox checked={filterOn} title="Toggles the chosen constraint filters"
          onChange={(e) => { setParam('ConstraintFilterEnabled', e.target.checked); applyTracking() }} />
        <button className="skp-tool skp-filter" data-panel-filter disabled={!filterOn} title="Filters constraints by type"
          onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setFilterAt(filterAt ? null : { x: r.left, y: r.bottom + 1 }) }}>Filter<span className="tb-caret">▾</span></button>
        <button className="tb-btn skp-tool" data-panel-showhide title="Toggles the visibility of all listed constraints from the 3D view" onClick={showHide}>
          <img src="./freecad-icons/Std_ToggleVisibility.svg" width={16} height={16} alt="" draggable={false} /></button>
        <SettingsButton entries={settings} />
      </div>
      {filterAt && <FilterPopup at={filterAt} which="constraints" items={C_FILTERS} states={p.cFilter} onToggle={(i) => setConstraintFilter(i, clicked(p.cFilter[i]))} onClose={() => setFilterAt(null)} />}
      <ul className="skp-list" ref={listRef} tabIndex={0} data-list="constraints"
        onMouseDown={(e) => { if (e.target === e.currentTarget && e.button === 0) { p.current = -1; selectRows([]) } }}
        onContextMenu={(e) => { e.preventDefault(); const li = (e.target as HTMLElement).closest('[data-row]'); setMenuAt({ x: e.clientX, y: e.clientY, row: li ? Number(li.getAttribute('data-row')) : null }) }}
        onKeyDown={(e) => {
          if (p.renaming !== null) return
          if (e.key === 'F2' && p.current >= 0) { e.preventDefault(); e.stopPropagation(); p.renaming = p.current; bump() }
          else if (e.key === 'Enter' && p.current >= 0) { e.preventDefault(); e.stopPropagation(); activate(p.current) }
        }}>
        {cs.map((c, i) => {
          const r = rows[i]
          return (
            <li key={i} data-row={i} data-text={r.text} data-hidden={r.hidden ? 1 : undefined} aria-selected={r.selected}
              className={r.selected ? 'sel' : p.current === i ? 'cur' : undefined} style={r.hidden ? { display: 'none' } : undefined} title={r.tip || undefined}
              onMouseDown={(e) => { e.stopPropagation(); press(i, e) }}
              onDoubleClick={(e) => { if ((e.target as HTMLElement).tagName !== 'INPUT') activate(i) }}>
              {/* ConstraintItem::updateVirtualSpaceStatus: checked when it is in the space the view shows */}
              <input type="checkbox" data-check checked={r.checked} title="Shows or hides the constraint in the 3D view" onMouseDown={(e) => e.stopPropagation()}
                onChange={(e) => doSetVirtualSpace([i], e.target.checked === S.isShownVirtualSpace())} />
              <ConstraintIcon c={c} />
              {p.renaming === i
                ? <RenameEditor initial={c.name} onDone={(text) => { p.renaming = null; bump(); if (text !== null) commitRename(i, text); listRef.current?.focus() }} />
                : <span className="skp-text">{r.text}</span>}
              {/* ExpressionDelegate::paint: bound-expression.svg on the right of a driving datum bound to an expression */}
              {c.driving && c.expr && <img className="skp-expr" src="./freecad-icons/bound-expression.svg" width={12} height={12} alt="" draggable={false} />}
            </li>
          )
        })}
      </ul>
      {menuAt && <ContextMenu at={menuAt} entries={constraintMenu(menuAt.row)} onClose={() => setMenuAt(null)} />}
    </PanelBox>
  )
}
function ConstraintIcon({ c }: { c: SK.Constraint }) {
  const name = constraintIcon(c)
  // selicon: a constraint that is not active in the sketch shows the icon's disabled pixmap
  const src = useIcon(name, c.active ? 'normal' : 'disabled')
  return <img src={src} width={24} height={24} alt="" draggable={false} className="skp-icon" data-icon={c.active ? name : `${name}:disabled`} />
}
function RenameEditor({ initial, onDone }: { initial: string; onDone(text: string | null): void }) {
  const ref = useRef<HTMLInputElement>(null)
  const done = useRef(false)
  useEffect(() => { ref.current?.focus(); ref.current?.select() }, [])
  const finish = (text: string | null) => { if (done.current) return; done.current = true; onDone(text) }
  return <input ref={ref} className="skp-rename qline" data-rename defaultValue={initial} onMouseDown={(e) => e.stopPropagation()}
    onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') { e.preventDefault(); finish(ref.current!.value) } else if (e.key === 'Escape') { e.preventDefault(); finish(null) } }}
    onBlur={() => finish(ref.current?.value ?? null)} />
}

// ── Elements ─────────────────────────────────────────────────────────────────────────────────────────────────────
const E_FILTERS: [string, number][] = [['Normal', 0], ['Construction', 0], ['Internal', 0], ['External', 0], ['All types', 0], ['Point', 1], ['Line', 1],
  ['Circle', 1], ['Ellipse', 1], ['Arc of circle', 1], ['Arc of ellipse', 1], ['Arc of hyperbola', 1], ['Arc of parabola', 1], ['B-spline', 1]]
const ALL_TYPES = 4
const TYPE_INDEX: Record<SK.Geo['type'], number> = { Point: 5, LineSegment: 6, Circle: 7, Ellipse: 8, ArcOfCircle: 9, ArcOfEllipse: 10, ArcOfHyperbola: 11,
  ArcOfParabola: 12, BSplineCurve: 13 }
type GeoState = 'normal' | 'construction' | 'constructionExternal' | 'internal' | 'external'
type Sub = 'edge' | 'start' | 'end' | 'mid'
/** ElementWidgetIcons::initIcons: each type's icons per point position. */
const ELEMENT_ICONS: Record<SK.Geo['type'], Partial<Record<Sub, string>>> = {
  ArcOfCircle: { edge: 'Sketcher_Element_Arc_Edge', start: 'Sketcher_Element_Arc_StartingPoint', end: 'Sketcher_Element_Arc_EndPoint', mid: 'Sketcher_Element_Arc_MidPoint' },
  Circle: { edge: 'Sketcher_Element_Circle_Edge', mid: 'Sketcher_Element_Circle_MidPoint' },
  LineSegment: { edge: 'Sketcher_Element_Line_Edge', start: 'Sketcher_Element_Line_StartingPoint', end: 'Sketcher_Element_Line_EndPoint' },
  Point: { start: 'Sketcher_Element_Point_StartingPoint' },
  Ellipse: { edge: 'Sketcher_Element_Ellipse_Edge_2', mid: 'Sketcher_Element_Ellipse_CentrePoint' },
  ArcOfEllipse: { edge: 'Sketcher_Element_Elliptical_Arc_Edge', start: 'Sketcher_Element_Elliptical_Arc_Start_Point', end: 'Sketcher_Element_Elliptical_Arc_End_Point', mid: 'Sketcher_Element_Elliptical_Arc_Centre_Point' },
  ArcOfHyperbola: { edge: 'Sketcher_Element_Hyperbolic_Arc_Edge', start: 'Sketcher_Element_Hyperbolic_Arc_Start_Point', end: 'Sketcher_Element_Hyperbolic_Arc_End_Point', mid: 'Sketcher_Element_Hyperbolic_Arc_Centre_Point' },
  ArcOfParabola: { edge: 'Sketcher_Element_Parabolic_Arc_Edge', start: 'Sketcher_Element_Parabolic_Arc_Start_Point', end: 'Sketcher_Element_Parabolic_Arc_End_Point', mid: 'Sketcher_Element_Parabolic_Arc_Centre_Point' },
  BSplineCurve: { edge: 'Sketcher_Element_BSpline_Edge', start: 'Sketcher_Element_BSpline_StartPoint', end: 'Sketcher_Element_BSpline_EndPoint' },
}
/** getIconImpl: an unknown position gives the invalid icon (in its normal colours, as the BadType entry). */
const elementIcon = (g: SK.Geo, sub: Sub) => ELEMENT_ICONS[g.type]?.[sub] ?? 'Sketcher_Element_SelectionTypeInvalid'
const MID_TYPES: SK.Geo['type'][] = ['ArcOfCircle', 'ArcOfEllipse', 'ArcOfHyperbola', 'ArcOfParabola', 'Circle', 'Ellipse']
const START_TYPES: SK.Geo['type'][] = ['Point', 'ArcOfCircle', 'ArcOfEllipse', 'ArcOfHyperbola', 'ArcOfParabola', 'LineSegment', 'BSplineCurve']
const END_TYPES: SK.Geo['type'][] = ['ArcOfCircle', 'ArcOfEllipse', 'ArcOfHyperbola', 'ArcOfParabola', 'LineSegment', 'BSplineCurve']
const validSub = (g: SK.Geo, sub: Sub) => (sub === 'mid' ? MID_TYPES.includes(g.type) : sub === 'start' ? START_TYPES.includes(g.type)
  : sub === 'end' ? END_TYPES.includes(g.type) : g.type !== 'Point')
type Element = { id: number; geo: SK.Geo; state: GeoState; label: string; start: number; mid: number; end: number
  /** A Text constraint's handle line (ElementItem::isTextHandle), and a geometry a Text or Group holds (hidden). */
  textHandle?: boolean; grouped?: boolean }
const BASE_NAMES: Record<SK.Geo['type'], string> = { Point: 'Point', LineSegment: 'Line', ArcOfCircle: 'Arc', Circle: 'Circle', Ellipse: 'Ellipse',
  ArcOfEllipse: 'Elliptical Arc', ArcOfHyperbola: 'Hyperbolic Arc', ArcOfParabola: 'Parabolic arc', BSplineCurve: 'B-spline' }
const EXT_NAMES: Record<SK.Geo['type'], [string, string]> = { Point: ['Point', 'Point'], LineSegment: ['Line', 'Line'], ArcOfCircle: ['Arc', 'Arc'],
  Circle: ['Circle', 'Circle'], Ellipse: ['Ellipse', 'Ellipse'], ArcOfEllipse: ['Elliptical Arc', 'Elliptical arc'], ArcOfHyperbola: ['Hyperbolic Arc', 'Hyperbolic arc'],
  ArcOfParabola: ['Parabolic Arc', 'Parabolic arc'], BSplineCurve: ['B-spline', 'B-spline'] }
/** TaskSketcherElements::slotElementsChanged: the sketch's geometry, then the external geometry after the axes. */
function elements(): Element[] {
  const geo = S.getGeometry(), cs = S.getConstraints(), ext = S.getExternal(), naming = param('ExtendedNaming')
  const internal = new Set(cs.filter((c) => c.type === 'InternalAlignment').map((c) => c.first))
  // the Group and Text constraints: their handles (named "Group" or "Text") and the geometry they hold (not listed)
  const handles = new Map<number, string>(), grouped = SK.inGroup(cs)
  for (const c of cs) if ((c.type === 'Group' || c.type === 'Text') && c.elements?.length) handles.set(c.elements[0][0], c.type)
  const out: Element[] = geo.map((g, k) => {
    const state: GeoState = internal.has(k) ? 'internal' : g.construction ? 'construction' : 'normal'
    const handle = g.type === 'LineSegment' ? handles.get(k) : undefined
    const base = handle ?? BASE_NAMES[g.type] ?? 'Other'
    const label = naming ? `${base}(Edge${k + 1}#ID${k})${state === 'construction' ? '-Construction' : state === 'internal' ? '-Internal' : ''}` : `${k + 1}-${base}`
    return { id: k, geo: g, state, label, start: S.vertexIndexOf(k, SK.START), mid: S.vertexIndexOf(k, SK.MID), end: S.vertexIndexOf(k, SK.END),
      textHandle: handle === 'Text', grouped: grouped.has(k) }
  })
  ext.geometry.forEach((g, k) => {
    const j = k + 3, id = -j, i = geo.length + j
    const [extended, short] = EXT_NAMES[g.type] ?? ['Other', 'Other']
    const ref = ext.refs[ext.owner[k] ?? k]
    const link = naming ? (ref ? `(ExternalEdge${j - 2}#ID${-j}, ${ref[0]}.${ref[1]})` : `(ExternalEdge${j - 2}#ID${-j})`) : ''
    // !Defining: the part file's external geometry is reference geometry (ConstructionExternal)
    out.push({ id, geo: g, state: 'constructionExternal', label: naming ? extended + link : `${i - 2}-${short}`, start: S.vertexIndexOf(id, SK.START), mid: S.vertexIndexOf(id, SK.MID), end: S.vertexIndexOf(id, SK.END) })
  })
  return out
}
/** TaskSketcherElements::setItemVisibility. */
function elementHidden(e: Element): boolean {
  if (e.grouped) return true // a member of a group is never listed
  if (!param('ElementFilterEnabled')) return false
  const f = getPanel().eFilter, off = (i: number) => f[i] === 0
  return (off(0) && e.state === 'normal') || (off(1) && e.state === 'construction') || (off(2) && e.state === 'internal') || (off(3) && e.state === 'external')
    || off(TYPE_INDEX[e.geo.type] ?? -1)
}
const subNames = (e: Element) => ({
  edge: e.id >= 0 ? `Edge${e.id + 1}` : `ExternalEdge${-e.id - 2}`,
  start: e.start >= 0 ? SK.vertexName(e.start) : null, end: e.end >= 0 ? SK.vertexName(e.end) : null, mid: e.mid >= 0 ? SK.vertexName(e.mid) : null,
})
function subSelected(e: Element, sel: Set<string>): Record<Sub, boolean> {
  const n = subNames(e)
  return { edge: sel.has(n.edge), start: !!n.start && sel.has(n.start), end: !!n.end && sel.has(n.end), mid: !!n.mid && sel.has(n.mid) }
}
export type ElementRow = { id: number; text: string; hidden: boolean; selected: boolean }
export function elementRows(): ElementRow[] {
  const sel = new Set(S.getSelection())
  return elements().map((e) => { const s = subSelected(e, sel); return { id: e.id, text: e.label, hidden: elementHidden(e), selected: s.edge || s.start || s.end || s.mid } })
}
/** onListMultiFilterItemChanged. */
function setElementFilter(index: number, state: Check) {
  const f = getPanel().eFilter
  f[index] = state
  if (index === ALL_TYPES) for (let i = ALL_TYPES + 1; i < f.length; i++) f[i] = state
  else if (index > ALL_TYPES) {
    const types = f.slice(ALL_TYPES + 1), some = types.some((x) => x === 2), none = types.some((x) => x === 0)
    f[ALL_TYPES] = some && none ? 1 : none ? 0 : 2
  }
  let st = 0
  for (let i = f.length - 1; i >= 0; i--) st = (st << 1) | (f[i] === 2 ? 1 : 0)
  setParam('ElementFilterState', st)
}
/** ElementView::contextMenuEvent. */
function elementMenu(): Entry[] {
  const items = S.getSelection().length > 0
  // one text handle selected: Convert to geometries (doConvertToGeometries: the handle deleted, which drops the Text
  // constraint and leaves the glyphs as plain geometry; FreeCAD opens no undo step for it)
  const one = S.getSelection(), m = one.length === 1 ? /^Edge(\d+)$/.exec(one[0]) : null, h = m ? Number(m[1]) - 1 : -1
  const isText = h >= 0 && S.getConstraints().some((c) => c.type === 'Text' && c.elements?.[0]?.[0] === h)
  const convert: Entry[] = isText ? ['sep', { label: 'Convert to geometries', onSelect: () => { S.clearSelection(); S.delGeometries([h]); S.solve() } }] : []
  const item = (icon: string, label: string, cmd: string, onSelection: boolean): Entry => ({ label, img: sketcherIcon(icon), kbd: cmdInfo(cmd).accel || undefined,
    disabled: onSelection && !items, onSelect: () => runSketchCommand(cmd) })
  return [
    ...convert,
    item('Constraint_PointOnPoint', 'Coincident Constraint', 'Sketcher_ConstrainCoincident', true),
    item('Constraint_PointOnObject', 'Point-On-Object Constraint', 'Sketcher_ConstrainPointOnObject', true),
    item('Constraint_Horizontal', 'Horizontal Constraint', 'Sketcher_ConstrainHorizontal', true),
    item('Constraint_Vertical', 'Vertical Constraint', 'Sketcher_ConstrainVertical', true),
    item('Constraint_Parallel', 'Parallel Constraint', 'Sketcher_ConstrainParallel', true),
    item('Constraint_Perpendicular', 'Perpendicular Constraint', 'Sketcher_ConstrainPerpendicular', true),
    item('Constraint_Tangent', 'Tangent Constraint', 'Sketcher_ConstrainTangent', true),
    item('Constraint_EqualLength', 'Equal Constraint', 'Sketcher_ConstrainEqual', true),
    item('Constraint_Symmetric', 'Symmetric Constraint', 'Sketcher_ConstrainSymmetric', true),
    item('Constraint_Block', 'Block Constraint', 'Sketcher_ConstrainBlock', true),
    // Sketcher_ConstrainGroup is not registered at this commit's maturity: CONTEXT_ITEM leaves it out
    item('Constraint_HorizontalDistance', 'Horizontal Dimension', 'Sketcher_ConstrainDistanceX', true),
    item('Constraint_VerticalDistance', 'Vertical Dimension', 'Sketcher_ConstrainDistanceY', true),
    item('Constraint_Length', 'Distance Dimension', 'Sketcher_ConstrainDistance', true),
    item('Constraint_Radiam', 'Radius/Diameter Dimension', 'Sketcher_ConstrainRadiam', true),
    item('Constraint_Radius', 'Radius Dimension', 'Sketcher_ConstrainRadius', true),
    item('Constraint_Diameter', 'Diameter Dimension', 'Sketcher_ConstrainDiameter', true),
    item('Constraint_InternalAngle', 'Angle Dimension', 'Sketcher_ConstrainAngle', true),
    item('Constraint_Lock', 'Lock Position', 'Sketcher_ConstrainLock', true),
    'sep',
    item('Sketcher_ToggleConstruction', 'Toggle Construction Geometry', 'Sketcher_ToggleConstruction', true),
    'sep',
    item('Sketcher_SelectConstraints', 'Select Constraints', 'Sketcher_SelectConstraints', true),
    item('Sketcher_SelectOrigin', 'Select Origin', 'Sketcher_SelectOrigin', false),
    item('Sketcher_SelectHorizontalAxis', 'Select Horizontal Axis', 'Sketcher_SelectHorizontalAxis', false),
    item('Sketcher_SelectVerticalAxis', 'Select Vertical Axis', 'Sketcher_SelectVerticalAxis', false),
    'sep',
    { label: 'Layer', sub: [
      { label: 'Layer 0', disabled: true, title: 'Visual layers are not in the part file yet' },
      { label: 'Layer 1', disabled: true, title: 'Visual layers are not in the part file yet' },
      { label: 'Hidden', disabled: true, title: 'Visual layers are not in the part file yet' }] },
    'sep',
    { label: 'Delete', kbd: isMac ? '⌫' : 'Del', disabled: !items, onSelect: () => S.deleteSelected() },
  ]
}
export function ElementsList() {
  useSketch(); usePanel()
  const p = getPanel()
  const els = elements(), sel = new Set(S.getSelection())
  const [filterAt, setFilterAt] = useState<{ x: number; y: number } | null>(null)
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null)
  const [hover, setHover] = useState<{ row: number; sub: Sub } | null>(null)
  const filterOn = param('ElementFilterEnabled')
  /** onListWidgetElementsItemPressed. */
  const press = (row: number, clickedOn: Sub, e: React.MouseEvent) => {
    const it = els[row], s0 = subSelected(it, sel)
    if (e.button === 2 && (s0.edge || s0.start || s0.end || s0.mid)) return // a right click on a selected item changes nothing
    const ctrl = isMac ? e.metaKey : e.ctrlKey
    const multiple = ctrl, consecutive = e.shiftKey && !ctrl
    const names: string[] = []
    els.forEach((item, i) => {
      const s = multiple || consecutive ? subSelected(item, sel) : { edge: false, start: false, end: false, mid: false }
      if (i === row) {
        if (clickedOn === 'mid' && MID_TYPES.includes(item.geo.type)) s.mid = !s.mid
        else if (clickedOn === 'start' && START_TYPES.includes(item.geo.type)) s.start = !s.start
        else if (clickedOn === 'end' && END_TYPES.includes(item.geo.type)) s.end = !s.end
        else if (clickedOn === 'edge' && item.geo.type !== 'Point') s.edge = !s.edge
      } else if (consecutive && p.previouslySelected >= 0 && ((i > p.focusItem && i < p.previouslySelected) || (i < p.focusItem && i > p.previouslySelected))) {
        if (item.geo.type === 'Point') s.start = true
        else s.edge = true
      }
      const n = subNames(item)
      if (s.edge) names.push(n.edge)
      if (s.start && n.start) names.push(n.start)
      if (s.end && n.end) names.push(n.end)
      if (s.mid && n.mid) names.push(n.mid)
    })
    ownSelection(() => S.setSelection(names))
    if (p.focusItem > -1 && p.focusItem < els.length) p.previouslySelected = p.focusItem
    bump()
  }
  /** onListWidgetElementsMouseMoveOnItem: the hovered sub-element is preselected in the view. */
  const hoverSub = (row: number, sub: Sub) => {
    if (hover?.row === row && hover.sub === sub) return
    setHover({ row, sub })
    const it = els[row]
    if (!validSub(it.geo, sub)) { S.setPreselection(null); return }
    if (sub === 'edge') S.setPreselection({ curve: it.id })
    else { const v = sub === 'start' ? it.start : sub === 'end' ? it.end : it.mid; S.setPreselection(v >= 0 ? { point: v } : null) }
  }
  return (
    <PanelBox title="Elements" icon="Sketcher_CreateLine" id="elements">
      <div className="skp-bar">
        <input type="checkbox" className="skp-filterbox" data-panel-filterbox checked={filterOn} title="Toggles the chosen element filters"
          onChange={(e) => setParam('ElementFilterEnabled', e.target.checked)} />
        <button className="skp-tool skp-filter" data-panel-filter disabled={!filterOn} title="Filters elements by type"
          onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setFilterAt(filterAt ? null : { x: r.left, y: r.bottom + 1 }) }}>Filter<span className="tb-caret">▾</span></button>
        <SettingsButton entries={() => [{ label: 'Extended information', checked: param('ExtendedNaming'), onSelect: () => setParam('ExtendedNaming', !param('ExtendedNaming')) }]} />
      </div>
      {filterAt && <FilterPopup at={filterAt} which="elements" items={E_FILTERS} states={p.eFilter} onToggle={(i) => setElementFilter(i, clicked(p.eFilter[i]))} onClose={() => setFilterAt(null)} />}
      <ul className="skp-list skp-elements" data-list="elements"
        onMouseDown={(e) => { if (e.target === e.currentTarget) S.clearSelection() }}
        onMouseLeave={() => { setHover(null); S.setPreselection(null) }}
        onContextMenu={(e) => { e.preventDefault(); setMenuAt({ x: e.clientX, y: e.clientY }) }}>
        {els.map((it, row) => {
          const s = subSelected(it, sel), any = s.edge || s.start || s.end || s.mid, hovered = hover?.row === row
          const opacity = (sub: Sub) => (s[sub] ? 1 : hovered && hover?.sub === sub ? 0.8 : hovered || any ? 0.4 : 1)
          const subAt = (e: React.MouseEvent): Sub => ((e.target as HTMLElement).closest('[data-sub]')?.getAttribute('data-sub') as Sub | null) ?? (it.geo.type === 'Point' ? 'start' : 'edge')
          return (
            <li key={it.id} data-row={row} data-text={it.label} data-hidden={elementHidden(it) ? 1 : undefined} aria-selected={any} className={any ? 'sel' : undefined}
              style={elementHidden(it) ? { display: 'none' } : undefined}
              onMouseEnter={() => { p.focusItem = row }}
              onMouseMove={(e) => hoverSub(row, subAt(e))}
              onMouseDown={(e) => { e.stopPropagation(); if ((e.target as HTMLElement).closest('[data-sub="check"]')) return; press(row, subAt(e), e) }}>
              {/* the visibility check box (layers): external geometry cannot be hidden; visual layers are not in the part file */}
              <input type="checkbox" data-sub="check" checked readOnly disabled title={it.id < 0 ? '' : 'Visual layers are not in the part file yet'} />
              {(['edge', 'start', 'end', 'mid'] as Sub[]).map((sub) => <ElementIcon key={sub} sub={sub} geo={it.geo} state={it.state} opacity={opacity(sub)} text={it.textHandle} />)}
              <span className="skp-text">{it.label}</span>
            </li>
          )
        })}
      </ul>
      {menuAt && <ContextMenu at={menuAt} entries={elementMenu()} onClose={() => setMenuAt(null)} />}
    </PanelBox>
  )
}
/** getIconImpl's text handle icons (Sketcher_CreateText, the text's start and end points; else the line's, in its
 *  normal colours). */
const TEXT_ICONS: Partial<Record<Sub, string>> = { edge: 'Sketcher_CreateText', start: 'Sketcher_Element_Text_StartPoint', end: 'Sketcher_Element_Text_EndPoint' }
function ElementIcon({ sub, geo, state, opacity, text }: { sub: Sub; geo: SK.Geo; state: GeoState; opacity: number; text?: boolean }) {
  const name = (text && TEXT_ICONS[sub]) || elementIcon(geo, sub)
  const variant = name === 'Sketcher_Element_SelectionTypeInvalid' || text ? 'normal' : state
  const src = useIcon(name, variant)
  return <img src={src} data-sub={sub} data-icon={`${name}:${variant}`} width={24} height={24} alt="" draggable={false} style={{ opacity }} className="skp-icon" />
}

// ── expressions (the part file's string values) ──────────────────────────────────────────────────────────────────
/** The part's PARAMS, as the expression engine takes them. */
export function paramVars(part: string | null): Record<string, number> {
  const params = part ? getState().features[part]?.params ?? {} : {}
  return Object.fromEntries(Object.entries(params).filter(([, v]) => typeof v === 'number')) as Record<string, number>
}
/** A value bound to an expression: what it evaluates to over the part's PARAMS (an angle's in degrees, as a unitless
 *  FreeCAD expression gives it, cad_agent/feature.py's Constraint.resolved). */
export function evaluateExpression(c: { type: string }, expr: string, part: string | null): number | null {
  const v = numberOf(expr, paramVars(part))
  if (v === null || !Number.isFinite(v)) return null
  return c.type === 'Angle' ? (v * Math.PI) / 180 : v
}
/** The part file's constraints for the edit: a string value becomes the expression it is, with its value. */
export function resolveExpressions(cons: Cons[], part: string | null): Cons[] {
  return cons.map((k) => {
    const v = k.value as unknown
    if (typeof v !== 'string') return k
    const n = evaluateExpression(k, v, part)
    if (n === null) report('warn', `Expression ${v} of a ${k.type} constraint could not be evaluated: its value is left at 0`)
    return { ...k, value: n ?? 0, expr: v }
  })
}

// ── for the checks ───────────────────────────────────────────────────────────────────────────────────────────────
/** What the boxes show (ui/scripts/sketchcheck.mjs's "panel" check, against fcsketch_dump.py's record of FreeCAD's). */
export function panelState() {
  if (!S.isEditing()) return null
  return { constraints: constraintRows(), elements: elementRows(), selection: [...S.getSelection()].sort(), virtualSpace: S.isShownVirtualSpace() }
}
