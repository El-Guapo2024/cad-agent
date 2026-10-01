// QMessageBox: a modal box with a title, an icon, the text and its buttons. Return presses
// the default (first) button; Esc the escape button (Cancel, No, or the only one).
import { useEffect, useRef, useSyncExternalStore, type ReactElement } from 'react'
import { createPortal } from 'react-dom'

export type MsgIcon = 'critical' | 'warning' | 'information' | 'question'
type Box = { title: string; icon: MsgIcon | null; text: string; buttons: string[]; resolve(button: string): void }

let box: Box | null = null
let before: HTMLElement | null = null // focus goes back here when the box closes
const subs = new Set<() => void>()
const set = (b: Box | null) => { box = b; subs.forEach((f) => f()) }

/** Show a message box (icon null: QMessageBox::NoIcon); resolves to the button pressed. */
export function messageBox(icon: MsgIcon | null, title: string, text: string, buttons: string[] = ['OK']): Promise<string> {
  before = document.activeElement as HTMLElement | null
  return new Promise((resolve) => set({ title, icon, text, buttons, resolve }))
}

const ICON: Record<MsgIcon, ReactElement> = {
  critical: <svg viewBox="0 0 32 32" width="32" height="32"><circle cx="16" cy="16" r="15" fill="#e0342c" /><path d="M10.5 10.5l11 11M21.5 10.5l-11 11" stroke="#fff" strokeWidth="3" strokeLinecap="round" /></svg>,
  warning: <svg viewBox="0 0 32 32" width="32" height="32"><path d="M16 2L31 29H1z" fill="#f5b400" /><path d="M16 11v9" stroke="#000" strokeWidth="3" strokeLinecap="round" /><circle cx="16" cy="24.5" r="1.8" /></svg>,
  information: <svg viewBox="0 0 32 32" width="32" height="32"><circle cx="16" cy="16" r="15" fill="#1c7ed6" /><circle cx="16" cy="9" r="2" fill="#fff" /><path d="M16 14v10" stroke="#fff" strokeWidth="3" strokeLinecap="round" /></svg>,
  question: <svg viewBox="0 0 32 32" width="32" height="32"><circle cx="16" cy="16" r="15" fill="#1c7ed6" /><path d="M11.5 12a4.5 4.5 0 1 1 6.2 4.2c-1 .4-1.7 1.2-1.7 2.3V20" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" /><circle cx="16" cy="24.5" r="1.8" fill="#fff" /></svg>,
}

export function MessageBoxHost() {
  const b = useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => box)
  const first = useRef<HTMLButtonElement>(null)
  useEffect(() => { first.current?.focus() }, [b])
  if (!b) return null
  const done = (button: string) => { set(null); before?.focus(); before = null; b.resolve(button) }
  const escape = b.buttons.find((x) => /^(Cancel|No|Close)$/.test(x)) ?? (b.buttons.length === 1 ? b.buttons[0] : null)
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => {
      e.stopPropagation()
      if (e.key === 'Escape' && escape) { e.preventDefault(); done(escape) }
    }}>
      <div className="msgbox" role="alertdialog" aria-label={b.title}>
        {b.title && <div className="msgbox-title">{b.title}</div>}
        <div className="msgbox-body">
          {b.icon && <span className="msgbox-icon">{ICON[b.icon]}</span>}
          <div className="msgbox-text">{b.text}</div>
        </div>
        <div className="msgbox-buttons">
          {b.buttons.map((x, i) => <button key={x} ref={i === 0 ? first : undefined} className={`qbtn${i === 0 ? ' default' : ''}`} onClick={() => done(x)}>{x}</button>)}
        </div>
      </div>
    </div>,
    document.body,
  )
}
