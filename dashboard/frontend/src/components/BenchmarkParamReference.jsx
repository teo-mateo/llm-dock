import { useState, useMemo, useRef, useCallback } from 'react'
import { BENCHMARK_ONLY_FLAGS, AUTO_ADDED_FLAGS } from '../hooks/useBenchmark'

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

function RefRow({ p, alreadyAdded, onAdd }) {
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

  const flagText = p.flag || p.long
  const isBenchOnly = BENCHMARK_ONLY_FLAGS.has(p.flag) || BENCHMARK_ONLY_FLAGS.has(p.long)
  const isAutoAdded = AUTO_ADDED_FLAGS.has(p.flag) || AUTO_ADDED_FLAGS.has(p.long)
  const flagColor = isBenchOnly ? 'text-orange-400' : 'text-yellow-400'
  const rowBorder = isBenchOnly ? 'border-l-2 border-orange-500/40' : 'border-l-2 border-transparent'
  const clickable = !isAutoAdded && !alreadyAdded

  const primaryFlag = p.flag || p.long
  const secondaryFlag = p.flag && p.long ? p.long : null

  return (
    <div
      ref={rowRef}
      onMouseEnter={p.tip ? handleMouseEnter : undefined}
      onClick={() => clickable && onAdd(flagText, p.def)}
      className={`group rounded-r mx-1 px-2 py-1.5 relative transition-colors ${rowBorder} ${
        isAutoAdded ? 'opacity-60'
        : clickable ? 'hover:bg-gray-700/50 cursor-pointer'
        : ''
      }`}
      title={!p.tip ? (
        isAutoAdded ? 'Auto-added, cannot be modified'
        : alreadyAdded ? 'Already in parameters'
        : (isBenchOnly ? 'Benchmark-only \u2014 not applied to service config. ' : '') + `Click to add ${flagText} to parameters`
      ) : undefined}
    >
      <div className="flex items-center gap-1 text-xs">
        <span className={`${flagColor} font-mono font-semibold`}>{primaryFlag}</span>
        {secondaryFlag && <span className="text-gray-600">{secondaryFlag}</span>}
        {isBenchOnly && (
          <span className="text-[9px] uppercase tracking-wide font-semibold bg-orange-500/15 text-orange-400 px-1 py-0.5 rounded">
            {isAutoAdded ? 'auto' : 'bench'}
          </span>
        )}
        {p.def && <span className="text-gray-600 ml-auto pl-2 whitespace-nowrap">{p.def}</span>}
      </div>
      <div className="text-gray-400 text-xs leading-snug mt-0.5">{p.desc}</div>
      {p.tip && <ParamTooltip tipRef={tipRef} html={p.tip} tipPos={tipPos} />}
    </div>
  )
}

export default function BenchmarkParamReference({ paramReference, params, onAddParam }) {
  const [search, setSearch] = useState('')

  const query = search.toLowerCase()

  const existingFlags = useMemo(
    () => new Set(params.filter(p => !p.isEmpty && p.flag).map(p => p.flag)),
    [params]
  )

  const { groups, hasResults } = useMemo(() => {
    let currentCat = ''
    const groups = []
    let hasResults = false

    paramReference.forEach(p => {
      const searchable = `${p.flag} ${p.long} ${p.desc} ${p.cat}`.toLowerCase()
      if (query && !searchable.includes(query)) return

      hasResults = true

      if (p.cat !== currentCat) {
        currentCat = p.cat
        groups.push({ type: 'category', name: currentCat })
      }
      groups.push({ type: 'param', param: p })
    })

    return { groups, hasResults }
  }, [paramReference, query])

  if (!paramReference || paramReference.length === 0) return null

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 h-full flex flex-col">
      {/* Header */}
      <div className="px-3 py-2 border-b border-gray-700 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <i className="fa-solid fa-book text-gray-500 text-xs"></i>
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Parameter Reference</span>
        </div>
        <a
          href="https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md"
          target="_blank"
          rel="noreferrer"
          className="text-gray-500 hover:text-gray-300 text-xs"
          title="llama-bench docs"
        >
          <i className="fa-solid fa-arrow-up-right-from-square"></i>
        </a>
      </div>

      {/* Search */}
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

      {/* Legend */}
      <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
        <div className="flex gap-3 text-[10px] text-gray-500">
          <span>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-400 mr-1"></span>
            Benchmark-only (not applied to service)
          </span>
          <span>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-yellow-400 mr-1"></span>
            Runtime param
          </span>
        </div>
      </div>

      {/* Flag list */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {!hasResults ? (
          <p className="text-gray-500 text-xs italic px-3 py-3">No matching parameters.</p>
        ) : (
          groups.map((item, i) => {
            if (item.type === 'category') {
              return (
                <div key={`cat-${item.name}`} className="text-gray-500 uppercase tracking-wider text-[10px] font-semibold mt-2 mb-1 px-3">
                  {item.name}
                </div>
              )
            }
            const p = item.param
            const flagKey = p.flag || p.long
            return (
              <RefRow
                key={flagKey}
                p={p}
                alreadyAdded={existingFlags.has(flagKey)}
                onAdd={onAddParam}
              />
            )
          })
        )}
      </div>
    </div>
  )
}
