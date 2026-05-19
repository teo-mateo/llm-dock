/* eslint-disable react-refresh/only-export-components --
   Context module intentionally co-exports the provider component, the
   useTheme hook, and AVAILABLE_THEMES. Splitting them would scatter the
   theme API; the rule only affects dev-time Fast Refresh granularity. */
import { createContext, useContext, useEffect, useState, useCallback } from 'react'

const STORAGE_KEY = 'dashboard_theme'
export const AVAILABLE_THEMES = ['dark', 'light']
const DEFAULT_THEME = 'dark'

// OS following is FIRST-LOAD-ONLY (issue #5, owner decision): prefers-color-
// scheme picks the initial theme only when the user has no stored override.
// Once the user picks a theme explicitly it is persisted and the OS is no
// longer followed. There is intentionally no "system" entry in
// AVAILABLE_THEMES; clearing localStorage restores OS-following on next load.
function osTheme() {
  try {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  } catch {
    return DEFAULT_THEME
  }
}

function readUserOverride() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return AVAILABLE_THEMES.includes(v) ? v : null
  } catch {
    return null
  }
}

function resolveInitial() {
  const override = readUserOverride()
  if (override) return override
  if (typeof document !== 'undefined') {
    const fromDom = document.documentElement.dataset.theme
    if (fromDom && AVAILABLE_THEMES.includes(fromDom)) return fromDom
  }
  return osTheme()
}

const ThemeContext = createContext({
  theme: DEFAULT_THEME,
  setTheme: () => {},
  cycleTheme: () => {},
  themes: AVAILABLE_THEMES,
})

function applyThemeToDom(next) {
  const root = document.documentElement
  root.classList.add('theme-swap-no-transitions')
  root.dataset.theme = next
  root.style.colorScheme = next
  void root.offsetHeight // force reflow so the no-transition frame takes effect
  requestAnimationFrame(() => {
    root.classList.remove('theme-swap-no-transitions')
  })
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(resolveInitial)

  // Authoritative on mount: re-assert the resolved theme even if the
  // inline anti-FOUC script failed or was changed (owner note 4).
  useEffect(() => {
    applyThemeToDom(theme)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setTheme = useCallback((next) => {
    if (!AVAILABLE_THEMES.includes(next)) return
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* ignore */ }
    applyThemeToDom(next)
    setThemeState(next)
  }, [])

  const cycleTheme = useCallback(() => {
    setThemeState((cur) => {
      const i = AVAILABLE_THEMES.indexOf(cur)
      const next = AVAILABLE_THEMES[(i + 1) % AVAILABLE_THEMES.length]
      try { localStorage.setItem(STORAGE_KEY, next) } catch { /* ignore */ }
      applyThemeToDom(next)
      return next
    })
  }, [])

  // Follow the OS only while the user has NOT chosen explicitly.
  useEffect(() => {
    if (readUserOverride()) return
    const mql = window.matchMedia('(prefers-color-scheme: light)')
    const handler = (e) => {
      if (readUserOverride()) return
      const next = e.matches ? 'light' : 'dark'
      applyThemeToDom(next)
      setThemeState(next)
    }
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, cycleTheme, themes: AVAILABLE_THEMES }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
