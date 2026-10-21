// Measures what our 3D view does with a selection of faces, edges and vertices, the way fcbehave.py measures FreeCAD's (sections
// "fit", "align" and "tree_menu" of fcbehave_dump.py): the camera after Fit All and Fit Selection on a perspective and an orthographic
// camera in a wide and a tall viewer, after Align to Selection from twelve starting orientations, and the entries of the tree's
// context menu on a part, on two parts and on the document. Writes OUT.json (same names as fcbehave.json) and, given the FreeCAD
// file, prints where the two differ.
//   NODE_PATH=<folder with playwright> node ui/scripts/oursselect.mjs URL PROJECTS_ROOT OUT.json [fcbehave.json] [--only=fit,align,tree_menu]
// URL is a workbench serving SCRATCH copies only, and PROJECTS_ROOT the folder it serves: the script adds a project "probe" to it (three
// plain solids, the same as the ones fcbehave_dump.py makes in FreeCAD) when there is none. It changes only the view and the selection.
// The pointer of the Mac is never moved (the right click on the tree is a Playwright event on the page).
import { createRequire } from 'module'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import path from 'path'
const require = createRequire(import.meta.url)
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = createRequire('/opt/node-tools/node_modules/')('playwright')) }
const args = process.argv.slice(2), flags = args.filter((a) => a.startsWith('--')), [BASE, ROOT, OUT, FC] = args.filter((a) => !a.startsWith('--'))
if (!BASE || !ROOT || !OUT) { console.error('usage: oursselect.mjs URL PROJECTS_ROOT OUT.json [fcbehave.json] [--only=fit,align,tree_menu,quickmeasure] [--compare-only]'); process.exit(2) }
const ONLY = new Set((flags.find((f) => f.startsWith('--only='))?.slice(7) ?? '').split(',').filter(Boolean))
const want = (n) => !ONLY.size || ONLY.has(n)
const COMPARE_ONLY = flags.includes('--compare-only') // compare an OUT.json written earlier with the FreeCAD file, without a browser
const url = BASE.replace(/#.*$/, '').replace(/\/?$/, '/')

// ── the project: block (Part::Box 170 x 82 x 40 from the origin), post (Part::Cylinder r 20, h 60, base at (300, 200, 10)) and tilted
// (Part::Box 120 x 70 x 30, corner at (400, 0, 0), turned 37 degrees about (1, 2, 3)) ──
const part = (doc, params, body) => `"""${doc}"""\nfrom build123d import Box, Cylinder\n\nMATERIAL = "aluminium"\nPROCESS = "cnc"\nMIN_FEATURE_MM = 1.0\nPARAMS = ${params}\n\n\ndef build(${Object.keys(JSON.parse(params.replace(/'/g, '"'))).join(', ')}):\n    return ${body}\n`
const PROJECT_FILES = {
  'assembly.py': `"""Scratch project for ui/scripts/oursselect.mjs: three plain solids, the same as the ones fcbehave_dump.py makes in FreeCAD."""
from build123d import Axis, Pos

from cad_agent.state import build_part

SLUG = "probe"


def parts():
    block, _ = build_part(SLUG, "block")
    post, _ = build_part(SLUG, "post")
    tilted, _ = build_part(SLUG, "tilted")
    # a part is built about its middle; a FreeCAD Placement turns a box about its corner, then moves it
    tilted = Pos(400, 0, 0) * (Pos(60, 35, 15) * tilted).rotate(Axis((0, 0, 0), (1, 2, 3)), 37)
    return {"block": Pos(85, 41, 20) * block, "post": Pos(300, 200, 40) * post, "tilted": tilted}
`,
  'parts/block.py': part('A plain box, 170 x 82 x 40.', '{"length": 170.0, "width": 82.0, "height": 40.0}', 'Box(length, width, height)'),
  'parts/post.py': part('A round post, radius 20 and 60 high.', '{"radius": 20.0, "height": 60.0}', 'Cylinder(radius, height)'),
  'parts/tilted.py': part('A second box, 120 x 70 x 30, turned by the assembly.', '{"length": 120.0, "width": 70.0, "height": 30.0}', 'Box(length, width, height)'),
}
const PROJECT_QM = {
  'assembly.py': `"""Scratch project for ui/scripts/oursselect.mjs's QuickMeasure section: block, post and a second post turned 30 degrees about x,
the same as the ones fcbehave_dump.py makes in FreeCAD."""
from build123d import Axis, Pos

from cad_agent.state import build_part

SLUG = "probeqm"


def parts():
    block, _ = build_part(SLUG, "block")
    post, _ = build_part(SLUG, "post")
    post2, _ = build_part(SLUG, "post2")
    # a Part::Cylinder turns about the middle of its base: lift the centred solid, turn it about the origin, then move it
    post2 = Pos(500, 200, 10) * (Pos(0, 0, 15) * post2).rotate(Axis((0, 0, 0), (1, 0, 0)), 30)
    return {"block": Pos(85, 41, 20) * block, "post": Pos(300, 200, 40) * post, "post2": post2}
`,
  'parts/block.py': PROJECT_FILES['parts/block.py'], 'parts/post.py': PROJECT_FILES['parts/post.py'],
  'parts/post2.py': part('A second round post, radius 10 and 30 high.', '{"radius": 10.0, "height": 30.0}', 'Cylinder(radius, height)'),
}
if (!COMPARE_ONLY) for (const [name, files] of [['probe', PROJECT_FILES], ['probeqm', PROJECT_QM]]) {
  const dir = path.join(ROOT, name)
  if (!existsSync(dir)) for (const [f, text] of Object.entries(files)) { mkdirSync(path.dirname(path.join(dir, f)), { recursive: true }); writeFileSync(path.join(dir, f), text) }
}
let out = { errors: {} }

if (!COMPARE_ONLY) {
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=angle', '--enable-unsafe-swiftshader'] })
const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } })
const p = await ctx.newPage()
const errs = []; p.on('pageerror', (e) => errs.push(e.message))
await p.goto(url + '#probe', { waitUntil: 'load' })
await p.waitForTimeout(3500)
await p.getByText('probe : 1').first().click()
for (let i = 0; i < 60; i++) { if (await p.evaluate(() => (cadui.getState().scene?.bodies.length ?? 0) >= 3)) break; await p.waitForTimeout(500) }
await p.waitForTimeout(1500)
await p.evaluate(() => cadui.setState({ animate: false })) // views change at once, as the FreeCAD probe's (setAnimationEnabled(False))

const settle = async () => {
  for (let i = 0; i < 80; i++) { const s = await p.evaluate(() => cadui.getView().probe()); if (s && !s.animating && !s.pendingFrame) break; await p.waitForTimeout(50) }
  await p.waitForTimeout(120)
}
const camera = () => p.evaluate(() => {
  const v = cadui.getView(), { cam, controls } = v.cameraParts(), t = controls.target, ortho = cam.isOrthographicCamera === true
  return { q: cam.quaternion.toArray(), position: cam.position.toArray(), target: t.toArray(), focal: cam.position.distanceTo(t),
    height: ortho ? (cam.top - cam.bottom) / cam.zoom : null, heightAngle: ortho ? null : (cam.fov * Math.PI) / 180, aspect: ortho ? (cam.right - cam.left) / (cam.top - cam.bottom) : cam.aspect }
})

// ── the same picks as fcbehave_dump.py: the Face, Edge or Vertex whose middle is nearest a point (kind null: the whole part) ──
const tiltPoint = (pt) => { // the tilted box's own point in the world: Rodrigues about (1, 2, 3), 37 degrees, then (400, 0, 0)
  const n = Math.hypot(1, 2, 3), k = [1 / n, 2 / n, 3 / n], c = Math.cos((37 * Math.PI) / 180), s = Math.sin((37 * Math.PI) / 180)
  const cr = [k[1] * pt[2] - k[2] * pt[1], k[2] * pt[0] - k[0] * pt[2], k[0] * pt[1] - k[1] * pt[0]], d = k[0] * pt[0] + k[1] * pt[1] + k[2] * pt[2]
  return [0, 1, 2].map((i) => pt[i] * c + cr[i] * s + k[i] * d * (1 - c) + [400, 0, 0][i])
}
const FIT_CASES = [
  ['fit all (no selection)', null],
  ['block whole', [['block', null, null]]],
  ['block +z face', [['block', 'Face', [85, 41, 40]]]],
  ['block -x face', [['block', 'Face', [0, 41, 20]]]],
  ['block vertical edge', [['block', 'Edge', [0, 0, 20]]]],
  ['block corner vertex', [['block', 'Vertex', [0, 0, 0]]]],
  ['block two faces +z +x', [['block', 'Face', [85, 41, 40]], ['block', 'Face', [170, 41, 20]]]],
  ['block opposite corners', [['block', 'Vertex', [0, 0, 0]], ['block', 'Vertex', [170, 82, 40]]]],
  ['post side face', [['post', 'Face', [300, 200, 40]]]],
  ['post top circle', [['post', 'Edge', [300, 200, 70]]]],
  ['block +z face and post whole', [['block', 'Face', [85, 41, 40]], ['post', null, null]]],
  ['block +z face and post top face', [['block', 'Face', [85, 41, 40]], ['post', 'Face', [300, 200, 70]]]],
  ['block whole and post vertex', [['block', null, null], ['post', 'Vertex', [320, 200, 70]]]],
  ['tilted -w face', [['tilted', 'Face', tiltPoint([60, 35, 0])]]],
]
const ALIGN_CASES = [
  ['block +z', [['block', 'Face', [85, 41, 40]]]], ['block -z', [['block', 'Face', [85, 41, 0]]]], ['block +x', [['block', 'Face', [170, 41, 20]]]],
  ['block -x', [['block', 'Face', [0, 41, 20]]]], ['block +y', [['block', 'Face', [85, 82, 20]]]], ['block -y', [['block', 'Face', [85, 0, 20]]]],
  ['tilted +u', [['tilted', 'Face', tiltPoint([120, 35, 15])]]], ['tilted -u', [['tilted', 'Face', tiltPoint([0, 35, 15])]]],
  ['tilted +v', [['tilted', 'Face', tiltPoint([60, 70, 15])]]], ['tilted -v', [['tilted', 'Face', tiltPoint([60, 0, 15])]]],
  ['tilted +w', [['tilted', 'Face', tiltPoint([60, 35, 30])]]], ['tilted -w', [['tilted', 'Face', tiltPoint([60, 35, 0])]]],
  ['post top disc', [['post', 'Face', [300, 200, 70]]]], ['post bottom disc', [['post', 'Face', [300, 200, 10]]]], ['post side', [['post', 'Face', [300, 200, 40]]]],
  ['block vertical edge', [['block', 'Edge', [0, 0, 20]]]], ['block top edge along x', [['block', 'Edge', [85, 0, 40]]]], ['post top circle', [['post', 'Edge', [300, 200, 70]]]],
  ['block +z and +x faces', [['block', 'Face', [85, 41, 40]], ['block', 'Face', [170, 41, 20]]]], ['block +z and post top', [['block', 'Face', [85, 41, 40]], ['post', 'Face', [300, 200, 70]]]],
  ['block corner vertex', [['block', 'Vertex', [0, 0, 0]]]], ['block whole', [['block', null, null]]],
]
const QM_CASES = [
  ['circle', [['post', 'Edge', [300, 200, 70]]]], ['disc face', [['post', 'Face', [300, 200, 70]]]], ['cylinder face', [['post', 'Face', [300, 200, 40]]]],
  ['two parallel edges', [['block', 'Edge', [0, 0, 20]], ['block', 'Edge', [170, 0, 20]]]],
  ['two circles, parallel axes', [['post', 'Edge', [300, 200, 70]], ['post', 'Edge', [300, 200, 10]]]],
  ['two circles, axes 30 degrees apart', [['post', 'Edge', [300, 200, 70]], ['post2', 'Edge', [500, 185, 35.98]]]],
  ['circle and a line', [['post', 'Edge', [300, 200, 70]], ['block', 'Edge', [0, 0, 20]]]],
  ['circle and a plane', [['post', 'Edge', [300, 200, 70]], ['block', 'Face', [85, 41, 40]]]],
  ['circle and its own cylinder', [['post', 'Edge', [300, 200, 70]], ['post', 'Face', [300, 200, 40]]]],
  ['circle and a cylinder 30 degrees off', [['post', 'Edge', [300, 200, 70]], ['post2', 'Face', [500, 192.5, 22.99]]]],
  ['point and a circle', [['block', 'Vertex', [0, 0, 0]], ['post', 'Edge', [300, 200, 70]]]],
  ['point and a cylinder', [['block', 'Vertex', [0, 0, 0]], ['post', 'Face', [300, 200, 40]]]],
  ['point and a plane', [['block', 'Vertex', [170, 82, 40]], ['post', 'Face', [300, 200, 70]]]],
]
const STARTS = [['front', 'front', 0], ['rear', 'rear', 0], ['top', 'top', 0], ['bottom', 'bottom', 0], ['left', 'left', 0], ['right', 'right', 0], ['iso', 'iso', 0],
  ['iso roll 30', 'iso', 30], ['front roll 60', 'front', 60], ['top roll 100', 'top', 100], ['top roll -170', 'top', -170], ['rear roll 20', 'rear', 20]]

/** The refs of a pick list: [body, kind, near] to "body.FaceN" (the element of that body whose middle is nearest `near`). */
const resolve = (picks) => p.evaluate((picks) => {
  const v = cadui.getView(), refs = []
  for (const [body, kind, near] of picks) {
    if (!kind) { refs.push({ body, ref: null }); continue }
    let best = null
    for (let n = 1; n < 500; n++) {
      const g = v.subGeometry(`${body}.${kind}${n}`)
      if (!g) break
      let mid
      if (g.kind === 'Face') {
        const c = { x: 0, y: 0, z: 0 }; let area = 0
        for (const [a, b, d] of g.tris) { const ar = b.clone().sub(a).cross(d.clone().sub(a)).length() / 2; area += ar; c.x += ar * (a.x + b.x + d.x) / 3; c.y += ar * (a.y + b.y + d.y) / 3; c.z += ar * (a.z + b.z + d.z) / 3 }
        mid = [c.x / area, c.y / area, c.z / area]
      } else if (g.kind === 'Edge') {
        const c = { x: 0, y: 0, z: 0 }; let len = 0
        for (const [a, b] of g.segs) { const l = a.distanceTo(b); len += l; c.x += l * (a.x + b.x) / 2; c.y += l * (a.y + b.y) / 2; c.z += l * (a.z + b.z) / 2 }
        mid = [c.x / len, c.y / len, c.z / len]
      } else mid = [g.point.x, g.point.y, g.point.z]
      const d = Math.hypot(mid[0] - near[0], mid[1] - near[1], mid[2] - near[2])
      if (!best || d < best.d) best = { d, ref: `${body}.${kind}${n}`, mid }
    }
    refs.push({ body, ref: best?.ref ?? null, mid: best?.mid })
  }
  return refs
}, picks)
const select = async (picks) => {
  const refs = await resolve(picks)
  const selected = [...new Set(refs.map((r) => r.body))], subSel = refs.filter((r) => r.ref).map((r) => r.ref)
  await p.evaluate(({ selected, subSel }) => cadui.setState({ selected, subSel }), { selected, subSel })
  await p.waitForTimeout(80)
  return { asked: refs.map((r) => r.ref ?? r.body), held: [selected, subSel] }
}
/** Std_ViewFitSelection / Std_AlignToSelection, through the command registry when the page has one (cadui.getCommand), else the view's own methods. */
const run = (cmd) => p.evaluate((cmd) => {
  const c = cadui.getCommand?.(cmd)
  if (c) { if (c.isEnabled()) c.run([]); return 'command' }
  const s = cadui.getState(), v = cadui.getView()
  if (cmd === 'Std_ViewFitSelection') { v.fitAll(s.selected); return 'fitAll' }
  const ref = s.subSel.find((r) => /\.Face\d+$/.test(r))
  if (ref) v.alignTo(ref)
  return 'alignTo'
}, cmd)
const setViewer = async (vw, vh) => {
  let W = 1280 + (vw - 936), H = 800 + (vh - 463), box
  for (let i = 0; i < 4; i++) {
    await p.setViewportSize({ width: Math.max(300, W), height: Math.max(300, H) }); await p.waitForTimeout(1200)
    box = await p.locator('canvas').first().boundingBox()
    W += Math.round(vw - box.width); H += Math.round(vh - box.height)
  }
  return [Math.round(box.width), Math.round(box.height)]
}
const setCamera = async (type) => { await p.evaluate((o) => cadui.getView().setOrtho(o), type === 'Orthographic'); await p.waitForTimeout(400); await settle() }
const view = async (name, roll) => {
  await p.evaluate(({ name, roll }) => {
    const v = cadui.getView()
    v.viewDir(name)
    if (roll) {
      const { cam } = v.cameraParts(), THREE_Q = cam.quaternion.constructor, V3 = cam.position.constructor
      const dir = new V3(0, 0, -1).applyQuaternion(cam.quaternion)
      v.orient(new THREE_Q().setFromAxisAngle(dir, (roll * Math.PI) / 180).multiply(cam.quaternion).toArray())
    }
  }, { name, roll })
  await settle()
}

if (want('fit')) try {
  out.fit = {}
  for (const vsz of [[1014, 661], [420, 760]]) {
    const got = await setViewer(...vsz), k = `${got[0]}x${got[1]}`
    out.fit[k] = {}
    for (const ctype of ['Perspective', 'Orthographic']) {
      await setCamera(ctype)
      const r = out.fit[k][ctype] = {}
      for (const [name, picks] of FIT_CASES) {
        await view('iso', 0)
        await p.evaluate(() => { cadui.setState({ selected: [], subSel: [] }); cadui.getView().fitAll() }); await settle()
        if (!picks) { r[name] = { state: await camera() }; continue }
        const sel = await select(picks)
        const before = await camera()
        const how = await run('Std_ViewFitSelection'); await settle()
        r[name] = { selection: sel, before, state: await camera(), how }
      }
    }
  }
  await setCamera('Orthographic')
} catch (e) { out.errors.fit = String(e.stack ?? e) }

if (want('align')) try {
  out.align = {}
  for (const [name, picks] of ALIGN_CASES) {
    const r = out.align[name] = {}
    for (const [sname, v, roll] of STARTS) {
      await view(v, roll)
      await p.evaluate(() => { cadui.setState({ selected: [], subSel: [] }); cadui.getView().fitAll() }); await settle()
      const sel = await select(picks)
      const before = await camera()
      const how = await run('Std_AlignToSelection'); await settle()
      r[sname] = { before: { q: before.q, target: before.target, focal: before.focal, height: before.height }, after: await camera(), how }
      if (sname === 'front') r.selection = sel
    }
  }
} catch (e) { out.errors.align = String(e.stack ?? e) }

if (want('tree_menu')) try {
  // The right-click menus are chrome.tsx's ContextMenu: a `.mb-content.ctx` of `.ctx-item`s (label, `.mb-kbd` key or arrow, `.mb-ico` check)
  // and `.mb-sep`s, whose sub-menu (`.ctx-sub`) is drawn inside the entry while the pointer is over it.
  const readMenu = () => p.evaluate(async () => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
    const root = () => document.querySelector('.mb-content.ctx')
    const over = (el, type) => el.dispatchEvent(new MouseEvent(type, { bubbles: true, relatedTarget: type === 'mouseover' ? document.body : el }))
    async function read(menu, depth) {
      const o = []
      for (const el of [...menu.children]) {
        if (el.classList.contains('mb-sep')) { o.push({ sep: true }); continue }
        if (!el.classList.contains('ctx-item')) continue
        const kbds = [...el.children].filter((c) => c.classList.contains('mb-kbd')).map((c) => c.textContent), lead = el.querySelector(':scope > .mb-ico')?.textContent ?? ''
        const text = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim()
        const isSub = kbds.includes('▸')
        const e = { text, shortcut: kbds.find((k) => k !== '▸') ?? '', name: el.getAttribute('data-cmd') || '', enabled: !el.hasAttribute('data-disabled'), checkable: lead.includes('✓'), checked: lead.includes('✓'), title: el.getAttribute('title') || '' }
        if (isSub && depth < 4) {
          over(el, 'mouseover'); await sleep(120)
          const sub = el.querySelector(':scope > .ctx-sub')
          e.menu = sub ? await read(sub, depth + 1) : []
          over(el, 'mouseout'); await sleep(60)
        }
        o.push(e)
      }
      return o
    }
    await sleep(300)
    const m = root()
    const items = m ? await read(m, 0) : 'no menu opened'
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await sleep(150)
    return items
  })
  await setViewer(1014, 661)
  await p.evaluate(() => cadui.showPanel('model'))
  await p.waitForTimeout(500)
  out.tree_menu = { workbench: 'ours' }
  const rightClick = async (row, names) => {
    await p.evaluate((n) => cadui.setState({ selected: n, subSel: [] }), names)
    await p.waitForTimeout(150)
    await row.click({ button: 'right' })
    return readMenu()
  }
  out.tree_menu.part = await rightClick(p.locator('.trow[data-name="block"]').first(), ['block'])
  out.tree_menu['two parts'] = await rightClick(p.locator('.trow[data-name="block"]').first(), ['block', 'post'])
  const docRow = p.locator('.trow.doc').first()
  out.tree_menu.document = (await docRow.count()) ? await rightClick(docRow, []) : 'no document row'
} catch (e) { out.errors.tree_menu = String(e.stack ?? e) }

if (want('quickmeasure')) try {
  await p.goto('about:blank')
  await p.goto(url + '#probeqm', { waitUntil: 'load' })
  await p.waitForTimeout(3500)
  await p.getByText('probeqm : 1').first().click()
  for (let i = 0; i < 60; i++) { if (await p.evaluate(() => (cadui.getState().scene?.bodies.length ?? 0) >= 3)) break; await p.waitForTimeout(500) }
  await p.waitForTimeout(1500)
  out.quickmeasure = {}
  for (const [name, picks] of QM_CASES) {
    const sel = await select(picks)
    await p.waitForTimeout(250)
    out.quickmeasure[name] = { selection: sel.held, message: await p.evaluate(() => { const e = document.querySelector('.sb-quick'); return e ? [e.textContent] : [] }) }
    await p.evaluate(() => cadui.setState({ selected: [], subSel: [] }))
  }
} catch (e) { out.errors.quickmeasure = String(e.stack ?? e) }

writeFileSync(OUT, JSON.stringify(out, null, 1))
if (errs.length) console.log('page errors:', [...new Set(errs)].slice(0, 5))
await b.close()
if (Object.keys(out.errors).length) console.log('errors:', out.errors)
} else out = JSON.parse(readFileSync(OUT, 'utf8'))

// ── the comparison with FreeCAD's file ──
if (FC) {
  const fc = JSON.parse(readFileSync(FC, 'utf8'))
  const qd = (a, c) => { const d = Math.abs(a[0] * c[0] + a[1] * c[1] + a[2] * c[2] + a[3] * c[3]); return (2 * Math.acos(Math.min(1, d)) * 180) / Math.PI }
  const f = (x) => (x == null ? '-' : Number(x).toFixed(3))
  const dist = (a, c) => Math.hypot(a[0] - c[0], a[1] - c[1], a[2] - c[2])
  if (out.fit && fc.fit) {
    console.log('\nFit All / Fit Selection: ours against FreeCAD (target = the focal point; the distance in a perspective view, the visible height in an orthographic one)')
    let bad = 0, total = 0, knownCount = 0
    for (const [vk, v] of Object.entries(out.fit)) {
      const fv = Object.entries(fc.fit).find(([k]) => Math.abs(Number(k.split('x')[0]) - Number(vk.split('x')[0])) < 4 && Math.abs(Number(k.split('x')[1]) - Number(vk.split('x')[1])) < 4)?.[1]
      if (!fv) { console.log(`  no FreeCAD viewer near ${vk}`); continue }
      for (const [ct, cases] of Object.entries(v)) {
        for (const [name, o] of Object.entries(cases)) {
          const c = fv[ct]?.[name]
          if (!c) continue
          total++
          const key = ct === 'Perspective' ? 'focal' : 'height'
          // both scale with 1 / min(1, aspect) and the two viewers are a pixel or two apart: compare what the shorter side shows
          const aspect = (k) => Number(k.split('x')[0]) / Number(k.split('x')[1]), fk = Object.keys(fc.fit).find((k) => fc.fit[k] === fv)
          const dt = dist(o.state.target, c.state.target), ratio = (o.state[key] * Math.min(1, aspect(vk))) / (c.state[key] * Math.min(1, aspect(fk)))
          // FreeCAD frames a part that has a Placement (post, tilted) by its box without the Placement when an element of it is selected
          const placed = /post|tilted/.test(name) && !/whole$/.test(name) && !/fit all/.test(name)
          const ok = dt < 0.5 && Math.abs(ratio - 1) < 0.003, known = !ok && placed
          if (!ok && !known) bad++
          if (known) knownCount++
          if (!ok || process.env.SHOW_ALL) console.log(`  ${ok ? ' ok ' : known ? 'known' : 'DIFF'} ${vk} ${ct.padEnd(12)} ${name.padEnd(34)} target off by ${f(dt)} mm, ${key} ours ${f(o.state[key])} FreeCAD ${f(c.state[key])} (x${f(ratio)})`)
        }
      }
    }
    console.log(`  ${total - bad - knownCount} of ${total} agree, ${knownCount} differ because FreeCAD frames a part with a Placement by its box without it (not copied)`)
  }
  if (out.align && fc.align) {
    console.log('\nAlign to Selection: ours against FreeCAD (orientation difference in degrees, focal point moved by)')
    let bad = 0, total = 0
    for (const [name, o] of Object.entries(out.align)) {
      const c = fc.align[name]
      if (!c) continue
      const rows = []
      for (const [sname, r] of Object.entries(o)) {
        if (sname === 'selection') continue
        total++
        const fr = c[sname], dq = qd(r.after.q, fr.after.q), moved = dist(r.after.target, fr.after.target)
        if (dq > 0.05 || moved > 0.5) { bad++; rows.push(`${sname} (${f(dq)} deg, ${f(moved)} mm)`) }
      }
      console.log(`  ${rows.length ? 'DIFF' : ' ok '} ${name.padEnd(26)} ${rows.length ? 'differs from ' + rows.length + ' of ' + (Object.keys(o).length - 1) + ' starts: ' + rows.slice(0, 4).join(', ') : ''}`)
    }
    console.log(`  ${total - bad} of ${total} agree`)
  }
  if (out.quickmeasure && fc.quickmeasure) {
    console.log('\nQuickMeasure (the status bar\'s right side): ours against FreeCAD')
    let bad = 0
    for (const [name, o] of Object.entries(out.quickmeasure)) {
      const c = fc.quickmeasure[name], ot = (o.message[0] ?? '').trim(), ct = (c?.message[0] ?? '').trim()
      if (ot !== ct) bad++
      console.log(`  ${ot === ct ? ' ok ' : 'DIFF'} ${name.padEnd(38)} ours "${ot}"${ot === ct ? '' : `  FreeCAD "${ct}"`}`)
    }
    console.log(`  ${Object.keys(out.quickmeasure).length - bad} of ${Object.keys(out.quickmeasure).length} agree`)
  }
  if (out.tree_menu && fc.tree_menu) {
    const MAC = { Ctrl: '⌘', Shift: '⇧', Alt: '⌥', Meta: '⌃', Backspace: '⌫', Return: '↵', Del: '⌦' }
    const native = (s) => { if (!s) return ''; const parts = s.split('+'), key = parts.pop(); const mods = ['Meta', 'Alt', 'Shift', 'Ctrl'].filter((m) => parts.includes(m)); return mods.map((m) => MAC[m]).join('') + (MAC[key] ?? key) }
    const norm = (t) => t.replace(/&&/g, '\0').replace(/&/g, '').replace(/\0/g, '&').replace(/…$/, '').trim()
    const flat = (items, pre = '') => items.flatMap((i) => (i.sep ? [] : [{ path: pre + norm(i.text), key: native(i.shortcut) || i.shortcut, enabled: i.enabled !== false, checked: !!i.checked }, ...(i.menu ? flat(i.menu, pre + norm(i.text) + ' > ') : [])]))
    console.log('\nTree context menu: ours against FreeCAD')
    for (const k of ['part', 'two parts', 'document']) {
      const o = out.tree_menu[k], c = fc.tree_menu[k]
      if (typeof o === 'string' || typeof c === 'string') { console.log(`  ${k}: ours ${typeof o === 'string' ? o : 'ok'}, FreeCAD ${typeof c === 'string' ? c : 'ok'}`); continue }
      const fo = flat(o), fcm = flat(c), seen = new Set()
      console.log(`  ${k}:`)
      for (const e of fcm) {
        const m = fo.find((x) => x.path === e.path)
        if (!m) { console.log(`    missing in ours: ${e.path}${e.key ? '  [' + e.key + ']' : ''}${e.enabled ? '' : ' (disabled)'}`); continue }
        seen.add(m.path)
        const d = []
        if (m.key !== e.key && !(m.key === '' && e.key === '')) d.push(`key ${m.key || '-'} vs ${e.key || '-'}`)
        if (m.enabled !== e.enabled) d.push(`enabled ${m.enabled} vs ${e.enabled}`)
        if (d.length) console.log(`    differs: ${e.path}: ${d.join(', ')}`)
      }
      for (const x of fo) if (!seen.has(x.path)) console.log(`    only in ours: ${x.path}${x.key ? '  [' + x.key + ']' : ''}`)
    }
  }
}
