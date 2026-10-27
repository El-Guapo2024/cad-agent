// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Assembly/App/AssemblyObject.cpp: 2023 Ondsel <development@ondsel.com>
//
// The Assembly workbench's solver in the browser: OndselSolver (FreeCAD's submodule at 4be80eef02a3, unchanged)
// with the solving half of AssemblyObject.cpp ported in front of it (ui/ondsel), compiled to WebAssembly
// (ui/ondsel/build.sh wasm writes ui/ondsel/dist). cad_agent/ondsel.py runs the same code natively, and
// tests/test_assembly_golden.py holds it to FreeCAD's answers. ui/ondsel/api.cpp describes the JSON in full; a
// document is what the server's /api/<slug>/assembly gives as "solver".

import createOndsel from '../ondsel/dist/ondsel.mjs'
import wasmUrl from '../ondsel/dist/ondsel.wasm?url'

export type Vec3 = [number, number, number]
// FreeCAD's Placement: Base, and Rotation.Q (x, y, z, w)
export interface Plc { base: Vec3; rotation: [number, number, number, number] }
export interface AsmRef { part: string; subs: string[]; geom: string; radius: number; obj?: Plc }
export interface AsmJoint {
  name: string; label?: string; type: string; suppressed?: boolean
  reference1: AsmRef | null; reference2: AsmRef | null; placement1: Plc; placement2: Plc
  distance?: number; distance2?: number; angle?: number
  enable_length_min?: boolean; enable_length_max?: boolean; enable_angle_min?: boolean; enable_angle_max?: boolean
  length_min?: number; length_max?: number; angle_min?: number; angle_max?: number
}
export interface AsmDoc {
  document?: string; origin?: string
  parts: { name: string; label?: string; placement: Plc; grounded?: boolean }[]
  joints: AsmJoint[]
  rigid_groups?: { name: string; suppressed?: boolean; members: string[] }[]   // the RigidGroupJoints
  rigid_cache?: [string, Plc][]                                               // AssemblyObject::rigidPlacementCache
}
export interface AsmResult {
  status: number           // AssemblyObject::solve()'s return: 0, -1 failed, -6 nothing grounded
  solver_status: number
  dof: number
  redundant: string[]
  placements: Record<string, Plc>
  joints: AsmJoint[]
  swapped: string[]
  dragged: string[]
  drag_failed: boolean
  warnings: string[]
  errors: string[]
  log: string
}
export interface AsmDrag {
  // the view provider's new placements for the dragged parts, one mouse move; the solve's answer back
  step(placements: Record<string, Plc>): AsmResult
  // a rigid group's member dragged: the placements, then a full solve (forceSolveOnMoveForRigid)
  rigidStep(placements: Record<string, Plc>): AsmResult
  end(): AsmResult
  dragged: string[]
}
export interface AsmSolver {
  solve(doc: AsmDoc): AsmResult
  query(doc: AsmDoc, op: string, ...args: string[]): unknown
  // AssemblyObject::preDrag(parts); the result's "dragged" are the parts the solver moves
  drag(doc: AsmDoc, parts: string[]): AsmDrag
}

type Module = {
  ccall: (name: string, ret: string | null, types: string[], args: unknown[]) => unknown
}

function parse<T>(raw: unknown): T {
  const out = JSON.parse(raw as string)
  if (out.error) throw new Error(`ondsel: ${out.error}`)
  return out as T
}

let loading: Promise<AsmSolver> | undefined

export function loadAssemblySolver(): Promise<AsmSolver> {
  loading ??= (async () => {
    const m: Module = await createOndsel({ locateFile: () => wasmUrl })
    const call = (name: string, ret: string | null, types: string[], ...args: unknown[]) =>
      m.ccall(name, ret, types, args)
    return {
      solve(doc: AsmDoc): AsmResult {
        return parse<AsmResult>(call('ondsel_solve', 'string', ['string'], JSON.stringify(doc)))
      },
      query(doc: AsmDoc, op: string, ...args: string[]): unknown {
        return parse<{ value: unknown }>(call('ondsel_query', 'string', ['string', 'string', 'string'],
          JSON.stringify(doc), op, JSON.stringify(args))).value
      },
      drag(doc: AsmDoc, parts: string[]): AsmDrag {
        const h = call('ondsel_new', 'number', ['string'], JSON.stringify(doc)) as number
        if (!h) throw new Error(`ondsel: ${call('ondsel_last_error', 'string', [])}`)
        let open = true
        let pre: AsmResult
        try {
          pre = parse<AsmResult>(call('ondsel_pre_drag', 'string', ['number', 'string'], h, JSON.stringify(parts)))
        } catch (e) {
          call('ondsel_free', null, ['number'], h)
          throw e
        }
        return {
          dragged: pre.dragged,
          step(placements: Record<string, Plc>): AsmResult {
            if (!open) throw new Error('ondsel: drag already ended')
            return parse<AsmResult>(call('ondsel_drag_step', 'string', ['number', 'string'], h, JSON.stringify(placements)))
          },
          rigidStep(placements: Record<string, Plc>): AsmResult {
            if (!open) throw new Error('ondsel: drag already ended')
            return parse<AsmResult>(call('ondsel_rigid_step', 'string', ['number', 'string'], h, JSON.stringify(placements)))
          },
          end(): AsmResult {
            if (!open) throw new Error('ondsel: drag already ended')
            open = false
            const out = parse<AsmResult>(call('ondsel_post_drag', 'string', ['number'], h))
            call('ondsel_free', null, ['number'], h)
            return out
          },
        }
      },
    }
  })()
  return loading
}
