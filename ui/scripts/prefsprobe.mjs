// Opens the Preferences page of a scratch workbench and prints what a script in the page says: a debugging aid.
//   NODE_PATH=<folder with playwright> node ui/scripts/prefsprobe.mjs URL PROJECT PAGE_LABEL 'js expression'
import { createRequire } from 'module'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [BASE, PROJECT, LABEL, EXPR] = process.argv.slice(2)
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const ctx = await browser.newContext({ viewport: { width: 1400, height: 1100 }, deviceScaleFactor: 1 })
const p = await ctx.newPage()
p.on('pageerror', (e) => console.log('pageerror', e.message))
await p.goto(BASE.replace(/\/?$/, '/') + '#' + PROJECT, { waitUntil: 'load' })
await p.waitForTimeout(3000)
await p.evaluate(() => cadui.setState({ prefsOpen: true }))
await p.waitForSelector('.pref-dlg')
await p.evaluate((l) => { [...document.querySelectorAll('.pref-item')].filter((e) => e.textContent.trim() === l)[0].click() }, LABEL)
await p.waitForTimeout(700)
console.log(JSON.stringify(await p.evaluate(EXPR), null, 1))
await browser.close()
