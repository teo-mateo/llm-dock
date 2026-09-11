import { useEffect, useId, useRef, useState } from 'react'
import useServicesSSE from '../../hooks/useServicesSSE'

// Per-conversation reasoning-level picker, rendered inside the composer.
//
// Renders nothing when the selected service declares no ladder: a control that
// can only ever be ignored is worse than no control. The ladder comes from the
// service payload, which is the same list the server validates against, so what
// is offered here is exactly what can reach the model.
//
// Read from the unfiltered service list, not the running-services one: the
// server accepts a level for a stopped service (that is what lets a level be
// saved before the model starts), so filtering by status here would hide the
// stored choice on precisely the conversations where it cannot be resent — and
// a cleared ladder would leave a stale value with no way to clear it.
//
// "Model default" is not the same choice as an "off" level. It stores null,
// which sends no reasoning field at all — the request an un-featured service
// makes. `off`, when a service declares it, actively instructs the model not to
// think. Levels are the model's own token names, shown verbatim and in the
// order the operator declared them.
//
// A custom listbox rather than a <select> because icons are the whole point of
// the control and native <option> elements cannot render them.

// Icons are derived from the level token, never hardcoded per service: the
// ladder is operator-declared, so any name can appear. Names are limited to
// icons in the free Font Awesome 6 set the app actually loads (6.5.1) —
// fa-gauge-low is the obvious pick for a low rung and is pro-only, so it renders
// an empty box.
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
  'Reasoning level. These are the model’s own level names, not token budgets: a '
  + 'level is an instruction to the model’s chat template, and how much it thinks '
  + 'is the model’s choice.'

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
    // Capture phase + stopPropagation: Escape with the list open should close
    // the list, not reach the conversation-level Escape handler (cancel run).
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

  // A stored level the service no longer declares is still shown (and still
  // will not be sent — the server drops it and says so on run_started). Hiding
  // it would make the conversation look like it was thinking, and would leave
  // the value with no way to clear it from here.
  const stale = !!value && !levels.some(l => l.id === value)
  // Nothing declared and nothing stored: the control could only ever be
  // ignored, so it stays out of the rail entirely.
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
        {/* Truncate rather than hide: narrow viewports are exactly where the
            current level matters most, and a hidden value leaves the control
            meaning nothing while still costing its width. */}
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
