# MCP Test Agent

Demo tool for the NashLearn session "Building Test Agents with MCP Servers"
(23 Oct 2026). See
`docs/superpowers/specs/2026-09-14-mcp-test-agent-design.md` for the design
and `AGENT_RUNBOOK.md` for how an orchestrating agent should drive the four
MCP servers.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Run the demo app

```bash
uvicorn demo_app.main:app --port 8000
```

## Run the reporting dashboard

```bash
uvicorn servers.reporting.dashboard:app --port 8766
```

Open http://127.0.0.1:8766 to watch the mock Jira/Slack feed update live.

## Run the MCP servers

```bash
python -m servers.ticket_spec.server
python -m servers.api_test.server
python -m servers.reporting.server
npx @playwright/mcp@latest
```

Point an MCP-capable agent (e.g. Claude Code) at all four and follow
`AGENT_RUNBOOK.md`.

## Tests

```bash
pytest tests/unit
pytest tests/integration
```
