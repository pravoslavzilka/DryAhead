import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Absolute site URL for Open Graph tags (social previews need absolute image
// URLs). Vercel sets VERCEL_PROJECT_PRODUCTION_URL at build time; VITE_SITE_URL
// overrides it. Without either, tags fall back to relative paths.
const siteUrl = process.env.VITE_SITE_URL
  ?? (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : '')

function siteUrlPlugin() {
  return {
    name: 'site-url',
    transformIndexHtml: (html) => html.replaceAll('__SITE_URL__', siteUrl),
  }
}

// Vite's dev/preview servers only serve the presentation at /blue/ and send
// /blue to the dashboard; redirect so /blue works locally too. On Vercel,
// vercel.json's rewrite handles it.
function blueSlashPlugin() {
  const redirect = (req, res, next) => {
    const [path, query] = req.url.split('?')
    if (path !== '/blue') return next()
    res.statusCode = 301
    res.setHeader('Location', `/blue/${query ? `?${query}` : ''}`)
    res.end()
  }
  return {
    name: 'blue-trailing-slash',
    configureServer: (server) => { server.middlewares.use(redirect) },
    configurePreviewServer: (server) => { server.middlewares.use(redirect) },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), siteUrlPlugin(), blueSlashPlugin()],
  build: {
    rollupOptions: {
      // Two pages: the dashboard (/) and the Blue Challenge presentation
      // (/blue/), a static page with its own small bundle and no Supabase
      // dependency, so it keeps working if the backend is down.
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        blue: resolve(import.meta.dirname, 'blue/index.html'),
      },
    },
  },
})
