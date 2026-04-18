"""Registry of available MCP servers."""

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
}


def get_tool_hints(server_ids: list) -> str:
    """Build a system prompt suffix describing enabled tools."""
    hints = []
    for sid in server_ids:
        server = MCP_SERVERS.get(sid)
        if server and server.get("tool_hint"):
            hints.append(server["tool_hint"])
    return "\n\n".join(hints)


def list_available_servers() -> list:
    """Return list of available MCP servers for the API."""
    return [
        {"id": sid, "name": s["name"], "description": s["description"], "icon": s["icon"]}
        for sid, s in MCP_SERVERS.items()
    ]


def get_server_config(server_id: str) -> dict:
    """Get the config for a specific server."""
    return MCP_SERVERS.get(server_id)
