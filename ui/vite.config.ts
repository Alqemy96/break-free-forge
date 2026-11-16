import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

// The production bundle lands where the Python server serves it from (docs/WEB_API.md, "Static").
const STATIC_DIR = fileURLToPath(new URL('../src/bl4forge/web/static', import.meta.url))

export default defineConfig(({ mode }) => {
  // Mock mode: `vite --mode mock` (reads .env.mock) or VITE_MOCK=1 in the environment.
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const mock = env.VITE_MOCK === '1' || process.env.VITE_MOCK === '1'

  return {
    base: '/',
    // A compile-time constant, so the production bundle drops the mock layer and its fixtures.
    define: { __BL4_MOCK__: JSON.stringify(mock) },
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      // `bl4forge serve` default bind. changeOrigin rewrites Host to 127.0.0.1:8734, which the
      // server's DNS-rebinding guard accepts.
      proxy: { '/api': { target: 'http://127.0.0.1:8734', changeOrigin: true } },
    },
    build: {
      outDir: STATIC_DIR,
      // Set BL4FORGE_UI_NO_EMPTY=1 only where deleting files is not allowed (stale assets stay).
      emptyOutDir: process.env.BL4FORGE_UI_NO_EMPTY !== '1',
      assetsDir: 'assets',
      target: 'es2022',
      sourcemap: false,
      chunkSizeWarningLimit: 700,
    },
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts'],
    },
  }
})
