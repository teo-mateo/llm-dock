# Plan: Resizable ChatSidebar

## Context

The ChatSidebar (`ChatSidebar.jsx`) currently has a fixed `w-72` (288px) width with a
collapsed `w-10` (40px) toggle. The file-explorer strip inside `ProjectChatSplit.jsx`
already has a proven custom resize pattern using a drag divider. The goal is to make the
conversation panel resizable so users can widen/narrow it to fit longer conversation
titles or compact it to give more room to the chat area.

## Approach: Extract shared resize logic, apply to ChatSidebar

The `ProjectChatSplit` resize logic is self-contained and follows a clear pattern:
localStorage persistence, `ResizeObserver` for window resizing, clamped drag with
`mousedown`/`mousemove`/`mouseup` on a thin divider element. Rather than duplicating
it, we extract the shared pieces into a reusable hook, then apply it in both places.

### 1. New shared hook: `useResizableWidth`

**File:** `dashboard/frontend/src/hooks/useResizableWidth.js`

Encapsulates the resize state machine:

| Parameter | Type | Purpose |
|-----------|------|---------|
| `storageKey` | `string` | localStorage key for persisted width |
| `minWidth` | `number` | Minimum allowed width (px), default `160` |
| `maxFraction` | `number` | Maximum fraction of container width, default `0.45` |
| `defaultWidthPx` | `number` | Default pixel width before first drag (replaces `defaultPercent`) |

Returns:

| Field | Type | Purpose |
|-------|------|---------|
| `containerRef` | `RefObject<HTMLDivElement>` | Ref to attach to the parent flex container |
| `currentWidth` | `number` | Current width in px (hook resolves default internally, never null) |
| `dragging` | `boolean` | Active drag state |
| `startDrag` | `() => void` | Call on divider `mousedown` to begin drag |

The hook handles:
- Reading/writing `width` to localStorage under `storageKey`
- `useLayoutEffect` + `ResizeObserver` on the container to compute `maxWidth`
  (fraction of container). `useLayoutEffect` used over `useEffect` to avoid layout
  flash when the container is first measured (matching existing `ProjectChatSplit`
  behavior at line 84).
- Clamping stored width against `maxWidth` on every render
- Window-level `mousemove`/`mouseup` listeners during drag
- `e.stopPropagation()` in `startDrag` to prevent event bubbling into parent
  resizable containers (critical for nested splits)
- Cursor style changes (`cursor-col-resize`) on the document body during drag

### 2. Modify `ChatSidebar.jsx`

**Changes:**
- Accept controlled `collapsed` and `onCollapse`/`onExpand` props
- Remove internal `collapsed` state management (the `useState(readCollapsed)` and
  accompanying `useEffect` that writes to localStorage)
- No longer imports or uses `useResizableWidth` directly — that belongs in `SidebarSplit`

**Scope note:** `ChatSidebar` is only imported by `ChatPage.jsx` and
`ChatSidebar.test.jsx`. The controlled-component change affects only these two files,
not a broader set of consumers.

### 3. New component: `SidebarSplit`

**File:** `dashboard/frontend/src/components/chat/SidebarSplit.jsx`

Thin wrapper component, structurally identical to the resize portion of
`ProjectChatSplit` but without the file-editor overlay logic:

```
<SidebarSplit>
  <ChatSidebar ... />    {/* left, resizable */}
  {children}             {/* right, flex-1 */}
</SidebarSplit>
```

Props:
- (No props needed; both `collapsed` and `width` state are internal)

Internal state:
- `collapsed` — migrated from ChatSidebar, persisted under `llmdock.chatSidebar.collapsed`
- `width` — from `useResizableWidth` hook, key `llmdock.chatSidebar.width`,
  `defaultWidthPx: 288`, `minWidth: 200`, `maxFraction: 0.35`
- `dragging` (from hook)

Layout:
```
<div ref={containerRef} className="flex-1 flex overflow-hidden">
  {collapsed && <collapsed-rail />}
  <div style={{ display: collapsed ? 'none' : undefined, width: `${currentWidth}px`, minWidth: `${minWidth}px` }}>
    <ChatSidebar collapsed={collapsed} onCollapse={...} onExpand={...} ... />
  </div>
  {!collapsed && <divider onMouseDown={startDrag} />}
  <div className="flex-1 flex min-w-0 relative">
    {children}
    {dragging && <transparent-overlay z-40 />}
  </div>
</div>
```

The collapsed rail geometry mirrors the existing ChatSidebar collapsed rail (h-16
bordered header, w-8 h-8 toggle, text-sm icon) so the expander chevrons of all
collapsed panels align.

The divider is conditionally rendered (`{!collapsed && ...}`), fully removed from the
DOM when collapsed — no hidden-but-present element intercepting clicks.

Transparent overlay uses `z-40` to match the existing `ProjectChatSplit` overlay
precedent (line 216).

### 4. Modify `ChatPage.jsx`

Replace the flat flex layout with `SidebarSplit`:

Before:
```jsx
<div className="flex-1 flex overflow-hidden">
  <ChatSidebar ... />
  {projectId ? <ProjectPage ... /> : <ProjectChatSplit ...>{children}</ProjectChatSplit>}
</div>
```

After:
```jsx
<SidebarSplit>
  <ChatSidebar ... />
  {projectId ? <ProjectPage ... /> : <ProjectChatSplit ...>{children}</ProjectChatSplit>}
</SidebarSplit>
```

### 5. Refactor `ProjectChatSplit.jsx`

Extract the resize logic into the shared `useResizableWidth` hook to avoid duplication.
`ProjectChatSplit` continues to manage its own width (key `llmdock.chatExplorer.width`,
`defaultWidthPx: null` — keeping the existing 20% percentage default behavior) but
delegates to the hook. The file-editor overlay logic stays in `ProjectChatSplit`.

## Implementation Order

1. **Create `useResizableWidth` hook** — extract logic from `ProjectChatSplit`
2. **Create `SidebarSplit` component** — uses the hook, wraps sidebar + content
3. **Smoke-test `SidebarSplit` with a dummy sidebar** — verify resize, divider,
   overlay, and collapse work before touching real components
4. **Modify `ChatSidebar`** — accept controlled `collapsed` prop, remove internal
   collapse state management
5. **Refactor `ProjectChatSplit`** — use the shared hook for resize logic
6. **Modify `ChatPage`** — wrap layout in `SidebarSplit`
7. **Update `ChatSidebar.test.jsx`** — adapt tests for controlled `collapsed` prop
8. **Test** — verify resize, collapse, localStorage persistence, window resize,
   nested splits (SidebarSplit + ProjectChatSplit), keyboard shortcuts

## Risks & Considerations

- **Backward compatibility:** Existing `llmdock.chatSidebar.collapsed` localStorage key
  is reused. New `llmdock.chatSidebar.width` key starts as `null` (default 288px).
- **No initial jump:** `defaultWidthPx: 288` matches the current `w-72` fixed width,
  so existing users see no visual change on first load.
- **Minimum width:** `200px` for the sidebar (vs `160px` for the file explorer).
  Conversation titles need more room than file names.
- **Maximum width:** `35%` fraction for the sidebar (vs `45%` for the file explorer).
  Conversation lists don't need to be extremely wide.
- **Nested resizable splits:** When the conversation belongs to a project, we'll have
  `SidebarSplit` (sidebar) -> `ProjectChatSplit` (explorer strip) -> Chat. Two resizable
  splits nested. Each has its own container ref and independently computes max width.
  The `startDrag` calls `e.stopPropagation()` to prevent the inner divider's drag from
  bubbling to the outer split. Transparent overlays won't conflict because they're in
  different subtrees.
- **Text truncation already handled:** `ConversationItem` already uses `truncate` class
  (line 137), so rapid reflow during drag won't cause vertical layout shifts.
- **Layout thrashing:** The existing `ProjectChatSplit` already uses `useState` updated
  on every `mousemove` without reported issues. The hook follows the same pattern.
- **Keyboard accessibility:** Add `Cmd/Ctrl + [` and `Cmd/Ctrl + ]` shortcuts on
  `ChatPage` to increment/decrement sidebar width (e.g. by 20px steps) and toggle
  collapse. Draggable dividers are inaccessible to keyboard-only users.

## Files Modified

| File | Change |
|------|--------|
| `hooks/useResizableWidth.js` | **New** — shared resize hook |
| `components/chat/SidebarSplit.jsx` | **New** — resizable sidebar wrapper |
| `components/chat/ChatSidebar.jsx` | Accept controlled `collapsed` prop |
| `components/chat/ProjectChatSplit.jsx` | Use shared hook |
| `components/chat/ChatPage.jsx` | Wrap in `SidebarSplit`, add keyboard shortcuts |
| `components/chat/ChatSidebar.test.jsx` | Adapt for controlled `collapsed` prop |
