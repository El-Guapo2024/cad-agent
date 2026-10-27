// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Assembly/CommandCreateSimulation.py: 2024 Ondsel
//   No copyright line in the file: src/Mod/Assembly/Gui/Resources/panels/TaskAssemblyCreateSimulation.ui
// The Assembly workbench's simulations: TaskAssemblyCreateSimulation (the motions, the settings, Generate and the
// Animation Player) and MotionEditDialog (a motion's joint, type and formula). Generate runs the solver's KINEMATIC
// analysis in the page's wasm (AssemblyObject::generateSimulation) and the slider shows a frame (updateForFrame); OK
// puts the parts back where they were (restoreAssemblyPartsPlacements) and keeps the Simulation and its motions.
import { useEffect, useRef, useState } from 'react'
import { closeTask } from './actions'
import { Icon } from './icons'
import { TaskBox } from './panels'
import { QuantityBox, LENGTH } from './qsb'
import type { Dims } from './units-data'
import { getState, report, useStore } from './store'
import { loadAssemblySolver, type Plc } from './ondsel'
import { applyAssembly, asmObject, showPlacements, type AsmObj, type AsmView } from './assembly_wb'

const TIME: Dims = [0, 0, 1, 0, 0, 0, 0, 0]
const DRIVEN = ['Revolute', 'Slider', 'Cylindrical']                 // MotionEditDialog.setup_joint_combo
type MType = 'Angular' | 'Linear'
interface Motion { name?: string; joint: string; type: MType; formula: string }
/** setup_motiontype_combo: a Revolute turns, a Slider slides, a Cylindrical does either. */
const typesOf = (jt: string): MType[] => (jt === 'Revolute' ? ['Angular'] : jt === 'Slider' ? ['Linear'] : ['Angular', 'Linear'])
const labelOfObj = (o?: AsmObj) => String(o?.label ?? o?.name ?? '')

/** The joints a motion can drive (getJointsOfType(assembly, ["Revolute", "Slider", "Cylindrical"])). */
function drivable(v: AsmView | null | undefined): AsmObj[] {
  return (v?.objects ?? []).filter((o) => o.kind === 'Joint' && DRIVEN.includes(String(o.joint_type)))
}

/** MotionEditDialog: the joint, the motion type and the formula, with the help Show/Hide. */
function MotionDialog({ motion, onOk, onCancel }: { motion: Motion | null; onOk(m: Motion): void; onCancel(): void }) {
  const v = useStore((s) => s.assembly)
  const joints = drivable(v)
  const [joint, setJoint] = useState(motion?.joint ?? joints[0]?.name ?? '')
  const jt = String(asmObject(v, joint)?.joint_type ?? '')
  const [type, setType] = useState<MType>(motion?.type ?? 'Angular')
  const [formula, setFormula] = useState(motion?.formula ?? 'initialValue + 5*time')
  const [help, setHelp] = useState(false)
  // the motion type reset to the joint's first when the joint cannot take it
  const types = typesOf(jt)
  const shownType = types.includes(type) ? type : types[0]
  return <div className="as-dialog" data-dialog="motion" role="dialog">
    <div className="as-grid">
      <label>Joint</label>
      <select data-qf="joint" value={joint} onChange={(e) => setJoint(e.target.value)}>
        {joints.map((j) => <option key={j.name} value={j.name}>{labelOfObj(j)}</option>)}
      </select>
      <label>Motion Type</label>
      <select data-qf="motionType" value={shownType} onChange={(e) => setType(e.target.value as MType)}>
        {types.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <label>Formula</label>
      <input className="qline" data-qf="formula" value={formula} placeholder="Enter your formula…" onChange={(e) => setFormula(e.target.value)} />
    </div>
    {help && <div className="as-help">
      <p>In capital are variables that you need to replace with actual values. 'initialValue' is dynamically replaced by the current angle or distance. More details about each example in its tooltip.</p>
      <p title="C is a constant offset, VEL is a velocity">{' - Linear: C + VEL*time'}</p>
      <p title="C is a constant offset, VEL is a velocity, ACC is an acceleration">{' - Quadratic: C + VEL*time + ACC*time^2'}</p>
      <p title="C is a constant offset, AMP is an amplitude, VEL is a velocity, PHASE is a phase offset">{' - Harmonic: C + AMP*sin(VEL*time - PHASE)'}</p>
      <p title="C is a constant offset, TIMEC is a time constant of the exponential">{' - Exponential: C*exp(time/TIMEC)'}</p>
      <p title="C is a constant offset, VEL is a velocity, ACC is an acceleration">{' - Smooth Step: L1 + (L2 - L1)*((1/2) + (1/pi)*arctan(SLP*(time - T0)))'}</p>
      <p title="Smooth Step and Ramp">{' - Smooth Square Impulse: (H/pi)*(arctan(SLP*(time - T1)) - arctan(SLP*(time - T2)))'}</p>
      <p title="Smooth Ramp Top Impulse">{' - Smooth Ramp Top Impulse: ((1/pi)*(arctan(1000*(time - T1)) - arctan(1000*(time - T2))))*(((H2 - H1)/(T2 - T1))*(time - T1) + H1)'}</p>
    </div>}
    <div className="tbuttons">
      <button className="qbtn" onClick={() => setHelp((h) => !h)}>{help ? 'Hide help' : 'Show help'}</button>
      <button className="qbtn default" disabled={!joint} onClick={() => onOk({ ...(motion?.name ? { name: motion.name } : {}), joint, type: shownType, formula })}>OK</button>
      <button className="qbtn" onClick={onCancel}>Cancel</button>
    </div>
  </div>
}

/** TaskAssemblyCreateSimulation: "Create Simulation", or "Edit <Label> Simulation" on one double-clicked. */
export function SimulationTask({ edit }: { edit?: string }) {
  const v = useStore((s) => s.assembly)
  const sim = edit ? asmObject(v, edit) : undefined
  const [motions, setMotions] = useState<Motion[]>(() => ((sim?.group as string[]) ?? []).map((n) => asmObject(v, n))
    .filter((o): o is AsmObj => !!o && o.kind === 'Motion')
    .map((o) => ({ name: o.name, joint: String(o.joint ?? ''), type: (o.motion_type as MType) ?? 'Angular', formula: String(o.formula ?? '') })))
  const num = (k: string, d: number) => (typeof sim?.[k] === 'number' ? (sim[k] as number) : d)
  const [start, setStart] = useState(num('a_time_start', 0))
  const [end, setEnd] = useState(num('b_time_end', 1))
  const [step, setStep] = useState(num('c_time_step_output', 1e-2))
  const [tol, setTol] = useState(num('f_global_error_tolerance', 1e-6))
  const [fps, setFps] = useState(num('j_frames_per_second', 30))
  const [sel, setSel] = useState(-1)
  const [dialog, setDialog] = useState<{ k: number } | null>(null)
  const [frames, setFrames] = useState<Record<string, Plc>[] | null>(null)
  const [frame, setFrame] = useState(1)
  const [msg, setMsg] = useState('')
  const timer = useRef<number | null>(null)
  const stop = () => { if (timer.current !== null) clearInterval(timer.current); timer.current = null }
  useEffect(() => () => { stop(); showPlacements(null) }, [])
  // onFrameChanged: the parts where the frame leaves them
  const show = (k: number) => { if (!frames) return; setFrame(k); showPlacements(frames[k]) }
  /** setFrameValue: clamped to 1 .. the slider's maximum */
  const setFrameValue = (k: number) => { if (!frames) return; show(Math.max(1, Math.min(frames.length - 1, k))) }
  const runKinematics = async () => {
    stop()
    const doc = getState().assembly?.solver
    if (!doc) return
    const solver = await loadAssemblySolver()
    const out = solver.simulate(doc as never, motions.map((m, i) => ({ name: m.name ?? `Motion${i}`, joint: m.joint, type: m.type, formula: m.formula })),
      { start, end, step, tolerance: tol })
    if (out.status !== 0 || !out.frames.length) {
      setFrames(null)
      setMsg(out.errors.join('\n') || 'Generation of simulation failed')
      report('err', `Generation of simulation failed${out.errors.length ? `: ${out.errors.join('; ')}` : ''}`)
      return
    }
    setMsg('')
    setFrames(out.frames)
    const last = out.frames.length - 1
    setFrame(last)
    showPlacements(out.frames[last])
  }
  /** animationTimerStart / playAnimation: from the slider's frame, wrapping between 1 and the last frame. */
  const play = (direction: 1 | -1) => {
    stop()
    if (!frames) return
    const startFrm = 1, endFrm = frames.length - 1
    if (startFrm >= endFrm) return
    const delta = 1 / fps, t0 = performance.now(), offset = frame - startFrm, range = endFrm - startFrm
    timer.current = window.setInterval(() => {
      const count = Math.floor((performance.now() - t0) / 1000 / delta)
      const index = ((((direction * count + offset) % range) + range) % range) + startFrm
      setFrame(index)
      showPlacements(frames[index])
    }, delta * 1000)
  }
  const stepBy = (d: 1 | -1) => {
    stop()
    if (!frames) return
    let k = frame + d
    if (k < 1) k = frames.length - 1                 // wraparound
    if (k > frames.length - 1) k = 1
    setFrameValue(k)
  }
  const ok = async () => {
    stop()
    closeTask()
    showPlacements(null)                              // restoreAssemblyPartsPlacements
    await applyAssembly([{ op: 'simulation', ...(edit ? { name: edit } : {}),
      settings: { a_time_start: start, b_time_end: end, c_time_step_output: step, f_global_error_tolerance: tol, j_frames_per_second: fps },
      motions: motions.map((m) => ({ ...(m.name ? { name: m.name } : {}), joint: m.joint, motion_type: m.type, formula: m.formula })) }],
    edit ? `Edit ${labelOfObj(sim)} Simulation` : 'Create Simulation')
  }
  const cancel = () => { stop(); closeTask(); showPlacements(null) }
  // updateLabel: "<the joint's Label> (Angular)"
  const motionLabel = (m: Motion) => `${labelOfObj(asmObject(v, m.joint)) || m.joint} (${m.type === 'Linear' ? 'Linear' : 'Angular'})`
  const remove = () => { if (sel >= 0) { setMotions((ms) => ms.filter((_, i) => i !== sel)); setSel(-1) } }
  const time = (setter: (x: number) => void, value: number, name: string, tip: string) =>
    <div className="tfield" title={tip}><span>{name}</span><QuantityBox value={value} dims={TIME} decimals={9} min={0} onChange={setter} /></div>
  return <div className="tasks as-task" data-task="simulation">
    <TaskBox title="Simulation" icon="as-simulation">
     <fieldset className="tgroup" data-qf="groupBox_motions"><legend>Motions</legend>
      <div className="as-list" data-qf="motionList" tabIndex={0} onKeyDown={(e) => { if (e.key === 'Delete') remove() }}>
        {motions.map((m, k) => <div key={k} className={`as-item${k === sel ? ' sel' : ''}`} data-motion={m.name ?? `new${k}`}
          onClick={() => setSel(k)} onDoubleClick={() => setDialog({ k })}>
          <Icon name={m.type === 'Linear' ? 'as-motion-linear' : 'as-motion-angular'} size={16} /> {motionLabel(m)}</div>)}
      </div>
      <div className="as-row">
        <button className="qbtn" data-qf="AddButton" title="Add a prescribed motion" onClick={() => setDialog({ k: -1 })}>+</button>
        <button className="qbtn" data-qf="RemoveButton" title="Delete selected motions" disabled={sel < 0} onClick={remove}>−</button>
      </div>
     </fieldset>
     <fieldset className="tgroup" data-qf="groupBox_settings"><legend>Simulation Settings</legend>
      {time(setStart, start, 'Start', 'Start time of the simulation')}
      {time(setEnd, end, 'End', 'End time of the simulation')}
      {time(setStep, step, 'Step', 'Time step')}
      {/* setSpinboxPrecision(GlobalErrorToleranceSpinBox, 9, App.Units.Length): FreeCAD shows the tolerance as a length */}
      <div className="tfield" title="Global error tolerance"><span>Tolerance</span><QuantityBox value={tol} dims={LENGTH} decimals={9} min={0} onChange={setTol} /></div>
      <div className="as-row">
        <button className="qbtn" data-qf="RunKinematicsButton" onClick={() => void runKinematics()}>Generate</button>
        {frames && <button className="qbtn" data-qf="SaveAnimationButton" disabled title="n/a: saving the animation as a video is not ported"><Icon name="save" size={16} /></button>}
      </div>
      {msg && <p className="hint as-error">{msg}</p>}
     </fieldset>
     {/* data-placements: the frame shown, for ui/scripts/assemblycheck.mjs */}
     {frames && <fieldset className="tgroup" data-qf="groupBox_player" data-placements={JSON.stringify(frames[frame] ?? {})}><legend>Animation Player</legend>
      <div className="as-row">
        <span data-qf="FrameLabel">Frame {frame}</span>
        <input type="range" data-qf="frameSlider" min={0} max={frames.length - 1} value={frame} onChange={(e) => { stop(); show(Number(e.target.value)) }} />
        <span data-qf="FrameTimeLabel">{(frame * step).toFixed(2)} s</span>
      </div>
      <div className="tfield"><span>Frames per second</span>
        <input type="number" className="qline" data-qf="FramesPerSecondSpinBox" min={0} max={99} value={fps} onChange={(e) => setFps(Math.max(0, Math.min(99, Number(e.target.value) || 0)))} /></div>
      <div className="as-row">
        <button className="qbtn" data-qf="StepBackwardButton" title="Step backward" onClick={() => stepBy(-1)}><Icon name="as-step-back" size={16} /></button>
        <button className="qbtn" data-qf="PlayBackwardButton" title="Play backward" onClick={() => play(-1)}><Icon name="as-play-back" size={16} /></button>
        <button className="qbtn" data-qf="StopButton" title="Stop" onClick={stop}><Icon name="as-stop" size={16} /></button>
        <button className="qbtn" data-qf="PlayForwardButton" title="Play forward" onClick={() => play(1)}><Icon name="as-play" size={16} /></button>
        <button className="qbtn" data-qf="StepForwardButton" title="Step forward" onClick={() => stepBy(1)}><Icon name="as-step" size={16} /></button>
      </div>
     </fieldset>}
    </TaskBox>
    <div className="tbuttons pd-buttons">
      <button className="qbtn default" onClick={() => void ok()}>OK</button>
      <button className="qbtn" onClick={cancel}>Cancel</button>
    </div>
    {dialog && <MotionDialog motion={dialog.k >= 0 ? motions[dialog.k] : null} onCancel={() => setDialog(null)}
      onOk={(m) => { setMotions((ms) => (dialog.k >= 0 ? ms.map((x, i) => (i === dialog.k ? m : x)) : [...ms, m])); setDialog(null) }} />}
  </div>
}
