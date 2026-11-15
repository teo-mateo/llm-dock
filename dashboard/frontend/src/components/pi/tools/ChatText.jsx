import Capped from './Capped'

export default function ChatText({ text, className = '' }) {
  return (
    <Capped items={text.split('\n')}>
      {(shown) => (
        <p className={`m-0 w-full min-w-0 whitespace-pre-wrap break-words text-sm text-fg ${className}`}>
          {shown.join('\n')}
        </p>
      )}
    </Capped>
  )
}
