// Runs ui/src/sketchxform.ts (bundled as engine.mjs by ui/scripts/sketchxform-bundle.sh) over the cases of a file and
// prints the answers as JSON, one per case:
//     node tests/golden/sketchxform/ours.mjs tests/golden/sketchxform/freecad.json
import { readFileSync } from 'node:fs'
import { runCase } from './engine.mjs'

const cases = JSON.parse(readFileSync(process.argv[2], 'utf8'))
process.stdout.write(JSON.stringify(cases.map((c) => runCase(c))))
