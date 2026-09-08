import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { configDefaults } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    // Playwright specs live in e2e/ and run via `npm run e2e`, not vitest.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
