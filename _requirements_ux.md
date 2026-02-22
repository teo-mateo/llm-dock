# Service Details Page - UX Design Specification

## 1. Design Principles

1. **Single-page consolidation**: Configuration editing, service controls, and live logs must coexist on one page without overwhelming the user. Each concern occupies a visually distinct zone.
2. **Progressive disclosure**: Show essential information at a glance (status, controls, metadata). Advanced details (parameters, command preview, logs) are available without extra navigation but can be collapsed.
3. **Inline context**: The user should never lose sight of what service they are working on. The service name, status, and engine type remain persistently visible in the page header.
4. **Non-destructive editing**: Configuration changes require an explicit save action. Unsaved changes are clearly indicated. Navigation away warns the user if edits are pending.
5. **Real-time awareness**: Service status and logs update live. The user always knows whether the service is running, stopped, or transitioning.
6. **Consistent vocabulary**: Reuse existing color meanings, component shapes, and interaction patterns from the dashboard to minimize cognitive load.

---

## 2. User Flow Diagrams

### 2.1 Navigating to the Details Page

```
Dashboard (Services Table)
  |
  +--> User clicks pencil icon (edit button) on a service row
  |      |
  |      +--> Browser navigates to /services/{name}
  |             (full page transition, not a modal)
  |
  +--> User clicks service name text (link)
         |
         +--> Same navigation to /services/{name}
```

### 2.2 Details Page Primary Flow

```
Details Page Loads
  |
  +--> Header shows: [Back arrow] [Service Name] [Status Badge] [Engine Badge]
  |
  +--> Three-zone layout renders:
  |      Zone A (left/top): Service Controls + Metadata
  |      Zone B (left/bottom or center): Configuration Editor
  |      Zone C (right or bottom): Live Log Viewer
  |
  +--> Polling begins for status + logs (3s interval, matching dashboard)
```

### 2.3 Editing Configuration

```
User modifies a field (port, model path, parameter, API key)
  |
  +--> "Unsaved changes" indicator appears in the config section header
  |    Save and Discard buttons become enabled
  |
  +--> User clicks "Save Changes"
  |      |
  |      +--> Validation runs client-side
  |      |      |
  |      |      +--> (fail) Inline error message on the invalid field
  |      |      +--> (pass) PUT /api/services/{name} request fires
  |      |             |
  |      |             +--> (success) Toast: "Configuration saved"
  |      |             |    Unsaved indicator disappears
  |      |             +--> (error) Inline error banner in config section
  |      |
  +--> User clicks "Discard Changes"
         |
         +--> Fields revert to last-saved values
         +--> Unsaved indicator disappears
```

### 2.4 Start/Stop Flow

```
User clicks "Start" button
  |
  +--> Button shows spinner + "Starting..."
  +--> POST /api/services/{name}/start
  |      |
  |      +--> (success) Status badge transitions to "Running" (green)
  |      |    Logs begin streaming
  |      +--> (error) Toast: "Failed to start: {message}"
  |
User clicks "Stop" button
  |
  +--> Confirmation inline: "Stop service?" [Confirm] [Cancel]
  +--> POST /api/services/{name}/stop
         |
         +--> Status badge transitions to "Stopped" (yellow/red)
```

### 2.5 Back Navigation

```
User clicks back arrow OR browser back
  |
  +--> If unsaved changes exist:
  |      "You have unsaved changes. Discard?" [Stay] [Discard & Leave]
  |
  +--> Navigate back to dashboard (services table view)
```

---

## 3. Page Layout

### 3.1 Desktop Layout (>= 1280px)

```
+--[Sidebar 224px]--+--[Main Content Area]-------------------------------------------+
|                    |                                                                 |
|   LLM-Dock        |  [Page Header]                                                  |
|   v1.0.0          |  +-----------------------------------------------------------+  |
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
|                    |  | |                    | |  | | [log line 4]               ||  |
|                    |  | | [Stop] [Restart]   | |  | | ...                        ||  |
|                    |  | +--------------------+ |  | |                            ||  |
|                    |  |                        |  | |                            ||  |
|                    |  | [Configuration]        |  | |                            ||  |
|                    |  | +--------------------+ |  | |                            ||  |
|                    |  | | * Unsaved changes  | |  | |                            ||  |
|                    |  | |                    | |  | |                            ||  |
|                    |  | | Engine: llama.cpp  | |  | |                            ||  |
|                    |  | | Model Path: [____] | |  | |                            ||  |
|                    |  | | Port:  [3302]      | |  | |                            ||  |
|                    |  | | API Key: [____][G] | |  | +----------------------------+|  |
|                    |  | |                    | |  | Last updated: 14:32:01         |  |
|                    |  | | Parameters (3)     | |  +-------------------------------+  |
|                    |  | | [-ngl] [999]    x  | |                                     |
|                    |  | | [-c]   [8192]   x  | |                                     |
|                    |  | | [-fa]  []       x  | |                                     |
|                    |  | | [+ Add parameter]  | |                                     |
|                    |  | |                    | |                                     |
|                    |  | | Command Preview    | |                                     |
|                    |  | | +----------------+ | |                                     |
|                    |  | | | llama-server   | | |                                     |
|                    |  | | | -m /path/...   | | |                                     |
|                    |  | | | --alias ...    | | |                                     |
|                    |  | | +----------------+ | |                                     |
|                    |  | |                    | |                                     |
|                    |  | | [Discard] [Save]   | |                                     |
|                    |  | +--------------------+ |                                     |
|                    |  +------------------------+                                     |
|                    |                                                                 |
|   [User/Logout]   |                                                                 |
+--------------------+-----------------------------------------------------------------+
```

### 3.2 Medium Layout (768px - 1279px)

```
+--[Sidebar]--+--[Main Content Area]---------------------------+
|             |                                                 |
|  LLM-Dock   |  [Page Header - same as desktop]               |
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

### 3.3 Mobile Layout (< 768px)

On mobile, the sidebar collapses (existing behavior). The content stacks vertically:

```
+--[Full Width]----------------------------------+
|  [Page Header]                                  |
|  <- Back   llamacpp-qwen-7b  [Running]          |
+-------------------------------------------------+
|  [Controls + Metadata - card]                   |
|  Status: Running  |  Port: 3302                 |
|  [Stop]  [Restart]                              |
+-------------------------------------------------+
|  [Configuration - collapsible card]             |
|  v Configuration                                |
|    (collapsed by default on mobile)             |
+-------------------------------------------------+
|  [Live Logs - card, limited height]             |
|  Container Logs                   [300px max-h] |
|  ...                                            |
+-------------------------------------------------+
```

---

## 4. Component Specifications

### 4.1 Page Header

**Purpose**: Persistent identification of the service being viewed and quick navigation back.

```
+-----------------------------------------------------------------------+
|  [<-]  llamacpp-qwen-7b  [copy]    [Running *]    llama.cpp    7.2 GB |
+-----------------------------------------------------------------------+
```

- **Back button**: `<- Back to Services` (left-aligned). Uses `fa-arrow-left` icon. On click, navigates to dashboard. If unsaved changes exist, shows confirmation.
- **Service name**: Large text (`text-2xl font-bold text-white`). Clicking does nothing (already on the page). Copy button beside it (existing `CopyButton` pattern).
- **Status badge**: Pill-shaped badge. Colors follow existing convention:
  - Running: `bg-green-500/20 text-green-400 border border-green-500/30`
  - Stopped/Exited: `bg-red-500/20 text-red-400 border border-red-500/30`
  - Not Created: `bg-gray-500/20 text-gray-400 border border-gray-500/30`
  - Transitioning: Animated pulse overlay
- **Engine badge**: Reuse existing `EngineBadge` component from `ServicesTable.jsx`.
- **Model size**: Small text (`text-sm text-gray-400`).

**Tailwind classes for header container**:
```
bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center gap-4 flex-wrap
```

### 4.2 Controls + Metadata Card

**Purpose**: Show real-time service metadata and provide start/stop/restart controls.

```
+-----------------------------------------------+
|  Service Info                                  |
|  +------------------+  +-------------------+  |
|  | Status           |  | Container         |  |
|  | Running          |  | a1b2c3d4e5f6      |  |
|  +------------------+  +-------------------+  |
|  +------------------+  +-------------------+  |
|  | Port             |  | Open WebUI        |  |
|  | 3302 [globe]     |  | Registered [unreg]|  |
|  +------------------+  +-------------------+  |
|  +------------------+  +-------------------+  |
|  | Model Size       |  | API Key           |  |
|  | 7.2 GB           |  | sk-abc1... [copy] |  |
|  +------------------+  +-------------------+  |
|                                                |
|  [Stop]   [Restart]   [View YAML]   [Delete]  |
+------------------------------------------------+
```

**Layout**: `bg-gray-800 rounded-lg border border-gray-700 p-5`

**Metadata grid**: `grid grid-cols-2 gap-4 mb-4` on desktop, `grid-cols-1` on mobile.

Each metadata item:
```
<div>
  <dt class="text-xs text-gray-500 uppercase tracking-wider mb-1">Status</dt>
  <dd class="text-sm text-white font-medium">Running</dd>
</div>
```

**Action buttons row**: `flex gap-3 mt-4 pt-4 border-t border-gray-700`

| Button | Style | Icon | Condition |
|--------|-------|------|-----------|
| Start | `bg-green-600 hover:bg-green-700` | `fa-play` | When stopped |
| Stop | `bg-red-600 hover:bg-red-700` | `fa-stop` | When running |
| Restart | `bg-yellow-600 hover:bg-yellow-700` | `fa-rotate-right` | When running |
| View YAML | `bg-gray-600 hover:bg-gray-700` | `fa-code` | Always |
| Delete | `bg-red-600 hover:bg-red-700` | `fa-trash` | Always (requires confirmation) |

**Transitioning states**: When an action is in progress, the active button shows `fa-spinner fa-spin` and is disabled. Other action buttons are also disabled during transitions.

### 4.3 Configuration Editor Section

**Purpose**: Edit service configuration inline on the page (replaces the edit modal).

```
+-------------------------------------------------------+
|  Configuration                    * Unsaved changes    |
+-------------------------------------------------------+
|                                                        |
|  Engine                                                |
|  [llama.cpp] (disabled - read-only chip)               |
|                                                        |
|  Model Path (container)                                |
|  [/hf-cache/hub/models--Qwen.../qwen-7b-q5.gguf   ]  |
|                                                        |
|  Port           API Key                                |
|  [3302    ]     [sk-abc123...         ] [Use Global]   |
|                                                        |
|  Parameters (3 configured)     [Copy from...] [Reset]  |
|  +--------------------------------------------------+ |
|  | Flag        Value                            [x]  | |
|  | [-ngl    ]  [999                            ]     | |
|  | [-c      ]  [8192                           ]     | |
|  | [-fa     ]  [                               ]     | |
|  | [+ Add parameter]                                 | |
|  +--------------------------------------------------+ |
|                                                        |
|  v Command Preview                                     |
|  +--------------------------------------------------+ |
|  | /llama.cpp/build/bin/llama-server                 | |
|  | -m /hf-cache/hub/.../qwen-7b-q5.gguf             | |
|  | --alias llamacpp-qwen-7b                          | |
|  | --host "0.0.0.0"                                  | |
|  | --port 8080                                       | |
|  | --api-key sk-abc123...                            | |
|  | -ngl 999                                          | |
|  | -c 8192                                           | |
|  | -fa                                               | |
|  +--------------------------------------------------+ |
|                                                        |
|  [Discard Changes]              [Save Changes]         |
+--------------------------------------------------------+
```

**Container**: `bg-gray-800 rounded-lg border border-gray-700`

**Section header**: `px-5 py-4 border-b border-gray-700 flex justify-between items-center`
- Title: `text-lg font-semibold text-gray-200`
- Unsaved indicator: `text-yellow-400 text-sm` with `fa-circle-exclamation` icon. Only visible when dirty.

**Form fields**: Reuse the exact same field styles as the existing create/edit modal:
- Labels: `block text-sm font-medium mb-2 text-gray-300`
- Inputs: `w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500`
- Engine shown as disabled chip, not editable (matches existing behavior)

**Parameters section**: Port the existing `param-rows.js` pattern. Each row is:
```
flex items-center gap-2 bg-gray-900 rounded px-3 py-2
```
- Flag input: `bg-gray-700 border border-gray-600 rounded px-2 py-1 font-mono text-sm w-32`
- Value input: `bg-gray-700 border border-gray-600 rounded px-2 py-1 font-mono text-sm flex-1`
- Remove button: `text-gray-500 hover:text-red-400`

**Command Preview**: Collapsible section (chevron toggle). Uses `bg-gray-900 rounded p-4 font-mono text-xs text-gray-300 whitespace-pre-wrap`. Updates live as fields change.

**Action buttons**:
- Discard: `bg-gray-600 hover:bg-gray-700 px-4 py-2 rounded font-semibold`
- Save: `bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-semibold`
- Both disabled when no unsaved changes (reduced opacity: `opacity-50 cursor-not-allowed`)

### 4.4 Live Log Viewer

**Purpose**: Show real-time container logs without needing a separate modal.

```
+---------------------------------------------------+
|  Container Logs                     [*] [pause]    |
+---------------------------------------------------+
|                                                    |
|  [timestamp] Starting llama-server...              |
|  [timestamp] Loading model /hf-cache/...           |
|  [timestamp] Model loaded in 3.2s                  |
|  [timestamp] Server listening on 0.0.0.0:8080      |
|  [timestamp] slot 0: context 8192 tokens           |
|  ...                                               |
|                                                    |
|  (auto-scrolls to bottom)                          |
|                                                    |
+---------------------------------------------------+
|  Last updated: 14:32:01  |  142 lines  | Polling   |
+---------------------------------------------------+
```

**Container**: `bg-gray-800 rounded-lg border border-gray-700 flex flex-col`

**Header**: `px-5 py-3 border-b border-gray-700 flex justify-between items-center`
- Title: `text-sm font-semibold text-gray-300 uppercase tracking-wider`
- Polling indicator: `w-2.5 h-2.5 rounded-full bg-green-500` with opacity pulse on each fetch
- Pause/Resume button: `text-gray-400 hover:text-white text-sm` with `fa-pause` / `fa-play` icon

**Log content area**:
- Container: `flex-1 overflow-auto p-4 min-h-[300px]`
- On desktop (side-by-side layout): The log viewer stretches to fill the right column height, matching the combined height of the metadata card + configuration section on the left. Uses `h-full` with `min-h-[400px]`.
- Text: `font-mono text-sm text-gray-300 whitespace-pre-wrap leading-relaxed`
- Auto-scroll behavior: Same as existing logs modal -- scroll to bottom unless user has scrolled up or has text selected.

**Footer**: `px-5 py-2 border-t border-gray-700 text-xs text-gray-500 flex justify-between`
- Left: "Last updated: {time} | {count} lines"
- Right: Polling status indicator

**Empty/error states**:
- No container: "Service has not been started. Start the service to see logs." in `text-gray-500 italic`
- Error fetching: "Failed to load logs: {error}" in `text-red-400`

---

## 5. State & Feedback Design

### 5.1 Page Loading States

| State | Visual |
|-------|--------|
| Initial page load | Skeleton placeholders: gray animated bars for metadata fields, pulsing `bg-gray-700/50` blocks for config and logs |
| Service data loaded | Metadata populates, config fields fill, logs begin streaming |
| Service not found | Full-page error: "Service not found" with back-to-dashboard link |

### 5.2 Service Status Transitions

| Transition | Controls Area | Status Badge | Logs |
|------------|--------------|-------------|------|
| Starting | Button shows spinner "Starting..." All buttons disabled | Pulsing amber/yellow badge "Starting..." | "Waiting for container..." placeholder |
| Running | Stop/Restart buttons appear | Solid green "Running" | Logs stream normally |
| Stopping | Button shows spinner "Stopping..." All buttons disabled | Pulsing amber/yellow badge "Stopping..." | Logs freeze, last content preserved |
| Stopped | Start button appears | Solid red/gray "Stopped (exit X)" | Last logs remain visible, polling stops |

### 5.3 Configuration Save States

| State | Visual |
|-------|--------|
| Clean (no changes) | Save/Discard buttons grayed out and disabled. No indicator. |
| Dirty (unsaved changes) | Yellow dot + "Unsaved changes" text in config header. Save/Discard buttons fully enabled. |
| Saving | Save button shows spinner "Saving...". All config fields disabled during save. |
| Save success | Brief green flash on config card border (`border-green-500` for 1.5s, then back to `border-gray-700`). Toast "Configuration saved" at bottom-right. |
| Save error | Red error banner inside config section: `bg-red-900/50 border border-red-700 text-red-300 rounded p-3`. Fields remain editable. |
| Discard | Fields revert immediately. No animation needed -- instant state reset. |

### 5.4 Delete Confirmation

Instead of a modal, use an inline confirmation pattern within the controls card:

```
Normal state:     [...] [Delete]
After click:      [Are you sure? This cannot be undone.]  [Cancel] [Confirm Delete]
```

The delete button area expands into a confirmation row with `bg-red-900/30 border border-red-700 rounded p-3`. After confirming, redirect to dashboard with a toast "Service deleted".

### 5.5 Toast Notifications

Reuse the existing `Toast` component pattern from `ServicesTable.jsx`:
- Position: `fixed bottom-6 right-6 z-50`
- Success: `bg-green-600 text-white`
- Error: `bg-red-600 text-white`
- Info: `bg-blue-600 text-white`
- Auto-dismiss after 3 seconds
- Animated entry: slide up + fade in

---

## 6. Responsive Design Considerations

### Breakpoints

| Breakpoint | Layout | Notes |
|-----------|--------|-------|
| >= 1280px (xl) | Two-column: left 55% (metadata + config), right 45% (logs) | Side-by-side view. Logs visible while editing. |
| 768px - 1279px (md-lg) | Single column, all stacked | Configuration section starts collapsed to save vertical space. |
| < 768px (sm) | Single column, sidebar hidden | Configuration collapsed by default. Logs limited to 300px height. Metadata grid switches to single column. |

### Specific Responsive Adjustments

- **Page header**: On mobile, wrap to two lines if needed. Back button and service name on first line, badges on second line.
- **Metadata grid**: `grid-cols-2` on md+, `grid-cols-1` on mobile.
- **Action buttons**: On mobile, stack vertically (`flex-col`) if they overflow.
- **Parameter rows**: On mobile, flag and value inputs stack vertically within each row.
- **Log viewer height**: On desktop side-by-side, `h-full` (fills available space). On stacked layouts, `max-h-[400px]` with scroll.
- **Command preview**: Always collapsible to save space.

---

## 7. Accessibility Requirements

### Keyboard Navigation

- All interactive elements must be focusable and operable via keyboard.
- Tab order follows visual reading order: Back button -> Service name copy -> Action buttons -> Config fields (top to bottom) -> Save/Discard -> Log controls.
- Enter/Space activates buttons.
- Escape from any field should not navigate away (reserved for modal patterns, not used here).

### ARIA Labels

- Back button: `aria-label="Back to services list"`
- Status badge: `aria-label="Service status: Running"` (dynamic)
- Polling indicator: `aria-label="Log updates active"` or `aria-label="Log updates paused"`
- Copy buttons: `aria-label="Copy service name"`, `aria-label="Copy API key"`
- Parameter remove buttons: `aria-label="Remove parameter -ngl"` (dynamic)
- Log pause: `aria-label="Pause log updates"` / `aria-label="Resume log updates"` (toggle)

### Screen Reader Considerations

- Use `role="status"` with `aria-live="polite"` on the service status badge so status changes are announced.
- Log viewer: Do NOT use `aria-live` on the log content (too noisy). Instead, the footer timestamp uses `aria-live="polite"` to announce update times.
- Unsaved changes indicator: Use `role="status"` with `aria-live="polite"`.
- Toast notifications: Use `role="alert"` (matches existing pattern).

### Color Contrast

All text must meet WCAG AA contrast ratios. Existing color pairs in the codebase already satisfy this:
- `text-white` on `bg-gray-800`: 12.6:1
- `text-gray-300` on `bg-gray-800`: 7.5:1
- `text-gray-400` on `bg-gray-900`: 5.5:1
- `text-green-400` on `bg-gray-800`: 6.1:1
- `text-red-400` on `bg-gray-800`: 5.2:1

### Focus Indicators

Use the existing `focus:outline-none focus:border-blue-500` pattern on all form inputs. For buttons, add `focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-800`.

---

## 8. Visual Design Notes

### Color Palette (Exact TailwindCSS Classes)

| Element | Background | Text | Border |
|---------|-----------|------|--------|
| Page background | `bg-gray-900` | - | - |
| Cards | `bg-gray-800` | - | `border-gray-700` |
| Form inputs | `bg-gray-700` | `text-white` | `border-gray-600` |
| Input focus | `bg-gray-700` | `text-white` | `border-blue-500` |
| Inset/code areas | `bg-gray-900` | `text-gray-300` | `border-gray-700` |
| Status: running | `bg-green-500/20` | `text-green-400` | `border-green-500/30` |
| Status: stopped | `bg-red-500/20` | `text-red-400` | `border-red-500/30` |
| Status: transitioning | `bg-yellow-500/20` | `text-yellow-400` | `border-yellow-500/30` |
| Unsaved indicator | - | `text-yellow-400` | - |
| Primary action (Save) | `bg-blue-600` | `text-white` | - |
| Danger action (Delete) | `bg-red-600` | `text-white` | - |
| Secondary action | `bg-gray-600` | `text-white` | - |
| Start button | `bg-green-600` | `text-white` | - |
| Stop button | `bg-red-600` | `text-white` | - |

### Typography

- Page title (service name): `text-2xl font-bold text-white`
- Section headings: `text-lg font-semibold text-gray-200`
- Metadata labels: `text-xs text-gray-500 uppercase tracking-wider`
- Metadata values: `text-sm text-white font-medium`
- Form labels: `text-sm font-medium text-gray-300`
- Log text: `font-mono text-sm text-gray-300`
- Command preview: `font-mono text-xs text-gray-300`
- Badges: `text-xs font-medium`

### Spacing

- Page padding: `p-6`
- Card internal padding: `p-5`
- Section gaps: `gap-6` (24px between major sections)
- Field gaps: `gap-4` (16px between form fields)
- Tight spacing (within groups): `gap-2` (8px)

### Shadows and Effects

- Cards: `shadow-sm` (subtle, matching existing)
- Hover effects on buttons: Standard Tailwind hover classes (e.g., `hover:bg-blue-700`)
- Transition timing: `transition-colors duration-150` on interactive elements
- Border radius: `rounded-lg` on cards, `rounded` on buttons and inputs (matching existing)

### Icons (FontAwesome)

- Back: `fa-solid fa-arrow-left`
- Copy: `fa-solid fa-copy`
- Start: `fa-solid fa-play`
- Stop: `fa-solid fa-stop`
- Restart: `fa-solid fa-rotate-right`
- Delete: `fa-solid fa-trash`
- Save: `fa-solid fa-save`
- View YAML: `fa-solid fa-code`
- Loading: `fa-solid fa-spinner fa-spin`
- Warning/unsaved: `fa-solid fa-circle-exclamation`
- Add parameter: `fa-solid fa-plus`
- Remove parameter: `fa-solid fa-xmark`
- Collapse/expand: `fa-solid fa-chevron-down` / `fa-chevron-up`
- Pause logs: `fa-solid fa-pause`
- Resume logs: `fa-solid fa-play`
- Engine (in header): Reuse `EngineBadge` from existing code

---

## 9. Navigation & Transition Design

### 9.1 Entry Points

**From the services table (React frontend)**:

The existing edit button (`pencil` icon) in `ActionButtons` changes from a no-op to a navigation action:
```jsx
// Before: onClick does nothing meaningful
// After: navigates to /services/{name}
<button onClick={e => { e.stopPropagation(); navigate(`/services/${service.name}`) }} ... >
```

The service name text in `ServiceRow` also becomes a clickable link:
```jsx
<a href={`/services/${service.name}`} className="font-medium text-gray-200 hover:text-blue-400 transition-colors">
  {service.name}
</a>
```

**From the vanilla dashboard** (`static/index.html`):

The edit button's `onclick="editService('${service.name}')"` changes to navigate:
```js
function editService(serviceName) {
    window.location.href = `/services/${serviceName}`;
}
```

### 9.2 Routing

React frontend should use client-side routing (React Router):
- `/` or `/services` -> Dashboard with services table
- `/services/:name` -> Service details page

The vanilla frontend uses server-rendered navigation (standard page loads).

### 9.3 Back Button Behavior

- **Visual back button** (top-left of page header): Navigates to `/` (dashboard).
- **Browser back button**: Standard history navigation. If the user came from the dashboard, returns there.
- **Unsaved changes guard**: Both triggers check for dirty state and prompt before leaving.

### 9.4 Page Transition

- No animated page transitions needed. Standard browser/React Router navigation.
- On arrival at the details page, content should appear immediately with skeleton loading states for async data (no fade-in animation).

### 9.5 Deep Linking

The URL `/services/{name}` is directly accessible (bookmarkable). If the user navigates directly to this URL:
- Page loads and fetches service data by name.
- If service does not exist, show "Service not found" error with link back to dashboard.
- Authentication is required (same as dashboard). If not authenticated, redirect to login.

### 9.6 Service Name in Browser Tab

The document title should update to: `{service-name} - LLM-Dock` (e.g., "llamacpp-qwen-7b - LLM-Dock").
