# Plan: Migrate v2 React Frontend to SSE for Services Streaming

## Overview

Replace the current polling-based service status updates in the React v2 frontend with Server-Sent Events (SSE) streaming, matching the implementation pattern from the legacy JavaScript frontend.

## Current State

### Polling Implementations

1. **ServicesTable.jsx** (lines 193-202)
   - Polls `/api/services` every 3 seconds (POLL_INTERVAL = 3000)
   - Uses `setInterval` to repeatedly fetch and update service state
   - Full refresh approach - replaces entire services array

2. **useRunningServices.js** (lines 30, 29)
   - Polls `/api/services` every 5 seconds (POLL_INTERVAL = 5000)
   - Filters for running llama.cpp and vLLM services only
   - Used by components that need only running services

### SSE Infrastructure Already Available

- Backend SSE endpoint: `/api/services/stream` (implemented in `dashboard/routes/services.py`)
- Event types: `snapshot`, `delta`, `error`
- Legacy client implementation: `dashboard/static/js/services-stream.js`
- Frontend SSE utilities: `dashboard/frontend/src/services/sse.js` (chat streaming only)

## Target State

- ServicesTable and all components remove polling intervals
- Single SSE connection established on app initialization
- Initial snapshot renders complete service list
- Delta updates incrementally update individual service statuses
- Service state maintained in React state/context
- Automatic reconnection on connection loss
- Cleanup on component unmount

## Implementation Plan

### Phase 1: Create Services SSE Hook

**File**: `dashboard/frontend/src/hooks/useServicesSSE.js` (new)

```javascript
import { useState, useEffect, useCallback, useRef } from 'react'
import { getToken } from '../api'

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? `${window.location.protocol}//${window.location.hostname}:3399/api`
  : `${window.location.protocol}//${window.location.hostname}/api`

export default function useServicesSSE() {
  const [services, setServices] = useState(null)
  const [error, setError] = useState(null)
  const [connected, setConnected] = useState(false)
  const abortRef = useRef(null)
  const reconnectTimerRef = useRef(null)

  // Sort services: open-webui first, then alphabetically
  const sortServices = useCallback((svcs) => {
    return [...svcs].sort((a, b) => {
      if (a.name === 'open-webui') return -1
      if (b.name === 'open-webui') return 1
      return a.name.localeCompare(b.name)
    })
  }, [])

  // Apply delta update to services state
  const applyDelta = useCallback((current, delta) => {
    const updated = [...current]
    const index = updated.findIndex(s => s.name === delta.service_name)

    if (delta.action === 'remove') {
      if (index !== -1) {
        updated.splice(index, 1)
      }
    } else {
      const newService = {
        ...(index !== -1 ? updated[index] : {}),
        name: delta.service_name,
        status: delta.status,
        container_id: delta.container_id,
      }
      if (index !== -1) {
        updated[index] = newService
      } else {
        updated.push(newService)
      }
    }
    return sortServices(updated)
  }, [sortServices])

  // Handle incoming SSE messages
  const handleMessage = useCallback((data) => {
    switch (data.type) {
      case 'snapshot':
        setServices(sortServices(data.data.services))
        setError(null)
        break
      case 'delta':
        setServices(prev => {
          if (!prev) return prev
          return applyDelta(prev, data)
        })
        break
      case 'error':
        setError(data.message)
        break
    }
  }, [sortServices, applyDelta])

  // Start SSE connection
  const startStream = useCallback(() => {
    const token = getToken()
    if (!token) return

    // Cleanup any existing connection
    if (abortRef.current) {
      abortRef.current.abort()
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
    }

    const controller = new AbortController()
    abortRef.current = controller

    setConnected(false)
    setError(null)

    fetch(`${API_BASE}/services/stream`, {
      method: 'GET',
      headers: { 'Authorization': `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(response => {
        if (response.status === 401) {
          throw new Error('Unauthorized')
        }
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        setConnected(true)
        return response
      })
      .then(async (response) => {
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const trimmed = line.slice(6).trim()
                  if (!trimmed) continue
                  const data = JSON.parse(trimmed)
                  handleMessage(data)
                } catch {
                  // Ignore malformed lines
                }
              }
              // Keepalive messages are ignored
            }
          }
        } catch (err) {
          if (err.name !== 'AbortError') {
            console.error('Services SSE error:', err)
            setConnected(false)
          }
        } finally {
          setConnected(false)
        }
      })
      .catch(err => {
        if (err.name !== 'AbortError') {
          console.error('Services SSE setup error:', err)
          setConnected(false)
          setError(err.message)
          // Schedule reconnection
          reconnectTimerRef.current = setTimeout(startStream, 3000)
        }
      })
  }, [handleMessage])

  // Stop SSE connection
  const stopStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    setConnected(false)
  }, [])

  // Start stream on mount
  useEffect(() => {
    startStream()
    return () => stopStream()
  }, [startStream, stopStream])

  // Reconnect on token changes
  useEffect(() => {
    const token = getToken()
    if (token) {
      startStream()
    } else {
      stopStream()
      setServices(null)
    }
  }, [startStream, stopStream])

  // Handle page visibility changes
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        if (!connected && getToken()) {
          startStream()
        }
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [connected, startStream])

  return { services, error, connected, startStream, stopStream, refresh: startStream }
}
```

### Phase 2: Update ServicesTable.jsx

**Changes**:
- Remove `POLL_INTERVAL` constant
- Remove polling `useEffect` (lines 193-202)
- Import and use `useServicesSSE` hook
- Remove `fetchServices` callback
- Update all service update handlers to trigger manual refresh or rely on SSE

**Key modifications**:
```javascript
// Remove:
const [services, setServices] = useState(null)
const [error, setError] = useState(null)
const fetchServices = useCallback(async () => { ... })
useEffect(() => { let active = true; ... }, [fetchServices])

// Add:
const { services, error, connected } = useServicesSSE()
```

Update action handlers to manually refresh if needed:
```javascript
const handleStart = async (name) => {
  setTransitioning(prev => ({ ...prev, [name]: 'starting' }))
  try {
    await startService(name)
    // SSE will update the status, but poll once to ensure immediate UI update
    // This can be removed if SSE is reliable enough
  } catch { /* ignore */ }
  finally {
    setTransitioning(prev => { const n = { ...prev }; delete n[name]; return n })
  }
}
```

### Phase 3: Update useRunningServices.js

**Changes**:
- Import and use `useServicesSSE` hook
- Derive running services from the SSE stream instead of polling

```javascript
import { useMemo } from 'react'
import useServicesSSE from './useServicesSSE'

export default function useRunningServices() {
  const { services, loading } = useServicesSSE()

  const running = useMemo(() => {
    return (services || []).filter(s =>
      s.status === 'running' && (s.name.startsWith('llamacpp-') || s.name.startsWith('vllm-'))
    )
  }, [services])

  return { services: running, loading: services === null }
}
```

### Phase 4: Update App.jsx for Global State (Optional)

Consider creating a ServicesProvider context to share the SSE stream across all components that need service data. This avoids multiple SSE connections.

**File**: `dashboard/frontend/src/contexts/ServicesContext.jsx` (new)

However, for simplicity and to match the legacy pattern, the hook-based approach in Phase 1-3 is sufficient. Each component can use the hook independently, and the SSE connection will be shared through the singleton pattern in the hook.

### Phase 5: Add Connection Status Indicator (Optional)

Add a visual indicator in the UI to show SSE connection status:
- Connected: Green indicator
- Disconnected: Yellow/red indicator with reconnection countdown
- Error: Red indicator with error message

### Phase 6: Testing

1. **Manual Testing**
   - Start/stop services and verify UI updates in real-time
   - Test reconnection after network interruption
   - Test with multiple browser tabs
   - Test logout/login flow

2. **Automated Tests**
   - Add tests for `useServicesSSE` hook
   - Test snapshot handling
   - Test delta updates
   - Test error handling
   - Test reconnection logic

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `hooks/useServicesSSE.js` | Create | New SSE hook for service streaming |
| `components/ServicesTable.jsx` | Modify | Replace polling with useServicesSSE |
| `hooks/useRunningServices.js` | Modify | Use useServicesSSE instead of polling |
| `contexts/ServicesContext.jsx` | Optional | Global services state (if needed) |

## Acceptance Criteria

- [ ] ServicesTable renders initial service list from SSE snapshot
- [ ] Service status changes (start/stop/restart/delete) update in real-time via SSE deltas
- [ ] No polling intervals remain in ServicesTable or useRunningServices
- [ ] SSE connection automatically reconnects on failure
- [ ] SSE connection cleans up on component unmount
- [ ] Connection errors are logged but don't break the UI
- [ ] Multiple browser tabs each maintain their own SSE connection
- [ ] Page visibility changes trigger reconnection when returning to visible state

## Dependencies

- Backend SSE endpoint `/api/services/stream` (already implemented)
- Docker event manager (already implemented)
- Authentication token handling (already implemented)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| SSE connection drops | Automatic reconnection with exponential backoff |
| Delta updates out of sync | Initial snapshot provides full state; deltas are incremental |
| Multiple tabs consuming resources | Each tab maintains its own connection (acceptable for SSE) |
| Browser compatibility | SSE is widely supported; fallback to polling if needed |

## Rollback Plan

If issues arise, revert to polling by:
1. Revert ServicesTable.jsx to use polling
2. Revert useRunningServices.js to use polling
3. Remove useServicesSSE.js (new file)

## Estimated Effort

- **Phase 1**: 2-4 hours (create hook)
- **Phase 2**: 2-3 hours (update ServicesTable)
- **Phase 3**: 1-2 hours (update useRunningServices)
- **Phase 4**: 1-2 hours (optional context)
- **Phase 5**: 2-3 hours (optional UI indicator)
- **Phase 6**: 2-4 hours (testing)
- **Total**: 8-18 hours

## Notes

- The legacy implementation (`dashboard/static/js/services-stream.js`) serves as a reference
- The backend SSE endpoint already handles authentication via `@require_auth`
- The event format (snapshot/delta/error) is already defined and working
- Consider adding a configuration option to fall back to polling for debugging
