// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerCarbonCopy.h: 2022 Abdullah Tahiri
// Sketcher_CarbonCopy's tool (DrawSketchHandlerCarbonCopy): the sketch picked (`cad gui select Sketch001`) copied into
// the one in edit (sketchcarbon.ts), if CarbonCopySelection lets it through, with its messages. Esc or a right click
// ends it.
import type { Geo } from './solver'
import * as S from './sketcher'
import type * as OPS from './sketchops'
import { DrawSketchHandler } from './sketchtools'
import { report, getState } from './store'
import { carbonCopy, carbonCopyAllowed, REASONS, type Placement } from './sketchcarbon'

// ── the tool (DrawSketchHandlerCarbonCopy) ───────────────────────────────────────────────────────────────────────
/** A Body's sketch: its geometry, constraints, external references and Placement (as the Sketcher opens it). */
export type SourceSketch = { doc: OPS.Doc; refs: [string, string][]; placement: Placement }
let sourceOf: ((part: string, name: string) => SourceSketch | null) | null = null
let reproject: ((refs: [string, string][]) => Promise<{ external: Geo[][]; errors: (string | null)[] } | null>) | null = null
/** sketchui.tsx hands the tool a Body's sketches and the server's projection. */
export function setCarbonSources(f: typeof sourceOf, p: typeof reproject) { sourceOf = f; reproject = p }

export class CarbonCopyHandler extends DrawSketchHandler {
  readonly toolName = 'DSH_CarbonCopy'
  private busy = false
  crosshair() { return 'Sketcher_Pointer_CarbonCopy' }
  hints() { return [{ message: '%1 pick sketch to copy', keys: ['LMB'] }] }
  activated() { S.clearSelection() }
  mouseMove() {}
  pressButton() { return true }
  releaseButton() { return true }
  pressRightButton() { S.purgeHandler() }
  registerPressedKey(pressed: boolean, key: string) { if (key === 'Escape') { if (!pressed) S.purgeHandler(); return true } return false }
  /** onSelectionChanged (AddSelection) of an object while the tool is on: a sketch is copied, if CarbonCopySelection
   *  lets it through. */
  pickNamed(obj: string, _sub: string): boolean {
    const sess = S.getSession(), part = sess?.ref.part
    if (!sess || !part || this.busy) return false
    const doc = getState().features[part]
    const f = doc?.features.find((x) => x.name === obj)
    if (!f) return false
    if (f.type !== 'Sketcher::SketchObject') { report('warn', 'Not allowed: Not a sketch'); return true }
    if (obj === sess.ref.name) return false
    // testIfLinkDAGCompatible: the source must not depend on this sketch
    if (S.dependsOnSketch(part, sess.ref.name, obj)) { report('warn', `Not allowed: ${REASONS.rlCircularReference}`); return true }
    const src = sourceOf?.(part, obj)
    if (!src) return false
    const ok = carbonCopyAllowed(sess.placement as Placement, src.placement)
    if ('reason' in ok) { report('warn', `Not allowed: ${REASONS[ok.reason]}`); return true }
    void this.copy(src, ok.xinv, ok.yinv)
    return true
  }
  private async copy(src: SourceSketch, xinv: boolean, yinv: boolean) {
    const ext = S.getExternal()
    for (const r of src.refs) if (ext.refs.some((e) => e[0] === r[0] && e[1] === r[1])) {
      report('err', `Link to ${r[1]} already exists in this sketch. Delete the link and try again`)
      report('err', 'Error: Failed to add carbon copy')
      return
    }
    this.busy = true
    // the source's references, projected onto this sketch (rebuildExternalGeometry)
    const proj = src.refs.length && reproject ? await reproject(src.refs) : { external: [], errors: [] }
    this.busy = false
    if (!S.isEditing() || !proj) return
    if (proj.errors.some((e) => e)) { report('err', 'Error: Failed to add carbon copy'); return }
    const d: OPS.Doc = { geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) }
    S.openCommand('Create a carbon copy')
    carbonCopy(d, src.doc, S.getSession()!.placement as Placement, xinv, yinv, S.isConstructionMode(), 2 + ext.geometry.length)
    S.setGeometry(d.geometry); S.setConstraints(d.constraints)
    src.refs.forEach((r, i) => S.addExternal(r, proj.external[i] ?? []))
    S.commitCommand()
    S.solve() // tryAutoRecomputeIfNotSolve
    S.clearSelection()
  }
}
