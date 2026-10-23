// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   No copyright line in the file: src/Gui/Stylesheets/FreeCAD.qss
//   src/Gui/Action.cpp: 2004 Werner Mayer
// Global QToolTip-style tooltip layer. Every element in this app that sets a native `title`
// attribute (hundreds of call sites) currently gets the OS/browser's own tooltip bubble. FreeCAD
// uses Qt's QToolTip, styled by FreeCAD.qss (freecad.css has the CSS this renders with, under
// `.fc-tooltip`; this file only renders classes, it sets no inline colors). Rather than touching
// every call site, this module takes over `title` globally:
//
//   - one delegated listener set on `document` (capture phase, so a library that calls
//     stopPropagation — e.g. Radix's menus — can't hide events from us) tracks which element is
//     hovered;
//   - on hover, the element's `title` is moved to `data-fc-title` so the native tooltip never
//     gets a chance to show, and is moved back on hide so React's reconciliation of the `title`
//     prop keeps working (React only touches the DOM attribute when the prop value actually
//     changes, so leaving it stolen would desync it permanently);
//   - a single positioned <div> (.fc-tooltip, created lazily) is shown/moved/hidden instead.
//
// Timing and placement follow Qt (qtbase QApplication's SH_ToolTip_* style hints and
// QToolTip::showText):
//   - 700ms "wake up" delay before the first tooltip in a round shows;
//   - once shown, hopping to another tooltip-bearing element shows the next one instantly until
//     2000ms of no tooltip passes (the "fall asleep" delay);
//   - shown at the cursor position + (2, 16), nudged back on screen if it would overflow;
//   - plain text, line breaks preserved, long lines still wrap;
//   - auto-hides after 10000ms + 40ms per character beyond 100;
//   - hidden on leaving the element, mouse press, wheel/scroll, or a key press.
//
// A command's tooltip (a host with `data-tip-head`, chrome.tsx's toolbar buttons) is Action::createToolTip's rich
// text: the menu text in bold with the shortcut after it, the help text (its `title`), and the command's name in
// italics, as the real toolbars show it (fctips.ts has FreeCAD's texts).
//
// `.statusbar` (chrome.tsx's <StatusBar>) gets the QStatusBar QToolTip variant (thinner border, no
// padding override, slightly transparent) via the .fc-tooltip--statusbar modifier class.

const WAKE_UP_DELAY = 700
const FALL_ASLEEP_DELAY = 2000
const STOLEN_TITLE_ATTR = 'data-fc-title'
const HOST_SELECTOR = `[title], [${STOLEN_TITLE_ATTR}]`

let tooltipEl: HTMLDivElement | null = null
let currentHost: Element | null = null
let titleObserver: MutationObserver | null = null

let wakeTimer: ReturnType<typeof setTimeout> | null = null
let asleepTimer: ReturnType<typeof setTimeout> | null = null
let autoHideTimer: ReturnType<typeof setTimeout> | null = null
let warm = false

let cursorX = 0
let cursorY = 0
let started = false

function clearTimer(t: ReturnType<typeof setTimeout> | null) {
  if (t != null) clearTimeout(t)
}

function ensureTooltipEl(): HTMLDivElement {
  if (!tooltipEl) {
    tooltipEl = document.createElement('div')
    tooltipEl.className = 'fc-tooltip'
    tooltipEl.style.display = 'none'
    document.body.appendChild(tooltipEl)
  }
  return tooltipEl
}

/** The nearest element (self included) still carrying a live or stolen title, innermost wins. */
function findHost(el: Element): Element | null {
  return el.closest(HOST_SELECTOR)
}

/** Moves a live `title` into the stolen attribute (no-op if already stolen or empty/absent). */
function stealTitle(host: Element): string {
  const live = host.getAttribute('title')
  if (live) {
    host.setAttribute(STOLEN_TITLE_ATTR, live)
    host.removeAttribute('title')
    return live
  }
  return host.getAttribute(STOLEN_TITLE_ATTR) ?? ''
}

function restoreTitle(host: Element) {
  const stolen = host.getAttribute(STOLEN_TITLE_ATTR)
  if (stolen != null) {
    host.setAttribute('title', stolen)
    host.removeAttribute(STOLEN_TITLE_ATTR)
  }
}

function currentText(host: Element): string {
  return host.getAttribute(STOLEN_TITLE_ATTR) ?? ''
}

/** QFontMetrics(action->font()).horizontalAdvance: the width of `text` in the application font (body's). */
let measureCtx: CanvasRenderingContext2D | null = null
function advance(text: string): number {
  measureCtx ??= document.createElement('canvas').getContext('2d')
  if (!measureCtx) return 0
  measureCtx.font = getComputedStyle(document.body).font
  return measureCtx.measureText(text).width
}

/** Action::cleanTitle: a mnemonic's & dropped. */
export const cleanTitle = (title: string) => title.replace(/&(.)/g, '$1')

/** Action::createToolTip (Action.cpp 315-407): `<p style='white-space:pre; margin-bottom:0.5em;'><b>title</b> (shortcut)</p>`,
 *  the help text, and `<p style='white-space:pre; margin-top:0.5em;'><i>Std_Name</i></p>`. The help text is one
 *  non-wrapping paragraph when it is at most 400 px wide in the action's font; a longer one is cut at the first space
 *  after its first 400 px' worth of characters, and what follows wraps at the width the paragraphs above set
 *  (`.tt-rest`). Returns null when there is no title, and the tooltip is then the plain help text. */
export function commandToolTip(helpText: string, title: string, shortCut: string, cmdName: string): DocumentFragment | null {
  const text = cleanTitle(title)
  if (!text) return null
  const p = (cls: string, ...kids: (Node | string)[]) => { const e = document.createElement('p'); e.className = cls; e.append(...kids); return e }
  const el = (tag: string, s: string) => { const e = document.createElement(tag); e.textContent = s; return e }
  let help = helpText
  if (shortCut && help.endsWith(shortCut)) help = help.slice(0, help.length - shortCut.length)
  const shortcut = shortCut ? ` (${shortCut})` : ''
  const out = document.createDocumentFragment()
  out.append(p('tt-head', el('b', text), shortcut))
  const cmd = cmdName ? p('tt-cmd', el('i', cmdName)) : null
  if (!help || help === text || help === title) { if (cmd) out.append(cmd); return out }
  if (help.includes('\n')) out.append(p('tt-pre', help))
  else {
    const tipWidth = 400, width = advance(help)
    if (width <= tipWidth) out.append(p('tt-pre', help))
    else {
      let index = Math.trunc((tipWidth / width) * help.length)
      for (let i = 0; i < 50 && index < help.length; ++i, ++index) if (help[index] === ' ') break
      const rest = document.createElement('div')
      rest.className = 'tt-rest'
      rest.textContent = help.slice(index).trim()
      out.append(p('tt-pre', help.slice(0, index)), rest)
    }
  }
  if (cmd) out.append(cmd)
  return out
}

/** Fills the tooltip with the host's text: a command's rich tooltip, or the plain `title`. */
function fill(el: HTMLElement, host: Element, text: string) {
  const head = host.getAttribute('data-tip-head')
  const rich = head ? commandToolTip(text, head, host.getAttribute('data-tip-key') ?? '', host.getAttribute('data-tip-cmd') ?? '') : null
  el.classList.toggle('fc-tooltip--rich', !!rich)
  if (rich) el.replaceChildren(rich)
  else el.textContent = text
}

function isStatusBar(host: Element): boolean {
  return host.closest('.statusbar') != null
}

/** Watches only the currently-hovered host, so a React re-render that sets a fresh `title` while
 *  hovered is re-stolen immediately instead of flashing the native tooltip. One shared observer,
 *  re-targeted per hover — not a listener per element. */
function observeHost(host: Element) {
  if (!titleObserver) titleObserver = new MutationObserver(onHostTitleMutated)
  titleObserver.observe(host, { attributes: true, attributeFilter: ['title'] })
}

function onHostTitleMutated() {
  if (!currentHost) return
  const fresh = currentHost.getAttribute('title')
  if (fresh) {
    currentHost.setAttribute(STOLEN_TITLE_ATTR, fresh)
    currentHost.removeAttribute('title')
    if (tooltipEl && tooltipEl.style.display !== 'none') {
      fill(tooltipEl, currentHost, fresh)
      position()
      scheduleAutoHide(fresh)
    }
    // else: still waking up (or about to show warm) — show()/armShow() reads the attribute fresh.
  } else {
    // Title was cleared outright while hovered: nothing left to show.
    currentHost.removeAttribute(STOLEN_TITLE_ATTR)
    hide()
  }
}

function position() {
  if (!tooltipEl) return
  const margin = 2
  const w = tooltipEl.offsetWidth, h = tooltipEl.offsetHeight
  let x = cursorX + 2
  let y = cursorY + 16
  if (x + w + margin > window.innerWidth) x = window.innerWidth - w - margin
  if (x < margin) x = margin
  if (y + h + margin > window.innerHeight) y = cursorY - h - 2
  if (y < margin) y = margin
  tooltipEl.style.left = `${x}px`
  tooltipEl.style.top = `${y}px`
}

function scheduleAutoHide(text: string) {
  clearTimer(autoHideTimer)
  autoHideTimer = setTimeout(hide, 10000 + Math.max(0, text.length - 100) * 40)
}

function show(host: Element) {
  const text = currentText(host)
  if (!text) { hide(); return }
  const el = ensureTooltipEl()
  fill(el, host, text)
  el.classList.toggle('fc-tooltip--statusbar', isStatusBar(host))
  el.style.display = 'block'
  position()
  warm = true
  clearTimer(asleepTimer)
  asleepTimer = null
  scheduleAutoHide(text)
}

function armShow(host: Element) {
  clearTimer(wakeTimer)
  if (warm) { show(host); return }
  wakeTimer = setTimeout(() => { wakeTimer = null; show(host) }, WAKE_UP_DELAY)
}

function hide() {
  clearTimer(wakeTimer)
  wakeTimer = null
  clearTimer(autoHideTimer)
  autoHideTimer = null
  if (tooltipEl) tooltipEl.style.display = 'none'
  titleObserver?.disconnect()
  if (currentHost) restoreTitle(currentHost)
  currentHost = null
  if (warm) {
    clearTimer(asleepTimer)
    asleepTimer = setTimeout(() => { warm = false; asleepTimer = null }, FALL_ASLEEP_DELAY)
  }
}

function onMouseOver(e: MouseEvent) {
  if (!(e.target instanceof Element)) return
  const host = findHost(e.target)
  if (host === currentHost) return
  if (currentHost) hide()
  if (!host) return
  const text = stealTitle(host)
  if (!text) return
  currentHost = host
  observeHost(host)
  armShow(host)
}

/** Only acts on "left the window entirely" — moving between elements inside the document is
 *  already handled by onMouseOver recomputing the host (and no-oping when it hasn't changed, so
 *  hopping between two children of the same titled element doesn't flicker). Disabled buttons
 *  (and anything else the browser excludes from mouse hit-testing) simply never become `target`,
 *  so they fall out of this naturally — same as the native title tooltip today. */
function onMouseOut(e: MouseEvent) {
  const related = e.relatedTarget as Node | null
  if (!related || !document.contains(related)) hide()
}

function onMouseMove(e: MouseEvent) {
  cursorX = e.clientX
  cursorY = e.clientY
  if (tooltipEl && tooltipEl.style.display !== 'none') position()
}

function onForceHide() {
  if (currentHost || (tooltipEl && tooltipEl.style.display !== 'none')) hide()
}

/** Call once at startup (src/main.tsx). Idempotent. */
export function initTooltips() {
  if (started) return
  started = true
  document.addEventListener('mouseover', onMouseOver, true)
  document.addEventListener('mouseout', onMouseOut, true)
  document.addEventListener('mousemove', onMouseMove, true)
  document.addEventListener('mousedown', onForceHide, true)
  document.addEventListener('keydown', onForceHide, true)
  document.addEventListener('wheel', onForceHide, { capture: true, passive: true })
  document.addEventListener('scroll', onForceHide, { capture: true, passive: true })
}
