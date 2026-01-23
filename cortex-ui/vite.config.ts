import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  envDir: '..',
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: {
      '/agents': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/multi/ws': {
        target: 'ws://localhost:8001',
        ws: true,
      },
      '/single/ws': {
        target: 'ws://localhost:8001',
        ws: true,
      },
    },
  },
})
