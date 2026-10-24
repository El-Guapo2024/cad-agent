// SPDX-License-Identifier: LGPL-2.1-or-later
// The page's way to the sketch kernel (sketchkernel.ts): `cad feature sketchkernel` through POST /api/cad, in the
// project in the page.
import { api, resultText } from './api'
import { getState } from './store'
import { setKernelFetch, type KAnswer } from './sketchkernel'

setKernelFetch(async (reqs) => {
  const slug = getState().slug
  if (!slug) throw new Error('no project for the sketch kernel')
  const r = await api.cad(slug, ['feature', 'sketchkernel', slug, '--req', JSON.stringify(reqs)])
  if (r.exit !== 0 || !r.data) throw new Error(`sketch kernel: ${resultText(r)}`)
  return (r.data.answers ?? []) as KAnswer[]
})
