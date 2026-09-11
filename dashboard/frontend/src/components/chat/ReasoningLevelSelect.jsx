import { useEffect, useId, useRef, useState } from 'react'
import useServicesSSE from '../../hooks/useServicesSSE'

// Per-conversation reasoning-level picker, in the composer's control rail.
// Reads the unfiltered service list: the server accepts a level for a stopped
// service, so a status filter would hide the control on exactly the
// conversations that have one. Renders nothing with no ladder and nothing
// stored. A listbox rather than a <select> because the icons are the point and
// native <option> elements cannot render them.

// Icons keyed off the level token, since any name can be declared. Free Font
// Awesome 6.5.1 only — the natural fa-gauge-low is pro-only, so it renders empty.
const ICON_RULES = [
  [/^off$/, 'fa-ban'],
  [/^(minimal|low|lite|quick)$/, 'fa-feather'],
  [/^(medium|mid|balanced)$/, 'fa-gauge-simple'],
  [/^(high|deep)$/, 'fa-gauge'],
  [/^(xhigh|max|ultra)$/, 'fa-gauge-high'],
]
const FALLBACK_ICON = 'fa-brain'
const DEFAULT_ICON = 'fa-wand-magic-sparkles'
const STALE_ICON = 'fa-triangle-exclamation'
const LEVEL_HINT =
  'Reasoning level. These are the model’s own level names, not token budgets: '
  + 'a level is an instruction to the model’s chat template, and how much it '
  + 'thinks is the model’s choice.'

function iconFor(id) {
  for (const [re, icon] of ICON_RULES) {
    if (re.test(id)) return icon
  }
  return FALLBACK_ICON
}

export default function ReasoningLevelSelect({ mainService, value, onChange, disabled }) {
  const { services, loading } = useServicesSSE()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const rootRef = useRef(null)
  const triggerRef = useRef(null)
  const optionBase = useId()

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    // Capture phase + stopPropagation, so Escape closes the list instead of
    // reaching the conversation-level handler (cancel run).
    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown, true)
    }
  }, [open])

  if (loading || !onChange || !mainService) return null

  const service = (services || []).find(s => s.name === mainService)
  const levels = service?.reasoning_levels || []

  // A level the service stopped offering stays visible and clearable, though the
  // server will not send it.
  const stale = !!value && !levels.some(l => l.id === value)
  if (levels.length === 0 && !stale) return null

  const options = [
    { id: null, label: 'Model default', icon: DEFAULT_ICON, note: '' },
    ...levels.map(l => ({ id: l.id, label: l.id, icon: iconFor(l.id), note: '' })),
  ]
  if (stale) {
    options.push({ id: value, label: value, icon: STALE_ICON, note: 'not offered by this model' })
  }

  const selectedIndex = Math.max(0, options.findIndex(o => (o.id ?? null) === (value ?? null)))

  const openMenu = () => {
    setActive(selectedIndex)
    setOpen(true)
  }

  const choose = (option) => {
    onChange(option.id)
    setOpen(false)
    triggerRef.current?.focus()
  }

  const onTriggerKeyDown = (e) => {
    if (!open && ['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault()
      openMenu()
      return
    }
    if (!open) return
    const last = options.length - 1
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive(a => Math.min(a + 1, last))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive(a => Math.max(a - 1, 0))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setActive(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      setActive(last)
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault() // Space would otherwise also fire the button's click
      choose(options[active])
    }
  }

  const triggerIcon = stale ? STALE_ICON : (value ? iconFor(value) : DEFAULT_ICON)
  const triggerTitle = stale
    ? `${value} — not offered by this model, so it is not sent. ${LEVEL_HINT}`
    : `${LEVEL_HINT} Currently: ${value || 'model default'}.`

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        data-testid="reasoning-level-select"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Reasoning level: ${value || 'model default'}`}
        aria-activedescendant={open ? `${optionBase}-opt-${active}` : undefined}
        title={triggerTitle}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={onTriggerKeyDown}
        className={[
          'h-10 shrink-0 flex items-center gap-1.5 rounded-md border px-2.5 leading-none text-xs transition-colors',
          'bg-elevated border-hairline hover:border-accent hover:text-accent',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50',
          stale ? 'text-critique' : 'text-fg-muted',
        ].join(' ')}
      >
        <i className={`fa-solid ${triggerIcon}`} aria-hidden="true"></i>
        {/* Truncated, not hidden: the current level matters most on narrow
            viewports, exactly where hiding it would cost most. */}
        <span className="min-w-0 truncate max-w-[10ch] min-[420px]:max-w-[12ch]">{value || 'default'}</span>
        <i className="fa-solid fa-chevron-down text-[9px] opacity-60" aria-hidden="true"></i>
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label="Reasoning level"
          className="absolute right-0 bottom-[calc(100%+6px)] z-30 min-w-[186px] max-h-64 overflow-auto rounded-lg border border-border bg-surface shadow-lg py-1"
        >
          {options.map((o, i) => {
            const isSelected = (o.id ?? null) === (value ?? null)
            return (
              <li
                key={o.id ?? '__default__'}
                id={`${optionBase}-opt-${i}`}
                role="option"
                aria-selected={isSelected}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(o)}
                className={[
                  'flex items-center gap-2 px-3 py-2 text-xs cursor-pointer whitespace-nowrap',
                  active === i ? 'bg-accent/10 text-fg' : 'text-fg-muted',
                ].join(' ')}
              >
                <i className={`fa-solid ${o.icon} w-4 text-center`} aria-hidden="true"></i>
                <span>{o.label}</span>
                {o.note && <span className="text-fg-subtle text-[10px]">{o.note}</span>}
                {isSelected && (
                  <i className="fa-solid fa-check text-accent text-[10px] ml-auto" aria-hidden="true"></i>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
