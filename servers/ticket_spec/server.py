import json
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "tickets.json"
DEMO_APP_URL = os.environ.get("DEMO_APP_URL", "http://127.0.0.1:8000")

mcp = FastMCP("ticket-spec")


def _load_tickets() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Fetch a mock Jira ticket by id. Returns its title and description
    (description may contain an optional Given/When/Then block)."""
    tickets = _load_tickets()
    if ticket_id not in tickets:
        return {"error": f"ticket {ticket_id} not found"}
    return tickets[ticket_id]


@mcp.tool()
def get_openapi_spec() -> dict:
    """Fetch the target demo app's live OpenAPI spec. Returns a structured
    error dict instead of raising if the demo app is unreachable or
    returns an error status."""
    try:
        resp = httpx.get(f"{DEMO_APP_URL}/openapi.json", timeout=5.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return {"error": f"demo app unreachable or returned an error: {exc}"}
    return resp.json()


if __name__ == "__main__":
    mcp.run()
