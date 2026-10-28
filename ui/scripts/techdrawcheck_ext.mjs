// SPDX-License-Identifier: LGPL-2.1-or-later
// techdrawcheck's `ext` section: TechDraw's extension commands (CommandExtensionPack.cpp, CommandExtensionDims.cpp,
// TechDraw_ShowAll, TechDraw_ExtensionPositionSectionView) in the page, held to the real FreeCAD GUI's own recording
// (ui/scripts/fctechdraw_ext.json, written by fctechdraw_ext.py). Each command is run as the recording ran it: the
// recording's selection made on the page, the command from the registry (what a menu or a toolbar button runs), then
// the view's edges and vertices in FreeCAD's numbering, its cosmetic geometry, the dimensions and balloons, the undo
// step and the message boxes are compared. techdrawcheck.mjs calls it with its helpers.
import { readFileSync } from 'fs'
import { join } from 'path'

const CMD = {
  pack_circle2: 'TechDraw_ExtensionDrawCosmCircle', pack_circle3: 'TechDraw_ExtensionDrawCosmCircle3Points', pack_arc: 'TechDraw_ExtensionDrawCosmArc',
  pack_parallel: 'TechDraw_ExtensionLineParallel', pack_perpendicular: 'TechDraw_ExtensionLinePerpendicular',
  pack_perpendicular_vertex_first: 'TechDraw_ExtensionLinePerpendicular', pack_parallel_bad: 'TechDraw_ExtensionLineParallel',
  pack_circle_cl: 'TechDraw_ExtensionCircleCenterLines', pack_circle_cl_line: 'TechDraw_ExtensionCircleCenterLines',
  pack_extend: 'TechDraw_ExtensionExtendLine', pack_shorten: 'TechDraw_ExtensionShortenLine', pack_extend_hlr: 'TechDraw_ExtensionExtendLine',
  pack_extend_circle: 'TechDraw_ExtensionExtendLine', pack_extend_cl: 'TechDraw_ExtensionExtendLine', pack_shorten_cl: 'TechDraw_ExtensionShortenLine',
  showall: 'TechDraw_ShowAll', showall_back: 'TechDraw_ShowAll', lock: 'TechDraw_ExtensionLockUnlockView', lock_back: 'TechDraw_ExtensionLockUnlockView',
  attrs_change: 'TechDraw_ExtensionChangeLineAttributes', attrs_extend: 'TechDraw_ExtensionExtendLine', attrs_circle: 'TechDraw_ExtensionDrawCosmCircle',
  attrs_perpendicular: 'TechDraw_ExtensionLinePerpendicular', pack_holecircle: 'TechDraw_ExtensionHoleCircle', pack_holecircle_three: 'TechDraw_ExtensionHoleCircle',
  pack_holecircle_two: 'TechDraw_ExtensionHoleCircle', pack_holecircle_cl: 'TechDraw_ExtensionCircleCenterLines',
  pack_thread_hole_side: 'TechDraw_ExtensionThreadHoleSide', pack_thread_bolt_side: 'TechDraw_ExtensionThreadBoltSide',
  pack_thread_side_one: 'TechDraw_ExtensionThreadBoltSide', pack_thread_hole_bottom: 'TechDraw_ExtensionThreadHoleBottom',
  pack_thread_bolt_bottom: 'TechDraw_ExtensionThreadBoltBottom', pack_thread_bottom_line: 'TechDraw_ExtensionThreadBoltBottom',
  dims_chain_h: 'TechDraw_ExtensionCreateHorizChainDimension', dims_chain_v: 'TechDraw_ExtensionCreateVertChainDimension',
  dims_chain_o: 'TechDraw_ExtensionCreateObliqueChainDimension', dims_coord_h: 'TechDraw_ExtensionCreateHorizCoordDimension',
  dims_coord_h_rev: 'TechDraw_ExtensionCreateHorizCoordDimension', dims_coord_v: 'TechDraw_ExtensionCreateVertCoordDimension',
  dims_coord_o: 'TechDraw_ExtensionCreateObliqueCoordDimension', dims_chamfer_h: 'TechDraw_ExtensionCreateHorizChamferDimension',
  dims_chamfer_v: 'TechDraw_ExtensionCreateVertChamferDimension', dims_chamfer_h_neg: 'TechDraw_ExtensionCreateHorizChamferDimension',
  dims_arc: 'TechDraw_ExtensionCreateLengthArc', dims_arc_line: 'TechDraw_ExtensionCreateLengthArc', dims_chain_h_one: 'TechDraw_ExtensionCreateHorizChainDimension',
  dims_pos_h: 'TechDraw_ExtensionPosHorizChainDimension', dims_pos_v: 'TechDraw_ExtensionPosVertChainDimension', dims_pos_o: 'TechDraw_ExtensionPosObliqueChainDimension',
  dims_pos_none: 'TechDraw_ExtensionPosHorizChainDimension', dims_cascade_h: 'TechDraw_ExtensionCascadeHorizDimension',
  dims_cascade_v: 'TechDraw_ExtensionCascadeVertDimension', dims_cascade_o: 'TechDraw_ExtensionCascadeObliqueDimension',
  dims_prefix_diameter: 'TechDraw_ExtensionInsertDiameter', dims_prefix_square: 'TechDraw_ExtensionInsertSquare',
  dims_prefix_repeat: 'TechDraw_ExtensionInsertRepetition', dims_prefix_remove: 'TechDraw_ExtensionRemovePrefixChar',
  dims_prefix_remove_again: 'TechDraw_ExtensionRemovePrefixChar', dims_decimal_up: 'TechDraw_ExtensionIncreaseDecimal', dims_decimal_down: 'TechDraw_ExtensionDecreaseDecimal',
  notes_area: 'TechDraw_ExtensionAreaAnnotation', notes_area_none: 'TechDraw_ExtensionAreaAnnotation', notes_arclength: 'TechDraw_ExtensionArcLengthAnnotation',
  notes_arclength_circle: 'TechDraw_ExtensionArcLengthAnnotation',
  verts_intersection_lines: 'TechDraw_ExtensionVertexAtIntersection', verts_intersection_circle: 'TechDraw_ExtensionVertexAtIntersection',
  verts_intersection_one: 'TechDraw_ExtensionVertexAtIntersection', verts_intersection_vertex: 'TechDraw_ExtensionVertexAtIntersection',
}
// FreeCAD makes no undo step for these (the object changes, not a property); here they are one, the page being a file
const NO_STEP_THERE = new Set(['pack_extend_cl', 'pack_shorten_cl', 'showall', 'showall_back', 'attrs_change'])
// after refreshCEGeoms FreeCAD's live view lists the centre lines before the cosmetic edges, until it is recomputed: we number them the other way
const UNORDERED = new Set(['attrs_change', 'pack_thread_bottom_line', 'dims_chain_h_one'])
const UNORDERED_PREFIX = 'dims_'

export async function extChecks(h) {
  const { page, st, until, runCmd, td, idle, select, sleep, check, same, near, bad, note, undoHead, ok, ROOT, SLUG, REPO } = h
  const EXT = JSON.parse(readFileSync(h.extFile ?? join(REPO, 'ui', 'scripts', 'fctechdraw_ext.json'), 'utf8'))
  console.log('ext')
  const clean = (t) => String(t ?? '').replace(/&(.)/g, '$1').replace(/…$/, '').trim()
  const cad = (...argv) => st(`fetch('/api/cad', { method: 'POST', headers: { 'X-CAD': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ slug: '${SLUG}', argv: ${JSON.stringify(argv)} }) }).then((r) => r.json())`)
  const doc = async () => (await td()).docs.Page
  const viewOf = async (name) => (await doc()).result.views[name]
  const objectOf = async (name) => (await doc()).objects.find((o) => o.name === name)
  const msgText = async () => { await until('!!document.querySelector(".msgbox")', 'a message', 8000); const t = await st('document.querySelector(".msgbox-text")?.textContent'); await page.click('.msgbox-buttons .qbtn'); await sleep(200); return t }
  const noMsg = async () => !(await st('!!document.querySelector(".msgbox")'))
  const round = (a) => a.map((x) => Math.round(x * 1e4) / 1e4)
  // ── a page: View (plate from above), Flange, ShaftF, ShaftT, as the recording's script made them ──
  await sleep(300)
  await runCmd('TechDraw_PageDefault')
  await until('cadui.td.state().pages.includes("Page")', 'the page')
  await st(`cadui.td.apply("Page", ${JSON.stringify([
    { op: 'view', source: ['plate'], direction: [0, 0, 1], name: 'View' }, { op: 'view', source: ['flange'], direction: [0, 0, 1], name: 'Flange' },
    { op: 'view', source: ['shaft'], direction: [0, -1, 0], name: 'ShaftF' }, { op: 'view', source: ['shaft'], direction: [0, 0, 1], name: 'ShaftT' }])}, "Create view")`)
  await idle(); await sleep(800)

  const geometry = async (view, rec, what, unordered = false) => {
    const v = await viewOf(view)
    if (v.edges.length !== rec.edges.length || v.vertices.length !== rec.vertices.length) { bad(`${what}: the geometry`, `${v.edges.length} edges and ${v.vertices.length} vertices, FreeCAD ${rec.edges.length} and ${rec.vertices.length}`); return }
    const s = v.scale
    const ours = v.edges.map((e) => [...round([e.start[0] / s, -e.start[1] / s, e.end[0] / s, -e.end[1] / s])])
    const theirs = rec.edges.map((e) => round([e.start[0], e.start[1], e.end[0], e.end[1]]))
    const key = (a) => JSON.stringify(a)
    const a = unordered ? [...ours].sort((x, y) => (key(x) < key(y) ? -1 : 1)) : ours, b = unordered ? [...theirs].sort((x, y) => (key(x) < key(y) ? -1 : 1)) : theirs
    let why = ''
    a.forEach((e, i) => { if (!why && !near(e, b[i], 1e-3)) why = `Edge${i}: ours ${JSON.stringify(e)} FreeCAD ${JSON.stringify(b[i])}` })
    v.vertices.forEach((p, i) => { if (!why && !near([p.x / s, -p.y / s], rec.vertices[i].slice(0, 2), 1e-3)) why = `Vertex${i}: ours ${JSON.stringify([p.x, p.y])} FreeCAD ${JSON.stringify(rec.vertices[i])}` })
    check(!why, `${what}: the edges and vertices${unordered ? '' : ", in FreeCAD's numbering"}`, why)
  }
  const cosmetics = async (view, rec, what) => {
    const o = await objectOf(view)
    const ce = o.cosmetic_edges ?? []
    if (ce.length !== rec.CosmeticEdges.length) { bad(`${what}: the cosmetic edges`, `${ce.length}, FreeCAD ${rec.CosmeticEdges.length}`); return }
    let why = ''
    ce.forEach((c, i) => {
      const r = rec.CosmeticEdges[i]
      const f = { style: 2, weight: 0.5, visible: true, ...(c.format ?? {}) }
      if (f.style !== r.Format.style || Math.abs(f.weight - r.Format.weight) > 1e-6 || f.visible !== r.Format.visible) why ||= `CE${i}: pen ${JSON.stringify(f)} FreeCAD ${JSON.stringify(r.Format)}`
      if (c.geom === 'line' ? !(near(c.start.slice(0, 2), r.Start.slice(0, 2), 1e-4) && near(c.end.slice(0, 2), r.End.slice(0, 2), 1e-4))
        : !(near(c.center.slice(0, 2), r.Center.slice(0, 2), 1e-4) && Math.abs(c.radius - r.Radius) < 1e-4)) why ||= `CE${i}: ours ${JSON.stringify(c)} FreeCAD ${JSON.stringify([r.Start, r.End, r.Center, r.Radius])}`
    })
    const cv = o.cosmetic_vertexes ?? []
    if (cv.length !== rec.CosmeticVertexes.length) why ||= `${cv.length} cosmetic vertices, FreeCAD ${rec.CosmeticVertexes.length}`
    check(!why, `${what}: the cosmetic edges and vertices`, why)
  }
  const dimsAndNotes = async (rec, what, newNames) => {
    const os = (await doc()).objects
    const dims = os.filter((o) => o.kind === 'DrawViewDimension'), balloons = os.filter((o) => o.kind === 'DrawViewBalloon')
    if (dims.length !== Object.keys(rec.dims).length) { bad(`${what}: the dimensions`, `${dims.map((d) => d.name)} vs ${Object.keys(rec.dims)}`); return }
    let why = ''
    for (const d of dims) {
      const r = rec.dims[d.name]
      if (!r) { why ||= `${d.name} is not FreeCAD's`; continue }
      const refs = JSON.stringify([[d.references_2d[0][0], d.references_2d.map((x) => x[1])]]), frefs = JSON.stringify(r.References2D)
      if (d.dim_type !== r.Type || d.format_spec !== r.FormatSpec || refs !== frefs || !!d.arbitrary !== r.Arbitrary) why ||= `${d.name}: ${d.dim_type} ${d.format_spec} ${refs}; FreeCAD ${r.Type} ${r.FormatSpec} ${frefs}`
      if (newNames.has(d.name) && !(Math.abs(d.x - r.X) < 1e-4 && Math.abs(d.y - r.Y) < 1e-4)) why ||= `${d.name}: X, Y ${d.x}, ${d.y}; FreeCAD ${r.X}, ${r.Y}`
    }
    check(!why, `${what}: the dimensions`, why)
    if (balloons.length !== Object.keys(rec.balloons).length) { bad(`${what}: the balloons`, `${balloons.map((d) => d.name)} vs ${Object.keys(rec.balloons)}`); return }
    for (const b of balloons) {
      const r = rec.balloons[b.name]
      if (newNames.has(b.name)) same([b.text, b.bubble_shape, b.end_type, Math.round(b.x * 1e3) / 1e3, Math.round(b.y * 1e3) / 1e3, b.font_size, b.line_visible],
        [r.Text, r.BubbleShape, r.EndType, Math.round(r.X * 1e3) / 1e3, Math.round(r.Y * 1e3) / 1e3, r.vp.Fontsize, r.vp.LineVisible], `${what}: ${b.name}`)
    }
  }
  // our Edge<n> for the recording's, after Change Line Attributes (FreeCAD's centre lines come first there)
  const ourNumbering = async (view, subs) => {
    const edges = (await viewOf(view)).edges
    const first = edges.findIndex((e) => e.cls === 'cosmetic' || e.cls === 'centerline')
    const nCe = edges.filter((e) => e.cls === 'cosmetic').length, nCl = edges.filter((e) => e.cls === 'centerline').length
    return subs.map((s) => {
      if (!s.startsWith('Edge')) return s
      let k = Number(s.slice(4))
      if (k >= first + nCl) k -= nCl; else if (k >= first) k += nCe
      return `Edge${k}`
    })
  }

  const run = async (key, { view = 'View', after = null } = {}) => {
    const rec = EXT[key]
    if (!rec) { bad(`${key}`, 'is not in the recording'); return }
    const sel = rec.selection
    let refs = sel.flatMap(([obj, subs]) => (subs.length ? subs.map((s) => `Page/${obj}.${s}`) : [`Page/${obj}`]))
    if (key === 'attrs_extend') refs = (await ourNumbering(sel[0][0], sel[0][1])).map((s) => `Page/${sel[0][0]}.${s}`)
    if (key.startsWith('dims_pos') || key.startsWith('dims_cascade')) {
      // the dimensions the recording moved about first (REC.scatter)
      const group = { dims_pos_h: 'chain_h', dims_pos_v: 'chain_v', dims_pos_o: 'chain_o', dims_cascade_h: 'coord_h', dims_cascade_v: 'coord_v', dims_cascade_o: 'coord_o' }[key]
      if (group) {
        await st(`cadui.td.apply("Page", ${JSON.stringify(Object.entries(EXT.scatter[group]).map(([name, xy]) => ({ op: 'set', name, props: { x: xy[0], y: xy[1] } })))}, "Drag Dimension")`)
        await idle(); await sleep(300)
      }
    }
    const before = new Set((await doc()).objects.map((o) => o.name))
    await select(refs)
    const n0 = await st('cadui.getState().undo[0]?.id ?? null')
    await runCmd(CMD[key])
    const dialog = rec.dialogs.find((d) => d.title !== 'Prefix Text')
    if (key === 'dims_prefix_repeat') {
      await until('!!document.querySelector(".msgbox input")', 'the Prefix Text dialog', 8000)
      await page.fill('.msgbox input', '4'); await page.click('.msgbox-buttons .qbtn')
    }
    if (dialog) same(await msgText(), dialog.text, `${key}: the message box`)
    if (process.env.EXT_DEBUG) console.log(key, JSON.stringify(await st('cadui.getState().log.slice(-3)')))
    await idle(); await sleep(500)
    const what = `${key} (${CMD[key].replace('TechDraw_Extension', '')})`
    check(await noMsg(), `${what}: no message box left`)
    const st1 = rec.state
    const unordered = UNORDERED.has(key) || key.startsWith(UNORDERED_PREFIX)
    await geometry(rec.selection[0][0] === 'View' || !(await viewOf(rec.selection[0][0])) ? 'View' : rec.selection[0][0], st1, what, unordered)
    const vname = (await viewOf(rec.selection[0][0])) ? rec.selection[0][0] : 'View'
    await cosmetics(vname, st1, what)
    const created = new Set((await doc()).objects.map((o) => o.name).filter((n) => !before.has(n)))
    await dimsAndNotes(st1, what, new Set([...created, ...(key.startsWith('dims_pos') || key.startsWith('dims_cascade') ? (dialog ? [] : rec.selection.map((x) => x[0])) : [])]))
    await sleep(300)
    const head = (await st('cadui.getState().undo[0]?.id ?? null')) !== n0 ? await undoHead() : null
    const f = rec.undo.head[0] ?? null
    if (NO_STEP_THERE.has(key)) {
      if (f === null) note(`${what}: no undo step in FreeCAD (${key.startsWith('showall') ? 'a view provider property' : 'no property changes'}); here ${head ? `"${head}"` : 'none'}`)
      else same(head, f, `${what}: the undo step`)
    } else same(head, f, `${what}: the undo step`)
    if (after) await after()
  }
  const panelNames = () => st(`[...document.querySelectorAll('.tasks [data-qf]')].map((e) => e.getAttribute('data-qf')).filter((n) => n && !n.includes('::'))`)
  const fcNames = (p) => [...new Set(p.flat().map((w) => w.name).filter((n) => n && !n.startsWith('qt_')))].sort()
  const fill = async (sel, text) => { await page.fill(sel, text); await page.locator(sel).evaluate((e) => e.blur()); await sleep(250) }
  const title = () => st(`document.querySelector('.tasks .tbox-head span')?.textContent`)
  const order = Object.keys(EXT).filter((k) => CMD[k] || k === 'dims_decimal_limits' || k === 'offset_vertex' || k.startsWith('customize_'))
  const done = new Set()
  for (const key of order) {
    if (key === 'pack_cl_make') continue
    if (key === 'offset_vertex') {
      // Offset Vertex (TaskAddOffsetVertex.py): the panel, the offset typed, OK; and Cancel of another
      const rec = EXT.offset_vertex
      for (const [ok_, vertex, r] of [[true, 'Vertex8', rec], [false, 'Vertex3', EXT.offset_vertex_cancel]]) {
        const n0 = await st('cadui.getState().undo[0]?.id ?? null'), cv0 = ((await objectOf('View')).cosmetic_vertexes ?? []).length
        await select([`Page/View.${vertex}`])
        await runCmd('TechDraw_CommandAddOffsetVertex')
        await until('cadui.getState().task?.other?.startsWith("offsetvertex:")', 'the Offset Vertex panel')
        await sleep(500)
        same((await panelNames()).filter((n, i, a) => a.indexOf(n) === i).sort(), fcNames(r.panel), `Offset Vertex: the panel's widgets`)
        same(await title(), 'Offset Vertex', 'Offset Vertex: the panel\'s title')
        same(await st(`document.querySelector('.tasks [data-qf="le_SourceVertex"]')?.value`), r.edit.source, 'Offset Vertex: the reference')
        await fill('.tasks [data-qf="dSpinBoxX"] input', String(r.edit.dSpinBoxX)); await fill('.tasks [data-qf="dSpinBoxY"] input', String(r.edit.dSpinBoxY))
        await idle(); await sleep(500)
        if (ok_) {
          await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(500)
          const cv = (await objectOf('View')).cosmetic_vertexes
          same(cv.at(-1).point.slice(0, 2), r.view.CosmeticVertexes.at(-1).Point.slice(0, 2), 'Offset Vertex: the vertex')
          same(cv.length, cv0 + 1, 'Offset Vertex: one vertex')
          same(await undoHead(), r.undo.head[0], 'Offset Vertex: the undo step')
        } else {
          await page.click('.tasks .tbuttons .qbtn:not(.default)'); await idle(); await sleep(500)
          same(((await objectOf('View')).cosmetic_vertexes ?? []).length, cv0, 'Offset Vertex, Cancel: no vertex')
          same(await st('cadui.getState().undo[0]?.id ?? null'), n0, 'Offset Vertex, Cancel: no undo step')
        }
      }
      continue
    }
    if (key.startsWith('customize_')) {
      // Customize Format Label (TaskCustomizeFormat): the format typed, two symbols clicked, the preview, OK
      const rec = EXT[key], name = rec.selection[0][0]
      await select([`Page/${name}`])
      await runCmd('TechDraw_ExtensionCustomizeFormat')
      await until('cadui.getState().task?.other?.startsWith("customize:")', 'the Customize Format panel')
      await sleep(500)
      same([...new Set(await panelNames())].sort(), fcNames(rec.panel), `${key}: the panel's widgets`)
      same(await title(), 'Customize Format', `${key}: the panel's title`)
      same(await st(`document.querySelector('.tasks [data-qf="leFormat"]')?.value`), rec.edit.before[0], `${key}: the format`)
      same(await st(`document.querySelector('.tasks [data-qf="lbShowPreview"]')?.textContent`), rec.edit.before[1], `${key}: the preview`)
      await fill('.tasks [data-qf="leFormat"]', '%.1f mm')
      same(await st(`document.querySelector('.tasks [data-qf="lbShowPreview"]')?.textContent`), rec.edit.typed[1], `${key}: the preview of what is typed`)
      for (const b of ['pbA01', 'pbC01']) { await page.click(`.tasks [data-qf="${b}"]`); await sleep(150) }
      same(await st(`document.querySelector('.tasks [data-qf="leFormat"]')?.value`), rec.edit.clicked[0], `${key}: the symbols inserted`)
      same(await st(`document.querySelector('.tasks [data-qf="lbShowPreview"]')?.textContent`), rec.edit.clicked[1], `${key}: the preview after the symbols`)
      await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(500)
      const o = await objectOf(name)
      same(key.endsWith('dim') ? o.format_spec : o.text, key.endsWith('dim') ? rec.after.FormatSpec : rec.after.Text, `${key}: the result`)
      same(await undoHead(), rec.undo.head[0], `${key}: the undo step`)
      continue
    }
    if (key === 'dims_decimal_limits') {
      // three decreases and eleven increases of the second dimension's decimals: they stop at 0 and at 9
      const two = EXT.dims_prefix_square.selection[0][0]
      for (const [cmd, n] of [['TechDraw_ExtensionDecreaseDecimal', 3], ['TechDraw_ExtensionIncreaseDecimal', 11]]) {
        for (let i = 0; i < n; i++) { await select([`Page/${two}`]); await runCmd(cmd); await idle(); await sleep(150) }
      }
      same((await objectOf(two)).format_spec, EXT.dims_decimal_limits.at(-1), 'the decimals stop at 0 and 9')
      continue
    }
    if (key === 'attrs_change' && !done.has('attrs')) {
      // Select Line Attributes: the panel, its first values, the values the recording typed, OK
      await select(['Page/View'])
      await runCmd('TechDraw_ExtensionSelectLineAttributes')
      await until('!!document.querySelector(".tasks [data-qf=cbLineStyle]")', 'TaskSelectLineAttributes')
      await sleep(400)
      const names = await st(`[...document.querySelectorAll('.tasks [data-qf]')].map((e) => e.getAttribute('data-qf')).filter((n) => n && !n.includes('::'))`)
      const fcNames = [...new Set(EXT.attrs_select.panel.flat().map((w) => w.name).filter((n) => n && !n.startsWith('qt_')))]
      same([...new Set(names)].sort(), fcNames.sort(), 'Select Line Attributes: the panel\'s widgets')
      same(await st(`document.querySelector('.tasks [data-qf="cbLineStyle"] .combo-label')?.textContent`), 'Hidden', 'Select Line Attributes: the style opens on Hidden')
      await page.click('.tasks [data-qf="cbLineStyle"]'); await page.locator('.combo-popup .combo-item', { hasText: /^Symmetry$/ }).first().click(); await sleep(200)
      await page.click('.tasks [data-qf="rbThick"] input'); await sleep(200)
      for (const [n, v] of [['sbSpacing', '12'], ['sbStretch', '4']]) { await page.fill(`.tasks [data-qf="${n}"] input`, v); await page.locator(`.tasks [data-qf="${n}"] input`).evaluate((e) => e.blur()); await sleep(200) }
      const n0 = await st('cadui.getState().undo[0]?.id ?? null')
      await page.click('.tasks .tbuttons .qbtn.default'); await sleep(400)
      check((await st('cadui.getState().undo[0]?.id ?? null')) === n0, 'Select Line Attributes: no undo step (the session\'s attributes)')
      done.add('attrs')
    }
    await run(key)
    if (key === 'pack_extend_circle') {
      // a centre line to extend, made by the panel of TechDraw_2LineCenterLine as the recording did
      await select(['Page/View.Edge0', 'Page/View.Edge4'])
      await runCmd('TechDraw_2LineCenterLine')
      await until('cadui.getState().task?.other?.startsWith("centerline:")', 'the centerline panel')
      await sleep(500)
      await page.click('.tasks .tbuttons .qbtn.default'); await idle(); await sleep(500)
      await geometry('View', EXT.pack_cl_make.view, 'pack_cl_make (2LineCenterLine)')
      await cosmetics('View', EXT.pack_cl_make.view, 'pack_cl_make')
    }
  }  // ── TechDraw_ExtensionPositionSectionView: a section of a projection group's item is lined up with the group ──
  await st(`cadui.td.apply("Page", ${JSON.stringify([{ op: 'projgroup', source: ['plate'] }])}, "Create projection group")`)
  await idle()
  await st(`cadui.td.apply("Page", ${JSON.stringify([{ op: 'set', name: 'ProjGroup', props: { x: 100, y: 150 } },
    { op: 'section', base_view: 'ProjItem', direction: 'Down', name: 'Sec' }])}, "Create Section View")`)
  await idle()
  await st(`cadui.td.apply("Page", ${JSON.stringify([{ op: 'set', name: 'Sec', props: { x: 160, y: 40 } }])}, "Drag view")`)
  await idle(); await sleep(300)
  await select(['Page/Sec'])
  await runCmd('TechDraw_ExtensionPositionSectionView'); await idle(); await sleep(500)
  const sec = await objectOf('Sec'), g = await objectOf('ProjGroup')
  same([sec.x, sec.y], [EXT.section_pos.state.sections.Section.X, EXT.section_pos.state.sections.Section.Y], 'Position Section View: the section lined up with its base view\'s group')
  same(g && [g.x, g.y], [100, 150], 'Position Section View: the group stays')
  note(`Position Section View: no undo step in FreeCAD (the Python command sets X and Y outside a transaction); here "${await undoHead()}"`)
}
