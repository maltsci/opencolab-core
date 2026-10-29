import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import viteLogFile from './plugins/vite-log-file'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), viteLogFile()],
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
