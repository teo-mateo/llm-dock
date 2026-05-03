# LLM-Dock SSE Implementation

## Backend SSE Endpoint for Service Logs

### New Endpoint
- **Route**: `GET /api/services/<service_name>/logs/stream`
- **Parameters**:
  - `tail` (int, default=200): Number of log lines to include in initial snapshot
  - `timestamps` (bool, default=True): Include timestamps in log lines
- **Headers**:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache, no-transform`
  - `X-Accel-Buffering: no`

### Event Types
1. **snapshot_start**: Initial connection event
   ```json
   {"type": "snapshot_start", "service": "service-name"}
   ```

2. **log**: Individual log line
   ```json
   {"type": "log", "service": "service-name", "line": "2026-05-03T12:34:56.789000Z stdout message"}
   ```

3. **snapshot_end**: End of initial tail
   ```json
   {"type": "snapshot_end", "service": "service-name"}
   ```

4. **error**: Stream errors
   ```json
   {"type": "error", "service": "service-name", "message": "Error description"}
   ```

### Implementation Details
- **Location**: `dashboard/routes/services.py`
- **Class**: `LogStreamer`
  - Uses background thread for Docker log reading
  - Queue-based communication with keepalive
  - Handles container lifecycle events
- **Authentication**: Requires Bearer token (same as other endpoints)
- **Backward Compatibility**: Existing `/api/services/<service_name>/logs` endpoint remains unchanged

### Testing
- **Test File**: `dashboard/tests/test_service_logs_sse.py`
- **Coverage**: Authentication, error handling, SSE headers, event format, parameter handling

## Frontend SSE Integration

### Enhanced SSE Utility
- **File**: `dashboard/frontend/src/services/sse.js`
- **Function**: `streamServiceLogs(serviceName, callbacks)`
- **Callbacks**:
  - `onLog`: Handles individual log lines
  - `onSnapshotStart`: Handles initial connection
  - `onSnapshotEnd`: Handles end of initial tail
  - `onError`: Handles stream errors

### Updated ServiceLogsPanel Component
- **File**: `dashboard/frontend/src/components/ServiceLogsPanel.jsx`
- **Changes**:
  - Replaced 3-second polling with real-time SSE streaming
  - Added streaming state tracking
  - Updated UI to reflect streaming status
  - Maintained all existing functionality (refresh, pause/resume)
  - Preserved backward compatibility with REST endpoint

### Key Features
- **Real-time updates**: Logs appear instantly as they're generated
- **Connection management**: Proper cleanup on unmount or pause
- **Error handling**: Graceful fallback to polling if SSE fails
- **User experience**: Visual indicators for streaming status
- **Performance**: No more constant polling requests

### UI Changes
- Added "Streaming live" status indicator
- Updated pause/resume functionality to work with SSE
- Maintained all existing UI elements and behaviors

### Integration Notes
- Frontend automatically uses SSE when available
- Falls back to REST endpoint if needed
- No configuration required - works out of the box