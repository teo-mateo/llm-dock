import { useState, useMemo, useCallback, useRef } from 'react'

function ParamTooltip({ html, tipRef, tipPos }) {
  return (
    <div
      ref={tipRef}
      style={tipPos ? { top: tipPos.top, left: tipPos.left } : undefined}
      className="fixed w-[280px] bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-slate-300 leading-relaxed shadow-[0_4px_20px_rgba(0,0,0,0.4)] z-[9999] opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none [&_b]:text-white [&_b]:font-semibold [&_code]:text-blue-300 [&_code]:bg-slate-700 [&_code]:px-1 [&_code]:rounded"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function ParamRow({ f, alreadyAdded, onAddFlag }) {
  const rowRef = useRef(null)
  const tipRef = useRef(null)
  const [tipPos, setTipPos] = useState(null)

  const handleMouseEnter = useCallback(() => {
    const row = rowRef.current
    if (!row) return
    const rect = row.getBoundingClientRect()
    const tipHeight = tipRef.current?.offsetHeight || 120
    const top = rect.top - tipHeight - 8 < 0
      ? rect.bottom + 8
      : rect.top - tipHeight - 8
    setTipPos({ top, left: rect.left })
  }, [])

  const cliFlag = f.cli || ''
  return (
    <div
      ref={rowRef}
      onMouseEnter={f.tip ? handleMouseEnter : undefined}
      onClick={() => !alreadyAdded && onAddFlag(cliFlag, f.default || '')}
      className={`group rounded mx-1 px-2 py-1.5 transition-colors ${
        alreadyAdded
          ? 'cursor-default'
          : 'hover:bg-gray-700/50 cursor-pointer'
      }`}
      title={!f.tip ? (alreadyAdded ? 'Already in parameters' : `Click to add ${cliFlag}`) : undefined}
    >
      <div className={alreadyAdded ? 'opacity-40' : ''}>
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-yellow-400 font-mono font-semibold">{cliFlag}</span>
          {f.default != null && f.default !== '' && (
            <span className="text-gray-600 ml-auto whitespace-nowrap">{f.default}</span>
          )}
        </div>
        <div className="text-gray-400 text-xs leading-snug mt-0.5">
          {f.description}
        </div>
      </div>
      {f.tip && <ParamTooltip tipRef={tipRef} html={f.tip} tipPos={tipPos} />}
    </div>
  )
}

function categorizeFlags(flagMetadata) {
  if (!flagMetadata) return []

  const grouped = {}
  for (const [key, meta] of Object.entries(flagMetadata)) {
    const category = meta.category || 'Other'
    if (!grouped[category]) grouped[category] = []
    grouped[category].push({ key, ...meta })
  }

  return Object.entries(grouped).map(([cat, flags]) => ({ category: cat, flags }))
}

export default function ParameterReference({ flagMetadata, existingFlags, onAddFlag }) {
  const [search, setSearch] = useState('')

  const groups = useMemo(
    () => categorizeFlags(flagMetadata),
    [flagMetadata]
  )

  const query = search.toLowerCase()
  const filtered = useMemo(() => {
    if (!query) return groups
    return groups.map(g => ({
      ...g,
      flags: g.flags.filter(f => {
        const searchable = `${f.cli || ''} ${f.description || ''} ${g.category}`.toLowerCase()
        return searchable.includes(query)
      })
    })).filter(g => g.flags.length > 0)
  }, [groups, query])

  const existingSet = useMemo(
    () => new Set((existingFlags || []).map(f => f.trim())),
    [existingFlags]
  )

  if (!flagMetadata || Object.keys(flagMetadata).length === 0) return null

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 h-full flex flex-col">
      <div className="px-3 py-2 border-b border-gray-700 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-book text-gray-500 text-xs"></i>
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Parameter Reference</span>
        </div>
        <a
          href="https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md"
          target="_blank"
          rel="noreferrer"
          className="text-gray-500 hover:text-gray-300 text-xs"
          title="llama-server docs"
        >
          <i className="fa-solid fa-arrow-up-right-from-square"></i>
        </a>
      </div>
      <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
        <div className="relative">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search flags..."
            className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 pr-7 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200 cursor-pointer"
              aria-label="Clear search"
            >
              <i className="fa-solid fa-xmark text-xs"></i>
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="text-gray-500 text-xs italic px-3 py-3">No matching flags.</p>
        ) : (
          filtered.map(({ category, flags }) => (
            <div key={category}>
              <div className="text-gray-500 uppercase tracking-wider text-[10px] font-semibold mt-2 mb-1 px-3">
                {category}
              </div>
              {flags.map(f => (
                <ParamRow
                  key={f.key}
                  f={f}
                  alreadyAdded={existingSet.has(f.cli || '')}
                  onAddFlag={onAddFlag}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
