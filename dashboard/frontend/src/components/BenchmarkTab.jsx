import { useState } from 'react'
import useBenchmark, { BENCHMARK_ONLY_FLAGS } from '../hooks/useBenchmark'
import BenchmarkHistory from './BenchmarkHistory'

function fmtTs(n) {
  if (n == null) return '—'
  return n.toFixed(2)
}

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString()
}

export default function BenchmarkTab({ serviceName, modelPath }) {
  const {
    params, paramsLoaded, setParam, removeParam, commandPreview,
    starting, startError, startBenchmark,
    currentRun, isRunActive, cancelRun,
    history, historyError, refreshHistory, refreshRun,
    applyingId, applyResult, applyRun, dismissApplyResult,
    deletingId, deleteRun,
  } = useBenchmark(serviceName, modelPath)

  const [newFlag, setNewFlag] = useState('')
  const [addFlagError, setAddFlagError] = useState(null)
  const [showOutput, setShowOutput] = useState(false)

  const paramEntries = Object.entries(params)

  const handleStart = async () => {
    try {
      await startBenchmark()
    } catch {
      // startError already set by the hook
    }
  }

  const handleAddFlag = () => {
    const flag = newFlag.trim()
    if (!flag) return
    if (!flag.startsWith('-')) {
      setAddFlagError('Flag names must start with - (e.g. -ngl or --flash-attn)')
      return
    }
    setAddFlagError(null)
    setParam(flag, params[flag] ?? '')
    setNewFlag('')
  }

  const handleApply = async (runId) => {
    if (!window.confirm('Write this run\'s non-benchmark flags back onto the service? Restart the service for them to take effect.')) return
    try {
      await applyRun(runId)
    } catch {
      // applyResult already set by the hook
    }
  }

  const handleDelete = async (runId) => {
    const run = history.find(r => r.id === runId)
    const verb = run && (run.status === 'running' || run.status === 'pending') ? 'Cancel' : 'Delete'
    if (!window.confirm(`${verb} benchmark ${runId.slice(0, 8)}?`)) return
    try {
      await deleteRun(runId)
    } catch {
      // the row stays; the error is transient
    }
  }

  return (
    <div className="space-y-6">
      <NewBenchmarkCard
        paramsLoaded={paramsLoaded}
        paramEntries={paramEntries}
        newFlag={newFlag}
        setNewFlag={(v) => { setNewFlag(v); setAddFlagError(null) }}
        addFlagError={addFlagError}
        onAddFlag={handleAddFlag}
        setParam={setParam}
        removeParam={removeParam}
        commandPreview={commandPreview}
        starting={starting}
        startError={startError}
        isRunActive={isRunActive}
        onStart={handleStart}
      />

      {applyResult && (
        <div className={`rounded-lg border p-4 text-sm ${applyResult.success ? 'border-success/40 bg-success/10' : 'border-danger/40 bg-danger/10'}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <div className={`font-medium ${applyResult.success ? 'text-success' : 'text-danger-fg'}`}>
                {applyResult.success ? 'Configuration applied' : 'Apply failed'}
              </div>
              <div className="text-fg-muted">{applyResult.message}</div>
              {applyResult.success && (
                <>
                  {Object.keys(applyResult.applied_params || {}).length > 0 && (
                    <pre className="bg-surface rounded p-2 font-mono text-xs text-fg overflow-x-auto">
                      {Object.entries(applyResult.applied_params).map(([f, v]) => `${f}${v ? ` ${v}` : ''}`).join('\n')}
                    </pre>
                  )}
                  {applyResult.skipped_flags && applyResult.skipped_flags.length > 0 && (
                    <div className="text-fg-subtle text-xs">
                      Skipped (benchmark-only): {applyResult.skipped_flags.join(', ')}
                    </div>
                  )}
                </>
              )}
            </div>
            <button onClick={dismissApplyResult} className="text-fg-subtle hover:text-fg cursor-pointer" aria-label="Dismiss">
              <i className="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>
      )}

      {currentRun && (
        <RunStatusCard
          run={currentRun}
          isRunActive={isRunActive}
          showOutput={showOutput}
          onToggleOutput={() => setShowOutput(v => !v)}
          onCancel={cancelRun}
        />
      )}

      <BenchmarkHistory
        history={history}
        applyingId={applyingId}
        deletingId={deletingId}
        onApply={handleApply}
        onDelete={handleDelete}
        onExpand={refreshRun}
      />
      {historyError && <div className="text-danger-fg text-xs">Failed to load history: {historyError}</div>}
      {!historyError && (
        <button onClick={refreshHistory} className="text-fg-subtle hover:text-fg text-xs cursor-pointer">
          <i className="fa-solid fa-rotate mr-1"></i>Refresh history
        </button>
      )}
    </div>
  )
}

function NewBenchmarkCard({
  paramsLoaded, paramEntries, newFlag, setNewFlag, onAddFlag, addFlagError,
  setParam, removeParam, commandPreview,
  starting, startError, isRunActive, onStart,
}) {
  return (
    <div className="bg-surface rounded-lg border border-border">
      <div className="px-5 py-4 border-b border-border flex justify-between items-center">
        <h3 className="text-lg font-semibold text-fg">New Benchmark</h3>
        <span className="text-fg-subtle text-xs">llama-bench (this service's model)</span>
      </div>
      <div className="p-5 space-y-4">
        <div className="space-y-2">
          {paramEntries.map(([flag, value]) => (
            <div key={flag} className="flex items-center gap-2">
              <span className={`w-44 shrink-0 text-xs font-mono truncate ${BENCHMARK_ONLY_FLAGS.has(flag) ? 'text-accent' : 'text-fg'}`} title={flag}>
                {flag}
              </span>
              {BENCHMARK_ONLY_FLAGS.has(flag) && (
                <span className="shrink-0 text-[9px] uppercase tracking-wide font-semibold bg-accent/15 text-accent px-1.5 py-0.5 rounded">bench</span>
              )}
              <input
                value={value ?? ''}
                onChange={e => setParam(flag, e.target.value)}
                placeholder="value (empty = flag only)"
                className="flex-1 bg-surface-strong border border-border rounded px-2 py-1 text-sm font-mono text-fg"
              />
              <button
                onClick={() => removeParam(flag)}
                className="text-fg-subtle hover:text-danger-fg cursor-pointer px-1"
                aria-label={`Remove ${flag}`}
              >
                <i className="fa-solid fa-xmark text-xs"></i>
              </button>
            </div>
          ))}
          {paramEntries.length === 0 && paramsLoaded && (
            <div className="text-fg-subtle text-xs">No parameters — the service's defaults are used.</div>
          )}
          <div className="flex items-center gap-2 pt-1 border-t border-border/50">
            <input
              value={newFlag}
              onChange={e => setNewFlag(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') onAddFlag() }}
              placeholder="add flag, e.g. -ngl or --flash-attn"
              className="flex-1 bg-surface-strong border border-border rounded px-2 py-1 text-sm font-mono text-fg"
            />
            <button
              onClick={onAddFlag}
              className="text-xs px-3 py-1.5 rounded bg-surface-strong hover:bg-accent hover:text-white text-fg-muted cursor-pointer font-medium"
            >
              Add flag
            </button>
            {addFlagError && <span className="text-danger-fg text-xs">{addFlagError}</span>}
          </div>
        </div>

        <pre className="bg-surface-strong rounded p-3 font-mono text-xs text-fg-muted overflow-x-auto whitespace-pre-wrap break-all">{commandPreview}</pre>

        {startError && <div className="text-danger-fg text-sm">{startError}</div>}

        {isRunActive ? (
          <button
            onClick={onStart}
            disabled
            className="px-4 py-2 rounded bg-surface-strong text-fg-subtle text-sm font-medium cursor-not-allowed"
          >
            <i className="fa-solid fa-spinner fa-spin mr-2"></i>Benchmark running
          </button>
        ) : (
          <button
            onClick={onStart}
            disabled={starting || !paramsLoaded}
            className="px-4 py-2 rounded bg-accent-strong hover:bg-accent text-white text-sm font-medium cursor-pointer disabled:opacity-50"
          >
            {starting ? 'Starting…' : 'Start benchmark'}
          </button>
        )}
      </div>
    </div>
  )
}

function RunStatusCard({ run, isRunActive, showOutput, onToggleOutput, onCancel }) {
  const statusColors = {
    pending: 'text-fg-muted',
    running: 'text-accent',
    completed: 'text-success',
    failed: 'text-danger-fg',
    cancelled: 'text-fg-subtle',
  }

  return (
    <div className="bg-surface rounded-lg border border-border">
      <div className="px-5 py-4 border-b border-border flex justify-between items-center">
        <h3 className="text-lg font-semibold text-fg">
          <span className={`mr-2 ${statusColors[run.status] || 'text-fg'}`}>{run.status}</span>
          <span className="text-fg-subtle text-sm font-normal">started {fmtTime(run.started_at)}</span>
        </h3>
        {isRunActive && (
          <button
            onClick={onCancel}
            className="text-xs px-2 py-1 rounded bg-surface-strong hover:bg-danger hover:text-white text-fg-muted cursor-pointer"
          >
            <i className="fa-solid fa-stop mr-1"></i>Cancel
          </button>
        )}
      </div>
      <div className="p-5 space-y-3">
        {(run.status === 'completed' || run.status === 'failed') && (
          <div className="flex flex-wrap gap-6 text-sm">
            <div>
              <div className="text-fg-subtle text-xs uppercase tracking-wide">Prompt processing</div>
              <div className="font-mono">{fmtTs(run.pp_avg_ts)} t/s{run.pp_stddev_ts != null && <span className="text-fg-subtle text-xs"> (±{run.pp_stddev_ts.toFixed(2)})</span>}</div>
            </div>
            <div>
              <div className="text-fg-subtle text-xs uppercase tracking-wide">Text generation</div>
              <div className="font-mono">{fmtTs(run.tg_avg_ts)} t/s{run.tg_stddev_ts != null && <span className="text-fg-subtle text-xs"> (±{run.tg_stddev_ts.toFixed(2)})</span>}</div>
            </div>
          </div>
        )}
        {run.status === 'failed' && run.error_message && (
          <pre className="bg-surface-strong rounded p-3 font-mono text-xs text-danger-fg whitespace-pre-wrap max-h-40 overflow-y-auto">{run.error_message}</pre>
        )}
        {run.status === 'running' && (
          <div className="text-fg-muted text-sm">
            <i className="fa-solid fa-spinner fa-spin mr-2 text-accent"></i>
            llama-bench is running — results land here when it finishes (no live stream; this view polls every 2 s).
          </div>
        )}
        {run.raw_output && (
          <>
            <button onClick={onToggleOutput} className="text-fg-subtle hover:text-fg text-xs cursor-pointer">
              <i className={`fa-solid fa-chevron-${showOutput ? 'up' : 'down'} mr-1`} />
              {showOutput ? 'Hide' : 'Show'} raw output
            </button>
            {showOutput && (
              <pre className="bg-surface-strong rounded p-3 font-mono text-xs text-fg-muted whitespace-pre-wrap max-h-64 overflow-y-auto">{run.raw_output}</pre>
            )}
          </>
        )}
      </div>
    </div>
  )
}
