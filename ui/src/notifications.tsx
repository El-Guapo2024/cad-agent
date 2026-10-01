// Gui::NotificationArea (src/Gui/NotificationArea.cpp/.h): the status bar's notification button,
// its dropdown list of warnings/errors/critical messages, the non-intrusive pop-up balloon
// (NotificationBox.cpp), and the setter behind Preferences > Notification Area (the page itself
// is built in panels.tsx's PrefsTask, from store.ts's NotifyPrefs). report() (store.ts) has no
// per-message module tag (unlike Base::Console), so every item is notified under one NOTIFIER,
// the way FreeCAD itself falls back to "FreeCAD" for untagged messages.
// Not ported: NotificationArea::confirmationRequired/showConfirmationDialog, a modal "skip
// confirmation?" prompt for Critical messages while a document loads — there's no document
// restore step here distinct from any other critical message.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ContextMenu, type Entry } from './chrome'
import { Icon, type IconName } from './icons'
import { cls } from './panels'
import { getState, onNotify, saved, setState, useStore, type Level, type Notification, type NotifyPrefs } from './store'

const NOTIFIER = 'CAD Agent'
const levelIcon = (level: Notification['level']): IconName => (level === 'err' ? 'notify-error' : level === 'warn' ? 'notify-warn' : 'notify-critical')
// NotificationItem::getMessage: "(%1 times)" once it has repeated.
const msgText = (n: Notification) => (n.repetitions > 0 ? `${n.text} (${n.repetitions + 1} times)` : n.text)

let nextId = 1
let inhibitTimer: ReturnType<typeof setTimeout> | undefined
const expiryTimers = new Map<number, ReturnType<typeof setTimeout>>() // per-item QTimer::singleShot(notificationExpirationTime)

/** DlgSettingsNotificationArea::saveSettings, applied live (this port has no restart to wait for). */
export function setNotifyPrefs(patch: Partial<NotifyPrefs>) {
  setState((s) => { const notifyPrefs = { ...s.notifyPrefs, ...patch }; saved.set('notifyPrefs', notifyPrefs); return { notifyPrefs } })
}

/** NotificationAreaObserver::sendLog, hooked into report() (store.ts): Message and Log never
 *  reach the notification area, only Warning/Error/Critical. developerErrors/developerWarnings
 *  (DeveloperWarning/ErrorSubscriptionEnabled upstream) are kept in NotifyPrefs for the
 *  Preferences page only: report() never tags a message as developer-only (no IntendedRecipient
 *  here), so there is nothing for them to admit or filter. */
function pushNotification(level: Level, text: string) {
  if (level !== 'warn' && level !== 'err' && level !== 'critical') return
  const prefs = getState().notifyPrefs
  if (!prefs.areaEnabled) return // NotificationAreaEnabled=false: no observer attached
  const msg = text.trim()
  if (!msg) return
  const list = getState().notifications
  const top = list[0]
  let next: Notification[]
  if (top && top.level === level && top.notifier === NOTIFIER && top.text === msg) {
    // NotificationItem::isRepeated + addRepetition: same as the last item, bump it instead.
    next = [{ ...top, unread: true, notifying: true, shown: false, repetitions: top.repetitions + 1 }, ...list.slice(1)]
  } else {
    next = [{ id: nextId++, t: Date.now(), level, notifier: NOTIFIER, text: msg, unread: true, notifying: true, shown: false, repetitions: 0 }, ...list]
    // MaxWidgetMessages, 0 = no limit.
    if (prefs.maxWidgetMessages && next.length > prefs.maxWidgetMessages) next = next.slice(0, prefs.maxWidgetMessages)
  }
  if (!prefs.popupEnabled) next[0] = { ...next[0], notifying: false } // widget only, no balloon
  setState({ notifications: next })
  if (!prefs.popupEnabled) return
  clearTimeout(inhibitTimer)
  inhibitTimer = setTimeout(showBalloon, 250) // inhibitNotificationTime: let a burst of messages settle
}
onNotify(pushNotification)

/** NotificationArea::showInNotificationArea: (re)builds the set of items on screen now. */
function showBalloon() {
  const prefs = getState().notifyPrefs
  const list = getState().notifications
  if (list.filter((n) => n.shown).length >= prefs.maxOpenNotifications) return // no room for more right now
  if (prefs.preventWhenInactive && !document.hasFocus()) { setState({ notifyMissed: true }); return }
  const notifying = list.filter((n) => n.notifying)
  const ids = new Set(notifying.slice(0, prefs.maxOpenNotifications).map((n) => n.id))
  setState({
    notifyOverflow: notifying.length > prefs.maxOpenNotifications,
    notifications: list.map((n) => (!n.notifying ? n : ids.has(n.id) ? { ...n, shown: true } : { ...n, notifying: false })),
  })
  for (const n of notifying) {
    if (!ids.has(n.id) || n.shown || expiryTimers.has(n.id)) continue
    const repetitions = n.repetitions
    expiryTimers.set(n.id, setTimeout(() => {
      expiryTimers.delete(n.id)
      // AutoRemoveUserNotifications only ever matched Base::LogStyle::Notification upstream, a
      // style report() never issues (warn/err/critical only), so it stays a no-op here too.
      setState((s) => ({ notifications: s.notifications.map((x) => (x.id === n.id && x.repetitions === repetitions ? { ...x, notifying: false, shown: false } : x)) }))
    }, prefs.maxDuration * 1000))
  }
}

/** Pops the balloon out early: a click inside it (always), or anywhere once MinimumOnScreenTime
 *  has elapsed (NotificationBox's doc comment: "shown during minShowTime, unless popped out"). */
function dismissBalloon() {
  getState().notifications.forEach((n) => { const t = expiryTimers.get(n.id); if (t !== undefined) { clearTimeout(t); expiryTimers.delete(n.id) } })
  setState((s) => ({ notifications: s.notifications.map((n) => (n.shown ? { ...n, shown: false, notifying: false } : n)) }))
}

/** NotificationBox::showText: one combined bubble table for every currently-shown item, anchored
 *  above the status bar button (RestrictAreaToReference; clamped to the viewport here, not a
 *  separate main-window rect). */
function NotifyBalloon({ anchor }: { anchor: HTMLElement | null }) {
  const list = useStore((s) => s.notifications)
  const overflow = useStore((s) => s.notifyOverflow)
  const width = useStore((s) => s.notifyPrefs.notificationWidth)
  const minDuration = useStore((s) => s.notifyPrefs.minDuration)
  const items = list.filter((n) => n.shown)
  const visible = items.length > 0
  const [pos, setPos] = useState<{ left: number; bottom: number; width: number } | null>(null)
  useEffect(() => {
    if (!anchor) return
    const place = () => {
      const r = anchor.getBoundingClientRect(), w = Math.min(width, innerWidth - 16)
      setPos({ left: Math.max(8, Math.min(r.left, innerWidth - w - 8)), bottom: innerHeight - r.top + 6, width: w })
    }
    place()
    addEventListener('resize', place)
    return () => removeEventListener('resize', place)
  }, [anchor, width])
  // A click anywhere closes it, but only once MinimumOnScreenTime has passed (the balloon's own
  // onClick below handles "clicked inside", unconditionally, the instant that fires first).
  useEffect(() => {
    if (!visible) return
    const shownAt = Date.now()
    const away = () => { if (Date.now() - shownAt >= minDuration * 1000) dismissBalloon() }
    addEventListener('pointerdown', away, true)
    return () => removeEventListener('pointerdown', away, true)
  }, [visible, minDuration])
  if (!visible || !pos) return null
  return createPortal(
    <div className="notify-balloon" style={{ left: pos.left, bottom: pos.bottom, width: pos.width }} onClick={dismissBalloon}>
      <table>
        <thead><tr><th>Type</th><th>Notifier</th><th>Message</th></tr></thead>
        <tbody>
          {overflow && <tr className="notify-balloon-overflow"><td><Icon name="notify-warn" size={16} /></td><td>{NOTIFIER}</td>
            <td>Too many opened non-intrusive notifications. Notifications are being omitted!</td></tr>}
          {items.map((n) => <tr key={n.id}><td><Icon name={levelIcon(n.level)} size={16} /></td><td>{n.notifier}</td><td>{msgText(n)}</td></tr>)}
        </tbody>
      </table>
    </div>, document.body)
}

/** NotificationsAction::createWidget: the QTreeWidget dropdown (Type/Notifier/Message columns),
 *  newest first, unread rows bold, with its own Delete/Delete User Notifications/Delete All menu. */
function NotifyList({ anchor, onClose }: { anchor: DOMRect; onClose(): void }) {
  const list = useStore((s) => s.notifications)
  const [sel, setSel] = useState<Set<number>>(new Set())
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  useEffect(() => {
    const away = (e: Event) => { if (!(e.target as HTMLElement).closest?.('.notify-list, .ctx')) onClose() }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    addEventListener('pointerdown', away, true)
    addEventListener('keydown', key, true)
    return () => { removeEventListener('pointerdown', away, true); removeEventListener('keydown', key, true) }
  }, [onClose])
  const del = (ids: Set<number>) => setState((s) => ({ notifications: s.notifications.filter((n) => !ids.has(n.id)) }))
  const entries = (): Entry[] => [
    { label: 'Delete', bold: true, disabled: !sel.size, onSelect: () => { del(sel); setSel(new Set()) } },
    'sep',
    // Only ever deletes Base::LogStyle::Notification items, a style report() never issues; kept
    // (and enabled whenever the list isn't empty) for menu parity with NotificationsAction.
    { label: 'Delete User Notifications', disabled: !list.length, onSelect: () => {} },
    { label: 'Delete All', disabled: !list.length, onSelect: () => { setState({ notifications: [] }); onClose() } },
  ]
  const w = 420, h = Math.min(360, list.length * 23 + 26)
  const left = Math.max(4, Math.min(anchor.right - w, innerWidth - w - 4)), top = Math.max(4, Math.min(anchor.bottom + 2, innerHeight - h - 4))
  return createPortal(
    <div className="notify-list" style={{ left, top, width: w, maxHeight: h }}
      onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}>
      <div className="notify-head"><span /><span>Notifier</span><span>Message</span></div>
      <div className="notify-body">
        {!list.length && <div className="notify-empty">No notifications</div>}
        {list.map((n) => (
          <div key={n.id} className={cls('notify-row', n.unread && 'unread', sel.has(n.id) && 'sel')}
            onClick={(e) => setSel((s) => { const keep = e.metaKey || e.ctrlKey; const next = new Set(keep ? s : []); if (next.has(n.id)) next.delete(n.id); else next.add(n.id); return next })}
            onContextMenu={() => setSel((s) => (s.has(n.id) ? s : new Set([n.id])))}>
            <Icon name={levelIcon(n.level)} size={16} /><span className="notify-notifier">{n.notifier}</span><span className="notify-text">{msgText(n)}</span>
          </div>
        ))}
      </div>
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={entries()} />}
    </div>, document.body)
}

/** The status bar push-button itself (order 800, between Bottom Panel Toggle and Navigation
 *  Styles): badge = unread count (0 while the list is open, mirroring aboutToShow/aboutToHide),
 *  left click opens the list, right click is NotificationArea::mousePressEvent's own small menu. */
export function NotificationArea() {
  const list = useStore((s) => s.notifications)
  const missed = useStore((s) => s.notifyMissed)
  const [open, setOpen] = useState(false)
  const [menuAt, setMenuAt] = useState<{ x: number; y: number } | null>(null)
  const ref = useRef<HTMLButtonElement>(null)
  const unread = open ? 0 : list.filter((n) => n.unread).length
  const close = () => { setOpen(false); setState((s) => ({ notifications: s.notifications.map((n) => (n.unread ? { ...n, unread: false } : n)) })) }
  const openList = () => { setOpen(true); setState({ notifyMissed: false }) }
  // HideNonIntrusiveNotificationsWhenWindowDeactivated: another window activated closes the balloon.
  useEffect(() => {
    const onBlur = () => { if (getState().notifyPrefs.hideWhenDeactivated) dismissBalloon() }
    addEventListener('blur', onBlur)
    return () => removeEventListener('blur', onBlur)
  }, [])
  return (
    <>
      <button ref={ref} className="sb-ind notify-btn" title="Notifications" onClick={() => (open ? close() : openList())}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); setMenuAt({ x: e.clientX, y: e.clientY }) }}>
        <Icon name={missed ? 'notify-tray-missed' : 'notify-tray'} size={16} />
        {/* NotificationArea: the button's text is the unread count, "0" included. */}
        <span className="notify-count">{unread}</span><span className="sb-menu-ind" />
      </button>
      {open && ref.current && <NotifyList anchor={ref.current.getBoundingClientRect()} onClose={close} />}
      {menuAt && <ContextMenu at={menuAt} onClose={() => setMenuAt(null)} entries={[
        { label: 'Delete User Notifications', disabled: !list.length, onSelect: () => {} },
        { label: 'Delete All', bold: true, disabled: !list.length, onSelect: () => setState({ notifications: [] }) },
      ]} />}
      <NotifyBalloon anchor={ref.current} />
    </>
  )
}
