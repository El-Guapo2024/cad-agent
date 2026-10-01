// The review page: a snapshot of one project at one commit, written by
// `cad page`. three-cad-viewer draws the model with its own tree and tools;
// this file fills in the title block, the gates, the parts and the renders.
import { Viewer, Display, decodeInstancedFormat } from './three-cad-viewer.esm.min.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (x, n = 2) => (x == null || Number.isNaN(+x) ? '—' : (+x).toFixed(n));
const CLS = { PASS: 's-pass', FAIL: 's-fail', UNCHECKED: 's-warn', 'N/A': 's-na' };
const ORDER = { FAIL: 0, UNCHECKED: 1, PASS: 2, 'N/A': 3 };

const [data, scene] = await Promise.all([
  fetch('data.json').then((r) => r.json()),
  fetch('scene.json').then((r) => r.json()),
]);

// ── title block ──────────────────────────────────────────────────────────────
const st = data.status || {};
const verdict = st.done ? ['DONE', 's-pass'] : st.verdict ? [st.verdict, CLS[st.verdict] || 's-na'] : ['Not verified', 's-na'];
const commit = data.git?.commit ? data.git.commit.slice(0, 10) + (data.git.dirty ? ' + edits' : '') : 'no git';
$('#titleblock').innerHTML = `
  <div class="name"><span class="tb-label">Project</span><h1>${esc(data.title)}</h1></div>
  <div><span class="tb-label">Verdict</span><span class="verdict ${verdict[1]}">${esc(verdict[0])}</span></div>
  <div><span class="tb-label">Commit</span><span class="tb-value">${esc(commit)}</span></div>
  <div><span class="tb-label">Verified</span><span class="tb-value">${st.verified_utc ? esc(st.verified_utc.replace('T', ' ').replace('Z', ' UTC')) : 'never'}</span></div>
  <div><span class="tb-label">Units · bodies</span><span class="tb-value">mm · ${scene.bodies.length}</span></div>`;
const reasons = $('#reasons');
reasons.hidden = false;
if (st.done) {
  reasons.className = 'reasons done';
  reasons.innerHTML = '<li><code>cad done</code> accepts this design: a fresh PASS on committed work.</li>';
} else {
  reasons.innerHTML = (st.reasons || ['no verdict recorded']).map((r) => `<li>${esc(r)}</li>`).join('');
}

// ── gates, parts, renders ────────────────────────────────────────────────────
const rows = (data.rows || []).slice().sort((a, b) => (ORDER[a.state] ?? 9) - (ORDER[b.state] ?? 9));
const row = (r) => `<tr><td class="state ${CLS[r.state] || ''}">${esc(r.state)}</td>
  <td><code>${esc(r.check ? r.check + '/' + r.rule : r.rule)}</code><span class="src">${esc(r.subject)}</span></td>
  <td><span class="num">${esc(r.measured)}</span>${r.limit && r.limit !== 'n/a' ? `<span class="src">limit ${esc(r.limit)}</span>` : ''}</td></tr>`;
const open = rows.filter((r) => r.state === 'FAIL' || r.state === 'UNCHECKED');
const rest = rows.filter((r) => !(r.state === 'FAIL' || r.state === 'UNCHECKED'));
const head = '<thead><tr><th>State</th><th>Gate</th><th>Measured</th></tr></thead>';
$('#gates').innerHTML = rows.length ? `
  ${open.length ? `<div class="table"><table>${head}<tbody>${open.map(row).join('')}</tbody></table></div>` : '<p class="s-pass">Every gate passes or does not apply.</p>'}
  ${rest.length ? `<details><summary>${rest.length} passing or not applicable</summary><div class="table"><table>${head}<tbody>${rest.map(row).join('')}</tbody></table></div></details>` : ''}`
  : '<p class="muted">No checks were run for this snapshot.</p>';

$('#parts').innerHTML = scene.bodies.map((b) => {
  const size = b.bbox[1].map((v, i) => v - b.bbox[0][i]);
  return `<tr><td><span class="swatch" style="background:${esc(b.color)}"></span>${esc(b.name)}
      ${b.placement ? '<span class="src">moved by hand (placements.toml)</span>' : ''}</td>
    <td>${esc(b.material || b.kind)}</td><td class="num">${b.mass_g != null ? fmt(b.mass_g, 1) + ' g' : '—'}</td>
    <td class="num">${size.map((v) => fmt(v, 1)).join(' × ')}</td></tr>`;
}).join('');

const shots = data.renders || [];
$('#render-section').hidden = !shots.length;
$('#renders').innerHTML = shots.map((r) => `<figure><img src="${esc(r.current || r.approved)}" alt="${esc(r.subject)} ${esc(r.view)} render" loading="lazy">
  <figcaption><span>${esc(r.subject)} · ${esc(r.view)}</span><span class="${r.approved ? 's-pass' : 's-warn'}">${r.approved ? 'approved' : 'not approved'}</span></figcaption></figure>`).join('');

$('#foot').innerHTML = `Written by <code>cad page</code> on ${esc(data.generated_utc.replace('T', ' ').replace('Z', ' UTC'))}.
  A snapshot, not a live view: the design lives in git, and <code>cad verify</code> decides when it is done.`;

// ── the model ────────────────────────────────────────────────────────────────
const box = $('#view');
const size = () => [box.clientWidth || 600, box.clientHeight || 400];
const [w, h] = size();
const display = new Display(box, { cadWidth: w, height: h, treeWidth: 200, glass: true, tools: true, theme: 'browser', pinning: false });
const viewer = new Viewer(display, { up: 'Z' }, () => {});
viewer.render(decodeInstancedFormat(scene.viewer), { ambientIntensity: 1, directIntensity: 1.1, metalness: 0.3,
  roughness: 0.65, edgeColor: 0x707070, defaultOpacity: 0.5, normalLen: 0 }, { up: 'Z' });
// The viewer draws a margin, a frame and its toolbar around the canvas: give
// the canvas the space left inside them.
const fit = () => {
  const b = box.getBoundingClientRect(), c = viewer.renderer.domElement.getBoundingClientRect();
  const r = box.firstElementChild.getBoundingClientRect(), margin = r.left - b.left;
  const [cw, ch] = size();
  viewer.resizeCadView(Math.max(200, Math.floor(cw - 2 * margin - (r.width - c.width))), 200,
                       Math.max(200, Math.floor(ch - (c.top - b.top) - (r.bottom - c.bottom) - margin)), true);
};
fit();
requestAnimationFrame(() => requestAnimationFrame(fit));   // the viewer settles its size after render
setTimeout(fit, 300);
viewer.presetCamera('iso');
new ResizeObserver(fit).observe(box);
