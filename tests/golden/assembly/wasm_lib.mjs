// SPDX-License-Identifier: LGPL-2.1-or-later
// The WebAssembly build of the assembly solver (ui/ondsel/dist), served to cad_agent/ondsel.py over stdin and
// stdout, one JSON request a line: {"fn": "ondsel_solve", "args": [...], "types": ["string"], "ret": "string"}
// answered by {"value": ...}. tests/test_assembly_golden.py runs the FreeCAD cases through it as through the
// native library, so the build the browser runs is held to FreeCAD too.
import { readFileSync } from 'node:fs'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dist = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'ui', 'ondsel', 'dist')
const { default: createOndsel } = await import(join(dist, 'ondsel.mjs'))
const m = await createOndsel({ wasmBinary: readFileSync(join(dist, 'ondsel.wasm')) })

const rl = createInterface({ input: process.stdin })
for await (const line of rl) {
  if (!line.trim()) continue
  let out
  try {
    const req = JSON.parse(line)
    out = { value: m.ccall(req.fn, req.ret, req.types, req.args) }
  } catch (e) {
    out = { crash: String(e) }
  }
  process.stdout.write(JSON.stringify(out) + '\n')
}
