import CappedText from './CappedText'
import ToolChip from './ToolChip'
import ToolMeta from './ToolMeta'

function BashMeta({ tool }) {
  const { item, view } = tool
  const failed = view.exitCode != null && view.exitCode !== 0
  return (
    <ToolMeta
      item={item}
      after={
        <>
          {view.dir != null && (
            <ToolChip title="from the leading cd">📁 {view.dir}</ToolChip>
          )}
          {view.timeout != null && <span className="text-fg-muted">timeout {view.timeout} s</span>}
        </>
      }
    >
      {failed && <ToolChip tone="danger">exit {view.exitCode}</ToolChip>}
    </ToolMeta>
  )
}

function BashOutput({ tool }) {
  const { output } = tool.view
  if (output == null) return null
  if (output === '') return <span className="text-xs text-fg-muted">(no output)</span>
  return <CappedText text={output} wrap={false} />
}

export default function BashToolBody({ tool }) {
  return (
    <>
      <BashMeta tool={tool} />
      <pre className="m-0 min-w-0 whitespace-pre-wrap break-words rounded border border-border bg-app px-2 py-1 font-mono text-xs text-fg">
        <span className="select-none text-success-fg">$ </span>
        {tool.view.command}
      </pre>
      <BashOutput tool={tool} />
    </>
  )
}
