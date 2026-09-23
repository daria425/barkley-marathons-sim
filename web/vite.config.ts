import { copyFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// maplibre-gl resolves its worker's URL at RUNTIME as
// `new URL('./' + (dev ? 'maplibre-gl-worker-dev.mjs' : 'maplibre-gl-worker.mjs'), import.meta.url)`
// — a dynamically-built string, not a literal Rollup can statically detect as an asset
// reference. So `vite build` never emits it into dist/assets/, the bundled chunk's
// import.meta.url points at .../assets/index-XXXX.js, and the worker 404s at
// .../assets/maplibre-gl-worker.mjs in production (falls back to serving index.html for that
// path, surfacing as a "non-JavaScript MIME type" module-script error). Copy it in verbatim,
// build-only — dev mode doesn't need this (see optimizeDeps.exclude below).
//
// The raw worker file has its own unresolved `import ... from "./maplibre-gl-shared.mjs"` —
// a real static import Rollup would normally handle, but since we're copying the worker file
// verbatim (unprocessed) rather than letting Rollup bundle it, that import stays unresolved
// too and needs the same verbatim-copy treatment. Confirmed maplibre-gl-shared.mjs has no
// further relative imports of its own (grepped its source) — these two files are the complete
// set, not a first guess.
const MAPLIBRE_ASSETS = ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']

function copyMaplibreWorker(): Plugin {
  return {
    name: 'copy-maplibre-gl-worker',
    apply: 'build',
    closeBundle() {
      const outDir = path.resolve(import.meta.dirname, 'dist/assets')
      mkdirSync(outDir, { recursive: true })
      for (const file of MAPLIBRE_ASSETS) {
        copyFileSync(
          path.resolve(import.meta.dirname, `node_modules/maplibre-gl/dist/${file}`),
          path.join(outDir, file),
        )
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), copyMaplibreWorker()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  // maplibre-gl ships a separate worker bundle (maplibre-gl-worker.mjs) that Vite's esbuild
  // dep-optimizer doesn't handle correctly — the worker fails to load and the map silently
  // never initializes (a blank canvas, no console error until you dig). Excluding it from
  // pre-bundling is the documented workaround.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
