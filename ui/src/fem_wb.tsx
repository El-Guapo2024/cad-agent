// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Fem/Gui/Workbench.cpp: 2008 Werner Mayer, 2023 Peter McB
//   src/Mod/Fem/Gui/Command.cpp: 2008 Jürgen Riegel, 2022 Peter McB; src/Mod/Fem/femcommands/commands.py: 2016 Bernd Hahnebach
// The FEM workbench: its Model, Mesh, Solve, Results and Utilities menus and its toolbars, every command by FreeCAD's
// name, menu text, tooltip and icon (fem_cmds.ts). A part's analysis is its part file's FEM list (cad_agent/
// feature_fem.py); Run Solver meshes it with Gmsh and solves it with CalculiX on the server (`cad fem run`) and the
// Report view gets the results. The commands that add objects to an analysis have no panels here yet: they are greyed
// with the reason, and the part file's FEM list is edited instead.
import { consoleLog, getState, report } from './store'
import { api, resultText } from './api'
import type { Entry } from './chrome'
import type { IconName } from './icons'
import { FEM_CMDS, FEM_MENUS, FEM_TOOLBARS, type FemItem } from './fem_cmds'

const cmdOf = (c: string) => FEM_CMDS[c] ?? { menu: c, tip: null, pixmap: null, accel: null }
const iconOf = (c: string) => (cmdOf(c).pixmap ? `fem-${cmdOf(c).pixmap}` : undefined) as IconName | undefined
const NOT_YET = 'n/a: not ported yet: write the analysis in the part file\'s FEM list (cad_agent/feature_fem.py: Fem.MaterialSolid, Fem.ConstraintFixed, Fem.ConstraintForce, Fem.ConstraintPressure, Fem.MeshGmsh, Fem.SolverCalculiX), then Run Solver'

/** The part Run Solver works on: the part of what is selected (a tree row or the 3D view's body), else the only one. */
function activePart(): string | null {
  const s = getState()
  const fromSel = s.featSel[0]?.split('/')[0]
  if (fromSel) return fromSel
  const fromScene = s.selected.map((n) => s.scene?.bodies.find((b) => b.name === n)?.part).find((p): p is string => !!p)
  if (fromScene) return fromScene
  const parts = Object.keys(s.features)
  return parts.length === 1 ? parts[0] : null
}

/** FEM_SolverRun: `cad fem run` on the part, the results in the Report view. */
async function runSolver() {
  const s = getState(), part = activePart()
  if (!s.slug || !part) { report('warn', 'Run Solver: select the part whose FEM analysis to run'); return }
  const argv = ['fem', 'run', s.slug, part]
  if (s.scriptToPyConsole) consoleLog('in', `cad ${argv.join(' ')}`)
  report('msg', `${part}: meshing with Gmsh and solving with CalculiX ...`)
  try {
    const r = await api.cad(s.slug, argv)
    if (r.exit !== 0) { report('err', `Run Solver: ${resultText(r)}`); return }
    const d = r.data ?? {}
    report('msg', `${part}: ${d.nodes} nodes, ${d.volumes} volume elements; max displacement ${Number(d.max_displacement_mm).toPrecision(6)} mm, `
      + `max von Mises stress ${Number(d.max_von_mises_mpa).toPrecision(6)} MPa (${d.workdir})`)
  } catch (e) { report('err', `Run Solver: ${e instanceof Error ? e.message : String(e)}`) }
}

function entry(it: FemItem): Entry {
  if (it === 'Separator') return 'sep'
  if (typeof it !== 'string') return { label: it.menu.replace(/&/g, ''), sub: it.items.map(entry) }
  const r = cmdOf(it), label = r.menu ?? it
  if (r.group) return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, sub: r.group.map(entry) }
  if (it === 'FEM_SolverRun') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => void runSolver() }
  return { label, icon: iconOf(it), cmd: it, disabled: true, title: NOT_YET }
}
export const femMenus = (): [string, Entry[]][] => FEM_MENUS.map((m) => [m.title.replace(/&/g, ''), m.items.map(entry)])
export const femToolbars = (): [string, Entry[]][] => FEM_TOOLBARS.map((t) => [t.title, t.items.map(entry)])
export const FEM_TOOLBAR_NAMES = FEM_TOOLBARS.map((t) => t.title)
/** Every FEM command the port runs (cmdreg.ts). */
export function femCommands(): [string, Exclude<Entry, 'sep'>][] {
  const out: [string, Exclude<Entry, 'sep'>][] = []
  const walk = (es: Entry[]) => { for (const e of es) { if (e === 'sep') continue; if (e.cmd && e.onSelect && !out.some(([c]) => c === e.cmd)) out.push([e.cmd, e]); if (e.sub) walk(e.sub) } }
  for (const [, es] of femMenus()) walk(es)
  return out
}
export const femRun = (cmd: string) => femCommands().find(([c]) => c === cmd)?.[1].onSelect?.()
export const femEnabled = (cmd: string) => { const e = femCommands().find(([c]) => c === cmd)?.[1]; return !!e && !e.disabled }
/** The menus and toolbars as plain data, for femcheck (cadui.fem()). */
export function femData() {
  const plain = (es: Entry[]): unknown[] => es.map((e) => (e === 'sep' ? { sep: true } : { text: e.label, cmd: e.cmd ?? null, enabled: !e.disabled, ...(e.sub ? { menu: plain(e.sub) } : {}) }))
  return { menus: femMenus().map(([t, es]) => ({ title: t, entries: plain(es) })), toolbars: femToolbars().map(([t, es]) => ({ title: t, buttons: plain(es) })) }
}
