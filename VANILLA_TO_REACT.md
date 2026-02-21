# Vanilla JS to React - Migration Brainstorm

## Current State

- Flask serves `dashboard/static/index.html` at `/`
- Vanilla JS modules in `dashboard/static/js/` (api, services, logs, gpu, modals, utils, etc.)
- Tailwind CSS via CDN, Font Awesome via CDN
- No build step, no Node.js tooling
- Design mockup at `dashboard/static/design-preview.html` shows the target UI (table rows, sidebar, chat panel)

## Goal

Introduce React alongside the existing vanilla `index.html`, without removing it. The React app will eventually implement the `design-preview.html` design and become the primary frontend.

## Strategy: Side-by-Side

Keep the current vanilla `index.html` working at its current route. Add a React app that builds to a separate directory and is served by Flask on a different route.

### Proposed Structure

```
dashboard/
  static/                  # existing, untouched
    index.html
    js/
      api.js
      services.js
      ...
  frontend/                # new React app (Vite)
    package.json
    vite.config.js
    src/
      main.jsx
      App.jsx
      components/
        ServiceRow.jsx
        GpuBar.jsx
        ChatPanel.jsx
        ActivityFeed.jsx
        ...
      api/
        services.js        # fetch wrappers for Flask API
      hooks/                # (optional, if using hooks)
    dist/                   # Vite build output
      index.html
      assets/
        *.js
        *.css
```

### Flask Routing

```python
# Existing - unchanged
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# New - serve React app
@app.route("/v2")
def index_v2():
    return send_from_directory("frontend/dist", "index.html")

@app.route("/v2/<path:path>")
def serve_v2_static(path):
    return send_from_directory("frontend/dist", path)
```

Both UIs talk to the same `/api/*` endpoints. No backend changes needed.

### Development Workflow

- `cd dashboard/frontend && npm run dev` - Vite dev server with hot reload (proxies API calls to Flask)
- `cd dashboard && python app.py` - Flask serves API + vanilla UI as before
- Vite config proxies `/api/*` to Flask during development:

```js
// vite.config.js
export default {
  server: {
    proxy: {
      '/api': 'http://localhost:5000'
    }
  },
  build: {
    outDir: 'dist'
  }
}
```

### Production / Deployment

- `npm run build` outputs static files to `dashboard/frontend/dist/`
- Flask serves them from `/v2`
- When React version is ready, swap `/` to serve React and move vanilla to `/legacy` (or remove it)

## API Endpoints (already exist, no changes needed)

### Services
- `GET /api/services` - list all
- `GET /api/services/<name>` - get one
- `POST /api/services` - create
- `PUT /api/services/<name>` - update
- `DELETE /api/services/<name>` - delete
- `POST /api/services/<name>/start` - start
- `POST /api/services/<name>/stop` - stop
- `GET /api/services/<name>/logs` - logs
- `GET /api/services/<name>/preview` - preview
- `POST /api/services/<name>/rename` - rename
- `POST /api/services/<name>/set-public-port` - set port
- `PUT /api/services/<name>/set-global-api-key` - set API key

### GPU / System
- `GET /api/gpu` - GPU info
- `GET /api/system/info` - system info
- `GET /api/health` - health check

### Open WebUI
- `POST /api/services/<name>/register-openwebui` - register
- `POST /api/services/<name>/unregister-openwebui` - unregister
- `POST /api/openwebui/restart` - restart

### Other
- `POST /api/auth/verify` - auth
- `GET /api/images/metadata` - image metadata
- `GET /api/flag-metadata/<template_type>` - flag metadata
- `GET /api/global-api-key` - global API key

## Migration Phases

### Phase 1: Scaffold
- `npm create vite@latest frontend -- --template react` inside `dashboard/`
- Add Tailwind CSS to the React app (keeps visual consistency)
- Add proxy config for API calls
- Add Flask route for `/v2`
- Verify: React hello world at `/v2`, vanilla still works at `/`

### Phase 2: Core Layout
- Sidebar navigation
- Top bar with search and actions
- Stats cards row (running count, GPU memory, GPU utilization, disk usage)
- Basic routing within React (if needed, or just conditional rendering)

### Phase 3: Services Table
- Fetch from `GET /api/services` and `GET /api/gpu`
- Render as table rows per design-preview
- Expandable row details
- Status indicators
- Action buttons (start, stop, logs, edit, delete)

### Phase 4: Interactive Features
- Create/edit service modal
- Log viewer
- Bulk selection + action bar
- Chat panel (slide-out)

### Phase 5: Swap
- Move React to `/`, vanilla to `/legacy`
- Eventually remove vanilla

## Open Questions

- Use TypeScript or plain JS? (plain JS is simpler to start)
- State management? (start with just useState/props, add something if it gets painful)
- Component library or hand-roll everything with Tailwind? (hand-roll keeps it simple)
- Keep benchmark page as vanilla or migrate too?
