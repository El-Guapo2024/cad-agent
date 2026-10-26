// SPDX-License-Identifier: LGPL-2.1-or-later
// Types for ondsel.mjs, the Emscripten module ui/ondsel/build.sh wasm writes.
export default function createOndsel(options?: { locateFile?: (path: string) => string }): Promise<{
  ccall: (name: string, ret: string | null, types: string[], args: unknown[]) => unknown
}>
