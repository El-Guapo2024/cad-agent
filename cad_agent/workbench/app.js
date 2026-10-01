// The workbench page. three-cad-viewer draws the model (tree, clipping,
// explode, measuring, camera); this file adds what it does not have: the
// project bar, the gate and activity panels, live reloads, and a drag handle
// whose moves are written to placements.toml through `cad place`.
import * as THREE from 'three';
import { TransformControls } from './vendor/TransformControls.js';
import { Viewer, Display, decodeInstancedFormat } from 'three-cad-viewer';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (x, n = 2) => (x == null || Number.isNaN(+x) ? '—' : (+x).toFixed(n));
const tokens = (s) => String(s || '').split(/[^A-Za-z0-9_]+/).filter(Boolean);
const V = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const DEG = Math.PI / 180;
const EXIT = { 0: 'OK', 1: 'FAIL', 2: 'UNCHECKED', 3: 'USAGE', 4: 'CRASH' };
const EXIT_CLS = { 0: 'pass', 1: 'fail', 2: 'warn', 3: 'na', 4: 'err' };
const STATE_CLS = { PASS: 'pass', FAIL: 'fail', UNCHECKED: 'warn', 'N/A': 'na' };
const BUSY_TEXT = { scene: 'building scene', check: 'checking', place: 'placing', set: 'saving', verify: 'verifying', measure: 'measuring', approve: 'approving' };
const TREE_W = 240;
const RENDER = { ambientIntensity: 1.0, directIntensity: 1.1, metalness: 0.3, roughness: 0.65,
                 edgeColor: 0x707070, defaultOpacity: 0.5, normalLen: 0 };

// ── server ───────────────────────────────────────────────────────────────────
async function http(method, path, body, params) {
  const url = params ? `${path}?${new URLSearchParams(params)}` : path;
  const opts = method === 'GET' ? {} : { method, headers: { 'Content-Type': 'application/json', 'X-CAD': '1' }, body: JSON.stringify(body || {}) };
  const r = await fetch(url, opts);
  const text = await r.text();
  let j;
  try { j = text ? JSON.parse(text) : {}; } catch { j = { error: text.slice(0, 300) }; }
  if (!r.ok) { const e = new Error(j.error || r.statusText); e.status = r.status; throw e; }
  return j;
}
const get = (p, params) => http('GET', p, null, params);
const post = (p, body) => http('POST', p, body);

const S = { projects: [], slug: null, scene: null, sceneHash: null, checks: null, status: null, log: [],
            busy: new Set(), tool: null, selected: null, undo: [], redo: [], placeRows: null, placeFor: null,
            loadingScene: false, pendingScene: false, rendered: false, snap: { on: true, mm: 1, deg: 15 } };
const store = {
  get(k, d) { try { const v = localStorage.getItem('cadwb.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('cadwb.' + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

// ── the viewer ───────────────────────────────────────────────────────────────
const host = $('#canvas');
const display = new Display(host, { cadWidth: host.clientWidth || 800, height: host.clientHeight || 600,
  treeWidth: TREE_W, glass: true, tools: true, theme: 'browser', pinning: false });
const viewer = new Viewer(display, { up: 'Z' }, (change) => onViewerChange(change));
// The viewer draws a margin, a frame and its toolbar around the canvas, so the
// canvas gets the space left inside them, measured (giving it the whole box
// cut off the bottom and the right edge).
function chrome(box, canvas) {
  const b = box.getBoundingClientRect(), c = canvas.getBoundingClientRect();
  const r = box.firstElementChild.getBoundingClientRect();
  const margin = r.left - b.left;                           // the same margin on the far side
  return { w: 2 * margin + (r.width - c.width), h: (c.top - b.top) + (r.bottom - c.bottom) + margin };
}
function fitView() {
  if (!S.rendered || !host.clientWidth) return;
  const x = chrome(host, viewer.renderer.domElement);
  viewer.resizeCadView(Math.max(200, Math.floor(host.clientWidth - x.w)), TREE_W,
                       Math.max(200, Math.floor(host.clientHeight - x.h)), true);
}
new ResizeObserver(fitView).observe(host);

function onViewerChange(change) {
  const pick = change.lastPick;                  // three-cad-viewer reports a double-click here
  if (pick && pick.new && pick.new.name && S.scene?.bodies.some((b) => b.name === pick.new.name)) select(pick.new.name);
}

function show(sc, keepView) {
  const cam = keepView && S.rendered ? viewer.getCameraLocationSettings() : null;
  const states = keepView && S.rendered ? viewer.getStates() : null;
  if (gizmo) gizmo.detach();
  if (S.rendered) viewer.clear();
  viewer.render(decodeInstancedFormat(sc.viewer), RENDER, { up: 'Z', ...(cam || {}) });
  S.rendered = true;
  // The viewer settles its own size a frame or two after render; fit after it.
  fitView();
  requestAnimationFrame(() => requestAnimationFrame(fitView));
  setTimeout(fitView, 300);
  if (!cam) viewer.presetCamera('iso');
  if (states) { try { viewer.setStates(states); } catch { /* a part came or went */ } }
  attachGizmo();
}

const groupOf = (name) => {
  const b = S.scene?.bodies.find((x) => x.name === name);
  return b ? viewer.nestedGroup?.groups?.[b.path] : null;
};

// ── the drag handle ──────────────────────────────────────────────────────────
let gizmo = null, drag = null;
function ensureGizmo() {
  const el = viewer.renderer.domElement;
  if (gizmo && gizmo.domElement === el) { gizmo.camera = viewer.camera.getCamera(); return gizmo; }
  if (gizmo) { gizmo.detach(); gizmo.dispose(); }
  gizmo = new TransformControls(viewer.camera.getCamera(), el);
  gizmo.setSpace('world');
  gizmo.size = 0.9;
  gizmo.addEventListener('change', () => viewer.update(true, false));
  gizmo.addEventListener('dragging-changed', (e) => {
    const c = viewer.controls;
    (c.controls || c).enabled = !e.value;
    if (e.value) dragStart(); else dragEnd();
  });
  gizmo.addEventListener('objectChange', dragging);
  return gizmo;
}

function attachGizmo() {
  const g = S.selected && S.tool && S.scene?.assembly ? groupOf(S.selected) : null;
  if (!g) { if (gizmo) { gizmo.detach(); viewer.update(true, false); } return; }
  const tc = ensureGizmo();
  tc.attach(g);
  tc.setMode(S.tool === 'move' ? 'translate' : 'rotate');
  tc.setRotationSnap(S.snap.on ? S.snap.deg * DEG : null);
  if (tc.getHelper().parent !== viewer.scene) viewer.scene.add(tc.getHelper());
  viewer.update(true, false);
}

// placements.toml: p' = R(p - about) + about + move, R = Rx·Ry·Rz (three's Euler XYZ)
function placementMatrix(p) {
  const R = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(p.turn[0] * DEG, p.turn[1] * DEG, p.turn[2] * DEG, 'XYZ'));
  const a = V(p.about);
  return R.setPosition(a.clone().add(V(p.move)).sub(a.clone().applyMatrix4(R)));
}
function toPlacement(P, about) {
  const R = new THREE.Matrix4().extractRotation(P);
  const e = new THREE.Euler().setFromRotationMatrix(R, 'XYZ');
  const move = new THREE.Vector3().setFromMatrixPosition(P).add(V(about).applyMatrix4(R)).sub(V(about));
  const q = (x) => Math.round(x * 1e4) / 1e4 || 0;
  return { move: [q(move.x), q(move.y), q(move.z)], turn: [q(e.x / DEG), q(e.y / DEG), q(e.z / DEG)], about: [...about] };
}
const isIdentity = (p) => !p || [...p.move, ...p.turn].every((v) => Math.abs(v) < 1e-6);
const current = (b) => b.placement || { move: [0, 0, 0], turn: [0, 0, 0], about: b.about };

function dragStart() {
  const b = S.scene.bodies.find((x) => x.name === S.selected), g = gizmo.object;
  g.updateMatrixWorld(true);
  drag = { b, g, m0: g.matrixWorld.clone(), start: g.position.clone(), before: current(b) };
}
function dragging() {
  if (!drag) return;
  const { g, start } = drag;
  if (S.snap.on && gizmo.mode === 'translate') {     // snap the change, not the absolute position
    const s = S.snap.mm, p = g.position;
    p.set(start.x + Math.round((p.x - start.x) / s) * s, start.y + Math.round((p.y - start.y) / s) * s,
          start.z + Math.round((p.z - start.z) / s) * s);
  }
  g.updateMatrixWorld(true);
  const d = new THREE.Vector3().setFromMatrixPosition(g.matrixWorld.clone().multiply(drag.m0.clone().invert()));
  const hud = $('#hud');
  hud.hidden = false;
  hud.textContent = gizmo.mode === 'translate'
    ? `${drag.b.name}   Δx ${fmt(d.x, 1)}   Δy ${fmt(d.y, 1)}   Δz ${fmt(d.z, 1)} mm`
    : `${drag.b.name}   rotating`;
}
function dragEnd() {
  $('#hud').hidden = true;
  if (!drag) return;
  const { b, g, m0, before } = drag;
  drag = null;
  g.updateMatrixWorld(true);
  const moved = g.matrixWorld.clone().multiply(m0.clone().invert());
  if (moved.equals(new THREE.Matrix4())) return;
  const after = toPlacement(moved.multiply(placementMatrix(before)), before.about);
  commit(b.name, before, after);
}

async function commit(name, before, after, { record = true } = {}) {
  const reset = isIdentity(after);
  if (record) { S.undo.push({ name, before, after }); S.redo = []; renderTools(); }
  try {
    const r = await post('/api/place', reset ? { slug: S.slug, body: name, reset: true } : { slug: S.slug, body: name, ...after });
    const d = r.data || {};
    if (r.exit > 1) throw new Error(d.error || EXIT[r.exit]);
    S.placeRows = d.rows || [];
    S.placeFor = name;
    const fails = S.placeRows.filter((x) => x.state === 'FAIL');
    if (fails.length) toast(`${name}: ${fails.map((f) => `${other(f.pair, name)}, ${f.detail}`).join('; ')}`, 'fail', 8000);
    else toast(reset ? `${name} is back where assembly.py puts it` : `${name} moved. Clear of every other body.`, 'ok');
    renderInspect();
  } catch (e) {
    toast(`Move not saved: ${e.message}`, 'fail', 8000);
    if (record) { S.undo.pop(); renderTools(); }
    loadScene({ force: true });                         // put the drawing back where the file says
  }
}
// Undo covers both kinds of edit: a hand move and a changed parameter.
function replay(u, back) {
  const [from, to] = back ? [u.after, u.before] : [u.before, u.after];
  if (u.kind === 'param') commitParam(u.part, u.key, from, to, { record: false });
  else commit(u.name, from, to, { record: false });
}
function undo() { const u = S.undo.pop(); if (!u) return toast('Nothing to undo'); S.redo.push(u); replay(u, true); renderTools(); }
function redo() { const u = S.redo.pop(); if (!u) return; S.undo.push(u); replay(u, false); renderTools(); }
function other(pair, name) { return tokens(pair).filter((t) => t !== 'vs' && t !== name)[0] || pair; }

function select(name) {
  S.selected = name;
  attachGizmo();
  renderInspect();
  switchTab('inspect');
}

// ── loading ──────────────────────────────────────────────────────────────────
async function loadProjects() {
  let r;
  try { r = await get('/api/projects'); } catch (e) { showOverlay(`The workbench server is not answering: ${e.message}`, false); return; }
  S.projects = r.projects;
  $('#project').innerHTML = S.projects.map((p) => `<option value="${esc(p.slug)}">${esc(p.slug)}</option>`).join('')
    + '<option value="__add">＋ Add projects folder…</option>';
  const want = [decodeURIComponent(location.hash.slice(1)), S.slug, store.get('slug', null),
                (S.projects.find((p) => p.assembly) || S.projects[0] || {}).slug].find((s) => s && S.projects.some((p) => p.slug === s));
  if (want) { $('#project').value = want; if (want !== S.slug) openProject(want); }
  else showOverlay('No projects here yet. Use "Add projects folder…" in the project menu.', false);
}

async function openProject(slug) {
  Object.assign(S, { slug, scene: null, sceneHash: null, checks: null, status: null, log: [], undo: [], redo: [],
                     selected: null, placeRows: null });
  store.set('slug', slug);
  history.replaceState(null, '', '#' + encodeURIComponent(slug));
  document.title = `${slug} · workbench`;
  renderAll();
  await Promise.all([loadScene({ fresh: true }), loadChecks(), loadStatus(), loadLog()]);
}

async function loadScene({ fresh = false, force = false } = {}) {
  if (S.loadingScene) { S.pendingScene = true; return; }
  S.loadingScene = true;
  const slug = S.slug;
  if (!S.scene) showOverlay('Building the scene. The first one starts the CAD kernel, about 30 seconds.', true);
  try {
    const sc = await get('/api/scene', { slug });
    if (slug !== S.slug) return;
    hideOverlay();
    $('#banner').hidden = true;
    if (fresh || force || sc.source_hash !== S.sceneHash) {
      S.scene = sc;
      S.sceneHash = sc.source_hash;
      if (S.selected && !sc.bodies.some((b) => b.name === S.selected)) S.selected = null;
      show(sc, !fresh);
      renderInspect(); renderTools();
    }
  } catch (e) {
    if (slug !== S.slug) return;
    if (S.scene) { $('#banner').hidden = false; $('#banner').textContent = `Rebuild failed, showing the last good scene. ${e.message}`; }
    else showOverlay(`${slug} did not build: ${e.message}`, false);
  } finally {
    S.loadingScene = false;
    if (S.pendingScene) { S.pendingScene = false; loadScene(); }
  }
}

async function loadChecks() { const slug = S.slug; let c = {}; try { c = await get('/api/checks', { slug }); } catch { c = {}; } if (slug === S.slug) { S.checks = c; renderChecks(); renderInspect(); } }
async function loadStatus() { const slug = S.slug; let st = null; try { st = await get('/api/status', { slug }); } catch { st = null; } if (slug === S.slug) { S.status = st; renderVerdict(); renderChecks(); } }
async function loadLog() { const slug = S.slug; let e = []; try { e = (await get('/api/log', { slug, limit: 300 })).entries; } catch { e = []; } if (slug === S.slug) { S.log = e.reverse(); renderActivity(); } }

// ── live events ──────────────────────────────────────────────────────────────
let designTimer = null;
function connect() {
  const es = new EventSource('/api/events');
  es.onopen = () => $('#live').classList.add('on');
  es.onerror = () => $('#live').classList.remove('on');
  es.onmessage = (m) => {
    let ev;
    try { ev = JSON.parse(m.data); } catch { return; }
    if (ev.type === 'projects') { loadProjects(); return; }
    if (ev.slug !== S.slug) return;
    if (ev.type === 'design') { clearTimeout(designTimer); designTimer = setTimeout(() => { loadScene(); loadStatus(); }, 250); }
    else if (ev.type === 'scene') { if (!S.loadingScene) loadScene(); }
    else if (ev.type === 'checks') loadChecks();
    else if (ev.type === 'verify') loadStatus();
    else if (ev.type === 'log') {
      S.log.unshift(...ev.entries.slice().reverse());
      S.log.length = Math.min(S.log.length, 500);
      renderActivity();
      if (!$('#tab-activity').classList.contains('on') && ev.entries.some((x) => x.cmd !== 'scene')) $('#actdot').hidden = false;
    } else if (ev.type === 'busy') { S.busy = new Set(ev.busy); renderBusy(); }
    else if (ev.type === 'checked') { S.placeRows = null; loadChecks(); loadStatus(); if (ev.exit > 2) toast(`Check could not run: ${ev.error || EXIT[ev.exit]}`, 'fail', 8000); }
    else if (ev.type === 'verifyed') { loadStatus(); loadChecks(); toast(ev.exit === 0 ? 'Verify: PASS' : `Verify: ${EXIT[ev.exit] || ev.exit}`, ev.exit === 0 ? 'ok' : 'warn', 6000); }
  };
}

// ── panels ───────────────────────────────────────────────────────────────────
const bodyNames = () => new Set((S.scene?.bodies || []).map((b) => b.name));
const rowBodies = (r) => { const n = bodyNames(); return [...new Set(tokens(r.subject || r.pair))].filter((t) => n.has(t)); };
const fileUrl = (path) => `/api/file?${new URLSearchParams({ slug: S.slug, path })}`;

function renderAll() { renderVerdict(); renderInspect(); renderChecks(); renderActivity(); renderTools(); renderBusy(); }

function renderVerdict() {
  const el = $('#verdict'), st = S.status;
  if (!st) { el.className = 'pill na'; el.textContent = '…'; return; }
  if (st.done) { el.className = 'pill done'; el.textContent = 'DONE'; el.title = `verified at ${st.commit || ''}`; return; }
  const v = st.verdict, stale = v && st.reasons.some((r) => !r.startsWith('the verdict was'));
  el.className = 'pill ' + (v ? STATE_CLS[v] || 'na' : 'na');
  el.textContent = v ? (stale ? `${v} · stale` : v) : 'NOT VERIFIED';
  el.title = st.reasons.join('\n');
}
function renderBusy() { $('#busy').innerHTML = [...S.busy].map((b) => `<span class="chip">${esc(BUSY_TEXT[b] || b)}</span>`).join(''); }
function renderTools() {
  $$('#tools button').forEach((b) => { b.classList.toggle('on', b.dataset.tool === S.tool); b.disabled = !S.scene?.assembly; });
  $('#undo').disabled = !S.undo.length;
  $('#redo').disabled = !S.redo.length;
  $('#snap').classList.toggle('on', S.snap.on);
}

function renderInspect() {
  const el = $('#tab-inspect'), sc = S.scene;
  if (!sc) { el.innerHTML = '<p class="muted">Loading the project…</p>'; return; }
  const b = sc.bodies.find((x) => x.name === S.selected);
  if (!b) {
    const size = sc.bbox ? sc.bbox[1].map((v, i) => v - sc.bbox[0][i]) : null;
    const env = sc.envelope?.max_mm, over = env && size && size.some((v, i) => v > env[i] + 1e-6);
    el.innerHTML = `<div class="card"><h3>${esc(sc.project)} <span class="badge">${sc.assembly ? 'assembly' : 'parts only'}</span></h3><dl class="kv">
      <dt>Bodies</dt><dd>${sc.bodies.length}</dd>
      <dt>Size</dt><dd>${size ? size.map((v) => fmt(v, 1)).join(' × ') + ' mm' : '—'}</dd>
      ${env ? `<dt>Envelope</dt><dd style="color:var(--${over ? 'fail' : 'pass'})">${env.join(' × ')} mm max${over ? ', exceeded' : ''}</dd>` : ''}
      <dt>Made parts</dt><dd>${fmt(sc.bodies.reduce((a, x) => a + (x.mass_g || 0), 0), 1)} g</dd>
      <dt>Axes</dt><dd>${sc.axes.length ? sc.axes.map((a) => esc(a.name)).join(', ') : 'none (static)'}</dd></dl>
      <p class="hint">Double-click a part to select it. With Move or Rotate on, drag its handle: the move is written to placements.toml and checked. The viewer's own toolbar does views, clipping, explode and measuring.</p></div>`;
    return;
  }
  const size = b.bbox[1].map((v, i) => v - b.bbox[0][i]), p = current(b);
  const rows = (S.checks?.rows || []).filter((r) => rowBodies(r).includes(b.name))
    .sort((x, y) => ({ FAIL: 0, UNCHECKED: 1, PASS: 2, 'N/A': 3 }[x.state] - { FAIL: 0, UNCHECKED: 1, PASS: 2, 'N/A': 3 }[y.state]));
  const placeRows = S.placeFor === b.name ? (S.placeRows || []) : [], fails = placeRows.filter((r) => r.state === 'FAIL');
  const xyz = (key, unit) => `<div class="xyz"><span>${key === 'move' ? 'Move' : 'Turn'}</span>${[0, 1, 2].map((i) =>
    `<input data-key="${key}" data-i="${i}" value="${fmt(p[key][i], key === 'move' ? 2 : 1)}" title="${'XYZ'[i]} ${unit}">`).join('')}</div>`;
  el.innerHTML = `<div class="card"><h3><span class="swatch" style="background:${esc(b.color)}"></span>${esc(b.name)} <span class="badge">${esc(b.kind)}</span></h3><dl class="kv">
      ${b.part ? `<dt>Part</dt><dd><code>parts/${esc(b.part)}.py</code></dd>` : ''}
      <dt>Material</dt><dd>${esc(b.material || '—')}</dd>
      <dt>Mass</dt><dd>${b.mass_g != null ? fmt(b.mass_g, 2) + ' g' : '—'}</dd>
      <dt>Size</dt><dd>${size.map((v) => fmt(v, 2)).join(' × ')} mm</dd></dl></div>
    ${paramsCard(b)}
    ${sc.assembly ? `<div class="card"><h3>Placement ${isIdentity(b.placement) ? '' : '<span class="badge" style="color:var(--accent)">moved</span>'}</h3>
      ${xyz('move', 'mm')}${xyz('turn', '°')}
      <div class="btnrow"><button class="btn" id="place-reset">Back to assembly.py</button></div>
      ${placeRows.length ? `<h4>Last move</h4>${fails.length ? `<ul class="fails">${fails.map((r) => `<li><span class="pill fail">FAIL</span>${esc(other(r.pair, b.name))}: ${esc(r.detail)}</li>`).join('')}</ul>` : '<p class="hint" style="color:var(--pass)">Clear of every other body.</p>'}` : ''}</div>` : ''}
    <div class="card"><h3>Gates <span class="count">${rows.length}</span></h3>${rows.length ? rows.map(checkRow).join('') : '<p class="hint">No check rows name this part yet.</p>'}</div>`;
}

// The part's PARAMS as fields: a change is written into the file by `cad set`.
function paramsCard(b) {
  const entries = Object.entries(b.params || {});
  if (!entries.length) return '';
  const others = (b.used_by || []).filter((n) => n !== b.name);
  const field = ([k, p]) => {
    if (!p.editable) return `<label class="param"><span>${esc(k)}</span><input disabled value="${esc(p.value)}" title="computed in the file"></label>`;
    if (p.type === 'bool') return `<label class="param"><span>${esc(k)}</span><input type="checkbox" data-param="${esc(k)}" ${p.value ? 'checked' : ''}></label>`;
    return `<label class="param"><span>${esc(k)}</span><input data-param="${esc(k)}" data-type="${p.type}" value="${esc(p.value)}"></label>`;
  };
  return `<div class="card"><h3>Parameters <span class="badge">parts/${esc(b.part)}.py</span></h3>
    ${others.length ? `<p class="hint">This part also makes ${others.map(esc).join(', ')}.</p>` : ''}
    <div class="params">${entries.map(field).join('')}</div>
    <p class="hint">Change a value and press Enter. It's written into the part's PARAMS, one line in git, after a check that the part still builds.</p></div>`;
}

async function commitParam(part, key, before, after, { record = true } = {}) {
  if (record) { S.undo.push({ kind: 'param', part, key, before, after }); S.redo = []; renderTools(); }
  try {
    const r = await post('/api/set', { slug: S.slug, part, values: { [key]: after } });
    const d = r.data || {};
    if (!d.changed) throw new Error(d.error || EXIT[r.exit]);
    const fails = d.failing || [];
    toast(`${part}.${key}: ${before} → ${after}${d.mass_g != null ? ` · ${fmt(d.mass_g, 1)} g` : ''}`
      + (fails.length ? ` · ${fails.length} part gate${fails.length > 1 ? 's' : ''} not passing` : ' · part gates pass'), fails.length ? 'warn' : 'ok', 6000);
  } catch (e) {
    toast(`Not saved: ${e.message}`, 'fail', 9000);
    if (record) { S.undo.pop(); renderTools(); }
    renderInspect();                                   // put the field back
  }
}

$('#tab-inspect').addEventListener('change', (e) => {
  const f = e.target.closest('[data-param]'), pb = S.scene?.bodies.find((x) => x.name === S.selected);
  if (!f || !pb) return;
  const p = pb.params[f.dataset.param];
  let v = f.type === 'checkbox' ? f.checked : f.value.trim();
  if (p.type === 'float' || p.type === 'int') {
    v = Number(v);
    if (!Number.isFinite(v) || (p.type === 'int' && !Number.isInteger(v))) { toast(`${f.dataset.param} needs a ${p.type === 'int' ? 'whole ' : ''}number`, 'fail'); renderInspect(); return; }
  }
  if (v === p.value) return;
  commitParam(pb.part, f.dataset.param, p.value, v);
});

$('#tab-inspect').addEventListener('change', (e) => {
  const inp = e.target.closest('.xyz input'), b = S.scene?.bodies.find((x) => x.name === S.selected);
  if (!inp || !b) return;
  const before = current(b), after = JSON.parse(JSON.stringify(before)), v = parseFloat(inp.value);
  if (Number.isNaN(v)) { renderInspect(); return; }
  after[inp.dataset.key][+inp.dataset.i] = v;
  commit(b.name, before, after);
});
$('#tab-inspect').addEventListener('click', (e) => {
  const b = S.scene?.bodies.find((x) => x.name === S.selected);
  if (e.target.id === 'place-reset' && b) {
    if (isIdentity(b.placement)) return toast(`${b.name} is already where assembly.py puts it.`);
    commit(b.name, current(b), null);
  }
});

function checkRow(r) {
  const idx = (S.checks?.rows || []).indexOf(r);
  const view = r.check === 'visual' && String(r.rule).startsWith('drift/') ? r.rule.split('/')[1] : null;
  const pngs = (r.artifacts || []).filter((a) => String(a).endsWith('.png'));
  const shots = view && !pngs.length ? [`out/${r.subject}_${view}.png`] : pngs;
  return `<div class="crow" data-row="${idx}"><span class="pill ${STATE_CLS[r.state] || 'na'}">${esc(r.state)}</span>
    <div><div class="crule">${esc(r.check ? r.check + '/' + r.rule : r.rule)} · <b>${esc(r.subject)}</b></div>
      <div class="cmeas">${esc(r.measured)}</div>
      ${r.limit && r.limit !== 'n/a' ? `<div class="climit">limit ${esc(r.limit)}${r.source ? ' · ' + esc(r.source) : ''}</div>` : r.source ? `<div class="climit">${esc(r.source)}</div>` : ''}
      ${view ? `<div class="thumbs">${shots.map((p) => `<img data-full="${esc(fileUrl(p))}" src="${esc(fileUrl(p))}" alt="">`).join('')}</div>` : ''}
      ${view && (r.state === 'UNCHECKED' || r.state === 'FAIL') ? `<button class="approve" data-part="${esc(r.subject)}" data-view="${esc(view)}">Approve this render…</button>` : ''}
    </div></div>`;
}

function renderChecks() {
  const el = $('#tab-checks'), c = S.checks || {}, rows = c.rows || [], st = S.status;
  const by = { FAIL: [], UNCHECKED: [], PASS: [], 'N/A': [] };
  rows.forEach((r) => (by[r.state] || by['N/A']).push(r));
  const open = by.FAIL.length + by.UNCHECKED.length;
  $('#checkcount').textContent = rows.length ? (open ? `${open}` : '✓') : '';
  const head = st ? `<div class="vc-top">${st.done ? '<span class="pill done">DONE</span>' : `<span class="pill ${st.verdict ? STATE_CLS[st.verdict] : 'na'}">${esc(st.verdict || 'NOT VERIFIED')}</span>`}
      <span class="muted small">${st.commit ? 'verified at ' + esc(st.commit.slice(0, 10)) : ''}</span></div>
      ${st.done ? '<p class="hint">cad done accepts this design.</p>' : `<ul class="reasons">${st.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`}` : '';
  el.innerHTML = `<div class="card">${head}
      <div class="vc-actions"><button id="run-check">Run checks</button><button id="run-verify">Verify</button></div>
      <div class="muted small">${c.written_utc ? `checks.json from ${new Date(c.written_utc).toLocaleString()}` : 'No checks.json yet'} · ${rows.length} rows</div></div>
    ${['FAIL', 'UNCHECKED', 'PASS', 'N/A'].map((k) => by[k].length ? `<details class="group" ${k === 'FAIL' || k === 'UNCHECKED' ? 'open' : ''}>
      <summary><span class="pill ${STATE_CLS[k]}">${k}</span> ${by[k].length}</summary>${by[k].map(checkRow).join('')}</details>` : '').join('')}`;
}

$('#right').addEventListener('click', async (e) => {
  const img = e.target.closest('.thumbs img');
  if (img) { $('#lightbox img').src = img.dataset.full; $('#lightbox').hidden = false; return; }
  const ap = e.target.closest('.approve');
  if (ap) {
    // Approval is a person's decision: only a click here sends it.
    if (!confirm(`Approve the current ${ap.dataset.view} render of ${ap.dataset.part} as the baseline?`)) return;
    try {
      const r = await post('/api/approve', { slug: S.slug, part: ap.dataset.part, view: ap.dataset.view });
      toast(r.exit === 0 ? `Approved ${ap.dataset.part} ${ap.dataset.view}` : `Approve failed: ${r.data?.error || EXIT[r.exit]}`, r.exit === 0 ? 'ok' : 'fail');
    } catch (err) { toast(`Approve failed: ${err.message}`, 'fail'); }
    return;
  }
  if (e.target.id === 'run-check') { post('/api/check', { slug: S.slug }).catch((err) => toast(err.message, 'fail')); return; }
  if (e.target.id === 'run-verify') { post('/api/verify', { slug: S.slug }).catch((err) => toast(err.message, 'fail')); return; }
  const row = e.target.closest('.crow');
  if (row) { const names = rowBodies((S.checks?.rows || [])[+row.dataset.row] || {}); if (names.length) select(names[0]); }
});
$('#lightbox').onclick = () => { $('#lightbox').hidden = true; };

function renderActivity() {
  const el = $('#tab-activity');
  const items = S.log.filter((e) => e.cmd !== 'scene').slice(0, 200);
  el.innerHTML = '<div class="act-head"><span>Every <code>cad</code> command, newest first</span></div>' + (items.length ? items.map((e) => {
    const argv = [];
    for (let i = 0, a = e.argv || []; i < a.length; i++) { if (a[i] === '--projects') i++; else if (a[i] !== '--json') argv.push(a[i]); }
    const pngs = (e.files || []).filter((f) => String(f).endsWith('.png')).slice(0, 4);
    return `<div class="act"><div class="act-top"><span class="pill ${EXIT_CLS[e.exit] || 'na'}">${esc(EXIT[e.exit] ?? e.exit)}</span><code>cad ${esc(argv.join(' '))}</code></div>
      ${e.summary ? `<div class="act-sum">${esc(e.summary)}</div>` : ''}<div class="act-meta">${e.t ? new Date(e.t).toLocaleTimeString() : ''} · ${fmt((e.ms || 0) / 1000, 1)} s</div>
      ${pngs.length ? `<div class="thumbs">${pngs.map((f) => `<img data-full="${esc(fileUrl(f))}" src="${esc(fileUrl(f))}" alt="">`).join('')}</div>` : ''}</div>`;
  }).join('') : '<p class="muted">Nothing yet. Commands the agent runs, and what you do here, show up as they happen.</p>');
}

// ── controls ─────────────────────────────────────────────────────────────────
$('#tools').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b || b.disabled) return;
  S.tool = S.tool === b.dataset.tool ? null : b.dataset.tool;
  if (S.tool && !S.selected) toast('Double-click a part to select it, then drag its handle.');
  attachGizmo(); renderTools();
});
function setSnap(on) {
  S.snap = { on, mm: parseFloat($('#snapmm').value) || 1, deg: parseFloat($('#snapdeg').value) || 15 };
  store.set('snap', S.snap);
  if (gizmo) gizmo.setRotationSnap(on ? S.snap.deg * DEG : null);
  renderTools();
}
$('#snap').onclick = () => setSnap(!S.snap.on);
$('#snapmm').onchange = $('#snapdeg').onchange = () => setSnap(S.snap.on);
$('#undo').onclick = undo;
$('#redo').onclick = redo;
$('#project').onchange = async (e) => {
  const v = e.target.value;
  if (v !== '__add') { openProject(v); return; }
  e.target.value = S.slug || '';
  const path = prompt('Folder that holds cad projects (each with a parts/ directory):');
  if (!path) return;
  try { const r = await post('/api/roots', { path }); toast(r.added ? 'Folder added' : 'Already listed, or not a folder', r.added ? 'ok' : 'warn'); loadProjects(); }
  catch (err) { toast(err.message, 'fail'); }
};
$('#toggle-right').onclick = () => { store.set('right', $('#main').classList.contains('no-right')); setPanels(); };
function setPanels() { $('#main').classList.toggle('no-right', !store.get('right', innerWidth > 860)); }
$$('.tabs button').forEach((b) => { b.onclick = () => switchTab(b.dataset.tab); });
function switchTab(t) {
  $$('.tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === t));
  $$('.tab').forEach((x) => x.classList.toggle('on', x.id === `tab-${t}`));
  if (t === 'activity') $('#actdot').hidden = true;
}
addEventListener('keydown', (e) => {                     // the viewer owns the other keys
  if (e.target.closest('input, select, textarea') || !(e.metaKey || e.ctrlKey)) return;
  const k = e.key.toLowerCase();
  if (k === 'z') { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
  else if (k === 'y') { e.preventDefault(); redo(); }
});

function toast(text, kind = '', ms = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = text;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), ms);
}
function showOverlay(text, spinning = true) { $('#overlay').hidden = false; $('#overlay').classList.toggle('static', !spinning); $('#overlay-text').textContent = text; }
function hideOverlay() { $('#overlay').hidden = true; }

const snap = store.get('snap', S.snap);
$('#snapmm').value = snap.mm; $('#snapdeg').value = snap.deg;
setSnap(snap.on);
setPanels();
addEventListener('resize', () => { setPanels(); requestAnimationFrame(fitView); });
renderAll();
loadProjects();
connect();
window.workbench = { viewer, state: S, select };   // for poking at it from the console
