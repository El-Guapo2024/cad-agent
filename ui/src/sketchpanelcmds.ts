// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/CommandSketcherVirtualSpace.cpp: 2017 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/CommandSketcherTools.cpp: 2014 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/CommandAlterGeometry.cpp: 2011 Jürgen Riegel
//   src/Mod/Sketcher/Gui/Command.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/ViewProviderSketch.cpp: 2009 Juergen Riegel
//   src/Mod/Sketcher/App/SketchObjectConstraints.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectGeometry.cpp: 2008 Jürgen Riegel
//   src/Mod/Show/mTempoVis.py: 2016 Victor Titov (DeepSOIC)
//   src/Gui/View3DInventorViewer.cpp: 2004 Jürgen Riegel
// The edit mode's commands around the task panel's lists: Sketcher_SwitchVirtualSpace, the selection commands
// (Select Origin and the axes, the redundant, conflicting, malformed and partially redundant constraints, the
// constraints of the selected geometry and the geometry of the selected constraints), Delete All Geometry and Delete
// All Constraints with their question, Toggle Construction Geometry (the creation mode, or the selected edges, points
// or external geometry), Toggle Section View (the sketch's clipping plane) and the panel's Center Sketch; the
// SketchObject calls under them (toggleVirtualSpace, setVirtualSpace, deleteAllGeometry, toggleConstruction).
import * as THREE from 'three'
import * as S from './sketcher'
import * as SK from './sketch'
import { idOf } from './sketchcons'
import { getView } from './actions'
import { messageBox } from './msgbox'
import { report } from './store'

const warn = (title: string, text: string) => report('warn', `${title}: ${text}`)
/** ViewProviderSketch's mode: STATUS_NONE (no tool, no drag), STATUS_SKETCH_UseHandler (a tool), or another. */
export const sketchMode = (): 'none' | 'handler' | 'other' => (S.getHandler() ? 'handler' : S.getMode() === 'none' ? 'none' : 'other')
/** SketcherGui::isCommandActive: in edit, with no drag or box selection going on. */
export const isCommandActive = () => S.isEditing() && sketchMode() !== 'other'
/** isSketcherVirtualSpaceActive, isCreateConstraintActive: STATUS_NONE (and something selected in the sketch). */
export const isStatusNone = (needsSelection = false) => S.isEditing() && sketchMode() === 'none' && (!needsSelection || S.getSelection().length > 0)
/** isCommandNeedingGeometryActive: a selected element with a GeoId (an edge, a vertex, the root, an axis). */
export const hasGeometrySelected = () => isCommandActive() && S.getSelection().some((n) => idOf(n) !== null)
/** isCommandNeedingConstraintActive. */
export const hasConstraintSelected = () => isCommandActive() && S.getSelection().some((n) => n.startsWith('Constraint'))
/** SketcherGui::ReleaseHandler: a running tool stops; true when there was one. */
export function releaseHandler() {
  if (!S.getHandler()) return false
  S.purgeHandler()
  return true
}
/** PropertyConstraintList::getIndexFromConstraintName. */
const constraintIndex = (name: string) => Number(name.slice(10)) - 1
const isConstraintName = (n: string) => n.length > 10 && n.startsWith('Constraint')

// ── Sketcher_SwitchVirtualSpace ──────────────────────────────────────────────────────────────────────────────────
/** CmdSketcherSwitchVirtualSpace::activated: the selected constraints go to the other virtual space; with no
 *  constraint selected, the view shows the other space. */
export function switchVirtualSpace() {
  const sel = S.getSelection()
  let modeChange = true
  if (sel.length) {
    if (sel.some(isConstraintName)) modeChange = false
  }
  if (modeChange) { S.setShownVirtualSpace(!S.isShownVirtualSpace()); return }
  S.openCommand('Toggle constraints to the other virtual space')
  let successful = sel.length
  for (const n of sel) {
    if (!isConstraintName(n)) { successful--; continue }
    if (!toggleVirtualSpace(constraintIndex(n))) successful--
  }
  if (successful > 0) S.commitCommand()
  else S.abortCommand()
  S.clearSelection()
  S.solve() // signalSolverUpdate: the view and the lists redraw
}
/** SketchObject::toggleVirtualSpace. */
export function toggleVirtualSpace(i: number): boolean {
  const c = S.getConstraints()[i]
  if (!c) return false
  S.setConstraint(i, { ...c, virtual: !c.virtual })
  return true
}
/** SketchObject::setVirtualSpace(ids, on). */
export function setVirtualSpace(ids: number[], on: boolean): boolean {
  const cs = S.getConstraints()
  if (!ids.length) return true
  if (Math.min(...ids) < 0 || Math.max(...ids) >= cs.length) return false
  for (const i of ids) if (cs[i].virtual !== on) S.setConstraint(i, { ...cs[i], virtual: on })
  return true
}

// ── selection commands (CommandSketcherTools.cpp) ────────────────────────────────────────────────────────────────
/** CmdSketcherSelectOrigin / SelectHorizontalAxis / SelectVerticalAxis: the element joins the selection, or leaves it
 *  when it is already there. */
export function toggleSelected(name: 'RootPoint' | 'H_Axis' | 'V_Axis') {
  if (S.isSelected(name)) S.rmvSelection(name)
  else S.addSelection(name)
}
/** CmdSketcherSelectRedundantConstraints and its siblings: the solver's last list, in the constraints' order. */
export function selectSolverList(ids: number[]) {
  S.clearSelection()
  const names = S.getConstraints().flatMap((_, i) => (ids.includes(i) ? [SK.constraintSelName(i)] : []))
  if (names.length) S.setSelection(names)
}
/** CmdSketcherSelectConstraints: the constraints that involve the selected geometry (involvesGeoId, or
 *  involvesGeoIdAndPosId for a point). */
export function selectAssociatedConstraints() {
  releaseHandler()
  const sel = S.getSelection()
  if (!sel.length) { warn('Wrong selection', 'Select elements from a single sketch.'); return }
  const ids = sel.map(idOf).filter((x): x is NonNullable<typeof x> => !!x)
  S.clearSelection()
  const out: string[] = []
  S.getConstraints().forEach((c, i) => {
    const els: [number, SK.PointPos][] = [[c.first, c.firstPos], [c.second, c.secondPos], [c.third, c.thirdPos]]
    const related = ids.some((s) => els.some(([g, p]) => g !== SK.GEO_UNDEF && g === s.geoId && (s.pos === SK.NONE || p === s.pos)))
    if (related) out.push(SK.constraintSelName(i))
  })
  if (out.length) S.setSelection(out)
}
/** CmdSketcherSelectElementsAssociatedWithConstraints: each selected constraint's First, Second and Third, an edge as
 *  EdgeN (GeoId + 1, whatever it is) and a point as its vertex. */
export function selectAssociatedElements() {
  const sel = S.getSelection(), cs = S.getConstraints(), out: string[] = []
  S.clearSelection()
  for (const n of sel) {
    if (!isConstraintName(n)) continue
    const c = cs[constraintIndex(n)]
    if (!c) continue
    for (const [g, p] of [[c.first, c.firstPos], [c.second, c.secondPos], [c.third, c.thirdPos]] as [number, SK.PointPos][]) {
      if (g === SK.GEO_UNDEF) continue
      if (p === SK.NONE) out.push(`Edge${g + 1}`)
      else { const v = S.vertexIndexOf(g, p); out.push(v > -1 ? SK.vertexName(v) : '') }
    }
  }
  // "Edge0" (the H axis) and "Edge-2" (an external edge) name nothing a sketch has; "" is the sketch itself
  const valid = out.filter((x) => x && (!x.startsWith('Edge') || Number(x.slice(4)) >= 1))
  if (!out.length) warn('No constraint selected', 'At least one constraint must be selected')
  else S.setSelection(valid)
}

// ── Delete All Geometry / Delete All Constraints ─────────────────────────────────────────────────────────────────
/** CmdSketcherDeleteAllGeometry: after the question, SketchObject::deleteAllGeometry (the geometry and every
 *  constraint go; the external geometry stays). */
export async function deleteAllGeometry() {
  const ret = await messageBox('question', 'Delete All Geometry', 'Delete all geometry and constraints?', ['Yes', 'Cancel'])
  if (ret !== 'Yes' || !S.isEditing()) return
  S.clearSelection()
  S.openCommand('Delete all geometry')
  S.setGeometry([]); S.setConstraints([])
  S.commitCommand()
  S.solve()
}
/** CmdSketcherDeleteAllConstraints: after the question, SketchObject::deleteAllConstraints. */
export async function deleteAllConstraints() {
  const ret = await messageBox('question', 'Delete All Constraints', 'Delete all the constraints in the sketch?', ['Yes', 'Cancel'])
  if (ret !== 'Yes' || !S.isEditing()) return
  S.clearSelection()
  S.openCommand('Delete all constraints')
  S.setConstraints([])
  S.commitCommand()
  S.solve()
}

// ── Sketcher_ToggleConstruction ──────────────────────────────────────────────────────────────────────────────────
/** GeometryFacade::isInternalAligned: the geometry an InternalAlignment constraint puts on its parent. */
const isInternalAligned = (g: number) => S.getConstraints().some((c) => c.type === 'InternalAlignment' && c.first === g)
/** CmdSketcherToggleConstruction::activated: nothing selected, the creation mode switches between normal and
 *  construction geometry; else the selected edges (an internal one is left alone) switch, or, when only vertices are
 *  selected, the points among them. */
export function toggleConstruction() {
  const sel = S.getSelection()
  if (!sel.length) {
    S.setConstructionMode(!S.isConstructionMode())
    S.applyCursor()
    return
  }
  S.openCommand('Toggle construction geometry')
  const verticesOnly = !sel.some((n) => (n.length > 4 && n.startsWith('Edge')) || (n.length > 12 && n.startsWith('ExternalEdge')))
  for (const n of sel) {
    if (n.length > 4 && n.startsWith('Edge')) {
      const g = Number(n.slice(4)) - 1
      if (!S.getGeometry()[g] || isInternalAligned(g)) continue
      S.toggleConstruction(g)
    } else if (n.length > 12 && n.startsWith('ExternalEdge')) {
      // toggleConstruction(GeoId <= RefExt) switches the external geometry's Defining flag; the part file has no such
      // flag yet, so external geometry stays reference geometry (ui/PARITY.md)
    } else if (verticesOnly && n.length > 6 && n.startsWith('Vertex')) {
      const [g] = S.geoVertexIndex(Number(n.slice(6)) - 1)
      if (g >= 0 && S.getGeometry()[g]?.type === 'Point') S.toggleConstruction(g)
    }
  }
  S.commitCommand()
  S.clearSelection()
  S.solve()
}

// ── Sketcher_ViewSection ─────────────────────────────────────────────────────────────────────────────────────────
let section = false
/** CmdSketcherViewSection: TempoVis.sketchClipPlane(sketch, editDoc, None, reverted) toggles a clipping plane through
 *  the sketch (EditingTransform, turned over when the view looks at the sketch from behind), moved 0.001 mm along its
 *  normal (ClipPlane's offset); toggleClippingPlane keeps what lies behind it (its normal is the sketch's -Z). */
export function viewSection() {
  const s = S.getSession(), view = getView()
  if (!s || !view) return
  section = !section
  if (!section) { view.setSectionPlane(null); return }
  const q = new THREE.Quaternion(...s.placement.rotation)
  // getViewOrientationFactor: -1 when the camera looks at the sketch's back
  const cam = view.cameraOrientation()
  const camZ = cam ? new THREE.Vector3(0, 0, 1).applyQuaternion(new THREE.Quaternion(...cam)) : new THREE.Vector3(0, 0, 1)
  const normal = new THREE.Vector3(0, 0, 1).applyQuaternion(q)
  if (camZ.dot(normal) < 0) normal.negate() // pla * App.Rotation(0, 1, 0, 0): the plane turned over
  const base = new THREE.Vector3(...s.placement.base).addScaledVector(normal, 0.001)
  // SbPlane(dir = R·(0, 0, -1), base): Coin keeps the side its normal points to
  view.setSectionPlane(new THREE.Plane().setFromNormalAndCoplanarPoint(normal.clone().negate(), base))
}
/** TempoVis.restore on leaving the sketch: the plane goes. */
S.onSketchClosed(() => { if (section) { section = false; getView()?.setSectionPlane(null) } })
export const isSectionView = () => section

// ── the panel's Center Sketch (ViewProviderSketch::centerSelection) ──────────────────────────────────────────────
/** The camera moves (keeping its direction and focal distance) so that the selected constraints' icons and labels
 *  are in the middle of the view. */
export function centerSelection() {
  const view = getView(), s = S.getSession(), hits = S.hitRegions()
  if (!view || !s || !hits) return
  const ids = S.selectedConstraints()
  const box = new THREE.Box2()
  for (const r of hits.icons) if (r.ids.some((i) => ids.has(i))) box.expandByPoint(new THREE.Vector2(r.x, r.y)).expandByPoint(new THREE.Vector2(r.x + r.w, r.y + r.h))
  for (const r of hits.labels) if (ids.has(r.id)) box.expandByPoint(new THREE.Vector2(r.x - r.w / 2, r.y - r.h / 2)).expandByPoint(new THREE.Vector2(r.x + r.w / 2, r.y + r.h / 2))
  if (box.isEmpty()) return
  const c = box.getCenter(new THREE.Vector2()), p = S.screenToSketch(c.x, c.y)
  if (!p) return
  const world = new THREE.Vector3(p[0], p[1], 0).applyQuaternion(new THREE.Quaternion(...s.placement.rotation)).add(new THREE.Vector3(...s.placement.base))
  const text = view.getCamera(), ori = view.cameraOrientation()
  if (!text || !ori) return
  const focal = Number(/focalDistance\s+(\S+)/.exec(text)?.[1] ?? 0)
  const dir = new THREE.Vector3(0, 0, 1).applyQuaternion(new THREE.Quaternion(...ori))
  const pos = world.clone().addScaledVector(dir, focal)
  view.setCamera(text.replace(/position\s+\S+\s+\S+\s+\S+/, `position ${pos.x} ${pos.y} ${pos.z}`))
}
