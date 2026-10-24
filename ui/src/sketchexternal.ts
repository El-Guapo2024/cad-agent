// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerExternal.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/CommandCreateGeo.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectExternal.cpp: 2008 Jürgen Riegel
// Sketcher_Projection (External Projection, G X): DrawSketchHandlerExternal with its ExternalSelection gate. While it
// is on, the Body's faces, edges and vertices shown in the 3D view preselect under the cursor; a click adds the element
// as external geometry ("Add external geometry", SketchObject::addExternal), its projection onto the sketch's plane
// computed as rebuildExternalGeometry does it, by the server (`cad feature project`, cad_agent/feature_attach.py). The
// tool stays on until Esc or a right click, as FreeCAD's does.
import * as S from './sketcher'
import type { Geo, XY } from './solver'
import { api, resultText } from './api'
import { getState, report, setState } from './store'
import { getView, preselect } from './actions'

/** ExternalSelection::allow and isExternalAllowed: what the Sketch may take, as [feature, element], or why not. */
export function externalAllowed(body: string, sub: string | null): { ref: [string, string] } | { why: string } | null {
  const sess = S.getSession(), st = getState()
  if (!sess) return null
  const part = sess.ref.part
  const b = st.scene?.bodies.find((x) => x.name === body)
  if (!b) return null
  // rlOtherBody: an object of another Body (another part module) cannot be linked
  if (!part || b.part !== part) return { why: 'This object belongs to another body, can\'t link.' }
  // ExternalSelection::allow: an element of the shape (Edge, Vertex, Face), not the whole object
  if (!sub || !/^(Edge|Vertex|Face)\d+$/.test(sub)) return null
  const doc = st.features[part]
  if (!doc) return null
  // the scene draws the Body as its Tip's solid: the element is that feature's (or the BaseFeature's)
  const feature = S.shownSolid(part)
  if (!feature) return null
  // rlCircularReference: the Tip depends on the sketch (it, or a feature before it, uses the sketch)
  if (S.dependsOnSketch(part, sess.ref.name)) return { why: 'Linking this will cause circular dependency.' }
  return { ref: [feature, sub] }
}

/** The projections of references onto the sketch in edit (`cad feature project`), one list per reference. */
export async function projectRefs(refs: [string, string][], part = S.getSession()?.ref.part, sketch = S.getSession()?.ref.name): Promise<{ external: Geo[][]; errors: (string | null)[] } | null> {
  const slug = getState().slug
  if (!slug || !part || !sketch) return null
  const args = ['feature', 'project', slug, part, sketch, ...refs.flatMap((r) => ['--ref', r[1] ? `${r[0]}.${r[1]}` : r[0]])]
  const r = await api.cad(slug, args)
  if (r.exit !== 0 || !r.data) { report('err', `External geometry: ${resultText(r)}`); return null }
  return { external: (r.data.external ?? []) as Geo[][], errors: (r.data.errors ?? []) as (string | null)[] }
}

export class ExternalHandler implements S.Handler {
  readonly toolName = 'DSH_External'
  private hover: { body: string; sub: string } | null = null
  private busy = false
  activated() { S.clearSelection() }
  deactivated() { this.hover = null; preselect(null, null); setState({ gateMsg: null }) }
  /** The 3D element under the cursor, preselected if the gate lets it through (Gui::Selection's preselection). */
  mouseMove(pos: XY) {
    const [x, y] = S.toScreen(pos)
    const h = getView()?.sceneHitAt(x, y) ?? null
    const ok = h ? externalAllowed(h.body, h.sub) : null
    if (ok && 'why' in ok) {
      this.hover = null
      preselect(null, null)
      const msg = `Not allowed: ${ok.why}`
      if (getState().gateMsg !== msg) setState({ gateMsg: msg })
      return
    }
    if (getState().gateMsg) setState({ gateMsg: null })
    if (ok && h?.sub) { this.hover = { body: h.body, sub: h.sub }; preselect(h.body, null, h.sub) }
    else { this.hover = null; preselect(null, null) }
  }
  pressButton() { return true }
  /** A click: the element under the cursor is selected, which onSelectionChanged takes (below). */
  releaseButton(): boolean {
    const h = this.hover
    if (!h || this.busy) return true
    const ok = externalAllowed(h.body, h.sub)
    if (ok && !('why' in ok)) void this.add(ok.ref)
    return true
  }
  /** Gui.Selection.addSelection(doc, "Pad", "Edge4") while the tool is on (`cad gui select Pad.Edge4`): the gate's
   *  rules for an object named, then the same as a click. */
  pickNamed(obj: string, sub: string): boolean {
    const sess = S.getSession(), part = sess?.ref.part
    const doc = part ? getState().features[part] : undefined
    if (!sess || !doc || !/^(Edge|Vertex|Face)\d+$/.test(sub)) return false
    if (obj !== 'BaseFeature' && !doc.features.some((f) => f.name === obj && f.name !== sess.ref.name)) return false
    if (S.dependsOnSketch(part!, sess.ref.name, obj)) { report('warn', 'Linking this will cause circular dependency.'); return true }
    void this.add([obj, sub])
    return true
  }
  /** onSelectionChanged (AddSelection): the element becomes external geometry, in its own command. */
  private async add(ref: [string, string]) {
    if (S.getExternal().refs.some((r) => r[0] === ref[0] && r[1] === ref[1])) return
    this.busy = true
    await projectRefs([ref]).then((p) => {
      this.busy = false
      if (!S.isEditing() || !p) return
      const geos = p.external[0] ?? [], err = p.errors[0]
      if (err || !geos.length) { report('err', `Failed to add external geometry${err ? `: ${err}` : ''}`); return }
      S.openCommand('Add external geometry')
      S.addExternal(ref, geos)
      S.commitCommand()
      S.solve() // tryAutoRecomputeIfNotSolve
      preselect(null, null)
    })
    return true
  }
  pressRightButton() { S.purgeHandler() }
  registerPressedKey(pressed: boolean, key: string) { if (key === 'Escape') { if (!pressed) S.purgeHandler(); return true } return false }
  cursor() { return { svg: 'Sketcher_Pointer_External', tail: [] } }
  hints() { return [{ message: '%1 pick external geometry', keys: ['LMB'] }] }
}
