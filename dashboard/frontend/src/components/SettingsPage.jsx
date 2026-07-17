import { useTheme } from '../contexts/ThemeContext'
import TOTPSetup from './TOTPSetup'

const THEMES = [
  { id: 'dark', icon: 'fa-moon', label: 'Dark' },
  { id: 'light', icon: 'fa-sun', label: 'Light' },
]

function ThemeCard() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="bg-surface border border-border rounded-lg p-6">
      <h2 className="text-lg font-medium text-fg mb-4">Appearance</h2>
      <div className="grid grid-cols-2 gap-3 max-w-xs">
        {THEMES.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTheme(t.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
              theme === t.id
                ? 'border-accent-strong bg-accent-strong/10 text-accent-fg-hover'
                : 'border-border hover:border-border-strong text-fg-muted hover:text-fg'
            }`}
          >
            <i className={`fa-solid ${t.icon} text-base`}></i>
            <span className="text-xs">{t.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  return (
    <div className="space-y-4 max-w-3xl">
      <div>
        <h1 className="text-xl text-fg">Settings</h1>
        <p className="text-sm text-fg-muted">
          Manage dashboard configuration and security.
        </p>
      </div>

      <ThemeCard />
      <TOTPSetup />
    </div>
  )
}
