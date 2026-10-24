// Runs ui/src/sketchops.ts (bundled as engine.mjs by ui/scripts/sketchops-bundle.sh) over the cases of a file, with
// the committed WebAssembly solver for the moves, and prints the answers as JSON, one per case:
//     node tests/golden/sketchops/ours.mjs tests/golden/sketchops/freecad.json
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
process.stdout.write(JSON.stringify(cases.map((c) => runCase(c, solve))))
