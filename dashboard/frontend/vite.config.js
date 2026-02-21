import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/v2/', // url prefix for all assets
  server: {
    proxy: {
      '/api': 'http://localhost:5000'
    }
  }

})
