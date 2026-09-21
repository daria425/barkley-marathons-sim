import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // maplibre-gl ships a separate worker bundle (maplibre-gl-worker.mjs) that Vite's esbuild
  // dep-optimizer doesn't handle correctly — the worker fails to load and the map silently
  // never initializes (a blank canvas, no console error until you dig). Excluding it from
  // pre-bundling is the documented workaround.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
