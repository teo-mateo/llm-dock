import { imageDataUri, openImage } from '../../../utils/piTools/images'
import { imageLabel } from '../../../utils/piTools/payload'

export default function ToolImage({ image }) {
  const src = imageDataUri(image)
  const label = imageLabel(image)
  return (
    <figure className="m-0 flex flex-col items-start gap-1">
      {src != null && (
        <button type="button" onClick={() => openImage(image)} title="Open full size" className="cursor-zoom-in">
          <img src={src} alt={label} className="max-h-80 max-w-80 rounded border border-border object-contain" />
        </button>
      )}
      <figcaption className="font-mono text-xs text-fg-muted">{label}</figcaption>
    </figure>
  )
}
