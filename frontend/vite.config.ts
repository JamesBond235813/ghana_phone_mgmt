import { defineConfig } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

const certDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'certs')
const keyFile = path.join(certDir, 'localhost-key.pem')
const certFile = path.join(certDir, 'localhost.pem')
const hasHttpsCertificate = fs.existsSync(keyFile) && fs.existsSync(certFile)

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    https: hasHttpsCertificate ? { key: fs.readFileSync(keyFile), cert: fs.readFileSync(certFile) } : undefined,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      manifest: {
        name: '手机流转管理',
        short_name: '手机流转',
        description: '深圳—加纳二手手机流转管理系统',
        theme_color: '#0f766e',
        background_color: '#f5f7f6',
        display: 'standalone',
        lang: 'zh-CN',
        start_url: '/',
        icons: [{ src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml' }]
      }
    })
  ]
})
