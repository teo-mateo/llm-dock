"""Schemdraw MCP Server — draws electronic circuit diagrams via stdio."""

import json
import traceback

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("schemdraw-circuits")


@mcp.tool()
def draw_circuit(code: str) -> str:
    """Draw an electronic circuit diagram using Schemdraw Python code.

    Write Python code that creates a schemdraw.Drawing and adds elements to it.
    The variables `schemdraw` and `elm` (schemdraw.elements) are pre-imported.

    Available elements include:
    - Passive: Resistor, Capacitor, Inductor, Fuse
    - Sources: SourceV, SourceI, BatteryCell, Battery
    - Semiconductors: Diode, LED, Zener, SchottkyDiode, Bjt, BjtNpn, BjtPnp, JFet, Mosfet
    - ICs: OpAmp, Ic555
    - Switches: Switch, SwitchSpst, SwitchDpst, SwitchDpdt
    - Connections: Ground, Vdd, Vss, Dot, Line, Arrow
    - Labels: Label

    Direction methods: .right(), .left(), .up(), .down()
    Labeling: .label('text'), .label('text', loc='bottom')
    Styling: .color('red'), .fill('blue')

    Example code:
        d = schemdraw.Drawing()
        d += elm.SourceV().label('12V').up()
        d += elm.Resistor().right().label('R1\\n10k$\\Omega$')
        d += elm.Capacitor().down().label('C1\\n100nF')
        d += elm.Line().left()
        d += elm.Ground().at(d.here)

    The drawing variable MUST be named 'd'.
    """
    import schemdraw
    import schemdraw.elements as elm

    namespace = {"schemdraw": schemdraw, "elm": elm}

    try:
        exec(code, namespace)
    except Exception as e:
        return json.dumps({
            "artifact": False,
            "error": f"Code execution failed: {str(e)}\n{traceback.format_exc()}",
        })

    d = namespace.get("d")
    if d is None:
        return json.dumps({
            "artifact": False,
            "error": "No drawing variable 'd' found. Make sure your code creates: d = schemdraw.Drawing()",
        })

    try:
        svg_bytes = d.get_imagedata("svg")
        svg_str = svg_bytes.decode("utf-8") if isinstance(svg_bytes, bytes) else svg_bytes
    except Exception as e:
        return json.dumps({
            "artifact": False,
            "error": f"Failed to render SVG: {str(e)}",
        })

    return json.dumps({
        "artifact": True,
        "type": "svg",
        "title": "Circuit Diagram",
        "content": svg_str,
        "description": "Circuit diagram generated successfully.",
    })


@mcp.tool()
def list_schemdraw_elements() -> str:
    """List all available Schemdraw elements and their categories.
    Use this to discover what circuit components are available."""
    import schemdraw.elements as elm

    categories = {
        "Passive Components": ["Resistor", "Resistor2", "Capacitor", "Capacitor2", "Inductor", "Inductor2", "Fuse"],
        "Sources": ["SourceV", "SourceI", "SourceSin", "SourcePulse", "SourceSquare", "SourceTriangle",
                     "SourceControlledV", "SourceControlledI", "BatteryCell", "Battery", "Solar"],
        "Diodes": ["Diode", "Schottky", "Zener", "LED", "LED2", "Photodiode", "Tunnel", "Varactor"],
        "Transistors": ["Bjt", "BjtNpn", "BjtPnp", "BjtNpn2", "BjtPnp2",
                        "JFet", "JFetN", "JFetP", "NFet", "PFet"],
        "Op-Amps": ["Opamp"],
        "Logic Gates": ["And", "Nand", "Or", "Nor", "Xor", "Xnor", "Not", "Buf"],
        "Switches": ["Switch", "SwitchSpst", "SwitchSpdt", "SwitchDpst", "SwitchDpdt", "Button"],
        "Connections": ["Ground", "GroundSignal", "GroundChassis", "Vdd", "Vss", "Vcc",
                        "Dot", "Line", "Arrow", "Arrowhead"],
        "Other": ["Speaker", "Mic", "Motor", "Lamp", "Antenna", "AntennaLoop",
                   "Crystal", "Jack", "Plug", "Transformer"],
    }

    lines = []
    for category, elements in categories.items():
        available = []
        for name in elements:
            if hasattr(elm, name):
                available.append(name)
        if available:
            lines.append(f"\n{category}:")
            lines.append(", ".join(available))

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
