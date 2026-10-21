// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/Navigation/NavigationStyle.cpp: 2008 Werner Mayer
//   src/Gui/NaviCube.cpp: 2017 Kustaa Nyholm; 2026 Joao Matos
// QApplication::doubleClickInterval(), which NavigationStyle::isDoubleClickCandidate, the button-combination styles (a
// quick click recentres the view) and the NaviCube's recentring click all ask for. Qt answers with the operating system's
// own setting: 500 ms by default on macOS (NSEvent.doubleClickInterval) and on Windows (GetDoubleClickTime), 400 ms on X11.
//
// A page cannot ask the system. It can see what the browser makes of it: a browser puts the OS's click count on each mouse
// press (`MouseEvent.detail`: 2 for a press that came within the OS's interval of the one before, at about the same spot).
// So the interval is at least as long as the longest gap between two presses the OS counted as a double click, and
// `doubleClickInterval()` is the platform's default, or a little over that gap when the gap is longer (a person who has set
// the system's double-click speed to slow gets a longer interval after the first slow double click). It never learns a
// shorter one from a press that was not counted: the browser's click count is also what a test's synthetic presses carry,
// and a shorter interval could only make a double click that Qt would have counted go unnoticed.
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const WIN = typeof navigator !== 'undefined' && /Win/.test(navigator.platform)
/** What Qt answers when the system has not been asked otherwise, in seconds. */
const DEFAULT = MAC || WIN ? 0.5 : 0.4
const DRAG_DISTANCE = 10 // QApplication::startDragDistance, px: a second press further away is no second click to the OS either
const FORGET = 3 // s: presses this far apart are never one double click

let longest = 0 // the longest gap, in seconds, between two presses the OS counted as a double click
let last: { t: number; x: number; y: number; button: number } | null = null

/** QApplication::doubleClickInterval(), in seconds. */
export function doubleClickInterval(): number {
  return Math.max(DEFAULT, longest * 1.1)
}

/** Learns from a mouse press: `detail` is the browser's click count for it. Call it for every `mousedown` on the view. */
export function observeMouseDown(e: { timeStamp: number; clientX: number; clientY: number; button: number; detail: number }) {
  const now = e.timeStamp / 1000, before = last
  last = { t: now, x: e.clientX, y: e.clientY, button: e.button }
  if (!before || before.button !== e.button || e.detail < 2) return
  const gap = now - before.t
  if (gap > 0 && gap <= FORGET && Math.hypot(e.clientX - before.x, e.clientY - before.y) <= DRAG_DISTANCE) longest = Math.max(longest, gap)
}

/** Forget what was learned (the tests). */
export function resetDoubleClickInterval() { longest = 0; last = null }
