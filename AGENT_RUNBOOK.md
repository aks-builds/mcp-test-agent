# Agent Runbook: MCP Test Agent

You are orchestrating a self-directed test run. Four MCP servers are
available. Call their tools in this order.

## Servers

| Server | Start command | Purpose |
|---|---|---|
| ticket-spec | `python -m servers.ticket_spec.server` | `get_ticket`, `get_openapi_spec` |
| api-test | `python -m servers.api_test.server` | `run_api_test` |
| reporting | `python -m servers.reporting.server` | `post_jira_comment`, `post_slack_message` |
| Playwright MCP | `npx @playwright/mcp@latest` | browser automation (`navigate`, `snapshot`, `click`, `fill`, ...) |

The target app must be running first: `uvicorn demo_app.main:app --port 8000`.

## Procedure

1. Call `ticket-spec.get_ticket(ticket_id)` to read the ticket. If it
   contains a Given/When/Then block, use it directly as your test
   strategy. If it is plain prose, extract the user-facing behavior
   yourself before continuing.
2. Call `ticket-spec.get_openapi_spec()` to see the real API surface.
3. Draft a short test strategy: which UI flow(s) and which API
   endpoint(s) cover the ticket's acceptance criteria.
4. Execute the UI flow using Playwright MCP against `http://127.0.0.1:8000/`.
   The ticket may reference a locator used by earlier automation (e.g. a
   button id), try that first.

   **If a locator fails:** when a `click`/`fill` action fails because the
   target locator is not found:

   a. Call Playwright MCP's `snapshot` tool to get the current
      accessibility tree.
   b. Find the element with the same role and accessible name that the
      ticket implied (e.g. a button named "Add Task").
   c. Retry the action using that element instead.
   d. State explicitly what locator you replaced and why, citing the
      snapshot, never silently substitute a locator without saying so.
5. Execute the API-level checks with `api-test.run_api_test(method, path,
   body, expected_status)` for each endpoint identified in step 3.
6. Summarize the run: what passed, what failed, what was self-healed and
   why.
7. Call `reporting.post_jira_comment(ticket_id, comment)` with the summary
   from step 6.
8. Call `reporting.post_slack_message(channel, text)` with a short version
   of the same summary. Use channel `#qa-alerts` unless told otherwise.

## Rules

- Never claim a test passed without having actually called the
  corresponding tool and observed a passing result.
- Every self-heal must name the old locator, the new locator, and the
  evidence (the snapshot) that justified the change.
- If a step fails and cannot be self-healed, report it as a failure in
  the summary, do not paper over it.
