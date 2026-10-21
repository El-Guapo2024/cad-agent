// SPDX-License-Identifier: LGPL-2.1-or-later
// A machine's named poses (assembly.py's POSES) in the 3D view. A pose is a position in mm for each of some
// axes (AXES); the machine at that pose is every body an axis carries slid along that axis's direction by its
// position, the sums of all the axes that carry it. That is `cad_agent/motion.py`'s `pose` and
// `subassembly.apply_pose`, line for line: the axis's unit direction times the position, translations added
// whatever the order. tests/test_workbench.py holds this arithmetic to apply_pose's on the mini_machine fixture.
// FreeCAD has no equivalent (an Assembly has joints, whose values a solve moves; a pose here is a declared set of
// them), so the command is ours: CADAgent_Pose.
import type { Scene, Vec3 } from './api'

/** The pose names a scene declares, in the order assembly.py wrote them. */
export const poseNames = (sc: Scene | null | undefined): string[] => Object.keys(sc?.poses ?? {})

/** How far each body moves in the world at pose `name` (a body no axis carries is not in the answer). */
export function poseOffsets(sc: Scene, name: string): Record<string, Vec3> {
  const out: Record<string, Vec3> = {}
  const pose = sc.poses?.[name]
  if (!pose) return out
  for (const [axisName, position] of Object.entries(pose)) {
    const axis = sc.axes?.find((a) => a.name === axisName)
    if (!axis) continue
    const len = Math.hypot(...axis.direction)
    if (!len) continue
    const step = axis.direction.map((c) => (c / len) * position) as Vec3
    for (const body of axis.moves) {
      const was = out[body] ?? [0, 0, 0]
      out[body] = [was[0] + step[0], was[1] + step[1], was[2] + step[2]]
    }
  }
  return out
}

/** One line for the Report view: where a pose puts each axis it names. */
export function poseText(sc: Scene, name: string): string {
  const at = Object.entries(sc.poses?.[name] ?? {}).map(([axis, position]) => `${axis} ${Number(position.toFixed(3))} mm`)
  return at.length ? at.join(', ') : 'no axis'
}
