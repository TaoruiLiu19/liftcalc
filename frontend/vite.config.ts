import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: './',
  plugins: [
    vue(),
    {
      name: 'local-cad-worker',
      generateBundle() {
        const worker = new URL(
          './node_modules/@mlightcad/cad-simple-viewer/dist/mtext-renderer-worker.js',
          import.meta.url,
        )
        this.emitFile({
          type: 'asset',
          fileName: 'assets/mtext-renderer-worker.js',
          source: readFileSync(worker),
        })
      },
    },
  ],
  build: {
    outDir: '../src/liftcalc/dusk_static',
    emptyOutDir: true,
    reportCompressedSize: false,
    license: { fileName: 'assets/THIRD-PARTY-LICENSES.md' },
  },
})
