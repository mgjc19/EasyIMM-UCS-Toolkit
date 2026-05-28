import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3100,
    proxy: {
      '/api': 'http://localhost:8200',
      '/ws': { target: 'ws://localhost:8200', ws: true },
    },
  },
})
