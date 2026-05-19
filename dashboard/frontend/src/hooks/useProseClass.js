import { useTheme } from '../contexts/ThemeContext'

/**
 * Shared markdown/prose class helper (issue #5, owner note 6).
 *
 * `prose-invert` is the Tailwind Typography dark-on-light inversion and is
 * only correct in the dark theme. Rather than repeating
 * `theme === 'light' ? ... : ...` in every chat component that renders
 * markdown, call this hook: it returns the base `prose` class plus
 * `prose-invert` only in dark, with any extra modifiers appended.
 *
 *   const proseClass = useProseClass('prose-xs', 'max-w-none')
 *   <div className={proseClass}> … </div>
 */
export default function useProseClass(...extra) {
  const { theme } = useTheme()
  return [
    'prose',
    theme === 'light' ? null : 'prose-invert',
    ...extra,
  ].filter(Boolean).join(' ')
}
