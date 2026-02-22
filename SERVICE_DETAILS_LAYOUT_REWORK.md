# Service Details Page -- Layout Rework (Config + Reference Sidebar, Logs as Tab)

## Goal

Restructure the service details page so that **configuration is the primary content** with the **Parameter Reference always visible as a right sidebar** (like the old modal layout). Move **logs to a separate route/tab**. Add a **direct link to logs** from the services table.

---

## Current State

```
/v2/services/:serviceName

  [Header: identity + metadata + toolbar]
  [Config ~55%]  [Logs ~45%]     ← two cards side by side
```

- Config and Logs share the same page in a two-column grid
- Parameter Reference is toggled open/closed inside the config card
- No way to navigate directly to logs from the services table

---

## Target State

```
/v2/services/:serviceName          → Config view (default tab)
/v2/services/:serviceName/logs     → Logs view (separate tab)

Config view layout:
  [Header: identity + metadata + toolbar]
  [Tab bar: Configuration | Logs]
  [Config form ~60%]  [Parameter Reference ~40%]    ← always visible sidebar

Logs view layout:
  [Header: identity + metadata + toolbar]
  [Tab bar: Configuration | Logs]
  [Full-width logs panel]
```

---

## Changes Required

### 1. Add Routes for Config and Logs Tabs

**File: `App.jsx`**

Update routing to support the logs sub-route. Both routes render the same `ServiceDetailsPage` wrapper (shared header), but with different content below:

```
<Route path="/services/:serviceName" element={<ServiceDetailsPage />}>
  <Route index element={<ServiceConfigView />} />
  <Route path="logs" element={<ServiceLogsView />} />
</Route>
```

Or alternatively, handle tab switching within `ServiceDetailsPage` using `useLocation` to check if the path ends with `/logs`.

### 2. Rework `ServiceDetailsPage.jsx`

The page becomes a layout shell:

```jsx
<div>
  <ServiceDetailsHeader ... />
  <TabBar activeTab={isLogsRoute ? 'logs' : 'config'} serviceName={serviceName} />
  {isLogsRoute ? (
    <ServiceLogsPanel ... />           // full width
  ) : (
    <ServiceConfigView ... />          // config + reference sidebar
  )}
  {toast && <Toast ... />}
</div>
```

**TabBar component** (simple, inline or extracted):
- Two tabs: "Configuration" and "Logs"
- Uses `<Link>` from react-router-dom for navigation (no full reload)
- Active tab has a bottom border highlight (`border-b-2 border-blue-500 text-white`)
- Inactive tab: `text-gray-400 hover:text-gray-200`
- Container: `flex gap-6 border-b border-gray-700 mb-6`
- Each tab: `pb-3 text-sm font-medium cursor-pointer`

**Remove** from the page layout:
- The two-column `grid grid-cols-1 xl:grid-cols-[55%_45%]` wrapping config + logs
- Direct rendering of `ServiceLogsPanel` on the config view

### 3. Create Config View Layout (Config + Reference Sidebar)

The config tab content should be a two-column layout:

```
Left (~60%): ServiceConfigPanel (form fields, params, command preview, save/discard)
Right (~40%): ParameterReference (always visible, scrollable, full height)
```

**Layout**: `grid grid-cols-1 xl:grid-cols-[60%_40%] gap-6`

On smaller screens (`< xl`), the reference panel stacks below the config form.

### 4. Extract `ParameterReference` from `ServiceConfigPanel.jsx`

Currently, `ParameterReference` is defined inside `ServiceConfigPanel.jsx` and toggled with a button. It needs to become an always-visible sidebar:

**Move these out of `ServiceConfigPanel.jsx`:**
- `ParameterReference` component
- `categorizeFlags` function
- `LLAMACPP_CATEGORIES` map
- `PARAM_TIPS` map
- `ParamTooltip` component

**Into a new file:** `components/ParameterReference.jsx`

This component will be rendered by the page layout (NOT inside the config panel), positioned as the right column.

**Props it needs:**
- `flagMetadata` — the flag data (fetched by config panel or lifted to page level)
- `templateType` — llamacpp or vllm
- `existingFlags` — array of currently configured flag names (to dim already-added ones)
- `onAddFlag(flag, defaultValue)` — callback to add a flag to the config panel's params

**Styling changes for always-visible mode:**
- Remove the `max-h-[300px]` constraint — let it fill available height
- Use `sticky top-0` so it stays visible while scrolling config
- Or use `h-full overflow-y-auto` to fill the column
- Keep the search input and category grouping
- Keep the click-to-add and already-added dimming

**Remove from `ServiceConfigPanel.jsx`:**
- The "Reference" toggle button in the parameters section header
- The `refPanelOpen` state
- The conditional `{refPanelOpen && <ParameterReference ... />}` rendering

### 5. Lift Flag Metadata Fetching

Currently `ServiceConfigPanel` fetches flag metadata internally. Since `ParameterReference` is now a sibling (not a child), the metadata fetch should be lifted:

**Option A (recommended):** Lift to `ServiceDetailsPage` level
- Fetch flag metadata there based on `config.template_type`
- Pass `flagMetadata` down to both `ServiceConfigPanel` and `ParameterReference`

**Option B:** Fetch in both components (wasteful, not recommended)

Also lift `existingFlags` communication:
- `ServiceConfigPanel` needs to expose its current params list (or accept a callback)
- The page can manage this via a shared state or callback pattern

**Simplest approach:** Have `ServiceConfigPanel` accept an `onParamsChange(flagsList)` callback that it calls whenever params change, and the page passes the current flags list to `ParameterReference`.

### 6. Update `ServiceLogsPanel.jsx`

Minor changes for full-width display:
- Remove `min-h-[300px] xl:min-h-[400px]` constraints
- Use `min-h-[500px]` or `flex-1` to fill available space since it now has the full width
- The component itself is mostly fine as-is

### 7. Add Logs Link to `ServicesTable.jsx`

Add a logs icon button to the `ActionButtons` component for non-infra services:

```jsx
<button
  onClick={e => { e.stopPropagation(); navigate(`/services/${service.name}/logs`) }}
  className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-purple-400 cursor-pointer"
  title="View logs"
>
  {/* terminal/logs icon */}
</button>
```

Place it between the Edit (pencil) and Delete buttons. Use a terminal or file-lines icon to suggest logs.

**Note:** `ServicesTable` already uses `useNavigate`, so this is straightforward.

### 8. Update Loading Skeleton

The `LoadingSkeleton` in `ServiceDetailsPage.jsx` currently shows the two-column config+logs layout. Update it to show the tab bar skeleton and config+reference layout instead.

---

## Component Architecture (After)

```
App
└── Routes
    ├── "/" → ServicesTable (+ logs icon per row)
    └── "/services/:serviceName" → ServiceDetailsPage
         ├── ServiceDetailsHeader (unchanged)
         ├── TabBar (new: Configuration | Logs)
         ├── [if config tab]:
         │    ├── ServiceConfigPanel (~60%, left column)
         │    └── ParameterReference (~40%, right column, always visible)
         └── [if logs tab]:
              └── ServiceLogsPanel (full width)
```

---

## Files to Modify

| File | Action |
|------|--------|
| `App.jsx` | Add nested route for `/services/:serviceName/logs` |
| `ServiceDetailsPage.jsx` | Add tab bar, conditional rendering config vs logs, lift flag metadata fetch |
| `ServiceConfigPanel.jsx` | Remove ParameterReference and related code, remove refPanelOpen toggle, accept onParamsChange callback |
| `ServiceLogsPanel.jsx` | Minor height adjustments for full-width mode |
| `ServicesTable.jsx` | Add logs icon button to ActionButtons |
| **New:** `ParameterReference.jsx` | Extracted component with always-visible layout |

---

## Files NOT to Change

- `ServiceDetailsHeader.jsx` — unchanged
- `useServiceDetails.js` — unchanged
- `api.js` — unchanged
- Flask backend — unchanged

---

## Visual Reference (Target: Config Tab)

```
+--[Sidebar]--+--[Main Content]--------------------------------------------------+
|             |                                                                    |
|             |  [Header: <- Back  service-name  Running  llama.cpp  7.2 GB]      |
|             |  [        Port: 3302  API Key: key-9e07...  WebUI: Registered]    |
|             |  [        [Stop] [Restart] | [Set as Public] [View YAML] [Unreg]] |
|             |                                                                    |
|             |  [ Configuration ]  [ Logs ]                                       |
|             |  ─────────────────────────────────────────────────────────────      |
|             |                                                                    |
|             |  +--[Config ~60%]----------------+  +--[Reference ~40%]--------+   |
|             |  |                               |  |                          |   |
|             |  |  Port: [3302]                 |  |  [Search flags...]       |   |
|             |  |  API Key: [key...] [Global]   |  |                          |   |
|             |  |                               |  |  CONTEXT                 |   |
|             |  |  Parameters (4)  [+ Add]      |  |  -c  --ctx-size   128000 |   |
|             |  |  [-b]  [256]            x     |  |  Context length...       |   |
|             |  |  [-c]  [32768]          x     |  |                          |   |
|             |  |  [-ngl] [999]           x     |  |  GPU                     |   |
|             |  |  [-ub] [256]            x     |  |  -ngl --n-gpu-layers 999 |   |
|             |  |                               |  |  Number of layers...     |   |
|             |  |  v Command Preview            |  |                          |   |
|             |  |                               |  |  BATCHING                |   |
|             |  |  [Discard] [Save]             |  |  -b  --batch-size   256  |   |
|             |  |                               |  |  ...                     |   |
|             |  +-------------------------------+  +--[scrollable]------------+   |
+--------------+-------------------------------------------------------------------+
```

## Visual Reference (Target: Logs Tab)

```
+--[Sidebar]--+--[Main Content]--------------------------------------------------+
|             |                                                                    |
|             |  [Header: same as above]                                          |
|             |                                                                    |
|             |  [ Configuration ]  [ Logs ]                                       |
|             |  ──────────────────═══════════════════════════════════════════      |
|             |                                                                    |
|             |  +--[Full-width Logs]------------------------------------------+   |
|             |  |  Container Logs                              [refresh] [||] |   |
|             |  |                                                             |   |
|             |  |  [log line 1]                                               |   |
|             |  |  [log line 2]                                               |   |
|             |  |  [log line 3]                                               |   |
|             |  |  ...                                                        |   |
|             |  |                                                             |   |
|             |  |  Last updated: 14:32:01 | 200 lines       Polling every 3s |   |
|             |  +-------------------------------------------------------------+   |
+--------------+-------------------------------------------------------------------+
```

---

## Acceptance Criteria

1. Configuration tab is the default view at `/v2/services/:serviceName`
2. Logs tab is at `/v2/services/:serviceName/logs` (deep-linkable)
3. Tab bar switches between views without full page reload
4. Parameter Reference is always visible as a right sidebar on the config tab
5. Parameter Reference search, category grouping, click-to-add, and tooltips all work
6. Reference panel scrolls independently and fills available height
7. Config form (port, API key, params, command preview, save/discard) works as before
8. Logs panel renders full-width on the logs tab
9. Services table has a logs icon that navigates directly to `/v2/services/:name/logs`
10. Header and toolbar are shared across both tabs (not re-rendered)
11. Browser back/forward works correctly between tabs and between services list
12. Loading skeleton reflects the new layout
13. Responsive: on smaller screens, reference stacks below config; logs are always full-width
