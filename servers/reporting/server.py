import json
import os
from pathlib import Path

from fastmcp import FastMCP

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
JIRA_FILE = DATA_DIR / "jira_comments.json"
SLACK_FILE = DATA_DIR / "slack_messages.json"

mcp = FastMCP("reporting")


def _dashboard_url() -> str:
    return os.environ.get("DASHBOARD_URL", "http://127.0.0.1:8766")


def _append(path: Path, key: str, entry: dict) -> None:
    store = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    store.setdefault(key, []).append(entry)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


@mcp.tool()
def post_jira_comment(ticket_id: str, comment: str) -> dict:
    """Post a comment to the mock Jira ticket thread. The response
    includes a url field pointing at the live reporting dashboard.
    Always share this URL with the user so they can see the posted
    comment."""
    _append(JIRA_FILE, ticket_id, {"comment": comment})
    return {"posted": True, "ticket_id": ticket_id, "url": _dashboard_url()}


@mcp.tool()
def post_slack_message(channel: str, text: str) -> dict:
    """Post a message to the mock Slack channel feed. The response
    includes a url field pointing at the live reporting dashboard.
    Always share this URL with the user so they can see the posted
    message."""
    _append(SLACK_FILE, channel, {"text": text})
    return {"posted": True, "channel": channel, "url": _dashboard_url()}


if __name__ == "__main__":
    mcp.run()
