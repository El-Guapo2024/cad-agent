// Runs the committed WebAssembly build (ui/planegcs/dist) over the cases of a golden file, the way
// make.py's ours() runs the native one, and prints the answers as JSON, one per case:
//     node tests/golden/sketcher/ours_wasm.mjs tests/golden/sketcher/freecad.json
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import createPlaneGCS from '../../../ui/planegcs/dist/planegcs.mjs'

const m = await createPlaneGCS({
  locateFile: (p) => fileURLToPath(new URL(`../../../ui/planegcs/dist/${p}`, import.meta.url)),
})
const call = (name, ret, types, ...args) => m.ccall(name, ret, types, args)
const golden = JSON.parse(readFileSync(process.argv[2], 'utf8'))

const state = (r) => ({
  geometry: r.stored_geometry,
  constructions: r.stored_geometry.map((g) => g.construction ?? false),
  values: r.constraints.map((c) => c.value),
})

const out = golden.map((c) => {
  const h = call('pgcs_new', 'number', ['string'], JSON.stringify({ geometry: c.geometry, constraints: c.constraints }))
  if (!h) return { error: call('pgcs_last_error', 'string', []) }
  try {
    let r = JSON.parse(call('pgcs_handle_solve', 'string', ['number'], h))
    const res = {
      status: r.status_code, dof: r.dof,
      conflicting: r.conflicting.map((i) => i + 1), redundant: r.redundant.map((i) => i + 1),
      partially_redundant: r.partially_redundant.map((i) => i + 1), malformed: r.malformed.map((i) => i + 1),
      ...state(r), drags: [],
    }
    for (const d of c.drags) {
      r = JSON.parse(call('pgcs_move_geometry', 'string', ['number', 'string', 'number', 'number', 'number'],
        h, JSON.stringify([[d.geo, d.pos]]), d.to[0], d.to[1], d.relative ? 1 : 0))
      res.drags.push({ ok: r.status_code === 0, ...state(r) })
    }
    return res
  } finally {
    call('pgcs_free', null, ['number'], h)
  }
})
process.stdout.write(JSON.stringify(out))
