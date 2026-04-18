import { useState } from 'react'

export default function SystemPromptEditor({ mainPrompt, sidekickPrompt, onChangeMain, onChangeSidekick }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-gray-700">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-2 text-xs text-gray-500 hover:text-gray-400 w-full text-left"
      >
        <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} text-[10px]`}></i>
        <i className="fa-solid fa-sliders"></i>
        <span>System Prompts</span>
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Main Model</label>
            <textarea
              value={mainPrompt}
              onChange={e => onChangeMain(e.target.value)}
              rows={3}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-200 resize-none focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Sidekick Model</label>
            <textarea
              value={sidekickPrompt}
              onChange={e => onChangeSidekick(e.target.value)}
              rows={3}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-200 resize-none focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
      )}
    </div>
  )
}
