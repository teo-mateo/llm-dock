import { imagePreview } from '../../../utils/piTools/images'
import { imageLabel } from '../../../utils/piTools/payload'
import { openBlob } from './openBlob'

export default function ToolImage({ image }) {
  const preview = imagePreview(image)
  const label = imageLabel(image)
  return (
    <figure className="m-0 flex w-full min-w-0 flex-col items-start gap-1">
      {preview != null && (
        <button
          type="button"
          onClick={() => openBlob(preview.toBlob())}
          title="Open full size"
          className="block max-w-[min(20rem,100%)] cursor-zoom-in"
        >
          <img src={preview.src} alt={label} className="block h-auto max-h-80 max-w-full rounded border border-border object-contain" />
        </button>
      )}
      <figcaption className="font-mono text-xs text-fg-muted">{label}</figcaption>
    </figure>
  )
}
