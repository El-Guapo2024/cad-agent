// Is every button in the workbench wired? Lists every clickable control, clicks each enabled one in a scratch workbench, and says
// what it did: the menu bar's menus and sub-menus, every toolbar button and drop-down, the right-click menus (the tree, the 3D view,
// the Report view, the console, the property and selection views, the NaviCube, the status bar, the notification list), the docks'
// tabs and title-bar buttons, the status bar's widgets, the buttons of every task panel, the Start page, and the Preferences and
// Customize dialogs with their pages. Then the flows that only a filled-in form or a made edit enables: Placement and a parameter
// through the property view with Undo and Redo, New Document and Open, a recorded macro and the Macros task, the Library task, a
// drawing and its tab, Evals, BOM, the Expression Editor, Customize's toolbars and macros, the Keyboard page.
//
//   node ui/scripts/wirecheck.mjs [URL PROJECTS_ROOT] [options]
//     --only=menus,toolbars,docks,status,tree,properties,panels,view3d,customize,customizeflow,start,notifications,msgbox,
//            expression,prefs,keyboard,tasks,params,macros,library,drawing,evals,shop,opendoc,newdoc,edits    (default: all)
//     --top=File,Edit,...    only these menus (with --only=menus)         --task=A|B    only the tasks whose menu path has A or B
//     --toolbar=A|B          only the toolbar buttons whose name has A or B (with --only=toolbars)
//     --entry=A|B            only the menu entries whose path has A or B (with --only=menus)
//     --forms                also the check boxes, radio buttons, combo boxes, colours and sliders of the panels (buttons only otherwise)
//     --project=NAME         the project the page opens (mini_machine)    --viewport=1400x900
//     --json=FILE            every control with its class, command id and what it did      --verbose  every row, with its timing
//     --debug-dom            where the page's DOM differed when that was all a click did
//
// With no URL it starts a scratch workbench of its own on a free port (never 8733, 8734, 8740 or 8792), on copies of
// tests/fixtures (mini_machine, mini_gantry, assembly_cell) and projects/arduino_car, with every CAD_* path in a scratch folder and
// the CPU renderer for the checks' pictures, and stops it again (its warm worker too). With a URL it drives that workbench instead:
// it must serve SCRATCH copies only (this script deletes, closes and undoes), and PROJECTS_ROOT is the folder it serves.
//
// What it does to a control: it puts the page in a known state (a selection, a quiet camera), clicks the control the way a person
// does (a menu is opened, a sub-menu hovered, then the entry clicked), waits for the page to be quiet, and compares a fingerprint
// of the page before and after: the store (selection, task, draw style, ...), the camera, the DOM, the Report view and console
// lines, localStorage, the /api calls the page made, downloads, pop-ups and clipboard writes, the values and selected text of the
// fields, a link to another tab, the draws of a dialog's preview, the state the view keeps for itself (the NaviCube's movable flag,
// the Transform dragger) and a menu entry's check mark flipping. An entry with an expectation (the camera looks the way FreeCAD's
// Camera.cpp says a Front view does, the store has `drawStyle: wireframe`) must also meet it. A right click that opens two menus,
// or the menu of the surface it sits in, is WRONG as well. Everything takes about an hour and a half on SwiftShader (the menus a
// quarter of it, the task panels another quarter), so --only picks the part to look at; the sections do not depend on each other.
//
// Classes (the summary is at the end of the output; the exit code is 1 when there is a NO-OP, ERROR or WRONG):
//   WORKS  it did what its label says (a camera turn, a store change, a task or dialog, a /api call, a download, a Report line)
//   N/A    disabled, with a reason in its tooltip or in PARITY.md; or enabled and by design the current choice of a pair
//   NO-OP  enabled, and nothing happened                       (a bug)
//   ERROR  a console error or an exception, or a control that cannot be reached     (a bug)
//   WRONG  it did something else than its label says            (a bug)
//   HUMAN  not clicked: approving, `lib fetch` and `eval run` stay a person's call
//
// It never presses Approve Renders' Yes, never approves, never runs `lib fetch` or `eval run`: those requests are refused at the
// network layer too. Downloads go to the scratch folder, Finder is not opened (the request is stubbed) and nothing leaves the
// machine (pop-ups and outside requests are refused). View animations are off here (cubecheck.mjs covers them) and so are CSS
// animations, which keep a browser drawing for as long as a check runs. It drives Chromium through Playwright's protocol, so the real
// mouse pointer never moves. Needs Playwright (NODE_PATH to one) with a Chromium; uses ANGLE's SwiftShader as keycheck.mjs does.
import { createRequire } from 'module'
import { spawn, spawnSync } from 'child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { createServer } from 'net'
import { tmpdir } from 'os'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..', '..')
const args = process.argv.slice(2)
const flag = (name, d) => { const a = args.find((x) => x.startsWith(`--${name}=`)); return a ? a.slice(name.length + 3) : d }
const positional = args.filter((x) => !x.startsWith('--'))
const ONLY = flag('only', '') ? flag('only', '').split(',') : null
const JSON_OUT = flag('json', '')
const PROJECT = flag('project', 'mini_machine')
const VERBOSE = args.includes('--verbose')
const DEBUG_DOM = args.includes('--debug-dom')
const want = (section) => !ONLY || ONLY.includes(section)
const FORBIDDEN_PORTS = new Set([8733, 8734, 8740, 8792])
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// ── a scratch workbench of our own, unless a URL was given ──────────────────────────────────────────────────────────
let BASE = positional[0] ?? '', ROOT = positional[1] ?? ''
let server = null, scratch = '', warmDir = '', env = {}
const freePort = (from) => new Promise((ok, no) => {
  const tryPort = (p) => {
    if (p > from + 40) return no(new Error('no free port'))
    if (FORBIDDEN_PORTS.has(p)) return tryPort(p + 1)
    const s = createServer()
    s.once('error', () => tryPort(p + 1)); s.once('listening', () => s.close(() => ok(p))); s.listen(p, '127.0.0.1')
  }
  tryPort(from)
})
async function startWorkbench() {
  scratch = mkdtempSync(join(tmpdir(), 'cad-wirecheck-'))
  warmDir = mkdtempSync('/tmp/cwc')           // short: macOS caps a socket path at 104 bytes
  ROOT = join(scratch, 'root'); mkdirSync(ROOT)
  for (const p of ['mini_machine', 'mini_gantry', 'assembly_cell']) cpSync(join(REPO, 'tests', 'fixtures', p), join(ROOT, p), { recursive: true })
  cpSync(join(REPO, 'projects', 'arduino_car'), join(ROOT, 'arduino_car'), { recursive: true })
  for (const d of ['runtime', 'macros', 'library']) mkdirSync(join(scratch, d))
  const python = process.env.CAD_PYTHON || join(REPO, '.venv', 'bin', 'python')
  const port = await freePort(8861)
  env = { ...process.env, CAD_WARM_DIR: warmDir, CAD_RUNTIME_DIR: join(scratch, 'runtime'), CAD_MACRO_DIR: join(scratch, 'macros'),
    CAD_LIBRARY: join(scratch, 'library'), CAD_PREFS: join(scratch, 'prefs.json'), PYTHONPATH: REPO, CAD_PYTHON: python,
    // The renders the checks make go through the CPU rasteriser: nothing here is about how they look, and a Mac whose GPU is busy
    // (the owner's workbench, other agents) leaves a Metal render waiting for minutes, and the check with it.
    CAD_RENDER_BACKEND: 'numpy' }
  delete env.CAD_PROJECTS
  server = spawn(python, ['-c', `import sys; from pathlib import Path; from cad_agent import serve; serve.run([Path(sys.argv[1])], host="127.0.0.1", port=${port})`, ROOT],
    { env, cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'] })
  server.stderr.on('data', (d) => process.stderr.write(`[workbench] ${d}`))
  await new Promise((ok, no) => {
    const t = setTimeout(() => no(new Error('the scratch workbench did not start')), 60000)
    server.stdout.on('data', (d) => { if (/workbench: http/.test(String(d))) { clearTimeout(t); ok() } })
    server.on('exit', (c) => no(new Error(`the scratch workbench exited with ${c}`)))
  })
  BASE = `http://127.0.0.1:${port}/next/`
}
async function stopWorkbench() {
  if (!server) return
  server.kill('SIGTERM')
  // the warm worker the workbench started: stop it, and nothing else (CAD_WARM_DIR is ours)
  spawnSync(env.CAD_PYTHON, ['-P', '-m', 'cad_agent.warm', 'warm', 'stop'], { env, cwd: REPO, timeout: 60000 })
  for (const d of [scratch, warmDir]) if (d) rmSync(d, { recursive: true, force: true })
}
if (!BASE) await startWorkbench()
else {
  BASE = BASE.replace(/\/?$/, '/'); if (!/\/next\/$/.test(BASE)) BASE += 'next/'
  if (!ROOT) { console.error('wirecheck: with a URL, pass the folder that workbench serves as the second argument'); process.exit(2) }
}
const PORT = Number(new URL(BASE).port)
if (FORBIDDEN_PORTS.has(PORT)) { console.error(`wirecheck: port ${PORT} is the owner's; point it at a scratch workbench`); process.exit(2) }
const OUT = join(scratch || tmpdir(), 'wirecheck-out'); mkdirSync(OUT, { recursive: true })
const PARITY = existsSync(join(REPO, 'ui', 'PARITY.md')) ? readFileSync(join(REPO, 'ui', 'PARITY.md'), 'utf8').toLowerCase() : ''

// ── the browser ─────────────────────────────────────────────────────────────────────────────────────────────────────
const events = []        // what the page did that the DOM and the store do not show (downloads, pop-ups, dialogs, file choosers)
const errs = []          // page errors and console errors, in order
const reqs = []          // /api calls: { m, url, body }
const blocked = []       // requests the safety net refused
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const [VW, VH] = flag('viewport', '1400x900').split('x').map(Number)
const ctx = await browser.newContext({ viewport: { width: VW, height: VH }, acceptDownloads: true })
const page = await ctx.newPage()
page.setDefaultTimeout(8000)
page.on('pageerror', (e) => errs.push(`pageerror: ${e.message}`))
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errs.push(`console: ${m.text()}`) })
let dialogMode = 'dismiss', fileAnswer = [], promptAnswers = []    // what a confirm(), a file chooser and (in order) a prompt() are told, set by the entry under test
page.on('dialog', async (d) => {
  events.push(`dialog:${d.type()}`)
  if (d.type() === 'prompt' && promptAnswers.length) return d.accept(promptAnswers.shift()).catch(() => {})
  await (dialogMode === 'accept' ? d.accept() : d.dismiss()).catch(() => {})
})
page.on('download', async (d) => { events.push(`download:${d.suggestedFilename()}`); try { await d.saveAs(join(OUT, d.suggestedFilename())) } catch { /* cancelled */ } })
page.on('filechooser', async (fc) => { events.push('filechooser'); await fc.setFiles(fileAnswer).catch(() => {}) })
ctx.on('page', (pg) => { if (pg !== page) { events.push('popup'); pg.close().catch(() => {}) } })
// Nothing leaves the machine; nothing the owner decides is decided here; Finder is not opened.
await ctx.route((u) => !['127.0.0.1', 'localhost'].includes(u.hostname), (r) => r.abort())
await ctx.route('**/api/**', async (route) => {
  const req = route.request(), u = new URL(req.url())
  let body = null; try { body = req.postData() ? JSON.parse(req.postData()) : null } catch { /* not JSON (an upload) */ }
  if (u.pathname !== '/api/events' && !(u.pathname === '/api/gui' && req.method() === 'POST')) reqs.push({ m: req.method(), url: u.pathname, q: u.search, body, t: Date.now() })
  const argv = Array.isArray(body?.argv) ? body.argv : []
  const banned = (argv[0] === 'eval' && argv[1] === 'run') || (argv[0] === 'lib' && argv[1] === 'fetch') || argv[0] === 'approve'
  if (u.pathname === '/api/reveal') {      // "Open file location": the answer is made up, so that Finder does not open on the owner's screen
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ revealed: '(not opened: wirecheck)' }) })
  }
  if (u.pathname === '/api/approve' || banned) {
    blocked.push(`${req.method()} ${u.pathname} ${argv.join(' ')}`.trim())
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ exit: 3, data: { error: 'refused by wirecheck: a person decides this' }, stderr: '' }) })
  }
  return route.continue()
})

// ── in the page: a fingerprint of everything a click can change ─────────────────────────────────────────────────────
await page.addInitScript((keepHtml) => {
  window.__wcKeepHtml = keepHtml
  // no CSS animation or transition: the status bar's busy indicator would keep the browser drawing, minute after minute, while a check runs
  document.addEventListener('DOMContentLoaded', () => {
    const st = document.createElement('style')
    st.textContent = '*, *::before, *::after { animation: none !important; transition: none !important; caret-color: transparent !important; }'
    document.head.appendChild(st)
  })
  const ev = (window.__wcEvents = [])
  try { Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (t) => { ev.push('clipboard'); window.__wcClip = String(t) }, readText: async () => window.__wcClip ?? '' } }) } catch { /* read-only here */ }
  window.open = (url) => { ev.push(`open:${url || 'blank'}`); return window.__wcBlockOpen ? null : { document: { write() {}, close() {} }, close() {}, focus() {}, print() {} } }
  window.print = () => { ev.push('print') }
  window.__wcPreviewDraws = 0
  for (const C of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!C) continue
    for (const m of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) {
      const f = C.prototype[m]
      if (f) C.prototype[m] = function (...a) { if (this.canvas?.closest?.('.pref-dlg, .taskview')) window.__wcPreviewDraws++; return f.apply(this, a) }
    }
  }
  addEventListener('click', (e) => { const a = e.target?.closest?.('a[href]'); if (a && a.target === '_blank' && !a.download) ev.push(`link:${a.getAttribute('href')}`) }, true)
  const aclick = HTMLAnchorElement.prototype.click
  HTMLAnchorElement.prototype.click = function () { if (this.download) ev.push(`anchor-download:${this.download}`); return aclick.call(this) }
  const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return h >>> 0 }
  // the store keys that follow the pointer, the server or the clock rather than a click
  const SKIP = new Set(['scene', 'checks', 'status', 'log', 'projects', 'roots', 'messages', 'consoleLines', 'notifications', 'live', 'offline', 'preselected', 'prePoint',
    'preSub', 'viewInfo', 'cameraNode', 'viewSize', 'subPts', 'hints', 'gateMsg', 'building', 'busy', 'picked', 'cubeOffset', 'notifyMissed', 'notifyOverflow'])
  // what the work of a click leaves in the busy list, even when it is over before anyone looks
  setInterval(() => { const b = window.cadui?.getState?.().busy; if (b?.length) for (const n of b) { const k = `busy:${n}`; if (!ev.includes(k)) ev.push(k) } }, 30)
  // Camera.cpp (3160daf1e2b6): the standard views, as Coin's x, y, z, w (cubecheck.mjs has the same table)
  const R2 = Math.SQRT1_2
  const STD = { top: [0, 0, 0, 1], bottom: [1, 0, 0, 0], front: [R2, 0, 0, R2], rear: [0, R2, R2, 0], right: [0.5, 0.5, 0.5, 0.5], left: [-0.5, 0.5, 0.5, -0.5],
    iso: [0.424708, 0.17592, 0.339851, 0.820473], dimetric: [0.567952, 0.103751, 0.146726, 0.803205], trimetric: [0.446015, 0.119509, 0.229575, 0.856787] }
  const qang = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / (Math.hypot(...a) * Math.hypot(...b)); return (2 * Math.acos(Math.min(1, d)) * 180) / Math.PI }
  window.__wc = {
    hash, STD, qang,
    cam() { return window.cadui.getView()?.probe?.() ?? null },
    /** whether the camera looks the way FreeCAD's standard view `name` does */
    isView(name) { const p = this.cam(); return !!p && qang(p.camera, STD[name]) < 0.05 },
    fwd(q) { const [x, y, z, w] = q, v = [0, 0, -1], t = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])]
      return [v[0] + w * t[0] + (y * t[2] - z * t[1]), v[1] + w * t[1] + (z * t[0] - x * t[2]), v[2] + w * t[2] + (x * t[1] - y * t[0])] },
    busy() { const S = window.cadui?.getState?.(); return !!S && (S.busy.length > 0 || S.building) },
    snap() {
      const S = window.cadui?.getState?.()
      if (!S) return null
      const store = {}
      for (const [k, v] of Object.entries(S)) {
        if (SKIP.has(k)) continue
        let j; try { j = JSON.stringify(v) } catch { j = String(v) }
        store[k] = hash(j ?? '')
      }
      store.scene = hash(S.scene ? JSON.stringify([S.scene.source_hash, S.scene.written_utc, S.scene.bodies.map((b) => [b.name, b.placement, b.params && Object.fromEntries(Object.entries(b.params).map(([k, p]) => [k, p.value]))])]) : '')
      store.checks = hash(JSON.stringify([S.checks?.written_utc, S.checks?.rows?.length ?? null]))
      store.status = hash(JSON.stringify(S.status ?? null))
      const v = window.cadui.getView?.(), pr = v?.probe?.()
      store['view.cubeDraggable'] = String(!!v?.isCubeDraggable?.())      // held by the view, not the store: the NaviCube menu's Movable Navigation Cube
      const drag = v?.getDragger?.()                                      // the Transform task's dragger, which Flip turns over without a field changing
      store['view.dragger'] = drag ? hash(Array.from(drag.elements).map((x) => x.toFixed(2)).join()) : ''
      const cam = pr ? hash(JSON.stringify([pr.ortho, pr.camera.map((x) => +x.toFixed(4)), pr.position.map((x) => +x.toFixed(2)), +pr.zoom.toFixed(3), pr.target.map((x) => +x.toFixed(2))])) : 0
      const c = document.body.cloneNode(true)
      c.querySelectorAll('.fc-tooltip, canvas').forEach((n) => n.remove())
      // attributes Radix and the browser rewrite on every open and close of a menu
      const NOISE = ['id', 'aria-labelledby', 'aria-controls', 'aria-expanded', 'data-state', 'data-highlighted', 'data-side', 'data-align', 'tabindex', 'title', 'data-fc-title']
      c.querySelectorAll(NOISE.map((a) => `[${a}]`).join(',')).forEach((n) => { for (const a of NOISE) n.removeAttribute(a) })
      c.querySelectorAll('.dv-scrollable-resizing').forEach((n) => n.classList.remove('dv-scrollable-resizing'))   // dockview, while its observer measures a tab strip
      const ls = {}
      try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith('cadui.')) ls[k.slice(6)] = hash(localStorage.getItem(k)) } } catch { /* no storage */ }
      const lines = document.body.innerText.split('\n').map((x) => x.trim()).filter(Boolean)
      return { store, cam, dom: hash(c.innerHTML + '|' + document.body.className + '|' + document.documentElement.className), html: window.__wcKeepHtml ? c.innerHTML : '', lines, ls, msgs: S.messages.length, cons: S.consoleLines.length, lastMsg: S.messages.at(-1)?.text ?? '',
        pdraw: window.__wcPreviewDraws,
        fields: hash([...document.querySelectorAll('input, select, textarea')].map((el) => (el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value)).join('\u0001')
          + '|' + [...document.querySelectorAll('textarea, input')].map((el) => { try { return el.selectionStart == null ? '' : `${el.selectionStart}-${el.selectionEnd}` } catch { return '' } }).join(',')),
        consTail: S.consoleLines.slice(-8).map((l) => l.text), url: location.href, fs: !!document.fullscreenElement, selText: (getSelection()?.toString() ?? '').length, wev: ev.length, task: S.task?.kind ?? null }
    },
    events(from) { return ev.slice(from) },
    /** Sets a controlled input's value the way typing does (React ignores a plain assignment). */
    setInput(el, v) {
      Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }))
    },
    /** Resolves true once nothing is busy and the fingerprint has not moved for `quiet` ms (after at least `min`), false at `max`. */
    settle(min, quiet, max) {
      return new Promise((done) => {
        const t0 = performance.now()
        let last = null, since = performance.now()
        const tick = () => {
          const now = performance.now(), S = window.cadui?.getState?.(), p = window.cadui?.getView?.()?.probe?.()
          // cheap on purpose: this runs every 60 ms while the page is busy drawing
          const key = S ? `${hash(document.body.innerHTML)}|${S.selected.length}|${S.hidden.length}|${S.task?.kind}|${S.drawStyle}|${S.ortho}|${S.messages.length}|${S.consoleLines.length}|${S.undo.length}|${S.redo.length}|${p ? p.position.map((x) => x.toFixed(1)).join() + p.zoom.toFixed(2) : ''}` : ''
          if (this.busy() || key !== last) { last = key; since = now }
          if (now - t0 >= min && !this.busy() && now - since >= quiet) return done(true)
          if (now - t0 >= max) return done(false)
          setTimeout(tick, 60)
        }
        setTimeout(tick, Math.min(min, 60))
      })
    },
  }
}, DEBUG_DOM)

// ── observing a click ───────────────────────────────────────────────────────────────────────────────────────────────
const snap = () => page.evaluate(() => window.__wc.snap())
const park = async () => { await page.mouse.move(1490, 12) }   // an empty corner of the toolbar row: no hover state to differ
const settle = ({ min = 250, quiet = 350, max = 90000 } = {}) => page.evaluate(([a, b, c]) => window.__wc.settle(a, b, c), [min, quiet, max])
/** The first line of the visible text that was not there before. */
const newLines = (a, b) => { const had = new Set(a); return b.filter((l) => !had.has(l)) }
/** Runs `act`, waits for the page to be quiet, and says what changed. */
async function observe(act, opts = {}) {
  const t0 = Date.now()
  await park(); await settle({ min: 80, quiet: 200, max: 60000 })
  const a = await snap(), e0 = errs.length, q0 = reqs.length, v0 = events.length, w0 = a.wev, b0 = blocked.length
  const rawBefore = opts.restore === false ? null : await page.evaluate(() => { const o = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); o[k] = localStorage.getItem(k) } return o })
  const t1 = Date.now()
  let threw = null
  try { await act() } catch (e) { threw = String(e.message).split('\n').filter((l) => l.trim() && !/^Call log:$/.test(l.trim())).slice(0, DEBUG_DOM ? 14 : 2).join(' | ').slice(0, DEBUG_DOM ? 1400 : 400) }
  const t2 = Date.now()
  const ok = await settle({ min: opts.min ?? 150, quiet: opts.quiet ?? 300, max: opts.max ?? 60000 })
  await park()
  const b = await snap()
  lastTiming = `${((t1 - t0) / 1000).toFixed(1)}+${((t2 - t1) / 1000).toFixed(1)}+${((Date.now() - t2) / 1000).toFixed(1)}s`
  const fx = []
  for (const k of new Set([...Object.keys(a.store), ...Object.keys(b.store)])) if (a.store[k] !== b.store[k]) fx.push(`store:${k}`)
  if (a.cam !== b.cam) fx.push('camera')
  if (b.msgs !== a.msgs) fx.push(`report:${b.lastMsg.slice(0, 70)}`)
  // The recorder's fallback line (`cad gui run PROJECT Std_X`) is written for any command that did not write its own: it says the
  // entry was invoked, not that it did anything, so it is not an effect.
  const added = b.consTail.slice(Math.max(0, b.consTail.length - (b.cons - a.cons)))
  const real = added.filter((l) => !/^# cad gui run \S+ (Std|CADAgent|Start|Part)_\w+/.test(l))
  if (b.cons !== a.cons && real.length) fx.push(`console:${real.at(-1).slice(0, 70)}`)
  for (const k of new Set([...Object.keys(a.ls), ...Object.keys(b.ls)])) if (a.ls[k] !== b.ls[k]) fx.push(`saved:${k}`)
  if (a.fields !== b.fields) fx.push('fields')
  if (a.pdraw !== b.pdraw) fx.push('preview redrawn')
  if (a.url !== b.url) fx.push('url')
  if (a.fs !== b.fs) fx.push('fullscreen')
  if (a.selText !== b.selText) fx.push('text selection')      // Select All in the Report view or the console selects text, which changes no DOM
  const fresh = newLines(a.lines, b.lines).filter((l) => l.length < 90)
  if (a.dom !== b.dom) {
    fx.push(`dom${fresh.length ? ':+' + fresh.slice(0, 3).join(' / ') : ''}`)
    if (DEBUG_DOM && !fresh.length && a.html && b.html) {       // say where it differs
      let i = 0; while (i < a.html.length && a.html[i] === b.html[i]) i++
      console.log(`   dom differs at ${i}: -${a.html.slice(Math.max(0, i - 60), i + 90)}\n                      +${b.html.slice(Math.max(0, i - 60), i + 90)}`)
    }
  }
  // a page reads the server back after almost any change (the scene, the checks, the journal): only what it sends is an effect
  for (const r of reqs.slice(q0)) if (r.m !== 'GET' || /^\/api\/(file|macro|cache)\b/.test(r.url)) fx.push(`${r.m} ${r.url}${r.body?.argv ? ' ' + r.body.argv.slice(0, 3).join(' ') : ''}`)
  for (const x of events.slice(v0)) fx.push(x)
  for (const x of await page.evaluate((n) => window.__wc.events(n), w0)) fx.push(x)
  const errors = errs.slice(e0)
  return { fx: [...new Set(fx)], errors, threw, quiet: ok, before: a, after: b, blocked: blocked.slice(b0), reqs: reqs.slice(q0), rawBefore }
}
/** Evaluates an expectation (an expression over S, the store, and V, the view) in the page. */
const check = (expr, fx = []) => page.evaluate(([src, FX]) => { try { return !!new Function('S', 'V', 'W', 'FX', `return (${src})`)(window.cadui.getState(), window.cadui.getView(), window.__wc, FX) } catch (e) { return false } }, [expr, fx])
const put = (patch) => page.evaluate((p) => window.cadui.setState(p), patch)
const getS = (expr) => page.evaluate((src) => new Function('S', 'V', 'W', `return (${src})`)(window.cadui.getState(), window.cadui.getView(), window.__wc), expr)

// ── results ─────────────────────────────────────────────────────────────────────────────────────────────────────────
const results = []
let lastTiming = ''
/** Why a greyed-out control is greyed out: its tooltip says so, or PARITY.md has a line about it that says n/a, disabled or stays. */
const PARITY_LINES = PARITY.split('\n')
const reasonFor = (label, title) => {
  if (title && /n\/a|not |no |can't|cannot|only|needs|nothing|select|stay|there is|there's|with no|without|unsaved|saved|disabled/i.test(title)) return 'tooltip'
  const l = label.replace(/…|\.\.\./g, '').replace(/\s*\(.*\)\s*$/, '').trim().toLowerCase()
  if (l.length > 2 && PARITY_LINES.some((line) => line.includes(l) && /n\/a|disabled|stay|missing|not shown|shown disabled/.test(line))) return 'PARITY.md'
  return title ? 'tooltip' : null
}
function note(surface, path, meta, klass, detail = '') {
  const row = { surface, path, cmd: meta.cmd ?? null, enabled: meta.enabled !== false, klass, detail }
  results.push(row)
  if (VERBOSE || !['WORKS', 'N/A'].includes(klass)) console.log(`${klass.padEnd(6)} ${surface.padEnd(9)} ${path}${meta.cmd ? `  [${meta.cmd}]` : ''}${detail ? `  -- ${detail}` : ''}${VERBOSE && lastTiming ? `  (${lastTiming})` : ''}`)
  lastTiming = ''
  return row
}
/** Judges a click, then undoes what it left in localStorage (see observe): the next control starts from the settings the page started with. */
async function judge(surface, path, meta, o, expect) {
  const row = await judge0(surface, path, meta, o, expect)
  if (o.rawBefore && o.fx.some((f) => f.startsWith('saved:'))) {
    await page.evaluate((raw) => { localStorage.clear(); for (const [k, v] of Object.entries(raw)) localStorage.setItem(k, v) }, o.rawBefore)
    await openFresh()
  }
  return row
}
/** Classifies one observed click: ERROR first, then WRONG against an expectation, then NO-OP when nothing changed. */
async function judge0(surface, path, meta, o, expect) {
  if (o.blocked.length) return note(surface, path, meta, 'HUMAN', `refused at the network layer: ${o.blocked.join('; ')}`)
  if (o.errors.length) return note(surface, path, meta, 'ERROR', o.errors.join(' | ').slice(0, 240))
  if (o.threw) return note(surface, path, meta, 'ERROR', `click failed: ${o.threw}`)
  const detail = o.fx.join('; ').slice(0, 200)
  if (!o.fx.length) return note(surface, path, meta, 'NO-OP', 'nothing changed')
  if (expect && !(await check(expect, o.fx))) return note(surface, path, meta, 'WRONG', `expected ${expect}; it did ${detail}`)
  return note(surface, path, meta, 'WORKS', detail)
}

// ── the page, a project open, a known state ─────────────────────────────────────────────────────────────────────────
/** The server keeps what the page says about hidden parts, view properties and parts that cannot be selected (out/gui.json), and a page
 *  opened afresh reads it back: a click that left a part transparent would make the next Toggle Transparency take it back. */
async function cleanGui(slug) {
  const origin = new URL(BASE).origin, headers = { 'Content-Type': 'application/json', 'X-CAD': '1' }
  try {
    const g = await (await fetch(`${origin}/api/gui?slug=${encodeURIComponent(slug)}`)).json()
    const view_props = Object.fromEntries(Object.keys(g.view_props ?? {}).map((b) => [b, { transparency: 0, boundingBox: false, showInTree: true, showPlacement: false,
      displayMode: 'Flat Lines', lighting: 'Two side', drawStyle: 'Solid', onTop: 'Disabled', selectionStyle: 'Shape' }]))
    await fetch(`${origin}/api/gui`, { method: 'POST', headers, body: JSON.stringify({ slug, state: { hidden: [], unselectable: [], ...(Object.keys(view_props).length ? { view_props } : {}) } }) })
  } catch { /* nothing to clean if the server does not answer */ }
}
async function openFresh(slug = PROJECT) {
  await cleanGui(slug)
  await page.goto('about:blank'); await page.goto(BASE + '#' + slug, { waitUntil: 'load' })
  await page.waitForSelector('.trow .tname', { timeout: 180000 })
  await page.waitForFunction(() => { const S = window.cadui?.getState?.(); return !!S?.scene && !S.building }, null, { timeout: 180000 })
  await page.locator('.dv-tab', { hasText: `${slug} : 1` }).first().click()
  await put({ animate: false })      // view animations are cubecheck.mjs's business; here a view command should be done when it returns
  await settle({ min: 800, quiet: 600 })
  baseline = await page.evaluate((keys) => Object.fromEntries(keys.map((k) => [k, window.cadui.getState()[k]])), BASE_KEYS)
  await page.evaluate(() => { window.__cam0 = window.cadui.getView()?.getCamera() ?? null })
}
/** The store fields a click on a view command can leave changed and a soft reset puts back (the 3D view is told as well). */
const BASE_KEYS = ['hidden', 'unselectable', 'view', 'drawStyle', 'ortho', 'axes', 'selBoxes', 'cube', 'clip', 'pose', 'selFilter', 'gateMsg', 'workbench', 'pickList', 'consoleDraft',
  'treeCollapsed', 'treeShowHidden', 'treeFilter', 'frozenViews', 'recordingMacro']
let baseline = null
const SELECTION = {
  none: { selected: [], subSel: [] },
  one: { selected: ['hot_plate'], subSel: [] },
  face: { selected: ['hot_plate'], subSel: ['hot_plate.Face1'] },
  two: { selected: ['base', 'hot_plate'], subSel: [] },
  child: { selected: ['gantry/tool_plate'], subSel: [] },
  faces2: { selected: ['base', 'hot_plate'], subSel: ['base.Face1', 'hot_plate.Face1'] },
}
/** Closes menus. A right-click menu (`.ctx`) takes Escape for itself, and nothing behind it sees the key; a menu bar menu is closed by clicking
 *  away, since Escape would also reach the page's own key handler, which clears the selection. (A click on an empty spot of the toolbar row
 *  would also close a dialog whose backdrop it lands on, so a right-click menu inside a dialog must not be closed that way.) */
async function closeMenus() {
  for (let i = 0; i < 5; i++) {
    if (await page.locator('.ctx').count()) { await page.keyboard.press('Escape'); await sleep(60); continue }
    if (await page.locator('[role=menu][data-state=open]').count()) { await page.mouse.click(1490, 12); await sleep(80); continue }
    return
  }
}
/** Closes a question the way a person answers one they did not ask for: No, Cancel or Close, and never Yes. */
async function answerNo() {
  for (const m of await page.locator('.msgbox').all()) {
    const no = m.getByRole('button', { name: /^(No|Cancel|Close)$/ })
    if (await no.count()) await no.first().click()
    else if ((await m.getByRole('button').count()) === 1) await m.getByRole('button').first().click()
    else await page.keyboard.press('Escape')
  }
}
/** Puts the page back the way a person leaves it between two clicks: menus, dialogs and tasks closed, then a selection. */
async function resetUI(sel = 'none') {
  promptAnswers.length = 0; dialogMode = 'dismiss'
  await closeMenus()
  await page.evaluate(() => document.activeElement?.blur?.())
  for (let i = 0; i < 5; i++) {
    const open = await getS('({ p: S.prefsOpen, c: S.customizeOpen, t: !!S.task, m: document.querySelectorAll(".msgbox").length, w: document.body.classList.contains("whats-this-cursor"), b: !!document.querySelector(".box-select"), x: !!document.querySelector(".expr-dlg") })')
    if (!open.p && !open.c && !open.t && !open.m && !open.w && !open.b && !open.x) break
    if (open.m) await answerNo()
    else if (open.x) await page.locator('.expr-dlg .expr-buttons .qbtn', { hasText: /^Reset$/ }).click()      // the Expression Editor's way out without a value
    else if (open.p) await page.locator('.pref-dlg .pref-buttons .qbtn', { hasText: /^Cancel$/ }).click()
    else if (open.c) await page.locator('.cu-dlg .qbtn', { hasText: /^Close$/ }).click()
    else if (open.w || open.b) await page.keyboard.press('Escape')
    else if (open.t) {
      const close = page.locator('.taskview .tbuttons .qbtn', { hasText: /^(Cancel|Close)$/ })
      if (await close.count()) await close.first().click(); else await page.keyboard.press('Escape')
    }
    await sleep(150)
  }
  if (baseline) {
    const turned = await page.evaluate(([base, selection]) => {
      const S = window.cadui.getState(), V = window.cadui.getView()
      let turned = false
      if (S.pose) V?.setPose(null)
      if (S.ortho !== base.ortho) V?.setOrtho(base.ortho)
      if (window.__cam0 && V && V.getCamera() !== window.__cam0) { V.setCamera(window.__cam0); turned = true }
      const { recordingMacro, ...rest } = base       // a macro being recorded is stopped through its own menu entry, not here
      window.cadui.setState({ ...rest, ...selection })
      return turned
    }, [baseline, SELECTION[sel]])
    if (turned) await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))))   // the picking reads the frame drawn last
  } else await put({ ...SELECTION[sel], treeFilter: null })
}

// ── menus: reading them, walking to an entry, clicking it ───────────────────────────────────────────────────────────
const trigger = (top) => page.locator('.mb-trigger', { hasText: new RegExp(`^${esc(top)}$`) })
const readMenuAt = (depth) => page.evaluate((d) => {
  const m = [...document.querySelectorAll('[role=menu][data-state=open]')][d]
  if (!m) return null
  return [...m.children].map((el, i) => {
    if (el.getAttribute('role') === 'separator') return { i, sep: true }
    const c = el.cloneNode(true); c.querySelectorAll('.mb-ico, .mb-kbd').forEach((n) => n.remove())
    return { i, label: c.textContent.trim(), disabled: el.hasAttribute('data-disabled') || el.getAttribute('aria-disabled') === 'true', sub: el.getAttribute('aria-haspopup') === 'menu',
      checked: !!el.querySelector('.mb-check'), kbd: [...el.querySelectorAll('.mb-kbd')].map((n) => n.textContent).filter((t) => t !== '▸').join(''),
      title: el.getAttribute('title') || el.getAttribute('data-fc-title') || '', cmd: el.dataset.cmd || '' }
  })
}, depth)
/** Opens `top` and then each sub-menu of `path` in turn; returns the depth of the menu that is open at the end. */
async function openMenu(top, path = []) {
  await closeMenus()
  await trigger(top).click()
  await page.locator('[role=menu][data-state=open]').first().waitFor({ timeout: 5000 })
  for (let d = 0; d < path.length; d++) {
    const items = await readMenuAt(d)
    const it = items?.find((x) => x.label === path[d])
    if (!it) throw new Error(`no menu entry ${top} > ${path.slice(0, d + 1).join(' > ')}`)
    await page.locator('[role=menu][data-state=open]').nth(d).locator(':scope > *').nth(it.i).click()
    await page.locator('[role=menu][data-state=open]').nth(d + 1).waitFor({ timeout: 5000 })
  }
  return path.length
}
/** Every entry of a top menu, sub-menus included, as { path: [...], label, disabled, sub, checked, kbd, title, cmd }. */
async function inventoryMenu(top) {
  const out = []
  const walk = async (path) => {
    const depth = await openMenu(top, path)
    const items = (await readMenuAt(depth)) ?? []
    await closeMenus()
    for (const it of items) {
      if (it.sep) continue
      out.push({ ...it, top, path: [...path, it.label] })
      if (it.sub && !it.disabled) await walk([...path, it.label])
    }
  }
  await walk([])
  return out
}

// ── menus: every entry, clicked ─────────────────────────────────────────────────────────────────────────────────────
const TOPS = flag('top', '') ? flag('top', '').split(',') : ['File', 'Edit', 'View', 'Tools', 'Macro', 'CAD Agent', 'Windows', 'Help']
const keyOf = (e) => [e.top, ...e.path].join(' > ')
/** The entries of every menu, as they stand with nothing selected, with a face selected and with two parts selected: an entry that is
 *  greyed in one state and live in another is tested in the state that enables it. */
async function menuInventory() {
  const union = new Map()
  for (const sel of ['none', 'face', 'two']) {
    await resetUI(sel)
    for (const top of TOPS) {
      const inv = await inventoryMenu(top)
      if (sel === 'none') note('menus', `${top} (menu bar title)`, { enabled: true }, inv.length ? 'WORKS' : 'NO-OP', inv.length ? `opens ${inv.length} entries` : 'opens nothing')
      for (const e of inv) {
        const key = keyOf(e), cur = union.get(key)
        if (!cur) union.set(key, { ...e, key, enabledIn: e.disabled ? [] : [sel] })
        else if (!e.disabled) cur.enabledIn.push(sel)
      }
    }
  }
  await resetUI('none')
  return [...union.values()]
}
async function clickMenuEntry(e) {
  const parent = e.path.slice(0, -1)
  const depth = await openMenu(e.top, parent)
  const it = (await readMenuAt(depth)).find((x) => x.label === e.label)
  if (!it || it.disabled) throw new Error(`${keyOf(e)} is not there or not enabled`)
  await page.locator('[role=menu][data-state=open]').nth(depth).locator(':scope > *').nth(it.i).click()
}
const entryAt = (top, ...path) => ({ top, path, label: path.at(-1), key: [top, ...path].join(' > ') })

// ── what an entry should do, and what it needs first ────────────────────────────────────────────────────────────────
// key: 'Top > Sub > Entry'. sel: the selection it needs (none, one, face, two, child); pre/post: set-up and put-back; expect: an
// expression over S (the store), V (the view), W (the page helpers) and FX (what the click was seen to do) that must hold;
// fresh: reload the page after (the entry changes something a soft reset does not put back); min/max: settle time.
const task = (k) => `S.task?.kind==='${k}'`
const sawReq = (re) => `FX.some((f) => new RegExp(${JSON.stringify(re)}).test(f))`
const orbitFar = () => page.evaluate(() => window.cadui.getView().orient([0.3, 0.2, 0.1, 0.9273]))
const remember = () => page.evaluate(() => { const p = window.cadui.getView().probe(); window.__q0 = p.camera; window.__z0 = p.zoom; window.__pos0 = p.position })
const exitFullscreen = () => page.evaluate(() => document.fullscreenElement && document.exitFullscreen())
const pngFile = () => { const f = join(OUT, 'pixel.png'); writeFileSync(f, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==', 'base64')); return f }
const viewSpec = (name) => ({ pre: orbitFar, expect: `W.isView('${name}')` })
const SPEC = {
  'File > New Document': { expect: task('newDocument') },
  'File > Open…': { expect: task('openDocument') },
  'File > Open Recent > Clear Recent Files': { pre: async () => { dialogMode = 'accept' }, post: async () => { dialogMode = 'dismiss' }, expect: `JSON.parse(localStorage.getItem('cadui.recentFiles')||'[]').length===0` },
  'File > Close': { fresh: true, expect: '!V' },
  'File > Close All': { fresh: true, expect: '!V' },
  'File > Import…': { expect: `${task('bought')}&&S.task.other==='import'` },
  'File > Export…': { sel: 'one', expect: task('export') },
  'File > Document Information': { expect: task('info') },
  'File > Print': { expect: sawReq('^open:') },
  'File > Print Preview': { expect: sawReq('^open:') },
  'File > Export PDF': { expect: sawReq('^open:') },
  'Edit > Undo': { pre: () => makeEdit(), post: () => unplace(), expect: sawReq('POST /api/undo') },
  'Edit > Redo': { pre: () => makeRedo(), post: () => unplace(), expect: sawReq('POST /api/redo') },
  'Edit > Copy': { sel: 'one', expect: `FX.includes('clipboard')` },
  'Edit > Recompute': { expect: sawReq('POST /api/check') },
  'Edit > Box Selection': { post: () => page.keyboard.press('Escape'), expect: `!!document.querySelector('.box-select')` },
  'Edit > Box Element Selection': { post: () => page.keyboard.press('Escape'), expect: `!!document.querySelector('.box-select')` },
  'Edit > Select All': { expect: 'S.selected.length===S.scene.bodies.length' },
  'Edit > Transform': { sel: 'one', expect: task('transform') },
  'Edit > Placement': { sel: 'one', expect: task('placement') },
  'Edit > Align To…': { sel: 'two', expect: task('align') },
  'Edit > Send to Console': { sel: 'one', expect: `S.consoleDraft.includes('hot_plate')` },
  'Edit > Properties': { pre: () => page.evaluate(() => window.cadui.showPanel('selection')), expect: `window.cadui.getDock().getPanel('model').api.isActive` },
  'Edit > Toggle Edit Mode': { sel: 'one', expect: `S.task?.kind==='params'||S.task?.kind==='transform'` },
  'Edit > Edit Mode > Default': { pre: () => put({ editMode: 'transform' }), fresh: true, expect: `S.editMode==='default'` },
  'Edit > Edit Mode > Transform': { fresh: true, expect: `S.editMode==='transform'` },
  'Edit > Edit Mode > Cutting': { fresh: true, expect: `S.editMode==='cutting'` },
  'Edit > Edit Mode > Color': { fresh: true, expect: `S.editMode==='color'` },
  'Edit > Preferences': { expect: 'S.prefsOpen' },
  'View > Orthographic View': { pre: () => page.evaluate(() => { window.cadui.getView().setOrtho(false); window.cadui.setState({ ortho: false }) }), expect: 'S.ortho&&V.probe().ortho' },
  'View > Perspective View': { expect: '!S.ortho&&!V.probe().ortho', post: () => page.evaluate(() => { window.cadui.getView().setOrtho(true); window.cadui.setState({ ortho: true }) }) },
  'View > Fullscreen': { post: exitFullscreen, expect: '!!document.fullscreenElement' },
  'View > Standard Views > Fit All': { pre: () => page.evaluate(() => { const v = window.cadui.getView(); v.zoomOut(); v.zoomOut(); v.zoomOut() }) },
  'View > Standard Views > Fit Selection': { sel: 'one', pre: () => page.evaluate(() => { const v = window.cadui.getView(); v.zoomOut(); v.zoomOut() }) },
  'View > Standard Views > Align to Selection': { sel: 'face', pre: orbitFar },
  'View > Standard Views > Axonometric > Isometric': viewSpec('iso'),
  'View > Standard Views > Axonometric > Dimetric': viewSpec('dimetric'),
  'View > Standard Views > Axonometric > Trimetric': viewSpec('trimetric'),
  'View > Standard Views > Home': { pre: orbitFar, expect: `W.isView('trimetric')` },
  'View > Standard Views > Front': viewSpec('front'),
  'View > Standard Views > Top': viewSpec('top'),
  'View > Standard Views > Right': viewSpec('right'),
  'View > Standard Views > Rear': viewSpec('rear'),
  'View > Standard Views > Bottom': viewSpec('bottom'),
  'View > Standard Views > Left': viewSpec('left'),
  'View > Standard Views > Rotate Left': { pre: async () => { await page.evaluate(() => window.cadui.getView().orient([0.5, 0.5, 0.5, 0.5])); await settle(); await remember() }, expect: 'Math.abs(W.qang(V.probe().camera, window.__q0)-90)<0.5' },
  'View > Standard Views > Rotates Right': { pre: async () => { await page.evaluate(() => window.cadui.getView().orient([0.5, 0.5, 0.5, 0.5])); await settle(); await remember() }, expect: 'Math.abs(W.qang(V.probe().camera, window.__q0)-90)<0.5' },
  'View > Standard Views > Store Working View': { expect: sawReq('report:Working view stored') },
  'View > Standard Views > Recall Working View': { pre: async () => { await page.evaluate(() => window.cadui.getView().storeView()); await remember(); await orbitFar() }, expect: 'W.qang(V.probe().camera, window.__q0)<0.1' },
  'View > Freeze Display > Save Views…': { pre: () => page.evaluate(() => window.cadui.setState({ frozenViews: [window.cadui.getView().getCamera()] })), expect: sawReq('download:views.cam') },
  'View > Freeze Display > Load Views…': { pre: async () => { fileAnswer = existsSync(join(OUT, 'views.cam')) ? [join(OUT, 'views.cam')] : [] }, post: async () => { fileAnswer = [] }, expect: `FX.includes('filechooser')` },
  'View > Freeze Display > Freeze View': { expect: 'S.frozenViews.length===1' },
  'View > Freeze Display > Clear Views': { pre: () => page.evaluate(() => window.cadui.setState({ frozenViews: [window.cadui.getView().getCamera()] })), expect: 'S.frozenViews.length===0' },
  'View > Draw Style > As Is': { pre: () => put({ drawStyle: 'shaded' }), expect: `S.drawStyle==='asis'` },
  'View > Draw Style > Points': { expect: `S.drawStyle==='points'`, post: () => put({ drawStyle: 'asis' }) },
  'View > Draw Style > Wireframe': { expect: `S.drawStyle==='wireframe'`, post: () => put({ drawStyle: 'asis' }) },
  'View > Draw Style > Hidden Line': { expect: `S.drawStyle==='hiddenline'`, post: () => put({ drawStyle: 'asis' }) },
  'View > Draw Style > No Shading': { expect: `S.drawStyle==='noshading'`, post: () => put({ drawStyle: 'asis' }) },
  'View > Draw Style > Shaded': { expect: `S.drawStyle==='shaded'`, post: () => put({ drawStyle: 'asis' }) },
  'View > Draw Style > Flat Lines': { expect: `S.drawStyle==='flatlines'`, post: () => put({ drawStyle: 'asis' }) },
  'View > Bounding Box': { expect: 'S.selBoxes', post: () => put({ selBoxes: false }) },
  'View > Zoom > Zoom In': { pre: remember, expect: 'V.probe().zoom>window.__z0' },
  'View > Zoom > Zoom Out': { pre: remember, expect: 'V.probe().zoom<window.__z0' },
  'View > Zoom > Box Zoom': { post: () => page.keyboard.press('Escape'), expect: `!!document.querySelector('.box-select')` },
  'View > Document Window > Fullscreen': { post: exitFullscreen, expect: '!!document.fullscreenElement' },
  'View > Issue Camera Position': { expect: sawReq('^report:.*Camera|^report:.*position') },
  'View > Toggle Axis Cross': { expect: 'S.axes', fresh: true },
  'View > Clipping View': { expect: task('clip'), post: () => put({ clip: null }) },
  'View > Visibility > Toggle Visibility': { sel: 'one', expect: `S.hidden.includes('hot_plate')`, post: () => put({ hidden: [] }) },
  'View > Visibility > Show Selection': { sel: 'one', pre: () => put({ hidden: ['hot_plate'] }), expect: `!S.hidden.includes('hot_plate')` },
  'View > Visibility > Hide Selection': { sel: 'one', expect: `S.hidden.includes('hot_plate')`, post: () => put({ hidden: [] }) },
  'View > Visibility > Select Visible Objects': { pre: () => put({ hidden: ['base'] }), expect: `S.selected.length===S.scene.bodies.length-1&&!S.selected.includes('base')`, post: () => put({ hidden: [] }) },
  'View > Visibility > Toggle All Objects': { expect: 'S.hidden.length===S.scene.bodies.length', post: () => put({ hidden: [] }) },
  'View > Visibility > Show All Objects': { pre: () => put({ hidden: ['base'] }), expect: 'S.hidden.length===0' },
  'View > Visibility > Hide All Objects': { expect: 'S.hidden.length===S.scene.bodies.length', post: () => put({ hidden: [] }) },
  'View > Visibility > Toggle Selectability': { sel: 'one', expect: `S.unselectable.includes('hot_plate')`, post: () => put({ unselectable: [] }) },
  'View > Appearance': { sel: 'one', expect: task('appearance') },
  'View > Random Color': { sel: 'one', expect: `S.view['hot_plate']?.shapeColor!=null`, post: () => put({ view: {} }) },
  'View > Toggle Transparency': { sel: 'one', expect: `S.view['hot_plate']?.transparency>0`, post: () => put({ view: {} }) },
  'View > Workbench > CAD Agent': { pre: () => put({ workbench: 'assembly' }), expect: `S.workbench==='agent'` },
  'View > Workbench > Assembly': { expect: `S.workbench==='assembly'`, post: () => put({ workbench: 'agent' }) },
  'View > Workbench > Inspection': { expect: `S.workbench==='inspection'`, post: () => put({ workbench: 'agent' }) },
  'View > Workbench > Part Design': { expect: `S.workbench==='design'`, post: () => put({ workbench: 'agent' }) },
  'View > Panels > Tasks': { expect: `!!window.cadui.getDock().getPanel('tasks')` },
  'View > Panels > Selection View': { expect: `window.cadui.getDock().getPanel('selection').api.isActive` },
  'View > Panels > Model': { pre: () => page.evaluate(() => window.cadui.showPanel('selection')), expect: `window.cadui.getDock().getPanel('model').api.isActive` },
  'View > Panels > Console': { expect: `window.cadui.getDock().getPanel('console').api.isActive` },
  'View > Panels > Report View': { pre: () => page.evaluate(() => window.cadui.showPanel('console')), expect: `window.cadui.getDock().getPanel('report').api.isActive` },
  'View > Panels > Checks': { expect: `window.cadui.getDock().getPanel('checks').api.isActive` },
  'View > Toggle Bottom Panels': { fresh: true },
  // the overlay commands act on the dock that is active, and (the Toggle Left/Bottom ones) on one that is in overlay mode already
  'View > Overlay Docked Panel > Toggle Overlay for All Panels': { fresh: true, expect: `window.cadui.getDock().getPanel('model').group.api.location.type==='floating'` },
  'View > Overlay Docked Panel > Toggle Transparent Panels': { fresh: true, expect: `document.querySelector('.dock').classList.contains('ovl-transparent')` },
  'View > Overlay Docked Panel > Toggle Overlay': { fresh: true, pre: () => showPanel('model'), expect: `window.cadui.getDock().getPanel('model').group.api.location.type==='floating'` },
  'View > Overlay Docked Panel > Toggle Transparent Mode': { fresh: true, pre: async () => { await showPanel('model'); await clickMenuEntry(entryAt('View', 'Overlay Docked Panel', 'Toggle Overlay')); await settle({ min: 500, quiet: 400 }) },
    expect: `!!document.querySelector('.dv-resize-container.ovl-transparent-one')` },
  'View > Overlay Docked Panel > Bypass Mouse Events in Overlay Panels': { fresh: true, expect: `document.querySelector('.dock').classList.contains('ovl-bypass')` },
  'View > Overlay Docked Panel > Toggle Left': { fresh: true, pre: async () => { await clickMenuEntry(entryAt('View', 'Overlay Docked Panel', 'Toggle Overlay for All Panels')); await settle({ min: 500, quiet: 400 }) },
    expect: `getComputedStyle(window.cadui.getDock().getPanel('model').group.element.closest('.dv-resize-container')).display==='none'` },
  'View > Overlay Docked Panel > Toggle Bottom': { fresh: true, pre: async () => { await clickMenuEntry(entryAt('View', 'Overlay Docked Panel', 'Toggle Overlay for All Panels')); await settle({ min: 500, quiet: 400 }) },
    expect: `getComputedStyle(window.cadui.getDock().getPanel('report').group.element.closest('.dv-resize-container')).display==='none'` },
  // Docked is the current choice of a pair whose other half (Fullscreen) hides the menus: clicking it can only do nothing
  'View > Document Window > Docked': { na: 'the current choice of a pair: its other half, Fullscreen, shows the 3D view alone, so no menu is there to click it from (V, D does it)' },
  'View > Tree View Actions > Go to Selection': { sel: 'one', pre: () => page.evaluate(() => window.cadui.showPanel('selection')), expect: `window.cadui.getDock().getPanel('model').api.isActive` },
  'View > Tree View Actions > Selection Back': { pre: async () => { await put({ selected: ['base'] }); await put({ selected: ['hot_plate'] }) }, expect: `S.selected[0]==='base'` },
  'View > Tree View Actions > Selection Forward': { pre: async () => { await put({ selected: ['base'] }); await put({ selected: ['hot_plate'] }); await clickMenuEntry(entryAt('View', 'Tree View Actions', 'Selection Back')) }, expect: `S.selected[0]==='hot_plate'` },
  'View > Status Bar': { fresh: true, expect: '!S.statusBar' },
  'Tools > Measure': { expect: task('measure') },
  'Tools > Mass Properties': { sel: 'one', expect: task('mass') },
  'Tools > Units Converter': { expect: task('units') },
  'Tools > Load Image…': { pre: async () => { fileAnswer = [pngFile()] }, post: async () => { fileAnswer = [] }, expect: sawReq('^report:Loaded pixel.png') },
  'Tools > Save Image…': { expect: task('shot') },
  'Tools > View Turntable': { expect: task('turntable') },
  'Tools > Scene Inspector': { expect: task('sceneInspector') },
  'Tools > Dependency Graph': { expect: task('dependencyGraph') },
  'Tools > Export Dependency Graph…': { expect: sawReq('download:') },
  'Tools > Edit Parameters': { expect: task('parameterEditor') },
  'Tools > Customize': { expect: 'S.customizeOpen' },
  'Macro > Record Macro': { expect: task('macroRecord') },
  'Macro > Macros': { expect: task('macros') },
  'CAD Agent > Check': { expect: task('check') },
  'CAD Agent > Verify': { expect: task('verify') },
  'CAD Agent > Done Gate': { expect: task('done') },
  'CAD Agent > Build Part…': { expect: task('build') },
  'CAD Agent > Cut List…': { expect: task('cutlist') },
  'CAD Agent > Bill of Materials…': { expect: task('bom') },
  'CAD Agent > Shop Files…': { expect: task('shop') },
  'CAD Agent > Drawing…': { sel: 'one', expect: task('drawing') },
  'CAD Agent > Tables…': { expect: task('tables') },
  'CAD Agent > Tool Envelope…': { expect: task('tool') },
  'CAD Agent > Bought Parts…': { expect: task('bought') },
  'CAD Agent > Library…': { expect: task('library') },
  'CAD Agent > Render…': { expect: task('render') },
  'CAD Agent > Approve Renders…': { expect: `!!document.querySelector('.msgbox')` },
  'CAD Agent > Rules…': { expect: task('rules') },
  'CAD Agent > Evals…': { expect: task('evals') },
  'Windows > Choose Open Window': { expect: task('windows') },
  'Windows > 1 Start': { pre: () => showPanel('view3d'), expect: `window.cadui.getDock().getPanel('start').api.isActive` },
  [`Windows > 2 ${PROJECT} : 1`]: { pre: () => showPanel('start'), expect: `window.cadui.getDock().getPanel('view3d').api.isActive` },
  'Tools > Clarify Selection': { pre: async () => { const [x, y] = await bodyPoint('hot_plate'); await page.mouse.move(x, y); await page.mouse.move(x + 1, y + 1) }, expect: `!!document.querySelector('.ctx')`, post: closeMenus },
  "Help > What's This?": { expect: `document.body.classList.contains('whats-this-cursor')`, post: () => page.keyboard.press('Escape') },
  'Help > Start Page': { expect: `window.cadui.getDock().getPanel('start').api.isActive` },
  'Help > User Documentation': { expect: sawReq('^open:https://wiki.freecad.org/User_hub') },
  'Help > FreeCAD Forum': { expect: sawReq('^open:https://forum.freecad.org') },
  'Help > Report an Issue': { expect: sawReq('^open:https://github.com/FreeCAD/FreeCAD/issues') },
  'Help > Developers Handbook': { expect: sawReq('^open:https://freecad.github.io/DevelopersHandbook/') },
  'Help > Python Modules Documentation': { expect: sawReq('^open:https://wiki.freecad.org') },
  'Help > FreeCAD Website': { expect: sawReq('^open:https://www.freecad.org') },
  'Help > Donate to FreeCAD': { expect: sawReq('^open:https://www.freecad.org/sponsor') },
  'Help > About cad-agent': { expect: sawReq('^report:cad-agent UI') },
}
const ENTRY = flag('entry', '') ? flag('entry', '').split('|') : null     // --entry=Overlay|Tree View: only the menu entries whose path has one of these
async function testMenus(inv) {
  for (const e of inv) {
    if (ENTRY && !ENTRY.some((t) => e.key.includes(t))) continue
    const meta = { cmd: e.cmd || null, enabled: !e.disabled }
    if (e.sub) { note('menus', e.key, meta, e.disabled && !e.enabledIn.length ? 'N/A' : 'WORKS', e.disabled ? 'sub-menu, empty' : 'opens its sub-menu'); continue }
    const spec = SPEC[e.key] ?? {}
    if (spec.na) { note('menus', e.key, meta, 'N/A', spec.na); continue }
    if (!e.enabledIn.length && !spec.pre) {
      const why = reasonFor(e.label, e.title)
      note('menus', e.key, { ...meta, enabled: false }, why ? 'N/A' : 'NO-OP', why ? `disabled (${why})` : 'disabled, and nothing says why')
      continue
    }
    await resetUI(spec.sel ?? e.enabledIn[0] ?? 'none')
    try { await spec.pre?.() } catch (x) { note('menus', e.key, meta, 'ERROR', `setup failed: ${String(x.message).split('\n')[0]}`); continue }
    const o = await observe(() => clickMenuEntry(e), spec)
    await judge('menus', e.key, meta, o, spec.expect)
    try { await spec.post?.() } catch { /* a reset follows */ }
    if (spec.fresh || o.threw) await openFresh()
  }
}

// ── right-click menus and drop-downs: they are Entry lists in a `.ctx` box, a sub-menu inside the hovered entry ───────
const ctxRoot = () => page.locator('.ctx').last()
/** The entries of the open `.ctx` menu at `path` (the labels of the sub-menus hovered to get there). */
const readCtxAt = (path) => page.evaluate((labels) => {
  const labelOf = (el) => { const c = el.cloneNode(true); c.querySelectorAll('.mb-ico, .mb-kbd, .ctx-sub').forEach((n) => n.remove()); return c.textContent.trim() }
  let box = [...document.querySelectorAll('.ctx')].at(-1)
  for (const l of labels) {
    const it = box && [...box.children].find((c) => c.classList.contains('mb-item') && labelOf(c) === l)
    box = it?.querySelector(':scope > .ctx-sub') ?? null
  }
  if (!box) return null
  return [...box.children].map((el, i) => {
    if (!el.classList.contains('mb-item')) return { i, sep: true }
    return { i, label: labelOf(el), disabled: el.hasAttribute('data-disabled'), sub: [...el.querySelectorAll('.mb-kbd')].some((k) => k.textContent === '▸'), checked: !!el.querySelector(':scope > .mb-ico .mb-check'),
      kbd: [...el.querySelectorAll(':scope > .mb-kbd')].map((n) => n.textContent).filter((t) => t !== '▸').join(''), title: el.getAttribute('title') || el.getAttribute('data-fc-title') || '', cmd: el.dataset.cmd || '' }
  })
}, path)
/** Opens a `.ctx` menu with `open`, then hovers down `path`; returns the locator of the box the last label opened. */
async function openCtx(open, path = []) {
  await closeMenus()
  await open()
  await ctxRoot().waitFor({ timeout: 5000 })
  let box = ctxRoot()
  for (let d = 0; d < path.length; d++) {
    const label = path[d]
    const items = await readCtxAt(path.slice(0, d))
    const it = items?.find((x) => x.label === label)
    if (!it) throw new Error(`no entry ${path.join(' > ')}`)
    const item = box.locator(':scope > *').nth(it.i)
    await item.hover()
    box = item.locator(':scope > .ctx-sub')
    await box.waitFor({ timeout: 3000 })
  }
  return box
}
async function inventoryCtx(open) {
  const out = []
  const walk = async (path) => {
    await openCtx(open, path)
    const items = (await readCtxAt(path)) ?? []
    await closeMenus()
    for (const it of items) {
      if (it.sep) continue
      out.push({ ...it, path: [...path, it.label] })
      if (it.sub && !it.disabled) await walk([...path, it.label])
    }
  }
  await walk([])
  return out
}
async function clickCtxEntry(open, e) {
  const parent = e.path.slice(0, -1)
  const box = await openCtx(open, parent)
  const it = (await readCtxAt(parent)).find((x) => x.label === e.label)
  if (!it || it.disabled) throw new Error(`${e.path.join(' > ')} is not there or not enabled`)
  await box.locator(':scope > *').nth(it.i).click()
  return it.checked
}
/** Every entry of one right-click menu or drop-down, tested like a menu bar entry. `spec` is keyed by the entry's path. */
async function testCtx(surface, open, { sel = 'none', specs = {}, prep, labels } = {}) {
  await resetUI(sel); await prep?.()
  // one right click opens one menu: a portal's events go up to the surface it was opened from, which can open its own menu over it
  await closeMenus(); await open(); await sleep(200)
  const stacked = await page.locator('body > .ctx').count()
  await closeMenus()
  if (stacked > 1) note('context', surface, { enabled: true }, 'WRONG', `${stacked} menus open at once`)
  const inv = await inventoryCtx(open)
  if (labels) {      // the menu must be this surface's own: a right click can open the menu of something it sits in
    const top = inv.filter((e) => e.path.length === 1).map((e) => e.label)
    const missing = labels.filter((l) => !top.includes(l)), extra = top.filter((l) => !labels.includes(l))
    if (missing.length || extra.length) note('context', surface, { enabled: true }, 'WRONG', `the menu has ${top.join(', ') || 'no entries'}; expected ${labels.join(', ')}`)
  }
  for (const e of inv) {
    const path = `${surface} > ${e.path.join(' > ')}`, meta = { cmd: e.cmd || null, enabled: !e.disabled }
    if (e.sub) { note('context', path, meta, e.disabled ? 'N/A' : 'WORKS', 'opens its sub-menu'); continue }
    const spec = specs[e.path.join(' > ')] ?? {}
    if (spec.na) { note('context', path, meta, 'N/A', spec.na); continue }
    if (e.disabled && !spec.pre) {
      const why = reasonFor(e.label, e.title)
      note('context', path, meta, why ? 'N/A' : 'NO-OP', why ? `disabled (${why})` : 'disabled, and nothing says why')
      continue
    }
    await resetUI(spec.sel ?? sel); await prep?.()
    try { await spec.pre?.() } catch (x) { note('context', path, meta, 'ERROR', `setup failed: ${String(x.message).split('\n')[0]}`); continue }
    let was
    const o = await observe(async () => { was = await clickCtxEntry(open, e) }, spec)
    if (!o.fx.length && !o.threw && was !== undefined) {      // a check mark that flipped is an effect the closed menu does not show
      try {
        await openCtx(open, e.path.slice(0, -1))
        const now = (await readCtxAt(e.path.slice(0, -1))).find((x) => x.label === e.label)
        await closeMenus()
        if (now && now.checked !== was) o.fx.push('check mark')
      } catch { /* the menu cannot be read again: the click stays as it was judged */ }
    }
    await judge('context', path, meta, o, spec.expect)
    try { await spec.post?.() } catch { /* a reset follows */ }
    if (spec.fresh || o.threw) await openFresh()
  }
}

// ── toolbars: every button, and every entry of its drop-down ────────────────────────────────────────────────────────────
const toolbarList = () => page.evaluate(() => [...document.querySelectorAll('.toolbar button')].map((el) => ({
  title: el.getAttribute('title') || el.getAttribute('data-fc-title') || '', text: el.textContent.trim(), cmd: el.dataset.cmd || '', disabled: el.disabled,
  drop: el.classList.contains('tb-drop'), combo: el.getAttribute('role') === 'combobox', tab: el.getAttribute('role') === 'tab' })))
/** The n-th toolbar button with this command id (a tooltip such as "Undo Placement" follows the journal), else this title or text. */
const toolbarButton = async (b, nth = 0) => (await page.evaluateHandle(({ title, text, cmd, drop, nth }) => {
  const all = [...document.querySelectorAll('.toolbar button')].filter((el) => (cmd
    ? el.dataset.cmd === cmd && el.classList.contains('tb-drop') === drop
    : (el.getAttribute('title') || el.getAttribute('data-fc-title') || '') === title && (title || el.textContent.trim() === text)))
  return all[nth] ?? null
}, { title: b.title, text: b.text, cmd: b.cmd || '', drop: !!b.drop, nth })).asElement()
const api = (path, body) => page.evaluate(async ([p, b]) => (await fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(b) })).json(), [path, body])
/** An edit the journal can undo (a hand move through `cad place`, as the Placement task writes it). */
let editSeq = 0
async function makeEdit(n = 1) {
  const have = await getS('S.undo.length')
  let answer
  // a different move each time: a change that undoing just took back is not recorded again as a new step
  for (let i = 0; i < n; i++) answer = await api('/api/place', { slug: PROJECT, body: 'hot_plate', move: [1 + 0.5 * ++editSeq, 0, 0], turn: [0, 0, 0], about: [0, 0, 0] })
  try { await page.waitForFunction((k) => window.cadui.getState().undo.length >= k, have + n, { timeout: 120000 }) } catch {
    throw new Error(`the journal did not grow in the page (it had ${have} steps; \`place\` answered exit ${answer?.exit} ${String(answer?.error ?? answer?.stderr ?? '').slice(0, 120)})`)
  }
  await settle({ min: 300, quiet: 500, max: 90000 })
}
async function makeRedo() {
  await makeEdit()
  await api('/api/undo', { slug: PROJECT })
  await page.waitForFunction(() => window.cadui.getState().redo.length > 0, null, { timeout: 60000 })
  await settle({ min: 300, quiet: 500, max: 90000 })
}
const unplace = async () => { await api('/api/place', { slug: PROJECT, body: 'hot_plate', reset: true }); await settle({ min: 300, quiet: 500, max: 90000 }) }
/** The menu bar's expectation for an entry of the same name, for the toolbar and right-click entries that run the same command. */
const menuSpec = (label) => { const k = Object.keys(SPEC).find((x) => x.endsWith(` > ${label}`)); return k ? SPEC[k] : undefined }
const TB_SPEC = {
  Std_New: { expect: task('newDocument') }, Std_Open: { expect: task('openDocument') },
  Std_Undo: { pre: makeEdit, post: unplace, expect: sawReq('POST /api/undo') },
  Std_Redo: { pre: makeRedo, post: unplace, expect: sawReq('POST /api/redo') },
  'Undo to…': { pre: makeEdit, post: unplace }, 'Redo to…': { pre: makeRedo, post: unplace },
  Std_Refresh: { expect: sawReq('POST /api/check') },
  Std_Copy: { sel: 'one', expect: `FX.includes('clipboard')` },
  Std_ViewFitAll: SPEC['View > Standard Views > Fit All'], Std_ViewFitSelection: SPEC['View > Standard Views > Fit Selection'],
  Std_AlignToSelection: SPEC['View > Standard Views > Align to Selection'],
  Std_Measure: { expect: task('measure') }, Std_MassProperties: { sel: 'one', expect: task('mass') },
  Std_ViewIsometric: viewSpec('iso'), Std_ViewFront: viewSpec('front'), Std_ViewTop: viewSpec('top'), Std_ViewRight: viewSpec('right'),
  Std_ViewRear: viewSpec('rear'), Std_ViewBottom: viewSpec('bottom'), Std_ViewLeft: viewSpec('left'),
  Std_WhatsThis: SPEC["Help > What's This?"],
  Std_DlgMacroRecord: { expect: task('macroRecord') }, Std_DlgMacroExecute: { expect: task('macros') },
  CADAgent_Check: { expect: task('check') }, CADAgent_Verify: { expect: task('verify') }, CADAgent_Done: { expect: task('done') },
  CADAgent_Tables: { expect: task('tables') }, CADAgent_ToolEnvelope: { expect: task('tool') }, CADAgent_Bought: { expect: task('bought') },
  CADAgent_Library: { expect: task('library') }, CADAgent_Bom: { expect: task('bom') }, CADAgent_Shop: { expect: task('shop') },
  CADAgent_Drawing: { sel: 'one', expect: task('drawing') }, CADAgent_Render: { expect: task('render') }, CADAgent_Rules: { expect: task('rules') },
  Std_ToggleVisibility: SPEC['View > Visibility > Toggle Visibility'], Std_Edit: SPEC['Edit > Toggle Edit Mode'],
  Std_TransformManip: { sel: 'one', expect: task('transform') }, Std_Placement: { sel: 'one', expect: task('placement') },
}
const key = (b, wb) => `${b.cmd || b.title || b.text}${wb === 'inspection' && b.cmd === 'CADAgent_Verify' ? '@inspection' : ''}`
TB_SPEC['CADAgent_Verify@inspection'] = { expect: sawReq('POST /api/verify') }
const ONLY_TB = flag('toolbar', '')
async function testToolbars() {
  await put({ toolbars: { Clipboard: true, Macro: true, 'Individual Views': true } })
  // which buttons there are depends on the workbench and on what is selected: list them all, test each where it is live
  const seen = new Map()
  for (const [wb, sel] of [['agent', 'none'], ['agent', 'one'], ['agent', 'face'], ['agent', 'two'], ['design', 'one'], ['assembly', 'none'], ['inspection', 'none']]) {
    await resetUI(sel); await put({ workbench: wb }); await sleep(300)
    const counts = new Map()
    for (const b of await toolbarList()) {
      const id = `${b.title}|${b.text}`, n = counts.get(id) ?? 0; counts.set(id, n + 1)
      const k = `${id}#${n}`, cur = seen.get(k)
      if (!cur) seen.set(k, { ...b, n, k, wb, enabledIn: b.disabled ? [] : [[wb, sel]] })
      else if (!b.disabled) cur.enabledIn.push([wb, sel])
    }
  }
  for (const b of seen.values()) {
    const name = (b.title || b.text).split(/ — |: /)[0].slice(0, 60), path = `toolbar > ${name}${b.drop ? ' (drop-down)' : ''}`, meta = { cmd: b.cmd || null, enabled: !b.disabled || b.enabledIn.length > 0 }
    if (ONLY_TB && !ONLY_TB.split('|').some((t) => name.includes(t))) continue
    const spec = TB_SPEC[key(b, b.enabledIn[0]?.[0])] ?? {}
    if (!b.enabledIn.length && !spec.pre) {
      const why = reasonFor(name, b.title)
      note('toolbars', path, { ...meta, enabled: false }, why ? 'N/A' : 'NO-OP', why ? `disabled (${why})` : 'disabled, and nothing says why')
      continue
    }
    const [wb, sel] = b.enabledIn[0] ?? [b.wb, 'none']
    const prep = async () => { await resetUI(spec.sel ?? sel); await put({ workbench: wb, toolbars: { Clipboard: true, Macro: true, 'Individual Views': true } }) }
    if (b.combo) {   // the workbench selector: each workbench in turn
      await prep()
      const o = await observe(async () => { await (await toolbarButton(b, b.n)).click(); await page.locator('[role=listbox] [role=option]:not(.current)').first().click() })
      await judge('toolbars', path, meta, o, `S.workbench!=='${wb}'`)
      continue
    }
    await prep()
    if (!b.drop) try { await spec.pre?.() } catch (x) { note('toolbars', path, meta, 'ERROR', `setup failed: ${String(x.message).split('\n')[0]}`); continue }
    if (b.drop) {
      // a drop-down: its entries are a menu
      const open = async () => { await (await toolbarButton(b, b.n)).click() }
      // the entries are the menu bar's: a spec of the same name there says what each should do
      // (the entries of Undo to… and Redo to… are steps of the journal named after what they did, not the commands of the same name)
      const own = { 'No Selection Filters': { pre: () => put({ selFilter: 'face' }), expect: 'S.selFilter===null' } }
      const journal = /^(Undo|Redo) to|^Pose/.test(name)       // (and the poses: Pose > Home puts the machine home, it is not the Home view)
      const same = new Proxy({}, { get: (_, path) => { if (typeof path !== 'string') return undefined; const last = path.split(' > ').at(-1); return own[last] ?? (journal ? {} : menuSpec(last)) } })
      await testCtx(`toolbar > ${name}`, open, { sel: spec.sel ?? sel, specs: same, prep: async () => { await put({ workbench: wb }); await spec.pre?.() } })
      await spec.post?.()
      continue
    }
    const o = await observe(async () => { await (await toolbarButton(b, b.n)).click() }, spec)
    await judge('toolbars', path, meta, o, spec.expect)
    try { await spec.post?.() } catch { /* a reset follows */ }
    if (spec.fresh || o.threw) await openFresh()
  }
  await put({ workbench: 'agent' })
}

// ── task panels: every button, check box, tab, link and combo box of each ───────────────────────────────────────────────
// The buttons of a panel (and its tabs, links and clickable rows) always; its check boxes, radio buttons, combo boxes, colours and sliders with --forms.
const FORMS = args.includes('--forms')
const BUTTONS = 'button:not([role=combobox]), a[href], a[download], [role=tab], .tbox-head, summary, .taskview .trow'
const CONTROLS = FORMS ? `${BUTTONS}, button[role=combobox], select, input[type=checkbox], input[type=radio], input[type=color], input[type=range]` : BUTTONS
/** What a panel holds that a click does something to, in document order. */
const listControls = (root) => page.evaluate(([rootSel, sel]) => {
  const r = document.querySelector(rootSel)
  if (!r) return []
  return [...r.querySelectorAll(sel)].map((el) => ({ tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '', type: el.type || '', text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
    title: el.getAttribute('title') || el.getAttribute('data-fc-title') || el.closest('[title]')?.getAttribute('title') || '', disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
    checked: el.checked ?? null, combo: el.getAttribute('role') === 'combobox', native: el.tagName === 'SELECT', label: el.closest('label')?.textContent?.trim().slice(0, 40) ?? '',
    current: (el.getAttribute('role') === 'tab' || el.classList.contains('trow')) && (el.getAttribute('aria-selected') === 'true' || el.classList.contains('sel') || el.classList.contains('on')),
    row: el.classList.contains('trow'), head: el.classList.contains('tbox-head') }))
}, [root, CONTROLS])
const controlId = (c) => `${c.tag}${c.type ? ':' + c.type : ''}|${c.role}|${c.text}|${c.title}|${c.label}`
/** The element of the n-th control with this identity (the panel's DOM changes as controls are used, so it is found again each time). */
async function controlHandle(root, c, nth) {
  return (await page.evaluateHandle(([rootSel, sel, id, n]) => {
    const r = document.querySelector(rootSel)
    const idOf = (el) => `${el.tagName.toLowerCase()}${el.type ? ':' + el.type : ''}|${el.getAttribute('role') || ''}|${(el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40)}|${el.getAttribute('title') || el.getAttribute('data-fc-title') || ''}|${el.closest('label')?.textContent?.trim().slice(0, 40) ?? ''}`
    return r ? [...r.querySelectorAll(sel)].filter((el) => idOf(el) === id)[n] ?? null : null
  }, [root, CONTROLS, controlId(c), nth])).asElement()
}
const CLOSERS = /^(OK|Cancel|Close|Done|Save|Create|Open|Record|Apply|Back)$/
const controlName = (c) => c.combo || c.native ? `${c.label || c.text || 'combo box'} (combo box)` : c.type === 'checkbox' || c.type === 'radio' ? `${c.label || c.title} (${c.type})`
  : c.type === 'color' || c.type === 'range' ? `${c.label || c.title || c.type} (${c.type})` : c.text || c.title || c.tag
/** Uses one control the way a person does, and says what that was. */
async function useControl(h, c) {
  if (c.native) {
    const other = await h.evaluate((el) => [...el.options].map((o) => o.value).find((v) => v !== el.value))
    if (other === undefined) throw new Error('a list with one choice')
    await h.selectOption(other)
  } else if (c.combo) {
    await h.click()
    const opt = page.locator('[role=listbox] [role=option]:not(.current):not(.disabled)').first()
    if (await opt.count()) await opt.click(); else throw new Error('a combo box with one choice')
  } else if (c.type === 'color') await h.evaluate((el) => window.__wc.setInput(el, el.value.toLowerCase() === '#336699' ? '#993366' : '#336699'))
  else if (c.type === 'range') await h.evaluate((el) => window.__wc.setInput(el, String(Math.round((+el.min + +el.max) / 2) === +el.value ? +el.max : Math.round((+el.min + +el.max) / 2))))
  else await h.click()
}
/** Opens a panel with `open`, then uses each live control in it (the ones that close it last). */
async function walkPanel(surface, root, open, { sel = 'none', fill, before, skip = () => false, ignore = () => false, expectFor = () => undefined, fresh = false, max = 90000, group = 'tasks' } = {}) {
  const reopen = async () => { await resetUI(sel); await open(); await settle({ min: 400, quiet: 500, max: 120000 }); await fill?.() }
  await reopen()
  const all = (await listControls(root)).filter((c) => !ignore(c))      // `ignore`: what the list picks up that is not a control (a read-only tree's rows)
  const counts = new Map(), plan = []
  for (const c of all) { const id = controlId(c), n = counts.get(id) ?? 0; counts.set(id, n + 1); plan.push({ c, n }) }
  // the ones that close the panel go last, so one visit shows the rest; a box's title folds the box, and the controls in it with it, so those come after the rest
  const rank = (x) => (CLOSERS.test(x.c.text) ? 2 : x.c.head ? 1 : 0)
  plan.sort((a, b) => rank(a) - rank(b))
  const later = []        // a radio button that is the choice already: it can only be clicked once another one has been
  const one = async ({ c, n }, again) => {
    const name = controlName(c), path = `${surface} > ${name}`, meta = { cmd: null, enabled: !c.disabled }
    if (skip(c)) return note(group, path, meta, 'HUMAN', 'not clicked: a person decides this')
    if (c.disabled) {
      const why = reasonFor(name, c.title)
      return note(group, path, { ...meta, enabled: false }, 'N/A', why ? `disabled (${why})` : 'disabled until its fields are filled or its state allows it')
    }
    if (((c.type === 'radio' && c.checked) || c.current) && !again) { later.push({ c, n }); return }
    await before?.()      // (a task an earlier click opened would make the next one that opens it look like it did nothing)
    // the panel may have closed or changed under the last click: open it again for this one
    let h = await controlHandle(root, c, n)
    if (!h || !(await h.evaluate((el) => el.isConnected).catch(() => false))) { await reopen(); h = await controlHandle(root, c, n) }
    if (!h) return note(group, path, meta, 'N/A', 'not there any more after the earlier clicks')
    if (await h.evaluate((el) => el.disabled === true).catch(() => false)) return note(group, path, { ...meta, enabled: false }, 'N/A', 'greyed out by an earlier click in this panel')
    let o = await observe(() => useControl(h, c), { max, restore: false })
    if (o.threw && /not attached|detached/i.test(o.threw)) {      // the panel drew again between finding the control and clicking it
      await reopen(); h = await controlHandle(root, c, n)
      if (h) o = await observe(() => useControl(h, c), { max, restore: false })
    }
    await judge(group, path, meta, o, expectFor(c))
    // never leave a question open: its answer is a person's
    await answerNo()
  }
  for (const item of plan) await one(item, false)
  for (const item of later) {
    const h = await controlHandle(root, item.c, item.n)
    if (h && !(await h.evaluate((el) => el.checked === true || el.classList.contains('sel') || el.getAttribute('aria-selected') === 'true'))) await one(item, true)
    else note(group, `${surface} > ${controlName(item.c)}`, { cmd: null, enabled: true }, 'N/A', 'the choice already made, and the only one of its group')
  }
  if (fresh) await openFresh()
}

// ── single controls: a thing to click, what it should do, what it needs ────────────────────────────────────────────────
/** Clicks `locate()` (an element handle or a locator) and judges what it did. `spec` as for menu entries, plus dbl and right. */
async function clickOne(surface, path, meta, locate, spec = {}) {
  await resetUI(spec.sel ?? 'none')
  try { await spec.pre?.() } catch (x) { return note(surface, path, meta, 'ERROR', `setup failed: ${String(x.message).split('\n')[0]}`) }
  const o = await observe(async () => {
    const target = await locate()
    if (!target) throw new Error('not on the page')
    if (spec.dbl) await target.dblclick(); else await target.click(spec.right ? { button: 'right' } : spec.click)
  }, spec)
  const row = await judge(surface, path, meta, o, spec.expect)
  try { await spec.post?.() } catch { /* a reset follows */ }
  if (spec.fresh || o.threw) await openFresh()
  return row
}
const L = (sel, opts) => () => page.locator(sel, opts).first()
const panelActive = (id) => `window.cadui.getDock().getPanel('${id}')?.api.isActive`
const panelGone = (id) => `!window.cadui.getDock().getPanel('${id}')`
const showPanel = (id) => page.evaluate((i) => window.cadui.showPanel(i), id)
const hasCtx = `!!document.querySelector('.ctx')`

// ── the docks: tabs, their close buttons and the title-bar buttons ─────────────────────────────────────────────────────
const dockBtn = (group, title) => L(`.dv-groupview:has(.dv-tab[aria-label="${group}"]) .ovl-tbtn[title^="${title}"]`)
async function testDocks() {
  const TABS = [['Model', 'model', 'selection'], ['Start', 'start', 'view3d'], ['Report View', 'report', 'console'], ['Checks', 'checks', 'console'], ['Console', 'console', 'report']]
  for (const [label, id, other] of TABS) {
    // a tab brings its panel forward: bring another one of its group forward first
    await clickOne('docks', `tab > ${label}`, { enabled: true }, L(`.dv-tab[aria-label="${label}"]`), { pre: () => showPanel(other), expect: panelActive(id) })
  }
  // the document tabs (QTabBar's close button) close their window; a dock closes from its title bar, below
  await clickOne('docks', 'tab > Start > close (x)', { enabled: true }, L(`.dv-tab[aria-label="Start"] .dv-default-tab-action`), { expect: panelGone('start'), fresh: true })
  await clickOne('docks', `tab > ${PROJECT} : 1 > close (x)`, { enabled: true }, L(`.dv-tab[aria-label="${PROJECT} : 1"] .dv-default-tab-action`), { expect: '!V', fresh: true })
  // the title bar of a docked panel (OverlayManager::createTitleBar), and of an overlaid one
  for (const [group, id] of [['Model', 'model'], ['Report View', 'report']]) {
    await clickOne('docks', `${group} title bar > Toggle overlay`, { enabled: true }, dockBtn(group, 'Toggle overlay'), { expect: `window.cadui.getDock().getPanel('${id}').group.api.location.type==='floating'`, fresh: true })
    // a button that is greyed out is not clicked: it says why in its tooltip, or it is a button that does nothing
    const floatBtn = dockBtn(group, 'Toggle floating window')
    if (await floatBtn().isDisabled()) note('docks', `${group} title bar > Toggle floating window`, { enabled: false }, reasonFor('Toggle floating window', await floatBtn().getAttribute('title')) ? 'N/A' : 'NO-OP', 'disabled (tooltip)')
    else await clickOne('docks', `${group} title bar > Toggle floating window`, { enabled: true }, floatBtn, {})
    await clickOne('docks', `${group} title bar > Close dock window`, { enabled: true }, dockBtn(group, 'Close dock window'), { expect: panelGone(id), fresh: true })
    const overlaid = async () => { await (await dockBtn(group, 'Toggle overlay')()).click(); await settle({ min: 700, quiet: 600 }) }
    for (const [title, expectation] of [['Toggle transparent mode', null], ['Select auto show/hide mode', hasCtx], ['Toggle overlay', `window.cadui.getDock().getPanel('${id}').group.api.location.type!=='floating'`], ['Toggles the visibility', null]]) {
      await clickOne('docks', `${group} overlay title bar > ${title}`, { enabled: true }, dockBtn(group, title), { pre: overlaid, expect: expectation ?? undefined, fresh: true })
    }
  }
}

// ── the status bar ─────────────────────────────────────────────────────────────────────────────────────────────────────
async function testStatusBar() {
  const bar = (sel) => L(`.statusbar ${sel}`)
  const toConsole = () => showPanel('console')
  await clickOne('status', 'checks count (click)', { enabled: true }, bar('.sb-item:not(.verdict):not(.live)'), { pre: toConsole, expect: panelActive('checks') })
  await clickOne('status', 'verdict (click)', { enabled: true }, bar('.verdict'), { pre: toConsole, expect: panelActive('checks') })
  await clickOne('status', 'bottom panel toggle', { enabled: true }, bar('.sb-btn'), { fresh: true })
  await clickOne('status', 'notifications button', { enabled: true }, bar('.notify-btn'), { expect: `!!document.querySelector('.notify-list')` })
  await clickOne('status', 'unit system (Dimension) button', { enabled: true }, bar('.sb-dim'), { expect: hasCtx })
  await clickOne('status', 'navigation style button', { enabled: true }, bar('.sb-nav'), { expect: hasCtx })
  await clickOne('status', 'right-click on the bar', { enabled: true }, bar('.sb-msg'), { right: true, expect: hasCtx })
  // the menus those buttons open
  await testCtx('status > Dimension menu', async () => { await page.locator('.statusbar .sb-dim').click() })
  await testCtx('status > navigation menu', async () => { await page.locator('.statusbar .sb-nav').click() })
  await testCtx('status > bar menu', async () => { await page.locator('.statusbar .sb-msg').click({ button: 'right' }) })
}

// ── the model tree ───────────────────────────────────────────────────────────────────────────────────────────────────────
const treeRow = (n) => L(`.trow[data-name="${n}"]`)
async function testTree() {
  const T = (path, locate, spec, enabled = true) => clickOne('tree', path, { enabled }, locate, spec)
  await T('eye icon (toggle visibility)', L('.trow[data-name="base"] .teye'), { expect: `S.hidden.includes('base')` })
  await T('document twisty (fold)', L('.trow.doc .twisty'), { expect: `document.querySelectorAll('.trow[data-name]').length===0`, fresh: true })
  await T('object row (click)', treeRow('hot_plate'), { expect: `S.selected.length===1&&S.selected[0]==='hot_plate'` })
  // Ctrl+click is a right click on a Mac; the page takes Cmd (a Qt Ctrl) for "add to the selection"
  await T('object row (Cmd+click adds)', treeRow('hot_plate'), { pre: () => put({ selected: ['base'] }), click: { modifiers: ['Meta'] }, expect: `S.selected.length===2` })
  await T('object row (Shift+click selects a range)', treeRow('hot_plate'), { pre: async () => { await treeRow('base')().click() }, click: { modifiers: ['Shift'] }, expect: `S.selected.length>=2` })
  await T('object row (double-click edits)', treeRow('hot_plate'), { dbl: true, expect: `S.task?.kind==='params'||S.task?.kind==='transform'` })
  await T('document row (click clears the selection)', L('.trow.doc'), { pre: () => put({ selected: ['base'] }), expect: 'S.selected.length===0' })
  const objectSpecs = {
    'Toggle Visibility': { expect: `S.hidden.includes('hot_plate')` }, 'Hide Selection': { expect: `S.hidden.includes('hot_plate')` }, 'Show Selection': { pre: () => put({ hidden: ['hot_plate'] }), expect: `!S.hidden.includes('hot_plate')` },
    'Toggle Selectability': { expect: `S.unselectable.includes('hot_plate')` }, 'Random Color': { expect: `S.view['hot_plate']?.shapeColor!=null` }, 'Toggle Transparency': { expect: `S.view['hot_plate']?.transparency>0` },
    Copy: { expect: `FX.includes('clipboard')` }, 'Send to Console': { expect: `S.consoleDraft.includes('hot_plate')` }, Transform: { expect: task('transform') }, Placement: { expect: task('placement') },
    'Drawing…': { expect: task('drawing') }, 'Mark to Recompute': { expect: sawReq('POST /api/check') }, 'Recompute Object': { expect: sawReq('POST /api/check') }, 'Open File Location': { expect: sawReq('POST /api/reveal') },
    'Properties': { na: 'the Model tab it brings forward is the one the tree is in' },
    'Edit hot_plate': { expect: `S.task?.kind==='params'||S.task?.kind==='transform'` }, 'Transform hot_plate': { expect: task('transform') },
    'Tree Settings > Show Description': { expect: `!S.treeUI.hideColumn` }, 'Tree Settings > Show Internal Name': { expect: `!S.treeUI.hideInternalNames` },
    'Show Items Hidden in Tree View': { expect: 'S.treeShowHidden' }, 'Toggle Visibility in Tree View': { expect: `S.view['hot_plate']?.showInTree===false` },
    'Select All Instances': { expect: `S.selected.includes('hot_plate')` },
  }
  const resetTree = async () => { await put({ treeUI: { ...(await getS('S.treeUI')), hideColumn: true, hideInternalNames: true }, treeShowHidden: false, view: {}, hidden: [], unselectable: [] }) }
  for (const s of Object.values(objectSpecs)) s.post = s.post ?? resetTree
  await testCtx('tree > object menu', async () => { await page.locator('.trow[data-name="hot_plate"]').click({ button: 'right' }) }, { specs: objectSpecs, sel: 'one' })
  await testCtx('tree > document menu', async () => { await page.locator('.trow.doc').click({ button: 'right' }) }, {
    specs: { 'Open File Location': { expect: sawReq('POST /api/reveal') }, 'Search Objects': { expect: 'S.treeFilter!==null' }, 'Mark to Recompute': { expect: sawReq('POST /api/check') }, 'Show Items Hidden in Tree View': { expect: 'S.treeShowHidden', post: resetTree } } })
  await testCtx('tree > empty space menu', async () => {
    const box = await page.locator('.tree').boundingBox()
    await page.mouse.click(box.x + box.width / 2, box.y + box.height - 8, { button: 'right' })
  }, { specs: { 'Tree Settings > Show Description': { expect: `!S.treeUI.hideColumn`, post: resetTree }, 'Tree Settings > Show Internal Name': { expect: `!S.treeUI.hideInternalNames`, post: resetTree } } })
}

// ── the property view ──────────────────────────────────────────────────────────────────────────────────────────────────
async function testProperties() {
  const T = (path, locate, spec, enabled = true) => clickOne('properties', path, { enabled }, locate, spec)
  const tab = (name) => L('.ptabs button', { hasText: new RegExp(`^${name}$`) })
  const data = async () => { await put(SELECTION.one); await tab('Data')().click(); await sleep(250); await page.evaluate(() => { window.__rows0 = document.querySelectorAll('.pgrid .prow').length }) }
  await T('View tab', tab('View'), { sel: 'one', expect: `!!document.querySelector('.pgrid .pgroup')&&document.querySelector('.pgrid').innerText.includes('Display Options')` })
  await T('Data tab', tab('Data'), { sel: 'one', pre: async () => { await put(SELECTION.one); await tab('View')().click() }, expect: `document.querySelector('.pgrid').innerText.includes('Placement')` })
  await T('Placement row (opens its Angle, Axis, Position)', L('.pgrid .prow.ro', { hasText: 'Placement' }), { sel: 'one', pre: data, expect: `document.querySelector('.pgrid').innerText.includes('Angle')` })
  await T('parameter value (click to edit)', L('.pgrid .pv.edit'), { sel: 'one', pre: data, expect: `!!document.querySelector('.pgrid .pedit, .pgrid .pv.edit input')` })
  await T('group header (double-click folds)', L('.pgrid .pgroup'), { sel: 'one', dbl: true, pre: data, expect: `document.querySelectorAll('.pgrid .prow').length<window.__rows0` })
  // the View tab's buttons
  await walkPanel('properties > View tab', '.props .pgrid', async () => { await put(SELECTION.one); await tab('View')().click() }, { sel: 'one', group: 'properties' })
  // the right-click menu: Expand to Default only shows on groups that are folded, Default Expand is the current choice of three
  const open = async () => { await page.locator('.pgrid .prow, .pgrid .pgroup').first().click({ button: 'right' }) }     // a row, or a group header when every group is folded
  const foldAll = async () => { await data(); for (const g of await page.locator('.pgrid .pgroup').all()) await g.dblclick() }
  const sub = (label) => async () => { await data(); await clickCtxEntry(open, { path: ['Expand/Collapse Properties', label], label }) }
  await testCtx('properties > menu', open, { sel: 'one', prep: data,
    specs: { Copy: { expect: `FX.includes('clipboard')` },
      'Expand/Collapse Properties > Expand to Default': { pre: foldAll, expect: `document.querySelectorAll('.pgrid .prow').length>3` },
      // Default Expand is the current choice until another is made: the click that makes another one is its set-up, and the page starts again without it
      'Expand/Collapse Properties > Default Expand': { pre: sub('Auto Expand'), expect: `JSON.parse(localStorage.getItem('cadui.props.expandMode')||'"default"')==='default'`,
        post: () => page.evaluate(() => localStorage.removeItem('cadui.props.expandMode')), fresh: true },
      'Expand/Collapse Properties > Auto Expand': { expect: `JSON.parse(localStorage.getItem('cadui.props.expandMode')||'"default"')==='auto-expand'` },
      'Expand/Collapse Properties > Auto Collapse': { expect: `JSON.parse(localStorage.getItem('cadui.props.expandMode')||'"default"')==='auto-collapse'` } } })
}

// ── the selection view, report view, console and checks ─────────────────────────────────────────────────────────────────
async function testPanels() {
  const T = (surface, path, locate, spec, enabled = true) => clickOne(surface, path, { enabled }, locate, spec)
  // Selection view
  await T('selection view', 'clear button (x)', L('.sv .sv-clear'), { pre: async () => { await showPanel('selection'); await page.locator('.sv .sv-search').fill('hot'); await sleep(200) }, expect: `document.querySelector('.sv-search').value===''` })
  await T('selection view', 'Picked object list (check box)', L('.sv .tcheck input'), { pre: () => showPanel('selection'), expect: 'S.pickList', post: () => put({ pickList: false }) })
  await T('selection view', 'item (double-click toggles it)', L('.sv .sv-item'), { sel: 'one', dbl: true, pre: () => showPanel('selection'), expect: 'S.selected.length===0' })
  await testCtx('selection view > item menu', async () => { await page.locator('.sv .sv-item').first().click({ button: 'right' }) }, { sel: 'one', prep: () => showPanel('selection'),
    specs: { 'Select Only': { expect: `S.selected.length===1` }, Deselect: { expect: 'S.selected.length===0' }, 'Zoom Fit': { expect: `S.selected.length===1` }, 'Go to Selection': { expect: panelActive('model') },
      'Mark to Recompute': { expect: sawReq('POST /api/check') }, 'To Python Console': { expect: `S.consoleDraft.includes('hot_plate')` } } })
  // Report view
  const report = () => showPanel('report')
  await testCtx('report view > menu', async () => { await page.locator('.report').click({ button: 'right' }) }, { prep: report,
    specs: { Copy: { expect: `FX.includes('clipboard')` }, 'Select All': { expect: `!getSelection().isCollapsed` }, Clear: { expect: `document.querySelectorAll('.report .rl').length===0` },
      'Save As…': { expect: sawReq('download:'), }, 'Options > Go to End': { expect: `JSON.parse(localStorage.getItem('cadui.report.goToEnd')??'true')===false` } } })
  // Console
  // the command line: what is typed runs as the same `cad` command an agent would run
  const typed = (line) => async () => ({ click: async () => { const input = page.locator('.console .cinput input'); await input.fill(line); await input.press('Enter') } })
  await T('console', 'command line (`help` + Enter)', typed('help'), { pre: () => showPanel('console'), expect: `S.consoleLines.some((l)=>l.kind==='out'&&/check \\| verify/.test(l.text))` })
  await T('console', 'command line (`select base` + Enter)', typed('select base'), { pre: () => showPanel('console'), expect: `S.selected.includes('base')` })
  await T('console', 'command line (`view top` + Enter)', typed('view top'), { pre: () => showPanel('console'), expect: `W.isView('top')` })
  await T('console', 'command line (`fit` + Enter)', typed('fit'), { pre: async () => { await showPanel('console'); await page.evaluate(() => window.cadui.getView().zoomOut()) } })
  await T('console', 'command line (`mass hot_plate` + Enter runs a cad command)', typed('mass hot_plate'), { pre: () => showPanel('console'), expect: sawReq('POST /api/cad mass') })
  const selectConsole = () => page.evaluate(() => { const c = document.querySelector('.console'), r = document.createRange(); r.selectNodeContents(c); getSelection().removeAllRanges(); getSelection().addRange(r) })
  await testCtx('console > menu', async () => { await page.locator('.console').click({ button: 'right', position: { x: 40, y: 20 } }) }, { prep: () => showPanel('console'),
    specs: {
      Copy: { pre: selectConsole, expect: `FX.includes('clipboard')` }, 'Copy Command': { pre: selectConsole, expect: `FX.includes('clipboard')` },
      'Copy History': { pre: () => runConsoleLine('help'), expect: `FX.includes('clipboard')` }, 'Save History As…': { pre: () => runConsoleLine('help'), expect: sawReq('download:') },
      Paste: { pre: () => page.evaluate(() => { window.__wcClip = 'wc-pasted' }), expect: `S.consoleDraft.includes('wc-pasted')` },
      'Select All': { expect: `!getSelection().isCollapsed` }, 'Clear Console': { expect: `document.querySelectorAll('.console .cl:not(.cinput)').length===0` },
      'Word Wrap': { expect: `!S.editorPrefs.wordWrap`, fresh: true }, 'Save History': { expect: 'S.editorPrefs.saveHistory', fresh: true }, 'Insert File Name…': { expect: `FX.includes('filechooser')` } } })
  // Checks
  await T('checks', 'Recompute button', L('.checks .chead .qbtn', { hasText: 'Recompute' }), { pre: () => showPanel('checks'), expect: sawReq('POST /api/check') })
  await T('checks', 'Verify button', L('.checks .chead .qbtn', { hasText: 'Verify' }), { pre: () => showPanel('checks'), expect: sawReq('POST /api/verify') })
  await T('checks', 'a row (click selects its bodies)', L('.checks .ctable tbody tr'), { pre: () => showPanel('checks'), expect: 'S.selected.length>0' })
}
const runConsoleLine = (line) => page.evaluate((l) => { window.cadui.setState({ consoleDraft: l }); return true }, line)

// ── the navigation cube and the 3D view ─────────────────────────────────────────────────────────────────────────────────
const bodyPoint = async (name) => {
  for (let i = 0; i < 6; i++) {      // a frame or two after a view change, the picking still sees the one before
    const at = await page.evaluate((n) => {
      const v = window.cadui.getView(), r = document.querySelector('.view3d-host').getBoundingClientRect()
      for (let gy = 0.2; gy < 0.9; gy += 0.04) for (let gx = 0.1; gx < 0.8; gx += 0.04) {
        const x = r.left + r.width * gx, y = r.top + r.height * gy
        const hit = v.picksAt({ x, y }, 1)[0]?.body
        if (n ? hit === n : hit) return [x, y]
      }
      return null
    }, name)
    if (at) return at
    await sleep(250)
  }
  return null
}
const emptyPoint = () => page.evaluate(() => {
  const v = window.cadui.getView(), r = document.querySelector('.view3d-host').getBoundingClientRect()
  for (const [gx, gy] of [[0.05, 0.9], [0.05, 0.5], [0.3, 0.92], [0.05, 0.2]]) {
    const x = r.left + r.width * gx, y = r.top + r.height * gy
    if (!v.picksAt({ x, y }, 5).length) return [x, y]
  }
  return null
})
async function testView3D() {
  const T = (path, spec, fn) => clickOne('3d view', path, { enabled: true }, fn, spec)
  const atBody = (name, opts) => async () => { const [x, y] = await bodyPoint(name); return { click: (o) => page.mouse.click(x, y, { ...opts, ...o }), dblclick: () => page.mouse.dblclick(x, y) } }
  await T('click on a part selects it', { expect: `S.selected.length===1` }, atBody('hot_plate'))
  await T('Cmd+click adds a part', { pre: () => put({ selected: ['hot_plate'] }), expect: `S.selected.length===2` },
    async () => { const [x, y] = await bodyPoint('base'); return { click: async () => { await page.keyboard.down('Meta'); await page.mouse.click(x, y); await page.keyboard.up('Meta') } } })
  await T('click on empty space clears the selection', { pre: () => put({ selected: ['hot_plate'] }), expect: 'S.selected.length===0' }, async () => { const [x, y] = await emptyPoint(); return { click: () => page.mouse.click(x, y) } })
  await T('double-click on a part edits it', { dbl: true, expect: `S.task?.kind==='params'||S.task?.kind==='transform'` }, atBody('hot_plate'))
  const menuOn = (name) => async () => {
    // an entry's set-up may have turned the view until the part is behind another: any part's menu has the same view entries
    const pt = name ? (await bodyPoint(name)) ?? (await bodyPoint(null)) : await emptyPoint()
    if (!pt) throw new Error(`no spot on ${name ?? 'empty space'} to right-click`)
    // FreeCAD opens the menu of the object preselected last (NavigationStyle::openPopupMenu), which a pointer that has just arrived has not changed yet
    await page.mouse.move(pt[0] - 2, pt[1] - 2); await page.mouse.move(pt[0], pt[1])
    await page.waitForFunction((n) => { const p = window.cadui.getState().preselected; return n ? !!p : !p }, name ?? null, { timeout: 4000 }).catch(() => {})
    await sleep(100)
    await page.mouse.click(pt[0], pt[1], { button: 'right' })
  }
  const viewSpecs = {
    'Fit All': SPEC['View > Standard Views > Fit All'], 'Fit Selection': SPEC['View > Standard Views > Fit Selection'], 'Align to Selection': SPEC['View > Standard Views > Align to Selection'],
    Isometric: viewSpec('iso'), Home: SPEC['View > Standard Views > Home'], Front: viewSpec('front'), Top: viewSpec('top'), Right: viewSpec('right'), Rear: viewSpec('rear'), Bottom: viewSpec('bottom'), Left: viewSpec('left'),
    'Rotate Left': SPEC['View > Standard Views > Rotate Left'], 'Rotates Right': SPEC['View > Standard Views > Rotates Right'],
    'Standard Views > Isometric': viewSpec('iso'), 'Standard Views > Home': SPEC['View > Standard Views > Home'], 'Standard Views > Front': viewSpec('front'), 'Standard Views > Top': viewSpec('top'),
    'Standard Views > Right': viewSpec('right'), 'Standard Views > Rear': viewSpec('rear'), 'Standard Views > Bottom': viewSpec('bottom'), 'Standard Views > Left': viewSpec('left'),
    'Standard Views > Rotate Left': SPEC['View > Standard Views > Rotate Left'], 'Standard Views > Rotates Right': SPEC['View > Standard Views > Rotates Right'],
    'Draw Style > As Is': SPEC['View > Draw Style > As Is'], 'Draw Style > Points': SPEC['View > Draw Style > Points'], 'Draw Style > Wireframe': SPEC['View > Draw Style > Wireframe'],
    'Draw Style > Hidden Line': SPEC['View > Draw Style > Hidden Line'], 'Draw Style > No Shading': SPEC['View > Draw Style > No Shading'], 'Draw Style > Shaded': SPEC['View > Draw Style > Shaded'],
    'Draw Style > Flat Lines': SPEC['View > Draw Style > Flat Lines'],
    'Document Window > Docked': SPEC['View > Document Window > Docked'], 'Document Window > Fullscreen': SPEC['View > Document Window > Fullscreen'],
    'Toggle Visibility': { expect: `S.hidden.includes('hot_plate')`, post: () => put({ hidden: [] }) }, 'Toggle Selectability': { expect: `S.unselectable.includes('hot_plate')`, post: () => put({ unselectable: [] }) },
    'Go to Selection': { pre: () => showPanel('selection'), expect: panelActive('model') }, 'Random Color': { expect: `S.view['hot_plate']?.shapeColor!=null`, post: () => put({ view: {} }) },
    'Toggle Transparency': { expect: `S.view['hot_plate']?.transparency>0`, post: () => put({ view: {} }) }, 'Send to Console': { expect: `S.consoleDraft.includes('hot_plate')` },
    Transform: { expect: task('transform') }, Placement: { expect: task('placement') }, 'Measure': { expect: task('measure') }, 'Mass Properties': { expect: task('mass') }, 'Drawing…': { expect: task('drawing') },
    'Clarify Selection': { expect: hasCtx },
  }
  await testCtx('3d view > menu on a part', menuOn('hot_plate'), { sel: 'none', specs: viewSpecs })
  await testCtx('3d view > menu on empty space', menuOn(null), { sel: 'none', specs: viewSpecs })
  // the cube's buttons
  const NAVI = [['n', 'Rotate the view up'], ['s', 'Rotate the view down'], ['w', 'Rotate the view left'], ['e', 'Rotate the view right'], ['rl', 'Roll left'], ['rr', 'Roll right'], ['home', 'Home view'], ['back', 'Look from the other side']]
  for (const [c, title] of NAVI) {
    await clickOne('navicube', title, { enabled: true }, L(`.navi.${c}`), { pre: () => page.evaluate(() => window.cadui.getView().orient([0.3, 0.2, 0.1, 0.9273])), expect: 'true' })
  }
  await testCtx('navicube > View menu', async () => { await page.locator('.navi.menu').click() }, { sel: 'none', specs: {
    'Orthographic View': { pre: () => page.evaluate(() => { window.cadui.getView().setOrtho(false); window.cadui.setState({ ortho: false }) }), expect: 'S.ortho' },
    'Perspective View': { expect: '!S.ortho', post: () => page.evaluate(() => { window.cadui.getView().setOrtho(true); window.cadui.setState({ ortho: true }) }) },
    Isometric: viewSpec('iso'), 'Fit All': SPEC['View > Standard Views > Fit All'], 'Fit Selection': SPEC['View > Standard Views > Fit Selection'], 'Align to Selection': SPEC['View > Standard Views > Align to Selection'],
    'Movable Navigation Cube': { expect: 'V.isCubeDraggable()', post: () => page.evaluate(() => window.cadui.getView().setCubeDraggable(false)) },
  } })
}

// ── the task panels ─────────────────────────────────────────────────────────────────────────────────────────────────────
const openByMenu = (...p) => () => clickMenuEntry(entryAt(p[0], ...p.slice(1)))
const typeInto = (sel, text) => async () => { await page.locator(sel).first().fill(text); await sleep(150) }
const TASKS = [
  ['File > New Document', { fill: typeInto('.taskview input', 'wc_new'), fresh: true }],
  ['File > Open…', { fresh: true }],
  ['File > Import…', {}],
  ['File > Export…', { sel: 'one' }],
  ['File > Document Information', {}],
  ['Edit > Transform', { sel: 'one' }],
  // Apply Axial moves the part along the axis by what the Axial field says, which is 0 until it is filled in
  ['Edit > Placement', { sel: 'one', fill: async () => { const f = page.locator('.taskview label.tfield', { hasText: /^Axial/ }).locator('input').first(); await f.fill('5 mm'); await f.press('Tab') } }],
  ['Edit > Align To…', { sel: 'two' }],
  ['Edit > Toggle Edit Mode', { sel: 'one' }],
  ['View > Clipping View', {}],
  ['View > Appearance', { sel: 'one' }],
  ['Tools > Measure', { sel: 'faces2', ignore: (c) => c.text === 'Save' }],      // Save needs a measurement, which Reset clears: it is tried below
  ['Tools > Mass Properties', { sel: 'one' }],
  ['Tools > Units Converter', {}],
  // the Screen ratio sets the height from the width: it only shows once the height is something else
  ['Tools > Save Image…', { fill: async () => { const f = page.locator('.taskview label.tfield', { hasText: /^Height/ }).locator('input').first(); await f.fill('111'); await f.press('Tab') } }],
  ['Tools > View Turntable', {}],
  ['Tools > Scene Inspector', { ignore: (c) => c.row || c.text === 'Refresh' }],      // its rows only fold (the twisty is tried below); a click on the row itself selects nothing
  ['Tools > Dependency Graph', {}],
  ['Tools > Edit Parameters', {}],
  // Macro > Record Macro is in testMacros: its Record button starts a recording that has to be stopped from the Macro menu
  ['Macro > Macros', {}],
  ['CAD Agent > Check', {}],
  ['CAD Agent > Verify', {}],
  ['CAD Agent > Done Gate', {}],
  ['CAD Agent > Build Part…', { sel: 'one' }],
  ['CAD Agent > Cut List…', {}],
  ['CAD Agent > Bill of Materials…', {}],
  ['CAD Agent > Shop Files…', {}],
  ['CAD Agent > Drawing…', { sel: 'one' }],
  ['CAD Agent > Tables…', {}],
  ['CAD Agent > Tool Envelope…', {}],
  ['CAD Agent > Bought Parts…', {}],
  ['CAD Agent > Library…', {}],
  ['CAD Agent > Render…', {}],
  ['CAD Agent > Rules…', {}],
  ['CAD Agent > Evals…', {}],
  ['Windows > Choose Open Window', {}],
]
async function testTasks() {
  for (const [path, opts] of TASKS) {
    if (ONLY_TASK && !ONLY_TASK.split('|').some((t) => path.includes(t))) continue
    const parts = path.split(' > ')
    await walkPanel(`task: ${parts.at(-1)}`, '.taskview', openByMenu(...parts), { ...opts, max: 120000 })
    if (path === 'Tools > Measure') {
      await clickOne('tasks', 'task: Measure > Save (two faces picked)', { enabled: true }, L('.taskview .tbuttons .qbtn', { hasText: /^Save$/ }), {
        sel: 'faces2', pre: async () => { await put(SELECTION.faces2); await openByMenu('Tools', 'Measure')(); await settle({ min: 500, quiet: 400 }) },
        expect: `document.body.innerText.includes('Saved measurements')` })
    }
    if (path === 'Tools > Scene Inspector') {
      await clickOne('tasks', 'task: Scene Inspector > a node\'s twisty (folds it)', { enabled: true }, L('.taskview .trow .twisty.open'), { pre: openByMenu('Tools', 'Scene Inspector'), expect: `!!document.querySelector('.taskview .trow .twisty:not(.open)')` })
      // the inspector reads the 3D scene when it opens and when Refresh is pressed: a measure line added meanwhile shows with Refresh
      await clickOne('tasks', 'task: Scene Inspector > Refresh', { enabled: true }, L('.taskview .qbtn', { hasText: /^Refresh$/ }), {
        pre: async () => {
          await openByMenu('Tools', 'Scene Inspector')(); await settle({ min: 300, quiet: 300 })
          await page.evaluate(() => { window.__rows0 = document.querySelectorAll('.taskview .trow').length; window.cadui.getView().showMeasure([[0, 0, 0], [50, 0, 0]]) })
        },
        expect: `document.querySelectorAll('.taskview .trow').length>window.__rows0`, post: () => page.evaluate(() => window.cadui.getView().showMeasure(null)) })
    }
  }
}
const ONLY_TASK = flag('task', '')

// ── Tools > Edit Parameters: its groups, items and their menus ────────────────────────────────────────────────────────────
/** The editor shows the page's saved settings as groups and items. An item and a group made here (a "custom" one) can be renamed and removed;
 *  the page's own settings cannot. `cadui.custom` is seeded with one of each, so that both kinds of entry are enabled for a click. */
async function testParameterEditor() {
  const seed = () => page.evaluate(() => localStorage.setItem('cadui.custom', JSON.stringify({ 'General/wcgroup/wcitem': { t: 'text', v: 'hello' } })))
  const open = async () => { await resetUI('none'); await seed(); await clickMenuEntry(entryAt('Tools', 'Edit Parameters')); await page.locator('.taskview .tree .trow').first().waitFor() }
  const rows = () => page.locator('.taskview .tree .trow')
  const customRow = () => rows().filter({ hasText: 'wcgroup' }).first()
  const leafRow = () => page.locator('.taskview .pgrid .prow', { hasText: 'wcitem' }).first()
  const T = (path, locate, spec) => clickOne('parameter editor', path, { enabled: true }, locate, { pre: open, ...spec })
  const gone = (what) => `![...document.querySelectorAll('.taskview .tree .trow, .taskview .pgrid .prow')].some((r)=>r.textContent.includes('${what}'))`
  const has = (what) => `[...document.querySelectorAll('.taskview .tree .trow, .taskview .pgrid .prow')].some((r)=>r.textContent.includes('${what}'))`
  const asks = { expect: `FX.includes('dialog:prompt')` }
  await T('group (click selects it)', () => rows().nth(1), { expect: `document.querySelectorAll('.taskview .tree .trow')[1].classList.contains('sel')` })
  await T('item value (click edits it)', L('.taskview .pgrid .pv.edit'), { expect: `!!document.querySelector('.taskview .pgrid input, .taskview .pgrid select')` })
  // the group's menu, on the group made here (the page's own groups are greyed for Remove and Rename)
  const onGroup = async () => { await customRow().click({ button: 'right' }) }
  await testCtx('parameter editor > group menu', onGroup, { prep: open, specs: {
    'Add Sub-Group': asks,
    'Remove Group': { pre: async () => { dialogMode = 'accept' }, expect: `FX.includes('dialog:confirm')&&${gone('wcgroup')}` },
    'Rename Group': { pre: async () => { promptAnswers.push('wcgroup2') }, expect: has('wcgroup2') } } })
  const onLeaf = async () => { await customRow().click(); await leafRow().click({ button: 'right' }) }
  await testCtx('parameter editor > item menu', onLeaf, { prep: open, specs: {
    'Change Value': { expect: `!!document.querySelector('.taskview .pgrid input')` },
    'Remove Key': { expect: gone('wcitem') },
    'Rename Key': { pre: async () => { promptAnswers.push('wcitem2') }, expect: has('wcitem2') },
    'New > New String Item': asks, 'New > New Float Item': asks, 'New > New Integer Item': asks, 'New > New Unsigned Item': asks, 'New > New Boolean Item': asks } })
  // the item list's own menu (New)
  const onList = async () => { await customRow().click(); await page.locator('.taskview .pgrid .phead').click({ button: 'right' }) }
  await testCtx('parameter editor > list menu', onList, { prep: open, specs: {
    'New String Item': asks, 'New Float Item': asks, 'New Integer Item': asks, 'New Unsigned Item': asks, 'New Boolean Item': asks } })
  // a page's own item: Remove and Rename say why they are greyed out
  const onOwn = async () => { await rows().first().click(); await page.locator('.taskview .pgrid .prow').first().click({ button: 'right' }) }
  await testCtx('parameter editor > own item menu', onOwn, { prep: open, specs: { 'Change Value': { expect: `!!document.querySelector('.taskview .pgrid input, .taskview .pgrid select')` } } })
  await page.evaluate(() => localStorage.removeItem('cadui.custom'))
  await openFresh()
}

// ── Preferences ─────────────────────────────────────────────────────────────────────────────────────────────────────────
async function testPrefs() {
  const open = async () => { await clickMenuEntry(entryAt('Edit', 'Preferences')); await page.locator('.pref-dlg').waitFor() }
  await resetUI(); await open()
  const pages = await page.locator('.pref-dlg .pref-item').allTextContents()
  await page.locator('.pref-dlg .pref-buttons .qbtn', { hasText: /^Cancel$/ }).click()
  console.log(`preferences: ${pages.length} pages: ${pages.join(', ')}`)
  // two pages are called General (the Display group's and the Python one's): by position, and the second is told apart in the report
  for (const [i, pg] of pages.entries()) {
    const name = pages.indexOf(pg) === i ? pg : `${pg} (${pages.slice(0, i + 1).filter((x) => x === pg).length})`
    await walkPanel(`Preferences > ${name}`, '.pref-page', async () => { await open(); await page.locator('.pref-dlg .pref-item').nth(i).click() }, { max: 60000, group: 'prefs' })
  }
  // the dialog's own buttons, search and Reset (the walk leaves the dialog open on the last page)
  const opened = async () => { await open() }
  await resetUI()
  await testPrefButtons(open)
  await clickOne('Preferences', 'search results (click a hit)', { enabled: true }, L('.pref-dlg .pref-hit'), { pre: async () => { await open(); await page.locator('.pref-dlg input[type=search]').first().fill('Navigation'); await sleep(300) }, expect: `document.querySelector('.pref-header').textContent!=='General'`, post: () => resetUI() })
  await testCtx('Preferences > Reset menu', async () => { await page.locator('.pref-dlg .pref-side > .qbtn').click() }, { prep: opened, specs: {
    "Reset Page 'General'": { expect: 'true' }, "Reset Group 'General'": { expect: 'true' }, 'Reset All': { expect: `!!document.querySelector('.msgbox')` } } })
  await resetUI()
}

/** The dialog's own buttons, on a setting that shows (Report View > timecode): Apply has no effect of its own, it is the setting Cancel comes
 *  back to, so it is judged by what Cancel does after it. */
async function testPrefButtons(open) {
  const box = () => page.locator('.pref-page label', { hasText: 'Include a timecode' }).locator('input')
  const btn = (t) => page.locator('.pref-dlg .pref-buttons .qbtn', { hasText: new RegExp(`^${t}$`) })
  const go = async () => { await open(); await page.locator('.pref-dlg .pref-item', { hasText: /^Report View$/ }).click() }
  await go()
  await box().click()                                   // timecode off
  await btn('Apply').click()                            // keep it
  await box().click()                                   // on again
  const o = await observe(() => btn('Cancel').click(), { max: 30000, restore: false })
  const kept = await check('S.reportTimecode===false')
  note('prefs', 'dialog > Apply', { enabled: true }, kept ? 'WORKS' : 'NO-OP', kept ? 'Cancel came back to the setting Apply kept' : 'Cancel went back past what Apply kept')
  await judge('prefs', 'dialog > Cancel', { enabled: true }, o, '!S.prefsOpen')
  await go()
  await box().click()                                   // timecode on again
  await judge('prefs', 'dialog > OK', { enabled: true }, await observe(() => btn('OK').click(), { max: 30000, restore: false }), '!S.prefsOpen&&S.reportTimecode')
}

// ── Tools > Customize ───────────────────────────────────────────────────────────────────────────────────────────────────
async function testCustomize() {
  const open = async () => { await clickMenuEntry(entryAt('Tools', 'Customize')); await page.locator('.cu-dlg').waitFor() }
  for (const tab of ['Toolbars', 'Macros']) {
    await walkPanel(`Customize > ${tab}`, '.cu-dlg', async () => { await open(); await page.locator('.cu-dlg .cu-tab', { hasText: new RegExp(`^${tab}$`) }).click() }, { max: 60000, group: 'customize' })
  }
}

// ── the Start page, the notification area, the message boxes ──────────────────────────────────────────────────────────
async function testStart() {
  const open = async () => { await showPanel('start') }
  // first start: the unit system and Done
  await walkPanel('Start page (first start)', '.start-first', open, { fresh: true, group: 'start' })
  await put({}); await page.evaluate(() => localStorage.setItem('cadui.start.firstStart', 'false'))
  await openFresh()
  await walkPanel('Start page', '.start', open, { fresh: true, group: 'start', before: () => put({ task: null }) })
}
async function testNotifications() {
  const warn = async () => { await page.evaluate(() => { window.__wcBlockOpen = true }); await clickMenuEntry(entryAt('File', 'Print')); await settle({ min: 600, quiet: 600 }) }
  // the list opens from the status bar's button, and a notification is made (a pop-up the browser blocked) when there is none
  const list = async () => {
    if (!(await getS('S.notifications.length'))) await warn()
    if (!(await page.locator('.notify-list').count())) await page.locator('.statusbar .notify-btn').click()
  }
  await clickOne('notifications', 'list rows (click selects)', { enabled: true }, L('.notify-list .notify-row'), { pre: list, expect: `!!document.querySelector('.notify-row.sel')` })
  await testCtx('notifications > list menu', async () => { await list(); await page.locator('.notify-list').click({ button: 'right' }) },
    { labels: ['Delete', 'Delete User Notifications', 'Delete All'], specs: { Delete: { pre: async () => { await list(); await page.locator('.notify-row').first().click() }, expect: `document.querySelectorAll('.notify-row').length===0` },
      'Delete All': { expect: `document.querySelectorAll('.notify-row').length===0` } } })
  await testCtx('notifications > button menu', async () => { if (!(await getS('S.notifications.length'))) await warn(); await page.locator('.statusbar .notify-btn').click({ button: 'right' }) },
    { labels: ['Delete User Notifications', 'Delete All'], specs: { 'Delete All': { expect: 'S.notifications.length===0' } } })
}
async function testMessageBox() {
  // File > Export… with nothing selected: a warning with OK
  await clickOne('message box', 'No Selection warning > OK', { enabled: true }, L('.msgbox .qbtn', { hasText: /^OK$/ }), { pre: () => clickMenuEntry(entryAt('File', 'Export…')), expect: `!document.querySelector('.msgbox')` })
  // CAD Agent > Approve Renders…: its question is a person's. No is clicked; Yes never is.
  await clickOne('message box', 'Approve Renders question > No', { enabled: true }, L('.msgbox .qbtn', { hasText: /^No$/ }), { pre: () => clickMenuEntry(entryAt('CAD Agent', 'Approve Renders…')), expect: `!document.querySelector('.msgbox')` })
  note('message box', 'Approve Renders question > Yes', { enabled: true }, 'HUMAN', "not clicked: approving renders is the owner's call")
  note('console', 'cad approve (Return on the console line)', { enabled: true }, 'HUMAN', "not run: approving is the owner's call (the request is refused at the network layer too)")
  note('console', 'cad lib fetch ENTRY (Return on the console line)', { enabled: true }, 'HUMAN', 'not run: it downloads a file')
  note('console', 'cad eval run TASK (Return on the console line)', { enabled: true }, 'HUMAN', "not run: it starts a real agent and spends the plan's usage")
}

// ── Tools > Customize: the Toolbars page and the Macros page, with something to work on ──────────────────────────────────
async function testCustomizeFlow() {
  const open = async (tab) => { await resetUI('none'); await clickMenuEntry(entryAt('Tools', 'Customize')); await page.locator('.cu-dlg').waitFor(); if (tab) await page.locator('.cu-dlg .cu-tab', { hasText: new RegExp(`^${tab}$`) }).click() }
  const dlg = page.locator('.cu-dlg')
  const btn = (t) => dlg.locator('.qbtn', { hasText: new RegExp(`^${esc(t)}$`) }).first()
  // (every step saves a setting, and a step that does would have its setting put back and the page reloaded under the dialog: the settings are cleared at the end)
  const F = async (path, act, expect) => judge('customize', path, { enabled: true }, await observe(act, { max: 30000, restore: false }), expect)
  const row = (side, text) => dlg.locator(`.cu-col:${side === 'left' ? 'first-child' : 'last-child'} .cu-row`, { hasText: text }).first()
  await open('Toolbars')
  await F('Toolbars page > New (asks for a name)', () => btn('New').click(), `!!document.querySelector('.cu-input')`)
  await F('name box > Cancel', () => page.locator('.cu-input .qbtn', { hasText: /^Cancel$/ }).click(), `!document.querySelector('.cu-input')&&S.customToolbars.length===0`)
  await btn('New').click()
  await F('name box > OK (makes the toolbar)', () => page.locator('.cu-input .qbtn', { hasText: /^OK$/ }).click(), `S.customToolbars.length===1`)
  await row('left', 'Fit All').click()
  await F('Toolbars page > → (puts the command on the toolbar)', () => btn('→').click(), `S.customToolbars[0].cmds.length===1`)
  await row('left', 'Home').click()
  await F('Toolbars page > → (a second command)', () => btn('→').click(), `S.customToolbars[0].cmds.length===2`)
  await F('Toolbars page > ↑ (moves the command up)', () => btn('↑').click(), `S.customToolbars[0].cmds[0]==='Std_ViewHome'`)
  await F('Toolbars page > ↓ (moves the command down)', () => btn('↓').click(), `S.customToolbars[0].cmds[1]==='Std_ViewHome'`)
  await F('Toolbars page > ← (takes the command off)', () => btn('←').click(), `S.customToolbars[0].cmds.length===1`)
  await F('Toolbars page > the toolbar\'s check box (hides it)', () => dlg.locator('.cu-col:last-child .cu-row input[type=checkbox]').first().click(), `S.customToolbars[0].active===false`)
  await row('right', 'Custom1').click()
  await F('Toolbars page > Rename', async () => { await btn('Rename').click(); await page.locator('.cu-input input').fill('Mine'); await page.locator('.cu-input .qbtn', { hasText: /^OK$/ }).click() }, `S.customToolbars[0].name==='Mine'`)
  await F('Toolbars page > Delete', () => btn('Delete').click(), `S.customToolbars.length===0`)
  await F('Toolbars page > the workbench list (Global)', () => dlg.locator('.cu-col:last-child select').selectOption('Global'), 'true')
  // the Macros page: a macro file to bind (made by the Macro tests, or here)
  await api('/api/macro', { name: 'wc_cmd', text: '# cad macro: wc_cmd\n' })
  await dlg.locator('.cu-tab', { hasText: /^Macros$/ }).click()
  await F('Macros page > Add without a macro (says so)', () => btn('Add').click(), `!!document.querySelector('.msgbox')`)
  await answerNo()
  await dlg.locator('.cu-form select').first().selectOption('wc_cmd')
  await dlg.locator('.cu-form input').first().fill('Wirecheck macro')
  await F('Macros page > Add', () => btn('Add').click(), `S.macroCommands.length===1`)
  await F('Macros page > a macro command (click selects it)', () => dlg.locator('.cu-macros .cu-list .cu-row').first().click(), `!!document.querySelector('.cu-macros .cu-row.sel')`)
  await F('Macros page > Replace', async () => { await dlg.locator('.cu-form input').first().fill('Wirecheck macro 2'); await btn('Replace').click() }, `S.macroCommands[0].menuText==='Wirecheck macro 2'`)
  await F('Macros page > Remove', () => btn('Remove').click(), `S.macroCommands.length===0`)
  await F('Customize > Help (What\'s This?)', () => btn('Help').click(), `document.body.classList.contains('whats-this-cursor')`)
  await btn('Close').click()          // in What's This? mode a click explains the button and leaves the mode (Escape would close the dialog)
  await F('Customize > Close', () => btn('Close').click(), '!S.customizeOpen')
  await page.evaluate(() => { for (const k of ['customToolbars', 'macroCommands', 'shortcuts']) localStorage.removeItem('cadui.' + k) })
  await openFresh()
}

// ── Preferences > Keyboard: assign, clear and reset a shortcut ─────────────────────────────────────────────────────────
async function testKeyboardPage() {
  const open = async () => { await resetUI('none'); await clickMenuEntry(entryAt('Edit', 'Preferences')); await page.locator('.pref-dlg').waitFor(); await page.locator('.pref-dlg .pref-item', { hasText: /^Keyboard$/ }).click() }
  const page_ = page.locator('.pref-page')
  const btn = (t) => page_.locator('.qbtn', { hasText: new RegExp(`^${esc(t)}$`) }).first()
  const F = async (path, act, expect) => judge('Preferences', `Keyboard > ${path}`, { enabled: true }, await observe(act, { max: 30000, restore: false }), expect)
  await open()
  await page_.locator('input[type=search]').fill('Fit All')
  await F('a command in the list (click selects it)', () => page_.locator('.kb-list .kb-row:not(.kb-head)').first().click(), `!!document.querySelector('.kb-row.sel')`)
  await page_.locator('.accel-edit').nth(1).focus()
  await page.keyboard.press('Control+Alt+k')
  await F('Assign (the new shortcut)', () => btn('Assign').click(), `Object.keys(S.shortcuts).length===1`)
  await F('Reset (back to the default)', () => btn('Reset').click(), `Object.keys(S.shortcuts).length===0`)
  await F('Clear (no shortcut at all)', () => btn('Clear').click(), `Object.values(S.shortcuts).includes('')`)
  await F('Reset All', () => btn('Reset All').click(), `Object.keys(S.shortcuts).length===0`)
  await page.locator('.pref-dlg .pref-buttons .qbtn', { hasText: /^Cancel$/ }).click()
  await page.evaluate(() => localStorage.removeItem('cadui.shortcuts'))
  await openFresh()
}

// ── flows: the controls that only do something after something else was done ──────────────────────────────────────────────
const okButton = () => page.locator('.taskview .tbuttons .qbtn', { hasText: /^OK$/ }).first()
const taskButton = (name) => page.locator('.taskview .qbtn', { hasText: new RegExp(`^${esc(name)}$`) }).first()
const bodyOf = (name) => `S.scene.bodies.find((b)=>b.name==='${name}')`
/** Edits through the page, then Undo and Redo: the journal the page and an agent share. */
async function testEdits() {
  const F = async (path, meta, act, expect, opts = {}) => {
    const o = await observe(act, { max: 120000, ...opts })
    return judge('edits', path, meta, o, expect)
  }
  await resetUI('one')
  await clickMenuEntry(entryAt('Edit', 'Placement'))
  const x = page.locator('.taskview fieldset', { hasText: 'Translation' }).locator('.tfield', { hasText: /^X/ }).locator('input').first()
  await x.fill('0.5 mm'); await x.press('Tab'); await sleep(300)
  await F('Placement task > OK (X = 0.5 mm)', { enabled: true }, () => okButton().click(), `${bodyOf('hot_plate')}.placement?.move?.[0]===0.5`)
  await F('Edit > Undo (takes the move back)', { cmd: 'Std_Undo', enabled: true }, () => clickMenuEntry(entryAt('Edit', 'Undo')), `!${bodyOf('hot_plate')}.placement&&S.redo.length>0`)
  await F('Edit > Redo (puts the move back)', { cmd: 'Std_Redo', enabled: true }, () => clickMenuEntry(entryAt('Edit', 'Redo')), `${bodyOf('hot_plate')}.placement?.move?.[0]===0.5`)
  await F('toolbar > Undo to… (a step from the list)', { enabled: true }, async () => {
    await (await toolbarButton({ title: 'Undo to…', text: '' }, 0)).click()
    await page.locator('.ctx .mb-item').first().click()
  }, `!${bodyOf('hot_plate')}.placement`)
  // a parameter, through the property view
  await resetUI('one')
  await page.locator('.ptabs button', { hasText: /^Data$/ }).click()
  const cell = page.locator('.pgrid .prow', { hasText: /^thickness/ }).locator('.pv.edit')
  await F('property view > a parameter (click, type, Enter)', { enabled: true }, async () => {
    await cell.click(); await page.locator('.pgrid .prow', { hasText: /^thickness/ }).locator('input').first().fill('11'); await page.keyboard.press('Enter')
  }, `${bodyOf('hot_plate')}.params.thickness.value===11`)
  await F('Edit > Undo (takes the parameter back)', { cmd: 'Std_Undo', enabled: true }, () => clickMenuEntry(entryAt('Edit', 'Undo')), `${bodyOf('hot_plate')}.params.thickness.value===10`)
  await resetUI('one')
  // the Parameters task (double-click a part): OK writes with cad set
  await clickMenuEntry(entryAt('Edit', 'Toggle Edit Mode'))
  const field = page.locator('.taskview .tfield', { hasText: /^thickness/ }).locator('input').first()
  await field.fill('12')
  await F('Parameters task > OK (thickness = 12)', { enabled: true }, () => okButton().click(), `${bodyOf('hot_plate')}.params.thickness.value===12`)
  await F('Edit > Undo (takes the task\'s change back)', { cmd: 'Std_Undo', enabled: true }, () => clickMenuEntry(entryAt('Edit', 'Undo')), `${bodyOf('hot_plate')}.params.thickness.value===10`)
}

/** Macro > Record Macro, the actions it records, Stop, then the Macros task on the file it wrote. */
async function testMacros() {
  // (running a macro puts it in Recent Macros, a saved setting: it stays for the steps after it, and is cleared at the end)
  const F = async (path, meta, act, expect, opts = {}) => judge('macros', path, meta, await observe(act, { max: 90000, restore: false, ...opts }), expect)
  const row = (n) => page.locator('.taskview .trow').filter({ has: page.locator('span', { hasText: new RegExp(`^${esc(n)}$`) }) }).first()
  const names = () => page.locator('.taskview .trow > span:first-child').allTextContents()
  await resetUI('none')
  await clickMenuEntry(entryAt('Macro', 'Record Macro'))
  await page.locator('.taskview input').first().fill('wc_macro')
  await F('Record Macro task > Record', { enabled: true }, () => taskButton('Record').click(), `S.recordingMacro==='wc_macro'`)
  await F('(an action while recording) View > Standard Views > Front', { enabled: true }, () => clickMenuEntry(entryAt('View', 'Standard Views', 'Front')), `W.isView('front')`)
  await F('Macro > Stop Macro Recording', { enabled: true }, () => clickMenuEntry(entryAt('Macro', 'Stop Macro Recording')), `!S.recordingMacro`)
  // the Macros task: select the new one, then each button
  const open = async (pick = 'wc_macro') => { await resetUI('none'); await clickMenuEntry(entryAt('Macro', 'Macros')); await row(pick).click() }
  await open()
  await F('Macros task > Execute', { enabled: true }, () => taskButton('Execute').click(), `!S.task`)
  await F('Macro > Recent Macros > wc_macro (runs it again)', { enabled: true }, () => clickMenuEntry(entryAt('Macro', 'Recent Macros', 'wc_macro')), sawReq('POST /api/macro/run'))
  await open()
  await F('Macros task > Edit', { enabled: true }, () => taskButton('Edit').click(), task('macroEdit'))
  await F('Macro edit task > Save', { enabled: true }, () => taskButton('Save').click(), task('macros'))
  await open()
  await F('Macros task > Duplicate', { enabled: true }, async () => { await taskButton('Duplicate').click(); await taskButton('Duplicate').click() },
    `document.body.innerText.includes('wc_macro_copy')`)
  await row('wc_macro_copy').click()
  await F('Macros task > Rename', { enabled: true }, async () => { await taskButton('Rename').click(); await page.locator('.taskview .hbox input').fill('wc_renamed'); await taskButton('Rename').click() },
    `document.body.innerText.includes('wc_renamed')&&!document.body.innerText.includes('wc_macro_copy')`)
  await F('Macros task > Create', { enabled: true }, async () => { await taskButton('Create').click(); await page.locator('.taskview .hbox input').fill('wc_created'); await page.locator('.taskview .hbox', { has: page.locator('input') }).locator('.qbtn.default').click() }, task('macroEdit'))
  await page.locator('.taskview .qbtn', { hasText: /^Close$/ }).first().click()   // back to the list
  // Delete asks first, and these are scratch macros, so Yes is safe here
  await row('wc_renamed').click()
  const del = await observe(async () => { await taskButton('Delete').click(); await page.locator('.msgbox .qbtn', { hasText: /^Yes$/ }).click() }, { max: 60000 })
  await judge('macros', 'Macros task > Delete (answered Yes: a scratch macro)', { enabled: true }, del, `!document.body.innerText.includes('wc_renamed')`)
  console.log(`macros left in the scratch folder: ${(await names()).join(', ')}`)
  await resetUI('none')
  await page.evaluate(() => localStorage.removeItem('cadui.recentMacros'))
  await openFresh()
}

/** File > New Document: a name, Create; it opens the new project. */
async function testNewDocument() {
  await resetUI('none')
  await clickMenuEntry(entryAt('File', 'New Document'))
  await page.locator('.taskview input').first().fill('wc_new')
  await page.locator('.taskview textarea').fill('a brief written by wirecheck')
  // the project opens when `cad init` has answered, which is the first command through the warm worker: the page shows nothing busy meanwhile
  const o = await observe(async () => {
    await taskButton('Create').click()
    await page.waitForFunction(() => window.cadui.getState().slug === 'wc_new', null, { timeout: 120000 })
  }, { max: 120000 })
  await judge('flows', 'New Document task > Create', { enabled: true }, o, `S.slug==='wc_new'`)
  await openFresh()
}

/** CAD Agent > Drawing…: Draw opens the sheet in a tab of its own; the tab's buttons; the Windows menu lists it; File > Close closes it. */
async function testDrawing() {
  const F = async (path, act, expect, max = 90000) => judge('drawing', path, { enabled: true }, await observe(act, { max }), expect)
  const drawing = `window.cadui.getDock().panels.find((p)=>p.id.startsWith('drawing:'))`
  await resetUI('one')
  await clickMenuEntry(entryAt('CAD Agent', 'Drawing…'))
  await F('Drawing task > Draw (opens the sheet in a tab)', () => taskButton('Draw').click(), `!!${drawing}`, 240000)
  await walkPanel('drawing tab', '.drawing', () => page.evaluate(() => window.cadui.getDock().panels.find((p) => p.id.startsWith('drawing:'))?.api.setActive()), { max: 60000, group: 'drawing' })
  // Windows lists the 3D view and the sheet: each entry brings its window forward
  const labels = (await openMenu('Windows').then(() => readMenuAt(0))).filter((x) => !x.sep && !x.disabled && /^\d /.test(x.label)).map((x) => x.label)
  await closeMenus()
  console.log(`drawing: Windows lists ${labels.join(' | ')}`)
  for (const label of labels) {
    const want = /Drawing$/.test(label) ? `${drawing}.api.isActive` : /: 1$/.test(label) ? `window.cadui.getDock().getPanel('view3d').api.isActive` : `window.cadui.getDock().getPanel('start').api.isActive`
    const other = /: 1$/.test(label) ? 'start' : 'view3d'      // bring another window forward first, so that the entry has something to do
    await showPanel(other); await settle({ min: 300, quiet: 300 })
    await F(`Windows > ${label}`, () => clickMenuEntry(entryAt('Windows', label)), want, 30000)
  }
  // File > Close closes the window in front: the sheet, not the 3D view
  await page.evaluate(() => window.cadui.getDock().panels.find((p) => p.id.startsWith('drawing:'))?.api.setActive())
  await F('File > Close (with the sheet in front)', () => clickMenuEntry(entryAt('File', 'Close')), `!${drawing}&&!!window.cadui.getDock().getPanel('view3d')`, 30000)
  await resetUI('none')
}

/** CAD Agent > Evals…: pick a task (its brief shows), then Score the open project against it (a copy is judged). */
async function testEvals() {
  const F = async (path, act, expect, max = 180000) => judge('evals', path, { enabled: true }, await observe(act, { max }), expect)
  await resetUI('none')
  await clickMenuEntry(entryAt('CAD Agent', 'Evals…'))
  await page.locator('.taskview .ctable tbody tr').first().waitFor({ timeout: 60000 })
  await F('Evals task > a task (click shows its brief)', () => page.locator('.taskview .ctable tbody tr').first().click(), `document.body.innerText.includes('Brief:')`, 60000)
  await F('Evals task > Score (the open project against it)', () => page.locator('.taskview .qbtn', { hasText: /^Score / }).click(), sawReq('POST /api/cad eval score'))
  await resetUI('none')
}

/** BOM and Shop files: the rows, the options, the downloads and the verdict buttons. */
async function testShop() {
  const F = async (path, act, expect, max = 240000) => judge('shop', path, { enabled: true }, await observe(act, { max }), expect)
  await resetUI('none')
  await clickMenuEntry(entryAt('CAD Agent', 'Bill of Materials…'))
  await page.locator('.taskview .ctable tbody tr').first().waitFor({ timeout: 240000 })
  await F('Bill of Materials > a line (click selects its bodies)', () => page.locator('.taskview .ctable tbody tr').nth(1).click(), 'S.selected.length>0', 30000)
}

/** The Expression Editor ("=" in a field): its OK and Reset buttons and its right-click menu, over the Placement task's X field. */
async function testExpression() {
  const F = async (path, act, expect) => judge('expression editor', path, { enabled: true }, await observe(act, { max: 30000 }), expect)
  const field = () => page.locator('.taskview fieldset', { hasText: 'Translation' }).locator('.tfield', { hasText: /^X/ }).locator('input').first()
  const opened = async () => { await field().click(); await page.keyboard.press('='); await page.locator('.expr-dlg').waitFor({ timeout: 5000 }) }
  await resetUI('one'); await clickMenuEntry(entryAt('Edit', 'Placement'))
  await F('"=" in the X field (opens it)', async () => { await field().click(); await page.keyboard.press('=') }, `!!document.querySelector('.expr-dlg')`)
  await page.locator('.expr-text').fill('2+3')
  await F('OK (takes the result)', () => page.locator('.expr-buttons .qbtn', { hasText: /^OK$/ }).click(), `!document.querySelector('.expr-dlg')`)
  await opened()
  await F('Reset (leaves the value as it was)', () => page.locator('.expr-buttons .qbtn', { hasText: /^Reset$/ }).click(), `!document.querySelector('.expr-dlg')`)
  await opened()
  await testCtx('expression editor > menu', async () => { await page.locator('.expr-text').click({ button: 'right' }) }, { specs: { 'Select All': { pre: () => page.locator('.expr-text').press('End'), expect: `(()=>{const t=document.querySelector('.expr-text');return t.selectionStart===0&&t.selectionEnd===t.value.length&&t.value.length>0})()` }, 'Exact Match': { expect: 'true' } },
    prep: async () => { await resetUI('one'); await clickMenuEntry(entryAt('Edit', 'Placement')); await opened() } })
  await resetUI('none')
}

/** File > Open…: pick another project in the list and open it (a row, double-click, then the Open button). */
async function testOpenDocument() {
  const F = async (path, act, expect) => judge('flows', path, { enabled: true }, await observe(act, { max: 90000 }), expect)
  await resetUI('none')
  await clickMenuEntry(entryAt('File', 'Open…'))
  await F('Open Document task > a project (click selects it)', () => page.locator('.taskview .trow', { hasText: 'arduino_car' }).click(), `!!document.querySelector('.taskview .trow.sel')`)
  await F('Open Document task > Open (the picked project)', () => taskButton('Open').click(), `S.slug==='arduino_car'`)
  await openFresh()
  await resetUI('none')
  await clickMenuEntry(entryAt('File', 'Open…'))
  await F('Open Document task > a project (double-click opens it)', () => page.locator('.taskview .trow', { hasText: 'arduino_car' }).dblclick(), `S.slug==='arduino_car'`)
  await openFresh()
}

/** The Library task on a real entry: pick, Use in the project, Undo, Check, Fetch… (which only fills the console line). */
async function testLibrary() {
  const F = async (path, act, expect, opts = {}) => judge('library', path, { enabled: true }, await observe(act, { max: 120000, ...opts }), expect)
  await resetUI('none')
  await clickMenuEntry(entryAt('CAD Agent', 'Library…'))
  await page.locator('.taskview .ctable tbody tr').first().waitFor({ timeout: 90000 })
  const rows = await page.locator('.taskview .ctable tbody tr').allInnerTexts()
  console.log(`library: ${rows.length} entries`)
  await F('Library task > Search (filters the table)', () => page.locator('.taskview input').first().fill('zzzz-nothing'), `document.body.innerText.includes('Nothing matches')`)
  await page.locator('.taskview input').first().fill('')
  await F('Library task > Browse > an entry (shows its facts)', () => page.locator('.taskview .ctable tbody tr').first().click(), `document.querySelector('.taskview .kv')!==null`)
  const usable = page.locator('.taskview .ctable tbody tr:not(.dim)').first()
  if (await usable.count()) {
    await usable.click(); await settle({ min: 800, quiet: 600, max: 60000 })
    await F('Library task > Use in the project', () => page.locator('.taskview .qbtn', { hasText: /^Use in / }).click(), sawReq('POST /api/cad lib use'))
    await F('Edit > Undo (takes the library part out again)', () => clickMenuEntry(entryAt('Edit', 'Undo')), sawReq('POST /api/undo'))
  } else console.log('library: no entry is ready to use here')
  const fetchable = page.locator('.taskview .ctable tbody tr.dim').first()
  if (await fetchable.count()) {
    await fetchable.click(); await settle({ min: 800, quiet: 600, max: 60000 })
    const f = page.locator('.taskview .qbtn', { hasText: /^Fetch…$/ })
    if (await f.count()) await F('Library task > Fetch… (puts `cad lib fetch` on the console line; the Return is a person\'s)', () => f.click(), `S.consoleDraft.startsWith('cad lib fetch')&&!FX.some((x)=>/lib fetch/.test(x))`)
  }
  await F('Library task > Check > Check the store', async () => { await taskButton('Check').click(); await page.locator('.taskview .qbtn', { hasText: /^Check the store$/ }).click() }, sawReq('POST /api/cad lib check'))
  await F("Library task > Check > Check the project's bought parts", () => page.locator('.taskview .qbtn', { hasText: /^Check .*bought parts$/ }).click(), sawReq('POST /api/cad lib check'))
  // Add…: a STEP picked on this computer (the page sends its bytes to /api/upload)
  const step = join(OUT, 'wc_box.step')
  spawnSync(env.CAD_PYTHON ?? process.env.CAD_PYTHON ?? join(REPO, '.venv', 'bin', 'python'), ['-c', 'import sys; from build123d import Box, export_step; export_step(Box(10, 10, 10), sys.argv[1])', step], { env: { ...process.env, PYTHONPATH: REPO }, timeout: 120000 })
  if (existsSync(step)) {
    await taskButtonByText('Add…').click()
    await page.locator('.taskview input[type=file]').setInputFiles(step)
    await page.locator('.taskview input[placeholder*="catalog entry"]').fill('wc-box'); await page.locator('.taskview input[placeholder*="page the file came from"]').fill('wirecheck')
    await F('Library task > Add… > Add (a picked STEP)', () => taskButton('Add').click(), sawReq('POST /api/cad lib add'))
  }
  await resetUI('none')
}
const taskButtonByText = (t) => page.locator('.taskview .qbtn', { hasText: new RegExp(`^${esc(t)}$`) }).first()

// ── run ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
const section = async (name, fn) => {
  if (!want(name)) return
  const t0 = Date.now(), n0 = results.length
  console.log(`\n== ${name}`)
  try { await fn() } catch (e) {
    // where the page was when the section gave up: a click that took the page away shows in its address and its first lines of text
    let where = await page.evaluate(() => `${location.href.slice(0, 80)} | ${document.body.innerText.slice(0, 120).replace(/\s+/g, ' ')}`).catch(() => 'the page is gone')
    if (DEBUG_DOM) {      // and a picture of it
      const shot = join(OUT, `stopped-${name}.png`)
      if (await page.screenshot({ path: shot }).then(() => true).catch(() => false)) where += ` | picture: ${shot}`
    }
    note(name, '(section stopped)', {}, 'ERROR', `${String(e.stack ?? e).split('\n').slice(0, DEBUG_DOM ? 14 : 3).join(' | ').slice(0, DEBUG_DOM ? 1200 : 300)} [page: ${where}]`)
  }
  console.log(`== ${name}: ${results.length - n0} controls in ${((Date.now() - t0) / 1000).toFixed(0)} s`)
  await openFresh()
}
async function main() {
  await openFresh()
  await section('menus', async () => {
    const inv = await menuInventory()
    console.log(`menus: ${inv.length} entries (${inv.filter((i) => i.sub).length} sub-menus, ${inv.filter((i) => !i.sub && !i.enabledIn.length).length} greyed out in every state)`)
    await testMenus(inv)
  })
  await section('toolbars', testToolbars)
  await section('docks', testDocks)
  await section('status', testStatusBar)
  await section('tree', testTree)
  await section('properties', testProperties)
  await section('panels', testPanels)
  await section('view3d', testView3D)
  await section('customize', testCustomize)
  await section('customizeflow', testCustomizeFlow)
  await section('start', testStart)
  await section('notifications', testNotifications)
  await section('msgbox', testMessageBox)
  await section('expression', testExpression)
  await section('prefs', testPrefs)
  await section('keyboard', testKeyboardPage)
  // the ones that wait for a check or a rebuild come last
  await section('tasks', testTasks)
  await section('params', testParameterEditor)
  await section('macros', testMacros)
  await section('library', testLibrary)
  await section('drawing', testDrawing)
  await section('evals', testEvals)
  await section('shop', testShop)
  await section('opendoc', testOpenDocument)
  await section('newdoc', testNewDocument)
  await section('edits', testEdits)
}
let failed = null
function summary() {
  const tally = {}, by = {}
  for (const r of results) { tally[r.klass] = (tally[r.klass] ?? 0) + 1; (by[r.surface] ??= {})[r.klass] = (by[r.surface][r.klass] ?? 0) + 1 }
  console.log('\n== summary')
  for (const [surface, t] of Object.entries(by)) console.log(`  ${surface.padEnd(14)} ${Object.entries(t).map(([k, v]) => `${k} ${v}`).join(', ')}`)
  console.log(`${results.length} controls: ${['WORKS', 'N/A', 'NO-OP', 'ERROR', 'WRONG', 'HUMAN'].map((k) => `${k} ${tally[k] ?? 0}`).join(', ')}`)
  const bad = results.filter((r) => ['NO-OP', 'ERROR', 'WRONG'].includes(r.klass))
  for (const r of bad) console.log(`  ${r.klass.padEnd(6)} ${r.surface}: ${r.path}${r.cmd ? ` [${r.cmd}]` : ''} -- ${r.detail}`)
  for (const r of results.filter((x) => x.klass === 'HUMAN')) console.log(`  HUMAN  ${r.surface}: ${r.path} -- ${r.detail}`)
  if (blocked.length) console.log(`  refused at the network layer: ${[...new Set(blocked)].join('; ')}`)
  if (errs.length) console.log(`  ${errs.length} page error(s) in all: ${[...new Set(errs)].slice(0, 5).join(' | ').slice(0, 400)}`)
}
try { await main() } catch (e) { failed = e; console.error(e) } finally {
  summary()
  if (JSON_OUT) writeFileSync(JSON_OUT, JSON.stringify(results, null, 1))
  await browser.close().catch(() => {})
  await stopWorkbench()
}
if (failed) process.exitCode = 3
else if (results.some((r) => ['NO-OP', 'ERROR', 'WRONG'].includes(r.klass))) process.exitCode = 1
