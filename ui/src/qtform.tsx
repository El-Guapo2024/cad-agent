// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/PreferencePages/DlgSettingsAdvanced.cpp: 2020 Zheng Lei (realthunder)
//   src/Gui/PrefWidgets.cpp: 2004 Werner Mayer
//   src/Gui/Widgets.cpp: 2004 Werner Mayer
//   No copyright line in the file: src/Gui/Stylesheets/FreeCAD.qss
// A Qt Designer form drawn the way Qt lays it out: what uic reads from FreeCAD's .ui files (uiforms.ts, made by ui/scripts/uigen.py)
// becomes DOM, and the Preferences pages (prefs-pages.tsx) bind the widgets that do something here by their object name.
//
// Qt's layouts (QBoxLayout, QGridLayout, qGeomCalc) give every item its size hint and then share what is left: if some item
// expands (a spacer or a widget whose size policy has the Expanding flag, or a stretch factor) the expanding ones get it all and the
// rest stay at their hints; if none does, all the items share it as equal totals, an item that would get less than its hint keeping
// the hint and the others dividing the remainder. That is CSS grid's `1fr` (minmax(auto, 1fr)) and a flex item's `flex: 1 1 0`, with
// the hint as the floor: a label or a check box has its text for it, a control a `min-width` from the hint the real FreeCAD measured
// (fc.h). A widget wider than the cell's room is held by its maximum size and sits at the cell's left; one that cannot grow
// (Fixed) is as wide as its hint; one that cannot grow taller is centred in the row. A hidden widget leaves no row, no column and no
// space. QGroupBox is FreeCAD.qss's: an 18 px band above for the title, a 1 px frame, 2 px under it.
import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { QComboBox } from './combo'
import type { UiForm, UiItem, UiLayout, UiWidget } from './uiforms'
import './qtform.css'

export const cls = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')
const HUGE = 16777215

/** What a page says about one widget of its form, by object name. A widget with no binding shows what FreeCAD shows, greyed out. */
export interface Binding {
  /** checked (check box, radio button, checkable group box), number (spin box), option value (combo box), text (line edit), #rrggbb (colour button). */
  value?: boolean | number | string
  /** Called with the new value: a widget with one is live, one without is greyed out. */
  set?: (v: never) => void
  /** Greyed out although it has a setter (or live although it has none: false). */
  off?: boolean
  /** Why it is greyed out, as the tool tip says it (after FreeCAD's own text). */
  why?: string
  /** Not shown: it leaves no space. */
  hide?: boolean
  /** The text of a label, button or check box, where it is not FreeCAD's. */
  text?: string
  /** A tool tip, where it is not FreeCAD's. */
  tip?: string
  /** The items of a combo box: value and text. */
  opts?: readonly (readonly [string | number, string])[]
  /** Overrides of a spin box's range, step, decimals, suffix and prefix. */
  min?: number; max?: number; step?: number; dec?: number; suffix?: string; prefix?: string
  /** A spin box that sets its value when typing ends (Return, or leaving the box), not with each valid keystroke. */
  lazy?: boolean
  /** A push button or tool button was pressed. */
  click?: () => void
  /** A link in a rich-text label was followed. */
  link?: (href: string) => void
  /** Replaces what the widget shows (a tree, a table, the preview). */
  node?: ReactNode
  /** The colour button's colour has a transparency (QColorDialog's alpha channel): `value` is #rrggbbaa. */
  alpha?: boolean
  /** Extra class names of the widget's element. */
  cls?: string
}
export type Bindings = Record<string, Binding>

const BindCtx = createContext<Bindings>({})
/** A checkable group box that is off turns off everything in it. */
const OffCtx = createContext(false)

// ── Policies and hints ──────────────────────────────────────────────────────────────────────────────────────────
/** QSizePolicy of each class, where the form does not say (fc.pol is what the real FreeCAD has). */
const DEFAULT_POL: Record<string, string> = {
  QLabel: 'PP', QCheckBox: 'mF', QRadioButton: 'mF', QPushButton: 'mF', QToolButton: 'mF', QComboBox: 'PF', QSpinBox: 'mF', QDoubleSpinBox: 'mF',
  QLineEdit: 'EF', QGroupBox: 'PP', QTreeWidget: 'EE', QTableWidget: 'EE', QListWidget: 'EE', QTextEdit: 'EE', QWidget: 'PP', Line: 'EF',
}
const base = (c: string) => c.replace(/^Gui::(Pref)?/, 'Q').replace(/^QColorButton$/, 'QPushButton').replace(/^QFileChooser$/, 'QLineEdit')
  .replace(/^QUnitSpinBox$|^QQuantitySpinBox$|^QUIntSpinBox$/, 'QSpinBox').replace(/^QAccelLineEdit$|^QModifierLineEdit$/, 'QLineEdit')
  .replace(/^QDoubleSpinBox$/, 'QDoubleSpinBox')
const polOf = (w: UiWidget) => w.fc?.pol ?? DEFAULT_POL[base(w.c)] ?? 'PP'
/** Can it grow beyond its hint? (Preferred, Minimum, Expanding, MinimumExpanding, Ignored: yes. Fixed, Maximum: no.) */
const grows = (p: string) => 'PmEXI'.includes(p)
/** QSizePolicy::ExpandFlag: Expanding and MinimumExpanding. */
const expands = (p: string) => p === 'E' || p === 'X'
/** Controls whose hint is the floor of their column: a combo box is as wide as its longest item, a spin box as its widest value. */
const FLOOR = new Set(['QComboBox', 'QSpinBox', 'QDoubleSpinBox', 'QPushButton', 'QToolButton', 'QLineEdit'])
const hasFloor = (w: UiWidget) => FLOOR.has(base(w.c))
/** Whether a nested layout in a grid cell makes the cell's column expand, as an expanding spacer or widget in it would: not in the layouts
 *  as FreeCAD measured them (the Navigation page: a spacer inside a box in a cell leaves the column at its share). In a box layout it
 *  does (a group box whose layout holds a table is itself expanding, the page gives it what is left over). */
const NESTED_EXPANDS_IN_GRID = false

const P = (w: UiWidget) => w.p ?? {}
const sizeProp = (w: UiWidget, k: string) => P(w)[k] as [number, number] | undefined

/** Is this widget shown? A page's `hide` first; else FreeCAD hides it (the fractional-inch box under a unit system without inches). */
function hiddenW(w: UiWidget, b: Binding | undefined) {
  return b?.hide ?? w.fc?.hid === 1
}

// ── Layout items ─────────────────────────────────────────────────────────────────────────────────────────────────
/** An item is shown unless it is a hidden widget, or a layout of nothing but hidden items. */
function visible(it: UiItem, bind: Bindings): boolean {
  if (it.w) return !hiddenW(it.w, bind[it.w.n])
  if (it.l) return it.l.i.some((x) => visible(x, bind))
  return true
}
/** Does the item expand along an axis (h or v)? A widget does if its size policy says so, or if it can grow that way and what its layout holds
 *  expands (QWidgetItem::expandingDirections): a group box with a table in it takes all the room the page has left over. */
function expansive(it: UiItem, axis: 'h' | 'v', bind: Bindings, inGrid = false): boolean {
  const k = axis === 'h' ? 0 : 1
  if (it.w) {
    const p = polOf(it.w)
    if (expands(p[k]) || (it.w.fc?.stretch?.[k] ?? 0) > 0) return true
    return !!it.w.l && grows(p[k]) && layoutExpands(it.w.l, axis, bind)
  }
  if (it.s) return it.s.o === axis && (it.s.t === 'Expanding' || it.s.t === 'MinimumExpanding')
  if (it.l) return (!inGrid || NESTED_EXPANDS_IN_GRID) && layoutExpands(it.l, axis, bind)
  return false
}
function layoutExpands(l: UiLayout, axis: 'h' | 'v', bind: Bindings): boolean {
  return l.i.some((it, i) => visible(it, bind) && (expansive(it, axis, bind) || (l.t !== 'G' && (l.st?.[i] ?? 0) > 0)))
}

type Slot = CSSProperties

/** What an item's own box asks of its cell: how it is held, aligned and floored by its size policy, hint and maximum size. */
function boxOf(w: UiWidget): CSSProperties {
  const [hp, vp] = polOf(w)
  const [hw, hh] = w.fc?.h ?? [0, 0]
  const min = sizeProp(w, 'minimumSize'), max = sizeProp(w, 'maximumSize')
  const s: CSSProperties = {}
  if (hasFloor(w)) s.minWidth = Math.max(Math.min(hw, max?.[0] ?? HUGE), min?.[0] ?? 0)
  else if (min?.[0]) s.minWidth = min[0]
  if (min?.[1]) s.minHeight = min[1]
  if (max && max[0] < HUGE) s.maxWidth = max[0]
  if (max && max[1] < HUGE) s.maxHeight = max[1]
  // (a widget the dump has no hint for, one of the viewer's own buttons, is as large as it is)
  const known = w.fc?.h !== undefined
  // (qSmartMaxSize: a policy that cannot grow caps the widget at its hint only where the form sets no maximum size of its own)
  const capW = max === undefined || max[0] >= HUGE, capH = max === undefined || max[1] >= HUGE
  if (hp === 'F' && known) { s.width = hw; s.maxWidth = hw }
  else if (hp === 'M' && known && capW) s.maxWidth = hw
  if (vp === 'F' && known) s.height = hh
  else if (vp === 'M' && known && capH) s.maxHeight = hh
  return s
}
/** Where a widget sits in a cell that is larger than it: left (or as the item says), the middle of the row. */
function alignOf(w: UiWidget, it: UiItem): CSSProperties {
  const [hp, vp] = polOf(w)
  const max = sizeProp(w, 'maximumSize')
  const left = (!grows(hp) && !(hp === 'M' && max !== undefined && max[0] < HUGE)) || (max !== undefined && max[0] < HUGE)
  const a = it.a ?? []
  const horiz: CSSProperties['justifySelf'] = a.includes('AlignRight') ? 'end' : a.includes('AlignHCenter') ? 'center' : left || a.includes('AlignLeft') ? 'start' : 'stretch'
  const vert: CSSProperties['alignSelf'] = a.includes('AlignTop') ? 'start' : a.includes('AlignBottom') ? 'end' : (!grows(vp) && !(vp === 'M' && max !== undefined && max[1] < HUGE)) || a.includes('AlignVCenter') ? 'center' : 'stretch'
  return { justifySelf: horiz, alignSelf: vert }
}

/** The text of a form string: a mnemonic's ampersand is not shown. */
const plain = (s: string) => s.replace(/&&/g, '\0').replace(/&/g, '').replace(/\0/g, '&')
const isRich = (s: string, w: UiWidget) => P(w).textFormat === 'RichText' || /^\s*<(html|p|b|i|a|span|br|!doctype)[\s>/]/i.test(s)
/** A rich-text label's HTML, from the form (never from a person): links go to the page's `link` handler. */
function Rich({ html, link, off }: { html: string; link?: (href: string) => void; off?: boolean }) {
  // (a link in a disabled label is not one: it says so to the page, and nothing follows it)
  return <span className="qf-rich" ref={(el) => { el?.querySelectorAll('a').forEach((a) => { if (off) a.setAttribute('aria-disabled', 'true'); else a.removeAttribute('aria-disabled') }) }} onClick={(e) => {
    const a = (e.target as HTMLElement).closest('a')
    if (!a) return
    e.preventDefault()
    if (off) return
    const href = a.getAttribute('href') ?? ''
    if (link) link(href)
    else if (/^https?:/.test(href)) window.open(href, '_blank', 'noopener')
  }} dangerouslySetInnerHTML={{ __html: html.replace(/<!DOCTYPE[^>]*>|<head>[\s\S]*?<\/head>|<\/?(html|body)[^>]*>/gi, '').replace(/<p [^>]*>|<\/p>/gi, ' ') }} />
}

function tipOf(w: UiWidget, b: Binding | undefined, off: boolean): string | undefined {
  const t = b?.tip ?? (P(w).toolTip as string | undefined) ?? ''
  const why = off && b?.why ? `n/a: ${b.why}` : ''
  return [t, why].filter(Boolean).join('\n\n') || undefined
}

// ── Widgets ──────────────────────────────────────────────────────────────────────────────────────────────────────
function Spacer({ s, slot }: { s: NonNullable<UiItem['s']>; slot: Slot }) {
  const horiz = s.o === 'h'
  const style: CSSProperties = { ...slot, width: s.w, height: s.h, minWidth: horiz && s.t !== 'Fixed' ? 0 : undefined, minHeight: !horiz && s.t !== 'Fixed' ? 0 : undefined }
  return <div className="qf-spacer" style={style} aria-hidden />
}

type WProps = { w: UiWidget; slot: Slot }

function Widget({ w, slot }: WProps) {
  const bind = useContext(BindCtx)
  const groupOff = useContext(OffCtx)
  const b = bind[w.n]
  if (hiddenW(w, b)) return null
  const c = base(w.c)
  const p = P(w)
  const fc = w.fc
  const live = !!b?.set || !!b?.click
  const operated = c !== 'QGroupBox' && c !== 'QWidget' && c !== 'QLabel' && c !== 'Line' && c !== 'QTreeWidget' && c !== 'QTableWidget' && c !== 'QListWidget' && c !== 'QTextEdit'
  const off = groupOff || (b?.off ?? (!live && operated)) || p.enabled === false || (!b && fc?.dis === 1)
  const tip = tipOf(w, b, off)
  const style: CSSProperties = { ...boxOf(w), ...slot }
  const common = { 'data-qf': w.n, title: tip, style }
  const txt = plain(b?.text ?? (p.text as string | undefined) ?? fc?.t ?? '')
  const fontSize = (p.font as { pt?: number } | undefined)?.pt

  if (b?.node !== undefined && c !== 'QGroupBox' && c !== 'QPushButton' && c !== 'QToolButton') {
    // A scroll area or a viewer is as large as its hint (a tree's, a text box's, 256 x 192) whatever it holds, and then as the layout gives it room
    const scroll = /^Q(Tree|Table|List)Widget$|^QTextEdit$/.test(c)
    const area = scroll || w.l !== undefined || expands(polOf(w)[1])
    const [hw, hh] = fc?.h ?? [0, 0]
    // (a plain widget's size hint is only the size it has: a viewer, with no layout of its own to size it, is as large as it is given)
    return (
      <div {...common} style={scroll ? { ...style, minWidth: style.minWidth ?? hw, minHeight: hh } : area ? { ...style, minHeight: 104 } : style} className={cls('qf-node', area && 'area', w.l && 'over', b.cls)}>
        {area ? <div className="qf-fill">{b.node}</div> : b.node}
        {w.l && <LayoutBox l={w.l} margins={w.l.m} className="qf-over" kids={w.ch} />}
      </div>)
  }

  // the colour buttons (Gui::ColorButton is a QPushButton with a `color`)
  if (/Color/.test(w.c)) {
    const col = typeof b?.value === 'string' ? b.value : argb(fc?.col ?? argbOf(p.color as number[] | undefined))
    return <ColorBtn {...common} value={col} off={off} alpha={b?.alpha} onSet={b?.set as ((v: string) => void) | undefined} />
  }
  switch (c) {
    case 'QGroupBox': return <GroupBox w={w} b={b} off={off} style={style} tip={tip} />
    case 'QWidget': return <Container w={w} style={style} />
    case 'QLabel': {
      const al = (p.alignment as string[] | undefined) ?? []
      const rich = isRich(txt, w)
      return (
        <label {...common} className={cls('qf-label', P(w).wordWrap === true && 'wrap', al.includes('AlignRight') && 'right', al.includes('AlignHCenter') && 'center', off && 'off', b?.cls)}
          style={{ ...style, fontSize }}>
          {rich ? <Rich html={txt} link={b?.link} off={off} /> : txt}
        </label>)
    }
    case 'QCheckBox': case 'QRadioButton': {
      const radio = c === 'QRadioButton'
      const checked = typeof b?.value === 'boolean' ? b.value : (fc?.chk ?? (p.checked as boolean | undefined) ?? false)
      return (
        <label {...common} className={cls('qf-check', radio && 'radio', off && 'off', b?.cls)}>
          <input type={radio ? 'radio' : 'checkbox'} checked={checked} disabled={off} onChange={(e) => (b?.set as ((v: boolean) => void) | undefined)?.(e.target.checked)} />
          <span>{txt}</span>
        </label>)
    }
    case 'QPushButton': case 'QToolButton': {
      const icon = typeof p.icon === 'string' && p.icon ? p.icon.replace(/^.*\//, '') : ''
      const tool = c === 'QToolButton'
      const is = (p.iconSize as [number, number] | undefined)?.[0] ?? (tool ? (fc?.h ? fc.h[0] - 8 : 24) : 16)
      return (
        <button {...common} type="button" className={cls(tool ? 'qf-tool' : 'qf-btn', icon && 'icon', b?.cls)} disabled={off} onClick={() => b?.click?.()}>
          {b?.node ?? (icon ? <img src={`./freecad-icons/${icon}`} width={is} height={is} alt="" /> : txt)}
          {b?.node === undefined && icon && !tool && txt}
        </button>)
    }
    case 'QComboBox': {
      const items = b?.opts ?? (fc?.it ?? (w.items as string[] | undefined) ?? []).map((t, i) => [i, t] as const)
      const val = b?.value ?? fc?.ci ?? (p.currentIndex as number | undefined) ?? 0
      return (
        <QComboBox className={cls('qf-combo', b?.cls)} value={String(val)} disabled={off} title={tip} style={style} data-qf={w.n}
          onChange={(e) => (b?.set as ((v: string | number) => void) | undefined)?.(typeof items[0]?.[0] === 'number' ? Number(e.target.value) : e.target.value)}>
          {items.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </QComboBox>)
    }
    case 'QSpinBox': case 'QDoubleSpinBox': {
      // Gui::QuantitySpinBox (and PrefUnitSpinBox, PrefQuantitySpinBox) is a spin box that writes a quantity: two decimals, 27 px high
      const quantity = /QuantitySpinBox|UnitSpinBox/.test(w.c)
      const dbl = c === 'QDoubleSpinBox' || w.c === 'Gui::PrefDoubleSpinBox'
      const value = typeof b?.value === 'number' ? b.value : (fc?.v ?? (p.value as number | undefined) ?? 0)
      // QAbstractSpinBox::alignment is AlignLeft unless the form says otherwise
      const right = (p.alignment as string[] | undefined)?.includes('AlignRight') ?? false
      return (
        <Spin {...common} value={value} min={b?.min ?? (p.minimum as number | undefined) ?? 0} max={b?.max ?? (p.maximum as number | undefined) ?? 99} step={b?.step ?? (p.singleStep as number | undefined) ?? 1}
          dec={b?.dec ?? (p.decimals as number | undefined) ?? (dbl || quantity ? 2 : 0)} suffix={b?.suffix ?? (p.suffix as string | undefined) ?? ''} prefix={b?.prefix ?? (p.prefix as string | undefined) ?? ''}
          special={(p.specialValueText as string | undefined) ?? ''} left={!right} quantity={quantity} off={off} lazy={b?.lazy} onSet={b?.set as ((v: number) => void) | undefined} />)
    }
    case 'QLineEdit': {
      const value = typeof b?.value === 'string' ? b.value : (fc?.t ?? '')
      // Gui::FileChooser: a line edit and a button with "..." (FreeCAD.qss: its button has no minimum width)
      if (/FileChooser/.test(w.c)) {
        return (
          <span {...common} className={cls('qf-chooser', off && 'off', b?.cls)}>
            <input type="text" value={value} readOnly disabled={off && !value} spellCheck={false} onChange={() => {}} />
            <button type="button" disabled={off} onClick={() => b?.click?.()}>...</button>
          </span>)
      }
      return (
        <input {...common} type="text" className={cls('qf-edit', b?.cls)} value={value} readOnly={!b?.set || p.readOnly === true} disabled={off && !(p.readOnly === true)} spellCheck={false}
          placeholder={fc?.ph ?? (p.placeholderText as string | undefined) ?? undefined} onChange={(e) => (b?.set as ((v: string) => void) | undefined)?.(e.target.value)} />)
    }
    case 'Line': return <div {...common} className="qf-line" />
    case 'QTreeWidget': case 'QTableWidget': case 'QListWidget': case 'QTextEdit': return <Sheet w={w} style={style} tip={tip} />
    default: break
  }
  return <div {...common} className="qf-node">{w.c}</div>
}

/** A colour from `#aarrggbb` (what the dump reads off a QColor) to `#rrggbbaa`, which a colour button holds. */
function argb(s: string | undefined): string {
  if (!s) return '#00000000'
  const m = /^#([0-9a-f]{2})([0-9a-f]{6})$/i.exec(s)
  return m ? `#${m[2]}${m[1]}` : s
}
function argbOf(c: number[] | undefined): string | undefined {
  if (!c) return undefined
  return '#' + [c[0], c[1], c[2], c[3]].map((n) => n.toString(16).padStart(2, '0')).join('')
}

/** QGroupBox: FreeCAD.qss gives it 18 px above for the title, a 1 px frame and 2 px under it. A checkable one has its check box in the
 *  title, and while it is off everything in it is off. */
function GroupBox({ w, b, off, style, tip }: { w: UiWidget; b: Binding | undefined; off: boolean; style: CSSProperties; tip?: string }) {
  const p = P(w)
  const checkable = p.checkable === true
  const checked = checkable ? (typeof b?.value === 'boolean' ? b.value : (w.fc?.chk ?? (p.checked as boolean | undefined) ?? false)) : true
  const title = plain(b?.text ?? (p.title as string | undefined) ?? '')
  return (
    <div data-qf={w.n} className={cls('qf-gb', off && 'off', b?.cls)} style={style} title={tip}>
      <div className="qf-gb-title">
        {checkable
          ? <label className={cls('qf-check', off && !b?.set && 'off')}><input type="checkbox" checked={checked} disabled={off && !b?.set} onChange={(e) => (b?.set as ((v: boolean) => void) | undefined)?.(e.target.checked)} /><span>{title}</span></label>
          : <span>{title}</span>}
      </div>
      <OffCtx.Provider value={off || !checked}>
        <LayoutBox l={w.l} margins={w.l?.m} className="qf-gb-frame" kids={w.ch} />
      </OffCtx.Provider>
    </div>)
}

/** A plain QWidget: the form's page, or a container with a layout of its own. */
function Container({ w, style }: { w: UiWidget; style: CSSProperties }) {
  return <div data-qf={w.n} className="qf-widget" style={style}><LayoutBox l={w.l} margins={w.l?.m} kids={w.ch} /></div>
}

// ── Layouts ──────────────────────────────────────────────────────────────────────────────────────────────────────
const LD = createContext<[number, number]>([6, 9])
/** The margins of a layout: the form's own, else the layout default of the .ui (margin 11) or the style's (9). */
function marginsOf(m: (number | null)[] | undefined, nested: boolean, ld: [number, number]): [number, number, number, number] {
  const d = nested ? 0 : ld[1]
  return [m?.[0] ?? d, m?.[1] ?? d, m?.[2] ?? d, m?.[3] ?? d]
}

/** Does the item hold anything but spacers? Qt's layouts count a spacer as empty (QSpacerItem::isEmpty is always true), and leave no spacing for an
 *  empty row, column or box item: the spacing comes once between two neighbours that are not empty, right after the first of them. */
function nonEmpty(it: UiItem, bind: Bindings): boolean {
  if (it.w) return !hiddenW(it.w, bind[it.w.n])
  if (it.l) return it.l.i.some((x) => nonEmpty(x, bind))
  return false
}

/** Is a row or column at its largest when it has its hint? qGridLayout keeps each track's maximum size as qMaxExpCalc folds it from its items (the smallest
 *  maximum of those that cannot expand, the largest of those that can; a spacer is empty and counts only where nothing else is), and qGeomCalc leaves a
 *  track whose maximum is no more than its hint at that hint, whatever room there is: a track of Fixed widgets, or of a Fixed widget and a label. */
function atMax(items: UiItem[], axis: 'h' | 'v', bind: Bindings): boolean {
  const k = axis === 'h' ? 0 : 1
  let max = HUGE, exp = false, empty = true, hint = 0
  for (const it of items) {
    let bmax = HUGE, bhint = 0
    if (it.w) {
      const mx = sizeProp(it.w, 'maximumSize')?.[k]
      bhint = it.w.fc?.h?.[k] ?? 0
      bmax = mx !== undefined && mx < HUGE ? mx : HUGE
      const pol = polOf(it.w)[k]
      if (pol === 'F' || (pol === 'M' && bmax >= HUGE)) bmax = Math.min(bmax, bhint)
    } else if (it.s) {
      bhint = k === 0 ? it.s.w : it.s.h
      if (it.s.o === axis && (it.s.t === 'Fixed' || it.s.t === 'Maximum')) bmax = bhint
    }
    const bexp = expansive(it, axis, bind, true), bempty = !nonEmpty(it, bind)
    if (exp) { if (bexp) max = Math.max(max, bmax) }
    else if (bexp || (empty && (!bempty || max === 0))) max = bmax
    else if (empty === bempty) max = Math.min(max, bmax)
    exp = exp || bexp
    empty = empty && bempty
    hint = Math.max(hint, bhint)
  }
  return max <= hint
}

/** The tracks of a row or column of items, as qGeomCalc sizes them. An expanding track (one with an expanding item, or a stretch factor) takes all
 *  that is left, as CSS stretches `auto` tracks (the others being `max-content`); with none expanding the tracks share the room as equal totals,
 *  which is `1fr`, floored at the items' hints (their minimum widths). Between two tracks that are not empty goes one gap, as a track of its own
 *  right after the first, so that a track of nothing but a spacer has no gap after it (the next one starts where the spacer ends). */
function tracks(list: number[], full: (t: number) => boolean, expandsOf: (t: number) => boolean, stretch: (t: number) => number, fixed: (t: number) => boolean, gap: number, width: boolean, fit: boolean, floor?: Map<number, number>) {
  const anyExp = list.some((t) => expandsOf(t) || stretch(t) > 0)
  // Two columns or rows that expand, with no stretch factor, get equal totals (qGeomCalc's `ideal`), each as large as its hint at least: `1fr` with the hint as the floor.
  const share = !fit && !list.some((t) => stretch(t) > 0) && list.filter(expandsOf).length > 1
  const tmpl: string[] = [], css = new Map<number, number>()
  list.forEach((t, k) => {
    const st = stretch(t), f = floor?.get(t) ? `${Math.round(floor.get(t)!)}px` : ''
    tmpl.push(st > 0 ? `minmax(${f || 'auto'}, ${st}fr)`
      : expandsOf(t) ? (share ? `minmax(${f || 'auto'}, 1fr)` : f ? `minmax(${f}, auto)` : 'auto')
      : anyExp || !full(t) || fixed(t) ? (f ? `minmax(${f}, max-content)` : 'max-content')
      : width && !fit ? `minmax(${f || 'auto'}, 1fr)` : f ? `minmax(${f}, auto)` : 'auto')
    css.set(t, tmpl.length)
    if (full(t) && list.slice(k + 1).some(full)) tmpl.push(`${gap}px`)
  })
  return { tmpl: tmpl.join(' '), arr: tmpl, css }
}

/** qGeomCalc for room beyond the hints (qlayoutengine.cpp): the items that expand, or have a stretch factor, share the space as equal totals (or in
 *  proportion to their stretch), none of them below its hint; the others stay at theirs; with none expanding all share it. */
function geom(items: { hint: number; exp: boolean; st: number }[], space: number): number[] {
  const size = items.map((i) => i.hint)
  if (space <= size.reduce((a, b) => a + b, 0)) return size
  const wanna = items.some((i) => i.exp || i.st > 0)
  const done = items.map((i) => wanna && !i.exp && i.st === 0)
  let left = space - items.reduce((n, i, k) => n + (done[k] ? i.hint : 0), 0)
  for (;;) {
    const open = items.map((_, k) => k).filter((k) => !done[k])
    if (!open.length) break
    const sum = open.reduce((n, k) => n + items[k].st, 0)
    const ideal = (k: number) => (sum ? (left * items[k].st) / sum : left / open.length)
    const low = open.filter((k) => ideal(k) < items[k].hint)
    if (!low.length) { open.forEach((k) => { size[k] = ideal(k) }); break }
    for (const k of low) { size[k] = items[k].hint; done[k] = true; left -= items[k].hint }
  }
  return size
}

function LayoutBox({ l, margins, className, nested = false, fit = false, slot, kids }: { l: UiLayout | undefined; margins: (number | null)[] | undefined; className?: string; nested?: boolean; fit?: boolean; slot?: Slot; kids?: UiWidget[] }) {
  const bind = useContext(BindCtx)
  const ld = useContext(LD)
  if (!l) return <div className={className} style={slot}>{kids?.map((k) => <Widget key={k.n} w={k} slot={{}} />)}</div>
  const [ml, mt, mr, mb] = marginsOf(margins, nested, ld)
  const sp = l.sp ?? ld[0]
  const shown = l.i.map((it, k) => ({ it, k })).filter(({ it }) => visible(it, bind))
  const padding = `${mt}px ${mr}px ${mb}px ${ml}px`
  const render = (it: UiItem, i: number, s: Slot, fitWidth = false) => {
    if (it.w) return <Widget key={it.w.n} w={it.w} slot={{ ...alignOf(it.w, it), ...s }} />
    if (it.l) return <LayoutBox key={`l${i}`} l={it.l} margins={it.l.m} nested fit={fitWidth} slot={s} />
    if (it.s) return <Spacer key={`s${i}`} s={it.s} slot={s} />
    return null
  }
  if (l.t === 'G') {
    // rows and columns that hold nothing shown are not there
    const used = (get: (it: UiItem) => [number, number]) => {
      const set = new Set<number>()
      for (const { it } of shown) { const [a, n] = get(it); for (let x = a; x < a + n; x++) set.add(x) }
      return [...set].sort((a, b) => a - b)
    }
    const rows = used((it) => [it.r ?? 0, it.rs ?? 1]), cols = used((it) => [it.c ?? 0, it.cs ?? 1])
    // a track is empty (no spacing around it) unless an item that is not a spacer lies over it, a widget across it making it not empty (distributeMultiBox)
    const covers = (axis: 'h' | 'v', it: UiItem, t: number) => { const a = (axis === 'h' ? it.c : it.r) ?? 0; return t >= a && t < a + ((axis === 'h' ? it.cs : it.rs) ?? 1) }
    const full = (axis: 'h' | 'v') => (t: number) => shown.some(({ it }) => covers(axis, it, t) && nonEmpty(it, bind))
    // the stretch factor of a track: the layout's own, else the largest of the widgets over it (a widget across tracks gives each of them its stretch)
    const stretchAt = (axis: 'h' | 'v') => (t: number) => {
      const explicit = (axis === 'h' ? l.cst?.[t] : l.rst?.[t]) ?? 0
      if (explicit > 0) return explicit
      return Math.max(0, ...shown.filter(({ it }) => it.w && covers(axis, it, t)).map(({ it }) => it.w!.fc?.stretch?.[axis === 'h' ? 0 : 1] ?? 0))
    }
    const expandsAt = (axis: 'h' | 'v') => (t: number) => shown.some(({ it }) => ((axis === 'h' ? it.cs : it.rs) ?? 1) === 1 && (axis === 'h' ? it.c ?? 0 : it.r ?? 0) === t && expansive(it, axis, bind, true))
    // A widget across columns needs its hint over them. Qt lays it out over the columns with qGeomCalc, its hint as the room (distributeMultiBox):
    // the columns that expand take what the others lack, so a column that nothing else is in stays at nothing, and the columns that hold more than
    // their own items' hints (a spacer's width is its hint) are floored at what they got.
    const hintOf = (it: UiItem) => (it.w ? Math.min(it.w.fc?.h?.[0] ?? 0, sizeProp(it.w, 'maximumSize')?.[0] ?? HUGE) : it.s && it.s.o === 'h' ? it.s.w : 0)
    const gapC = l.hsp ?? sp
    const expC = expandsAt('h')
    const colHint = new Map<number, number>()
    for (const { it } of shown) if ((it.cs ?? 1) === 1) { const c = it.c ?? 0; colHint.set(c, Math.max(colHint.get(c) ?? 0, hintOf(it))) }
    const own = new Map(colHint)
    shown.filter(({ it }) => (it.cs ?? 1) > 1 && (it.w || it.l)).sort((x, y) => (x.it.cs ?? 1) - (y.it.cs ?? 1)).forEach(({ it }) => {
      const span = cols.filter((x) => x >= (it.c ?? 0) && x < (it.c ?? 0) + (it.cs ?? 1))
      if (span.length < 2) return
      const sizes = geom(span.map((x) => ({ hint: colHint.get(x) ?? 0, exp: expC(x), st: l.cst?.[x] ?? 0 })), hintOf(it) - gapC * (span.length - 1))
      span.forEach((x, k) => colHint.set(x, Math.max(colHint.get(x) ?? 0, sizes[k])))
    })
    const floors = new Map<number, number>()
    for (const [c, h] of colHint) if (h > (own.get(c) ?? 0)) floors.set(c, h)
    const atMaxAt = (axis: 'h' | 'v') => (t: number) => atMax(shown.filter(({ it }) => ((axis === 'h' ? it.cs : it.rs) ?? 1) === 1 && (axis === 'h' ? it.c ?? 0 : it.r ?? 0) === t).map((x) => x.it), axis, bind)
    const cT = tracks(cols, full('h'), expandsAt('h'), stretchAt('h'), atMaxAt('h'), l.hsp ?? sp, true, fit, floors)
    const rT = tracks(rows, full('v'), expandsAt('v'), stretchAt('v'), atMaxAt('v'), l.vsp ?? sp, false, fit)
    const line = (list: number[], css: Map<number, number>, from: number, n: number) => {
      const inside = list.filter((x) => x >= from && x < from + n)
      return `${css.get(inside[0])} / ${css.get(inside[inside.length - 1])! + 1}`
    }
    return (
      <div className={cls('qf-grid', className)} style={{ ...slot, padding, gridTemplateColumns: cT.tmpl, gridTemplateRows: rT.tmpl }}>
        {shown.map(({ it }, i) => render(it, i, {
          gridRow: line(rows, rT.css, it.r ?? 0, it.rs ?? 1),
          gridColumn: line(cols, cT.css, it.c ?? 0, it.cs ?? 1),
          // an item across columns does not size them (Qt shares what it needs out over the columns that are there): it is as wide as they are
          ...((it.cs ?? 1) > 1 && (it.w || it.l) ? { width: 0, minWidth: '100%', maxWidth: 'none' } : {}),
        }, !(cT.arr[(cT.css.get(it.c ?? 0) ?? 1) - 1] ?? '').includes('fr')))}
      </div>)
  }
  // A box layout is a row or a column of tracks, sized and spaced the same way
  const horiz = l.t === 'H'
  const axis = horiz ? 'h' : 'v'
  const at = shown.map(({ it }, i) => ({ it, i }))
  const idx = at.map((x) => x.i)
  const stretchOf = (i: number) => l.st?.[shown[i].k] ?? shown[i].it.w?.fc?.stretch?.[horiz ? 0 : 1] ?? 0
  const T = tracks(idx, (i) => nonEmpty(shown[i].it, bind), (i) => expansive(shown[i].it, axis, bind), stretchOf, (i) => atMax([shown[i].it], axis, bind), sp, horiz, fit)
  const across = horiz ? { gridTemplateRows: 'auto', gridTemplateColumns: T.tmpl } : { gridTemplateColumns: 'minmax(0, 1fr)', gridTemplateRows: T.tmpl }
  return (
    <div className={cls('qf-grid', horiz ? 'h' : 'v', className)} style={{ ...slot, padding, ...across }}>
      {at.map(({ it, i }) => render(it, i, horiz ? { gridColumn: T.css.get(i), gridRow: 1 } : { gridRow: T.css.get(i), gridColumn: 1 }, horiz ? !T.arr[T.css.get(i)! - 1].includes('fr') : fit))}
    </div>)
}

/** A form: its page, drawn from its layout with the page's bindings. */
export function QtForm({ form, bind }: { form: UiForm; bind: Bindings }) {
  const ld: [number, number] = form.ld ?? [6, 9]
  return (
    <BindCtx.Provider value={bind}>
      <LD.Provider value={ld}>
        <div className="qf-form" data-form={form.title}>
          <PageRoot w={form.root} />
        </div>
      </LD.Provider>
    </BindCtx.Provider>)
}
/** The page widget: DlgPreferencesImp::createPreferencePage resets its margins, and its layout's, to 0. */
function PageRoot({ w }: { w: UiWidget }) {
  return <div className="qf-page" data-qf={w.n}><LayoutBox l={w.l} margins={[0, 0, 0, 0]} kids={w.ch} /></div>
}

// ── Spin box ─────────────────────────────────────────────────────────────────────────────────────────────────────
/** QSpinBox and QDoubleSpinBox as FreeCAD.qss draws them: the value right-aligned (or as the form says) with its suffix, an up and a
 *  down button; typing commits what is valid, Up/Down and the wheel step, leaving the box shows the value as the box writes it. */
function Spin({ value, min, max, step, dec, suffix, prefix, special, left, quantity, off, lazy, onSet, ...rest }: {
  value: number; min: number; max: number; step: number; dec: number; suffix: string; prefix: string; special: string; left: boolean; quantity?: boolean; off: boolean; lazy?: boolean
  onSet?: (v: number) => void; style?: CSSProperties; title?: string; 'data-qf'?: string
}) {
  const live = !!onSet && !off
  const show = (v: number) => (special && v === min ? special : `${prefix}${v.toFixed(dec)}${suffix}`)
  const [text, setText] = useState(show(value))
  const [focus, setFocus] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!focus) setText(show(value)) }, [value, focus, dec, suffix, prefix]) // eslint-disable-line react-hooks/exhaustive-deps
  const clamp = (v: number) => Math.min(max, Math.max(min, v))
  const num = (t: string) => { const n = Number(t.replace(suffix.trim(), '').replace(prefix, '').replace(',', '.').trim()); return Number.isFinite(n) && t.trim() !== '' ? n : null }
  const commit = (v: number) => { const c = Math.round(clamp(v) * 10 ** dec) / 10 ** dec; if (c !== value) onSet?.(c as never); return c }
  const stepBy = (n: number) => { const c = commit(value + n * step); setText(show(c)) }
  const hold = useRef<number>(0)
  const press = (dir: 1 | -1) => (e: React.PointerEvent) => {
    if (!live) return
    e.preventDefault(); input.current?.focus()
    stepBy(dir)
    const tick = () => { stepBy(dir); hold.current = window.setTimeout(tick, 150) }
    hold.current = window.setTimeout(tick, 500)
    const stop = () => { clearTimeout(hold.current); removeEventListener('pointerup', stop); removeEventListener('pointercancel', stop) }
    addEventListener('pointerup', stop); addEventListener('pointercancel', stop)
  }
  useEffect(() => () => clearTimeout(hold.current), [])
  return (
    <span {...rest} className={cls('qf-spin', quantity && 'q', off && 'off', focus && 'focus')}>
      <input ref={input} type="text" inputMode="decimal" spellCheck={false} value={text} disabled={off} readOnly={!live} style={{ textAlign: left ? 'left' : 'right' }}
        onFocus={() => setFocus(true)}
        onBlur={() => { setFocus(false); const n = num(text); if (n !== null) { const c = commit(n); setText(show(c)) } else setText(show(value)) }}
        onChange={(e) => { setText(e.target.value); const n = num(e.target.value); if (!lazy && n !== null && n >= min && n <= max) commit(n) }}
        onKeyDown={(e) => {
          if (!live) return
          if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); stepBy(e.key === 'ArrowUp' ? 1 : -1) }
          else if (e.key === 'PageUp' || e.key === 'PageDown') { e.preventDefault(); stepBy(e.key === 'PageUp' ? 10 : -10) }
          else if (e.key === 'Enter') { const n = num(text); if (n !== null) setText(show(commit(n))) }
        }}
        onWheel={(e) => { if (live && document.activeElement === input.current) { e.preventDefault(); stepBy(e.deltaY < 0 ? 1 : -1) } }} />
      <span className="qf-spin-btns">
        <button tabIndex={-1} type="button" className="up" disabled={!live || value >= max} onPointerDown={press(1)} aria-label="Step up" />
        <button tabIndex={-1} type="button" className="down" disabled={!live || value <= min} onPointerDown={press(-1)} aria-label="Step down" />
      </span>
    </span>)
}

// ── Colour button ────────────────────────────────────────────────────────────────────────────────────────────────
/** Gui::ColorButton: a push button with the colour in a framed swatch. The colour is #rrggbb, or #rrggbbaa where it has a transparency. */
function ColorBtn({ value, off, alpha, onSet, ...rest }: { value: string; off: boolean; alpha?: boolean; onSet?: (v: string) => void; style?: CSSProperties; title?: string; 'data-qf'?: string }) {
  const rgb = value.slice(0, 7), a = value.length > 7 ? parseInt(value.slice(7, 9), 16) / 255 : 1
  const [open, setOpen] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  return (
    <span {...rest} className={cls('qf-color', off && 'off')}>
      <button type="button" disabled={off} onClick={() => { if (alpha) setOpen((o) => !o); else input.current?.click() }}>
        <span className="qf-swatch" style={{ background: `linear-gradient(${rgb + Math.round(a * 255).toString(16).padStart(2, '0')}, ${rgb + Math.round(a * 255).toString(16).padStart(2, '0')}), #fff` }} />
      </button>
      <input ref={input} type="color" tabIndex={-1} value={rgb} disabled={off} onChange={(e) => onSet?.(alpha ? e.target.value + value.slice(7, 9) || e.target.value + 'ff' : e.target.value)} />
      {open && alpha && (
        <span className="qf-color-pop" onMouseLeave={() => setOpen(false)}>
          <input type="color" value={rgb} onChange={(e) => onSet?.(e.target.value + (value.slice(7, 9) || 'ff'))} />
          <input type="range" min={0} max={255} value={Math.round(a * 255)} onChange={(e) => onSet?.(rgb + Number(e.target.value).toString(16).padStart(2, '0'))} aria-label="Transparency" />
        </span>)}
    </span>)
}

// ── Trees, tables and lists a page does not fill ────────────────────────────────────────────────────────────────
/** A tree, table or list as FreeCAD shows it in a fresh profile: its header and rows (fc.hd, fc.rows). */
function Sheet({ w, style, tip }: { w: UiWidget; style: CSSProperties; tip?: string }) {
  const head = w.fc?.hd ?? (w.cols as string[] | undefined) ?? []
  const rows = w.fc?.rows ?? []
  return (
    <div data-qf={w.n} className={cls('qf-sheet', base(w.c) === 'QTextEdit' && 'text')} style={style} title={tip}>
      {head.length > 0 && <div className="qf-sheet-head" style={{ gridTemplateColumns: `repeat(${head.length}, 1fr)` }}>{head.map((h, i) => <span key={i}>{h}</span>)}</div>}
      {rows.map((r, i) => <div key={i} className="qf-sheet-row" style={{ gridTemplateColumns: `repeat(${head.length || 1}, 1fr)` }}>{r.map((c, j) => <span key={j}>{c}</span>)}</div>)}
    </div>)
}

export { Spin as QSpin, ColorBtn as QColorButton }
