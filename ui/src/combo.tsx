// Qt's QComboBox, styled by FreeCAD.qss (~1416-1503: QComboBox, ::drop-down, ::down-arrow,
// QComboBox QAbstractItemView, ::item, :selected/:checked) — a drop-in replacement for the native
// <select> used throughout this app. Closed, it renders like today's native selects (same classes:
// .qselect / .wb / .pv / .tfield keep applying — see combo.css for the few extra rules a plain
// <select> never needed but a custom combobox does: the painted drop-down arrow, and the .pv/.tfield
// skins re-scoped off a class instead of the `select` tag). Open, it paints its own popup (a portal
// to document.body) instead of the browser/OS native one:
//  - opens on mouse press, below the box, or above if there's no room; at least as wide as the box
//  - the current item starts highlighted
//  - Up/Down/Home/End/PageUp/PageDown move the highlight while open
//  - Up/Down change the value directly, without opening, while closed (so does the wheel, when
//    the box is focused)
//  - typing jumps to the first item starting with the typed letters, open or closed
//  - Enter/Space selects (closed: opens instead); Esc or an outside click closes without changing
//    the value; Alt+Down/F4 toggles it open
//  - disabled options are greyed out and skipped by keyboard/typeahead navigation and clicks
//  - scrolls past maxVisibleItems (10)
// Focus never leaves the closed box (mousedown on a popup row calls preventDefault, same trick
// Gui::ContextMenu-style popups in this codebase don't need since they never held focus to begin
// with) — that's what lets aria-activedescendant point at the highlighted row the standard way.
import { Children, isValidElement, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type WheelEvent } from 'react'
import { createPortal } from 'react-dom'

const cls = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')

export type ComboChangeEvent = { target: { value: string } }

export interface QComboBoxProps {
  /** Controlled value (string or number — a numeric `value={x}` on an <option> works as it does
   *  natively: the DOM/compare value is String(x)). Omit and use `defaultValue` for uncontrolled. */
  value?: string | number
  defaultValue?: string | number
  onChange?(e: ComboChangeEvent): void
  onBlur?(): void
  disabled?: boolean
  className?: string
  title?: string
  autoFocus?: boolean
  id?: string
  /** <option value=… disabled?>label</option>, optionally grouped in <optgroup label=…>. */
  children?: ReactNode
}

type Item = { value: string; label: string; disabled: boolean; group?: string }

function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children)
  return ''
}

function optionOf(opt: ReactNode, group?: string): Item | null {
  if (!isValidElement(opt)) return null
  const p = opt.props as { value?: string | number; disabled?: boolean; children?: ReactNode }
  const label = textOf(p.children)
  return { value: p.value !== undefined ? String(p.value) : label, label, disabled: !!p.disabled, group }
}

/** Flattens <option>/<optgroup> children into a plain list, the way a real <select>.options would
 *  — including a bare <option> (no value=) defaulting its value to its text, same as HTML. */
function flatten(children: ReactNode): Item[] {
  const out: Item[] = []
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return
    if (child.type === 'optgroup') {
      const { label, children: kids } = child.props as { label?: string; children?: ReactNode }
      Children.forEach(kids, (opt) => { const it = optionOf(opt, label); if (it) out.push(it) })
    } else {
      const it = optionOf(child)
      if (it) out.push(it)
    }
  })
  return out
}

const ITEM_H = 20 // .combo-item's min-height in combo.css — keep in sync
const MAX_VISIBLE = 10 // QComboBox's default maxVisibleItems

export function QComboBox({ value, defaultValue, onChange, onBlur, disabled, className, title, autoFocus, id, children }: QComboBoxProps) {
  const items = useMemo(() => flatten(children), [children])
  const isControlled = value !== undefined
  const [inner, setInner] = useState(() => String(defaultValue ?? value ?? items.find((i) => !i.disabled)?.value ?? ''))
  const current = String(isControlled ? (value as string | number) : inner)
  const selectedIndex = items.findIndex((i) => i.value === current)

  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const safeHighlight = items.length ? Math.max(0, Math.min(highlight, items.length - 1)) : -1
  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null)
  const typeBuf = useRef(''), typeTimer = useRef<number | undefined>(undefined)
  const btnRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const listId = `cb${useId()}`

  useEffect(() => { if (disabled) setOpen(false) }, [disabled])

  const firstEnabled = () => items.findIndex((i) => !i.disabled)
  const lastEnabled = () => { for (let i = items.length - 1; i >= 0; i--) if (!items[i].disabled) return i; return -1 }
  const stepEnabled = (from: number, dir: 1 | -1) => {
    let i = from
    for (let k = 0; k < items.length; k++) {
      i += dir
      if (i < 0 || i >= items.length) return from
      if (!items[i].disabled) return i
    }
    return from
  }
  const pageStep = (from: number, dir: 1 | -1) => { let i = from; for (let k = 0; k < MAX_VISIBLE; k++) i = stepEnabled(i, dir); return i }

  const commit = (v: string) => {
    if (!isControlled) setInner(v)
    onChange?.({ target: { value: v } })
  }

  const reposition = () => {
    const b = btnRef.current
    if (!b) return
    const r = b.getBoundingClientRect()
    const h = Math.min(items.length, MAX_VISIBLE) * ITEM_H + 2 // +2 for the popup's own 1px border
    const openUp = r.bottom + h > innerHeight && r.top - h >= 0
    setRect({ left: Math.max(2, Math.min(r.left, innerWidth - r.width - 2)), top: openUp ? Math.max(2, r.top - h) : r.bottom, width: r.width })
  }
  const openPopup = () => {
    if (disabled || !items.length) return
    reposition()
    setHighlight(selectedIndex >= 0 ? selectedIndex : firstEnabled())
    setOpen(true)
  }
  const closePopup = () => setOpen(false)
  const selectIndex = (idx: number) => {
    const it = items[idx]
    if (!it || it.disabled) return
    commit(it.value)
    closePopup()
  }

  useEffect(() => {
    if (!open) return
    const away = (e: Event) => {
      const t = e.target as Node
      if (btnRef.current?.contains(t) || popRef.current?.contains(t)) return
      closePopup()
    }
    addEventListener('pointerdown', away, true)
    addEventListener('blur', closePopup)
    addEventListener('resize', reposition)
    addEventListener('scroll', reposition, true)
    return () => {
      removeEventListener('pointerdown', away, true)
      removeEventListener('blur', closePopup)
      removeEventListener('resize', reposition)
      removeEventListener('scroll', reposition, true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const typeahead = (ch: string) => {
    clearTimeout(typeTimer.current)
    typeBuf.current = (typeBuf.current + ch).toLowerCase()
    const buf = typeBuf.current
    typeTimer.current = window.setTimeout(() => { typeBuf.current = '' }, 700)
    const idx = items.findIndex((i) => !i.disabled && i.label.toLowerCase().startsWith(buf))
    if (idx < 0) return
    if (open) setHighlight(idx); else commit(items[idx].value)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    const k = e.key
    if ((e.altKey && k === 'ArrowDown') || k === 'F4') { e.preventDefault(); if (open) closePopup(); else openPopup(); return }
    if (!open) {
      if (k === 'ArrowDown' || k === 'ArrowUp') {
        e.preventDefault()
        const idx = stepEnabled(selectedIndex, k === 'ArrowDown' ? 1 : -1)
        if (idx >= 0) commit(items[idx].value)
        return
      }
      if (k === ' ' || k === 'Enter') { e.preventDefault(); openPopup(); return }
      if (k.length === 1 && /\S/.test(k)) { e.preventDefault(); typeahead(k) }
      return
    }
    switch (k) {
      case 'ArrowDown': e.preventDefault(); setHighlight((h) => stepEnabled(h, 1)); break
      case 'ArrowUp': e.preventDefault(); setHighlight((h) => stepEnabled(h, -1)); break
      case 'Home': e.preventDefault(); setHighlight(firstEnabled()); break
      case 'End': e.preventDefault(); setHighlight(lastEnabled()); break
      case 'PageDown': e.preventDefault(); setHighlight((h) => pageStep(h, 1)); break
      case 'PageUp': e.preventDefault(); setHighlight((h) => pageStep(h, -1)); break
      case 'Enter': case ' ': e.preventDefault(); selectIndex(safeHighlight); break
      case 'Escape': e.preventDefault(); e.stopPropagation(); closePopup(); break
      case 'Tab': closePopup(); break
      default: if (k.length === 1 && /\S/.test(k)) { e.preventDefault(); typeahead(k) }
    }
  }

  const onWheel = (e: WheelEvent<HTMLButtonElement>) => {
    if (disabled || open || document.activeElement !== btnRef.current) return
    e.preventDefault()
    const idx = stepEnabled(selectedIndex, e.deltaY > 0 ? 1 : -1)
    if (idx >= 0) commit(items[idx].value)
  }

  const label = items.find((i) => i.value === current)?.label ?? ''

  return (
    <>
      <button type="button" ref={btnRef} id={id} title={title} disabled={disabled} autoFocus={autoFocus}
        className={cls('qselect', className)} role="combobox" aria-haspopup="listbox" aria-expanded={open}
        aria-controls={open ? listId : undefined} aria-activedescendant={open && safeHighlight >= 0 ? `${listId}-${safeHighlight}` : undefined}
        onBlur={() => onBlur?.()} onKeyDown={onKeyDown} onWheel={onWheel}
        onMouseDown={(e) => { e.preventDefault(); btnRef.current?.focus(); if (open) closePopup(); else openPopup() }}>
        <span className="combo-label">{label}</span>
        <span className="combo-arrow" aria-hidden="true" />
      </button>
      {open && rect && createPortal(
        <div ref={popRef} id={listId} role="listbox" className="combo-popup"
          style={{ left: rect.left, top: rect.top, minWidth: rect.width }}
          onMouseDown={(e) => e.preventDefault()}>
          {items.map((it, idx) => (
            <div key={it.value + '#' + idx} id={`${listId}-${idx}`} role="option"
              aria-selected={it.value === current} aria-disabled={it.disabled || undefined}
              className={cls('combo-item', it.value === current && 'current', idx === safeHighlight && 'active', it.disabled && 'disabled')}
              onMouseEnter={() => !it.disabled && setHighlight(idx)}
              onClick={() => selectIndex(idx)}>
              {it.label}
            </div>
          ))}
        </div>, document.body,
      )}
    </>
  )
}
