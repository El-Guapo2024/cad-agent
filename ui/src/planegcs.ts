// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/Sketch.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObject.cpp: 2008 Jürgen Riegel
//
// The Sketcher's solver in the browser: FreeCAD's PlaneGCS and its Sketch.cpp, ported in
// ui/planegcs and compiled to WebAssembly (ui/planegcs/build.sh wasm writes ui/planegcs/dist).
// It answers as FreeCAD 26.3 (3160daf1e2b6) does; tests/test_planegcs.py holds the same code,
// built natively, to FreeCAD's recorded answers. cad_agent/planegcs.py takes and returns the same
// objects from Python. ui/planegcs/api.cpp describes the JSON in full.

import createPlaneGCS from '../planegcs/dist/planegcs.mjs'
import wasmUrl from '../planegcs/dist/planegcs.wasm?url'

export type XY = [number, number]
export type Geo =
  | { type: 'Point'; at: XY; construction?: boolean }
  | { type: 'LineSegment'; start: XY; end: XY; construction?: boolean }
  | { type: 'Circle'; center: XY; radius: number; construction?: boolean }
  | { type: 'ArcOfCircle'; center: XY; radius: number; start_angle: number; end_angle: number; construction?: boolean }
// FreeCAD's Sketcher.Constraint argument list after the type, value last when it has one, e.g.
// { type: 'DistanceX', args: [0, 1, 0, 2], value: 40 }; driving false = reference constraint.
// Extensions: active false switches a constraint off (Sketcher.Constraint's activated argument);
// orientation is FreeCAD's ConstraintOrientations flags (1 ccw, 2 cw, 4 internal, 8 external) of
// a Distance or Tangent, computed from the geometry when left out, as FreeCAD does on adding.
export type Cons = {
  type: string; args: number[]; value?: number; driving?: boolean; name?: string
  active?: boolean; orientation?: number
}
export type Sketch = { geometry: Geo[]; constraints: Cons[] }
export type Status = 'solved' | 'failed' | 'conflicting' | 'redundant' | 'malformed'
// Constraint indices are 0-based (FreeCAD's messages count from 1).
export interface SolveResult {
  status: Status
  geometry: Geo[]          // the solver's geometry: what the Sketcher draws
  dof: number
  conflicting: number[]
  redundant: number[]
  partially_redundant: number[]
  malformed: number[]
  // Extensions:
  status_code?: number     // SketchObject.solve()'s: 0, -1 solver error, -2 redundant, -3 conflicting, -4 over-constrained, -5 malformed
  status_name?: string
  solver_status?: number   // GCS: 0 success, 1 converged, 2 failed, 3 invalid geometry
  move_status?: number     // a drag step's GCS status (0: the geometry followed)
  fully_constrained?: boolean
  stored_geometry?: Geo[]  // what FreeCAD keeps in the sketch: updated only when a solve succeeds
  constraints?: { type: string; value: number; orientation: number; driving: boolean; active: boolean; name?: string }[]
  dependent?: [number, number, number][]          // (geoId, pos, index) of parameters still free
  dependency_groups?: [number, number][][]
}
export interface Drag { move(to: XY, relative?: boolean): SolveResult; end(): void }
export interface Solver { solve(s: Sketch): SolveResult; drag(s: Sketch, geoId: number, pos: number): Drag }

type Module = {
  ccall: (name: string, ret: string | null, types: string[], args: unknown[]) => unknown
}

function parse(raw: unknown): SolveResult {
  const out = JSON.parse(raw as string)
  if (out.error) throw new Error(`planegcs: ${out.error}`)
  return out as SolveResult
}

let loading: Promise<Solver> | undefined

export function loadSolver(): Promise<Solver> {
  loading ??= (async () => {
    const m: Module = await createPlaneGCS({ locateFile: () => wasmUrl })
    const call = (name: string, ret: string | null, types: string[], ...args: unknown[]) =>
      m.ccall(name, ret, types, args)
    return {
      solve(s: Sketch): SolveResult {
        return parse(call('pgcs_solve', 'string', ['string'], JSON.stringify(s)))
      },
      // Solve, then start dragging point `pos` of geometry `geoId` (pos 0: the edge), as the
      // Sketcher does on mouse down; each move() is one mouse move.
      drag(s: Sketch, geoId: number, pos: number): Drag {
        const h = call('pgcs_new', 'number', ['string'], JSON.stringify(s)) as number
        if (!h) throw new Error(`planegcs: ${call('pgcs_last_error', 'string', [])}`)
        let open = true
        try {
          parse(call('pgcs_handle_solve', 'string', ['number'], h))
          parse(call('pgcs_init_move', 'string', ['number', 'string'], h, JSON.stringify([[geoId, pos]])))
        } catch (e) {
          call('pgcs_free', null, ['number'], h)
          throw e
        }
        return {
          move(to: XY, relative = false): SolveResult {
            if (!open) throw new Error('planegcs: drag already ended')
            return parse(call('pgcs_move', 'string', ['number', 'number', 'number', 'number'], h, to[0], to[1], relative ? 1 : 0))
          },
          end(): void {
            if (!open) return
            open = false
            call('pgcs_end_move', null, ['number'], h)
            call('pgcs_free', null, ['number'], h)
          },
        }
      },
    }
  })()
  return loading
}
