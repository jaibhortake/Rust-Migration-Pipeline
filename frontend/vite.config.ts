import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5280, strictPort: true, proxy: { '/api': { target: 'http://127.0.0.1:8280', ws: true, changeOrigin: true } } },
})
