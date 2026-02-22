# Service Details Page -- Toolbar Rework

## Goal

Consolidate the header, overview panel, lifecycle controls, and service actions into a single unified header area with an "old-school toolbar" feel. Remove the Overview panel and Delete action entirely. The result: the top of the page contains everything about the service's identity, status, metadata, and actions. Below it, only the Configuration panel (left) and Logs panel (right) remain.

---

## Current State (What Exists)

```
ServiceDetailsHeader        ← service name, status badge, engine badge, rename, back button
ServiceOverviewPanel        ← metadata grid: status, port, API key, Open WebUI, container ID
ServiceLifecycleControls    ← Start / Stop / Restart buttons
ServiceActions              ← View YAML, Set as Public, Delete (with confirmation + YAML modal)
ServiceConfigPanel          ← configuration editor (left column)
ServiceLogsPanel            ← log viewer (right column)
```

**Current layout (top to bottom, left column):**
1. Header bar (name, status, engine, model size)
2. Overview card (metadata grid)
3. Lifecycle buttons (Start/Stop/Restart)
4. Action buttons (View YAML, Set as Public, Delete)
5. Configuration card

---

## Target State

```
ServiceDetailsHeader (reworked)
  ├── Top row: back button | service name + rename + copy | status badge | engine badge | model size
  ├── Metadata row: port (with link) | API key (truncated + copy) | container ID (+ copy) | Open WebUI status
  └── Toolbar row: [Start/Stop] [Restart] | [Set as Public] [View YAML] [Register/Unregister WebUI]

ServiceConfigPanel          ← unchanged (left column)
ServiceLogsPanel            ← unchanged (right column)
```

**Target layout (top to bottom, left column):**
1. Unified header (identity + metadata + toolbar)
2. Configuration card

---

## Changes Required

### 1. Rework `ServiceDetailsHeader.jsx`

The header currently shows: back button, service name, copy, rename, status badge, engine badge, model size.

**Expand it to three visual rows** (all within the same `bg-gray-800` header container):

#### Row 1 -- Identity (exists today, keep as-is)
- Back button ("Back to Services")
- Divider
- Service name (h1) + copy button + rename pencil icon
- Status badge (Running/Stopped/Not Created with transition states)
- Engine badge (llama.cpp / vLLM)
- Model size

#### Row 2 -- Metadata (moved from ServiceOverviewPanel)
Compact, inline metadata items separated by subtle dividers. Each item is a label + value pair displayed horizontally.

| Item | Display | Notes |
|------|---------|-------|
| Port | `Port: 3302` (clickable link when running) | Include globe icon if port 3301 |
| API Key | `API Key: key-9e074...` + copy button | Truncated to ~16 chars |
| Container ID | `Container: a1b2c3d` + copy button | Only shown when container exists |
| Open WebUI | `WebUI: Registered` or `WebUI: Not registered` | Status text only (action is in toolbar) |
| Status detail | `Exit code: 1` | Only shown when status is exited and exit_code is non-null |

Style: `text-xs text-gray-400` for labels, `text-xs text-white` for values. Items laid out as `flex items-center gap-4 flex-wrap`. A thin `border-t border-gray-700` separates this from Row 1.

#### Row 3 -- Toolbar (moved from ServiceLifecycleControls + ServiceActions)
A horizontal button bar with a classic toolbar aesthetic: grouped buttons with a muted background strip.

**Toolbar container**: `flex items-center gap-2 flex-wrap mt-3 pt-3 border-t border-gray-700`

**Button groups** (visually separated by a thin vertical divider `w-px h-5 bg-gray-600 mx-1`):

Group 1 -- Lifecycle:
- **Start** (when stopped): green, `fa-play` icon
- **Stop** (when running): red, `fa-stop` icon
- **Restart** (when running): yellow, `fa-rotate-right` icon
- All show spinner + disabled state during transitions (same logic as current `ServiceLifecycleControls`)

Group 2 -- Actions:
- **Set as Public** / **Public (3301)** badge: `fa-globe` icon. Button when not public, badge when already public.
- **View YAML**: `fa-code` icon. Opens the YAML preview modal (keep `YamlPreviewModal` component).
- **Register** / **Unregister WebUI**: `fa-network-wired` icon. Toggle button based on current registration state. Show spinner during toggle.

**Toolbar button style** (compact, toolbar-like):
```
px-3 py-1.5 rounded text-xs font-medium inline-flex items-center gap-1.5
```
Use the same color conventions as today (green for Start, red for Stop, yellow for Restart, gray for View YAML / Set as Public).

### 2. Remove `ServiceOverviewPanel.jsx`

Delete this component entirely. All its content moves to the header's Row 2. The Open WebUI toggle action moves to the toolbar (Row 3).

### 3. Remove `ServiceLifecycleControls.jsx`

Delete this component. Start/Stop/Restart buttons move into the header toolbar (Row 3, Group 1).

### 4. Rework `ServiceActions.jsx`

This component currently contains: View YAML button + YAML modal, Set as Public button, Delete button + confirmation.

**Changes:**
- **Remove** the Delete button and `DeleteConfirmation` sub-component entirely
- **Move** the View YAML and Set as Public button logic into the header toolbar
- **Keep** `YamlPreviewModal` as a shared component (either extract it to its own file or keep it in the header). The modal should still be rendered at the page level so it overlays correctly.
- **Remove** the `ServiceActions` component file after migrating its logic

### 5. Update `ServiceDetailsPage.jsx`

**Remove** from the left column:
- `<ServiceOverviewPanel />`
- `<ServiceLifecycleControls />`
- `<ServiceActions />`

**Update** the header to pass additional props it now needs:
- `actions` (start, stop, restart, setPublicPort, fetchYamlPreview, registerOpenWebUI, unregisterOpenWebUI)
- `onSuccess`, `onError` callbacks
- The full `config` and `runtime` objects (already passed)

**Result**: The left column contains ONLY `<ServiceConfigPanel />`. The right column remains `<ServiceLogsPanel />`.

The YAML preview modal state can live in the header or be lifted to the page level.

### 6. Update `useServiceDetails.js`

No changes needed to the hook itself. The same actions and data are used, just wired to different components.

### 7. Remove `onDeleted` handling

Since Delete is removed:
- Remove the `handleDeleted` callback from `ServiceDetailsPage.jsx`
- Remove `onDeleted` prop from anywhere it was passed
- Remove the `deleteService` action from being exposed (or just leave it in the hook unused -- no harm)

---

## Component Architecture (After)

```
ServiceDetailsPage
  ├── ServiceDetailsHeader (expanded)
  │     ├── Row 1: Back | Name + Copy + Rename | Status | Engine | Size
  │     ├── Row 2: Port | API Key + Copy | Container ID + Copy | WebUI status | Exit code
  │     └── Row 3: [Start/Stop] [Restart] | [Set as Public] [View YAML] [Register/Unregister]
  ├── Two-column grid
  │     ├── Left: ServiceConfigPanel (unchanged)
  │     └── Right: ServiceLogsPanel (unchanged)
  ├── YamlPreviewModal (when active)
  └── Toast
```

---

## Files to Modify

| File | Action |
|------|--------|
| `ServiceDetailsHeader.jsx` | Major rework: absorb metadata + toolbar |
| `ServiceDetailsPage.jsx` | Remove Overview, Lifecycle, Actions from layout; pass new props to header |
| `ServiceOverviewPanel.jsx` | **Delete** |
| `ServiceLifecycleControls.jsx` | **Delete** |
| `ServiceActions.jsx` | **Delete** (migrate YamlPreviewModal out first) |

---

## What NOT to Change

- `ServiceConfigPanel.jsx` -- no changes
- `ServiceLogsPanel.jsx` -- no changes
- `useServiceDetails.js` -- no changes needed
- `api.js` -- no changes
- Routing, Flask backend -- no changes
- The two-column layout grid -- stays the same, just fewer items in the left column

---

## Visual Reference (Target)

```
+--[Sidebar]--+--[Main Content]-------------------------------------------------------+
|             |                                                                         |
|             |  +--[Header]-------------------------------------------------------+   |
|             |  | <- Back   llamacpp-qwen-7b [copy][rename]  [Running*]  llama.cpp |   |
|             |  |                                                           7.2 GB |   |
|             |  |- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -|   |
|             |  | Port: 3302  API Key: key-9e07...[copy]  Container: a1b2  WebUI:+ |   |
|             |  |- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -|   |
|             |  | [Stop] [Restart] | [Set as Public] [View YAML] [Unregister]     |   |
|             |  +-------------------------------------------------------------+---+   |
|             |                                                                         |
|             |  +--[Config Panel ~55%]---------+  +--[Logs Panel ~45%]----------+      |
|             |  |                              |  |                              |      |
|             |  |  Configuration               |  |  Container Logs              |      |
|             |  |  Engine: llama.cpp            |  |  [log lines...]             |      |
|             |  |  Model: /path/to/model        |  |                              |      |
|             |  |  Port: [3302]                 |  |                              |      |
|             |  |  API Key: [key...] [Global]   |  |                              |      |
|             |  |  Parameters (4) [Ref] [+Add]  |  |                              |      |
|             |  |  ...                          |  |                              |      |
|             |  |  [Discard] [Save]             |  |                              |      |
|             |  +------------------------------+  +------------------------------+      |
+--------------+------------------------------------------------------------------------+
```

---

## CopyButton Duplication Note

`CopyButton` is currently defined independently in three files: `ServiceDetailsHeader.jsx`, `ServiceOverviewPanel.jsx`, and `ServiceActions.jsx`. After this rework, since Overview and Actions are deleted, the remaining copy is in the header. However, consider extracting `CopyButton` to a shared file (e.g., `components/CopyButton.jsx`) since `ServiceConfigPanel` or other future components may need it. This is optional but recommended for cleanliness.

---

## Acceptance Criteria

1. The header area contains all service identity, metadata, and actions in a compact toolbar layout
2. No separate Overview panel exists
3. No separate Lifecycle Controls or Service Actions components exist
4. No Delete button anywhere on the page
5. Start/Stop/Restart work correctly from the toolbar with proper transition states
6. View YAML opens the modal from the toolbar
7. Set as Public works from the toolbar with proper feedback
8. Register/Unregister WebUI works from the toolbar with proper feedback
9. All metadata (port, API key, container ID, WebUI status) is visible in the header
10. Port is clickable when running
11. API key has copy button
12. Container ID has copy button (only shown when container exists)
13. The page layout below the header is unchanged (config left, logs right)
14. Loading skeleton still works
15. Responsive behavior: toolbar buttons wrap on smaller screens
