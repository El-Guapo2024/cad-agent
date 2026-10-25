// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/TaskExtrudeParameters.cpp: 2021 Werner Mayer (setSelectionMode, onSelectionChanged, selectedFace,
//     selectedShape, selectedShapeFace, selectedReferenceAxis, onAllFacesToggled, fillDirectionCombo, setDirectionMode,
//     handleLineFaceNameClick/No, updateShapeName, updateShapeFaces)
//   src/Mod/PartDesign/Gui/TaskSketchBasedParameters.cpp: 2013 Jan Rheinländer (onAddSelection)
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskPadPocketParameters.ui
// The 3D picks of Pad's and Pocket's task panel (partdesign.tsx's ExtrudeTask): Up to face's Select Face, Up to shape's
// Select Shape, "Select all faces" and the faces' Select, and Direction/edge's Select reference… with the custom direction,
// each a selection mode of TaskExtrudeParameters through pd_pick.tsx's gate.
import { useState } from 'react'
import { getState, type FeatureDoc } from './store'
import { cls } from './panels'
import { QComboBox } from './combo'
import { axisRefText, refText, useRefPick, type Allow, type Picked, type Ref } from './pd_pick'

/** TaskExtrudeParameters::SelectionMode. */
export type ExtrudeSel = { mode: 'face' | 'shape' | 'shapeFaces' | 'axis'; side: 1 | 2 } | null
/** What the panel holds of the references, as the part file writes them. */
export type ExtrudeRefs = {
  up_to_face: Ref | null; up_to_face2: Ref | null; up_to_shape: Ref[]; up_to_shape2: Ref[]; all_faces: boolean; all_faces2: boolean
  reference_axis: Ref | null; use_custom_vector: boolean; direction: [number, number, number]; along_sketch_normal: boolean
  /** The panel's session: the references picked for Direction/edge (each stays in the combo, addAxisToCombo) and the
   *  direction the current one gives (FeatureExtrude's Direction after the recompute), for the greyed X, Y, Z. */
  axis_items: Ref[]; axis_dir: [number, number, number] | null
}
/** Select Shape's gate: setSelectionMode adds "SELECT Part::Feature COUNT 1" after ReferenceSelection(WHOLE), and the second
 *  gate replaces the first, so any element of a feature (or a PartDesign datum, a Part::Feature) names the shape. */
const partFeature = (p: Picked) => p.kind === 'element' || p.type.startsWith('PartDesign::')
const ALLOW: Record<NonNullable<ExtrudeSel>['mode'], Allow | ((p: Picked) => boolean)> = {
  face: { face: true }, shape: partFeature, shapeFaces: { face: true }, axis: { edge: true, planar: true, circle: true },
}

/** The selection modes' picks (TaskExtrudeParameters::onSelectionChanged). */
export function useExtrudePick(part: string, feature: string | null, sel: ExtrudeSel, setSel: (s: ExtrudeSel) => void,
  refs: ExtrudeRefs, set: (p: Partial<ExtrudeRefs>) => void, normal: [number, number, number] = [0, 0, 1]) {
  useRefPick(sel !== null, {
    part, feature, allow: sel ? ALLOW[sel.mode] : {},
    onPick: (p: Picked) => {
      if (!sel) return
      const two = sel.side === 2
      if (sel.mode === 'face') {
        // selectedFace / onAddSelection: a datum by itself (an LCS's feature as the LCS and its name), else (feature, FaceN)
        set(two ? { up_to_face2: p.ref } : { up_to_face: p.ref })
        setSel(null)
      } else if (sel.mode === 'shape') {
        // selectedShape: the object picked, whole (its sub-element dropped), "Select all faces" on
        set(two ? { up_to_shape2: [p.obj], all_faces2: true } : { up_to_shape: [p.obj], all_faces: true })
        setSel(null)
      } else if (sel.mode === 'shapeFaces') {
        // selectedShapeFace: a face of the shape (the feature's own when there is none) toggles in the list
        const list = two ? refs.up_to_shape2 : refs.up_to_shape
        const owner = shapeOwner(list) ?? feature ?? ''
        if (p.kind !== 'element' || p.obj !== owner || !p.sub) return
        const faces = shapeFaces(list)
        const next = faces.includes(p.sub) ? faces.filter((f) => f !== p.sub) : [...faces, p.sub]
        const v: Ref[] = next.length ? next.map((f) => [owner, f] as [string, string]) : [owner]
        set(two ? { up_to_shape2: v } : { up_to_shape: v })
      } else if (sel.mode === 'axis') {
        // selectedReferenceAxis: getReferencedSelection (a datum with no sub-element); the combo keeps every link picked
        const items = refs.axis_items.some((r) => JSON.stringify(r) === JSON.stringify(p.ref)) ? refs.axis_items : [...refs.axis_items, p.ref]
        // a reference in the sketch's plane fails the recompute ("Axis must not be parallel to the sketch plane"): the
        // Direction FreeCAD shows stays the one it had
        const inPlane = p.dir && Math.abs(p.dir[0] * normal[0] + p.dir[1] * normal[1] + p.dir[2] * normal[2]) < 1e-7
        set({ reference_axis: p.ref, use_custom_vector: false, axis_items: items, axis_dir: inPlane ? refs.axis_dir : p.dir ?? null })
        setSel(null)
      }
    },
  })
}
/** An UpToShape as the part file has it ("Pad", ["Pad"], [["Pad", ["Face3", "Face6"]]]) as one reference per face. */
export function shapeFromDoc(v: unknown): Ref[] {
  if (v == null) return []
  const list = typeof v === 'string' ? [v] : Array.isArray(v) && v.length === 2 && typeof v[0] === 'string' && Array.isArray(v[1]) ? [v] : (v as unknown[])
  const out: Ref[] = []
  for (const r of list) {
    if (typeof r === 'string') { out.push(r); continue }
    const [o, subs] = r as [string, string | string[]]
    for (const s of typeof subs === 'string' ? [subs] : subs) out.push([o, s])
  }
  return out
}
/** And back, as PropertyLinkSubList keeps it: the object with its faces. */
export function shapeToDoc(list: Ref[]): unknown {
  const owner = shapeOwner(list)
  if (!owner) return null
  const faces = shapeFaces(list)
  return faces.length ? [[owner, faces]] : [owner]
}
/** The object an UpToShape names, and its faces (getShapeFaces: the sub-elements that are faces). */
export const shapeOwner = (list: Ref[]) => (list.length ? (typeof list[0] === 'string' ? list[0] : list[0][0]) : null)
export const shapeFaces = (list: Ref[]) => list.filter((r): r is [string, string] => Array.isArray(r) && r[1].startsWith('Face')).map((r) => r[1])

/** Up to face's row: lineFaceName and Select Face (handleLineFaceNameClick: "Face selection active" while it selects). */
export function FaceRow({ doc, value, side, sel, setSel }: { doc: FeatureDoc; value: Ref | null; side: 1 | 2; sel: ExtrudeSel; setSel(s: ExtrudeSel): void }) {
  const on = sel?.mode === 'face' && sel.side === side
  return <div className="tfield pd-pickrow">
    <input readOnly data-qf={side === 2 ? 'lineFaceName2' : 'lineFaceName'} value={refText(doc, value)} placeholder={on ? 'Face selection active' : 'No face selected'} />
    <button className={cls('qbtn', on && 'on')} aria-pressed={on} data-qf={side === 2 ? 'buttonFace2' : 'buttonFace'} onClick={() => setSel(on ? null : { mode: 'face', side })}>Select Face</button>
  </div>
}

/** Up to shape's rows (upToShapeList): the shape's name and Select Shape, "Select all faces", and with it off the faces' list
 *  and its Select (upToShapeFaces). */
export function ShapeRows({ list, allFaces, side, sel, setSel, set, feature }: { list: Ref[]; allFaces: boolean; side: 1 | 2; sel: ExtrudeSel; setSel(s: ExtrudeSel): void
  set(p: Partial<ExtrudeRefs>): void; feature: string | null }) {
  const two = side === 2, owner = shapeOwner(list)
  const shapeOn = sel?.mode === 'shape' && sel.side === side, facesOn = sel?.mode === 'shapeFaces' && sel.side === side
  const faces = shapeFaces(list)
  const [cur, setCur] = useState<string[]>([])
  // the .ui's "Select"; onSelectShapeFacesToggle makes it "Preview" while selecting and "Select Faces" after
  const [toggled, setToggled] = useState(false)
  // upToShapeFaces: shown at first whatever "Select all faces" says (setupDialog checks it before the toggle is connected);
  // onAllFacesToggled shows it when the box goes off and hides it when it comes on
  const [facesShown, setFacesShown] = useState(true)
  const slug = getState().slug ?? 'Unnamed'
  const remove = () => {
    // onUnselectShapeFacesTrigger: the selected rows out of the list
    const next = faces.filter((f) => !cur.includes(f)), o = owner ?? feature ?? ''
    set(two ? { up_to_shape2: next.length ? next.map((f) => [o, f] as [string, string]) : o ? [o] : [] } : { up_to_shape: next.length ? next.map((f) => [o, f] as [string, string]) : o ? [o] : [] })
    setCur([])
  }
  return <div className="pd-shape">
    <div className="tfield pd-pickrow">
      <input readOnly data-qf={two ? 'lineShapeName2' : 'lineShapeName'} value={shapeOn ? '' : owner ? `${slug}#${owner}` : ''}
        placeholder={shapeOn ? 'Click on a shape in the model' : 'No shape selected'} />
      <button className={cls('qbtn', shapeOn && 'on')} aria-pressed={shapeOn} data-qf={two ? 'buttonShape2' : 'buttonShape'} onClick={() => setSel(shapeOn ? null : { mode: 'shape', side })}>Select Shape</button>
    </div>
    <label className="tcheck" title="Selects all faces of the shape"><input type="checkbox" data-qf={two ? 'checkBoxAllFaces2' : 'checkBoxAllFaces'} checked={allFaces}
      onChange={(e) => {
        // onAllFacesToggled: the faces' box shows when it is off; on again, UpToShape is the shape alone
        const v = e.target.checked
        if (facesOn) setSel(null)
        if (v && owner) set(two ? { up_to_shape2: [owner], all_faces2: true } : { up_to_shape: [owner], all_faces: true })
        else set(two ? { all_faces2: v } : { all_faces: v })
        setFacesShown(!v)
      }} /> Select all faces</label>
    {facesShown && <div className="pd-shapefaces">
      <button className={cls('qbtn', facesOn && 'on')} aria-pressed={facesOn} data-qf={two ? 'buttonShapeFace2' : 'buttonShapeFace'} title="Toggles between selection and preview mode"
        onClick={() => { setToggled(true); setSel(facesOn ? null : { mode: 'shapeFaces', side }) }}>{facesOn ? 'Preview' : toggled ? 'Select Faces' : 'Select'}</button>
      <div className="pd-reflist" role="listbox" tabIndex={0} data-qf={two ? 'listWidgetReferences2' : 'listWidgetReferences'}
        onKeyDown={(e) => { if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); remove() } }}>
        {faces.map((f) => <div key={f} role="option" aria-selected={cur.includes(f)} className={cls('pd-mode', cur.includes(f) && 'sel')}
          onClick={(e) => setCur((c) => (e.ctrlKey || e.metaKey ? (c.includes(f) ? c.filter((x) => x !== f) : [...c, f]) : [f]))}>{f}</div>)}
      </div>
    </div>}
  </div>
}

/** The Direction group (fillDirectionCombo, setDirectionMode): Sketch normal, Select reference…, Custom direction and the
 *  reference picked (getRefStr); the custom vector's X, Y, Z (shown but greyed for a reference) and "Length along sketch
 *  normal" (hidden for the sketch normal). */
export function DirectionGroup({ doc, refs, set, sel, setSel, normal }: { doc: FeatureDoc; refs: ExtrudeRefs; set(p: Partial<ExtrudeRefs>): void
  sel: ExtrudeSel; setSel(s: ExtrudeSel): void; normal: [number, number, number] }) {
  const picking = sel?.mode === 'axis'
  const r = refs.reference_axis
  // fillDirectionCombo: Sketch normal, Select reference…, Custom direction, then each link picked (getRefStr's text)
  const items = r && !refs.axis_items.some((x) => JSON.stringify(x) === JSON.stringify(r)) ? [...refs.axis_items, r] : refs.axis_items
  const at = r ? items.findIndex((x) => JSON.stringify(x) === JSON.stringify(r)) : -1
  const current = picking ? 'select' : refs.use_custom_vector ? 'custom' : at >= 0 ? `ref${at}` : 'normal'
  const shown = current !== 'normal'
  const vec = refs.use_custom_vector ? refs.direction : r && refs.axis_dir ? refs.axis_dir : normal
  return <fieldset className="tgroup"><legend>Direction</legend>
    <label className="tfield" title={'Set a direction or select an edge\nfrom the model as reference'}><span>Direction/edge</span>
      <QComboBox data-qf="directionCB" value={current} onChange={(e) => {
        const k = e.target.value
        if (k === 'normal') { setSel(null); set({ reference_axis: null, use_custom_vector: false }) }
        else if (k === 'select') setSel({ mode: 'axis', side: 1 })
        else if (k === 'custom') { setSel(null); set({ use_custom_vector: true, reference_axis: null, direction: refs.use_custom_vector ? refs.direction : vec }) }
        else { setSel(null); set({ reference_axis: items[Number(k.slice(3))], use_custom_vector: false }) }
      }}>
        <option value="normal">Sketch normal</option><option value="select">Select reference…</option><option value="custom">Custom direction</option>
        {items.map((x, i) => <option key={i} value={`ref${i}`}>{axisRefText(doc, x)}</option>)}
      </QComboBox></label>
    {shown && <div className="pd-vector" data-qf="groupBoxDirection" title={'Use custom vector for pad direction, otherwise\nthe sketch plane\'s normal vector will be used'}>
      {(['X', 'Y', 'Z'] as const).map((a, i) => <label key={a} className="tfield"><span>{a}</span>
        <input type="number" step={0.1} min={-100} max={100} disabled={!refs.use_custom_vector} data-qf={`${a}DirectionEdit`} value={Number(vec[i].toFixed(6))}
          title={`${a}-component of direction vector`}
          onChange={(e) => { const d = [...refs.direction] as [number, number, number]; d[i] = Number(e.target.value); set({ direction: d }) }} /></label>)}
    </div>}
    {shown && <label className="tcheck" title={'If unchecked, the length will be\nmeasured along the specified direction'}><input type="checkbox" data-qf="checkBoxAlongDirection" checked={refs.along_sketch_normal}
      onChange={(e) => set({ along_sketch_normal: e.target.checked })} /> Length along sketch normal</label>}
  </fieldset>
}
