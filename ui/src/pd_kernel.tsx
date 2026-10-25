// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/PartDesign/Gui/TaskExtrudeParameters.cpp: 2021 Werner Mayer (updateStartUI, onStartModeChanged,
//     onSelectStartReferenceToggle, updateSideUI's taper rows, setupOperation's Operation combo)
//   src/Mod/PartDesign/Gui/TaskSketchBasedParameters.cpp: 2013 Jan Rheinländer (updateReferenceName)
//   src/Mod/PartDesign/App/FeatureExtrude.cpp: 2020 Werner Mayer (updateProperties: which taper is read-only)
//   No copyright line in the file: src/Mod/PartDesign/Gui/TaskPadPocketParameters.ui
// The task-panel rows and property-view rules of PartDesign's kernel behaviour in cad_agent (feature_taper.py,
// feature_startref.py, the subtractive features' Operation): the Taper angle boxes, the Start group's Reference row with
// Pick Reference, and the Operation combo of a Pocket, Groove or Hole. partdesign.tsx and pd_revolve.tsx place them.
import { useState } from 'react'
import { type Feature } from './store'
import { QuantityBox, ANGLE } from './qsb'
import { QComboBox } from './combo'
import { useRefPick } from './pd_pick'

/** A start reference as the part file holds it: an origin plane or a sketch by name, or [feature, "FaceN"]. */
export type StartRef = string | [string, string] | null
/** TaskSketchBasedParameters::updateReferenceName: the object's label, then ":Face6" (or ":sub"). */
export function startRefText(r: StartRef | undefined): string {
  if (r == null) return ''
  if (typeof r === 'string') return r
  const [obj, sub] = r
  return sub.startsWith('Face') ? `${obj}:Face${sub.slice(4)}` : sub ? `${obj}:${sub}` : obj
}
/** The property view's text for it (PropertyLinkSub's "Pad [Face6]"). */
export function startRefProp(r: StartRef | undefined): string {
  if (r == null) return ''
  return typeof r === 'string' ? r : r[1] ? `${r[0]} [${r[1]}]` : r[0]
}
/** FeatureExtrude::maxAngle, TaperAngle's constraint {-maxAngle, maxAngle}. */
export const MAX_TAPER = 90 - (1e-12 * 180) / Math.PI

/** The Start group's Reference row (labelStartReference, lineStartReference read-only, buttonStartReference): Pick Reference
 *  toggles to Cancel, and the next face, plane or sketch picked in the 3D view or the tree is the reference. The line shows
 *  "No start reference selected", or "Select face, plane..." while picking. onStartModeChanged starts picking when the mode
 *  turns to Reference with no reference yet. */
export function StartReferenceRow({ part, value, onChange, self }: { part: string; value: StartRef; onChange(r: StartRef): void; self?: string }) {
  const [picking, setPicking] = useState(value === null)
  // onSelectReference(AllowSelection::FACE) through the shared picker (pd_pick.tsx): the base shown in the Body's place and its
  // faces, datum planes, an LCS's planes, the Origin's (from the tree); edges and lines refused by the gate
  useRefPick(picking, { part, feature: self ?? null, allow: { face: true }, onPick: (p) => { onChange(p.ref); setPicking(false) } })
  return <>
    <div className="tfield"><span>Reference</span>
      <input readOnly data-qf="lineStartReference" value={startRefText(value)}
        placeholder={picking ? 'Select face, plane...' : 'No start reference selected'} /></div>
    <div className="tfield"><span /><button className="qbtn" data-qf="buttonStartReference" onClick={() => setPicking(!picking)}>
      {picking ? 'Cancel' : 'Pick Reference'}</button></div>
  </>
}

/** Taper angle (taperEdit, taperEdit2): degrees within TaperAngle's constraint. */
export function TaperRow({ value, onChange, name }: { value: number; onChange(v: number): void; name: string }) {
  return <label className="tfield" title="Angle to taper the extrusion"><span>Taper angle</span>
    <span className="pdk-box" data-qf={name}><QuantityBox value={value} dims={ANGLE} min={-MAX_TAPER} max={MAX_TAPER} onChange={(x) => onChange(x)} /></span></label>
}

/** setupOperation: a subtractive feature's Operation combo (FeatureAddSub::defineSubtractive's enums). */
export function OperationRow({ value, onChange }: { value: string; onChange(v: string): void }) {
  return <label className="tfield"><span>Operation</span><QComboBox data-qf="comboOperation" value={value} onChange={(e) => onChange(e.target.value)}>
    <option>Subtraction</option><option>Common</option></QComboBox></label>
}

/** FeatureExtrude::updateProperties: TaperAngle is read-only unless Side 1's type is Length or Through all, TaperAngle2
 *  unless the Side Type is Two sides and Side 2's type is one of them. */
export function taperReadOnly(f: Feature, which: 1 | 2, sideType: string, type1: string): string | null {
  const ok = (t: string) => t === 'Length' || t === 'ThroughAll'
  if (which === 1) return ok(type1) ? null : 'only for a Length or Through all type'
  if (sideType !== 'Two sides') return 'Side Type is not Two sides'
  return ok(String(f.type2 ?? 'Length')) ? null : 'only for a Length or Through all type'
}
