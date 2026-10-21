import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { licenses } from './scripts/licenses.mjs'

// The build lands inside the Python package, so `cad serve` hosts it at /next/
// and running it needs no Node. In dev, Vite proxies the API to the workbench
// service (CAD_API overrides where that is). The build also writes the licences of what it bundles (and LICENSE and NOTICE)
// next to the bundle: scripts/licenses.mjs.
const api = process.env.CAD_API ?? 'http://127.0.0.1:8733'

export default defineConfig({
  plugins: [react(), licenses()],
  base: './',
  build: { outDir: '../cad_agent/workbench/next', emptyOutDir: true, chunkSizeWarningLimit: 4000 },
  server: { port: Number(process.env.PORT) || 5173, proxy: { '/api': { target: api, changeOrigin: true } } },
})
