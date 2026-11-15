export default function ShowAllToggle({ expanded, total, onToggle }) {
  return (
    <button type="button" onClick={onToggle} className="text-xs text-accent-fg hover:underline">
      {expanded ? 'Show less' : `Show all ${total} lines`}
    </button>
  )
}
