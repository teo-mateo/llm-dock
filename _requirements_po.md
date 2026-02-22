# Service Details Page -- Product Owner Requirements

## 1. Feature Overview

The Service Details Page replaces the current modal-based editing workflow with a dedicated, full-page view for each LLM service. Instead of juggling multiple overlapping modals (edit, logs, rename, YAML preview, delete), users get a single coherent page that consolidates all service-related information and actions. This reduces context-switching, lets users see logs and configuration side-by-side, and provides enough screen space to display information that was previously cramped inside modals.

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
- Clicking the edit button (pencil icon) on a service row navigates to `/v2/services/{service-name}` (or equivalent route)
- Clicking the service name in the table row also navigates to the details page
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
- Port number is displayed, with a link to the service endpoint when running (for llama.cpp services)
- Public port indicator (globe icon) is visible when the service is on port 3301
- API key is shown (truncated) with a copy-to-clipboard button
- Model path (llama.cpp) or model name (vLLM) is displayed
- Model size is displayed when available
- Open WebUI registration status is shown
- Status updates automatically via polling (every 3 seconds, consistent with the main table)

---

### US-3: Control Service Lifecycle (Must Have)

**As a** dashboard user
**I want to** start, stop, and restart a service from its details page
**So that** I don't have to go back to the main list to control the service

**Acceptance Criteria:**
- A Start button is shown when the service is stopped or not created
- A Stop button is shown when the service is running
- A Restart button is always available (stop then start)
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
- The configuration section displays all editable fields: port, API key, and CLI parameters (params)
- Model path/name is displayed but NOT editable (changing the model is a destructive operation requiring a new service)
- Template type (llama.cpp / vLLM) is displayed but not editable
- Port field validates that the port is not already in use by another service
- CLI parameters are displayed as key-value rows with the ability to add, edit, and remove parameters
- Flag metadata (descriptions, defaults) from the API is used to provide tooltips or help text for parameters
- A Save button persists changes via `PUT /api/services/{name}`
- The user sees a success confirmation after saving
- If the service was running when configuration was saved, the user is informed that the container will be recreated
- The "Set Global API Key" action is available to replace the service's API key with the global one
- Unsaved changes are indicated visually (e.g., the Save button becomes active only when changes exist)

---

### US-5: View Container Logs (Must Have)

**As a** dashboard user
**I want to** see the container's recent logs on the details page
**So that** I can diagnose issues without opening a separate logs modal

**Acceptance Criteria:**
- A logs section displays the most recent container logs (default 100 lines)
- Logs are displayed in a monospace font with timestamps
- The user can adjust the number of lines displayed (e.g., 50, 100, 200, 500)
- A refresh button reloads the logs on demand
- Auto-refresh can be toggled (e.g., poll every 5 seconds)
- The log viewer auto-scrolls to the bottom on load and on new data (with the ability to scroll up to inspect earlier output)
- If the container has not been created yet, the logs section shows an informational message instead of an error
- Log text is selectable and copyable

---

### US-6: Rename Service (Should Have)

**As a** dashboard user
**I want to** rename a service from its details page
**So that** I can correct naming mistakes without going back to the main list

**Acceptance Criteria:**
- A rename action is accessible from the details page (e.g., a small edit icon next to the service name, or an action in a menu)
- Rename is only enabled when the service is stopped (the UI disables the control and shows a tooltip explaining why when the service is running)
- After a successful rename, the URL updates to reflect the new name and the page continues showing the renamed service
- If rename fails (e.g., name conflict), an error message is displayed

---

### US-7: Preview Generated YAML (Should Have)

**As a** dashboard user
**I want to** see the rendered Docker Compose YAML for this service
**So that** I can verify what will be generated before starting the service

**Acceptance Criteria:**
- A "View YAML" or "Preview" action shows the rendered YAML for this service
- The YAML is displayed in a code block with syntax highlighting (or at minimum, monospace formatting)
- A copy-to-clipboard button is available for the YAML content
- The preview reflects the currently saved configuration (not unsaved edits)

---

### US-8: Delete Service (Should Have)

**As a** dashboard user
**I want to** delete a service from its details page
**So that** I can remove services I no longer need without going back to the main list

**Acceptance Criteria:**
- A delete action is available (e.g., a red "Delete Service" button, placed to avoid accidental clicks)
- Clicking delete shows a confirmation dialog: "Delete service {name}? This cannot be undone."
- After successful deletion, the user is navigated back to the main services list
- If the service is running, it is automatically stopped and removed before deletion (handled by backend)

---

### US-9: Set Public Port (Should Have)

**As a** dashboard user
**I want to** assign the public port (3301) to this service from the details page
**So that** I can expose this service externally without switching views

**Acceptance Criteria:**
- If the service is NOT on port 3301, a "Set as Public" button or toggle is shown
- If the service is already on port 3301, a "Public" badge is displayed instead
- Clicking "Set as Public" calls the existing API endpoint and shows a success/failure toast
- The user is informed if another service was displaced from port 3301

---

### US-10: Register/Unregister with Open WebUI (Could Have)

**As a** dashboard user
**I want to** register or unregister this service with Open WebUI from the details page
**So that** I can manage the Open WebUI integration in context

**Acceptance Criteria:**
- The current registration status is displayed (registered / not registered)
- A "Register" button is shown when not registered; an "Unregister" button when registered
- Success/failure feedback is provided via toast notification
- This action is only available for llama.cpp and vLLM services (not for the open-webui infrastructure service itself)

---

### US-11: Return to Services List (Must Have)

**As a** dashboard user
**I want to** easily navigate back to the main services list from any details page
**So that** I can continue managing other services

**Acceptance Criteria:**
- A clear back navigation element is always visible (e.g., breadcrumb "Services > {service-name}" or a back arrow)
- Clicking it returns the user to the services list without a full page reload
- If the user has unsaved changes, no blocking prompt is shown (configuration changes require explicit Save; navigating away discards unsaved edits silently)

---

## 3. Priority Ranking (MoSCoW)

### Must Have
1. **US-1** -- Navigate to Service Details (entry point; without this, nothing works)
2. **US-2** -- View Service Status and Metadata (core value of the page)
3. **US-3** -- Control Service Lifecycle (start/stop/restart is the most frequent action)
4. **US-4** -- Edit Service Configuration (replaces the current edit modal)
5. **US-5** -- View Container Logs (high-value consolidation -- seeing logs alongside config is the primary advantage over modals)
6. **US-11** -- Return to Services List (basic navigation requirement)

### Should Have
7. **US-6** -- Rename Service
8. **US-7** -- Preview Generated YAML
9. **US-8** -- Delete Service
10. **US-9** -- Set Public Port

### Could Have
11. **US-10** -- Register/Unregister with Open WebUI

### Won't Have (this iteration)
- Real-time log streaming via WebSocket (polling is sufficient for now)
- Benchmarking integration on the details page (exists as a separate page already)
- Service cloning / "Copy From" on the details page (keep in create modal)
- Multi-service comparison view
- Configuration version history or undo

---

## 4. Edge Cases and Error Scenarios

### Navigation
- **Service not found:** If the user navigates to `/v2/services/{name}` and the service does not exist (e.g., it was deleted in another tab), show a "Service not found" message with a link back to the services list.
- **Service renamed in another tab:** If the service is renamed externally while the details page is open, the next poll should detect the 404 and notify the user that the service no longer exists under this name.

### Configuration Editing
- **Port conflict:** When the user changes the port to one already in use, show an inline validation error before allowing save. The backend returns HTTP 409 for port conflicts.
- **Invalid parameters:** If the backend validation rejects the configuration, display the specific error details returned by the API (the `details` field in the 400 response).
- **Concurrent edit:** If two browser tabs edit the same service, the last save wins. No optimistic locking is required for this iteration, but the save response should reflect the final state.
- **Template type immutability:** The template type field must be read-only. The backend rejects attempts to change it (HTTP 400).

### Lifecycle Control
- **Start failure:** If starting fails (e.g., port already bound at the OS level, Docker error), display the error message from the backend response.
- **Stop timeout:** If stopping takes longer than expected, the UI should remain in the "stopping" transitioning state until the next poll confirms the new status.
- **Service not created:** For services that exist in the database but have never been started (status: "not-created"), the Start button should work normally. Stop and Restart should be disabled or hidden.
- **Rapid button clicks:** Lifecycle buttons must be disabled during transitions to prevent duplicate requests.

### Logs
- **No container:** If the service has never been started, the logs endpoint returns 404. Display a friendly message: "No logs available. Start the service to see container output."
- **Empty logs:** If the container exists but has no output, show an empty state message.
- **Very long log lines:** Log lines should wrap or be horizontally scrollable to prevent layout breakage.

### Rename
- **Running service:** Rename must be blocked when the service is running. The UI should disable the rename control and explain that the service must be stopped first.
- **Name conflict:** If the new name conflicts with an existing service, display the error from the backend.
- **URL update after rename:** After a successful rename, the browser URL must update to the new service name. The details page should continue showing the service without requiring the user to navigate away and back.

### Delete
- **Accidental deletion:** Always require confirmation via a dialog. The dialog should include the service name for clarity.
- **Running service deletion:** The backend handles stopping the container before deletion. The UI should warn the user that the running service will be stopped.

### Network / Auth
- **Authentication expired:** If the API returns 401, redirect to the login screen (consistent with the existing `fetchAPI` behavior).
- **Network failure:** If polling fails due to a network error, show a non-blocking warning (e.g., a subtle banner) but do not disrupt the page layout. Resume polling when the network recovers.
- **Backend unavailable:** If the details page fails to load initial data, show an error state with a retry button.
