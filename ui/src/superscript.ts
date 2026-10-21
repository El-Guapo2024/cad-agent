// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Base/UnitsApi.cpp: 2009 Jürgen Riegel
// UnitsApi::toUnicodeSuperscript (Base/UnitsApi.cpp at FreeCAD main 3160daf1e2b6, LGPL-2.1-or-later).
/** UnitsApi::toUnicodeSuperscript: "mm^2" as "mm²", "1/s^-1" as "1/s⁻¹". */
export function toUnicodeSuperscript(str: string): string {
  const sup = ['⁰', '¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹']
  let out = '', state: 'normal' | 'caret' | 'minus' | 'exp' = 'normal'
  for (const ch of str) {
    const digit = ch >= '0' && ch <= '9'
    if (state === 'normal') { if (ch === '^') state = 'caret'; else out += ch }
    else if (state === 'caret') {
      if (ch === '^') out += '^'
      else if (ch === '-') state = 'minus'
      else if (digit) { out += sup[+ch]; state = 'exp' }
      else { out += '^' + ch; state = 'normal' }
    } else if (state === 'minus') {
      if (digit) { out += '⁻' + sup[+ch]; state = 'exp' }
      else if (ch === '^') { out += '^-'; state = 'caret' }
      else { out += '^-' + ch; state = 'normal' }
    } else if (digit) out += sup[+ch]
    else if (ch === '^') state = 'caret'
    else { out += ch; state = 'normal' }
  }
  return out + (state === 'caret' ? '^' : state === 'minus' ? '^-' : '')
}
