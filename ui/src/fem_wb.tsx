// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Fem/Gui/Workbench.cpp: 2008 Werner Mayer, 2023 Peter McB
//   src/Mod/Fem/Gui/Command.cpp: 2008 Jürgen Riegel, 2022 Peter McB; src/Mod/Fem/femcommands/commands.py: 2016 Bernd Hahnebach
// The FEM workbench: its Model, Mesh, Solve, Results and Utilities menus and its toolbars, every command by FreeCAD's
// name, menu text, tooltip and icon (fem_cmds.ts). A part's analysis is its part file's FEM list (cad_agent/
// feature_fem.py); Run Solver meshes it with Gmsh and solves it with CalculiX, Elmer, Mystran or Z88 on the server (`cad fem run`) and
// the Report view gets the results. Analysis, the material, the fixed, force and pressure boundary conditions, the Gmsh mesh,
// the solver and Show Result have their panels (fem_tasks.tsx); the rest are greyed with the reason.
import { consoleLog, getState, report } from './store'
import { openTask } from './actions'
import { addDirect, addEquation, addSolver } from './fem_tasks'
import { api, resultText } from './api'
import type { Entry } from './chrome'
import type { IconName } from './icons'
import { FEM_CMDS, FEM_MENUS, FEM_TOOLBARS, type FemItem } from './fem_cmds'

const cmdOf = (c: string) => FEM_CMDS[c] ?? { menu: c, tip: null, pixmap: null, accel: null }
const iconOf = (c: string) => (cmdOf(c).pixmap ? `fem-${cmdOf(c).pixmap}` : undefined) as IconName | undefined
const NOT_YET = 'n/a: not ported yet: only the solid material, the fixed, force, pressure, displacement, gravity, temperature, initial temperature and heat flux conditions, the Gmsh mesh, CalculiX (static, frequency, thermomech), Elmer (its elasticity and heat equations) Mystran (static, fixed and force) and Z88 (static: fixed, displacement, force and pressure) are'

/** The part the FEM commands work on: the open panel's, else the part of what is selected (a tree row or the 3D view's body), else the only one. */
export function activePart(): string | null {
  const s = getState()
  if (s.task?.kind === 'fem') return s.task.body       // the analysis being worked on: an edit's reload clears the selection
  const fromSel = s.featSel[0]?.split('/')[0]
  if (fromSel) return fromSel
  const fromScene = s.selected.map((n) => s.scene?.bodies.find((b) => b.name === n)?.part).find((p): p is string => !!p)
  if (fromScene) return fromScene
  const parts = Object.keys(s.features)
  return parts.length === 1 ? parts[0] : null
}

/** FEM_SolverRun: `cad fem run` on the part, the results in the Report view. */
export async function runSolver() {
  const s = getState(), part = activePart()
  if (!s.slug || !part) { report('warn', 'Run Solver: select the part whose FEM analysis to run'); return }
  const argv = ['fem', 'run', s.slug, part]
  if (s.scriptToPyConsole) consoleLog('in', `cad ${argv.join(' ')}`)
  report('msg', `${part}: meshing with Gmsh and solving ...`)
  try {
    const r = await api.cad(s.slug, argv)
    if (r.exit !== 0) { report('err', `Run Solver: ${resultText(r)}`); return }
    const d = r.data ?? {}
    report('msg', `${part}: ${d.nodes} nodes, ${d.volumes} volume elements; max displacement ${Number(d.max_displacement_mm).toPrecision(6)} mm, `
      + (d.max_von_mises_mpa != null ? `max von Mises stress ${Number(d.max_von_mises_mpa).toPrecision(6)} MPa`
        : `max nodal force ${Number(d.max_nodal_force_n).toPrecision(6)} N (Z88 gives no stresses to FreeCAD's result)`)
      + (Array.isArray(d.frequencies_hz) ? `; frequencies ${(d.frequencies_hz as number[]).map((f) => f.toPrecision(6)).join(', ')} Hz` : '')
      + (Array.isArray(d.buckling_factors) ? `; buckling factors ${(d.buckling_factors as number[]).map((f) => f.toPrecision(6)).join(', ')}` : '')
      + (d.max_temperature_k !== undefined ? `; temperature ${Number(d.min_temperature_k).toPrecision(6)} to ${Number(d.max_temperature_k).toPrecision(6)} K` : '') + ` (${d.workdir})`)
  } catch (e) { report('err', `Run Solver: ${e instanceof Error ? e.message : String(e)}`) }
}

const PANELS: Record<string, string> = { FEM_Analysis: 'analysis', FEM_MaterialSolid: 'add:MaterialSolid', FEM_ConstraintFixed: 'add:ConstraintFixed', FEM_ConstraintForce: 'add:ConstraintForce',
  FEM_ConstraintPressure: 'add:ConstraintPressure', FEM_MeshGmshFromShape: 'add:MeshGmsh', FEM_ResultShow: 'result',
  FEM_ConstraintDisplacement: 'add:ConstraintDisplacement', FEM_ConstraintTemperature: 'add:ConstraintTemperature',
  FEM_ConstraintInitialTemperature: 'add:ConstraintInitialTemperature', FEM_ConstraintHeatflux: 'add:ConstraintHeatflux' }
function inPart(cmd: string, go: (part: string) => void) {
  const part = activePart()
  if (part) go(part); else report('warn', `${cmdOf(cmd).menu ?? cmd}: select the part the analysis belongs to`)
}

function entry(it: FemItem): Entry {
  if (it === 'Separator') return 'sep'
  if (typeof it !== 'string') return { label: it.menu.replace(/&/g, ''), sub: it.items.map(entry) }
  const r = cmdOf(it), label = r.menu ?? it
  if (r.group) return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, sub: r.group.map(entry) }
  if (it === 'FEM_SolverRun') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => void runSolver() }
  const task = PANELS[it]
  if (task) return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => openTask('fem', p, task)) }
  if (it === 'FEM_ConstraintSelfWeight') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => void addDirect(p, 'ConstraintSelfWeight')) }
  if (it === 'FEM_SolverCalculiX' || it === 'FEM_SolverCalculiXCcxTools') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => void addSolver(p)) }
  if (it === 'FEM_SolverElmer') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => void addDirect(p, 'SolverElmer')) }
  if (it === 'FEM_SolverMystran') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => void addDirect(p, 'SolverMystran')) }
  if (it === 'FEM_SolverZ88') return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => void addDirect(p, 'SolverZ88')) }
  if (it === 'FEM_EquationElasticity' || it === 'FEM_EquationHeat') {
    const kind = it === 'FEM_EquationHeat' ? 'EquationHeat' : 'EquationElasticity'
    return { label, icon: iconOf(it), cmd: it, title: r.tip ?? undefined, disabled: !getState().slug, onSelect: () => inPart(it, (p) => void addEquation(p, kind)) }
  }
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
