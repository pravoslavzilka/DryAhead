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

// Vite's dev/preview servers only serve the static pages at /blue/ and
// /about/ and send /blue, /about to the dashboard; redirect so they work
// locally too. On Vercel, vercel.json's rewrites handle it.
const STATIC_PAGES = ['/blue', '/about']
function trailingSlashPlugin() {
  const redirect = (req, res, next) => {
    const [path, query] = req.url.split('?')
    if (!STATIC_PAGES.includes(path)) return next()
    res.statusCode = 301
    res.setHeader('Location', `${path}/${query ? `?${query}` : ''}`)
    res.end()
  }
  return {
    name: 'static-page-trailing-slash',
    configureServer: (server) => { server.middlewares.use(redirect) },
    configurePreviewServer: (server) => { server.middlewares.use(redirect) },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), siteUrlPlugin(), trailingSlashPlugin()],
  build: {
    rollupOptions: {
      // Three pages: the dashboard (/), the Blue Challenge presentation
      // (/blue/, Slovak) and the project about page (/about/, English). The
      // last two are static pages with their own small bundles and no
      // Supabase dependency, so they keep working if the backend is down.
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        blue: resolve(import.meta.dirname, 'blue/index.html'),
        about: resolve(import.meta.dirname, 'about/index.html'),
      },
    },
  },
})
