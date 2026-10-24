// SPDX-License-Identifier: LGPL-2.1-or-later
// Types for planegcs.mjs, the Emscripten module ui/planegcs/build.sh wasm writes.
export default function createPlaneGCS(options?: { locateFile?: (path: string) => string }): Promise<{
  ccall: (name: string, ret: string | null, types: string[], args: unknown[]) => unknown
}>
