// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/Gui/TaskLinkArrayParameters.cpp: 2026 Boyer Pierre-Louis
//   src/Mod/Part/Gui/Command.cpp: 2002 Jürgen Riegel
//   No copyright line in the file: src/Mod/Part/Gui/TaskLinkArrayParameters.ui,
//       src/Mod/Part/Gui/PatternCircularParametersWidget.ui
// Part_LinkArrays in the Assembly: Linear and Polar Link Array (activateLinkArrayCommand: the selected component's part,
// or the one chosen here, as LinkedObject; the array added to the active Assembly) and TaskLinkArrayParameters (Linked
// object, then PatternParametersWidget's fields, as PartDesign's pattern panels lay them out). OK writes the array
// (`cad assembly apply` with an array op, cad_agent/assembly_array.py) or the changed settings of the one double-clicked.
import { useMemo, useState } from 'react'
import { closeTask } from './actions'
import { TaskBox } from './panels'
import { QComboBox } from './combo'
import { LENGTH, QuantityBox } from './qsb'
import { getState, useStore, type Feature, type FeatureDoc } from './store'
import { LINEAR, POLAR, TransformFields } from './pd_transform'
import { applyAssembly, asmObject } from './assembly_wb'

export type ArrayKind = 'LinkArrayLinear' | 'LinkArrayPolar' | 'LinkArrayCircular'
const TITLE: Record<ArrayKind, string> = { LinkArrayLinear: 'Linear Link Array', LinkArrayPolar: 'Polar Link Array', LinkArrayCircular: 'Circular Link Array' }
// LinkArrayLinear and LinkArrayPolar's property defaults (FreeCAD's, as cad_agent/assembly_array.py has them)
const DEFAULTS: Record<ArrayKind, Record<string, unknown>> = {
  LinkArrayLinear: { direction: null, reversed: false, mode: 'Extent', length: 100, offset: 10, spacings: [-1], spacing_pattern: [0],
    occurrences: 2, direction2: null, reversed2: false, mode2: 'Extent', length2: 100, offset2: 10, spacings2: [0], spacing_pattern2: [0],
    occurrences2: 1 },
  LinkArrayPolar: { axis: null, reversed: false, mode: 'Extent', angle: 360, offset: 120, spacings: [-1, -1], spacing_pattern: [0], occurrences: 3 },
  LinkArrayCircular: { axis: null, radial_distance: 50, tangential_distance: 25, number_circles: 3, symmetry: 1 },
}
const NO_DOC: FeatureDoc = { part: '', params: {}, base: false, features: [], tip: null }

/** TaskLinkArrayParameters on a new array (kind) or the array double-clicked (edit). */
export function ArrayTask({ kind: kind0, edit }: { kind?: ArrayKind; edit?: string }) {
  const v = useStore((s) => s.assembly), features = useStore((s) => s.features), scene = useStore((s) => s.scene)
  const old = edit ? asmObject(v, edit) : undefined
  const kind = (old?.kind as ArrayKind | undefined) ?? kind0 ?? 'LinkArrayLinear'
  const parts = useMemo(() => [...new Set([...Object.keys(features), ...(scene?.bodies.map((b) => b.part).filter((p): p is string => !!p) ?? [])])].sort(),
    [features, scene])
  // activateLinkArrayCommand: the selection's object as LinkedObject (here a selected component's part)
  const selPart = (() => {
    const sel = getState().asmSel?.[0]
    const o = sel ? asmObject(v, sel) : undefined
    return typeof o?.linked_object === 'string' ? o.linked_object : undefined
  })()
  const [part, setPart] = useState<string>(String(old?.linked_object ?? selPart ?? parts[0] ?? ''))
  const start = Object.fromEntries(Object.keys(DEFAULTS[kind]).map((k) => [k, old?.[k] ?? DEFAULTS[kind][k]]))
  const [props, setProps] = useState<Record<string, unknown>>(start)
  const f: Feature = { name: edit ?? kind, type: kind === 'LinkArrayPolar' ? POLAR : LINEAR, ...props }
  async function ok() {
    if (edit) {
      const changed = Object.fromEntries(Object.entries(props).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(start[k])))
      if (Object.keys(changed).length && !await applyAssembly([{ op: 'set', name: edit, props: changed }], `Edit ${TITLE[kind]}`)) return
    } else {
      const given = Object.fromEntries(Object.entries(props).filter(([k, x]) => JSON.stringify(x) !== JSON.stringify(DEFAULTS[kind][k])))
      if (!await applyAssembly([{ op: 'array', kind, part, props: given }], TITLE[kind])) return
    }
    closeTask()
  }
  return <div className="tasks as-task" data-task="array">
    <div className="tbuttons"><button className="qbtn default" onClick={() => void ok()}>OK</button><button className="qbtn" onClick={() => closeTask()}>Cancel</button></div>
    <TaskBox title={TITLE[kind]} icon="link">
      <div className="as-grid">
        <label>Linked object</label>
        {/* linkedObjectButton ("Select Object", a pick in the 3D view): the project's parts to choose from here */}
        <QComboBox data-qf="linkedObjectButton" value={part} disabled={!!edit} onChange={(e) => setPart(e.target.value)}>
          {parts.map((p) => <option key={p} value={p}>{p}</option>)}
        </QComboBox>
      </div>
      <div data-qf="parametersWidgetPlaceholder">
        {kind === 'LinkArrayCircular'
          ? <CircularFields props={props} set={(p) => setProps((o) => ({ ...o, ...p }))} />
          : <TransformFields doc={NO_DOC} f={f} sketch={undefined} set={(p) => setProps((o) => ({ ...o, ...p }))} picking={null} setPicking={() => {}} />}
      </div>
    </TaskBox>
  </div>
}

/** PatternCircularParametersWidget.ui: Axis, Radial distance, Tangential distance, Concentric circles (from 2), Symmetry (from 1). */
function CircularFields({ props, set }: { props: Record<string, unknown>; set(p: Record<string, unknown>): void }) {
  const int = (k: string, min: number, name: string) => <input className="pdx-int" data-qf={name} type="number" min={min} step={1} value={Number(props[k])}
    onChange={(e) => { const n = Math.round(Number(e.target.value)); if (Number.isFinite(n) && n >= min) set({ [k]: n }) }} />
  return <fieldset className="tgroup"><legend>Circular Pattern</legend>
    <label className="tfield"><span>Axis</span>
      <QComboBox data-qf="axisCombo" value={String(props.axis ?? 'Z_Axis')} onChange={(e) => set({ axis: e.target.value === 'Z_Axis' ? null : e.target.value })}>
        <option value="X_Axis">Base X-axis</option><option value="Y_Axis">Base Y-axis</option><option value="Z_Axis">Base Z-axis</option>
      </QComboBox></label>
    <label className="tfield"><span>Radial distance</span><QuantityBox value={Number(props.radial_distance)} dims={LENGTH} onChange={(x) => set({ radial_distance: x })} /></label>
    <label className="tfield"><span>Tangential distance</span><QuantityBox value={Number(props.tangential_distance)} dims={LENGTH} onChange={(x) => set({ tangential_distance: x })} /></label>
    <label className="tfield"><span>Concentric circles</span>{int('number_circles', 2, 'numberCircles')}</label>
    <label className="tfield"><span>Symmetry</span>{int('symmetry', 1, 'symmetry')}</label>
  </fieldset>
}
