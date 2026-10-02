// Runs menudiff.js headless and prints its differences (fcref.py writes the reference first).
//   node ui/scripts/menurun.mjs [URL]     (default http://127.0.0.1:8733/next/#arduino_car)
// Point it at a workbench serving SCRATCH copies only. Needs Playwright, as keycheck.mjs.
import { createRequire } from 'module'
import { readFileSync } from 'fs'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [PAGE = 'http://127.0.0.1:8733/next/#arduino_car'] = process.argv.slice(2)
const code = readFileSync(new URL('./menudiff.js', import.meta.url), 'utf8')
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1400, height: 900 } })
await p.goto(PAGE, { waitUntil: 'load' })
await p.waitForTimeout(3000)
const rep = await p.evaluate((c) => eval('(async()=>{' + c + '})()'), code)
console.log(rep.length ? rep.join('\n') : 'menudiff: no differences')
console.log(`menudiff: ${rep.length} differences`)
await b.close()
