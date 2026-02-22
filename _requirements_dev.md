# Service Details Page -- Technical Requirements

## 1. Technical Analysis of Current State

### Vanilla Frontend (Primary -- `/dashboard/static/`)
- **Entry point:** `index.html` served at `/` via Flask `send_from_directory`
- **JS modules:** All loaded as plain `<script>` tags (no bundler, no ES modules):
  - `api.js` -- `fetchAPI()` wrapper, auth token management, login modal
  - `services.js` -- `loadServices()`, `renderServices()`, card-based HTML generation via template literals
  - `logs.js` -- Log modal with 3-second polling (`setInterval`), tail=200 lines
  - `service-modal/create-service.js` -- Create/Update modal (dual-mode), smart defaults, command preview
  - `service-modal/param-rows.js` -- Dynamic CLI flag rows, copy-from-service modal
  - `service-modal/param-reference.js` -- Inline parameter reference panel
  - `utils.js` -- Toast, clipboard, global API key, image metadata, `escapeAttr()`/`escapeHtml()`
  - `modal-manager.js` -- Scroll lock with reference counting for stacked modals
  - `init.js` -- Bootstrap, token verification, 3-second auto-refresh for services + GPU
  - `gpu.js` -- GPU stats rendering
  - `system-info.js` -- System info rendering
- **State management:** Global variables (`currentLogsService`, `_transitioningServices`, `serviceToDelete`, etc.)
- **Routing:** None. Single-page with modals for all interactions.
- **Styling:** TailwindCSS via CDN, FontAwesome icons, dark theme (gray-800/900 backgrounds)

### React Frontend (Secondary -- `/dashboard/frontend/`)
- **Served at:** `/v2` and `/v2/<path>` via Flask `send_from_directory("frontend/dist", ...)`
- **Build:** Vite + React 18 + `@tailwindcss/vite` plugin, `base: '/v2/'`
- **Components:**
  - `App.jsx` -- Layout shell: `Sidebar` + `Header` + content area with `GpuMonitor` + `ServicesTable`
  - `ServicesTable.jsx` -- Table-based service list, 3-second polling, start/stop/delete actions, toast for errors
  - `GpuMonitor.jsx` -- GPU polling with 60-second rolling history
  - `GpuStats.jsx` / `GpuGraph.jsx` -- GPU stat cards and sparkline graphs
  - `Sidebar.jsx` -- Static sidebar with logo, "Services" nav link, user section
  - `Header.jsx` -- Empty placeholder
- **API layer:** `api.js` -- `fetchAPI()` wrapper, token from `localStorage`, same pattern as vanilla
- **State:** Component-local `useState`/`useEffect` with polling. No global state management (no Redux/Zustand/Context).
- **Routing:** None. No `react-router-dom` installed. Single view.
- **Missing features vs. vanilla:** No login flow, no create/edit service modal, no logs modal, no rename, no preview YAML, no global API key, no benchmarks link

### Backend API (Flask -- `/dashboard/routes/services.py`, `/dashboard/routes/openwebui.py`)
Existing endpoints relevant to a details page:

| Endpoint | Method | Returns |
|---|---|---|
| `GET /api/services` | GET | All services with runtime status (Docker container state, ports, API keys, model sizes, Open WebUI registration) |
| `GET /api/services/{name}` | GET | Service config from `services.json` (template_type, params, model_path/model_name, alias, port, api_key, model_size) |
| `PUT /api/services/{name}` | PUT | Update service config, rebuild compose |
| `POST /api/services/{name}/start` | POST | Start container via `docker compose up -d` |
| `POST /api/services/{name}/stop` | POST | Stop container via `container.stop()` |
| `GET /api/services/{name}/logs` | GET | Container logs (tail=N, timestamps=True, returns JSON with `logs` string) |
| `GET /api/services/{name}/preview` | GET | Rendered docker-compose YAML for this service |
| `POST /api/services/{name}/rename` | POST | Rename service (must be stopped) |
| `POST /api/services/{name}/set-public-port` | POST | Assign port 3301, swap if needed |
| `POST /api/services/{name}/register-openwebui` | POST | Register with Open WebUI |
| `POST /api/services/{name}/unregister-openwebui` | POST | Unregister from Open WebUI |
| `PUT /api/services/{name}/set-global-api-key` | PUT | Replace service API key with global key |
| `GET /api/flag-metadata/{template_type}` | GET | Flag metadata and mandatory fields |
| `DELETE /api/services/{name}` | DELETE | Stop, remove container, remove from DB, rebuild compose |

### Data Model (`services.json`)
Each service entry contains:
```json
{
  "template_type": "llamacpp" | "vllm",
  "alias": "string",
  "port": 3302,
  "api_key": "key-xxx",
  "model_path": "/hf-cache/..." | null,     // llamacpp only
  "model_name": "org/model-name" | null,     // vllm only
  "params": { "-ngl": "999", "-c": "32768" },
  "model_size": 40447959840,
  "model_size_str": "37.67 GB"
}
```

Runtime status from Docker (returned by `GET /api/services`):
```json
{
  "name": "llamacpp-mymodel",
  "status": "running" | "exited" | "not-created",
  "exit_code": null | 139,
  "container_id": "abc123def456",
  "host_port": 3302,
  "api_key": "key-xxx",
  "openwebui_registered": true,
  "model_size": 40447959840,
  "model_size_str": "37.67 GB"
}
```

### Reusable Code
- **Backend:** All API endpoints already exist. No new backend routes are strictly required for an MVP details page.
- **React `fetchAPI()`:** Directly reusable, same auth pattern.
- **React `ServicesTable.jsx`:** Polling pattern, action handlers (`handleStart`/`handleStop`/`handleDelete`), transition state management -- all reusable patterns.
- **Vanilla `logs.js`:** Polling pattern for logs is the reference implementation.


## 2. Architecture Decision: React vs Vanilla

**Recommendation: Build in React (the `/v2` frontend).**

**Rationale:**

| Factor | Vanilla | React |
|---|---|---|
| Component composition | Template literals, manual DOM | JSX components, composable |
| State management | Global variables, manual DOM updates | `useState`/`useEffect`, declarative rendering |
| Routing | None; would require hash routing or full rewrite | Add `react-router-dom`; straightforward |
| Form handling | Manual DOM queries (`getElementById`) | Controlled components, form state in React |
| Real-time updates | `setInterval` + manual DOM patching | `useEffect` cleanup, polling or SSE with state |
| Code organization | Flat JS files loaded in order | Module imports, component tree |
| Effort to add detail page | High -- need hash router, manual state, template strings for complex layout | Medium -- add router, create components |
| Existing detail-page patterns | Edit modal exists but is 700+ lines of imperative DOM manipulation | Clean component patterns in ServicesTable |

Adding a details page to the vanilla frontend would require either: (a) building a hash-based router and managing complex state with global variables, or (b) opening yet another modal (the current approach), which does not meet the "dedicated page" requirement. The React frontend already has a component architecture that supports this naturally.

**Gap analysis for React frontend:**
The React frontend is currently missing: login flow, create/edit modals, logs, rename, preview, etc. However, the details page can be built as a self-contained feature. Missing features (login) can be addressed incrementally -- for now, the React frontend can share the same `dashboard_token` in localStorage as the vanilla frontend.

**Migration note:** This is not a full migration. The vanilla frontend remains at `/` and the React frontend at `/v2`. The details page is a new route under `/v2/services/:name`.


## 3. Component Architecture

### Route Structure
```
/v2/                       -> App -> ServicesTable (list view)
/v2/services/:serviceName  -> App -> ServiceDetails (detail view)
```

### Component Tree
```
App
 +-- Sidebar (updated: nav links to list + active state awareness)
 +-- Header
 +-- Routes
      +-- "/" -> ServicesTable (existing, updated with row click navigation)
      +-- "/services/:serviceName" -> ServiceDetailsPage
           +-- ServiceDetailsHeader
           |    +-- BackButton (link to /v2/)
           |    +-- ServiceName + EngineBadge + StatusDot
           |    +-- ActionBar (Start/Stop, Edit, Delete, SetPublicPort)
           +-- ServiceOverviewPanel
           |    +-- StatusCard (status, container ID, uptime, exit code)
           |    +-- ConnectionCard (port, API key with copy, endpoint URL)
           |    +-- ModelCard (model path/name, model size, engine type)
           |    +-- OpenWebUICard (registration status, register/unregister)
           +-- ServiceConfigPanel
           |    +-- ParametersTable (CLI flags in a readable table)
           |    +-- ComposePreview (rendered YAML, copy button)
           +-- ServiceLogsPanel
                +-- LogViewer (auto-scroll, tail control, polling indicator)
                +-- LogControls (tail count, pause/resume, clear)
```

### Key Props and State

**ServiceDetailsPage:**
```jsx
// URL param
const { serviceName } = useParams()

// State
const [runtimeStatus, setRuntimeStatus] = useState(null)   // from GET /api/services (filtered)
const [serviceConfig, setServiceConfig] = useState(null)    // from GET /api/services/{name}
const [logs, setLogs] = useState('')                         // from GET /api/services/{name}/logs
const [composeYaml, setComposeYaml] = useState(null)        // from GET /api/services/{name}/preview
const [transitioning, setTransitioning] = useState(null)     // 'starting' | 'stopping' | null
const [logsEnabled, setLogsEnabled] = useState(true)         // pause/resume log polling
const [logTail, setLogTail] = useState(200)                  // number of log lines to fetch
const [error, setError] = useState(null)
```

**Data fetching strategy:**
- On mount: Fetch `GET /api/services/{name}` (config) and `GET /api/services` (runtime status, filtered by name). Both requests in parallel.
- Polling (3s): Re-fetch runtime status via `GET /api/services` and filter. This keeps status, port, Open WebUI registration current.
- Log polling (3s): Fetch `GET /api/services/{name}/logs?tail={logTail}` when `logsEnabled` is true and container exists.
- Compose preview: Fetch once on mount. Re-fetch after config changes (edit/save).


## 4. API Requirements

### Existing Endpoints to Reuse (No Changes Needed)
All current endpoints are sufficient for the details page MVP. Summary of usage:

| Feature | Endpoint | Notes |
|---|---|---|
| Service config | `GET /api/services/{name}` | Returns full config from services.json |
| Runtime status | `GET /api/services` | Filter client-side by name. Returns status, container_id, host_port, api_key, openwebui_registered |
| Start/Stop | `POST /api/services/{name}/start\|stop` | Existing lifecycle endpoints |
| Logs | `GET /api/services/{name}/logs?tail=N` | Returns JSON `{ logs: string, lines: int, timestamp: string }` |
| Compose preview | `GET /api/services/{name}/preview` | Returns rendered YAML |
| Rename | `POST /api/services/{name}/rename` | Body: `{ new_name: string }` |
| Set public port | `POST /api/services/{name}/set-public-port` | Assigns port 3301 |
| Open WebUI | `POST /api/services/{name}/register-openwebui\|unregister-openwebui` | Toggle registration |
| Update config | `PUT /api/services/{name}` | Full config update |
| Delete | `DELETE /api/services/{name}` | Stops, removes, rebuilds compose |
| Flag metadata | `GET /api/flag-metadata/{template_type}` | For edit form |
| Global API key | `GET /api/global-api-key` | For "use global key" button |

### Recommended New Endpoint

**`GET /api/services/{name}/status`** -- Returns combined runtime + config data for a single service.

Currently, getting full details requires two API calls: `GET /api/services` (list all, filter client-side) + `GET /api/services/{name}` (config only). A dedicated status endpoint would be more efficient for the details page polling:

```python
# routes/services.py
@services_bp.route("/api/services/<service_name>/status", methods=["GET"])
@require_auth
def get_service_status(service_name):
    """Get combined runtime status and config for a single service"""
    compose_mgr = ComposeManager(COMPOSE_FILE)
    config = compose_mgr.get_service_from_db(service_name)
    if not config:
        return jsonify({"error": f'Service "{service_name}" not found'}), 404

    container = get_service_container(service_name)
    # ... build combined response with runtime status + config
```

Response shape:
```json
{
  "service_name": "llamacpp-mymodel",
  "config": {
    "template_type": "llamacpp",
    "alias": "mymodel",
    "port": 3302,
    "api_key": "key-xxx",
    "model_path": "/hf-cache/...",
    "params": { "-ngl": "999", "-c": "32768" },
    "model_size": 40447959840,
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

**Priority:** Nice-to-have for MVP. The details page can work without it by using the existing two endpoints. Add if the double-fetch becomes a performance concern.

### Data Contracts

No changes needed to existing response schemas. The React frontend already consumes these formats in `ServicesTable.jsx`.


## 5. Real-time Features

### Log Streaming Approach

**Recommendation: Polling (same as current implementation), with SSE as a future upgrade.**

**Analysis of options:**

| Approach | Pros | Cons |
|---|---|---|
| Polling (current) | Simple, proven, works with Flask, no infrastructure changes | ~3s latency, unnecessary requests when idle, bandwidth for full log payload each time |
| SSE (Server-Sent Events) | True real-time, lower bandwidth (delta updates), native browser support | Requires Flask streaming response or background thread, connection management, proxy considerations |
| WebSocket | Bidirectional, lowest latency | Overkill for read-only logs, requires Flask-SocketIO or similar, more complex |

**MVP: Polling at 3-second intervals** (matching current vanilla implementation).

Implementation in React:
```jsx
useEffect(() => {
  if (!logsEnabled || runtimeStatus?.status === 'not-created') return

  let active = true
  async function fetchLogs() {
    try {
      const data = await fetchAPI(`/services/${serviceName}/logs?tail=${logTail}`)
      if (active) setLogs(data.logs || '')
    } catch (err) { /* handle */ }
  }
  fetchLogs()
  const id = setInterval(fetchLogs, 3000)
  return () => { active = false; clearInterval(id) }
}, [serviceName, logTail, logsEnabled, runtimeStatus?.status])
```

**Future upgrade path to SSE:**
```python
# Flask SSE endpoint (future)
@services_bp.route("/api/services/<service_name>/logs/stream")
@require_auth
def stream_logs(service_name):
    def generate():
        container = get_service_container(service_name)
        for line in container.logs(stream=True, follow=True, tail=50):
            yield f"data: {line.decode('utf-8')}\n\n"
    return Response(generate(), mimetype='text/event-stream')
```

### Status Polling

Runtime status polling at 3-second intervals, same as `ServicesTable.jsx`. On the details page, we only need status for a single service, so we can either:
1. Filter from `GET /api/services` (reuse existing endpoint)
2. Use the proposed `GET /api/services/{name}/status` endpoint

Both are lightweight enough for 3-second polling.


## 6. Routing Strategy

### Adding React Router

Install `react-router-dom`:
```bash
cd dashboard/frontend && npm install react-router-dom
```

### Route Configuration

Update `App.jsx`:
```jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'

function App() {
  return (
    <BrowserRouter basename="/v2">
      <div className="flex h-screen bg-gray-900 text-gray-100">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <div className="flex-1 overflow-auto p-6">
            <Routes>
              <Route path="/" element={<><GpuMonitor /><ServicesTable /></>} />
              <Route path="/services/:serviceName" element={<ServiceDetailsPage />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

Key config: `basename="/v2"` aligns with Vite's `base: '/v2/'`.

### Flask Catch-all for Client-side Routing

The existing Flask routes already serve the React app:
```python
@app.route("/v2")
def serve_v2_index():
    return send_from_directory("frontend/dist", "index.html")

@app.route("/v2/<path:whatever>")
def serve_v2_static(whatever):
    return send_from_directory("frontend/dist", whatever)
```

However, the catch-all `serve_v2_static` currently serves files from `frontend/dist`. For client-side routing to work (e.g., direct navigation to `/v2/services/llamacpp-mymodel`), the catch-all must fall back to `index.html` when the file is not found:

```python
@app.route("/v2/<path:whatever>")
def serve_v2_static(whatever):
    # Try to serve as static file first, fall back to index.html for client-side routes
    dist_dir = os.path.join(app.root_path, "frontend", "dist")
    file_path = os.path.join(dist_dir, whatever)
    if os.path.isfile(file_path):
        return send_from_directory("frontend/dist", whatever)
    return send_from_directory("frontend/dist", "index.html")
```

### Navigation Patterns

**List -> Details:**
- Click on a service row in `ServicesTable` navigates to `/v2/services/{serviceName}`
- Use `useNavigate()` from react-router-dom:
  ```jsx
  const navigate = useNavigate()
  // In ServiceRow:
  <tr onClick={() => navigate(`/services/${svc.name}`)} className="cursor-pointer ...">
  ```

**Details -> List:**
- Back button at top of details page: `<Link to="/">` or `navigate(-1)`
- Browser back button works naturally with client-side routing

**Details -> Details (switching services):**
- Sidebar could show a compact service list for quick switching
- Or: breadcrumb "Services > {serviceName}" where "Services" links back

**Post-action navigation:**
- After deleting a service from the details page, navigate back to the list: `navigate('/')`
- After renaming, update the URL: `navigate(`/services/${newName}`, { replace: true })`


## 7. State Management

### Approach: Component-local State + Custom Hook

No global state library needed. The details page is self-contained and does not share state with other pages. Extract data-fetching into a custom hook for clean separation:

```jsx
// hooks/useServiceDetails.js
export function useServiceDetails(serviceName) {
  const [config, setConfig] = useState(null)
  const [runtime, setRuntime] = useState(null)
  const [logs, setLogs] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Initial fetch: config + runtime in parallel
  // Polling: runtime every 3s
  // Logs: separate polling, pausable

  return {
    config, runtime, logs,
    loading, error,
    actions: { start, stop, rename, setPublicPort, ... },
    logsControls: { setTail, setPaused }
  }
}
```

### Form State for Edit Mode

If the details page includes inline editing (e.g., editing parameters directly on the page), use a local `editState`:

```jsx
const [isEditing, setIsEditing] = useState(false)
const [editForm, setEditForm] = useState(null) // copy of config for editing

function startEditing() {
  setEditForm({ ...config })
  setIsEditing(true)
}

function saveEdit() {
  await fetchAPI(`/services/${serviceName}`, {
    method: 'PUT',
    body: JSON.stringify(editForm)
  })
  setIsEditing(false)
  // Re-fetch config
}
```

### Transitioning / Optimistic Updates

For start/stop actions, use the same pattern as `ServicesTable.jsx`:
```jsx
const [transitioning, setTransitioning] = useState(null) // 'starting' | 'stopping'

async function handleStart() {
  setTransitioning('starting')
  try {
    await fetchAPI(`/services/${serviceName}/start`, { method: 'POST' })
  } catch { /* will be caught by next poll */ }
  // Poll will update runtime status
  setTransitioning(null)
}
```


## 8. Error Handling Patterns

### API Error Handling

Reuse the existing `fetchAPI()` pattern from `dashboard/frontend/src/api.js`:
- 401 -> Clear token, throw "Authentication failed"
- Non-OK -> Parse JSON error body, throw with message
- Network error -> Throw with fetch error message

### Details Page Error States

| Scenario | Handling |
|---|---|
| Service not found (404 from config endpoint) | Show "Service not found" message with link back to list |
| Service deleted while viewing | Polling will get 404; show toast "Service was deleted" and redirect to list |
| Auth expired during polling | `fetchAPI` clears token; redirect to login (or show login overlay) |
| Container not created (logs endpoint returns 404) | Show "Container not created. Start the service to see logs." in logs panel |
| Start/stop fails | Show error toast (same pattern as `ServicesTable.jsx`) |
| Network error during polling | Show warning banner but keep displaying last-known data; retry on next interval |
| Rename fails (409 -- name taken, or service running) | Show inline error in rename form |

### Error Boundary

Wrap `ServiceDetailsPage` in a React error boundary to catch unexpected rendering errors:
```jsx
<Route path="/services/:serviceName" element={
  <ErrorBoundary fallback={<ServiceDetailsError />}>
    <ServiceDetailsPage />
  </ErrorBoundary>
} />
```

### Toast Notifications

Reuse or extract the `Toast` component from `ServicesTable.jsx` (currently defined inline). Move to a shared location:
```
components/Toast.jsx   -- reusable toast component
```


## 9. Technical Risks and Mitigations

### Risk 1: Flask catch-all route conflict
**Problem:** The `/v2/<path:whatever>` route currently serves static files. Adding client-side routing means some paths (e.g., `/v2/services/llamacpp-mymodel`) won't match actual files and will 404.
**Mitigation:** Update the Flask catch-all to fall back to `index.html` for non-file paths (see Section 6). This is a standard SPA pattern.

### Risk 2: Log polling performance
**Problem:** Fetching 200 lines of logs every 3 seconds generates repeated large payloads. With multiple tabs or long logs, this could burden the backend.
**Mitigation:** (a) Only poll logs when the logs panel is visible (e.g., collapsed panels don't poll). (b) Add a `since` parameter to the logs endpoint to fetch only new lines (future optimization). (c) Use the existing `tail` parameter -- 200 lines is reasonable.

### Risk 3: Race conditions during start/stop
**Problem:** User clicks Start, polling fetches stale "stopped" status, UI flickers.
**Mitigation:** Use `transitioning` state to override displayed status during actions (same pattern as existing `ServicesTable.jsx`). After action completes, poll a few times with short interval before clearing transitioning state.

### Risk 4: React frontend missing login flow
**Problem:** If `dashboard_token` is not in localStorage, the React frontend has no login UI.
**Mitigation:** For MVP, user logs in via vanilla frontend at `/`, which sets `dashboard_token` in localStorage. React frontend at `/v2` reads the same token. Both run on the same origin, so localStorage is shared. A React login component can be added later.

### Risk 5: Stale data after config edit
**Problem:** After editing params via the details page, the compose YAML preview and runtime config may be stale.
**Mitigation:** After a successful `PUT /api/services/{name}`, re-fetch both config and compose preview. The compose file is rebuilt server-side on every PUT, so the preview endpoint will return updated YAML.

### Risk 6: URL encoding for service names
**Problem:** Service names contain hyphens (e.g., `llamacpp-qwen3-vl-8b-q8`), which are URL-safe. However, future names could theoretically contain characters that need encoding.
**Mitigation:** Current service name validation (alphanumeric + hyphens + underscores, max 63 chars) ensures URL-safe names. No special encoding needed. The `useParams()` hook handles URL decoding automatically.

### Risk 7: Browser back/forward with React Router
**Problem:** Users may expect browser back button to work after navigating between list and details.
**Mitigation:** React Router with `BrowserRouter` handles this natively. The Flask catch-all ensures direct URL access and refresh also work.

### Risk 8: Build and deployment
**Problem:** React changes require `npm run build` to update `frontend/dist/`.
**Mitigation:** This is the existing workflow for the React frontend. No change. For development, `npm run dev` with Vite proxy (`/api -> http://localhost:5000`) provides hot reload.
