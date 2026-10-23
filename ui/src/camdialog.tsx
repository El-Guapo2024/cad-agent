// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/PreferencePages/DlgSettingsNavigation.cpp: 2004 Werner Mayer
// The Custom default camera orientation: DlgSettingsNavigation's CameraDialog ("Camera Settings", DlgSettingsNavigation.cpp:394-495),
// which the Navigation page opens when Custom is picked in Default camera orientation (onNewDocViewChanged, :380-390), and the page's
// own Q0..Q3 (q0 .. q3, 0 0 0 1 until loadSettings finds the parameter is Custom: addOrientations, :244-250).
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { QtForm, type Bindings } from './qtform'
import { getView } from './actions'
import type { UiForm, UiItem } from './uiforms'
import { getState } from './store'

export type Quat = [number, number, number, number]

// ── the page's q0 .. q3 ──────────────────────────────────────────────────────────────────────────────────────────
let pageQ: Quat = [0, 0, 0, 1]
/** DlgSettingsNavigation::addOrientations, as the Preferences dialog opens: the page holds View/Custom's Q0..Q3 when the orientation
 *  is Custom, else its constructor's 0, 0, 0, 1 (so a Custom picked later starts from those, whatever View/Custom still holds). */
export function loadCameraPage() {
  const s = getState()
  pageQ = s.homeView === 'Custom' && s.customCamera ? [...s.customCamera] : [0, 0, 0, 1]
}

// ── the dialog ───────────────────────────────────────────────────────────────────────────────────────────────────
type Open = { q: Quat; resolve(q: Quat): void }
let open: Open | null = null
const subs = new Set<() => void>()
const set = (o: Open | null) => { open = o; subs.forEach((f) => f()) }

/** onNewDocViewChanged's Custom: CameraDialog with the page's values; OK keeps what it shows (Cancel keeps the page's), and the page's
 *  values are what the orientation then uses. */
export function pickCustomCamera(): Promise<Quat> {
  return new Promise((resolve) => set({ q: [...pageQ], resolve: (q) => { pageQ = q; resolve(q) } }))
}

/** The Orientation group: a QGridLayout of four QLabel / QDoubleSpinBox rows (range -1 to 1, step 0.1, QDoubleSpinBox's 2 decimals)
 *  and Current View in column 1 across rows 4 and 5 (DlgSettingsNavigation.cpp:413-459). */
const ROWS: UiItem[] = [0, 1, 2, 3].flatMap((i) => [
  { r: i, c: 0, w: { c: 'QLabel', n: `label${i}`, p: { text: `Q${i}` }, fc: { h: [17, 16], pol: 'PP' } } },
  { r: i, c: 1, w: { c: 'QDoubleSpinBox', n: `sb${i}`, p: { minimum: -1, maximum: 1, singleStep: 0.1 }, fc: { h: [60, 23], pol: 'mF' } } },
] as UiItem[])
const FORM: UiForm = { title: 'Camera Settings', root: { c: 'QWidget', n: 'CameraDialog', l: { t: 'V', i: [
  { w: { c: 'QGroupBox', n: 'groupBox', p: { title: 'Orientation' }, fc: { h: [0, 0], pol: 'PP' }, l: { t: 'G', i: [
    ...ROWS,
    { r: 4, c: 1, rs: 2, w: { c: 'QPushButton', n: 'currentView', p: { text: 'Current View' }, fc: { h: [99, 24], pol: 'mF' } } },
  ] } } },
] } } }

export function CameraDialogHost() {
  const o = useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => open)
  return o ? <CameraDialog o={o} /> : null
}

function CameraDialog({ o }: { o: Open }) {
  const [q, setQ] = useState<Quat>(() => [...o.q])
  const okBtn = useRef<HTMLButtonElement>(null)
  useEffect(() => { okBtn.current?.focus() }, [])
  const done = (accept: boolean) => { set(null); o.resolve(accept ? q : o.q) }
  const bind: Bindings = { groupBox: {}, label0: {}, label1: {}, label2: {}, label3: {} }
  for (let i = 0; i < 4; i++) bind[`sb${i}`] = { value: q[i], set: (v: number) => setQ((x) => x.map((y, j) => (j === i ? v : y)) as Quat) }
  // onCurrentViewClicked: the active 3D view's camera orientation, as SbRotation::getValue gives it (float32), into the boxes, which
  // round it to their 2 decimals.
  bind.currentView = { click: () => {
    const c = getView()?.cameraOrientation()
    if (c) setQ(c.map((v) => Math.round(Math.fround(v) * 100) / 100) as Quat)
  } }
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => {
      e.stopPropagation()
      if (e.key === 'Escape') { e.preventDefault(); done(false) }
      else if (e.key === 'Enter' && !(e.target instanceof HTMLButtonElement)) { e.preventDefault(); done(true) }
    }}>
      <div className="msgbox camdlg" role="dialog" aria-label="Camera Settings">
        <div className="msgbox-title">Camera Settings</div>
        <div className="camdlg-body"><QtForm form={FORM} bind={bind} /></div>
        {/* QDialogButtonBox Cancel | Ok, in the Mac's order (MacLayout: the accept button last) */}
        <div className="msgbox-buttons camdlg-buttons">
          <button className="qbtn" onClick={() => done(false)}>Cancel</button>
          <button ref={okBtn} className="qbtn default" onClick={() => done(true)}>OK</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
