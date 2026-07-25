# F05 · Rendering assistant output

**Mockup:** screen 05 · Rendered answer · **Depends on:** F04

What the model can actually put on a 6-inch screen. Everything here
already comes down the stream — the question is how much renderer is
worth writing.

The web UI renders GitHub-flavoured Markdown with maths, raw HTML
passthrough, and an artifact panel. R-B allows all of it; cost decides
what lands in v1.

---

## F05-R1 · Markdown (Must)

Assistant text renders as GitHub-flavoured Markdown: headings, bold and
italic, ordered and unordered lists, nested lists, blockquotes, links,
horizontal rules, inline code.

Rendering happens **during** streaming, not only at the end — a
half-arrived list must not flicker between raw and rendered on every
delta.

**Acceptance criteria**

- [ ] Each construct above renders correctly in a live stream and after a
      reload, identically.
- [ ] An unterminated construct mid-stream (an open fence, a half-written
      table) renders without flicker or layout jumps.
- [ ] Links open in the browser; a long URL does not push the layout
      sideways.
- [ ] Text that is not Markdown renders as written, with no lost
      characters.

## F05-R2 · Code blocks (Must)

Fenced code with its language label and a copy button. Code scrolls
horizontally inside its own box; the page never scrolls sideways.

This is non-negotiable for how these models get used.

**Acceptance criteria**

- [ ] A fenced block shows its language and a working copy button.
- [ ] Copy puts the exact code — no leading indentation added, no fence
      markers — on the clipboard, with visible confirmation.
- [ ] A long line scrolls within the block; the message column does not.
- [ ] Code is rendered in a monospace face at a size readable on a phone.

## F05-R3 · Copy, select, share (Must)

Under each assistant answer: copy the whole message, select text within
it, and share it to any other Android app.

**Acceptance criteria**

- [ ] Copy places the message's Markdown source on the clipboard.
- [ ] Text selection works inside rendered prose, not only in code blocks.
- [ ] Share opens the system share sheet with the message text.

## F05-R4 · Typography (Should)

Serif for assistant prose, monospace for the user's own text — the same
split the dashboard uses. On a small screen it earns its keep: you can
tell who is talking without looking for an avatar. Settings offers a
toggle (F13).

**Acceptance criteria**

- [ ] Assistant and user messages are distinguishable by face alone, with
      the screen at arm's length.
- [ ] The Settings toggle switches assistant prose to a sans face and
      persists.

## F05-R5 · Tables (Should)

Markdown tables render as tables and scroll sideways inside their own
box.

**Acceptance criteria**

- [ ] A wide table scrolls horizontally within its container; the message
      column does not move.
- [ ] A table with a missing or ragged row renders without crashing the
      message.

## F05-R6 · Images (Should)

Two sources: images the user attached (F04-R9), which are part of the
message; and `artifact` frames of type `image` or `svg`, produced by
tools such as schemdraw.

**Acceptance criteria**

- [ ] An attached image renders inline in the user's message.
- [ ] An `image` artifact renders inline in the assistant turn.
- [ ] An `svg` artifact renders as a picture, not as markup text.
- [ ] Tapping an image opens it full-screen with pinch-zoom.
- [ ] An artifact that fails to decode shows a placeholder, not a broken
      message.

## F05-R7 · Maths (Later)

**Cut for v1.** The web UI renders LaTeX via KaTeX, so web parity would
have permitted it, but it is real cost on Android — a WebView per formula
or a native maths renderer — and the mockup's own recommendation was to
skip it.

What v1 must not do is lose the content. LaTeX passes through as source
text, legibly.

**Acceptance criteria**

- [ ] `$…$` and `$$…$$` spans render as their literal source, complete
      and readable.
- [ ] No maths delimiter is silently stripped, and no formula is
      swallowed by the Markdown renderer.
- [ ] A message that is mostly maths is still selectable, copyable and
      shareable with its source intact.

## F05-R8 · HTML artifacts (Later)

`artifact_type: "html"` — the render-html MCP tool's output. The web
shows it in a sandboxed frame. On the phone this means a WebView per
artifact.

Not in v1. The app shows that an HTML artifact was produced, with its
title, and says it can be opened on the desktop.

**Acceptance criteria**

- [ ] An HTML artifact appears as a labelled placeholder, not as a wall
      of raw markup and not silently dropped.

---

## Deviations from the mockup

None on the Must items. F05-R7 (maths) and F05-R8 (HTML artifacts) are
both cut for v1, matching the mockup's own decision table, even though
web parity would have allowed them.

## Out of scope

- Editing or re-flowing model output.
- Exporting a thread to a file.
- Syntax highlighting inside code blocks is not required for v1 — a
  monospace block with a language label satisfies F05-R2.
