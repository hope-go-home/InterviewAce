import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        ws: true,                                  // 支持 WebSocket（实时语音）
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
