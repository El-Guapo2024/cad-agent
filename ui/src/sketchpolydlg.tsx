// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/SketcherRegularPolygonDialog.cpp: 2017 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SketcherRegularPolygonDialog.ui: 2017 Abdullah Tahiri
// Sketcher_CreateRegularPolygon's dialog (SketcherRegularPolygonDialog, an application-modal QDialog): the number of
// sides, a Gui::PrefSpinBox (3 to 99, 9 by default) kept in Mod/Sketcher/DefaultRegularPolygonSides when OK saves it.
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { sketcherParam, setSketcherParams } from './sketchovp'
import { QuantityBox } from './qsb'

const PREF = 'Mod/Sketcher/DefaultRegularPolygonSides'
const COUNT: [number, number, number, number, number, number, number, number] = [0, 0, 0, 0, 0, 0, 0, 0]
let pending: ((sides: number | null) => void) | null = null
const subs = new Set<() => void>()
const changed = () => subs.forEach((f) => f())

/** srpd.exec(): the sides asked for, or null when the dialog is cancelled. */
export function askPolygonSides(): Promise<number | null> {
  pending?.(null)
  return new Promise((resolve) => { pending = resolve; changed() })
}

export function RegularPolygonDialog() {
  const open = useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f) } }, () => !!pending)
  const [sides, setSides] = useState(9)
  const okRef = useRef<HTMLButtonElement>(null)
  // onRestore: the box shows the value last saved
  useEffect(() => { if (open) setSides(Math.min(99, Math.max(3, Math.round(sketcherParam<number>(PREF, 9))))) }, [open])
  if (!open) return null
  const done = (v: number | null) => { const f = pending; pending = null; changed(); f?.(v) }
  const accept = () => { setSketcherParams({ [PREF]: sides }); done(sides) } // onSave, then updateValues
  return createPortal(
    <div className="msgbox-back" onKeyDown={(e) => {
      e.stopPropagation()
      if (e.key === 'Escape') { e.preventDefault(); done(null) }
      if (e.key === 'Enter') { e.preventDefault(); accept() }
    }}>
      <div className="msgbox datum-dlg" role="dialog" aria-label="Create Regular Polygon">
        <div className="msgbox-title">Create Regular Polygon</div>
        <div className="datum-body">
          <div className="hbox fill"><span>Number of sides</span>
            <QuantityBox value={sides} dims={COUNT} min={3} max={99} decimals={0} autoFocus title="Number of columns of the linear array"
              onChange={(v) => setSides(Math.round(v))} onFinish={() => okRef.current?.focus()} /></div>
        </div>
        <div className="msgbox-buttons">
          <button ref={okRef} className="qbtn default" onClick={accept}>OK</button>
          <button className="qbtn" onClick={() => done(null)}>Cancel</button>
        </div>
      </div>
    </div>, document.body)
}
