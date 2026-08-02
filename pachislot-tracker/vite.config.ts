import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  base: '/smart_apps/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: 'パチスロ収支管理',
        short_name: '収支管理',
        description: 'パチスロの収支をカレンダーで記録するアプリ',
        lang: 'ja',
        start_url: '/smart_apps/',
        scope: '/smart_apps/',
        display: 'standalone',
        background_color: '#f6f2ea',
        theme_color: '#3f8fa0',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
})
