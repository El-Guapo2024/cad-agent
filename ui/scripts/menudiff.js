// Run in the UI page (scripts/fcgui.py made the reference): opens every menu, reads its entries
// (label, shortcut, data-cmd, checked, enabled, submenus) and compares them with FreeCAD's
// PartWorkbench menus (its Std menus) exported to out/fc-ref.png in the open project; resolves to
// the list of differences. Body of an async function: `await eval('(async()=>{' + code + '})()')`.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const key = (el, k) => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }))
const openMenus = () => [...document.querySelectorAll('[role=menu][data-state=open]')]
async function read(menu, depth) {
  const out = []
  for (const el of [...menu.children]) {
    const role = el.getAttribute('role')
    if (role === 'separator') { out.push({ sep: true }); continue }
    if (!role || !role.startsWith('menuitem')) continue
    const kbd = el.querySelector('.mb-kbd')?.textContent ?? '', lead = el.querySelector('.mb-ico')?.textContent ?? ''
    const label = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim()
    const isSub = kbd === '▸'
    const e = { label, kbd: isSub ? '' : kbd, cmd: el.getAttribute('data-cmd') || '', enabled: !el.hasAttribute('data-disabled'), checked: lead.includes('✓') }
    if (isSub && depth < 4) {
      const before = openMenus().length
      el.focus(); key(el, 'ArrowRight'); await sleep(150)
      const now = openMenus()
      if (now.length > before) { const sub = now[now.length - 1]; e.sub = await read(sub, depth + 1); key(sub, 'ArrowLeft'); await sleep(120) } else e.sub = []
    }
    out.push(e)
  }
  return out
}
while (openMenus().length) { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await sleep(100) }
const ours = {}
for (const t of [...document.querySelectorAll('[role=menubar] [role=menuitem]')]) {
  t.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))
  await sleep(250)
  const m = openMenus()[0]
  ours[t.textContent.trim()] = m ? await read(m, 0) : 'did not open'
  while (openMenus().length) { key(openMenus()[0], 'Escape'); document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await sleep(100) }
}
window.__ourMenus = ours
const fc = JSON.parse(await (await fetch(`/api/file?slug=${encodeURIComponent(location.hash.slice(1))}&path=out/fc-ref.png`)).text())
const norm = (s) => s.replace(/(\.\.\.|…)$/, '').trim().toLowerCase()
const rep = []
function cmp(path, F, O) {
  if (!Array.isArray(O)) { rep.push(`${path}: ours ${O}`); return }
  const fi = F.filter((e) => !e.sep), oi = O.filter((e) => !e.sep), used = new Set()
  const match = fi.map((f) => { const j = oi.findIndex((o, k) => !used.has(k) && ((o.cmd && o.cmd === f.cmd) || norm(o.label) === norm(f.label))); if (j >= 0) used.add(j); return j })
  fi.forEach((f, i) => {
    const j = match[i]
    if (j < 0) { rep.push(`${path}: missing "${f.label}" [${f.cmd}]${f.kbd ? ' ' + f.kbd : ''}`); return }
    const o = oi[j], d = []
    if (o.label !== f.label) d.push(`label "${o.label}" vs FreeCAD "${f.label}"`)
    if (o.kbd !== f.kbd) d.push(`key "${o.kbd}" vs "${f.kbd}"`)
    if (o.cmd && f.cmd && o.cmd !== f.cmd) d.push(`cmd ${o.cmd} vs ${f.cmd}`)
    if (d.length) rep.push(`${path}/${f.label}: ${d.join('; ')}`)
    if (f.sub) cmp(`${path}/${f.label}`, f.sub, o.sub ?? 'no submenu')
  })
  oi.forEach((o, k) => { if (!used.has(k)) rep.push(`${path}: extra "${o.label}"${o.cmd ? ' [' + o.cmd + ']' : ''}`) })
  const order = match.filter((j) => j >= 0)
  if (order.some((j, i) => i && j < order[i - 1])) rep.push(`${path}: order differs`)
  const sig = (L) => L.map((e) => (e.sep ? '|' : '•')).join('').replace(/^\|+|\|+$/g, '')
  if (sig(F) !== sig(O)) rep.push(`${path}: separators FreeCAD ${sig(F)} ours ${sig(O)}`)
}
for (const name of Object.keys(fc.menus)) if (name !== 'Part') cmp(name, fc.menus[name], ours[name] ?? 'absent')
return rep
