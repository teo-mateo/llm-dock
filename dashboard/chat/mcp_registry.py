"""Built-in MCP servers.

External servers (machine-local, declared in JSON) are layered on top of
these by `mcp_config.py`. This file holds only the in-tree servers that
ship with the repo and run under the dashboard's own interpreter.
"""

import os
import sys

_SERVERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_servers")

MCP_SERVERS = {
    "sympy-math": {
        "name": "SymPy Math",
        "description": "Symbolic mathematics — solve equations, differentiate, integrate, simplify, factor, limits, matrices",
        "command": [sys.executable, os.path.join(_SERVERS_DIR, "sympy_server.py")],
        "icon": "fa-calculator",
        "tool_hint": "You have access to SymPy math tools. Use them for calculations, solving equations, derivatives, integrals, limits, matrix operations, and LaTeX conversion. Trust the tool results — do not re-derive or verify them manually.",
    },
    "schemdraw-circuits": {
        "name": "Schemdraw Circuits",
        "description": "Draw electronic circuit diagrams — resistors, capacitors, op-amps, transistors, etc.",
        "command": [sys.executable, os.path.join(_SERVERS_DIR, "schemdraw_server.py")],
        "icon": "fa-microchip",
        "tool_hint": """You have access to Schemdraw for drawing electronic circuit diagrams. When asked to draw or design a circuit, use the draw_circuit tool with valid Schemdraw Python code. The drawing variable must be named 'd'.

Schemdraw examples:

Voltage divider:
d = schemdraw.Drawing()
d += elm.Ground()
d += elm.SourceV().up().label('Vin')
d += elm.Resistor().right().label('R1')
dot = d.add(elm.Dot())
d += elm.Resistor().down().label('R2')
d += elm.Ground()
d += elm.Line().at(dot.start).right()
d += elm.Dot(open=True).label('Vout', loc='right')

RC low-pass filter:
d = schemdraw.Drawing()
d += elm.Dot(open=True).label('Vin', loc='left')
d += elm.Resistor().right().label('R')
dot = d.add(elm.Dot())
d += elm.Capacitor().down().label('C')
d += elm.Ground()
d += elm.Line().at(dot.start).right()
d += elm.Dot(open=True).label('Vout', loc='right')

Non-inverting op-amp amplifier:
d = schemdraw.Drawing()
op = d.add(elm.Opamp())
d += elm.Line().at(op.in1).left()
d += elm.Ground()
d += elm.Line().at(op.in2).left().length(1)
d += elm.Dot(open=True).label('Vin', loc='left')
d += elm.Line().at(op.out).right().length(1)
d += elm.Dot(open=True).label('Vout', loc='right')
d += elm.Line().at(op.out).right().length(0.5)
fb = d.add(elm.Dot())
d += elm.Resistor().down().label('Rf')
jn = d.add(elm.Dot())
d += elm.Resistor().down().label('R1')
d += elm.Ground()
d += elm.Line().at(jn.start).left().tox(op.in1)
d += elm.Line().down().toy(jn.start)

Key patterns:
- Use .right(), .left(), .up(), .down() for direction
- Use .label('text') for labels, .label('text', loc='bottom') for position
- Use elm.Dot() for junctions, elm.Dot(open=True) for terminals
- Use .at(point) to start from a specific location
- Use .tox(point) / .toy(point) to draw to a specific x/y coordinate
- Use d.add() when you need a reference to the element for later connections

Layout tips for clean, readable diagrams:
- ALWAYS use d = schemdraw.Drawing(unit=4) for generous spacing between components
- Use .length(d.unit * 1.5) for longer wires to avoid cramped layouts
- Place labels carefully: use loc='left', loc='right', loc='top', loc='bottom' to prevent overlaps
- For vertical components, prefer loc='left' or loc='right' for labels
- For horizontal components, prefer loc='top' or loc='bottom' for labels
- Add elm.Line() segments between components to create visual breathing room
- For power rails (VCC/VDD), use elm.Vdd() only once at the top, connect with elm.Line()
- For ground, use elm.Ground() — avoid duplicating ground symbols unnecessarily
- Use .anchor('center') or .anchor('start') for precise element placement
- When connecting to a transistor, use the named anchors: .base, .collector, .emitter
- Route output lines with enough length before placing the output terminal

BJT common-emitter amplifier example (good layout):
d = schemdraw.Drawing(unit=4)
# Input
d += elm.Dot(open=True).label('$V_{in}$', loc='left')
d += elm.Capacitor().right().label('$C_{in}$', loc='top')
dot_base = d.add(elm.Dot())
# Bias resistors
d += elm.Resistor().at(dot_base.start).up().label('$R_1$', loc='left')
d += elm.Vdd().label('$V_{CC}$')
d += elm.Resistor().at(dot_base.start).down().label('$R_2$', loc='left')
d += elm.Ground()
# Transistor
Q = d.add(elm.BjtNpn().at(dot_base.start).anchor('base'))
# Collector
d += elm.Resistor().at(Q.collector).up().label('$R_C$', loc='left')
d += elm.Vdd().label('$V_{CC}$')
# Output from collector
d += elm.Line().at(Q.collector).right().length(d.unit * 0.5)
dot_out = d.add(elm.Dot())
d += elm.Capacitor().right().label('$C_{out}$', loc='top')
d += elm.Dot(open=True).label('$V_{out}$', loc='right')
# Emitter
d += elm.Resistor().at(Q.emitter).down().label('$R_E$', loc='left')
gnd_pos = d.add(elm.Ground())
# Bypass capacitor
d += elm.Line().at(Q.emitter).right().length(d.unit * 0.5)
d += elm.Capacitor().down().label('$C_E$', loc='right')
d += elm.Ground()

Important rules:
- If draw_circuit returns an error, read the error message, fix your code, and try again. Do not give up.
- If unsure what elements are available, call list_schemdraw_elements first to discover them.
- For math in labels, use LaTeX: elm.Resistor().label('$R_1$') or elm.Capacitor().label('$C_1 = 100\\,\\mathrm{nF}$')
- Do NOT use \\n in labels inside the code string — it causes syntax errors. Use separate .label() calls or keep labels on one line.
- Always test that your code creates a variable named 'd' (the drawing).
- Prioritize clean, readable layout over compact layout. Spread components out.

The diagram will be rendered automatically as an artifact.""",
    },
    "project-files": {
        "name": "Project Files",
        "description": "Read and edit this conversation's project files — list, read, search, create, write. Auto-enabled for conversations inside a project; does nothing outside one.",
        "command": [sys.executable, os.path.join(_SERVERS_DIR, "project_files_server.py")],
        "icon": "fa-folder-tree",
        "tool_hint": "This conversation belongs to a project with a file area (documents, notes, data the user keeps alongside the project's conversations). Reading: list_files shows the file tree, read_file returns a text file's content, search_files finds a substring across file names and contents. Writing: create_file makes a new text file (parent folders are created automatically; it refuses to overwrite), write_file replaces an existing file's entire content, edit_file swaps one exact snippet for another (copy the snippet verbatim from read_file — for small changes prefer this over write_file), insert_text adds lines after a given line number. All files are UTF-8 text up to 2 MB; paths are relative to the project root, e.g. 'docs/plan.md' — use them exactly as list_files prints them. When the user refers to project files or material \"in the project\", consult these tools instead of guessing, and when they ask you to save or update something in the project, actually write the file rather than only replying in chat.",
    },
    "render-html": {
        "name": "Render HTML",
        "description": "Render HTML or Markdown as an artifact in the chat",
        "command": [sys.executable, os.path.join(_SERVERS_DIR, "render_html_server.py")],
        "icon": "fa-window-restore",
        "tool_hint": "You can render HTML or Markdown directly in this chat window. Use render_html when you've produced an HTML document or fragment the user should see formatted (reports, tables, dashboards, mock UI, charts, etc.) — pass a complete <!doctype html> document if you want full control over styling, or just a fragment if you don't care. Use render_html_from_markdown when the content is markdown and you want it styled nicely without writing HTML yourself. The output appears as an artifact panel attached to your message, inside a sandboxed iframe — the user can also pop it out to a full-window tab. There is NO file-system access: you cannot pass paths, only literal content.",
    },
}


def get_tool_hints(server_ids: list) -> str:
    """Build a system prompt suffix describing enabled tools."""
    from . import mcp_config

    hints = []
    for sid in server_ids:
        cfg = mcp_config.get_config(sid)
        if cfg and cfg.get("tool_hint"):
            hints.append(cfg["tool_hint"])
    return "\n\n".join(hints)


def list_available_servers() -> list:
    """Return list of enabled MCP servers for the API."""
    from . import mcp_config

    return mcp_config.list_enabled()


def get_server_config(server_id: str):
    """Return the config for an enabled server, or None."""
    from . import mcp_config

    return mcp_config.get_config(server_id)
