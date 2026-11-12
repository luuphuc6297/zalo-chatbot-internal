/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type Plugin } from 'vite';

// Content-Security-Policy for the built console (file:// in Electron, or any static host).
// Only injected at build time: the dev server needs an inline React refresh preamble, and the
// Electron shell sets its own CSP header for the dev URL. Customer text is never rendered as HTML.
const BUILD_CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "connect-src 'self' http://127.0.0.1:8787 http://localhost:8787 https:",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
].join('; ');

function cspAtBuild(): Plugin {
  return {
    name: 'thomhouse-csp',
    apply: 'build',
    transformIndexHtml: () => [
      { tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: BUILD_CSP }, injectTo: 'head' },
    ],
  };
}

// base './' so Electron can load dist/index.html from file://.
// Dev: the console calls the API on its own origin and Vite proxies to the Worker, so no CORS is needed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const target = env.VITE_API_URL || 'http://127.0.0.1:8787';
  return {
    base: './',
    plugins: [react(), cspAtBuild()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { '/staff': target, '/health': target },
    },
    test: {
      environment: 'jsdom',
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
