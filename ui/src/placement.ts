import * as THREE from 'three'
import type { Placement, Vec3 } from './api'

const round = (n: number) => Math.round(n * 1e6) / 1e6 + 0 // + 0 turns -0 into 0

/** The rigid move a placements.toml entry stands for, as cad_agent/placements.py
 *  applies it: p' = R (p - about) + about + move, with R from XYZ Euler angles in degrees. */
export function placementMatrix(p: Placement): THREE.Matrix4 {
  const [ax, ay, az] = p.about, [mx, my, mz] = p.move
  const d = THREE.MathUtils.degToRad
  const r = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(d(p.turn[0]), d(p.turn[1]), d(p.turn[2]), 'XYZ'))
  return new THREE.Matrix4().makeTranslation(ax + mx, ay + my, az + mz).multiply(r).multiply(new THREE.Matrix4().makeTranslation(-ax, -ay, -az))
}

/** FreeCAD's way of showing the same move: rotate by Angle about Axis through the
 *  origin, then translate by Position (its Placement property). */
export function toFreeCAD(p: Placement): { angle: number; axis: Vec3; position: Vec3 } {
  const t = new THREE.Vector3(), q = new THREE.Quaternion()
  placementMatrix(p).decompose(t, q, new THREE.Vector3())
  const s = Math.sqrt(Math.max(0, 1 - q.w * q.w))
  let axis: Vec3 = s < 1e-9 ? [0, 0, 1] : [q.x / s, q.y / s, q.z / s]
  if (q.w < 0) axis = axis.map((v) => -v) as Vec3 // keep the angle in 0..180
  const angle = THREE.MathUtils.radToDeg(2 * Math.acos(Math.min(1, Math.abs(q.w))))
  return { angle: round(angle), axis: axis.map(round) as Vec3, position: [round(t.x), round(t.y), round(t.z)] }
}

export function fromFreeCAD(angle: number, axis: Vec3, position: Vec3, about: Vec3): Placement {
  const ax = new THREE.Vector3(...axis)
  if (ax.lengthSq() < 1e-12) ax.set(0, 0, 1)
  const m = new THREE.Matrix4().makeRotationAxis(ax.normalize(), THREE.MathUtils.degToRad(angle))
  m.setPosition(position[0], position[1], position[2])
  return toPlacement(m, about)
}

/** The same kind of move written back as a placement around a fixed `about`. */
export function toPlacement(m: THREE.Matrix4, about: Vec3): Placement {
  const t = new THREE.Vector3(), q = new THREE.Quaternion()
  m.decompose(t, q, new THREE.Vector3())
  const e = new THREE.Euler().setFromQuaternion(q, 'XYZ')
  const a = new THREE.Vector3(...about)
  const move = t.sub(a).add(a.clone().applyQuaternion(q)) // translation - about + R about
  const deg = THREE.MathUtils.radToDeg
  return { move: [round(move.x), round(move.y), round(move.z)], turn: [round(deg(e.x)), round(deg(e.y)), round(deg(e.z))], about }
}
