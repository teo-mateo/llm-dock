import useBenchmark from '../hooks/useBenchmark'
import BenchmarkParamsPanel from './BenchmarkParamsPanel'
import BenchmarkParamReference from './BenchmarkParamReference'
import BenchmarkLiveOutput from './BenchmarkLiveOutput'
import BenchmarkHistory from './BenchmarkHistory'

export default function BenchmarkTab({ serviceName, config, onSuccess, onError }) {
  const {
    params,
    isRunning,
    runStatus,
    liveOutput,
    liveOutputClass,
    history,
    paramReference,
    commandPreview,
    setParamFlag,
    setParamValue,
    removeParam,
    addParam,
    resetToDefaults,
    runBenchmark,
    rerunFromHistory,
    getApplyPreview,
    applyToService,
    deleteRun,
  } = useBenchmark(serviceName, config?.model_path)

  const handleRun = async () => {
    const result = await runBenchmark()
    if (result.success) {
      onSuccess('Benchmark started')
    } else {
      onError(result.error || 'Failed to start benchmark')
    }
  }

  const handleReset = () => {
    resetToDefaults()
    onSuccess('Parameters reset to defaults')
  }

  const handleRerun = (runId) => {
    rerunFromHistory(runId)
    window.scrollTo({ top: 0, behavior: 'smooth' })
    onSuccess('Parameters loaded from history run')
  }

  const handleApply = async (runId) => {
    const preview = getApplyPreview(runId)
    if (!preview) return

    if (Object.keys(preview.applicable).length === 0) {
      onError('No applicable parameters to apply (all are benchmark-only flags)')
      return
    }

    const msg = `Apply to ${serviceName}?\n\nParams: ${preview.appliedStr}\nSkipped: ${preview.skipped.join(', ')}\n\nService must be restarted for changes to take effect.`
    if (!window.confirm(msg)) return

    const result = await applyToService(runId)
    if (result.success) {
      onSuccess(result.message)
    } else {
      onError(result.error || 'Failed to apply')
    }
  }

  const handleDelete = async (runId) => {
    const result = await deleteRun(runId)
    if (result.success) {
      onSuccess('Benchmark run deleted')
    } else {
      onError(result.error || 'Failed to delete')
    }
  }

  const handleAddParam = (flag, defaultValue) => {
    const added = addParam(flag, defaultValue)
    if (added) {
      onSuccess(`Added ${flag}`)
    } else {
      onError(`${flag} is already in your parameters`)
    }
  }

  return (
    <div>
      {/* Two-column: Parameters (left) + Reference (right) */}
      <div className="grid grid-cols-1 xl:grid-cols-[60%_1fr] gap-6 mb-4">
        <div>
          <BenchmarkParamsPanel
            params={params}
            isRunning={isRunning}
            commandPreview={commandPreview}
            onFlagChange={setParamFlag}
            onValueChange={setParamValue}
            onRemove={removeParam}
            onReset={handleReset}
            onRun={handleRun}
          />
        </div>
        <div className="relative min-h-0 overflow-hidden">
          <div className="absolute inset-0 overflow-hidden">
            <BenchmarkParamReference
              paramReference={paramReference}
              params={params}
              onAddParam={handleAddParam}
            />
          </div>
        </div>
      </div>

      <BenchmarkLiveOutput
        output={liveOutput}
        outputClass={liveOutputClass}
        runStatus={runStatus}
      />

      <BenchmarkHistory
        history={history}
        onRerun={handleRerun}
        onApply={handleApply}
        onDelete={handleDelete}
      />
    </div>
  )
}
