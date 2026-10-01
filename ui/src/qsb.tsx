// Gui::QuantitySpinBox (Gui/QuantitySpinBox.cpp at FreeCAD main 3160daf1e2b6, LGPL-2.1-or-later):
// a value with its unit, written in the user's unit system. Typing commits each valid value
// (keyboard tracking); a bare number takes the unit shown; Enter and leaving the box check the
// text and, if it is wrong, say why under it. Up/Down, Page Up/Down, the wheel and the arrow
// buttons step by one unit of what is shown (⌘/Ctrl: ten). Esc puts the value back.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from './store'
import { isMac } from './nav'
import type { Dims } from './units-data'
import { DIAGNOSTIC, interpretInput, isNormalized, numberLength, shownText, type DisplayUnit } from './quantity-input'

export const LENGTH: Dims = [1, 0, 0, 0, 0, 0, 0, 0]
export const ANGLE: Dims = [0, 0, 0, 0, 0, 0, 0, 1]
export const NUMBER: Dims = [0, 0, 0, 0, 0, 0, 0, 0]

// Focus from the keyboard (Tab) selects the number, as Qt's TabFocusReason does.
let tabbing = false
addEventListener('keydown', (e) => { if (e.key === 'Tab') tabbing = true }, true)
addEventListener('pointerdown', () => { tabbing = false }, true)

type Props = {
  value: number; dims: Dims; onChange(v: number): void
  /** returnPressed / editingFinished. */
  onFinish?(): void
  /** Whether the text is a valid value (hasValidInput), for a dialog to check before OK. */
  onValid?(ok: boolean): void
  /** ExpressionSpinBox::handleKeyEvent: "=" in a bound box opens the expression editor. */
  onEquals?(text: string, at: { x: number; y: number }): void
  /** inputRejected(message, start, length): a commit (Return, leaving the box) was refused. */
  onRejected?(message: string, start: number, length: number): void
  /** inputCleared(): the box was emptied. */
  onCleared?(): void
  min?: number; max?: number; step?: number; disabled?: boolean; title?: string; autoFocus?: boolean
  /** QuantitySpinBox::setDecimals: override the schema's own decimal count for this box. */
  decimals?: number
  /** lineEdit()->setMaxLength() via autoAdjustWidth/maxExpectedDigits. */
  maxLength?: number
}

export function QuantityBox({ value, dims, onChange, onFinish, onValid, onEquals, onRejected, onCleared, min, max, step = 1, disabled, title, autoFocus, decimals, maxLength }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const committed = useRef(value)
  const display = useRef<DisplayUnit>(shownText({ value, dims }, decimals).display)
  const valid = useRef(true), validStr = useRef('')
  const [text, setText] = useState(() => { const s = shownText({ value, dims }, decimals).text; validStr.current = s; return s })
  const [tip, setTip] = useState<string | null>(null)
  // numericInputInvalid: shown only once a commit (Return, leaving the box) is refused.
  const [refused, setRefused] = useState(false)
  const [, redraw] = useState(0)
  const pendingSel = useRef<[number, number] | null>(null)
  const clamp = (v: number) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, v))
  const shown = (v: number) => shownText({ value: v, dims }, decimals)

  const setValid = (ok: boolean) => { if (valid.current !== ok) { valid.current = ok; onValid?.(ok); redraw((n) => n + 1) } }
  /** updateText: the value as the unit system writes it, preserving the cursor position
   *  (clamped to the number, as updateEdit's cursor-adjust does) across the reformat. */
  const reformat = (v: number) => {
    const s = shown(v)
    const sel = input.current?.selectionStart
    display.current = s.display
    validStr.current = s.text
    setText(s.text)
    setRefused(false)
    setValid(true)
    if (sel != null) { const c = Math.min(sel, numberLength(s.text)); pendingSel.current = [c, c] }
  }
  /** commitQuantity: keep it within range; tell the dialog. */
  const commit = (v: number, reformatText: boolean, notify: boolean) => {
    v = clamp(v)
    committed.current = v
    setTip(null)
    if (reformatText) reformat(v)
    else setValid(true)
    if (notify) onChange(v)
  }

  // A new value from outside (setValue), or a new unit system while not editing.
  const units = useStore((s) => s.units)
  useEffect(() => {
    if (value !== committed.current) { committed.current = value; reformat(value) }
  }, [value])
  useEffect(() => {
    if (document.activeElement !== input.current) reformat(committed.current)
  }, [units])
  useLayoutEffect(() => {
    if (pendingSel.current && input.current) { input.current.setSelectionRange(...pendingSel.current); pendingSel.current = null }
  })

  const opts = (phase: 'editing' | 'commit') => ({ dims, display: display.current, min, max, phase })
  /** userInput: each valid edit is committed as typed. */
  const edit = (t: string) => {
    if (t === '') onCleared?.()
    setText(t)
    setTip(null)
    setRefused(false)
    const r = interpretInput(t, opts('editing'))
    if (r.status === 'ok') { validStr.current = t; commit(r.q.value, false, true) }
    else setValid(false)
  }
  /** validateInput: check the text; if it is wrong, say why and select the fault. */
  const validate = (): boolean => {
    const t = input.current?.value ?? text
    if (valid.current && t !== '' && t === validStr.current) return true
    const r = interpretInput(t, opts('commit'))
    if (r.status === 'ok') { validStr.current = t; commit(r.q.value, false, true); return true }
    setValid(false)
    setRefused(true)
    setTip(DIAGNOSTIC[r.kind])
    pendingSel.current = [r.offset, Math.min(t.length, r.offset + r.length)]
    onRejected?.(DIAGNOSTIC[r.kind], r.offset, r.length)
    redraw((n) => n + 1) // to apply the selection
    return false
  }
  /** stepBy: in steps of one of what is shown, from the value as it stands. */
  const stepBy = (steps: number) => {
    const base = committed.current
    if ((steps > 0 && max !== undefined && base >= max) || (steps < 0 && min !== undefined && base <= min)) return
    const scale = shown(base).display.scale.value
    const v = clamp((base / scale + steps * step) * scale)
    commit(v, true, true)
    pendingSel.current = [0, numberLength(shown(v).text)]
  }
  const fast = (e: { metaKey: boolean; ctrlKey: boolean }) => ((isMac ? e.metaKey : e.ctrlKey) ? 10 : 1)

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === '=' && onEquals) {
      e.preventDefault()
      const r = e.currentTarget.getBoundingClientRect()
      onEquals(e.currentTarget.value, { x: r.left, y: r.top })
      return
    }
    if (e.key === 'Escape') {
      // Put the value back; the task panel then cancels.
      setTip(null)
      reformat(committed.current)
      return
    }
    if (e.key === 'Enter') {
      if (!validate()) { e.preventDefault(); e.stopPropagation(); return }
      const t = input.current?.value ?? ''
      if (!isNormalized(t, shown(committed.current).text)) reformat(committed.current)
      onFinish?.()
      return // a valid Return reaches the task panel (its default button)
    }
    // Page Up/Down's own x10 is Qt's stepBy(10) default; unlike Up/Down it never carries the
    // ⌘/Ctrl fast multiplier too (no such stacking exists anywhere in QuantitySpinBox/SpinBox).
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); stepBy((e.key === 'ArrowUp' ? 1 : -1) * fast(e)); return }
    if (e.key === 'PageUp' || e.key === 'PageDown') { e.preventDefault(); stepBy(e.key === 'PageUp' ? 10 : -10) }
  }
  const onBlur = () => {
    if (validate()) reformat(committed.current)
    setTip(null)
  }
  const onFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    // focusInEvent: Tab selects all, then just the number (selectNumber).
    if (!tabbing) return
    const el = e.currentTarget
    requestAnimationFrame(() => el.setSelectionRange(0, numberLength(el.value)))
  }

  // QAbstractSpinBox::wheelEvent: 120 per step, over the box, which takes focus.
  const acc = useRef(0)
  useEffect(() => {
    const el = input.current?.parentElement
    if (!el) return
    const wheel = (e: WheelEvent) => {
      if (disabled) return
      e.preventDefault()
      // A mouse notch is 120; trackpad pixels count double (Qt's cocoa pixelsToDegrees 1/4).
      const wd = (e as WheelEvent & { wheelDeltaY?: number }).wheelDeltaY
      acc.current += wd && Math.abs(wd) % 120 === 0 ? -Math.sign(e.deltaY) * Math.abs(wd)
        : -e.deltaY * (e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 800 : 2)
      const steps = Math.trunc(acc.current / 120)
      if (!steps) return
      acc.current -= steps * 120
      input.current?.focus()
      stepBy(steps * fast(e))
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  })

  // The arrow buttons repeat while held (SH_SpinBox_ClickAutoRepeatThreshold 500 ms, Rate 150 ms).
  const repeat = useRef<number>(0)
  const press = (dir: 1 | -1) => (e: React.PointerEvent) => {
    if (disabled) return
    e.preventDefault()
    input.current?.focus()
    const n = dir * fast(e)
    stepBy(n)
    const tick = () => { stepBy(n); repeat.current = window.setTimeout(tick, 150) }
    repeat.current = window.setTimeout(tick, 500)
    const stop = () => { clearTimeout(repeat.current); removeEventListener('pointerup', stop); removeEventListener('pointercancel', stop) }
    addEventListener('pointerup', stop)
    addEventListener('pointercancel', stop)
  }
  useEffect(() => () => clearTimeout(repeat.current), [])

  const upOff = disabled || (max !== undefined && committed.current >= max), downOff = disabled || (min !== undefined && committed.current <= min)
  return (
    <span className={`qsb${disabled ? ' off' : ''}`} title={title}>
      <input ref={input} value={text} disabled={disabled} autoFocus={autoFocus} maxLength={maxLength} className={refused ? 'bad' : ''} data-invalid={!valid.current || undefined} spellCheck={false}
        onChange={(e) => edit(e.target.value)} onKeyDown={onKeyDown} onBlur={onBlur} onFocus={onFocus} />
      <span className="qsb-btns">
        <button tabIndex={-1} className="qsb-btn" disabled={upOff} onPointerDown={press(1)} aria-label="Step up">▴</button>
        <button tabIndex={-1} className="qsb-btn" disabled={downOff} onPointerDown={press(-1)} aria-label="Step down">▾</button>
      </span>
      {tip && <span className="qsb-tip" role="alert">{tip}</span>}
    </span>
  )
}
