export default function ShowAllToggle({ expanded, total, onToggle, noun = 'lines' }) {
  return (
    <button type="button" onClick={onToggle} className="text-xs text-accent-fg hover:underline">
      {expanded ? 'Show less' : `Show all ${total} ${noun}`}
    </button>
  )
}
