// SPDX-License-Identifier: LGPL-2.1-or-later
// exprdiff.py's other half: the same expressions through our evaluator (bundled by exprdiff.py with vite).
// usage: node scripts/exprdiff_ours.mjs BUNDLE CASES.json OUT.json
import fs from 'node:fs'
const [bundle, inPath, outPath] = process.argv.slice(2)
const { run } = await import(bundle)
const cases = JSON.parse(fs.readFileSync(inPath, 'utf8'))
fs.writeFileSync(outPath, JSON.stringify(cases.map((text) => run(text))))
