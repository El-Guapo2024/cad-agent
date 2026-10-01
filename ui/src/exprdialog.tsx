// Gui::Dialog::DlgExpressionInput (Gui/Dialogs/DlgExpressionInput.cpp at FreeCAD main
// 3160daf1e2b6, LGPL-2.1-or-later): typing "=" in a property's field opens it over the field.
// The expression is checked as it is typed and its result shown; OK takes it, Reset
// (discard) and Esc leave the value as it was. The part's other parameters are its names.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { evaluate } from './expr'
import { userString, type Quantity } from './quantity'
import type { Dims } from './units-data'

type Props = {
  /** Where the field is: the dialog opens on it. */
  at: { x: number; y: number }
  /** The field's text (the parent's "text" property). */
  text: string
  /** The unit the property wants (impliedUnit), or null for a plain number. */
  dims: Dims | null
  vars: Record<string, Quantity>
  /** NumberRange::throwIfOutOfRange, in the field's own internal unit. */
  min?: number
  max?: number
  onOk(value: number, expression: string): void
  onCancel(): void
}

export function ExpressionDialog({ at, text, dims, vars, min, max, onOk, onCancel }: Props) {
  const [expr, setExpr] = useState(text)
  const area = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { area.current?.focus(); area.current?.select() }, [])
  // checkExpression. DlgExpressionInput leaves the last Result message/color on screen while
  // the box is empty rather than blanking it, so remember the last non-empty result.
  const last = useRef({ msg: '', bad: false })
  let msg = '', bad = false, value: number | null = null
  if (expr.trim()) {
    try {
      const q = evaluate(expr, vars)
      if (!Number.isFinite(q.value)) throw new Error('Not a Number')
      const unitless = q.dims.every((d) => d === 0)
      msg = userString(q).text
      if (dims && !dims.every((d) => d === 0)) {
        if (!unitless && !q.dims.every((d, i) => d === dims[i])) throw new Error('Unit mismatch between result and required unit')
      } else if (!unitless) { msg += ' (Warning: unit discarded)'; bad = true }
      const resultDims = dims && unitless ? dims : q.dims
      if ((min !== undefined && q.value < min) || (max !== undefined && q.value > max)) {
        const fmt = (v: number) => userString({ value: v, dims: resultDims }).text
        throw new Error(`Value out of range (${fmt(q.value)} out of [${fmt(min ?? q.value)}, ${fmt(max ?? q.value)}])`)
      }
      value = q.value
      if (dims && unitless) msg = userString({ value: q.value, dims }).text
    } catch (e) { msg = (e as Error).message; bad = true; value = null }
    last.current = { msg, bad }
  } else {
    msg = last.current.msg
    bad = last.current.bad
  }
  const ok = () => { if (value !== null) onOk(value, expr.trim()) }
  return createPortal(
    <div className="expr-back" onPointerDown={(e) => { if (e.target === e.currentTarget) onCancel() }}>
      <div className="expr-dlg" role="dialog" aria-label="Expression Editor" style={{ left: Math.max(4, Math.min(at.x, innerWidth - 330)), top: Math.max(4, Math.min(at.y, innerHeight - 170)) }}
        onKeyDown={(e) => {
          e.stopPropagation()
          if (e.key === 'Escape') { e.preventDefault(); onCancel() }
          else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ok() }
        }}>
        <textarea ref={area} className="expr-text" value={expr} spellCheck={false} onChange={(e) => setExpr(e.target.value)} />
        <div className="expr-result"><span>Result</span><span className={bad ? 'expr-msg bad' : 'expr-msg'}>{msg}</span></div>
        <div className="expr-buttons">
          <button className={value === null ? 'qbtn' : 'qbtn default'} disabled={value === null} onClick={ok}>OK</button>
          <button className={value === null ? 'qbtn default' : 'qbtn'} title="Revert to last calculated value (as constant)" onClick={onCancel}>Reset</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
