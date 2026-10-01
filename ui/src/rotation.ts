// The rotation readouts the Placement and Transform task panels show: axis and angle, yaw,
// pitch and roll, and Euler angles in a given sequence. Ported from Base::Rotation
// (src/Base/Rotation.cpp at FreeCAD main 3160daf1e2b6, LGPL-2.1-or-later), whose Euler code is
// itself OCCT's gp_Quaternion (Ken Shoemake, Graphics Gems IV); scripts/fcdiff.py checks it
// against FreeCAD. FreeCAD's quaternion is (x, y, z, w), as three.js's.
import * as THREE from 'three'
import type { Vec3 } from './api'

type Quat = { x: number; y: number; z: number; w: number }
// Base/Tools.h
const toRadians = (degrees: number) => degrees * (Math.PI / 180)
const toDegrees = (radians: number) => radians * (180 / Math.PI)
// Tolerance copied from OCC "gp_Quaternion.cxx"
const TOLERANCE = 16 * Number.EPSILON

/** Rotation::setValue(q0, q1, q2, q3): stored normalized. */
function normalized(x: number, y: number, z: number, w: number): THREE.Quaternion {
  const len = Math.sqrt(x * x + y * y + z * z + w * w)
  return len > 0.0 ? new THREE.Quaternion(x / len, y / len, z / len, w / len) : new THREE.Quaternion(x, y, z, w)
}
const rotation = (q: Quat) => normalized(q.x, q.y, q.z, q.w)

/** Rotation::evaluateVector, then getRawValue: axis and angle (degrees, 0 to 360). */
export function axisAngleOf(q: Quat): { axis: Vec3; angle: number } {
  const r = rotation(q)
  // Note: -1 < w < +1 (|w| == 1 not allowed, with w:=quat[3])
  if (r.w > -1.0 && r.w < 1.0) {
    const rfAngle = Math.acos(r.w) * 2.0
    const scale = Math.sin(rfAngle / 2.0)
    return { axis: [r.x / scale, r.y / scale, r.z / scale], angle: toDegrees(rfAngle) }
  }
  return { axis: [0, 0, 1], angle: 0 }
}

/** Rotation::setYawPitchRoll: the angles (degrees) are intrinsic Z, Y′, X″. */
export function quatOfYpr(yaw: number, pitch: number, roll: number): THREE.Quaternion {
  const y = toRadians(yaw), p = toRadians(pitch), r = toRadians(roll)
  const c1 = Math.cos(y / 2.0), s1 = Math.sin(y / 2.0)
  const c2 = Math.cos(p / 2.0), s2 = Math.sin(p / 2.0)
  const c3 = Math.cos(r / 2.0), s3 = Math.sin(r / 2.0)
  return normalized(c1 * c2 * s3 - s1 * s2 * c3, c1 * s2 * c3 + s1 * c2 * s3, s1 * c2 * c3 - c1 * s2 * s3, c1 * c2 * c3 + s1 * s2 * s3)
}

/** Rotation::getYawPitchRoll, in degrees. */
export function yprOfQuat(rot: Quat): Vec3 {
  const q = rotation(rot)
  const q00 = q.x * q.x, q11 = q.y * q.y, q22 = q.z * q.z, q33 = q.w * q.w
  const q01 = q.x * q.y, q02 = q.x * q.z, q03 = q.x * q.w
  const q12 = q.y * q.z, q13 = q.y * q.w, q23 = q.z * q.w
  const qd2 = 2.0 * (q13 - q02)
  let y: number, p: number, r: number
  // handle gimbal lock
  if (Math.abs(qd2 - 1.0) <= TOLERANCE) { // north pole
    y = 0.0; p = Math.PI / 2.0; r = 2.0 * Math.atan2(q.x, q.w)
  } else if (Math.abs(qd2 + 1.0) <= TOLERANCE) { // south pole
    y = 0.0; p = -Math.PI / 2.0; r = 2.0 * Math.atan2(q.x, q.w)
  } else {
    y = Math.atan2(2.0 * (q01 + q23), (q00 + q33) - (q11 + q22))
    p = qd2 > 1.0 ? Math.PI / 2.0 : qd2 < -1.0 ? -Math.PI / 2.0 : Math.asin(qd2)
    r = Math.atan2(2.0 * (q12 + q03), (q22 + q33) - (q00 + q11))
  }
  return [toDegrees(y), toDegrees(p), toDegrees(r)]
}

/** Rotation::EulerSequence, less Invalid. */
export type EulerSeq = 'EulerAngles' | 'YawPitchRoll'
  | 'Extrinsic_XYZ' | 'Extrinsic_XZY' | 'Extrinsic_YZX' | 'Extrinsic_YXZ' | 'Extrinsic_ZXY' | 'Extrinsic_ZYX'
  | 'Intrinsic_XYZ' | 'Intrinsic_XZY' | 'Intrinsic_YZX' | 'Intrinsic_YXZ' | 'Intrinsic_ZXY' | 'Intrinsic_ZYX'
  | 'Extrinsic_XYX' | 'Extrinsic_XZX' | 'Extrinsic_YZY' | 'Extrinsic_YXY' | 'Extrinsic_ZYZ' | 'Extrinsic_ZXZ'
  | 'Intrinsic_XYX' | 'Intrinsic_XZX' | 'Intrinsic_YZY' | 'Intrinsic_YXY' | 'Intrinsic_ZXZ' | 'Intrinsic_ZYZ'

/** EulerSequence_Parameters: the first rotation axis (1-3), whether the first two axes are an
 *  odd permutation (e.g. XZ), whether the third axis is the first again, whether extrinsic. */
type Params = { i: number; j: number; k: number; isOdd: boolean; isTwoAxes: boolean; isExtrinsic: boolean }
const params = (ax1: number, isOdd: boolean, isTwoAxes: boolean, isExtrinsic: boolean): Params => ({
  i: ax1, j: 1 + ((ax1 + (isOdd ? 1 : 0)) % 3), k: 1 + ((ax1 + (isOdd ? 0 : 1)) % 3), isOdd, isTwoAxes, isExtrinsic,
})
const F = false, T = true
// translateEulerSequence. Intrinsic rotations are extrinsic ones by the same angles in the
// inverted order: the sequence of axes is inverted here, the angles swapped (Alpha <-> Gamma)
// in the conversions. Proper Euler angles (the last blocks) are symmetric for the sequence.
const SEQUENCES: Record<EulerSeq, Params> = {
  Extrinsic_XYZ: params(1, F, F, T), Extrinsic_XZY: params(1, T, F, T), Extrinsic_YZX: params(2, F, F, T),
  Extrinsic_YXZ: params(2, T, F, T), Extrinsic_ZXY: params(3, F, F, T), Extrinsic_ZYX: params(3, T, F, T),
  Intrinsic_XYZ: params(3, T, F, F), Intrinsic_XZY: params(2, F, F, F), Intrinsic_YZX: params(1, T, F, F),
  Intrinsic_YXZ: params(3, F, F, F), Intrinsic_ZXY: params(2, T, F, F), Intrinsic_ZYX: params(1, F, F, F),
  Extrinsic_XYX: params(1, F, T, T), Extrinsic_XZX: params(1, T, T, T), Extrinsic_YZY: params(2, F, T, T),
  Extrinsic_YXY: params(2, T, T, T), Extrinsic_ZXZ: params(3, F, T, T), Extrinsic_ZYZ: params(3, T, T, T),
  Intrinsic_XYX: params(1, F, T, F), Intrinsic_XZX: params(1, T, T, F), Intrinsic_YZY: params(2, F, T, F),
  Intrinsic_YXY: params(2, T, T, F), Intrinsic_ZXZ: params(3, F, T, F), Intrinsic_ZYZ: params(3, T, T, F),
  EulerAngles: params(3, F, T, F), // = Intrinsic_ZXZ
  YawPitchRoll: params(1, F, F, F), // = Intrinsic_ZYX
}

/** Rotation::setEulerAngles (degrees). */
export function quatOfEuler([theAlpha, theBeta, theGamma]: Vec3, order: EulerSeq): THREE.Quaternion {
  const o = SEQUENCES[order]
  let a = toRadians(theAlpha), b = toRadians(theBeta), c = toRadians(theGamma)
  if (!o.isExtrinsic) [a, c] = [c, a]
  if (o.isOdd) b = -b
  const ti = 0.5 * a, tj = 0.5 * b, th = 0.5 * c
  const ci = Math.cos(ti), cj = Math.cos(tj), ch = Math.cos(th)
  const si = Math.sin(ti), sj = Math.sin(tj), sh = Math.sin(th)
  const cc = ci * ch, cs = ci * sh, sc = si * ch, ss = si * sh
  const values = [0, 0, 0, 0] // w, x, y, z
  if (o.isTwoAxes) {
    values[o.i] = cj * (cs + sc)
    values[o.j] = sj * (cc + ss)
    values[o.k] = sj * (cs - sc)
    values[0] = cj * (cc - ss)
  } else {
    values[o.i] = cj * sc - sj * cs
    values[o.j] = cj * ss + sj * cc
    values[o.k] = cj * cs - sj * sc
    values[0] = cj * cc + sj * ss
  }
  if (o.isOdd) values[o.j] = -values[o.j]
  return new THREE.Quaternion(values[1], values[2], values[3], values[0])
}

/** Rotation::getEulerAngles (degrees), from the matrix getValue(Matrix4D) makes. */
export function eulerOf(rot: Quat, order: EulerSeq): Vec3 {
  const q = rotation(rot)
  const l = Math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w)
  const x = q.x / l, y = q.y / l, z = q.z / l, w = q.w / l
  const m = [
    [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
    [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
    [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
  ]
  const M = (r: number, col: number) => m[r - 1][col - 1]
  const o = SEQUENCES[order]
  let theAlpha: number, theBeta: number, theGamma: number
  if (o.isTwoAxes) {
    const sy = Math.sqrt(M(o.i, o.j) * M(o.i, o.j) + M(o.i, o.k) * M(o.i, o.k))
    if (sy > TOLERANCE) {
      theAlpha = Math.atan2(M(o.i, o.j), M(o.i, o.k))
      theGamma = Math.atan2(M(o.j, o.i), -M(o.k, o.i))
    } else {
      theAlpha = Math.atan2(-M(o.j, o.k), M(o.j, o.j))
      theGamma = 0
    }
    theBeta = Math.atan2(sy, M(o.i, o.i))
  } else {
    const cy = Math.sqrt(M(o.i, o.i) * M(o.i, o.i) + M(o.j, o.i) * M(o.j, o.i))
    if (cy > TOLERANCE) {
      theAlpha = Math.atan2(M(o.k, o.j), M(o.k, o.k))
      theGamma = Math.atan2(M(o.j, o.i), M(o.i, o.i))
    } else {
      theAlpha = Math.atan2(-M(o.j, o.k), M(o.j, o.j))
      theGamma = 0
    }
    theBeta = Math.atan2(-M(o.k, o.i), cy)
  }
  if (o.isOdd) { theAlpha = -theAlpha; theBeta = -theBeta; theGamma = -theGamma }
  if (!o.isExtrinsic) [theAlpha, theGamma] = [theGamma, theAlpha]
  return [toDegrees(theAlpha), toDegrees(theBeta), toDegrees(theGamma)]
}
