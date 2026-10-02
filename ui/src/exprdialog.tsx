// Gui::Dialog::DlgExpressionInput (Gui/Dialogs/DlgExpressionInput.cpp at FreeCAD main
// 3160daf1e2b6, LGPL-2.1-or-later): typing "=" in a property's field opens it over the field.
// The expression is checked as it is typed and its result shown; OK takes it, Reset
// (discard) and Esc leave the value as it was. The part's other parameters are its names, offered
// as you type by ExpressionTextEdit's completer (Gui/ExpressionCompleter.cpp): the identifier
// before the cursor is matched case-insensitively anywhere in a name (MatchContains), or at its
// start with the context menu's Exact Match; the arrows preview a name in the text (highlighted),
// Tab or a click takes it (Tab with none chosen takes the first), Esc closes the list.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { evaluate } from './expr'
import { ContextMenu } from './chrome'
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
  const [exact, setExact] = useState(false)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  // The completer: its matches, the highlighted row and the prefix's range in the text.
  const [comp, setComp] = useState<{ items: string[]; row: number; start: number; end: number } | null>(null)
  // ExpressionCompleter::slotUpdate: the token before the cursor (the tokenizer's last identifier).
  const update = (value: string, pos: number, exactMatch = exact) => {
    const m = /[A-Za-z_][A-Za-z0-9_]*$/.exec(value.slice(0, pos))
    if (!m) { setComp(null); return }
    const p = m[0].toLowerCase()
    const items = Object.keys(vars).filter((n) => (exactMatch ? n.toLowerCase().startsWith(p) : n.toLowerCase().includes(p))).sort()
    setComp(items.length ? { items, row: -1, start: m.index, end: pos } : null)
  }
  // slotCompleteText: replace the prefix with the completion, keeping the list's range in step.
  const complete = (name: string, keepOpen: boolean, row = -1) => {
    if (!comp) return
    const t = area.current!, v = expr.slice(0, comp.start) + name + expr.slice(comp.end), end = comp.start + name.length
    setExpr(v)
    setComp(keepOpen ? { ...comp, row, end } : null)
    requestAnimationFrame(() => { t.focus(); t.selectionStart = t.selectionEnd = end })
  }
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
          if (comp && e.target === area.current) {
            if (e.key === 'Escape') { e.preventDefault(); setComp(null); return } // the popup takes Esc
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
              e.preventDefault()
              const n = comp.items.length, row = e.key === 'ArrowDown' ? (comp.row + 1) % n : (comp.row <= 0 ? n - 1 : comp.row - 1)
              complete(comp.items[row], true, row)
              return
            }
            if (e.key === 'Tab') { e.preventDefault(); complete(comp.items[Math.max(0, comp.row)], false); return }
            if (e.key === 'Enter' && comp.row >= 0) { e.preventDefault(); setComp(null); return } // activated: already in the text
          }
          if (e.key === 'Escape') { e.preventDefault(); onCancel() }
          else if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ok() }
        }}>
        <textarea ref={area} className="expr-text" value={expr} spellCheck={false}
          onChange={(e) => { setExpr(e.target.value); update(e.target.value, e.target.selectionStart) }}
          onBlur={() => setTimeout(() => { if (document.activeElement !== area.current) setComp(null) }, 150)}
          onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }} />
        {comp && <div className="expr-comp" role="listbox">{comp.items.map((n, i) => (
          <div key={n} role="option" aria-selected={i === comp.row} className={i === comp.row ? 'sel' : undefined}
            onMouseDown={(e) => { e.preventDefault(); complete(n, false) }}>{n}</div>))}</div>}
        {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
          { label: 'Select All', onSelect: () => area.current?.select() },
          'sep',
          { label: 'Exact Match', checked: exact, onSelect: () => { setExact(!exact); const t = area.current; if (t) update(t.value, t.selectionStart, !exact) } },
        ]} />}
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
