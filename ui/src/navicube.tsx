// The NaviCube's buttons and menu around the cube (Gui/NaviCube.cpp at FreeCAD main
// 3160daf1e2b6, LGPL-2.1-or-later). The cube itself is drawn and picked in viewer.ts.
import { useState } from 'react'
import { getState, useStore } from './store'
import { getView, setOrtho } from './actions'
import { alignToSelection, navi, viewHome } from './commands'
import { ContextMenu } from './chrome'

/** The NaviCube's buttons around the cube (NaviCube.cpp): four 45° arrows, two
 *  rolls, the backside flip, home, and its menu. */
export function NaviButtons() {
  const cube = useStore((s) => s.cube), size = useStore((s) => s.naviCube.size), place = useStore((s) => s.cubePlace)
  const off = useStore((s) => s.cubeOffset)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  if (!cube) return null
  // The buttons sit around the cube, wherever it is: a box the cube's size plus its 10 px
  // offset on each side (and room below for the menu button), at viewer.ts's cubeLayout offset
  // for the cube's current (continuous) position — not just its nearest placement's corner.
  const w = size + 20, h = size + 32, [vert, horiz] = place.split('-')
  const box: React.CSSProperties = { width: w, height: h,
    ...(vert === 'top' ? { top: Math.max(0, off.top - 10) } : vert === 'bottom' ? { bottom: Math.max(0, off.bottom - 10) } : { top: `calc(50% - ${h / 2}px + ${off.top}px)` }),
    ...(horiz === 'left' ? { left: Math.max(0, off.left - 10) } : horiz === 'right' ? { right: Math.max(0, off.right - 10) } : { left: `calc(50% - ${w / 2}px + ${off.left}px)` }) }
  const at: Record<string, React.CSSProperties> = {
    n: { top: 0, left: (w - 16) / 2 }, s: { top: h - 21, left: (w - 16) / 2 }, w: { top: (w - 16) / 2, left: 0 }, e: { top: (w - 16) / 2, left: w - 16 },
    rl: { top: 4, left: 6 }, rr: { top: 4, left: w - 20 }, home: { top: h - 38, left: 6 }, back: { top: h - 38, left: w - 20 }, menu: { top: h - 18, left: w - 20 },
  }
  const b = (cls: string, title: string, text: string, f: () => void) => <button className={'navi ' + cls} style={at[cls]} title={title} onClick={f}>{text}</button>
  return (
    <div className="navi-box" style={box}>
      {b('n', 'Rotate the view up', '▲', navi.north)}{b('s', 'Rotate the view down', '▼', navi.south)}
      {b('w', 'Rotate the view left', '◀', navi.west)}{b('e', 'Rotate the view right', '▶', navi.east)}
      {b('rl', 'Roll left', '↺', navi.rollLeft)}{b('rr', 'Roll right', '↻', navi.rollRight)}
      {b('home', 'Home view', '⌂', viewHome)}{b('back', 'Look from the other side', '⇄', navi.backside)}
      <button className="navi menu" style={at.menu} title="View menu" onClick={(e) => setMenu({ x: e.clientX - 180, y: e.clientY + 8 })}>☰</button>
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
