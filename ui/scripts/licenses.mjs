// SPDX-License-Identifier: LGPL-2.1-or-later
// The notices of everything the production bundle includes, written next to it by the build.
//
// It is a Vite plugin (vite.config.ts uses it), so it reads the modules the bundler really put in each output chunk, not a
// guess from package.json: every npm package that has code or a style sheet in assets/ gets its licence text, as its authors
// ship it, in THIRD_PARTY_LICENSES.txt. It also puts ui/LICENSE and ui/NOTICE beside it (as LICENSE and NOTICE), so the
// folder carries its own terms when it is copied out of the repository. Nothing but node is needed, and nothing in the
// output depends on the time or the machine: the same bundle gives the same file.
//
// A package that ships no licence file stops the build unless FALLBACK has a text for it; a package whose licence file says
// something other than its package.json declares is flagged in the output, so a human looks at it.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

/** Published builds that already contain other packages' code (a bundle inside the package), which the bundler cannot see.
 *  three-cad-viewer's dist has postprocessing (Zlib) and n8ao inlined, besides three.js. */
export const INLINED = { 'three-cad-viewer': ['postprocessing', 'n8ao'] }

/** What a licence text of each declared kind contains, to catch a package whose licence file says something else. */
const SIGNATURE = {
  MIT: /Permission is hereby granted, free of charge/i,
  ISC: /Permission to use, copy, modify, and\/or distribute this software/i,
  '0BSD': /Permission to use, copy, modify, and\/or distribute this software/i,
  'BSD-2-Clause': /Redistributions in binary form must reproduce/i,
  'BSD-3-Clause': /Neither the name of/i,
  'Apache-2.0': /Apache License/i,
  Zlib: /provided 'as-is'/i,
}

const MIT = (holder) => `MIT License

Copyright (c) ${holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`

/** For a package that ships no licence file: the text its package.json declares, with the author it names as the holder
 *  (react-remove-scroll-bar says MIT and Anton Korzunov and ships no LICENSE). Marked as assembled in the output. */
const FALLBACK = { MIT }

const bar = '-'.repeat(78)

/** The package a module id belongs to: its folder and name, or null for our own sources. Vite and Rolldown put a few small
 *  helpers of their own in a bundle (the module preload polyfill, the module runtime), under ids that name them. */
function packageOf(id) {
  const clean = id.replace(/^\0/, '').split('?')[0]
  const own = /^(vite|rolldown)\//.exec(clean)
  if (own) return { name: own[1], dir: path.join(UI, 'node_modules', own[1]) }
  const marker = '/node_modules/'
  const at = clean.lastIndexOf(marker)
  if (at < 0) return null
  const parts = clean.slice(at + marker.length).split('/')
  const name = parts[0].startsWith('@') ? parts.slice(0, 2).join('/') : parts[0]
  return { name, dir: clean.slice(0, at + marker.length) + name }
}

const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'))

/** A repository field as a plain https URL. */
function repoUrl(repository) {
  const raw = typeof repository === 'string' ? repository : repository?.url
  if (!raw) return ''
  return raw.replace(/^git\+/, '').replace(/^git@github\.com:/, 'https://github.com/').replace(/^git:\/\//, 'https://').replace(/\.git$/, '')
}

/** The holder an author field names, without the e-mail address or the URL some carry. */
function holderOf(author) {
  const raw = typeof author === 'string' ? author : author?.name ?? ''
  return raw.replace(/<[^>]*>|\([^)]*\)/g, '').replace(/\s+/g, ' ').trim()
}

/** One package's record: version, declared licence, source, and the text of every licence or notice file it ships. */
function describe(name, dir, via) {
  const pkg = readJson(path.join(dir, 'package.json'))
  const declared = typeof pkg.license === 'string' ? pkg.license : pkg.license?.type ?? ''
  const files = fs.readdirSync(dir).filter((f) => /^(licen[cs]e|copying|notice)(\.[a-z]+)?$/i.test(f))
    .sort((a, b) => Number(/^notice/i.test(a)) - Number(/^notice/i.test(b)) || a.localeCompare(b))
  let texts = files.map((f) => ({ file: f, text: fs.readFileSync(path.join(dir, f), 'utf8').replace(/\r\n/g, '\n').trim() }))
  // Vite's file is its own MIT text followed by the licences of the dependencies it bundles (100 KB); only the first part is ours.
  texts = texts.map((t) => ({ ...t, text: t.text.split(/^# Licenses of bundled dependencies/m)[0].trim() }))
  const notes = []
  if (!texts.length) {
    const make = FALLBACK[declared]
    const holder = holderOf(pkg.author)
    if (!make || !holder) throw new Error(`licenses.mjs: ${name} ships no licence file, and FALLBACK has no text for "${declared}"; add its licence text here`)
    texts = [{ file: '(assembled)', text: make(holder) }]
    notes.push(`the package ships no licence file: this is the ${declared} text with the holder its package.json names (${holder})`)
  }
  const sig = SIGNATURE[declared]
  if (sig && !texts.some((t) => sig.test(t.text))) notes.push(`its package.json declares ${declared}, but the licence text it ships reads differently: compare the text below`)
  if (via) notes.push(`its code is inside the published build of ${via}, which the bundler includes as one module`)
  return { name, version: pkg.version, declared, source: repoUrl(pkg.repository) || pkg.homepage || '', texts, notes }
}

/** The packages with code or a style sheet in the bundle, sorted by name. */
export function bundledPackages(bundle) {
  const found = new Map()
  for (const out of Object.values(bundle)) {
    if (out.type !== 'chunk') continue
    for (const id of Object.keys(out.modules ?? {})) {
      const p = packageOf(id)
      if (p && !found.has(p.name)) found.set(p.name, { dir: p.dir, via: null })
    }
  }
  for (const [host, inner] of Object.entries(INLINED)) {
    if (!found.has(host)) continue
    for (const name of inner) {
      if (found.has(name)) continue
      const dir = path.join(path.dirname(found.get(host).dir), ...name.split('/'))
      if (!fs.existsSync(path.join(dir, 'package.json'))) throw new Error(`licenses.mjs: ${host} inlines ${name}, which is not installed next to it`)
      found.set(name, { dir, via: host })
    }
  }
  return [...found.entries()].sort(([a], [b]) => a.localeCompare(b, 'en')).map(([name, { dir, via }]) => describe(name, dir, via))
}

/** The text of THIRD_PARTY_LICENSES.txt. */
export function render(packages) {
  const out = []
  out.push('Third-party notices for the cad-agent workbench bundle', '='.repeat(54), '')
  out.push(`This folder is the build of ui/ (npm run build). The workbench itself is licensed under the GNU Lesser General Public
License, version 2.1 or (at your option) any later version (LICENSE in this folder), because it is ported from FreeCAD;
NOTICE names the FreeCAD files and authors it follows. The icons in freecad-icons/ are FreeCAD's, each under the licence
its own metadata states (freecad-icons/README.md).

The JavaScript and CSS in assets/ also contain the ${packages.length} npm packages below. This file is written by the build
(ui/scripts/licenses.mjs) from the modules the bundler included, with each package's licence text as its authors ship it.
`)
  out.push('Packages')
  for (const p of packages) out.push(`  ${p.name} ${p.version}  ${p.declared || '(no licence declared)'}`)
  for (const p of packages) {
    out.push('', bar, `${p.name} ${p.version}`, `  declared licence: ${p.declared || '(none)'}`)
    if (p.source) out.push(`  source: ${p.source}`)
    for (const n of p.notes) out.push(`  note: ${n}`)
    for (const t of p.texts) out.push('', ...(p.texts.length > 1 || t.file === '(assembled)' ? [`  [${t.file}]`] : []), t.text)
  }
  out.push('')
  return out.join('\n')
}

/** The Vite plugin: emits THIRD_PARTY_LICENSES.txt, LICENSE and NOTICE into the output folder. */
export function licenses() {
  return {
    name: 'cad-agent-licenses',
    apply: 'build',
    generateBundle(_options, bundle) {
      const source = render(bundledPackages(bundle))
      this.emitFile({ type: 'asset', fileName: 'THIRD_PARTY_LICENSES.txt', source })
      for (const f of ['LICENSE', 'NOTICE']) this.emitFile({ type: 'asset', fileName: f, source: fs.readFileSync(path.join(UI, f), 'utf8') })
    },
  }
}
