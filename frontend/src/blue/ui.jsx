import { useEffect, useRef, useState } from 'react'

export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

/** True once the element has entered the viewport (stays true). */
export function useInView(options = { rootMargin: '0px 0px -10% 0px' }) {
  const ref = useRef(null)
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || inView) return
    if (!('IntersectionObserver' in window)) { setInView(true); return }
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setInView(true); io.disconnect() }
    }, options)
    io.observe(el)
    return () => io.disconnect()
  }, [inView]) // eslint-disable-line react-hooks/exhaustive-deps
  return [ref, inView]
}

/** Width of an element in CSS px, tracked with ResizeObserver. */
export function useWidth(fallback = 640) {
  const ref = useRef(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

export function Reveal({ as: Tag = 'div', className = '', children, ...rest }) {
  const [ref, inView] = useInView()
  return (
    <Tag ref={ref} className={`reveal ${inView ? 'in' : ''} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

/** Number that counts up when it scrolls into view. `decimals` uses a Slovak comma. */
export function Counter({ to, decimals = 0, prefix = '', suffix = '', duration = 1400 }) {
  const [ref, inView] = useInView()
  const reduced = useReducedMotion()
  const [value, setValue] = useState(reduced ? to : 0)
  useEffect(() => {
    if (!inView) return
    if (reduced) { setValue(to); return }
    let raf
    const start = performance.now()
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration)
      setValue(to * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [inView, reduced, to, duration])
  const text = value.toFixed(decimals).replace('.', ',')
  return (
    <span ref={ref}>
      <span className="visually-hidden">{prefix}{to.toFixed(decimals).replace('.', ',')}{suffix}</span>
      <span aria-hidden="true">{prefix}{text}{suffix}</span>
    </span>
  )
}

export function Source({ href, children }) {
  return (
    <span className="source">
      Zdroj: <a href={href} target="_blank" rel="noopener noreferrer">{children ?? new URL(href).hostname.replace('www.', '')}</a>
    </span>
  )
}

/** Visible placeholder for data the author still has to fill in. */
export function Fill({ children }) {
  return <span className="fill">[DOPLNIŤ: {children}]</span>
}

export function ThemeToggle() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? null)
  const systemDark = typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
  const dark = theme ? theme === 'dark' : systemDark
  const toggle = () => {
    const next = dark ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    try { localStorage.setItem('dryahead-theme', next) } catch { /* private mode */ }
    setTheme(next)
  }
  return (
    <button className="icon-btn" onClick={toggle} aria-label={dark ? 'Prepnúť na svetlý režim' : 'Prepnúť na tmavý režim'}>
      {dark ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" strokeLinecap="round" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  )
}

export function fmtDate(iso, opts = { day: 'numeric', month: 'numeric' }) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('sk-SK', opts)
}
