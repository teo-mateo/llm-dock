export default function SpinoffTaskbar({ windows, onRestore, onClose }) {
  const minimized = windows.filter(w => w.minimized)
  if (minimized.length === 0) return null

  return (
    <div className="fixed bottom-0 left-56 right-0 z-40 bg-app border-t border-border px-2 py-1 flex gap-1 overflow-x-auto">
      {minimized.map(w => (
        <div
          key={w.id}
          className="flex items-center gap-1.5 bg-surface border border-border rounded px-2.5 py-1.5 text-xs text-fg-muted hover:bg-surface-strong cursor-pointer group max-w-[200px]"
          onClick={() => onRestore(w.id)}
        >
          <i className="fa-solid fa-code-branch text-purple-400 text-[10px] flex-shrink-0"></i>
          <span className="truncate">{w.text.length > 25 ? w.text.slice(0, 25) + '...' : w.text}</span>
          <button
            onClick={e => { e.stopPropagation(); onClose(w.id) }}
            className="text-fg-faint hover:text-danger-fg flex-shrink-0 opacity-0 group-hover:opacity-100"
          >
            <i className="fa-solid fa-xmark text-[10px]"></i>
          </button>
        </div>
      ))}
    </div>
  )
}
