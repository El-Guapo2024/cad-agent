// Dumps every Preferences page's strings from the dialog's off-screen search index, for prefdiff.py.
//   node ui/scripts/prefdump.mjs [URL] [OUT]   (default http://127.0.0.1:8733/next/, prefs-dump.json)
// Point it at a workbench serving SCRATCH copies only. Needs Playwright, as keycheck.mjs.
import { createRequire } from 'module'
import { writeFileSync } from 'fs'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [PAGE = 'http://127.0.0.1:8733/next/', OUT = 'prefs-dump.json'] = process.argv.slice(2)
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1400, height: 900 } })
await p.goto(PAGE, { waitUntil: 'load' })
await p.waitForTimeout(2500)
await p.keyboard.press('Control+Comma')
await p.waitForSelector('.pref-dlg', { timeout: 5000 })
const data = await p.evaluate(() => {
  const out = {}
  for (const el of document.querySelectorAll('.pref-index [data-page]')) {
    const texts = new Set()
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    while (w.nextNode()) { const t = w.currentNode.textContent.replace(/\s+/g, ' ').trim(); if (t) texts.add(t) }
    for (const o of el.querySelectorAll('option')) texts.add(o.textContent.trim())
    for (const i of el.querySelectorAll('[placeholder]')) texts.add(i.getAttribute('placeholder'))
    for (const i of el.querySelectorAll('input[value]:not([type=checkbox]):not([type=radio])')) texts.add(i.value)
    for (const l of el.querySelectorAll('label, legend, button, th, span, p')) { const t = l.textContent.replace(/\s+/g, ' ').trim(); if (t && t.length < 200) texts.add(t) }
    out[el.dataset.page] = [...texts]
  }
  return out
})
writeFileSync(OUT, JSON.stringify(data, null, 1))
console.log(`prefdump: ${Object.keys(data).length} pages -> ${OUT}`)
await b.close()
