import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    open: true
  },
  build: {
    outDir: 'dist_admin',
    sourcemap: true,
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          antd: ['antd'],
          router: ['react-router-dom'],
          icons: ['react-icons'],
          charts: ['recharts'],
          utils: ['axios', 'date-fns', 'dayjs'],
          maps: ['@react-google-maps/api']
        },
        onwarn(warning, warn) {
          // Suppress dynamic import warnings for @react-google-maps/api
          if (warning.code === 'DYNAMIC_IMPORT') {
            return
          }
          if (warning.code === 'MODULE_LEVEL_DIRECTIVE') {
            return
          }
          warn(warning)
        }
      }
    }
  },
  base: './'
})
