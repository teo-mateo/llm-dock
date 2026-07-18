# Chat window redesign — "Drydock"

## Why a redesign

The current chat UI is functionally complete but visually generic: default
system sans, `gray-900/800/700` surfaces, `blue-600` everywhere, rounded
chat bubbles. It reads like every other AI chat clone and doesn't reflect
what this tool actually *is*: a single-operator console for docking and
driving local models on a workstation, with model orchestration (main +
sidekick critic), MCP tools, reasoning traces, and live telemetry.

## Concept

**Drydock** — a harbor-instrument console. Conversations are *berths*;
spin-offs are *tenders*; the composer is a *command console*; the critique
panel is an *inspector*. The aesthetic is **refined-industrial**: an
oscilloscope / mission-control / high-end audio-interface feel. Dark, but
not flat gray — deep "harbor at night" ink with hairline rules, corner
ticks, status LEDs, and one signature live motion (a signal sweep during
streaming).

The memorable idea: **the operator types in monospace (a console prompt);
the model answers in an editorial serif (a considered voice)**, all wrapped
in industrial chrome with monospace telemetry. Nothing like the gray-bubble
clone.

## Type

- **Archivo** — display / UI chrome (industrial grotesque; letter-spaced for
  an "expanded instrument" feel on labels).
- **IBM Plex Mono** — telemetry, labels, operator input, code, tool traces
  (technical-instrument heritage; tabular numerals).
- **Newsreader** — assistant prose only (gives generated answers an
  authored, deliberate quality and a strong contrast with the mono chrome).

No Inter / Roboto / system stack; no Space Grotesk.

## Palette

| Token | Value | Use |
|------|-------|-----|
| ink-900 | `#07090a` | app shell |
| ink-800 | `#0c1213` | panels |
| ink-700 | `#111a1c` | raised cards / inputs |
| line | `rgba(140,170,175,.09)` | hairline borders |
| amber | `#ff9d00` / `#ffbf57` | OPERATOR · primary actions · tools |
| cyan | `#2fd6c2` / `#5fe3d3` | MACHINE · streaming · success-active |
| coral | `#ff6f5e` | drift warnings · stop · destructive |
| green | `#57d98a` | switch ON / tool OK |

Warm amber = the operator and primary intent; cold cyan = the machine and
its live pulse. The amber/cyan tension on deep harbor ink is the cohesive,
non-cliché core (explicitly not blue-on-gray, not purple-on-white).

## Spatial moves

- **Berths rail** replaces the plain conversation list: status LED + display
  title + mono meta, with a hairline tree connector for tenders (spin-offs)
  and inline multi-select / bulk delete preserved.
- **Instrument header strip**: model selectors as readout tiles
  (`MAIN ▸ value ▾`), MCP tools as physical toggle switches, a live
  telemetry cluster (tok/s, ctx, GPU, elapsed), and a coral STOP. A 1px
  signal-sweep line sits under it while streaming.
- **Transcript as a log**, not bubbles: a left timeline spine with tick
  nodes; each turn is a hairline block with a colored left spine
  (amber=operator, cyan=model) and a mono meta line (role · model · seq ·
  time). Operator content is mono with a `▸` prompt; model prose is
  Newsreader serif.
- Reasoning = a collapsible **reasoning tape** (scanline texture). Tool
  calls = **instrument cards** with a strace-like mono trace + status LED +
  result readout. Artifacts, format-drift chip, heartbeat all restyled to
  the instrument language.
- **Command console** composer docked at the bottom (prompt glyph, inline
  attach/tools, amber SEND, mono hint line, pending-critique + attachment
  chips). The empty-state is the same console centered with a dock mark —
  consistent with the feature we just shipped.
- **Inspector rail** (critique) on the right in cyan; annotations as
  margin-note cards with severity LEDs and an "insert ▸" action.
- **Tender window** (spin-off) + **dock tray** (minimized) reuse the same
  instrument chrome.

## Motion (restrained)

One signature moment: the streaming **signal sweep** (amber→cyan gradient
travelling under the header and along the live block's spine) plus a
pulsing cyan caret. Everything else is subtle hover/elevation. Refined, not
maximalist — precision in hairlines, spacing (4/8/12/16/24 scale), and
tabular telemetry carries the design.

## Deliverable

`mock.html` — a single self-contained file (Google Fonts + Font Awesome
CDN, plain CSS, minimal JS) rendering one dense screen that exercises every
existing capability: berths rail w/ tender + selection, instrument header,
a full transcript (operator turn w/ image, model turn w/ reasoning tape +
tool card + artifact + serif answer + code, a drift-warning block, a live
streaming block), command console w/ chips, inspector rail, a floating
tender + dock tray. It is a visual proposal, not wired to the app.
