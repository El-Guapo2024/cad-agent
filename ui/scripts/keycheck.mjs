// Presses every default shortcut (keymap.ts's table, the standard views 0-6 and draw styles
// V,1-V,7) in a running workbench and checks each one ran a command: with "Show script commands
// in Python console" on, every command leaves its line in the Console.
//   node ui/scripts/keycheck.mjs [URL] [PROJECT] [PART]
// Point it at a workbench serving SCRATCH copies only: it recomputes, undoes and toggles things.
// Needs Playwright (npm i -g playwright, or NODE_PATH to one) with a Chromium.
import { createRequire } from 'module'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const [BASE = 'http://127.0.0.1:8733/next/', PROJECT = 'arduino_car', PART = 'chassis'] = process.argv.slice(2)
const src = readFileSync(fileURLToPath(new URL('../src/keymap.ts', import.meta.url)), 'utf8')
const base = src.slice(src.indexOf('const BASE_ACCEL'), src.indexOf('let accel'))
const table = [...base.matchAll(/(\w+): '([^']+)'/g)].map((m) => [m[1], m[2]])
for (const [k, c] of [['0', 'Std_ViewIsometric'], ['1', 'Std_ViewFront'], ['2', 'Std_ViewTop'], ['3', 'Std_ViewRight'], ['4', 'Std_ViewRear'], ['5', 'Std_ViewBottom'], ['6', 'Std_ViewLeft']]) table.push([c, k])
for (let i = 1; i <= 7; i++) table.push([`Std_DrawStyle#${i}`, `V, ${i}`])
const KEY = { Return: 'Enter', Left: 'ArrowLeft', Right: 'ArrowRight', Up: 'ArrowUp', Down: 'ArrowDown', ',': 'Comma', '+': 'Equal', '-': 'Minus', Space: 'Space' }
const chord = (c) => { const parts = c.endsWith('++') ? [...c.slice(0, -2).split('+'), '+'] : c.split('+'); const key = parts.pop(); return [...parts.map((m) => (m === 'Ctrl' ? 'Control' : m)), KEY[key] ?? (key.length === 1 ? key.toLowerCase() : key)].join('+') }
const b = await chromium.launch()
const p = await b.newPage({ viewport: { width: 1400, height: 900 } })
const errs = []; p.on('pageerror', (e) => errs.push(e.message))
await p.goto(BASE, { waitUntil: 'load' })
await p.waitForTimeout(2500)
await p.getByText(`${PROJECT} : 1`).click(); await p.waitForTimeout(1500)
await p.getByText('Console', { exact: true }).first().click()
const results = []
for (const [cmd, seq] of table) {
  await p.locator('.trow', { hasText: PART }).first().click()
  await p.evaluate(() => (document.activeElement)?.blur?.())
  await p.waitForTimeout(100)
  const before = await p.locator('.console .cl:not(.cinput)').allInnerTexts(); const e0 = errs.length
  for (const c of seq.split(', ')) await p.keyboard.press(chord(c))
  await p.waitForTimeout(250)
  const after = await p.locator('.console .cl:not(.cinput)').allInnerTexts()
  const added = after.slice(before.length).map((t) => t.replace(/\s+/g, ' ').trim()).filter((t) => t.startsWith('>>>')).map((t) => t.replace(/^>>> /, ''))
  results.push(`${errs.length > e0 ? 'ERR' : ''}${added.length ? 'OK ' : 'NO '} ${cmd.padEnd(32)} ${seq.padEnd(14)} ${added.join(' | ').slice(0, 90)}`)
  // put things back: dialogs, tasks, toggles
  for (const t of ['Cancel', 'Close']) { const d = p.locator('.pref-dlg, .cu-dlg, .msgbox').getByText(t, { exact: true }); if (await d.count()) await d.first().click() }
  await p.keyboard.press('Escape'); await p.keyboard.press('Escape')
  if (/Overlay|BottomPanels|Fullscreen|DockOverlayMouse|BoxSelection|BoxElement|ViewBoxZoom/.test(cmd)) { for (const c of seq.split(', ')) await p.keyboard.press(chord(c)); await p.keyboard.press('Escape') }
  await p.waitForTimeout(150)
  if (errs.length > e0) results.push(`   ^ errors during ${cmd} (incl. putting back): ${errs.slice(e0).join(' / ').slice(0, 120)}`)
}
console.log(results.join('\n'))
const bad = results.filter((r) => !r.startsWith('OK')).length + errs.length
console.log(`keycheck: ${results.filter((r) => r.startsWith('OK')).length} fired, ${bad} problems`)
process.exitCode = bad ? 1 : 0
await b.close()
