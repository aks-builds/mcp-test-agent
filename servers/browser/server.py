"""Browser part: Microsoft's Playwright MCP, passed through as-is.

We do not write browser tools ourselves. test-mcp starts the official
Playwright MCP server (npx @playwright/mcp) once and forwards every
browser_* call to it. The same pattern works for any third-party MCP
server you want to pull under the umbrella: make a FastMCP, add a
ProxyProvider that returns one long-lived client, expose it as `mcp`.
"""
import os
import shutil

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.server.providers.proxy import ProxyProvider

PLAYWRIGHT_MCP = "@playwright/mcp@0.0.83"


def _playwright_client() -> Client:
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found. Install Node.js 18+ to run the Playwright MCP server.")
    args = ["-y", PLAYWRIGHT_MCP, "--isolated", "--viewport-size", "900,600"]
    if os.environ.get("PLAYWRIGHT_HEADLESS") == "1":
        args.append("--headless")
    # keep_alive: one Playwright process for the whole run, so the page
    # opened by browser_navigate is still there for browser_snapshot.
    return Client(StdioTransport(npx, args, keep_alive=True))


_shared = _playwright_client()

mcp = FastMCP("browser")
mcp.add_provider(ProxyProvider(lambda: _shared, cache_ttl=0))


if __name__ == "__main__":
    mcp.run(show_banner=False)
