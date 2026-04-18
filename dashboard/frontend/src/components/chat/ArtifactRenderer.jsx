import { useState } from 'react'

function downloadArtifact(artifact) {
  const t = artifact.type || artifact.artifact_type
  const ext = t === 'svg' ? 'svg' : t === 'html' ? 'html' : t === 'code' ? (artifact.language || 'txt') : 'txt'
  const mime = t === 'svg' ? 'image/svg+xml' : t === 'html' ? 'text/html' : 'text/plain'
  const blob = new Blob([artifact.content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${(artifact.title || 'artifact').replace(/\s+/g, '_')}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

export default function ArtifactRenderer({ artifact }) {
  const [expanded, setExpanded] = useState(true)
  // Normalize: SSE sends artifact_type, DB sends type
  const artType = artifact.type || artifact.artifact_type

  return (
    <div className="rounded-lg border border-blue-500/30 overflow-hidden bg-gray-900/50 my-2">
      {/* Title bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-blue-500/10 border-b border-blue-500/20">
        <div className="flex items-center gap-2 text-xs">
          <i className={`fa-solid ${
            artType === 'svg' ? 'fa-image' :
            artType === 'code' ? 'fa-code' :
            artType === 'html' ? 'fa-globe' :
            'fa-file'
          } text-blue-400 text-[10px]`}></i>
          <span className="text-blue-300 font-medium">{artifact.title || 'Artifact'}</span>
          <span className="text-gray-500 text-[10px]">{artType.toUpperCase()}</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => downloadArtifact(artifact)}
            className="text-gray-500 hover:text-blue-400 px-1.5 py-0.5 rounded hover:bg-blue-500/10"
            title="Download"
          >
            <i className="fa-solid fa-download text-[10px]"></i>
          </button>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-gray-500 hover:text-gray-300 px-1.5 py-0.5 rounded hover:bg-gray-700"
          >
            <i className={`fa-solid fa-chevron-${expanded ? 'up' : 'down'} text-[10px]`}></i>
          </button>
        </div>
      </div>

      {/* Content */}
      {expanded && (
        <div className="p-3">
          {artType === 'svg' && (
            <div
              className="bg-white rounded p-4 flex items-center justify-center"
              dangerouslySetInnerHTML={{ __html: artifact.content }}
            />
          )}

          {artType === 'image' && (
            <img
              src={artifact.content}
              alt={artifact.title || 'Image'}
              className="max-w-full rounded"
            />
          )}

          {artType === 'code' && (
            <pre className="bg-gray-950 rounded p-3 text-xs text-gray-300 overflow-auto max-h-96">
              <code>{artifact.content}</code>
            </pre>
          )}

          {artType === 'html' && (
            <iframe
              srcDoc={artifact.content}
              className="w-full h-96 border-0 rounded bg-white"
              sandbox="allow-scripts"
              title={artifact.title || 'HTML Artifact'}
            />
          )}
        </div>
      )}
    </div>
  )
}
