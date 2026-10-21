// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   No copyright line in the file: src/Gui/Stylesheets/FreeCAD.qss
// QSlider::sub-page (FreeCAD.qss): the groove left of the handle is AccentColor. WebKit has no
// pseudo-element for that part, so every range input carries its filled fraction as --fill.
function sync(el: HTMLInputElement) {
  const min = Number(el.min || 0), max = Number(el.max || 100), v = Number(el.value)
  el.style.setProperty('--fill', `${max > min ? ((v - min) / (max - min)) * 100 : 0}%`)
}
const all = () => document.querySelectorAll<HTMLInputElement>('input[type=range]').forEach(sync)

export function initSliders() {
  document.addEventListener('input', (e) => { const t = e.target as HTMLInputElement; if (t?.type === 'range') sync(t) }, true)
  // Ranges React renders or re-values (a panel opening, a setting loaded) — not only user drags.
  let queued = false
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; all() }) } })
    .observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['value'] })
  all()
}
