// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/NaviCube.cpp: 2017 Kustaa Nyholm; 2026 Joao Matos
//   src/Gui/Inventor/SoNaviCube.cpp: 2025-2026 Joao Matos
// The NaviCube's buttons and menu (Gui/NaviCube.cpp at FreeCAD main 3160daf1e2b6, LGPL-2.1-or-later). The cube and the
// buttons' shapes are drawn in viewer.ts (navicube3d.ts); here each button is an element exactly over its drawn shape, which
// takes its clicks.
import { useState } from 'react'
import { getState, useStore } from './store'
import { getView, setOrtho } from './actions'
import { alignToSelection, navi, viewHome } from './commands'
import { ContextMenu } from './chrome'
import { BUTTON_SHAPES, NAVI_BUTTONS, type NaviButton } from './navicube3d'

/** What each button does (NaviCube.cpp mouseReleased): four arrows that turn the view by 360° / NaviStepByTurn, two rolls,
 *  the backside flip, home, and the menu. FreeCAD's buttons carry no tooltip; the labels are for assistive technology only. */
const ACTION: Record<Exclude<NaviButton, 'menu'>, [string, () => void]> = {
  n: ['Rotate the view up', navi.north], s: ['Rotate the view down', navi.south], w: ['Rotate the view left', navi.west], e: ['Rotate the view right', navi.east],
  rl: ['Roll left', navi.rollLeft], rr: ['Roll right', navi.rollRight], home: ['Home view', viewHome], back: ['Look from the other side', navi.backside],
}

/** Where a button's element goes in the cube's square (px), and the outline that clips it: pickAt (SoNaviCube.cpp:1400-1406)
 *  takes the hit rectangle of the two buttons that have one (the menu and the backside, whose loops leave gaps), and for the
 *  others what a ray meets, the drawn shape itself. */
function buttonBox(id: NaviButton, size: number): React.CSSProperties {
  const s = BUTTON_SHAPES[id]
  const pts = s.loops.flat()
  const r = s.hit ?? { left: Math.min(...pts.map((p) => p[0])), top: Math.min(...pts.map((p) => p[1])), right: Math.max(...pts.map((p) => p[0])), bottom: Math.max(...pts.map((p) => p[1])) }
  const box: React.CSSProperties = { left: r.left * size, top: r.top * size, width: (r.right - r.left) * size, height: (r.bottom - r.top) * size }
  if (!s.hit) {
    const w = r.right - r.left, h = r.bottom - r.top
    box.clipPath = `polygon(${s.loops[0].map(([x, y]) => `${(((x - r.left) / w) * 100).toFixed(2)}% ${(((y - r.top) / h) * 100).toFixed(2)}%`).join(', ')})`
  }
  return box
}

export function NaviButtons() {
  const cube = useStore((s) => s.cube), size = useStore((s) => s.naviCube.size)
  const off = useStore((s) => s.cubeOffset)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  if (!cube) return null
  // The buttons lie over the cube's square, wherever viewer.ts has put it (cubeLayout).
  const box: React.CSSProperties = { left: off.left, top: off.top, width: size, height: size }
  return (
    <div className="navi-box" style={box}>
      {NAVI_BUTTONS.map((id) => id === 'menu'
        // handleMenu: menu->exec(QCursor::pos()), the menu at the pointer
        ? <button key={id} className="navi menu" style={buttonBox(id, size)} aria-label="View menu" onClick={(e) => setMenu({ x: e.clientX, y: e.clientY })} />
        : <button key={id} className={'navi ' + id} style={buttonBox(id, size)} aria-label={ACTION[id][0]} onClick={ACTION[id][1]} />)}
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={[
        { label: 'Orthographic View', checked: getState().ortho, onSelect: () => setOrtho(true) },
        { label: 'Perspective View', checked: !getState().ortho, onSelect: () => setOrtho(false) },
        { label: 'Isometric', icon: 'iso', onSelect: () => getView()?.viewDir('iso') },
        'sep',
        { label: 'Fit All', icon: 'fit-all', onSelect: () => getView()?.fitAll() },
        { label: 'Fit Selection', icon: 'fit-sel', disabled: !getState().selected.length, onSelect: () => getView()?.fitAll(getState().selected) },
        { label: 'Align to Selection', icon: 'align', disabled: !getState().subSel.some((r) => /\.Face\d+$/.test(r)), onSelect: alignToSelection },
        'sep',
        { label: 'Movable Navigation Cube', checked: getView()?.isCubeDraggable() ?? false, onSelect: () => { const v = getView(); if (v) v.setCubeDraggable(!v.isCubeDraggable()) } },
      ]} />}
    </div>
  )
}
