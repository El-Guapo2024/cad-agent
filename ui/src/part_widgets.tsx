// SPDX-License-Identifier: LGPL-2.1-or-later
// The small widgets the Part task panels share (part_tasks.tsx, part_static.tsx), each as the .ui dialogs lay them out.
import type { ReactNode } from 'react'
import { cls } from './panels'
import { QuantityBox, LENGTH } from './qsb'

export function Buttons({ items }: { items: [string, () => void, boolean?][] }) {
  return <div className="tbuttons pd-buttons">{items.map(([t, f, def]) => <button key={t} className={cls('qbtn', def && 'default')} onClick={f}>{t}</button>)}</div>
}
export function Field({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return <label className="tfield" title={title}><span>{label}</span>{children}</label>
}
export function Check({ label, checked, onChange, disabled, name }: { label: string; checked: boolean; onChange(v: boolean): void; disabled?: boolean; name?: string }) {
  return <label className="tcheck" data-qf={name}><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} /> {label}</label>
}
export function Radio({ label, checked, onChange, name }: { label: string; checked: boolean; onChange(): void; name?: string }) {
  return <label className="tcheck" data-qf={name}><input type="radio" checked={checked} onChange={onChange} /> {label}</label>
}
export function Legend({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="tgroup"><legend>{title}</legend>{children}</fieldset>
}
/** A Gui::QuantitySpinBox of the dialog: a length, an angle, or a plain number. */
export function Q({ label, value, dims = LENGTH, onChange, min, max, disabled, name, step, decimals }: { label?: string; value: number; dims?: number[]; onChange(v: number): void
  min?: number; max?: number; disabled?: boolean; name?: string; step?: number; decimals?: number }) {
  const box = <span data-qf={name}><QuantityBox key={`${name}:${value}`} value={value} dims={dims as typeof LENGTH} min={min} max={max} step={step} disabled={disabled} decimals={decimals} onChange={onChange} /></span>
  return label ? <Field label={label}>{box}</Field> : box
}
