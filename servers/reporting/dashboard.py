import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
JIRA_FILE = DATA_DIR / "jira_comments.json"
SLACK_FILE = DATA_DIR / "slack_messages.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Reporting Dashboard")


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/api/jira")
def jira_feed():
    return _read(JIRA_FILE)


@app.get("/api/slack")
def slack_feed():
    return _read(SLACK_FILE)
