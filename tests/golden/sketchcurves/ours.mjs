// Runs the Sketcher's curve tools (bundled as engine.mjs by ui/scripts/sketchcurves-bundle.sh) over the cases of a
// file, the sketch kernel's answers from a second file (request JSON -> answer), the committed WebAssembly solver for
// the moves; prints {results, needs}: one result per case (null while it waits for the kernel) and the requests none
// of the answers cover (make.py answers them and runs this again):
//     node tests/golden/sketchcurves/ours.mjs tests/golden/sketchcurves/freecad.json kernel.json
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import createPlaneGCS from '../../../ui/planegcs/dist/planegcs.mjs'
import { runCase } from './engine.mjs'

const m = await createPlaneGCS({
  locateFile: (p) => fileURLToPath(new URL(`../../../ui/planegcs/dist/${p}`, import.meta.url)),
})
const solve = (json) => {
  const r = JSON.parse(m.ccall('pgcs_solve', 'string', ['string'], [json]))
  if (r.error) throw new Error(`planegcs: ${r.error}`)
  return r
}
const cases = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const answers = new Map(Object.entries(process.argv[3] ? JSON.parse(readFileSync(process.argv[3], 'utf8')) : {}))
const needs = new Set()
const results = cases.map((c) => {
  const r = runCase(c, solve, answers)
  for (const q of r.needs ?? []) needs.add(JSON.stringify(q))
  return r.result ?? null
})
process.stdout.write(JSON.stringify({ results, needs: [...needs] }))
