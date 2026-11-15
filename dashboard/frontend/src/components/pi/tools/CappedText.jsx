import Capped from './Capped'

const TONES = {
  fg: 'text-fg',
  muted: 'text-fg-muted',
  error: 'text-danger-fg',
}

export default function CappedText({ text, tone = 'muted', wrap = true, bare = false }) {
  const layout = wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre overflow-x-auto'
  const frame = bare ? '' : 'max-h-[32rem] overflow-y-auto rounded border border-border bg-app px-2 py-1'
  return (
    <Capped items={text.split('\n')}>
      {(shown) => (
        <pre className={`m-0 w-full min-w-0 font-mono text-xs ${layout} ${frame} ${TONES[tone]}`}>{shown.join('\n')}</pre>
      )}
    </Capped>
  )
}
