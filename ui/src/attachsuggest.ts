// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/App/Attacher.cpp: 2015 Victor Titov (DeepSOIC)
// AttachEngine::suggestMapModes, downgradeType, getTypeRank and isShapeOfType, as cad_agent/attacher.py has them (held to
// freecadcmd by tests/test_attacher.py): what the Attachment panel lists for references whose types the page knows,
// before the server's answer comes (the server's attacher stays the one that places).
import { ENGINE_MODES, MODE_REFS, REF_TYPES } from './attachmodes'

const FLAG = 0x100
const T = Object.fromEntries(REF_TYPES.map((n, i) => [n, i])) as Record<string, number>
export const refType = (name: string) => { const [b, f] = name.split('|'); return (T[b] ?? 0) | (f === 'Placement' ? FLAG : 0) }
export const refTypeName = (t: number) => REF_TYPES[t & 0xff] + (t & FLAG ? '|Placement' : '')

function downgrade(t: number): number {
  t &= FLAG - 1
  const n = REF_TYPES[t]
  if (['Vertex', 'Edge', 'Face', 'Any', 'Object'].includes(n)) return T.Any
  if (n === 'Line' || n === 'Curve') return T.Edge
  if (n === 'Conic' || n === 'Circle') return T.Curve
  if (['Ellipse', 'Parabola', 'Hyperbola'].includes(n)) return T.Conic
  if (['Plane', 'Sphere', 'Revolve'].includes(n)) return T.Face
  if (['Cylinder', 'Torus', 'Cone'].includes(n)) return T.Revolve
  if (n === 'Solid' || n === 'Wire') return T.Object
  throw new Error('AttachEngine::downgradeType: unknown type')
}
function rank(t: number) { t &= FLAG - 1; let r = 0; while (t !== T.Any) { t = downgrade(t); r++ } return r }
/** -1 no, 0 the topology fits but not the geometry, 1 and up yes (the higher the more specific). */
export function isShapeOfType(shape: number, req: number): number {
  if (req & FLAG && !(shape & FLAG)) return -1
  shape &= FLAG - 1; req &= FLAG - 1
  if (req === T.Any) return 1
  const r = rank(req)
  for (let d = shape; d !== T.Any; d = downgrade(d)) if (d === req) return r
  req = downgrade(req)
  if (req !== T.Any) for (let d = shape; d !== T.Any; d = downgrade(d)) if (d === req) return 0
  return -1
}
export type Suggestion = { message: string; best: string; all: string[]; reachable: Record<string, string[][]>; hints: string[]; types: string[] }
/** AttachEngine::suggestMapModes over the engine's modes in eMapMode order. */
export function suggest(engine: string, types: string[]): Suggestion {
  const ts = types.map(refType)
  let bestScore = -1, best = 'Deactivated', message = 'NoModesFit'
  const all: string[] = [], reachable: Record<string, string[][]> = {}, hints = new Set<number>()
  for (const m of ENGINE_MODES[engine].slice(1)) {
    for (const combo of MODE_REFS[engine][m]) {
      const s = combo.map(refType)
      let score = 1
      for (let k = 0; k < Math.min(s.length, ts.length); k++) {
        const match = isShapeOfType(ts[k], s[k])
        if (match === -1) { score = -1; break }
        if (match === 0) score = 0
        else if (match >= 2 && score > 0) score += match
      }
      if (score > 0 && s.length > ts.length) {
        hints.add(s[ts.length])
        ;(reachable[m] ??= []).push(s.slice(ts.length).map(refTypeName))
      }
      if (s.length !== ts.length) score = -1
      if (score > -1 && score > bestScore) { bestScore = score; best = m; message = score > 0 ? 'OK' : 'IncompatibleGeometry' }
      if (score > 0 && all[all.length - 1] !== m) all.push(m)
    }
  }
  for (const m of all) delete reachable[m]
  return { message, best, all, reachable, hints: [...hints].sort((a, b) => a - b).map(refTypeName), types: ts.map(refTypeName) }
}
