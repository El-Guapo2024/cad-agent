// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/App/AttachExtension.cpp: 2015 Victor Titov (DeepSOIC)
//   src/Mod/Sketcher/App/SketchObjectExternal.cpp: 2008 Jürgen Riegel
// Where the Body attaches each object (FreeCAD's AttachExtension::positionBySupport), as the server computes it:
// `cad feature list` and `cad feature apply` give a feature list `attached` (cad_agent/feature_attach.py's body_info)
// when the Body has a datum, a sketch on anything but an origin plane, or a sketch with external geometry. This module
// copies each object's entry onto its feature (`f.attached`), so the tree, the 3D view and the Sketcher read it there.
import * as THREE from 'three'
import type { Feature, FeatureDoc } from './store'

/** Base::Placement as the server writes it: position, quaternion (x, y, z, w), the 3x3 rotation, yaw-pitch-roll. */
export type PlacementData = { position: number[]; rotation: number[]; matrix: number[][]; ypr: number[] }
/** One object's attachment as the Body built it: its Placement, the MapMode it was attached with (a datum's best
 *  fit when the file names none), and a sketch's external geometry (SketchObject's ExternalGeo after the two axes:
 *  GeoId -3, -4, …), in planegcs's geometry form. */
export type Attached = { placement: PlacementData; map_mode?: string; external?: unknown[] }
export type AttachedDoc = { objects: Record<string, Attached>; error: string | null }

/** The doc with each feature's `attached` set from doc.attached (a doc without it is returned as it is). */
export function withAttached(doc: FeatureDoc): FeatureDoc {
  const att = (doc as FeatureDoc & { attached?: AttachedDoc }).attached
  if (!att?.objects) return doc
  return { ...doc, features: doc.features.map((f) => (att.objects[f.name] ? { ...f, attached: att.objects[f.name] } : f)) }
}
export function withAttachedAll(docs: Record<string, FeatureDoc>): Record<string, FeatureDoc> {
  return Object.fromEntries(Object.entries(docs).map(([k, d]) => [k, withAttached(d)]))
}
export const attachedOf = (f: Feature): Attached | undefined => f.attached as Attached | undefined
/** The Body's build error, if the server could not attach everything (what is attached before it still shows). */
export const attachError = (doc: FeatureDoc | undefined) => ((doc as (FeatureDoc & { attached?: AttachedDoc }) | undefined)?.attached?.error ?? null)

/** The datums a Body can hold: Part's, which FreeCAD 26.3's Edit > Create > Datums makes (Mod/Part/Gui/Command.cpp:
 *  Part_DatumPlane …, each opening its own transaction), and PartDesign's own (PartDesign::Plane …, no longer in
 *  the menus). kind is the part file's call, engine the attacher (AttacherType), base the name FreeCAD gives a new
 *  one (getUniqueObjectName), icon the tree's (the ViewProvider's sPixmap). */
export type DatumType = { kind: string; engine: '3D' | 'Plane' | 'Line' | 'Point'; base: string; icon: string; menu: string;
  cmd: string; txn: string; shape: 'plane' | 'line' | 'point' | 'lcs' | 'cs' }
export const DATUM_TYPES: Record<string, DatumType> = {
  'Part::LocalCoordinateSystem': { kind: 'LocalCoordinateSystem', engine: '3D', base: 'LCS', icon: 'std-origin', menu: 'Coordinate System', cmd: 'Part_CoordinateSystem', txn: 'Add coordinate system', shape: 'lcs' },
  'Part::DatumPlane': { kind: 'DatumPlane', engine: 'Plane', base: 'DatumPlane', icon: 'std-plane', menu: 'Datum Plane', cmd: 'Part_DatumPlane', txn: 'Add datum plane', shape: 'plane' },
  'Part::DatumLine': { kind: 'DatumLine', engine: 'Line', base: 'DatumLine', icon: 'std-axis', menu: 'Datum Line', cmd: 'Part_DatumLine', txn: 'Add datum line', shape: 'line' },
  'Part::DatumPoint': { kind: 'DatumPoint', engine: 'Point', base: 'DatumPoint', icon: 'std-point', menu: 'Datum Point', cmd: 'Part_DatumPoint', txn: 'Add datum point', shape: 'point' },
  'PartDesign::Plane': { kind: 'PartDesignPlane', engine: 'Plane', base: 'DatumPlane', icon: 'pd-datum-plane', menu: 'Datum Plane', cmd: 'PartDesign_Plane', txn: 'Create DatumPlane', shape: 'plane' },
  'PartDesign::Line': { kind: 'PartDesignLine', engine: 'Line', base: 'DatumLine', icon: 'pd-datum-line', menu: 'Datum Line', cmd: 'PartDesign_Line', txn: 'Create DatumLine', shape: 'line' },
  'PartDesign::Point': { kind: 'PartDesignPoint', engine: 'Point', base: 'DatumPoint', icon: 'pd-datum-point', menu: 'Datum Point', cmd: 'PartDesign_Point', txn: 'Create DatumPoint', shape: 'point' },
  'PartDesign::CoordinateSystem': { kind: 'PartDesignCoordinateSystem', engine: '3D', base: 'Local_CS', icon: 'pd-datum-cs', menu: 'Local Coordinate System', cmd: 'PartDesign_CoordinateSystem', txn: 'Create Local_CS', shape: 'cs' },
}
export const isDatum = (type: unknown): type is string => typeof type === 'string' && type in DATUM_TYPES
/** The Body's origin and a coordinate system's features, by role (App::LocalCoordinateSystem's roles). */
export const ROLES = ['X_Axis', 'Y_Axis', 'Z_Axis', 'XY_Plane', 'XZ_Plane', 'YZ_Plane', 'Origin']

/** A placement as a THREE.Matrix4 (the rotation's columns are the object's x, y and z, then its position). */
export function placementMatrix(p: PlacementData): THREE.Matrix4 {
  const [r0, r1, r2] = p.matrix
  return new THREE.Matrix4().set(r0[0], r0[1], r0[2], p.position[0], r1[0], r1[1], r1[2], p.position[1],
    r2[0], r2[1], r2[2], p.position[2], 0, 0, 0, 1)
}
