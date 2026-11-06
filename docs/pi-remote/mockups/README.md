# pi-remote UI mockups

Design reference for the pi-remote screens (plan: `docs/plans/pi-remote.md` §5 Android,
web view issues). Source of the canvas: the owner's private claude.ai design artifact
"pi remote UI"; these files are a copy of its artboards.

| File | Screen | Phase |
|---|---|---|
| `Main.dc.html` | Android · pi tab: session list (live/ended, idle/working, model, cwd, context %) | P2 |
| `PhoneSession.dc.html` | Android · live session: user message, collapsible thinking, tool card, streaming reply; composer that steers while working, Stop | P2 view, P3 controls |
| `PhonePrompt.dc.html` | Android · approval bottom sheet for the rm gate (Deny / Allow; terminal and phone race, first answer wins) | P4 |
| `Web.dc.html` | Web `/v2/pi`: session sidebar + transcript + composer, fluid page | P1 web view, P3 controls |

How to read them: each file is HTML with inline styles. `{{name}}` holes and
`<sc-for>` loops are template syntax from the design tool — the values are in the
`renderVals()` script at the bottom of each file (sample data, not real). The colours,
spacing, type sizes and copy are the intended ones; components are built in the real
stack (React + Tailwind on the web, Compose on Android), not copied as HTML.

Palette: ground `#0F1115`, surface `#181B22`, border `#262A33`, text `#E8EAEE`,
muted `#A0A8B6`, accent `#6AA8FF`; state colours working `#F2A54A`, idle `#5CC48A`,
waiting `#CDBBFF`, ended `#5A6170`, stop `#FF9C9C`/`#2A1717`. Fonts: Inter, JetBrains Mono
for paths and tool output. State is never shown by colour alone (each has a text label).
