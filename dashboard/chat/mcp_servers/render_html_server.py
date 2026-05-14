"""Render HTML MCP Server — turn model-generated HTML or Markdown into
chat artifacts that the dashboard renders in a sandboxed iframe.

No native browser, no DISPLAY, no subprocess. Just emits the existing
artifact convention (mcp_client.py:134-145) so the dashboard's
ArtifactRenderer picks them up as `type: 'html'` artifacts.
"""

import json

from markdown_it import MarkdownIt
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("render-html")

_md = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True}).enable("table").enable("strikethrough")

# Lean default stylesheet — readable defaults for markdown that wasn't
# styled by the model. Kept small on purpose; the iframe lives inside
# the chat UI and shouldn't compete visually with it.
_DEFAULT_CSS = """
body { font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       color: #1f2937; background: #fff; max-width: 760px; margin: 0 auto; padding: 1.25rem; }
h1, h2, h3, h4 { line-height: 1.25; margin-top: 1.4em; margin-bottom: .5em; }
h1 { font-size: 1.7em; border-bottom: 1px solid #e5e7eb; padding-bottom: .3em; }
h2 { font-size: 1.35em; border-bottom: 1px solid #f1f5f9; padding-bottom: .25em; }
h3 { font-size: 1.15em; }
p, ul, ol, blockquote, table, pre { margin: .65em 0; }
code { background: #f3f4f6; padding: .1em .35em; border-radius: 3px; font-size: .92em; }
pre { background: #f3f4f6; padding: .75em 1em; border-radius: 6px; overflow-x: auto; }
pre code { background: transparent; padding: 0; }
blockquote { border-left: 3px solid #d1d5db; color: #4b5563; padding: 0 .9em; }
table { border-collapse: collapse; }
th, td { border: 1px solid #e5e7eb; padding: .35em .6em; text-align: left; }
th { background: #f9fafb; }
a { color: #2563eb; }
img { max-width: 100%; }
hr { border: 0; border-top: 1px solid #e5e7eb; margin: 1.5em 0; }
"""


def _wrap_document(body: str, title: str | None, *, inject_css: bool) -> str:
    """Wrap a body fragment in a minimal HTML5 document.

    `inject_css` is True for markdown (we own the styling) and False for
    raw HTML the model produced (it likely brought its own styles).
    """
    css_block = f"<style>{_DEFAULT_CSS}</style>" if inject_css else ""
    safe_title = (title or "Rendered").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html>\n"
        '<html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{safe_title}</title>"
        f"{css_block}"
        "</head><body>"
        f"{body}"
        "</body></html>"
    )


def _looks_like_document(html: str) -> bool:
    head = html.lstrip()[:200].lower()
    return head.startswith("<!doctype") or head.startswith("<html")


@mcp.tool()
def render_html(html: str, title: str = "Rendered HTML") -> str:
    """Render HTML in a sandboxed iframe inside the chat window.

    Pass a complete HTML document (starting with <!doctype html> or <html>)
    OR a fragment — fragments are wrapped in a minimal HTML5 shell
    automatically. Scripts run, but inside a sandbox that has no access
    to the parent dashboard. The result appears as an artifact panel
    attached to your message.
    """
    if _looks_like_document(html):
        document = html
    else:
        # Don't inject the default CSS for raw HTML — the model probably
        # styled it deliberately. Just supply a doctype + viewport shell.
        document = _wrap_document(html, title, inject_css=False)

    return json.dumps({
        "artifact": True,
        "type": "html",
        "title": title,
        "content": document,
        "description": f"Rendered HTML artifact '{title}'.",
    })


@mcp.tool()
def render_html_from_markdown(markdown: str, title: str = "Rendered Markdown") -> str:
    """Render Markdown as HTML in a sandboxed iframe inside the chat window.

    Accepts CommonMark plus tables and strikethrough. The output is
    wrapped in a minimal stylesheet so headings, code blocks, and tables
    look reasonable without further work. The result appears as an
    artifact panel attached to your message.
    """
    body = _md.render(markdown)
    document = _wrap_document(body, title, inject_css=True)

    return json.dumps({
        "artifact": True,
        "type": "html",
        "title": title,
        "content": document,
        "description": f"Rendered Markdown artifact '{title}'.",
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
