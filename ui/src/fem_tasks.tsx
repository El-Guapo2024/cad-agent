// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), each file LGPL-2.1-or-later (ui/NOTICE has them all):
//   No copyright line in the file: src/Mod/Fem/Gui/TaskFemConstraintFixed.ui, src/Mod/Fem/Gui/TaskFemConstraintForce.ui,
//       src/Mod/Fem/Gui/TaskFemConstraintPressure.ui, src/Mod/Fem/Gui/Resources/ui/Material.ui,
//       src/Mod/Fem/Gui/Resources/ui/MeshGmsh.ui, src/Mod/Fem/Gui/Resources/ui/ResultShow.ui,
//       src/Mod/Fem/Gui/TaskFemConstraintDisplacement.ui, src/Mod/Fem/Gui/TaskFemConstraintTemperature.ui,
//       src/Mod/Fem/Gui/TaskFemConstraintInitialTemperature.ui, src/Mod/Fem/Gui/TaskFemConstraintHeatflux.ui
// The FEM workbench's task panels: the analysis's objects, adding or changing a constraint, a material, a mesh, a
// solver or an Elmer equation, each written to the part file's FEM list (`cad fem apply`, cad_agent/fem_edit.py), and Results > Show Result,
// the last run's values on the mesh's outside as a helper in the 3D view (`cad fem result`).
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api, resultText } from './api'
import { closeTask, getView, loadHistory, openTask } from './actions'
import { TaskBox } from './panels'
import { QComboBox } from './combo'
import type { IconName } from './icons'
import { parsePartPick, partMatrix, shownNames, usePartScene } from './part_pick'
import { Check, Radio } from './part_widgets'
import { getState, report, setState, useStore } from './store'
import { runSolver } from './fem_wb'

export type FemObject = { name: string; kind: string; [k: string]: unknown }
type Ref = [string, string]
type Kind = 'ConstraintFixed' | 'ConstraintForce' | 'ConstraintPressure' | 'MaterialSolid' | 'MeshGmsh' | 'SolverCalculiX'
  | 'ConstraintDisplacement' | 'ConstraintSelfWeight' | 'ConstraintTemperature' | 'ConstraintInitialTemperature' | 'ConstraintHeatflux'
  | 'SolverElmer' | 'SolverMystran' | 'SolverZ88' | 'EquationElasticity' | 'EquationHeat'

const TITLE: Record<Kind, string> = { ConstraintFixed: 'Fixed Boundary Condition', ConstraintForce: 'Force Load', ConstraintPressure: 'Pressure Load',
  MaterialSolid: 'Material', MeshGmsh: 'Mesh', SolverCalculiX: 'Solver CalculiX Standard', ConstraintDisplacement: 'Displacement Boundary Condition',
  ConstraintSelfWeight: 'Gravity Load', ConstraintTemperature: 'Temperature Boundary Condition', ConstraintInitialTemperature: 'Initial Temperature',
  ConstraintHeatflux: 'Heat Flux Load', SolverElmer: 'Solver Elmer', SolverMystran: 'Solver Mystran', SolverZ88: 'Solver Z88', EquationElasticity: 'Elasticity Equation', EquationHeat: 'Heat Equation' }
// FreeCAD's names for new objects (ObjectsFem's defaults; the commands' labels)
export const BASE_NAME: Record<Kind, string> = { ConstraintFixed: 'ConstraintFixed', ConstraintForce: 'ConstraintForce', ConstraintPressure: 'ConstraintPressure',
  MaterialSolid: 'MaterialSolid', MeshGmsh: 'FEMMeshGmsh', SolverCalculiX: 'CalculiXccxTools', ConstraintDisplacement: 'ConstraintDisplacement',
  ConstraintSelfWeight: 'ConstraintSelfWeight', ConstraintTemperature: 'ConstraintTemperature', ConstraintInitialTemperature: 'ConstraintInitialTemperature',
  ConstraintHeatflux: 'ConstraintHeatflux', SolverElmer: 'SolverElmer', SolverMystran: 'SolverMystran', SolverZ88: 'SolverZ88', EquationElasticity: 'Elasticity', EquationHeat: 'Heat' }
const ICON: Record<Kind, string> = { ConstraintFixed: 'FEM_ConstraintFixed', ConstraintForce: 'FEM_ConstraintForce', ConstraintPressure: 'FEM_ConstraintPressure',
  MaterialSolid: 'FEM_MaterialSolid', MeshGmsh: 'FEM_MeshGmshFromShape', SolverCalculiX: 'FEM_SolverStandard', ConstraintDisplacement: 'FEM_ConstraintDisplacement',
  ConstraintSelfWeight: 'FEM_ConstraintSelfWeight', ConstraintTemperature: 'FEM_ConstraintTemperature', ConstraintInitialTemperature: 'FEM_ConstraintInitialTemperature',
  ConstraintHeatflux: 'FEM_ConstraintHeatflux', SolverElmer: 'FEM_SolverElmer', SolverMystran: 'FEM_SolverMystran', SolverZ88: 'FEM_SolverZ88', EquationElasticity: 'FEM_EquationElasticity', EquationHeat: 'FEM_EquationHeat' }
const icon = (k: Kind) => `fem-${ICON[k]}` as IconName
const DEFAULTS: Record<Kind, Record<string, unknown>> = {
  ConstraintFixed: { references: [] },
  ConstraintForce: { references: [], force: '0 N', direction: null, reversed: false },
  ConstraintPressure: { references: [], pressure: '0 MPa', reversed: false },
  MaterialSolid: { material_name: 'Steel', youngs_modulus: '210000 MPa', poisson_ratio: 0.3, density: '7900 kg/m^3', references: [],
    thermal_conductivity: null, thermal_expansion_coefficient: null, specific_heat: null },
  ConstraintDisplacement: { references: [], x_free: true, x_displacement: '0 mm', y_free: true, y_displacement: '0 mm', z_free: true, z_displacement: '0 mm' },
  ConstraintSelfWeight: { gravity_acceleration: '9806.65 mm/s^2', gravity_direction: [0, 0, -1] },
  ConstraintTemperature: { references: [], temperature: '300 K', constraint_type: 'Temperature', concentrated_heat_flux: '0 W' },
  ConstraintInitialTemperature: { initial_temperature: '300 K' },
  ConstraintHeatflux: { references: [], constraint_type: 'Convection', film_coef: '0 W/m^2/K', ambient_temp: '0 K', distributed_heat_flux: '0 W/m^2' },
  MeshGmsh: { shape: null, characteristic_length_max: null, characteristic_length_min: null, element_order: null, element_dimension: null },
  SolverCalculiX: { analysis_type: null, eigenmodes_count: null },
  SolverElmer: {},
  SolverMystran: {},
  SolverZ88: { solver_type: null },
  EquationElasticity: { solver: null, calculate_stresses: null, calculate_principal: null, calculate_strains: null },
  EquationHeat: { solver: null },
}
// what the Elasticity equation's flags are when left as made (equations/elasticity.py)
const ELASTICITY_FLAGS: [string, string, boolean][] = [['calculate_stresses', 'CalculateStresses', false], ['calculate_principal', 'CalculatePrincipal', true],
  ['calculate_strains', 'CalculateStrains', false]]
// the kinds of element each panel's lbl_info names
const ELEMENTS: Partial<Record<Kind, string[]>> = { ConstraintFixed: ['Vertex', 'Edge', 'Face'], ConstraintForce: ['Vertex', 'Edge', 'Face'], ConstraintPressure: ['Edge', 'Face'],
  ConstraintDisplacement: ['Vertex', 'Edge', 'Face'], ConstraintTemperature: ['Vertex', 'Edge', 'Face'], ConstraintHeatflux: ['Edge', 'Face'] }
const QUANTITY = /^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?\s*[A-Za-zµ][A-Za-zµ0-9^/*·]*$/i

async function listObjects(part: string): Promise<FemObject[] | null> {
  const slug = getState().slug
  if (!slug) return null
  const r = await api.cad(slug, ['fem', 'list', slug, part])
  if (r.exit !== 0) { report('err', `FEM: ${resultText(r)}`); return null }
  return (r.data?.objects ?? []) as FemObject[]
}

/** `cad fem apply`: the ops as one undo step; false (and the reason in the Report view) when the file did not change. */
export async function applyFem(part: string, ops: Record<string, unknown>[], name: string): Promise<boolean> {
  const slug = getState().slug
  if (!slug) return false
  try {
    const r = await api.cad(slug, ['fem', 'apply', slug, part, '--ops', JSON.stringify(ops), '--name', name])
    if (r.exit !== 0) { report('err', `${name}: ${resultText(r)}`); return false }
    report('msg', `${part}: ${name}`)
    loadHistory()
    return true
  } catch (e) { report('err', `${name}: ${e instanceof Error ? e.message : String(e)}`); return false }
}

/** A name no object of the analysis has: FreeCAD's base name, then 001, 002, ... */
export async function freshName(part: string, kind: Kind): Promise<string | null> {
  const have = await listObjects(part)
  if (!have) return null
  const doc = getState().features[part]
  const used = new Set([...have.map((o) => o.name), ...(doc?.objects ?? []).map((o) => o.name), ...(doc?.features ?? []).map((o) => o.name)])
  const base = BASE_NAME[kind]
  if (!used.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!used.has(n)) return n }
}

/** The solvers and Gravity have no panel when made: the command adds them, as FreeCAD's does (Edit changes them). */
export async function addDirect(part: string, kind: 'SolverCalculiX' | 'SolverElmer' | 'SolverMystran' | 'SolverZ88' | 'ConstraintSelfWeight') {
  const name = await freshName(part, kind)
  if (name && await applyFem(part, [{ op: 'add', kind, name }], TITLE[kind])) openTask('fem', part, 'analysis')
}
export const addSolver = (part: string) => addDirect(part, 'SolverCalculiX')

/** An Elmer equation, made for the analysis's Elmer solver (FreeCAD's equation commands want one selected). */
export async function addEquation(part: string, kind: 'EquationElasticity' | 'EquationHeat') {
  const have = await listObjects(part)
  if (!have) return
  const solver = have.find((o) => o.kind === 'SolverElmer')
  if (!solver) { report('warn', `${TITLE[kind]}: the analysis has no Elmer solver; add Solve > Solvers > Solver Elmer first`); return }
  const name = await freshName(part, kind)
  if (name && await applyFem(part, [{ op: 'add', kind, name, props: { solver: solver.name } }], TITLE[kind])) openTask('fem', part, 'analysis')
}

/** The analysis's objects, each to change or delete; Run Solver and Show Result. FreeCAD has these in the tree. */
function AnalysisTask({ part }: { part: string }) {
  const [objects, setObjects] = useState<FemObject[] | null>(null)
  const [rev, setRev] = useState(0)
  const task = useStore((s) => s.task)                // openTask again (the solver added): a new task, the list read again
  useEffect(() => { let live = true; void listObjects(part).then((o) => { if (live) setObjects(o ?? []) }); return () => { live = false } }, [part, rev, task])
  async function remove(name: string) { if (await applyFem(part, [{ op: 'delete', name }], `Delete ${name}`)) setRev((r) => r + 1) }
  return <div className="tasks" data-task="fem-analysis">
    <div className="tbuttons"><button className="qbtn" onClick={() => closeTask()}>Close</button></div>
    <TaskBox title={`Analysis of ${part}`} icon={'fem-FEM_Analysis' as IconName}>
      {objects === null ? <div>Loading ...</div> : !objects.length ? <div data-qf="empty">No objects yet: add a solver, a material, boundary conditions and a mesh from the Model and Mesh menus.</div>
        : <table data-qf="objects" style={{ width: '100%' }}><tbody>{objects.map((o) => <tr key={o.name} data-name={o.name}>
          <td>{o.name}</td><td style={{ opacity: 0.7 }}>{TITLE[o.kind as Kind] ?? o.kind}</td>
          <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
            {<button className="qbtn" data-qf="edit" onClick={() => openTask('fem', part, `edit:${o.name}`)}>Edit</button>}
            <button className="qbtn" data-qf="delete" onClick={() => void remove(o.name)}>Delete</button>
          </td></tr>)}</tbody></table>}
      <div className="tbuttons">
        <button className="qbtn" data-qf="run" onClick={() => void runSolver()}>Run Solver</button>
        <button className="qbtn" data-qf="result" onClick={() => openTask('fem', part, 'result')}>Show Result</button>
      </div>
    </TaskBox>
  </div>
}

/** The element picks drawn in the selection colour over the panel's shapes. */
function useRefHighlight(part: string, meshes: ReturnType<typeof usePartScene>, refs: Ref[]) {
  const key = JSON.stringify(refs)
  useEffect(() => {
    const v = getView()
    if (!v) return
    const g = new THREE.Group(), color = new THREE.Color(getState().selPrefs.color)
    for (const [o, el] of JSON.parse(key) as Ref[]) {
      const m = meshes[o]
      const geo = new THREE.BufferGeometry()
      if (el.startsWith('Vertex')) {
        const x = m?.vertices?.find((p) => p.name === el); if (!x) continue
        geo.setAttribute('position', new THREE.Float32BufferAttribute(x.point, 3))
        g.add(new THREE.Points(geo, new THREE.PointsMaterial({ color, size: 9, sizeAttenuation: false })))
      } else if (el.startsWith('Edge')) {
        const x = m?.edges.find((p) => p.name === el); if (!x) continue
        geo.setAttribute('position', new THREE.Float32BufferAttribute(x.points, 3))
        g.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color })))
      } else {
        const x = m?.faces.find((p) => p.name === el); if (!x) continue
        geo.setAttribute('position', new THREE.Float32BufferAttribute(x.points, 3)); geo.setIndex(x.index)
        g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, transparent: true, opacity: 0.6, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })))
      }
    }
    g.applyMatrix4(partMatrix(getState().scene?.bodies.find((b) => b.part === part)))
    v.setHelper('fem-refs', g.children.length ? g : null)
    return () => getView()?.setHelper('fem-refs', null)
  }, [key, meshes, part])
}

function Text({ label, name, value, onChange }: { label: string; name: string; value: string; onChange(v: string): void }) {
  return <label className="tfield"><span>{label}</span><input data-qf={name} value={value} onChange={(e) => onChange(e.target.value)} /></label>
}

/** A constraint's, the material's or the mesh's panel, on a new object (kind) or the one edited (edit). */
function ObjectTask({ part, kind: kind0, edit }: { part: string; kind?: Kind; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const [props, setProps] = useState<Record<string, unknown> | null>(kind0 ? DEFAULTS[kind0] : null)
  const [kind, setKind] = useState<Kind | undefined>(kind0)
  const [direction, setDirection] = useState(false)     // the Direction button waits for an edge or a face
  const [start] = useState<{ current: Record<string, unknown> | null }>({ current: null })
  useEffect(() => {
    if (!edit) return
    let live = true
    void listObjects(part).then((all) => {
      const o = all?.find((x) => x.name === edit)
      if (!live) return
      if (!o) { report('err', `The analysis has no object ${edit}`); closeTask(); return }
      const { name: _n, kind: k, ...rest } = o
      void _n
      start.current = rest; setKind(k as Kind); setProps(rest)
    })
    return () => { live = false }
  }, [part, edit, start])
  const set = (p: Record<string, unknown>) => setProps((o) => ({ ...(o ?? {}), ...p }))
  const refs = (props?.references ?? []) as Ref[]
  const allowed = kind ? ELEMENTS[kind] : undefined
  const picksRef = useRef<(p: Ref) => void>(() => {})
  picksRef.current = ([o, el]) => {
    if (direction) { set({ direction: [o, el] }); setDirection(false); return }
    set({ references: refs.some((r) => r[0] === o && r[1] === el) ? refs.filter((r) => !(r[0] === o && r[1] === el)) : [...refs, [o, el]] })
  }
  const meshes = usePartScene({ part, active: !!doc && !!allowed, vertices: true, helperKey: 'fem-task', gateKey: `${kind}:${direction}`,
    allow: (_o, el) => (direction ? el.startsWith('Edge') || el.startsWith('Face') : !!allowed?.some((a) => el.startsWith(a))),
    onPick: (name) => { const p = parsePartPick(name); if (p) picksRef.current(p) } })
  useRefHighlight(part, meshes, allowed ? [...refs, ...(props?.direction ? [props.direction as Ref] : [])] : [])
  if (!props || !kind) return <div className="tasks">Loading ...</div>
  const shapes = shownNames(doc)
  const str = (k: string) => String(props[k] ?? '')
  const num = (k: string, what: string) => (QUANTITY.test(str(k).trim()) ? null : `${what}: "${str(k)}" is not a number with a unit`)
  const opt = (k: string, what: string) => (str(k).trim() === '' ? null : num(k, what))
  function problem(): string | null {
    if (kind === 'ConstraintForce') return num('force', 'Force')
    if (kind === 'ConstraintPressure') return num('pressure', 'Pressure')
    if (kind === 'MaterialSolid') {
      const p = Number(props!.poisson_ratio)
      return num('youngs_modulus', "Young's modulus") ?? num('density', 'Density') ?? (Number.isFinite(p) && p >= 0 && p < 0.5 ? null : 'Poisson ratio is a number from 0 up to 0.5')
        ?? opt('thermal_conductivity', 'Thermal conductivity') ?? opt('thermal_expansion_coefficient', 'Expansion coefficient') ?? opt('specific_heat', 'Specific heat capacity')
    }
    if (kind === 'ConstraintDisplacement') {
      for (const a of ['x', 'y', 'z']) if (!props![`${a}_free`]) { const bad = num(`${a}_displacement`, `Displacement ${a.toUpperCase()}`); if (bad) return bad }
      return null
    }
    if (kind === 'ConstraintTemperature') return props!.constraint_type === 'CFlux' ? num('concentrated_heat_flux', 'Concentrated heat flux') : num('temperature', 'Temperature')
    if (kind === 'ConstraintInitialTemperature') return num('initial_temperature', 'Initial temperature')
    if (kind === 'ConstraintHeatflux') return props!.constraint_type === 'DFlux' ? num('distributed_heat_flux', 'Surface heat flux') : num('film_coef', 'Film coefficient') ?? num('ambient_temp', 'Ambient temperature')
    if (kind === 'ConstraintSelfWeight') {
      const d = (props!.gravity_direction as number[]) ?? []
      return num('gravity_acceleration', 'Gravity acceleration') ?? (d.length === 3 && d.every(Number.isFinite) && d.some((x) => x !== 0) ? null : 'Direction: three numbers, not all 0')
    }
    if (kind === 'MeshGmsh') {
      if (!props!.shape && shapes.length !== 1) return 'Mesh: choose the object to mesh'
      for (const [k, w] of [['characteristic_length_max', 'Maximum size'], ['characteristic_length_min', 'Minimum size']] as const)
        if (str(k).trim() && !QUANTITY.test(str(k).trim())) return `${w}: "${str(k)}" is not a length with a unit`
    }
    return null
  }
  async function ok() {
    const bad = problem()
    if (bad) { report('warn', bad); return }
    const clean: Record<string, unknown> = { ...props }
    if (kind === 'MeshGmsh') {
      clean.shape = clean.shape ?? shapes[0]
      for (const k of ['characteristic_length_max', 'characteristic_length_min']) clean[k] = String(clean[k] ?? '').trim() || null
    }
    if (kind === 'MaterialSolid') {
      clean.poisson_ratio = Number(clean.poisson_ratio)
      for (const k of ['thermal_conductivity', 'thermal_expansion_coefficient', 'specific_heat']) clean[k] = String(clean[k] ?? '').trim() || null
    }
    if (edit) {
      const changed = Object.fromEntries(Object.entries(clean).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(start.current?.[k])))
      if (Object.keys(changed).length && !await applyFem(part, [{ op: 'set', name: edit, props: changed }], `Edit ${edit}`)) return
    } else {
      const name = await freshName(part, kind!)
      if (!name || !await applyFem(part, [{ op: 'add', kind, name, props: clean }], TITLE[kind!])) return
    }
    openTask('fem', part, 'analysis')
  }
  return <div className="tasks pt-task" data-task="fem-object" data-kind={kind}>
    <div className="tbuttons"><button className="qbtn default" data-qf="ok" onClick={() => void ok()}>OK</button><button className="qbtn" onClick={() => openTask('fem', part, 'analysis')}>Cancel</button></div>
    <TaskBox title={edit ?? TITLE[kind]} icon={icon(kind)}>
      {allowed && <>
        <div data-qf="lbl_info">Select geometry of type: {allowed.join(', ')}</div>
        <div data-qf="references" style={{ minHeight: 60, maxHeight: 140, overflow: 'auto', border: '1px solid var(--border)', padding: 2, margin: '3px 0' }}>
          {refs.map(([o, el]) => <div key={o + el} data-ref={`${o}:${el}`} style={{ display: 'flex', justifyContent: 'space-between' }}><span>{o}:{el}</span>
            <button className="qbtn" title="Remove" onClick={() => set({ references: refs.filter((r) => !(r[0] === o && r[1] === el)) })}>×</button></div>)}
        </div>
      </>}
      {kind === 'ConstraintForce' && <>
        <Text label="Force" name="spinForce" value={str('force')} onChange={(v) => set({ force: v })} />
        <label className="tfield"><span><button className="qbtn" data-qf="buttonDirection" aria-pressed={direction} onClick={(e) => { e.preventDefault(); setDirection((d) => !d) }}>Direction</button></span>
          <input data-qf="lineDirection" readOnly value={props.direction ? (props.direction as Ref).join(':') : ''} placeholder={direction ? 'Pick an edge or a face' : ''} /></label>
      </>}
      {kind === 'ConstraintPressure' && <Text label="Pressure" name="if_pressure" value={str('pressure')} onChange={(v) => set({ pressure: v })} />}
      {(kind === 'ConstraintForce' || kind === 'ConstraintPressure') && <Check label="Reverse direction" name="checkReverse" checked={!!props.reversed} onChange={(v) => set({ reversed: v })} />}
      {kind === 'MaterialSolid' && <>
        <Text label="Material" name="material_name" value={str('material_name')} onChange={(v) => set({ material_name: v })} />
        <fieldset className="tgroup"><legend>Basic Properties</legend><Text label="Density" name="qsb_density" value={str('density')} onChange={(v) => set({ density: v })} /></fieldset>
        <fieldset className="tgroup"><legend>Mechanical Properties</legend>
          <Text label="Young's modulus" name="qsb_young_modulus" value={str('youngs_modulus')} onChange={(v) => set({ youngs_modulus: v })} />
          <Text label="Poisson ratio" name="qsb_poisson_ratio" value={str('poisson_ratio')} onChange={(v) => set({ poisson_ratio: v })} />
        </fieldset>
      </>}
      {kind === 'MaterialSolid' && <fieldset className="tgroup"><legend>Thermal Properties</legend>
        <Text label="Thermal conductivity" name="qsb_thermal_conductivity" value={str('thermal_conductivity')} onChange={(v) => set({ thermal_conductivity: v })} />
        <Text label="Expansion coefficient" name="qsb_expansion_coefficient" value={str('thermal_expansion_coefficient')} onChange={(v) => set({ thermal_expansion_coefficient: v })} />
        <Text label="Specific heat capacity" name="qsb_specific_heat" value={str('specific_heat')} onChange={(v) => set({ specific_heat: v })} />
      </fieldset>}
      {kind === 'ConstraintDisplacement' && (['x', 'y', 'z'] as const).map((a) => <fieldset key={a} className="tgroup" data-qf={`Displacement${a.toUpperCase()}GB`}>
        <legend><label><input type="checkbox" checked={!props[`${a}_free`]} onChange={(e) => set({ [`${a}_free`]: !e.target.checked })} /> Displacement {a.toUpperCase()}</label></legend>
        {!props[`${a}_free`] && <Text label="Displacement" name={`spin${a}Displacement`} value={str(`${a}_displacement`)} onChange={(v) => set({ [`${a}_displacement`]: v })} />}
      </fieldset>)}
      {kind === 'ConstraintTemperature' && <>
        <label className="tfield"><span>Constraint type</span><QComboBox data-qf="cb_constr_type" value={str('constraint_type')} onChange={(e) => set({ constraint_type: e.target.value })}>
          <option value="Temperature">Temperature</option><option value="CFlux">Concentrated heat flux</option></QComboBox></label>
        {props.constraint_type === 'CFlux' ? <Text label="Concentrated heat flux" name="qsb_cflux" value={str('concentrated_heat_flux')} onChange={(v) => set({ concentrated_heat_flux: v })} />
          : <Text label="Temperature" name="qsb_temperature" value={str('temperature')} onChange={(v) => set({ temperature: v })} />}
      </>}
      {kind === 'ConstraintInitialTemperature' && <Text label="Initial temperature" name="if_temperature" value={str('initial_temperature')} onChange={(v) => set({ initial_temperature: v })} />}
      {kind === 'ConstraintHeatflux' && <>
        <label className="tfield"><span>Constraint type</span><QComboBox data-qf="cb_constr_type" value={str('constraint_type')} onChange={(e) => set({ constraint_type: e.target.value })}>
          <option value="Convection">Convection</option><option value="DFlux">Surface heat flux</option></QComboBox></label>
        {props.constraint_type === 'DFlux' ? <Text label="Surface heat flux" name="qsb_heat_flux" value={str('distributed_heat_flux')} onChange={(v) => set({ distributed_heat_flux: v })} />
          : <><Text label="Film coefficient" name="qsb_film_coef" value={str('film_coef')} onChange={(v) => set({ film_coef: v })} />
            <Text label="Ambient temperature" name="qsb_ambienttemp_conv" value={str('ambient_temp')} onChange={(v) => set({ ambient_temp: v })} /></>}
      </>}
      {kind === 'ConstraintSelfWeight' && <>
        <Text label="Gravity acceleration" name="GravityAcceleration" value={str('gravity_acceleration')} onChange={(v) => set({ gravity_acceleration: v })} />
        <Text label="Direction" name="GravityDirection" value={((props.gravity_direction as number[]) ?? []).join(', ')}
          onChange={(v) => set({ gravity_direction: v.split(',').map((x) => Number(x.trim())) })} />
      </>}
      {kind === 'SolverCalculiX' && <label className="tfield"><span>Analysis type</span><QComboBox data-qf="AnalysisType" value={str('analysis_type') || 'static'}
        onChange={(e) => set({ analysis_type: e.target.value === 'static' ? null : e.target.value })}><option value="static">static</option><option value="frequency">frequency</option><option value="thermomech">thermomech</option><option value="buckling">buckling</option></QComboBox></label>}
      {kind === 'SolverCalculiX' && props.analysis_type === 'buckling' && <label className="tfield"><span>Buckling factors</span><input data-qf="BucklingFactors" type="number" min={1} value={Number(props.buckling_factors ?? 1)}
        onChange={(e) => { const n = Math.round(Number(e.target.value)); if (n >= 1) set({ buckling_factors: n === 1 ? null : n }) }} /></label>}
      {kind === 'SolverCalculiX' && props.analysis_type === 'frequency' && <label className="tfield"><span>Eigenmodes</span><input data-qf="EigenmodesCount" type="number" min={1} value={Number(props.eigenmodes_count ?? 10)}
        onChange={(e) => { const n = Math.round(Number(e.target.value)); if (n >= 1) set({ eigenmodes_count: n === 10 ? null : n }) }} /></label>}
      {kind === 'EquationElasticity' && <fieldset className="tgroup"><legend>Elasticity</legend>
        {ELASTICITY_FLAGS.map(([k, prop, d]) => <Check key={k} label={prop.replace(/([a-z])([A-Z])/g, '$1 $2')} name={prop}
          checked={props[k] === null || props[k] === undefined ? d : !!props[k]} onChange={(v) => set({ [k]: v === d ? null : v })} />)}
      </fieldset>}
      {(kind === 'EquationElasticity' || kind === 'EquationHeat') && <div data-qf="solver">Solver: {str('solver')}</div>}
      {kind === 'MeshGmsh' && <fieldset className="tgroup"><legend>Mesh Parameters</legend>
        <label className="tfield"><span>Shape</span><QComboBox data-qf="shape" value={str('shape') || shapes[0] || ''} onChange={(e) => set({ shape: e.target.value })}>{shapes.map((n) => <option key={n} value={n}>{n}</option>)}</QComboBox></label>
        <label className="tfield"><span>Element dimension</span><QComboBox data-qf="cb_dimension" value={str('element_dimension') || 'From Shape'} onChange={(e) => set({ element_dimension: e.target.value })}>{['From Shape', '1D', '2D', '3D'].map((n) => <option key={n}>{n}</option>)}</QComboBox></label>
        <Text label="Maximum size" name="qsb_max_size" value={str('characteristic_length_max')} onChange={(v) => set({ characteristic_length_max: v })} />
        <Text label="Minimum size" name="qsb_min_size" value={str('characteristic_length_min')} onChange={(v) => set({ characteristic_length_min: v })} />
        <label className="tfield"><span>Element order</span><QComboBox data-qf="cb_order" value={str('element_order') || '2nd'} onChange={(e) => set({ element_order: e.target.value })}>{['1st', '2nd'].map((n) => <option key={n}>{n}</option>)}</QComboBox></label>
      </fieldset>}
    </TaskBox>
  </div>
}

type Hist = { low: number; high: number; counts: number[] }
type Fields = { displacement: number[]; fields: Record<string, number[]>; range: Record<string, [number, number]>; histogram?: Record<string, Hist> }
type ResultData = Fields & { points: number[]; triangles: number[]; nodes: number; volumes: number; modes?: (Fields & { frequency?: number; factor?: number })[] }
const RESULT_FIELDS: [string, string, string, string][] = [['displacement', 'Displacement magnitude', 'rb_abs_displacement', 'mm'], ['von_mises', 'von Mises stress', 'rb_vm_stress', 'MPa'],
  ['displacement_x', 'Displacement X', 'rb_x_displacement', 'mm'], ['max_principal', 'Maximum principal stress', 'rb_maxprin', 'MPa'],
  ['displacement_y', 'Displacement Y', 'rb_y_displacement', 'mm'], ['min_principal', 'Minimum principal stress', 'rb_minprin', 'MPa'],
  ['displacement_z', 'Displacement Z', 'rb_z_displacement', 'mm'], ['max_shear', 'Maximum shear stress (Tresca)', 'rb_max_shear_stress', 'MPa'],
  ['temperature', 'Temperature', 'rb_temperature', 'K']]
/** Blue, cyan, green, yellow, red from the smallest value to the largest. */
export function rainbow(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t)) * 4, s = Math.min(3, Math.floor(x)), f = x - s
  return ([[0, f, 1], [0, 1, 1 - f], [f, 1, 0], [1, 1 - f, 0]] as [number, number, number][])[s]
}

/** The Histogram button's plot (task_result_mechanical.py: a histogram of every node's value, 50 bins). */
function Histogram({ h, title, unit }: { h: Hist; title: string; unit: string }) {
  const W = 260, H = 110, top = Math.max(1, ...h.counts), bw = W / h.counts.length
  return <figure data-qf="histogram" style={{ margin: '6px 0' }}>
    <figcaption style={{ fontSize: '90%' }}>Histogram of {title}</figcaption>
    <svg viewBox={`0 0 ${W} ${H + 14}`} width="100%" role="img" aria-label={`Histogram of ${title}`}>
      {h.counts.map((c, i) => <rect key={i} x={i * bw} y={H - (c / top) * H} width={Math.max(0.5, bw - 0.5)} height={(c / top) * H} fill="#4d7fd6" opacity="0.7" />)}
      <line x1="0" y1={H} x2={W} y2={H} stroke="currentColor" strokeWidth="0.5" />
      <text x="0" y={H + 11} fontSize="9" fill="currentColor">{h.low.toPrecision(4)}</text>
      <text x={W} y={H + 11} fontSize="9" fill="currentColor" textAnchor="end">{h.high.toPrecision(4)} {unit}</text>
    </svg>
  </figure>
}

/** Results > Show Result (ResultShow.ui): the result (a frequency analysis's mode), the field, its range and histogram,
 *  the displacement scaled and animated; the part hidden meanwhile. */
function ResultTask({ part }: { part: string }) {
  const [data, setData] = useState<ResultData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState(0)
  const [field, setField] = useState<string | null>('von_mises')
  const [show, setShow] = useState(false)
  const [factor, setFactor] = useState(5)             // ResultShow.ui's sb_displacement_factor and its slider maximum
  const [factorMax, setFactorMax] = useState(10)
  const [histogram, setHistogram] = useState(false)
  const [anim, setAnim] = useState({ steps: 24, loops: 4, rate: 24, half: false })
  const [phase, setPhase] = useState<number | null>(null)      // the animation's sin(st * inc), null when stopped
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    const slug = getState().slug
    if (!slug) return
    let live = true
    void api.cad(slug, ['fem', 'result', slug, part]).then((r) => { if (!live) return; if (r.exit !== 0) setError(resultText(r)); else setData(r.data as unknown as ResultData) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : String(e)) })
    return () => { live = false }
  }, [part])
  useEffect(() => {                                   // the result mesh is drawn in the part's place
    if (!data) return
    const mine = (getState().scene?.bodies ?? []).filter((b) => b.part === part).map((b) => b.name).filter((n) => !getState().hidden.includes(n))
    setState((s) => ({ hidden: [...s.hidden, ...mine] }))
    return () => setState((s) => ({ hidden: s.hidden.filter((n) => !mine.includes(n)) }))
  }, [data, part])
  const cur: Fields | null = data ? (data.modes?.[mode] ?? data) : null
  useEffect(() => {                                   // no stresses (Z88's result): Displacement, its default field
    if (cur && field && !cur.fields[field]) setField(cur.fields.displacement ? 'displacement' : (RESULT_FIELDS.find(([k]) => cur.fields[k])?.[0] ?? null))
  }, [cur, field])
  useEffect(() => {
    const v = getView()
    if (!v || !data || !cur) return
    const n = data.points.length / 3, pos = new Float32Array(n * 3), col = new Float32Array(n * 3)
    const values = field ? cur.fields[field] : null, [lo, hi] = field && cur.range[field] ? cur.range[field] : [0, 0]
    const k = phase !== null ? phase * factor : show ? factor : 0
    for (let i = 0; i < n; i++) {
      for (let a = 0; a < 3; a++) pos[3 * i + a] = data.points[3 * i + a] + k * cur.displacement[3 * i + a]
      col.set(values ? rainbow(hi > lo ? (values[i] - lo) / (hi - lo) : 0) : [0.8, 0.8, 0.8], 3 * i)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3)); geo.setIndex(data.triangles)
    const g = new THREE.Group()
    g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })))
    g.applyMatrix4(partMatrix(getState().scene?.bodies.find((b) => b.part === part)))
    v.setHelper('fem-result', g)
  }, [data, cur, field, show, factor, phase, part])
  const stop = () => { if (timer.current) clearInterval(timer.current); timer.current = null; setPhase(null) }
  useEffect(() => () => { stop(); getView()?.setHelper('fem-result', null) }, [])
  /** animate_displacement: (cycles * steps + 1) frames at the frame rate, sin(st * inc) times the factor (full cycle) or
   *  its absolute value (half cycle; inc halved, or quartered for 0 cycles). */
  function start() {
    if (timer.current) { stop(); return }
    setShow(true)
    const steps = Math.max(1, Math.round(anim.steps)), loops = Math.max(1, Math.round(anim.loops)) * steps + 1
    const sinc = (Math.PI / steps) * 2, inc = anim.half ? (anim.loops > 0 ? sinc / 2 : sinc / 4) : sinc
    let st = 0
    timer.current = setInterval(() => {
      if (st >= loops) { stop(); return }
      const x = Math.sin(st * inc)
      setPhase(anim.half ? Math.abs(x) : x)
      st++
    }, 1000 / Math.max(1, anim.rate))
  }
  const close = () => openTask('fem', part, 'analysis')
  if (error) return <div className="tasks" data-task="fem-result"><div className="tbuttons"><button className="qbtn" onClick={close}>Close</button></div><div data-qf="error">{error}</div></div>
  if (!data || !cur) return <div className="tasks">Loading ...</div>
  const shown = RESULT_FIELDS.filter(([k]) => cur.fields[k])
  const fdef = RESULT_FIELDS.find(([k]) => k === field)
  const unit = fdef?.[3] ?? ''
  const range = field ? cur.range[field] : null
  const num = (k: 'steps' | 'loops' | 'rate', name: string, label: string) => <label className="tfield"><span>{label}</span>
    <input data-qf={name} type="number" min={k === 'loops' ? 0 : 1} value={anim[k]} onChange={(e) => { const x = Number(e.target.value); if (Number.isFinite(x) && x >= 0) setAnim((a) => ({ ...a, [k]: x })) }} /></label>
  return <div className="tasks pt-task" data-task="fem-result">
    <div className="tbuttons"><button className="qbtn" onClick={close}>Close</button></div>
    <TaskBox title="Show Result" icon={'fem-FEM_ResultShow' as IconName}>
      {data.modes && <label className="tfield"><span>Result</span><QComboBox data-qf="result_mode" value={String(mode)} onChange={(e) => setMode(Number(e.target.value))}>
        {data.modes.map((m, i) => <option key={i} value={String(i)}>{m.factor !== undefined ? `Mode ${i + 1}: buckling factor ${m.factor.toPrecision(6)}` : `Mode ${i + 1}: ${(m.frequency ?? 0).toPrecision(6)} Hz`}</option>)}</QComboBox></label>}
      <fieldset className="tgroup"><legend>Result Type</legend>
        <Radio label="None" name="rb_none" checked={field === null} onChange={() => setField(null)} />
        {shown.map(([k, label, name]) => <Radio key={k} label={label} name={name} checked={field === k} onChange={() => setField(k)} />)}
        {range && <>
          <div data-qf="colorbar" style={{ height: 10, margin: '6px 0 2px', background: 'linear-gradient(to right, #00f, #0ff, #0f0, #ff0, #f00)' }} />
          <label className="tfield"><span>Minimum</span><input data-qf="le_min" readOnly value={`${range[0].toPrecision(6)} ${unit}`} /></label>
          <label className="tfield"><span>Maximum</span><input data-qf="le_max" readOnly value={`${range[1].toPrecision(6)} ${unit}`} /></label>
        </>}
        <button className="qbtn" data-qf="show_histogram" disabled={!field || !cur.histogram?.[field]} onClick={() => setHistogram((h) => !h)}>Histogram</button>
        {histogram && field && cur.histogram?.[field] && <Histogram h={cur.histogram[field]} title={fdef?.[1] ?? field} unit={unit} />}
      </fieldset>
      <fieldset className="tgroup"><legend>Displacement Scaling</legend>
        <Check label="Show" name="cb_show_displacement" checked={show} onChange={setShow} />
        <input data-qf="hsb_displacement_factor" type="range" style={{ width: '100%' }} min={0} max={factorMax} step={factorMax / 100} value={factor} onChange={(e) => setFactor(Number(e.target.value))} />
        <label className="tfield"><span>Factor</span><input data-qf="sb_displacement_factor" type="number" min={0} value={factor} onChange={(e) => { const x = Number(e.target.value); if (Number.isFinite(x) && x >= 0) setFactor(x) }} /></label>
        <label className="tfield"><span>Slider maximum</span><input data-qf="sb_displacement_factor_max" type="number" min={1} value={factorMax} onChange={(e) => { const x = Number(e.target.value); if (Number.isFinite(x) && x >= 1) setFactorMax(x) }} /></label>
      </fieldset>
      <fieldset className="tgroup"><legend>Animation Control</legend>
        {num('steps', 'steps', 'Number of steps per cycle')}
        {num('loops', 'loops', 'Number of cycles')}
        {num('rate', 'framerate', 'Frame rate')}
        <Radio label="Full cycle" name="rb_full_cycle" checked={!anim.half} onChange={() => setAnim((a) => ({ ...a, half: false }))} />
        <Radio label="Half cycle" name="rb_half_cycle" checked={anim.half} onChange={() => setAnim((a) => ({ ...a, half: true }))} />
        <button className="qbtn" data-qf="startButton" onClick={start}>{phase !== null ? 'Stop Animation' : 'Start Animation'}</button>
      </fieldset>
    </TaskBox>
  </div>
}

/** openTask('fem', part, other): other is analysis, result, add:<kind> or edit:<name>. */
export function FemTask({ body: part, other }: { body: string; other: string }) {
  const [what, arg] = other.split(':')
  if (what === 'result') return <ResultTask key={part} part={part} />
  if (what === 'add') return <ObjectTask key={other} part={part} kind={arg as Kind} />
  if (what === 'edit') return <ObjectTask key={other} part={part} edit={arg} />
  return <AnalysisTask key={part} part={part} />
}
