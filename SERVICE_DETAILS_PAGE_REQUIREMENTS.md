# Service Details Page -- Requirements Specification

## 1. Feature Overview

The Service Details Page replaces the current modal-based editing workflow with a dedicated, full-page view for each LLM service. Instead of juggling multiple overlapping modals (edit, logs, rename, YAML preview, delete), users get a single coherent page that consolidates all service-related information and actions. This reduces context-switching, lets users see logs and configuration side-by-side, and provides enough screen space to display information that was previously cramped inside modals.

The page is accessible from the main dashboard by clicking the pencil (edit) button or the service name on a service row. It supports viewing and editing service configuration, controlling the service lifecycle (start/stop/restart), observing live container logs, and managing metadata -- all from one unified view.

---

## 2. User Stories

### Epic: Service Details Page

> As a user managing local LLM services, I want a dedicated details page for each service so that I can view, configure, and control a service from one place without juggling multiple modals.

---

### US-1: Navigate to Service Details (Must Have)

**As a** dashboard user
**I want to** click on a service row (or its pencil/edit button) and be taken to a details page
**So that** I can see all information about that service in one place

**Acceptance Criteria:**
- Clicking the edit button (pencil icon) on a service row navigates to `/v2/services/{service-name}`
- Clicking the service name text also navigates to the details page
- The browser URL updates to reflect the service being viewed (deep-linkable)
- A back button or breadcrumb navigation returns the user to the main services list
- The page loads without a full browser reload (client-side routing)

---

### US-2: View Service Status and Metadata (Must Have)

**As a** dashboard user
**I want to** see the service's current status, engine type, port, model info, and API key at a glance
**So that** I know the runtime state of the service without checking multiple places

**Acceptance Criteria:**
- The page header displays: service name, engine badge (llama.cpp / vLLM), and live status indicator (running / stopped / not created)
- Port number is displayed, with a link to the service endpoint when running
- Public port indicator (globe icon) is visible when the service is on port 3301
- API key is shown (truncated) with a copy-to-clipboard button
- Model path (llama.cpp) or model name (vLLM) is displayed
- Model size is displayed when available
- Open WebUI registration status is shown
- Container ID is displayed when available
- Status updates automatically via polling (every 3 seconds)

---

### US-3: Control Service Lifecycle (Must Have)

**As a** dashboard user
**I want to** start, stop, and restart a service from its details page
**So that** I don't have to go back to the main list to control the service

**Acceptance Criteria:**
- A Start button is shown when the service is stopped or not created
- A Stop button is shown when the service is running
- A Restart button is always available when running (stop then start)
- Buttons show a loading/transitioning state while the operation is in progress
- Buttons are disabled during transitions to prevent double-clicks
- After a lifecycle action completes, the status indicator updates to reflect the new state
- Error messages are shown as toast notifications if a lifecycle action fails

---

### US-4: Edit Service Configuration (Must Have)

**As a** dashboard user
**I want to** edit the service's configuration (port, API key, CLI parameters) on the details page
**So that** I can tune the service without opening a separate modal

**Acceptance Criteria:**
- The configuration section displays all editable fields: port, API key, and CLI parameters
- Model path/name is displayed but NOT editable (changing the model requires a new service)
- Template type (llama.cpp / vLLM) is displayed but not editable
- Port field validates that the port is not already in use by another service
- CLI parameters are displayed as key-value rows with the ability to add, edit, and remove parameters
- Flag metadata (descriptions, defaults) from the API is used to provide tooltips or help text
- A Save button persists changes via `PUT /api/services/{name}`
- The user sees a success confirmation after saving
- If the service was running when configuration was saved, the user is informed that the container will be recreated
- Unsaved changes are indicated visually (yellow dot + "Unsaved changes" text)
- Save and Discard buttons are disabled when no changes exist

---

### US-5: View Container Logs (Must Have)

**As a** dashboard user
**I want to** see the container's recent logs on the details page
**So that** I can diagnose issues without opening a separate logs modal

**Acceptance Criteria:**
- A logs section displays the most recent container logs (default 200 lines)
- Logs are displayed in a monospace font with timestamps
- A refresh button reloads the logs on demand
- Auto-refresh can be toggled (pause/resume with 3-second polling)
- The log viewer auto-scrolls to the bottom on load and on new data (unless user has scrolled up)
- If the container has not been created yet, a friendly message is shown instead of an error
- Log text is selectable and copyable

---

### US-6: Rename Service (Should Have)

**As a** dashboard user
**I want to** rename a service from its details page

**Acceptance Criteria:**
- A rename action is accessible (e.g., edit icon next to the service name)
- Rename is only enabled when the service is stopped (UI disables the control with tooltip when running)
- After a successful rename, the URL updates to reflect the new name
- If rename fails (e.g., name conflict), an error message is displayed

---

### US-7: Preview Generated YAML (Should Have)

**As a** dashboard user
**I want to** see the rendered Docker Compose YAML for this service

**Acceptance Criteria:**
- A "View YAML" action shows the rendered YAML in a code block with monospace formatting
- A copy-to-clipboard button is available for the YAML content
- The preview reflects the currently saved configuration (not unsaved edits)

---

### US-8: Delete Service (Should Have)

**As a** dashboard user
**I want to** delete a service from its details page

**Acceptance Criteria:**
- A delete action is available (red button, placed to avoid accidental clicks)
- Clicking delete shows an inline confirmation: "Are you sure? This cannot be undone." with Cancel and Confirm Delete buttons
- After successful deletion, the user is navigated back to the main services list with a toast confirmation
- If the service is running, it is automatically stopped before deletion (handled by backend)

---

### US-9: Set Public Port (Should Have)

**As a** dashboard user
**I want to** assign the public port (3301) to this service from the details page

**Acceptance Criteria:**
- If the service is NOT on port 3301, a "Set as Public" button is shown
- If the service is already on port 3301, a "Public" badge is displayed
- Success/failure feedback is provided via toast notification
- The user is informed if another service was displaced from port 3301

---

### US-10: Register/Unregister with Open WebUI (Could Have)

**As a** dashboard user
**I want to** manage Open WebUI registration from the details page

**Acceptance Criteria:**
- The current registration status is displayed (registered / not registered)
- Register/Unregister buttons toggle the state
- Success/failure feedback via toast notification

---

### US-11: Return to Services List (Must Have)

**As a** dashboard user
**I want to** easily navigate back to the main services list from any details page

**Acceptance Criteria:**
- A clear back navigation element is always visible (back arrow + "Back to Services")
- Clicking it returns the user to the services list without a full page reload
- Browser back button also works naturally

---

## 3. Priority Ranking (MoSCoW)

### Must Have
1. **US-1** -- Navigate to Service Details (entry point)
2. **US-2** -- View Service Status and Metadata (core value)
3. **US-3** -- Control Service Lifecycle (most frequent action)
4. **US-4** -- Edit Service Configuration (replaces current edit modal)
5. **US-5** -- View Container Logs (high-value consolidation)
6. **US-11** -- Return to Services List (basic navigation)

### Should Have
7. **US-6** -- Rename Service
8. **US-7** -- Preview Generated YAML
9. **US-8** -- Delete Service
10. **US-9** -- Set Public Port

### Could Have
11. **US-10** -- Register/Unregister with Open WebUI

### Won't Have (this iteration)
- Real-time log streaming via WebSocket (polling is sufficient)
- Benchmarking integration on the details page (exists as separate page)
- Service cloning / "Copy From" on the details page
- Multi-service comparison view
- Configuration version history or undo

---

## 4. Architecture Decision

### Build in React (`/v2` frontend)

| Factor | Vanilla | React |
|---|---|---|
| Component composition | Template literals, manual DOM | JSX components, composable |
| State management | Global variables, manual DOM updates | `useState`/`useEffect`, declarative rendering |
| Routing | None; would require hash routing or rewrite | Add `react-router-dom`; straightforward |
| Form handling | Manual DOM queries (`getElementById`) | Controlled components, form state |
| Real-time updates | `setInterval` + manual DOM patching | `useEffect` cleanup, polling with state |
| Code organization | Flat JS files loaded in order | Module imports, component tree |

The React frontend already has component patterns that support a details page naturally. The vanilla frontend has no router and relies on global variables + imperative DOM manipulation. The React frontend at `/v2` is the right foundation.

**Login flow note:** For MVP, users log in via the vanilla frontend at `/`, which sets `dashboard_token` in localStorage. The React frontend at `/v2` reads the same token (shared origin). A React login component can be added later.

---

## 5. Routing Strategy

### React Router Setup

Install `react-router-dom` and configure routes:

```
/v2/                       -> App -> ServicesTable (list view)
/v2/services/:serviceName  -> App -> ServiceDetailsPage (detail view)
```

Use `BrowserRouter` with `basename="/v2"` to align with Vite's `base: '/v2/'`.

### Flask Catch-all Update

The existing Flask catch-all route must fall back to `index.html` for client-side routes:

```python
@app.route("/v2/<path:whatever>")
def serve_v2_static(whatever):
    dist_dir = os.path.join(app.root_path, "frontend", "dist")
    file_path = os.path.join(dist_dir, whatever)
    if os.path.isfile(file_path):
        return send_from_directory("frontend/dist", whatever)
    return send_from_directory("frontend/dist", "index.html")
```

### Navigation Patterns

- **List -> Details:** Click service row or pencil icon -> `navigate(`/services/${svc.name}`)`
- **Details -> List:** Back button -> `navigate('/')` or `navigate(-1)`
- **Post-delete:** `navigate('/')` with toast
- **Post-rename:** `navigate(`/services/${newName}`, { replace: true })`
- **Browser tab title:** `{service-name} - LLM-Dock`

---

## 6. Component Architecture

```
App
 +-- Sidebar (updated: nav links to list + active state)
 +-- Header
 +-- Routes
      +-- "/" -> ServicesTable (existing, updated with row click navigation)
      +-- "/services/:serviceName" -> ServiceDetailsPage
           +-- ServiceDetailsHeader
           |    +-- BackButton (link to /v2/)
           |    +-- ServiceName + EngineBadge + StatusDot
           |    +-- ActionBar (Start/Stop, Restart, View YAML, Delete)
           +-- ServiceOverviewPanel
           |    +-- StatusCard (status, container ID, exit code)
           |    +-- ConnectionCard (port, API key with copy, endpoint URL)
           |    +-- ModelCard (model path/name, model size, engine type)
           |    +-- OpenWebUICard (registration status, register/unregister)
           +-- ServiceConfigPanel
           |    +-- ParametersTable (CLI flags as key-value rows)
           |    +-- CommandPreview (rendered command, collapsible)
           |    +-- SaveBar (Discard + Save buttons)
           +-- ServiceLogsPanel
                +-- LogViewer (auto-scroll, monospace, 200-line tail)
                +-- LogControls (pause/resume, polling indicator)
```

---

## 7. API Requirements

### Existing Endpoints (No Changes Needed)

All current endpoints are sufficient for the MVP:

| Feature | Endpoint | Method |
|---|---|---|
| Service config | `/api/services/{name}` | GET |
| Runtime status | `/api/services` | GET (filter by name client-side) |
| Start/Stop | `/api/services/{name}/start\|stop` | POST |
| Logs | `/api/services/{name}/logs?tail=N` | GET |
| Compose preview | `/api/services/{name}/preview` | GET |
| Update config | `/api/services/{name}` | PUT |
| Rename | `/api/services/{name}/rename` | POST |
| Set public port | `/api/services/{name}/set-public-port` | POST |
| Open WebUI | `/api/services/{name}/register-openwebui\|unregister-openwebui` | POST |
| Delete | `/api/services/{name}` | DELETE |
| Flag metadata | `/api/flag-metadata/{template_type}` | GET |

### Recommended New Endpoint (Nice-to-Have)

**`GET /api/services/{name}/status`** -- Combined runtime + config in a single call. Reduces the two-fetch pattern (list all + get config) to one call for polling efficiency:

```json
{
  "service_name": "llamacpp-mymodel",
  "config": {
    "template_type": "llamacpp",
    "port": 3302,
    "api_key": "key-xxx",
    "model_path": "/hf-cache/...",
    "params": { "-ngl": "999", "-c": "32768" },
    "model_size_str": "37.67 GB"
  },
  "runtime": {
    "status": "running",
    "container_id": "abc123def456",
    "exit_code": null,
    "host_port": 3302,
    "openwebui_registered": true
  }
}
```

---

## 8. State Management

### Custom Hook: `useServiceDetails`

Component-local state with a custom hook. No global state library needed:

```jsx
export function useServiceDetails(serviceName) {
  const [config, setConfig] = useState(null)
  const [runtime, setRuntime] = useState(null)
  const [logs, setLogs] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Initial fetch: config + runtime in parallel
  // Polling: runtime every 3s
  // Logs: separate polling (3s), pausable

  return {
    config, runtime, logs,
    loading, error,
    actions: { start, stop, rename, setPublicPort, ... },
    logsControls: { setTail, setPaused }
  }
}
```

### Form State for Editing

```jsx
const [isEditing, setIsEditing] = useState(false)
const [editForm, setEditForm] = useState(null) // copy of config for editing
const [isDirty, setIsDirty] = useState(false)
```

### Transition State

Same pattern as existing `ServicesTable.jsx`:
```jsx
const [transitioning, setTransitioning] = useState(null) // 'starting' | 'stopping'
```

---

## 9. Real-time Features

### Log Streaming: Polling (MVP)

Poll `GET /api/services/{name}/logs?tail=200` every 3 seconds, matching the current vanilla implementation. Only poll when:
- `logsEnabled` is true (not paused)
- Service status is not `not-created`

### Status Polling

Runtime status polled every 3 seconds via `GET /api/services` (filtered client-side) or the proposed `/status` endpoint.

### Future Upgrade Path (SSE)

A future iteration could add Server-Sent Events for real-time log streaming:
```python
@services_bp.route("/api/services/<service_name>/logs/stream")
def stream_logs(service_name):
    def generate():
        container = get_service_container(service_name)
        for line in container.logs(stream=True, follow=True, tail=50):
            yield f"data: {line.decode('utf-8')}\n\n"
    return Response(generate(), mimetype='text/event-stream')
```

---

## 10. Page Layout

### Desktop Layout (>= 1280px) -- Two-column

```
+--[Sidebar 224px]--+--[Main Content Area]-------------------------------------------+
|                    |                                                                 |
|   LLM-Dock        |  [Page Header]                                                  |
|                    |  +-----------------------------------------------------------+  |
|                    |  | <- Back    llamacpp-qwen-7b    [Running *]  llama.cpp     |  |
|   Services  <--   |  +-----------------------------------------------------------+  |
|                    |                                                                 |
|                    |  +--[Left Column ~55%]----+  +--[Right Column ~45%]----------+  |
|                    |  |                        |  |                                |  |
|                    |  | [Controls + Metadata]  |  | [Live Logs]                   |  |
|                    |  | +--------------------+ |  | +----------------------------+|  |
|                    |  | | Status   Running   | |  | | Container Logs             ||  |
|                    |  | | Port     3302      | |  | |                            ||  |
|                    |  | | Container a1b2c3d  | |  | | [log line 1]               ||  |
|                    |  | | Model    7.2 GB    | |  | | [log line 2]               ||  |
|                    |  | | WebUI   Registered | |  | | [log line 3]               ||  |
|                    |  | |                    | |  | | ...                        ||  |
|                    |  | | [Stop] [Restart]   | |  | |                            ||  |
|                    |  | +--------------------+ |  | |                            ||  |
|                    |  |                        |  | |                            ||  |
|                    |  | [Configuration]        |  | |                            ||  |
|                    |  | +--------------------+ |  | |                            ||  |
|                    |  | | * Unsaved changes  | |  | |                            ||  |
|                    |  | |                    | |  | |                            ||  |
|                    |  | | Engine: llama.cpp  | |  | |                            ||  |
|                    |  | | Model Path: [____] | |  | |                            ||  |
|                    |  | | Port:  [3302]      | |  | +----------------------------+|  |
|                    |  | | API Key: [____][G] | |  | Last updated: 14:32:01         |  |
|                    |  | |                    | |  +-------------------------------+  |
|                    |  | | Parameters (3)     | |                                     |
|                    |  | | [-ngl] [999]    x  | |                                     |
|                    |  | | [-c]   [8192]   x  | |                                     |
|                    |  | | [-fa]  []       x  | |                                     |
|                    |  | | [+ Add parameter]  | |                                     |
|                    |  | |                    | |                                     |
|                    |  | | v Command Preview  | |                                     |
|                    |  | |                    | |                                     |
|                    |  | | [Discard] [Save]   | |                                     |
|                    |  | +--------------------+ |                                     |
|                    |  +------------------------+                                     |
+--------------------+-----------------------------------------------------------------+
```

### Tablet Layout (768px - 1279px) -- Single column, stacked

```
+--[Sidebar]--+--[Main Content Area]---------------------------+
|             |                                                 |
|             |  [Page Header - same as desktop]               |
|             |                                                 |
|             |  [Controls + Metadata - full width]             |
|             |  +-------------------------------------------+  |
|             |  | Status: Running   Port: 3302  ...         |  |
|             |  | [Stop] [Restart]                           |  |
|             |  +-------------------------------------------+  |
|             |                                                 |
|             |  [Configuration - full width, collapsed]        |
|             |  +-------------------------------------------+  |
|             |  | v Configuration               * Unsaved   |  |
|             |  |   (fields shown when expanded)             |  |
|             |  +-------------------------------------------+  |
|             |                                                 |
|             |  [Live Logs - full width]                       |
|             |  +-------------------------------------------+  |
|             |  | Container Logs                  [h: 400px] |  |
|             |  | ...                                        |  |
|             |  +-------------------------------------------+  |
+--------------+------------------------------------------------+
```

### Mobile Layout (< 768px) -- Single column, sidebar hidden

```
+--[Full Width]----------------------------------+
|  [Page Header]                                  |
|  <- Back   llamacpp-qwen-7b  [Running]          |
+-------------------------------------------------+
|  [Controls + Metadata - card]                   |
|  Status: Running  |  Port: 3302                 |
|  [Stop]  [Restart]                              |
+-------------------------------------------------+
|  [Configuration - collapsible, collapsed]       |
|  v Configuration                                |
+-------------------------------------------------+
|  [Live Logs - card, 300px max-h]                |
|  Container Logs                                 |
|  ...                                            |
+-------------------------------------------------+
```

---

## 11. Component Specifications

### 11.1 Page Header

```
+-----------------------------------------------------------------------+
|  [<-]  llamacpp-qwen-7b  [copy]    [Running *]    llama.cpp    7.2 GB |
+-----------------------------------------------------------------------+
```

- **Back button**: `fa-arrow-left` icon + "Back to Services" text. `aria-label="Back to services list"`
- **Service name**: `text-2xl font-bold text-white` with copy button
- **Status badge**: Pill-shaped badge with status-specific colors:
  - Running: `bg-green-500/20 text-green-400 border border-green-500/30`
  - Stopped/Exited: `bg-red-500/20 text-red-400 border border-red-500/30`
  - Not Created: `bg-gray-500/20 text-gray-400 border border-gray-500/30`
  - Transitioning: Animated pulse overlay
- **Engine badge**: Reuse existing `EngineBadge` component
- **Header container**: `bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center gap-4 flex-wrap`

### 11.2 Controls + Metadata Card

**Layout**: `bg-gray-800 rounded-lg border border-gray-700 p-5`

**Metadata grid**: `grid grid-cols-2 gap-4 mb-4` on desktop, `grid-cols-1` on mobile.

Each metadata item:
```html
<dt class="text-xs text-gray-500 uppercase tracking-wider mb-1">Status</dt>
<dd class="text-sm text-white font-medium">Running</dd>
```

**Action buttons row**: `flex gap-3 mt-4 pt-4 border-t border-gray-700`

| Button | Style | Icon | Condition |
|--------|-------|------|-----------|
| Start | `bg-green-600 hover:bg-green-700` | `fa-play` | When stopped |
| Stop | `bg-red-600 hover:bg-red-700` | `fa-stop` | When running |
| Restart | `bg-yellow-600 hover:bg-yellow-700` | `fa-rotate-right` | When running |
| View YAML | `bg-gray-600 hover:bg-gray-700` | `fa-code` | Always |
| Delete | `bg-red-600 hover:bg-red-700` | `fa-trash` | Always (requires inline confirmation) |

### 11.3 Configuration Editor

**Container**: `bg-gray-800 rounded-lg border border-gray-700`

**Section header**: `px-5 py-4 border-b border-gray-700 flex justify-between items-center`
- Title: `text-lg font-semibold text-gray-200`
- Unsaved indicator: `text-yellow-400 text-sm` with `fa-circle-exclamation` icon

**Form fields**:
- Labels: `block text-sm font-medium mb-2 text-gray-300`
- Inputs: `w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500`
- Engine shown as disabled chip (not editable)

**Parameters section**: Each row:
```
flex items-center gap-2 bg-gray-900 rounded px-3 py-2
```
- Flag input: `bg-gray-700 border border-gray-600 rounded px-2 py-1 font-mono text-sm w-32`
- Value input: Same style, `flex-1`
- Remove button: `text-gray-500 hover:text-red-400` with `aria-label="Remove parameter -ngl"`

**Command Preview**: Collapsible. `bg-gray-900 rounded p-4 font-mono text-xs text-gray-300 whitespace-pre-wrap`

**Action buttons**:
- Discard: `bg-gray-600 hover:bg-gray-700 px-4 py-2 rounded font-semibold`
- Save: `bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-semibold`
- Disabled state: `opacity-50 cursor-not-allowed`

### 11.4 Live Log Viewer

**Container**: `bg-gray-800 rounded-lg border border-gray-700 flex flex-col`

**Header**: `px-5 py-3 border-b border-gray-700 flex justify-between items-center`
- Title: `text-sm font-semibold text-gray-300 uppercase tracking-wider`
- Polling indicator: `w-2.5 h-2.5 rounded-full bg-green-500` with pulse animation
- Pause/Resume: `fa-pause` / `fa-play` toggle

**Log content area**:
- Container: `flex-1 overflow-auto p-4 min-h-[300px]`
- On desktop: `h-full min-h-[400px]` (stretches to match left column height)
- Text: `font-mono text-sm text-gray-300 whitespace-pre-wrap leading-relaxed`
- Auto-scroll: scroll to bottom unless user has scrolled up or has text selected

**Footer**: `px-5 py-2 border-t border-gray-700 text-xs text-gray-500 flex justify-between`
- Left: "Last updated: {time} | {count} lines"
- Right: Polling status

**Empty states**:
- No container: "Service has not been started. Start the service to see logs." (`text-gray-500 italic`)
- Error: "Failed to load logs: {error}" (`text-red-400`)

---

## 12. State & Feedback Design

### Page Loading States

| State | Visual |
|-------|--------|
| Initial load | Skeleton placeholders: animated `bg-gray-700/50` blocks |
| Data loaded | Content populates, logs begin streaming |
| Service not found | Full-page error with back-to-dashboard link |

### Service Status Transitions

| Transition | Controls | Status Badge | Logs |
|------------|---------|-------------|------|
| Starting | Spinner "Starting...", all buttons disabled | Pulsing amber badge | "Waiting for container..." |
| Running | Stop/Restart appear | Solid green "Running" | Streaming normally |
| Stopping | Spinner "Stopping...", all buttons disabled | Pulsing amber badge | Frozen, last content preserved |
| Stopped | Start appears | Solid red/gray "Stopped" | Last logs remain, polling stops |

### Configuration Save States

| State | Visual |
|-------|--------|
| Clean | Save/Discard disabled (`opacity-50`), no indicator |
| Dirty | Yellow dot + "Unsaved changes", buttons enabled |
| Saving | Spinner "Saving...", fields disabled |
| Success | Green border flash (1.5s), toast "Configuration saved" |
| Error | Red banner inside config section, fields remain editable |

### Delete Confirmation (Inline)

```
Normal:       [...] [Delete]
After click:  [Are you sure? This cannot be undone.]  [Cancel] [Confirm Delete]
```

The delete area expands to `bg-red-900/30 border border-red-700 rounded p-3`.

### Toast Notifications

- Position: `fixed bottom-6 right-6 z-50`
- Success: `bg-green-600 text-white`
- Error: `bg-red-600 text-white`
- Auto-dismiss after 3 seconds
- Slide up + fade in animation

---

## 13. Responsive Design

| Breakpoint | Layout | Notes |
|-----------|--------|-------|
| >= 1280px (xl) | Two-column: left 55% (metadata + config), right 45% (logs) | Side-by-side view |
| 768px - 1279px | Single column, stacked | Config section starts collapsed |
| < 768px | Single column, sidebar hidden | Config collapsed, logs 300px max-h |

### Specific Adjustments
- **Page header**: Wraps to two lines on mobile
- **Metadata grid**: `grid-cols-2` on md+, `grid-cols-1` on mobile
- **Action buttons**: Stack vertically on mobile if overflow
- **Parameter rows**: Flag/value inputs stack vertically on mobile
- **Command preview**: Always collapsible

---

## 14. Accessibility

### Keyboard Navigation
- All interactive elements focusable and operable via keyboard
- Tab order follows visual reading order: Back -> Name copy -> Actions -> Config fields -> Save/Discard -> Log controls
- Enter/Space activates buttons

### ARIA Labels
- Back button: `aria-label="Back to services list"`
- Status badge: `aria-label="Service status: Running"` (dynamic)
- Polling indicator: `aria-label="Log updates active"` / `"Log updates paused"`
- Copy buttons: `aria-label="Copy service name"`, `aria-label="Copy API key"`
- Parameter remove: `aria-label="Remove parameter -ngl"` (dynamic)

### Screen Reader
- `role="status"` with `aria-live="polite"` on status badge
- Log footer uses `aria-live="polite"` (NOT log content -- too noisy)
- Unsaved changes indicator: `role="status"` with `aria-live="polite"`
- Toasts: `role="alert"`

### Focus Indicators
- Inputs: `focus:outline-none focus:border-blue-500`
- Buttons: `focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-800`

---

## 15. Edge Cases and Error Scenarios

### Navigation
- **Service not found**: Show "Service not found" with link back to services list
- **Service deleted externally**: Next poll detects 404 -> toast + redirect to list
- **Service renamed externally**: Same 404 detection

### Configuration Editing
- **Port conflict**: Inline validation error before save; backend returns HTTP 409
- **Invalid parameters**: Display error details from API 400 response
- **Concurrent edit**: Last save wins (no optimistic locking for this iteration)
- **Template type immutability**: Read-only display; backend rejects changes (HTTP 400)

### Lifecycle Control
- **Start failure**: Error toast with backend message
- **Stop timeout**: Remain in "stopping" state until poll confirms
- **Service not created**: Start works normally; Stop/Restart disabled
- **Rapid clicks**: Buttons disabled during transitions

### Logs
- **No container**: Friendly message: "No logs available. Start the service to see container output."
- **Empty logs**: Empty state message
- **Long lines**: Wrap or horizontal scroll

### Rename
- **Running service**: Rename disabled with tooltip explanation
- **Name conflict**: Error from backend displayed
- **URL update**: Browser URL updates to new name after rename

### Network / Auth
- **Auth expired (401)**: Redirect to login
- **Network failure**: Non-blocking warning banner; keep last-known data; resume polling on recovery
- **Backend unavailable**: Error state with retry button

---

## 16. Technical Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Flask catch-all route conflict for SPA | Update `/v2/<path>` to fall back to `index.html` for non-file paths |
| Log polling performance | Only poll when logs panel visible; use `tail` param; future SSE upgrade |
| Race conditions during start/stop | `transitioning` state overrides displayed status during actions |
| React frontend missing login flow | Shared `dashboard_token` in localStorage from vanilla frontend |
| Stale data after config edit | Re-fetch config + compose preview after successful PUT |
| URL encoding for service names | Current validation ensures URL-safe names (alphanumeric + hyphens) |
| Browser back/forward | React Router `BrowserRouter` handles natively |

---

## 17. Visual Design Reference

### Color Palette

| Element | Background | Text | Border |
|---------|-----------|------|--------|
| Page | `bg-gray-900` | -- | -- |
| Cards | `bg-gray-800` | -- | `border-gray-700` |
| Form inputs | `bg-gray-700` | `text-white` | `border-gray-600` |
| Input focus | `bg-gray-700` | `text-white` | `border-blue-500` |
| Code/inset areas | `bg-gray-900` | `text-gray-300` | `border-gray-700` |
| Running | `bg-green-500/20` | `text-green-400` | `border-green-500/30` |
| Stopped | `bg-red-500/20` | `text-red-400` | `border-red-500/30` |
| Transitioning | `bg-yellow-500/20` | `text-yellow-400` | `border-yellow-500/30` |
| Unsaved | -- | `text-yellow-400` | -- |
| Save (primary) | `bg-blue-600` | `text-white` | -- |
| Delete (danger) | `bg-red-600` | `text-white` | -- |
| Start | `bg-green-600` | `text-white` | -- |
| Stop | `bg-red-600` | `text-white` | -- |

### Typography

| Element | Classes |
|---------|---------|
| Service name | `text-2xl font-bold text-white` |
| Section headings | `text-lg font-semibold text-gray-200` |
| Metadata labels | `text-xs text-gray-500 uppercase tracking-wider` |
| Metadata values | `text-sm text-white font-medium` |
| Form labels | `text-sm font-medium text-gray-300` |
| Log text | `font-mono text-sm text-gray-300` |
| Command preview | `font-mono text-xs text-gray-300` |
| Badges | `text-xs font-medium` |

### Icons (FontAwesome)

| Action | Icon |
|--------|------|
| Back | `fa-solid fa-arrow-left` |
| Copy | `fa-solid fa-copy` |
| Start | `fa-solid fa-play` |
| Stop | `fa-solid fa-stop` |
| Restart | `fa-solid fa-rotate-right` |
| Delete | `fa-solid fa-trash` |
| Save | `fa-solid fa-save` |
| View YAML | `fa-solid fa-code` |
| Loading | `fa-solid fa-spinner fa-spin` |
| Unsaved | `fa-solid fa-circle-exclamation` |
| Add param | `fa-solid fa-plus` |
| Remove param | `fa-solid fa-xmark` |
| Collapse/expand | `fa-solid fa-chevron-down` / `fa-chevron-up` |
| Pause logs | `fa-solid fa-pause` |
| Resume logs | `fa-solid fa-play` |
