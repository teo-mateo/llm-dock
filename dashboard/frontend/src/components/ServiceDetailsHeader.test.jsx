import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ServiceDetailsHeader from './ServiceDetailsHeader'

afterEach(() => cleanup())

const MISSING_IMAGE = 'llm-dock-llamacpp:glm5next-0910-lru'

// The backend shape for an image that does not exist locally (issue #233's
// service was configured with exactly this).
const missingImageInfo = {
  name: MISSING_IMAGE,
  exists: false,
  source: null,
  created: null,
  size: null,
  build_date: null,
  build_commit: null,
  registry: null,
  upstream_url: null,
  upstream_version: null,
}

const builtImageInfo = {
  name: 'llm-dock-llamacpp:latest',
  exists: true,
  source: 'built',
  created: '2026-09-10T08:00:00Z',
  size: 10900000000,
  build_date: '2026-09-10T07:55:00Z',
  build_commit: 'abcdef1234567890',
  registry: null,
  upstream_url: null,
  upstream_version: null,
}

function renderHeader({ onFetch, config, runtime }) {
  const onError = vi.fn()
  const actions = {
    fetchImageInfo: onFetch,
    fetchYamlPreview: vi.fn(),
    setPublicPort: vi.fn(),
    registerOpenWebUI: vi.fn(),
    unregisterOpenWebUI: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    restart: vi.fn(),
  }
  render(
    <MemoryRouter>
      <ServiceDetailsHeader
        serviceName={config?.alias || 'llamacpp-test'}
        config={config || { template_type: 'llamacpp', image: MISSING_IMAGE, port: 3336 }}
        runtime={runtime || { status: 'not-created', api_key: 'key-not-a-real-key-1234567890abcdef' }}
        transitioning={null}
        actions={actions}
        onRename={vi.fn()}
        onSuccess={vi.fn()}
        onError={onError}
      />
    </MemoryRouter>
  )
  return { onError }
}

function openPopover() {
  fireEvent.click(screen.getByTitle('Image details'))
}

describe('ImagePopover', () => {
  it('keeps the popover open with the error and a retry when the fetch fails', async () => {
    const onFetch = vi.fn().mockRejectedValueOnce(new Error('HTTP 404'))
    const { onError } = renderHeader({ onFetch })

    openPopover()

    const message = await screen.findByText(/Failed to load image details: HTTP 404/)
    expect(message).toBeTruthy()
    // The failure is surfaced in place, not via the page-level toast
    expect(onError).not.toHaveBeenCalled()
    // The popover stayed open: the image name is still visible next to the error
    expect(screen.getByText(MISSING_IMAGE)).toBeTruthy()
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy()
  })

  it('retry refetches and renders the details on success', async () => {
    const onFetch = vi.fn()
      .mockRejectedValueOnce(new Error('HTTP 404'))
      .mockResolvedValueOnce(builtImageInfo)
    renderHeader({ onFetch })

    openPopover()
    await screen.findByText(/Failed to load image details: HTTP 404/)

    fireEvent.click(screen.getByRole('button', { name: /retry/i }))

    await screen.findByText('Built locally')
    expect(onFetch).toHaveBeenCalledTimes(2)
    expect(screen.getByText(/commit abcdef12/)).toBeTruthy()
  })

  it('an image missing locally is not an error: the popover opens with a not-present notice', async () => {
    const onFetch = vi.fn().mockResolvedValue(missingImageInfo)
    const { onError } = renderHeader({ onFetch })

    openPopover()

    await screen.findByText('Image not present locally')
    expect(screen.queryByText(/Failed to load image details/)).toBeNull()
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull()
    expect(onError).not.toHaveBeenCalled()
  })
})
