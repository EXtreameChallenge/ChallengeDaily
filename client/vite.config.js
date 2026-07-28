import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/**
 * Vite 插件：移除构建产物中的 crossorigin 属性
 * 在 Electron file:// 协议下，crossorigin 属性会导致浏览器将本地文件视为跨域请求，
 * 从而阻断动态 import()（懒加载页面全部报 "Failed to fetch dynamically imported module"）
 */
function removeCrossorigin() {
  return {
    name: 'remove-crossorigin',
    transformIndexHtml(html) {
      return html
        .replace(/ crossorigin=""/g, '')
        .replace(/ crossorigin/g, '')
    }
  }
}

export default defineConfig({
  plugins: [react(), removeCrossorigin()],
  base: './',
  root: '.',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1000,
    // 禁用 modulepreload：在 Electron file:// 下预加载链接不可靠，
    // 且 preload 链也带 crossorigin 属性会引发同样问题
    modulePreload: false,
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        pet: path.resolve(__dirname, 'pet.html'),
      },
      output: {
        manualChunks: {
          // React 核心
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // Markdown 渲染 + recharts 图表
          'vendor-md-chart': ['react-markdown', 'remark-gfm', 'recharts'],
          // UI 图标
          'vendor-lucide': ['lucide-react'],
          // 日期处理
          'vendor-dayjs': ['dayjs'],
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
})
