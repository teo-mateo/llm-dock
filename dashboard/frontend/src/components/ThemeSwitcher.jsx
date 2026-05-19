import { useTheme } from '../contexts/ThemeContext'

const META = {
  dark:  { icon: 'fa-moon', label: 'Dark' },
  light: { icon: 'fa-sun',  label: 'Light' },
}

// Generic over the themes array: cycles for ≤2, renders a <select> for 3+.
// Adding a third theme needs zero JSX edits here.
export default function ThemeSwitcher() {
  const { theme, setTheme, themes } = useTheme()

  if (themes.length <= 2) {
    const next = themes[(themes.indexOf(theme) + 1) % themes.length]
    return (
      <button
        type="button"
        onClick={() => setTheme(next)}
        className="text-fg-subtle hover:text-fg-muted px-2 py-1 rounded transition-colors"
        title={`Switch to ${META[next]?.label || next} theme`}
        aria-label={`Switch to ${META[next]?.label || next} theme`}
      >
        <i className={`fa-solid ${META[theme]?.icon || 'fa-circle-half-stroke'} text-xs`}></i>
      </button>
    )
  }

  return (
    <select
      value={theme}
      onChange={(e) => setTheme(e.target.value)}
      className="bg-surface border border-border text-fg text-xs rounded px-2 py-1"
      aria-label="Theme"
    >
      {themes.map((t) => (
        <option key={t} value={t}>{META[t]?.label || t}</option>
      ))}
    </select>
  )
}
