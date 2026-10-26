// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/Gui/DlgPrimitives.cpp: 2007 Werner Mayer
//   src/Mod/Part/Gui/DlgExtrusion.cpp: 2008 Werner Mayer
//   src/Mod/Part/Gui/DlgRevolution.cpp: 2009 Werner Mayer
//   src/Mod/Part/Gui/Mirroring.cpp: 2007 Werner Mayer
//   src/Mod/Part/Gui/DlgFilletEdges.cpp: 2008 Werner Mayer
//   src/Mod/Part/Gui/TaskLoft.cpp: 2011 Werner Mayer
//   src/Mod/Part/Gui/TaskSweep.cpp: 2011 Werner Mayer
//   src/Mod/Part/Gui/TaskOffset.cpp: 2012 Werner Mayer
//   src/Mod/Part/Gui/TaskThickness.cpp: 2012 Werner Mayer
//   src/Mod/Part/Gui/DlgBooleanOperation.cpp: 2007 Werner Mayer
//   src/Mod/Part/Gui/DlgProjectionOnSurface.cpp: 2019 Manuel Apeltauer, direkt cnc-systeme GmbH
//   src/Mod/Part/Gui/DlgScale.cpp: 2023 Wanderer Fan
//   src/Mod/Part/BasicShapes/CommandShapes.py: 2020 Werner Mayer
//   src/Mod/Sketcher/Gui/SketchOrientationDialog.cpp: 2011 Jürgen Riegel
//   No copyright line in the file: src/Mod/Part/Gui/DlgPrimitives.ui, src/Mod/Part/Gui/Location.ui, src/Mod/Part/BasicShapes/TaskTube.ui,
//       src/Mod/Part/Gui/DlgExtrusion.ui, src/Mod/Part/Gui/DlgRevolution.ui, src/Mod/Part/Gui/Mirroring.ui,
//       src/Mod/Part/Gui/DlgFilletEdges.ui, src/Mod/Part/Gui/TaskLoft.ui, src/Mod/Part/Gui/TaskSweep.ui,
//       src/Mod/Part/Gui/TaskOffset.ui, src/Mod/Part/Gui/DlgBooleanOperation.ui, src/Mod/Part/Gui/DlgProjectionOnSurface.ui,
//       src/Mod/Part/Gui/DlgScale.ui, src/Mod/Sketcher/Gui/SketchOrientationDialog.ui
// The Part workbench's task panels, each laid out as its .ui lays out the dialog, with the dialog's own defaults (the
// values FreeCAD's dialog starts from, ui/scripts/fcpart.json, which are not always the property's: the Primitives dialog
// starts a Plane at 10 mm, a Line at (10, 10, 10)). OK (or Create, Apply) writes the object as the dialog's Python does, in
// its transaction; Cancel and Close write nothing. The objects a list offers are those its dialog lists (DlgExtrusion's
// canExtrude, TaskLoft's profiles, DlgFilletEdges' solids), told apart here by their type.
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import type { FeatureOp } from './api'
import { getState, report, useStore, type Feature, type FeatureDoc } from './store'
import { closeTask, editSketch } from './actions'
import { Icon, type IconName } from './icons'
import { cls, TaskBox } from './panels'
import { QuantityBox, LENGTH, ANGLE, NUMBER } from './qsb'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import { applyOps, numberOf, refOf, SKETCH } from './partdesign'
import { addObject, labelOf, objectOf, partIcon, selectedObjects, setObjectPicker, uniqueLabel, uniqueName } from './part_wb'
import { parsePartPick, partMesh, usePartScene, type Mesh } from './part_pick'
import './part_tasks.css'

// ── pieces ───────────────────────────────────────────────────────────────────────────────────────────────────────
function Buttons({ items }: { items: [string, () => void, boolean?][] }) {
  return <div className="tbuttons pd-buttons">{items.map(([t, f, def]) => <button key={t} className={cls('qbtn', def && 'default')} onClick={f}>{t}</button>)}</div>
}
function Field({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return <label className="tfield" title={title}><span>{label}</span>{children}</label>
}
function Check({ label, checked, onChange, disabled, name }: { label: string; checked: boolean; onChange(v: boolean): void; disabled?: boolean; name?: string }) {
  return <label className="tcheck" data-qf={name}><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} /> {label}</label>
}
function Radio({ label, checked, onChange, name }: { label: string; checked: boolean; onChange(): void; name?: string }) {
  return <label className="tcheck" data-qf={name}><input type="radio" checked={checked} onChange={onChange} /> {label}</label>
}
function Legend({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="tgroup"><legend>{title}</legend>{children}</fieldset>
}
/** A Gui::QuantitySpinBox of the dialog: a length, an angle, or a plain number. */
function Q({ label, value, dims = LENGTH, onChange, min, max, disabled, name, step, decimals }: { label?: string; value: number; dims?: number[]; onChange(v: number): void
  min?: number; max?: number; disabled?: boolean; name?: string; step?: number; decimals?: number }) {
  const box = <span data-qf={name}><QuantityBox key={`${name}:${value}`} value={value} dims={dims as typeof LENGTH} min={min} max={max} step={step} disabled={disabled} decimals={decimals} onChange={onChange} /></span>
  return label ? <Field label={label}>{box}</Field> : box
}
/** A QTreeWidget of objects, by Label with their icons; click picks one (or toggles one, multi). */
function ObjList({ doc, names, picked, onPick, header, multi, name }: { doc: FeatureDoc; names: string[]; picked: string[]; onPick(next: string[]): void
  header?: string; multi?: boolean; name?: string }) {
  return (
    <div className="pt-list" data-qf={name}>
      {header && <div className="pt-list-head">{header}</div>}
      {names.map((n) => {
        const o = objectOf(doc, n) ?? doc.features?.find((f) => f.name === n)
        const on = picked.includes(n)
        return <div key={n} className={cls('pt-item', on && 'sel')} onClick={() => onPick(multi ? (on ? picked.filter((x) => x !== n) : [...picked, n]) : [n])}>
          <Icon name={o ? partIcon(o.type) : 'part'} size={14} /> {o ? labelOf(o) : n}</div>
      })}
    </div>
  )
}
const num = (doc: FeatureDoc | undefined, v: unknown, d: number) => numberOf(v, doc?.params ?? {}) ?? d
const r2 = (x: number) => Math.round(x * 100) / 100       // Base::UnitsApi::getDecimals(): what the dialogs' Python strings carry
const nearly = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

// what each dialog lists, by type (the shapes their filters take)
const FLAT = new Set([SKETCH, 'Part::Plane', 'Part::Helix', 'Part::Spiral', 'Part::Circle', 'Part::Ellipse', 'Part::Vertex', 'Part::Line',
  'Part::RegularPolygon', 'Part::Polygon', 'Part::Section', 'Part::Offset2D', 'Part::ProjectOnSurface'])
const SOLIDS = new Set(['Part::Box', 'Part::Cylinder', 'Part::Sphere', 'Part::Cone', 'Part::Torus', 'Part::Tube', 'Part::Prism', 'Part::Wedge', 'Part::Ellipsoid',
  'Part::Cut', 'Part::Fuse', 'Part::MultiFuse', 'Part::Common', 'Part::MultiCommon', 'Part::Fillet', 'Part::Chamfer', 'Part::Refine', 'Part::Mirroring',
  'Part::Offset', 'Part::Thickness', 'Part::Compound', 'Part::BooleanFragments', 'Part::Slice', 'Part::XOR', 'Part::Connect', 'Part::Embed', 'Part::Cutout',
  'Part::CompoundFilter'])
const isFlat = (o: Feature) => FLAT.has(o.type) || ((o.type === 'Part::Extrusion' || o.type === 'Part::Revolution' || o.type === 'Part::Loft' || o.type === 'Part::Sweep') && o.solid === false)
const isSolid = (o: Feature) => SOLIDS.has(o.type) || ((o.type === 'Part::Extrusion' || o.type === 'Part::Revolution' || o.type === 'Part::Loft' || o.type === 'Part::Sweep') && o.solid !== false)
const names = (doc: FeatureDoc, keep: (o: Feature) => boolean, except?: string) => (doc.objects ?? []).filter((o) => o.name !== except && keep(o)).map((o) => o.name)

/** The Location panel (Location.ui): Position X, Y, Z; Rotation Axis X, Y, Z and Angle. */
type Loc = { pos: [number, number, number]; axis: [number, number, number]; angle: number }
function locOf(pl: unknown): Loc {
  const [pos, ypr] = Array.isArray(pl) ? (pl as number[][]) : [[0, 0, 0], [0, 0, 0]]
  const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(THREE.MathUtils.degToRad(ypr[2]), THREE.MathUtils.degToRad(ypr[1]), THREE.MathUtils.degToRad(ypr[0]), 'ZYX'))
  const angle = 2 * Math.acos(Math.min(1, Math.abs(q.w))), s = Math.sqrt(Math.max(0, 1 - q.w * q.w)) * Math.sign(q.w || 1)
  return { pos: [pos[0], pos[1], pos[2]], axis: s < 1e-9 ? [0, 0, 1] : [q.x / s, q.y / s, q.z / s], angle: THREE.MathUtils.radToDeg(angle) }
}
/** Location::toPlacement's App.Placement(App.Vector(x, y, z), App.Rotation(App.Vector(axis), angle)), with the decimals
 *  the Python string carries, as the part file's ((x, y, z), (yaw, pitch, roll)); null for the identity. */
function placementOf(l: Loc): unknown {
  const axis = new THREE.Vector3(...l.axis.map(r2))
  const q = axis.lengthSq() > 0 ? new THREE.Quaternion().setFromAxisAngle(axis.normalize(), THREE.MathUtils.degToRad(r2(l.angle))) : new THREE.Quaternion()
  const e = new THREE.Euler().setFromQuaternion(q, 'ZYX')
  const r9 = (x: number) => Math.round(x * 1e9) / 1e9 + 0
  const ypr = [THREE.MathUtils.radToDeg(e.z), THREE.MathUtils.radToDeg(e.y), THREE.MathUtils.radToDeg(e.x)].map(r9)
  const pos = l.pos.map(r2)
  return pos.every((x) => x === 0) && ypr.every((x) => x === 0) ? null : [pos, ypr]
}
function LocationBox({ loc, set }: { loc: Loc; set(l: Loc): void }) {
  return (
    <TaskBox title="Location" icon="placement">
      <Legend title="Position">
        {(['X', 'Y', 'Z'] as const).map((a, i) => <Q key={a} label={a} name={`${a}PositionQSB`} value={loc.pos[i]} onChange={(v) => { const p = [...loc.pos] as Loc['pos']; p[i] = v; set({ ...loc, pos: p }) }} />)}
        <button className="qbtn" disabled title="Picks a point in the 3D view: not in this view yet">Pick Position</button>
      </Legend>
      <Legend title="Rotation Axis">
        {(['X', 'Y', 'Z'] as const).map((a, i) => <Q key={a} label={a} name={`${a}DirectionEdit`} dims={NUMBER} value={loc.axis[i]} onChange={(v) => { const p = [...loc.axis] as Loc['axis']; p[i] = v; set({ ...loc, axis: p }) }} />)}
        <Q label="Angle" name="AngleQSB" dims={ANGLE} value={loc.angle} onChange={(v) => set({ ...loc, angle: v })} />
      </Legend>
    </TaskBox>
  )
}

// ── Primitives (DlgPrimitives: the type list, each type's Parameter page with the dialog's defaults) ───────────────────
type PField = [string, string, number[], number, number?, number?]   // label, property, dims, dialog default, min, max
type PType = { item: string; type: string; base: string; label: string; icon: IconName; fields: PField[]; combo?: [string, string, string[]] }
const L = LENGTH, A = ANGLE, N = NUMBER
/** DlgPrimitives.ui's pages in the combo's order, labels as it has them, with the values the dialog starts from. */
export const PRIMITIVE_PAGES: PType[] = [
  { item: 'Plane', type: 'Part::Plane', base: 'Plane', label: 'Plane', icon: 'pt-plane', fields: [['Length', 'length', L, 10, 0], ['Width', 'width', L, 10, 0]] },
  { item: 'Box', type: 'Part::Box', base: 'Box', label: 'Box', icon: 'pt-box', fields: [['Length', 'length', L, 10, 0], ['Width', 'width', L, 10, 0], ['Height', 'height', L, 10, 0]] },
  { item: 'Cylinder', type: 'Part::Cylinder', base: 'Cylinder', label: 'Cylinder', icon: 'pt-cylinder', fields: [['Radius', 'radius', L, 2, 0], ['Height', 'height', L, 10, 0],
    ['Angle in first direction', 'first_angle', A, 0, -89.99999, 89.99999], ['Angle in second direction', 'second_angle', A, 0, -89.99999, 89.99999], ['Rotation angle', 'angle', A, 360, 0, 360]] },
  { item: 'Cone', type: 'Part::Cone', base: 'Cone', label: 'Cone', icon: 'pt-cone', fields: [['Radius 1', 'radius1', L, 2, 0], ['Radius 2', 'radius2', L, 4, 0], ['Height', 'height', L, 10, 0], ['Angle', 'angle', A, 360, 0, 360]] },
  { item: 'Sphere', type: 'Part::Sphere', base: 'Sphere', label: 'Sphere', icon: 'pt-sphere', fields: [['Radius', 'radius', L, 5, 0], ['U parameter', 'angle3', A, 360, 0, 360],
    ['V parameters', 'angle1', A, -90, -90, 90], ['', 'angle2', A, 90, -90, 90]] },
  { item: 'Ellipsoid', type: 'Part::Ellipsoid', base: 'Ellipsoid', label: 'Ellipsoid', icon: 'pt-ellipsoid', fields: [['Radius 1', 'radius1', L, 2, 0], ['Radius 2', 'radius2', L, 4, 0],
    ['Radius 3', 'radius3', L, 4, 0], ['U parameter', 'angle3', A, 360, 0, 360], ['V parameter', 'angle1', A, -90, -90, 90], ['', 'angle2', A, 90, -90, 90]] },
  { item: 'Torus', type: 'Part::Torus', base: 'Torus', label: 'Torus', icon: 'pt-torus', fields: [['Radius 1', 'radius1', L, 10, 0], ['Radius 2', 'radius2', L, 2, 0],
    ['U parameter', 'angle3', A, 360, 0, 360], ['V parameter', 'angle1', A, -180, -180, 180], ['', 'angle2', A, 180, -180, 180]] },
  { item: 'Prism', type: 'Part::Prism', base: 'Prism', label: 'Prism', icon: 'pt-prism', fields: [['Polygon', 'polygon', N, 6, 3], ['Circumradius', 'circumradius', L, 2, 0], ['Height', 'height', L, 10, 0],
    ['Angle in first direction', 'first_angle', A, 0, -89.99999, 89.99999], ['Angle in second direction', 'second_angle', A, 0, -89.99999, 89.99999]] },
  { item: 'Wedge', type: 'Part::Wedge', base: 'Wedge', label: 'Wedge', icon: 'pt-wedge', fields: [['X min/max', 'xmin', L, 0], ['', 'xmax', L, 10], ['Y min/max', 'ymin', L, 0], ['', 'ymax', L, 10],
    ['Z min/max', 'zmin', L, 0], ['', 'zmax', L, 10], ['X2 min/max', 'x2min', L, 2], ['', 'x2max', L, 8], ['Z2 min/max', 'z2min', L, 2], ['', 'z2max', L, 8]] },
  { item: 'Helix', type: 'Part::Helix', base: 'Helix', label: 'Helix', icon: 'pt-helix', fields: [['Pitch', 'pitch', L, 1, 0], ['Height', 'height', L, 2, 0], ['Radius', 'radius', L, 1, 0], ['Angle', 'angle', A, 0, -89.9, 89.9]],
    combo: ['Coordinate system', 'local_coord', ['Right-handed', 'Left-handed']] },
  { item: 'Spiral', type: 'Part::Spiral', base: 'Spiral', label: 'Spiral', icon: 'pt-spiral', fields: [['Growth', 'growth', L, 1, 0], ['Number of rotations', 'rotations', N, 2, 0], ['Radius', 'radius', L, 1, 0]] },
  { item: 'Circle', type: 'Part::Circle', base: 'Circle', label: 'Circle', icon: 'pt-circle', fields: [['Radius', 'radius', L, 2, 0], ['Angle 1', 'angle1', A, 0, 0, 360], ['Angle 2', 'angle2', A, 360, 0, 360]] },
  { item: 'Ellipse', type: 'Part::Ellipse', base: 'Ellipse', label: 'Ellipse', icon: 'pt-ellipse', fields: [['Major radius', 'major_radius', L, 4, 0], ['Minor radius', 'minor_radius', L, 2, 0],
    ['Angle 1', 'angle1', A, 0, 0, 360], ['Angle 2', 'angle2', A, 360, 0, 360]] },
  { item: 'Point', type: 'Part::Vertex', base: 'Vertex', label: 'Vertex', icon: 'pt-point', fields: [['X', 'x', L, 0], ['Y', 'y', L, 0], ['Z', 'z', L, 0]] },
  { item: 'Line', type: 'Part::Line', base: 'Line', label: 'Line', icon: 'pt-line', fields: [['X', 'x1', L, 0], ['', 'x2', L, 10], ['Y', 'y1', L, 0], ['', 'y2', L, 10], ['Z', 'z1', L, 0], ['', 'z2', L, 10]] },
  { item: 'Regular polygon', type: 'Part::RegularPolygon', base: 'RegularPolygon', label: 'Regular polygon', icon: 'pt-polygon', fields: [['Polygon', 'polygon', N, 6, 3], ['Circumradius', 'circumradius', L, 2, 0]] },
]
/** The defaults of the part file's classes (feature_part_prim.py's DEFAULTS, FreeCAD's properties'), to leave out what equals them. */
const PROP_DEFAULT: Record<string, Record<string, unknown>> = {
  'Part::Plane': { length: 100, width: 100 }, 'Part::Box': { length: 10, width: 10, height: 10 },
  'Part::Cylinder': { radius: 2, height: 10, angle: 360, first_angle: 0, second_angle: 0 }, 'Part::Cone': { radius1: 2, radius2: 4, height: 10, angle: 360 },
  'Part::Sphere': { radius: 5, angle1: -90, angle2: 90, angle3: 360 }, 'Part::Ellipsoid': { radius1: 2, radius2: 4, radius3: 0, angle1: -90, angle2: 90, angle3: 360 },
  'Part::Torus': { radius1: 10, radius2: 2, angle1: -180, angle2: 180, angle3: 360 }, 'Part::Prism': { polygon: 6, circumradius: 2, height: 10, first_angle: 0, second_angle: 0 },
  'Part::Wedge': { xmin: 0, ymin: 0, zmin: 0, x2min: 2, z2min: 2, xmax: 10, ymax: 10, zmax: 10, x2max: 8, z2max: 8 },
  'Part::Helix': { pitch: 1, height: 2, radius: 1, angle: 0, local_coord: 'Right-handed', segment_length: 0 }, 'Part::Spiral': { growth: 1, radius: 1, rotations: 2, segment_length: 1 },
  'Part::Circle': { radius: 2, angle1: 0, angle2: 360 }, 'Part::Ellipse': { major_radius: 4, minor_radius: 4, angle1: 0, angle2: 360 },
  'Part::Vertex': { x: 0, y: 0, z: 0 }, 'Part::Line': { x1: 0, y1: 0, z1: 0, x2: 0, y2: 0, z2: 1 }, 'Part::RegularPolygon': { polygon: 6, circumradius: 2 },
  'Part::Tube': { outer_radius: 5, inner_radius: 2, height: 10 },
}
/** DlgPrimitives.ui's widget name of a property's box: the page's prefix and the property (cylinderRadius, wedgeX2min,
 *  edgeX1), its skew angles XSkew and YSkew, the Spiral's rotations spiralRotation. */
const PREFIX: Record<string, string> = { 'Part::Plane': 'plane', 'Part::Box': 'box', 'Part::Cylinder': 'cylinder', 'Part::Cone': 'cone',
  'Part::Sphere': 'sphere', 'Part::Ellipsoid': 'ellipsoid', 'Part::Torus': 'torus', 'Part::Prism': 'prism', 'Part::Wedge': 'wedge',
  'Part::Helix': 'helix', 'Part::Spiral': 'spiral', 'Part::Circle': 'circle', 'Part::Ellipse': 'ellipse', 'Part::Vertex': 'vertex',
  'Part::Line': 'edge', 'Part::RegularPolygon': 'regularPolygon' }
const widgetName = (type: string, key: string) => {
  const own: Record<string, string> = { first_angle: 'XSkew', second_angle: 'YSkew', rotations: 'Rotation', local_coord: 'LocalCS' }
  return PREFIX[type] + (own[key] ?? key.split('_').map((w) => w[0].toUpperCase() + w.slice(1)).join(''))
}
function PrimitivesTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const [page, setPage] = useState(() => Math.max(0, existing ? PRIMITIVE_PAGES.findIndex((p) => p.type === existing.type) : 0))
  const P = PRIMITIVE_PAGES[page]
  const start = (p: PType): Record<string, unknown> => Object.fromEntries([...p.fields.map(([, k, , d]) => [k, existing ? (existing[k] ?? PROP_DEFAULT[p.type][k]) : d]),
    ...(p.combo ? [[p.combo[1], existing ? (existing[p.combo[1]] ?? PROP_DEFAULT[p.type][p.combo[1]]) : p.combo[2][0]]] : [])])
  const [vals, setVals] = useState(() => start(P))
  const [loc, setLoc] = useState<Loc>(() => locOf(existing?.placement))
  useEffect(() => { if (!existing) setVals(start(P)) }, [page])
  if (!doc) return null
  const props = () => {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(vals)) {
      const d = PROP_DEFAULT[P.type][k]
      const x = typeof v === 'number' ? (k === 'polygon' ? Math.round(v) : r2(v)) : v
      if (!nearly(x, d)) out[k] = x
    }
    const pl = placementOf(loc)
    if (pl) out.placement = pl
    return out
  }
  const create = async () => {
    const name = uniqueName(getState().features[part], P.base)
    const label = uniqueLabel(getState().features[part], P.label)
    await addObject(part, { name, type: P.type, ...props(), ...(label !== name ? { label } : {}) }, `Create ${P.item}`)
  }
  const accept = async () => {   // DlgPrimitives::acceptChanges: every property set, in "Edit <item>"
    if (!existing) return
    const want = props(), changed: Record<string, unknown> = {}
    for (const k of [...Object.keys(PROP_DEFAULT[P.type]), 'placement']) {
      const v = k in want ? want[k] : (k === 'placement' ? null : PROP_DEFAULT[P.type][k])
      if (!nearly(v, existing[k] ?? (k === 'placement' ? null : PROP_DEFAULT[P.type][k]))) changed[k] = v
    }
    closeTask()
    if (Object.keys(changed).length) await applyOps(part, [{ op: 'set', name: existing.name, props: changed }], { name: `Edit ${P.item}` })
  }
  const field = ([label, k, dims, , min, max]: PField) => (
    <Q key={k} label={label} name={widgetName(P.type, k)} dims={dims} value={num(doc, vals[k], 0)} min={min} max={max} step={1} decimals={k === 'polygon' ? 0 : undefined}
      onChange={(v) => setVals((x) => ({ ...x, [k]: v }))} />)
  return (
    <div className="tasks pt-task" data-task="primitives">
      {existing ? <Buttons items={[['OK', () => void accept(), true], ['Cancel', closeTask]]} />
        : <Buttons items={[['Create', () => void create(), true], ['Close', closeTask]]} />}
      <TaskBox title="Geometric Primitives" icon={P.icon}>
        <div data-qf="PrimitiveTypeCB"><QComboBox value={String(page)} disabled={!!existing} onChange={(e) => setPage(Number(e.target.value))}>
          {PRIMITIVE_PAGES.map((p, i) => <option key={p.item} value={i}>{p.item}</option>)}</QComboBox></div>
        <Legend title="Parameter">
          {P.type === 'Part::Line' && <div className="tfield pt-line-head"><span /><span className="tlabel">Start point</span><span className="tlabel">End point</span></div>}
          {P.fields.map(field)}
          {P.combo && <Field label={P.combo[0]}><QComboBox data-qf={widgetName(P.type, P.combo[1])} value={String(vals[P.combo[1]])} onChange={(e) => setVals((x) => ({ ...x, [P.combo![1]]: e.target.value }))}>
            {P.combo[2].map((o) => <option key={o}>{o}</option>)}</QComboBox></Field>}
          {P.type === 'Part::Circle' && <button className="qbtn" disabled title="Picks three points in the 3D view: not in this view yet">From 3 Points</button>}
        </Legend>
      </TaskBox>
      <LocationBox loc={loc} set={setLoc} />
    </div>
  )
}

// ── Tube (BasicShapes' TaskTube.ui; CommandShapes.CommandTube: "Create tube") ────────────────────────────────────────────
function TubeTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const [v, setV] = useState({ outer_radius: num(doc, existing?.outer_radius, 5), inner_radius: num(doc, existing?.inner_radius, 2), height: num(doc, existing?.height, 10) })
  if (!doc) return null
  const props = () => Object.fromEntries(Object.entries(v).map(([k, x]) => [k, r2(x)]).filter(([k, x]) => x !== PROP_DEFAULT['Part::Tube'][k as string]))
  const ok = async () => {
    closeTask()
    if (existing) {
      const ch = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, r2(x)]).filter(([k, x]) => num(doc, existing[k as string], PROP_DEFAULT['Part::Tube'][k as string] as number) !== x))
      if (Object.keys(ch).length) await applyOps(part, [{ op: 'set', name: existing.name, props: ch }], { name: 'Edit tube' })
      return
    }
    await addObject(part, { name: uniqueName(getState().features[part], 'Tube'), type: 'Part::Tube', ...props() }, 'Create tube')
  }
  return (
    <div className="tasks pt-task" data-task="tube">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title="Tube" icon="pt-tube">
        <Legend title="Parameter">
          <Q label="Outer radius" name="tubeOuterRadius" value={v.outer_radius} min={0} onChange={(x) => setV({ ...v, outer_radius: x })} />
          <Q label="Inner radius" name="tubeInnerRadius" value={v.inner_radius} min={0} onChange={(x) => setV({ ...v, inner_radius: x })} />
          <Q label="Height" name="tubeHeight" value={v.height} min={0} onChange={(x) => setV({ ...v, height: x })} />
        </Legend>
      </TaskBox>
    </div>
  )
}

// ── Extrude (DlgExtrusion) ───────────────────────────────────────────────────────────────────────────────────────
function ExtrudeTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const list = doc ? names(doc, isFlat, edit) : []
  const [shapes, setShapes] = useState<string[]>(() => existing ? [String(existing.base)] : selectedObjects(part).filter((n) => list.includes(n)))
  const [mode, setMode] = useState(String(existing?.dir_mode ?? 'Normal'))
  const [dir, setDir] = useState<number[]>((existing?.dir as number[]) ?? [0, 0, 1])
  const [link, setLink] = useState<unknown>(existing?.dir_link ?? null)
  const [v, setV] = useState({ fwd: num(doc, existing?.length_fwd, existing ? 0 : 10), rev: num(doc, existing?.length_rev, 0), t1: num(doc, existing?.taper_angle, 0), t2: num(doc, existing?.taper_angle_rev, 0) })
  const [flags, setFlags] = useState({ reversed: existing?.reversed === true, symmetric: existing?.symmetric === true, solid: existing ? existing.solid === true : true })
  const [picking, setPicking] = useState(false)
  useEffect(() => { setObjectPicker(picking ? (ref) => { const n = ref.slice(part.length + 1); if (objectOf(doc, n)) { setLink([n, 'Edge1']); setMode('Edge'); setPicking(false) } } : null); return () => setObjectPicker(null) }, [picking])
  if (!doc) return null
  const props = (): Record<string, unknown> => {
    const out: Record<string, unknown> = { dir_mode: mode }
    if (mode === 'Custom') out.dir = dir.map(r2)
    if (mode === 'Edge') out.dir_link = link
    out.length_fwd = r2(v.fwd); out.length_rev = r2(v.rev); out.taper_angle = r2(v.t1); out.taper_angle_rev = r2(v.t2)
    out.solid = flags.solid; out.reversed = flags.reversed; out.symmetric = flags.symmetric
    return out
  }
  const apply = async (close: boolean) => {
    if (!shapes.length) { await messageBox('critical', 'Extrude', 'No shapes selected for extrusion. Select some, first.'); return }
    if (existing) {
      if (close) closeTask()
      await applyOps(part, [{ op: 'set', name: existing.name, props: props() }], { name: 'Edit Extrude' })
      return
    }
    // DlgExtrusion::apply: an Extrude for each shape, in one "Extrude" transaction, the shapes hidden
    let d = getState().features[part]
    const ops: FeatureOp[] = []
    for (const s of shapes) {
      const name = uniqueName(d, 'Extrude')
      ops.push({ op: 'add', feature: { name, type: 'Part::Extrusion', base: s, ...props() } })
      d = { ...d, objects: [...(d.objects ?? []), { name, type: 'Part::Extrusion' }] }
    }
    if (close) closeTask()
    await applyOps(part, ops, { name: 'Extrude' })
  }
  const axisBtn = (a: number) => () => { setMode('Custom'); setDir([0, 1, 2].map((i) => (i === a ? 1 : 0))) }
  return (
    <div className="tasks pt-task" data-task="extrude">
      <Buttons items={[['OK', () => void apply(true), true], ['Close', closeTask], ['Apply', () => void apply(false)]]} />
      <TaskBox title="Extrude" icon="pt-extrude">
        <Legend title="Direction">
          <Radio name="rbDirModeNormal" label="Along normal" checked={mode === 'Normal'} onChange={() => setMode('Normal')} />
          <Check name="chkReversed" label="Reversed" checked={flags.reversed} onChange={(x) => setFlags({ ...flags, reversed: x })} />
          <Radio name="rbDirModeEdge" label="Along edge" checked={mode === 'Edge'} onChange={() => setMode('Edge')} />
          <div className="tfield"><input className="qline" data-qf="txtLink" disabled={mode !== 'Edge'} readOnly value={link ? (Array.isArray(link) ? `${link[0]}:${link[1]}` : String(link)) : ''} />
            <button className={cls('qbtn', picking && 'on')} onClick={() => setPicking(!picking)}>{picking ? 'Cancel' : 'Select'}</button></div>
          <Radio name="rbDirModeCustom" label="Custom direction" checked={mode === 'Custom'} onChange={() => setMode('Custom')} />
          {(['X', 'Y', 'Z'] as const).map((a, i) => <div key={a} className="pt-row"><button className="qbtn" onClick={axisBtn(i)}>{a}</button>
            <Q name={`dir${a}`} dims={NUMBER} value={dir[i]} disabled={mode !== 'Custom'} onChange={(x) => { const d = [...dir]; d[i] = x; setDir(d) }} /></div>)}
        </Legend>
        <Legend title="Length">
          <Q label="Along" name="spinLenFwd" value={v.fwd} onChange={(x) => setV({ ...v, fwd: x })} />
          <Q label="Against" name="spinLenRev" value={v.rev} onChange={(x) => setV({ ...v, rev: x })} />
          <Check name="chkSymmetric" label="Symmetric" checked={flags.symmetric} onChange={(x) => setFlags({ ...flags, symmetric: x })} />
          <Q label="Taper angle along" name="spinTaperAngle" dims={ANGLE} value={v.t1} onChange={(x) => setV({ ...v, t1: x })} />
          <Q label="Taper angle against" name="spinTaperAngleRev" dims={ANGLE} value={v.t2} onChange={(x) => setV({ ...v, t2: x })} />
        </Legend>
        <Check name="chkSolid" label="Create solid" checked={flags.solid} onChange={(x) => setFlags({ ...flags, solid: x })} />
        <ObjList name="treeWidget" header="Shape" doc={doc} names={existing ? [String(existing.base)] : list} picked={shapes} onPick={setShapes} multi />
      </TaskBox>
    </div>
  )
}

// ── Revolve (DlgRevolution) ──────────────────────────────────────────────────────────────────────────────────────
function RevolveTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const list = doc ? names(doc, isFlat, edit) : []
  const [shapes, setShapes] = useState<string[]>(() => existing ? [String(existing.source)] : selectedObjects(part).filter((n) => list.includes(n)))
  const [base, setBase] = useState<number[]>((existing?.base as number[]) ?? [0, 0, 0])
  const [axis, setAxis] = useState<number[]>((existing?.axis as number[]) ?? [0, 0, 1])
  const [link, setLink] = useState<unknown>(existing?.axis_link ?? null)
  const [angle, setAngle] = useState(num(doc, existing?.angle, 360))
  const [sym, setSym] = useState(existing?.symmetric === true), [solid, setSolid] = useState(existing ? existing.solid === true : true)
  const [picking, setPicking] = useState(false)
  useEffect(() => { setObjectPicker(picking ? (ref) => { const n = ref.slice(part.length + 1); if (objectOf(doc, n)) { setLink([n, 'Edge1']); setPicking(false) } } : null); return () => setObjectPicker(null) }, [picking])
  if (!doc) return null
  const ok = async () => {
    if (!shapes.length) { await messageBox('critical', 'Revolve', 'Select a shape for revolution, first.'); return }
    const props: Record<string, unknown> = { base: base.map(r2), axis: axis.map(r2), angle: r2(angle), symmetric: sym, solid }
    if (link) props.axis_link = link
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props }], { name: 'Edit Revolve' }); return }
    let d = getState().features[part]
    const ops: FeatureOp[] = []
    for (const s of shapes) {
      const name = uniqueName(d, 'Revolve')
      ops.push({ op: 'add', feature: { name, type: 'Part::Revolution', source: s, ...props } })
      d = { ...d, objects: [...(d.objects ?? []), { name, type: 'Part::Revolution' }] }
    }
    await applyOps(part, ops, { name: 'Revolve' })
  }
  return (
    <div className="tasks pt-task" data-task="revolve">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title="Revolve" icon="pt-revolve">
        <ObjList name="treeWidget" header="Shape" doc={doc} names={existing ? [String(existing.source)] : list} picked={shapes} onPick={setShapes} multi />
        <Legend title="Revolution Axis">
          {(['X', 'Y', 'Z'] as const).map((a, i) => <Q key={a} label={`Center ${a}`} name={`${a.toLowerCase()}Pos`} value={base[i]} disabled={!!link} onChange={(x) => { const b = [...base]; b[i] = x; setBase(b) }} />)}
          {(['X', 'Y', 'Z'] as const).map((a, i) => <div key={a} className="pt-row"><Q name={`${a.toLowerCase()}Dir`} dims={NUMBER} value={axis[i]} disabled={!!link} onChange={(x) => { const d = [...axis]; d[i] = x; setAxis(d) }} />
            <button className="qbtn" onClick={() => { setLink(null); setAxis([0, 1, 2].map((j) => (j === i ? 1 : 0))) }}>{a}-Direction</button></div>)}
          <div className="tfield"><button className={cls('qbtn', picking && 'on')} onClick={() => setPicking(!picking)}>{picking ? 'Cancel' : 'Select Reference'}</button>
            <input className="qline" data-qf="txtAxisLink" readOnly value={link ? `${(link as string[])[0]}:${(link as string[])[1]}` : ''} onDoubleClick={() => setLink(null)} /></div>
        </Legend>
        <Q label="Angle" name="angle" dims={ANGLE} value={angle} min={0} max={360} onChange={setAngle} />
        <Check name="checkSymmetric" label="Symmetric angle" checked={sym} onChange={setSym} />
        <Check name="checkSolid" label="Create solid" checked={solid} onChange={setSolid} />
      </TaskBox>
    </div>
  )
}

// ── Mirror (Mirroring.ui; PartGui::Mirroring::accept: "Mirroring", the label "<Label> (Mirror #n)") ───────────────────
const PLANES: [string, number[]][] = [['XY-plane', [0, 0, 1]], ['XZ-plane', [0, 1, 0]], ['YZ-plane', [1, 0, 0]]]
function MirrorTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const list = doc ? (doc.objects ?? []).filter((o) => o.name !== edit && o.type !== SKETCH).map((o) => o.name) : []
  const [shapes, setShapes] = useState<string[]>(() => existing ? [String(existing.source)] : selectedObjects(part).filter((n) => list.includes(n)))
  const n0 = existing ? PLANES.findIndex(([, v]) => nearly(v, existing.normal ?? [0, 0, 1])) : 0
  const [plane, setPlane] = useState(existing?.mirror_plane ? 3 : Math.max(0, n0))
  const [ref, setRef] = useState<unknown>(existing?.mirror_plane ?? null)
  const [base, setBase] = useState<number[]>((existing?.base as number[]) ?? [0, 0, 0])
  const [picking, setPicking] = useState(true)
  useEffect(() => { setObjectPicker(picking ? (r) => { const n = r.slice(part.length + 1); if (objectOf(doc, n) && !shapes.includes(n)) { setRef(n); setPlane(3) } } : null); return () => setObjectPicker(null) }, [picking, shapes])
  if (!doc) return null
  const ok = async () => {
    if (!shapes.length) { await messageBox('critical', 'No shapes selected', 'Select one or more shapes to mirror first'); return }
    if (plane === 3 && !ref) { await messageBox('critical', 'Invalid reference', 'Select a valid plane, face or circle for the mirror plane'); return }
    const props: Record<string, unknown> = plane === 3 ? { mirror_plane: ref } : { normal: PLANES[plane][1], base: base.map(r2) }
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props }], { name: 'Edit Mirroring' }); return }
    let d = getState().features[part]
    const ops: FeatureOp[] = []
    let count = (d.objects ?? []).filter((o) => o.type === 'Part::Mirroring').length
    for (const s of shapes) {
      const name = uniqueName(d, 'Part__Mirroring'), src = objectOf(d, s)
      ops.push({ op: 'add', feature: { name, type: 'Part::Mirroring', source: s, ...props, label: `${src ? labelOf(src) : s} (Mirror #${++count})` } })
      d = { ...d, objects: [...(d.objects ?? []), { name, type: 'Part::Mirroring' }] }
    }
    await applyOps(part, ops, { name: 'Mirroring' })
  }
  return (
    <div className="tasks pt-task" data-task="mirror">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title="Mirror" icon="pt-mirror">
        <ObjList name="shapes" doc={doc} names={existing ? [String(existing.source)] : list} picked={shapes} onPick={setShapes} multi />
        <Field label="Mirror plane"><QComboBox value={String(plane)} onChange={(e) => setPlane(Number(e.target.value))}>
          {[...PLANES.map(([t]) => t), 'Use selected reference'].map((t, i) => <option key={t} value={i}>{t}</option>)}</QComboBox></Field>
        <div className="tfield"><input className="qline" data-qf="referenceLineEdit" readOnly value={ref ? (Array.isArray(ref) ? `${ref[0]}:${ref[1]}` : String(ref)) : ''} />
          <button className={cls('qbtn', picking && 'on')} onClick={() => setPicking(!picking)}>{picking ? 'Selecting' : 'Select reference'}</button></div>
        <Legend title="Base Point">
          {(['X', 'Y', 'Z'] as const).map((a, i) => <Q key={a} label={a} name={`base${a}`} value={base[i]} disabled={plane === 3} onChange={(x) => { const b = [...base]; b[i] = x; setBase(b) }} />)}
        </Legend>
      </TaskBox>
    </div>
  )
}

// ── Scale (DlgScale: the uniform or per-axis factors, the shapes to scale) ────────────────────────────────────────────
/** DlgScale::findShapes and canScale: every document object with a shape that can be scaled (not a vertex, not an empty
 *  compound), by name. A Body's features are document objects of it too, and the Body, whose shape is its Tip's. */
export function scalableList(doc: FeatureDoc): string[] {
  const out: string[] = []
  const add = (n: string, type?: string, links?: unknown) => {
    if (type === 'Part::Vertex') return
    if (type === 'Part::Compound' && !(Array.isArray(links) && links.length)) return
    if (!out.includes(n)) out.push(n)
  }
  for (const o of doc.objects ?? []) add(o.name, o.type, o.links)
  for (const f of doc.features ?? []) add(f.name, f.type)
  if (doc.body && doc.tip) add('Body')
  return out
}
const r7 = (x: number) => Number(x.toFixed(7))       // DlgScale::writeParametersToFeature's "%.7f"
function ScaleTask({ part }: { part: string }) {
  const doc = useStore((s) => s.features[part])
  // findShapes runs once, as the dialog is built: an Apply's new Scale objects do not join the list
  const [list] = useState<string[]>(() => (doc ? scalableList(doc) : []))
  const [shapes, setShapes] = useState<string[]>(() => selectedObjects(part).filter((n) => list.includes(n)))
  const [uniform, setUniform] = useState(true)
  const [factor, setFactor] = useState(1)
  const [xyz, setXyz] = useState<[number, number, number]>([1, 1, 1])
  if (!doc) return null
  const apply = async (close: boolean) => {
    if (!shapes.length) {
      // DlgScale::accept: the message, then QDialog::accept() — OK closes anyway; Apply does not
      await messageBox('critical', 'Scale', 'No scalable shapes selected')
      if (close) closeTask()
      return
    }
    let d = getState().features[part]
    const props = { uniform, uniform_scale: r7(factor), x_scale: r7(xyz[0]), y_scale: r7(xyz[1]), z_scale: r7(xyz[2]) }
    const ops: FeatureOp[] = []
    for (const s of shapes) {
      const name = uniqueName(d, 'Scale')
      ops.push({ op: 'add', feature: { name, type: 'Part::Scale', base: s, ...props } })
      d = { ...d, objects: [...(d.objects ?? []), { name, type: 'Part::Scale' }] }
    }
    if (close) closeTask()
    // one "Scale" transaction; DlgScale::apply hides each source it scaled (Part::Scale's HIDES does)
    await applyOps(part, ops, { name: 'Scale' })
  }
  const axis = (i: 0 | 1 | 2) => (x: number) => setXyz((v) => v.map((y, j) => (j === i ? x : y)) as typeof v)
  return (
    <div className="tasks pt-task" data-task="scale">
      {/* TaskScale::getStandardButtons: Ok | Apply | Close */}
      <Buttons items={[['OK', () => void apply(true), true], ['Close', closeTask], ['Apply', () => void apply(false)]]} />
      <TaskBox title="Scale" icon="pt-scale">
        <Radio name="rbUniform" label="Uniform scaling" checked={uniform} onChange={() => setUniform(true)} />
        <Q label="Factor" name="dsbUniformScale" dims={NUMBER} value={factor} min={-2147480000} max={2147480000}
          disabled={!uniform} onChange={setFactor} />
        <Radio name="rbNonUniform" label="Non-uniform scaling" checked={!uniform} onChange={() => setUniform(false)} />
        <Q label="X-factor" name="dsbXScale" dims={NUMBER} value={xyz[0]} min={-2147480000} max={2147480000}
          disabled={uniform} onChange={axis(0)} />
        <Q label="Y-factor" name="dsbYScale" dims={NUMBER} value={xyz[1]} min={-2147480000} max={2147480000}
          disabled={uniform} onChange={axis(1)} />
        <Q label="Z-factor" name="dsbZScale" dims={NUMBER} value={xyz[2]} min={-2147480000} max={2147480000}
          disabled={uniform} onChange={axis(2)} />
        <ObjList name="treeWidget" header="Shape" doc={doc} names={list} picked={shapes} onPick={setShapes} multi />
      </TaskBox>
    </div>
  )
}

// ── Fillet and Chamfer (DlgFilletEdges: the shape, its edges with their radii, "Fillet" / "Chamfer") ─────────────────
/** The shape of an object as the server builds it (cad feature shape), its faces and edges by FreeCAD's names: the
 *  lists the dialogs show, and what the 3D view picks (part_pick.tsx's helpers). */
function useShapeOf(part: string, name: string | null): Mesh | null {
  const [m, setM] = useState<Mesh | null>(null)
  useEffect(() => {
    setM(null)
    if (!name) return
    let live = true
    void partMesh(part, name).then((x) => { if (live) setM(x) })
    return () => { live = false }
  }, [part, name])
  return m
}
function FilletTask({ part, edit, kind }: { part: string; edit?: string; kind: 'Fillet' | 'Chamfer' }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const solids = doc ? names(doc, isSolid, edit) : []
  const [shape, setShape] = useState<string>(() => existing ? String(existing.base) : selectedObjects(part).find((n) => solids.includes(n)) ?? '')
  const shapeInfo = useShapeOf(part, shape || null)
  const was = useMemo(() => new Map(((existing?.edges ?? []) as [number, number, number][]).map(([i, a, b]) => [i, [a, b]])), [existing])
  const [checked, setChecked] = useState<Map<number, [number, number]>>(() => new Map(was as Map<number, [number, number]>))
  const [variable, setVariable] = useState(false)
  const [r1, setR1] = useState(1), [rEnd, setREnd] = useState(1)
  const count = shapeInfo?.edges.length ?? 0
  const toggle = (i: number) => setChecked((c) => { const n = new Map(c); if (n.has(i)) n.delete(i); else n.set(i, [r1, variable ? rEnd : r1]); return n })
  const all = (on: boolean) => setChecked(on ? new Map(Array.from({ length: count }, (_, i) => [i + 1, [r1, variable ? rEnd : r1]])) : new Map())
  // the shape's edges are picked in the 3D view (DlgFilletEdges' Select edges), as the list's checkboxes pick them; the
  // scene's joint body shows the shape already, so only its edges are drawn, over it
  usePartScene({ part, active: !!shape, only: shape ? [shape] : [], helperKey: 'pt-pick',
    allow: (o, el, face) => o === shape && !face,
    onPick: (name) => { const p = parsePartPick(name); if (p && p[0] === shape && /^Edge\d+$/.test(p[1])) toggle(Number(p[1].slice(4))) } })
  if (!doc) return null
  const ok = async () => {
    if (!shape) { await messageBox('warning', 'No shape selected', 'No valid shape is selected.\nSelect a valid shape in the drop-down box first.'); return }
    if (!checked.size) { await messageBox('warning', 'No edge selected', `No edge entity is checked to ${kind.toLowerCase()}.\nCheck one or more edge entities first.`); return }
    const edges = [...checked.entries()].sort(([a], [b]) => a - b).map(([i, [a, b]]) => [i, r2(a), r2(b)])
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props: { edges } }], { name: kind }); return }
    await addObject(part, { name: uniqueName(getState().features[part], kind), type: `Part::${kind}`, base: shape, edges }, kind)
  }
  const what = kind === 'Fillet' ? 'Fillet' : 'Chamfer'
  return (
    <div className="tasks pt-task" data-task={kind.toLowerCase()}>
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title={`${what} Edges`} icon={kind === 'Fillet' ? 'pt-fillet' : 'pt-chamfer'}>
        <Legend title="Shape">
          <Field label="Selected shape"><span data-qf="shapeObject"><QComboBox value={shape} disabled={!!existing} onChange={(e) => { setShape(e.target.value); setChecked(new Map()) }}>
            <option value="">No selection</option>{solids.map((n) => <option key={n} value={n}>{labelOf(objectOf(doc, n)!)}</option>)}</QComboBox></span></Field>
        </Legend>
        <Legend title={kind === 'Fillet' ? 'Fillet parameter' : 'Chamfer parameters'}>
          <Legend title="Selection">
            <Radio name="selectEdges" label="Select edges" checked onChange={() => {}} />
            <label className="tcheck" data-qf="selectFaces" title="a face picks all its edges in FreeCAD's 3D view; here pick the shape's edges in the 3D view or the list"><input type="radio" disabled /> Select faces</label>
            <button className="qbtn" onClick={() => all(true)}>All</button><button className="qbtn" onClick={() => all(false)}>None</button>
          </Legend>
          <Field label={kind === 'Fillet' ? 'Fillet type' : 'Chamfer type'}><QComboBox value={variable ? '1' : '0'} onChange={(e) => setVariable(e.target.value === '1')}>
            <option value="0">{kind === 'Fillet' ? 'Constant radius' : 'Equal distance'}</option><option value="1">{kind === 'Fillet' ? 'Variable radius' : 'Two distances'}</option></QComboBox></Field>
          <Q label={kind === 'Fillet' ? 'Radius' : 'Length'} name="filletStartRadius" value={r1} min={0} onChange={(x) => { setR1(x); setChecked((c) => new Map([...c.keys()].map((i) => [i, [x, variable ? (c.get(i)?.[1] ?? x) : x]]))) }} />
          {variable && <Q label={kind === 'Fillet' ? 'End radius' : 'Length 2'} name="filletEndRadius" value={rEnd} min={0} onChange={(x) => { setREnd(x); setChecked((c) => new Map([...c.keys()].map((i) => [i, [c.get(i)?.[0] ?? r1, x]]))) }} />}
          <div className="pt-list pt-edges" data-qf="treeView">
            <div className="pt-list-head"><span>Edges to {kind.toLowerCase()}</span><span>{kind === 'Fillet' ? 'Radius' : 'Size'}</span>{variable && <span>{kind === 'Fillet' ? 'End radius' : 'Size 2'}</span>}</div>
            {!shapeInfo && shape && <div className="hint">…</div>}
            {Array.from({ length: count }, (_, k) => k + 1).map((i) => (
              <label key={i} className={cls('pt-item', checked.has(i) && 'sel')}><input type="checkbox" checked={checked.has(i)} onChange={() => toggle(i)} /> Edge{i}
                <span>{checked.has(i) ? `${checked.get(i)![0].toFixed(2)} mm` : ''}</span>{variable && <span>{checked.has(i) ? `${checked.get(i)![1].toFixed(2)} mm` : ''}</span>}</label>))}
          </div>
        </Legend>
      </TaskBox>
    </div>
  )
}

// ── Loft and Sweep (TaskLoft.ui, TaskSweep.ui: available and selected profiles) ────────────────────────────────────────
function Profiles({ doc, avail, picked, setPicked }: { doc: FeatureDoc; avail: string[]; picked: string[]; setPicked(p: string[]): void }) {
  const [a, setA] = useState<string | null>(null), [b, setB] = useState<string | null>(null)
  const left = avail.filter((n) => !picked.includes(n))
  const move = (d: number) => { if (!b) return; const i = picked.indexOf(b), j = i + d; if (j < 0 || j >= picked.length) return; const p = [...picked]; [p[i], p[j]] = [p[j], p[i]]; setPicked(p) }
  return (
    <div className="pt-profiles">
      <div><div className="tlabel">Available profiles</div><ObjList name="availableTreeWidget" doc={doc} names={left} picked={a ? [a] : []} onPick={(x) => setA(x[0] ?? null)} /></div>
      <div className="pt-arrows">
        <button className="qbtn" data-qf="addButton" disabled={!a} title="Add" onClick={() => { if (a) { setPicked([...picked, a]); setA(null) } }}>→</button>
        <button className="qbtn" data-qf="removeButton" disabled={!b} title="Remove" onClick={() => { if (b) { setPicked(picked.filter((x) => x !== b)); setB(null) } }}>←</button>
        <button className="qbtn" data-qf="upButton" disabled={!b} title="Move up" onClick={() => move(-1)}>↑</button>
        <button className="qbtn" data-qf="downButton" disabled={!b} title="Move down" onClick={() => move(1)}>↓</button>
      </div>
      <div><div className="tlabel">Selected profiles</div><ObjList name="selectedTreeWidget" doc={doc} names={picked} picked={b ? [b] : []} onPick={(x) => setB(x[0] ?? null)} /></div>
    </div>
  )
}
const PROFILE_TYPES = new Set([SKETCH, 'Part::Circle', 'Part::Ellipse', 'Part::RegularPolygon', 'Part::Polygon', 'Part::Vertex', 'Part::Plane', 'Part::Offset2D'])
function LoftTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const avail = doc ? names(doc, (o) => PROFILE_TYPES.has(o.type) || o.type === 'Part::Sphere' || o.type === 'Part::Torus' || o.type === 'Part::Ellipsoid', edit) : []
  const [picked, setPicked] = useState<string[]>(() => ((existing?.sections ?? []) as string[]).map(String))
  const [solid, setSolid] = useState(existing ? existing.solid !== false : true), [ruled, setRuled] = useState(existing?.ruled === true), [closed, setClosed] = useState(existing?.closed === true)
  if (!doc) return null
  const ok = async () => {
    if (picked.length < 2) { await messageBox('critical', 'Too few elements', 'At least two vertices, edges, wires or faces are required.'); return }
    const props = { sections: picked, ...(solid ? {} : { solid: false }), ...(ruled ? { ruled: true } : {}), ...(closed ? { closed: true } : {}) }
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props: { sections: picked, solid, ruled, closed } }], { name: 'Edit Loft' }); return }
    await addObject(part, { name: uniqueName(getState().features[part], 'Loft'), type: 'Part::Loft', ...props }, 'Loft')
  }
  return (
    <div className="tasks pt-task" data-task="loft">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title="Loft" icon="pt-loft">
        <Profiles doc={doc} avail={avail} picked={picked} setPicked={setPicked} />
        <Check name="checkSolid" label="Create solid" checked={solid} onChange={setSolid} />
        <Check name="checkRuledSurface" label="Ruled surface" checked={ruled} onChange={setRuled} />
        <Check name="checkClosed" label="Closed" checked={closed} onChange={setClosed} />
      </TaskBox>
    </div>
  )
}
function SweepTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const avail = doc ? names(doc, (o) => PROFILE_TYPES.has(o.type) || ['Part::Helix', 'Part::Spiral', 'Part::Line'].includes(o.type), edit) : []
  const [picked, setPicked] = useState<string[]>(() => ((existing?.sections ?? []) as string[]).map(String))
  const [spine, setSpine] = useState<unknown>(existing?.spine ?? null)
  const [pickPath, setPickPath] = useState(false)
  const [solid, setSolid] = useState(existing ? existing.solid !== false : true), [frenet, setFrenet] = useState(existing ? existing.frenet !== false : true)
  useEffect(() => { setObjectPicker(pickPath ? (r) => { const n = r.slice(part.length + 1); if (objectOf(doc, n)) { setSpine(n); setPickPath(false) } } : null); return () => setObjectPicker(null) }, [pickPath])
  if (!doc) return null
  const ok = async () => {
    if (!picked.length) { await messageBox('critical', 'Too few elements', 'At least one edge or wire is required.'); return }
    if (!spine) { await messageBox('critical', 'Invalid selection', 'Select one or more connected edges in the 3D view and press \'Done\''); return }
    const props = { sections: picked, spine, ...(solid ? {} : { solid: false }), ...(frenet ? {} : { frenet: false }) }
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props: { sections: picked, spine, solid, frenet } }], { name: 'Edit Sweep' }); return }
    await addObject(part, { name: uniqueName(getState().features[part], 'Sweep'), type: 'Part::Sweep', ...props }, 'Sweep')
  }
  return (
    <div className="tasks pt-task" data-task="sweep">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask], ['Help', () => void messageBox('information', 'Sweep', 'Select the profiles, then the path: press Sweep Path and pick the object whose edges are the path in the tree (FreeCAD picks its edges in the 3D view), then OK.')]]} />
      <TaskBox title="Sweep" icon="pt-sweep">
        <Profiles doc={doc} avail={avail} picked={picked} setPicked={setPicked} />
        <div className="tfield"><button className={cls('qbtn', pickPath && 'on')} data-qf="buttonPath" onClick={() => setPickPath(!pickPath)}>{pickPath ? 'Done' : 'Sweep Path'}</button>
          <span className="hint">{spine ? (Array.isArray(spine) ? `${spine[0]}: ${[spine[1]].flat().join(', ')}` : String(spine)) : ''}</span></div>
        <Check name="checkSolid" label="Create solid" checked={solid} onChange={setSolid} />
        <Check name="checkFrenet" label="Frenet" checked={frenet} onChange={setFrenet} />
      </TaskBox>
    </div>
  )
}

// ── Offset, 2D Offset, Thickness (TaskOffset.ui; Command.cpp's "Make Offset", "Make 2D Offset", "Make Thickness") ──────
const MODES: [string, string][] = [['Skin', 'Skin'], ['Pipe', 'Pipe'], ['RectoVerso', 'Recto verso']]
const JOINS = ['Arc', 'Tangent', 'Intersection']
function OffsetTask({ part, edit, kind }: { part: string; edit?: string; kind: 'offset' | 'offset2d' | 'thickness' }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const source = existing ? (kind === 'thickness' ? String((existing.faces as unknown[])?.[0]) : String(existing.source)) : selectedObjects(part)[0] ?? ''
  const info = useShapeOf(part, kind === 'thickness' ? source || null : null)
  const [value, setValue] = useState(num(doc, existing?.value, 1))
  const [mode, setMode] = useState(String(existing?.mode ?? (kind === 'offset2d' ? 'Pipe' : 'Skin')))
  const [join, setJoin] = useState(String(existing?.join ?? 'Arc'))
  const [inter, setInter] = useState(existing?.intersection === true), [self, setSelf] = useState(existing?.self_intersection === true), [fill, setFill] = useState(existing?.fill === true)
  const [faces, setFaces] = useState<string[]>(() => (kind === 'thickness' && existing ? [((existing.faces as unknown[])?.[1] as string[])].flat().map(String) : []))
  const [picking, setPicking] = useState(false)
  // Thickness' Faces button: the source's faces are picked in the 3D view, tinted over the shape as FreeCAD's selection
  // tints it; the list below picks the same faces
  usePartScene({ part, active: kind === 'thickness' && picking && !!source, only: source ? [source] : [], helperKey: 'pt-pick',
    style: { face: '#ffaa00', edge: '#b26b00', opacity: 0.55 },
    allow: (o, el, face) => o === source && face,
    onPick: (name) => { const p = parsePartPick(name); if (p && p[0] === source && !faces.includes(p[1])) setFaces([...faces, p[1]]) } })
  if (!doc) return null
  const cfg = { offset: ['Offset', 'Part::Offset', 'Offset', 'Make Offset', 'pt-offset'], offset2d: ['Offset', 'Part::Offset2D', 'Offset2D', 'Make 2D Offset', 'pt-offset2d'],
    thickness: ['Thickness', 'Part::Thickness', 'Thickness', 'Make Thickness', 'pt-thickness'] }[kind] as [string, string, string, string, IconName]
  const ok = async () => {
    if (!source) { await messageBox('warning', cfg[0], 'Select one shape, please.'); return }
    if (kind === 'thickness' && !faces.length) { await messageBox('warning', 'Wrong selection', 'Selected one or more faces of a shape'); return }
    const props: Record<string, unknown> = { value: r2(value), mode, join, intersection: inter, self_intersection: self }
    if (kind !== 'thickness') props.fill = fill
    if (kind === 'offset2d') delete props.self_intersection
    if (kind === 'thickness') props.faces = [source, faces]
    else props.source = source
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props }], { name: `Edit ${cfg[2]}` }); return }
    const clean = Object.fromEntries(Object.entries(props).filter(([k, x]) => !(x === false || (k === 'mode' && x === (kind === 'offset2d' ? 'Pipe' : 'Skin')) || (k === 'join' && x === 'Arc') || (k === 'value' && x === 1))))
    await addObject(part, { name: uniqueName(getState().features[part], cfg[2]), type: cfg[1], ...clean }, cfg[3])
  }
  return (
    <div className="tasks pt-task" data-task={kind}>
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title={cfg[0]} icon={cfg[4]}>
        <Q label={kind === 'thickness' ? 'Thickness' : 'Offset'} name="spinOffset" value={value} onChange={setValue} />
        <Field label="Mode"><span data-qf="modeType"><QComboBox value={mode} onChange={(e) => setMode(e.target.value)}>{(kind === 'offset2d' ? MODES.slice(0, 2) : MODES).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</QComboBox></span></Field>
        <Field label="Join type"><span data-qf="joinType"><QComboBox value={join} onChange={(e) => setJoin(e.target.value)}>{JOINS.map((j) => <option key={j}>{j}</option>)}</QComboBox></span></Field>
        <Check name="intersection" label="Intersection" checked={inter} onChange={setInter} />
        {kind !== 'offset2d' && <Check name="selfIntersection" label="Self-intersection" checked={self} onChange={setSelf} />}
        {kind !== 'thickness' && <Check name="fillOffset" label="Fill offset" checked={fill} onChange={setFill} />}
        {kind === 'thickness' && <>
          <button className={cls('qbtn', picking && 'on')} data-qf="facesButton" onClick={() => setPicking(!picking)}>{picking ? 'Done' : 'Faces'}</button>
          {picking && <div className="pt-list" title="the faces are picked in the 3D view; here they are listed too">{(info?.faces ?? []).map((f) => f.name).map((f) => (
            <label key={f} className={cls('pt-item', faces.includes(f) && 'sel')}><input type="checkbox" checked={faces.includes(f)} onChange={() => setFaces(faces.includes(f) ? faces.filter((x) => x !== f) : [...faces, f])} /> {f}</label>))}</div>}
          <div className="hint">{faces.length ? `${source}: ${faces.join(', ')}` : ''}</div></>}
        <Check name="updateView" label="Update view" checked onChange={() => {}} disabled />
      </TaskBox>
    </div>
  )
}

// ── Boolean Operation (DlgBooleanOperation: two shapes by kind, the operation; Apply makes it, "Boolean operation") ─────
function BooleanTask({ part }: { part: string }) {
  const doc = useStore((s) => s.features[part])
  const [op, setOp] = useState<'union' | 'diff' | 'inter' | 'section'>('union')
  const [first, setFirst] = useState<string | null>(null), [second, setSecond] = useState<string | null>(null)
  if (!doc) return null
  const objs = (doc.objects ?? []).filter((o) => o.type !== SKETCH)
  const group = (o: Feature) => (isSolid(o) ? (o.type === 'Part::Compound' || o.type === 'Part::BooleanFragments' ? 'Compounds' : 'Solids') : o.type === 'Part::Plane' ? 'Faces' : 'Shells')
  const tree = (picked: string | null, set: (n: string) => void, other: string | null, name: string) => (
    <div className="pt-list" data-qf={name}>{['Solids', 'Shells', 'Compounds', 'Faces'].map((g) => <div key={g}><div className="pt-list-head">{g}</div>
      {objs.filter((o) => group(o) === g && o.name !== other).map((o) => <div key={o.name} className={cls('pt-item', picked === o.name && 'sel')} style={{ paddingLeft: 18 }} onClick={() => set(o.name)}>
        <Icon name={partIcon(o.type)} size={14} /> {labelOf(o)}</div>)}</div>)}</div>)
  const apply = async () => {
    if (!first || !second) { await messageBox('critical', 'Boolean Operation', 'Select two shapes'); return }
    const method = { union: ['Part::Fuse', 'Fusion'], inter: ['Part::Common', 'Common'], diff: ['Part::Cut', 'Cut'], section: ['Part::Section', 'Section'] }[op]
    const [a, b] = [objectOf(doc, first)!, objectOf(doc, second)!]
    if (op !== 'section' && (!isSolid(a) || !isSolid(b))) {
      await messageBox('critical', 'Boolean Operation', `Performing ${op === 'union' ? 'union' : op === 'inter' ? 'intersection' : 'difference'} on non-solids is not possible`); return
    }
    await addObject(part, { name: uniqueName(getState().features[part], method[1]), type: method[0], base: first, tool: second }, 'Boolean operation')
    setFirst(null); setSecond(null)
  }
  return (
    <div className="tasks pt-task" data-task="boolean">
      <Buttons items={[['Close', closeTask], ['Apply', () => void apply(), true]]} />
      <TaskBox title="Boolean Operation" icon="pt-booleans">
        <Legend title="Boolean Operation">
          <Radio name="unionButton" label="Union" checked={op === 'union'} onChange={() => setOp('union')} />
          <Radio name="diffButton" label="Difference" checked={op === 'diff'} onChange={() => setOp('diff')} />
          <Radio name="interButton" label="Intersection" checked={op === 'inter'} onChange={() => setOp('inter')} />
          <Radio name="sectionButton" label="Section" checked={op === 'section'} onChange={() => setOp('section')} />
        </Legend>
        <div className="pt-profiles">{tree(first, setFirst, second, 'firstShape')}{tree(second, setSecond, first, 'secondShape')}</div>
        <button className="qbtn" data-qf="swapButton" onClick={() => { setFirst(second); setSecond(first) }}>Swap Selection</button>
      </TaskBox>
    </div>
  )
}

// ── Project on Surface (DlgProjectionOnSurface; "Project on surface") ────────────────────────────────────────────────
function ProjectionTask({ part, edit }: { part: string; edit?: string }) {
  const doc = useStore((s) => s.features[part])
  const existing = edit ? objectOf(doc, edit) : undefined
  const [support, setSupport] = useState<[string, string] | null>((existing?.support_face as [string, string]) ?? null)
  const [proj, setProj] = useState<[string, string][]>(((existing?.projection ?? []) as [string, string][]))
  const [mode, setMode] = useState(String(existing?.mode ?? 'All'))
  const [height, setHeight] = useState(num(doc, existing?.height, 0)), [offset, setOffset] = useState(num(doc, existing?.offset, 0))
  const [dir, setDir] = useState<number[]>((existing?.direction as number[]) ?? [0, 0, 1])
  const [adding, setAdding] = useState<'support' | 'Face' | 'Wire' | 'Edge' | null>(null)
  const [obj, setObj] = useState('')
  const info = useShapeOf(part, obj || null)
  // DlgProjectionOnSurface picks the surface and what is projected in the 3D view: a face, or an edge for a wire or an
  // edge, of any object the document shows
  usePartScene({ part, active: !!adding, helperKey: 'pt-pick',
    allow: (o, el, face) => adding === 'support' || adding === 'Face' ? face : !face,
    onPick: (name) => {
      const p = parsePartPick(name)
      if (!p) return
      if (adding === 'support') setSupport(p)
      else setProj((x) => [...x.filter((q) => !(q[0] === p[0] && q[1] === p[1])), p])
      setAdding(null)
    } })
  if (!doc) return null
  const objs = (doc.objects ?? []).filter((o) => o.name !== edit)
  const ok = async () => {
    if (!support) { await messageBox('warning', 'Project on surface', 'Select the projection surface first: press Select Projection Surface and pick a face'); return }
    if (!proj.length) { await messageBox('warning', 'Project on surface', 'Add the faces, wires or edges to project first'); return }
    const props: Record<string, unknown> = { support_face: support, projection: proj, mode, height: r2(height), offset: r2(offset), direction: dir.map(r2) }
    closeTask()
    if (existing) { await applyOps(part, [{ op: 'set', name: existing.name, props }], { name: 'Edit Projection' }); return }
    await addObject(part, { name: uniqueName(getState().features[part], 'Projection'), type: 'Part::ProjectOnSurface', ...props }, 'Project on surface')
  }
  const subs = (k: 'Face' | 'Wire' | 'Edge' | 'support'): string[] =>
    (k === 'Edge' || k === 'Wire' ? info?.edges.map((e) => e.name) : info?.faces.map((f) => f.name)) ?? []
  return (
    <div className="tasks pt-task" data-task="projection">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title="Project on Surface" icon="pt-projection">
        {(['support', 'Face', 'Wire', 'Edge'] as const).map((k) => (
          <button key={k} className={cls('qbtn', adding === k && 'on')} data-qf={k === 'support' ? 'pushButtonAddProjFace' : `pushButtonAdd${k}`} onClick={() => setAdding(adding === k ? null : k)}>
            {k === 'support' ? 'Select Projection Surface' : `Add ${k}`}</button>))}
        {adding && <div className="pt-pick" title="the elements are picked in the 3D view; here an object and its element">
          <QComboBox value={obj} onChange={(e) => setObj(e.target.value)}><option value="">…</option>{objs.map((o) => <option key={o.name} value={o.name}>{labelOf(o)}</option>)}</QComboBox>
          {obj && <div className="pt-list">{subs(adding).map((sub) => <div key={sub} className="pt-item" onClick={() => {
            if (adding === 'support') setSupport([obj, sub]); else setProj([...proj.filter((p) => !(p[0] === obj && p[1] === sub)), [obj, sub]])
            setAdding(null)
          }}>{sub}</div>)}</div>}</div>}
        <div className="hint">{support ? `on ${support[0]}.${support[1]}` : ''}{proj.length ? ` · ${proj.map((p) => `${p[0]}.${p[1]}`).join(', ')}` : ''}</div>
        <Radio name="radioButtonShowAll" label="Show all" checked={mode === 'All'} onChange={() => setMode('All')} />
        <Radio name="radioButtonFaces" label="Show faces" checked={mode === 'Faces'} onChange={() => setMode('Faces')} />
        <Radio name="radioButtonEdges" label="Show edges" checked={mode === 'Edges'} onChange={() => setMode('Edges')} />
        <Q label="Extrude height" name="doubleSpinBoxExtrudeHeight" dims={NUMBER} value={height} min={0} onChange={setHeight} />
        <Q label="Solid depth" name="doubleSpinBoxSolidDepth" dims={NUMBER} value={offset} onChange={setOffset} />
        <Legend title="Direction">
          <button className="qbtn" disabled title="the camera's direction is not read from the view yet">Get Current Camera Direction</button>
          {(['X', 'Y', 'Z'] as const).map((a, i) => <div key={a} className="pt-row"><button className="qbtn" onClick={() => setDir([0, 1, 2].map((j) => (j === i ? 1 : 0)))}>{a}</button>
            <Q name={`doubleSpinBoxDir${a}`} dims={NUMBER} value={dir[i]} disabled onChange={() => {}} /></div>)}
        </Legend>
      </TaskBox>
    </div>
  )
}

// ── New Sketch outside a Body (SketchOrientationDialog: the plane, Reverse direction, Offset) ───────────────────────
function SketchTask({ part }: { part: string }) {
  const doc = useStore((s) => s.features[part])
  const [plane, setPlane] = useState<'XY' | 'XZ' | 'YZ'>('XY')
  const [rev, setRev] = useState(false), [offset, setOffset] = useState(0)
  if (!doc) return null
  const ok = async () => {
    const name = uniqueName(doc, 'Sketch')
    const off = r2(offset)
    // SketchOrientationDialog: Reverse direction turns the plane over (180° about its x axis), Offset moves it along its normal
    const attach = rev || off ? { attachment_offset: [[0, 0, off], [0, 0, rev ? 180 : 0]] } : {}
    closeTask()
    const done = await applyOps(part, [{ op: 'add', feature: { name, type: SKETCH, support: plane, ...attach, geometry: [], constraints: [] }, list: 'OBJECTS' } as FeatureOp], { name: 'Create a new sketch' })
    if (done) editSketch(part, name)
  }
  return (
    <div className="tasks pt-task" data-task="sketch">
      <Buttons items={[['OK', () => void ok(), true], ['Cancel', closeTask]]} />
      <TaskBox title="Choose orientation" icon="pd-new-sketch">
        <Legend title="Sketch Orientation">
          <Radio name="XY_radioButton" label="XY-plane" checked={plane === 'XY'} onChange={() => setPlane('XY')} />
          <Radio name="XZ_radioButton" label="XZ-plane" checked={plane === 'XZ'} onChange={() => setPlane('XZ')} />
          <Radio name="YZ_radioButton" label="YZ-plane" checked={plane === 'YZ'} onChange={() => setPlane('YZ')} />
          <Check name="Reverse_checkBox" label="Reverse direction" checked={rev} onChange={setRev} />
          <Q label="Offset" name="Offset_doubleSpinBox" value={offset} onChange={setOffset} />
        </Legend>
      </TaskBox>
    </div>
  )
}

/** panels.tsx's TaskContent hands the 'part' task here: other is "<which>" or "<which>:<object being edited>". */
export function PartTask({ part, other }: { part: string; other: string }) {
  const [which, edit] = other.includes(':') ? [other.slice(0, other.indexOf(':')), other.slice(other.indexOf(':') + 1)] : [other, undefined]
  const key = `${part}:${other}`
  switch (which) {
    case 'primitives': return <PrimitivesTask key={key} part={part} edit={edit} />
    case 'tube': return <TubeTask key={key} part={part} edit={edit} />
    case 'extrude': return <ExtrudeTask key={key} part={part} edit={edit} />
    case 'revolve': return <RevolveTask key={key} part={part} edit={edit} />
    case 'mirror': return <MirrorTask key={key} part={part} edit={edit} />
    case 'scale': return <ScaleTask key={key} part={part} />
    case 'fillet': return <FilletTask key={key} part={part} edit={edit} kind="Fillet" />
    case 'chamfer': return <FilletTask key={key} part={part} edit={edit} kind="Chamfer" />
    case 'loft': return <LoftTask key={key} part={part} edit={edit} />
    case 'sweep': return <SweepTask key={key} part={part} edit={edit} />
    case 'offset': case 'offset2d': case 'thickness': return <OffsetTask key={key} part={part} edit={edit} kind={which} />
    case 'boolean': return <BooleanTask key={key} part={part} />
    case 'projection': return <ProjectionTask key={key} part={part} edit={edit} />
    case 'sketch': return <SketchTask key={key} part={part} />
  }
  report('err', `no Part task panel ${which}`)
  return null
}
void refOf
