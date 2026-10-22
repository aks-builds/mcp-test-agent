"""The umbrella: parts mounted under prefixes, procedure served by the
server, one trace line per call. Runs in-process without the browser
part so it is fast; the browser part is covered by the integration run."""
import json

import pytest
from fastmcp import Client

import servers.test_mcp.server as umbrella

PYTHON_PARTS = [p for p in umbrella.PARTS if p[0] != "servers.browser.server"]


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(umbrella, "TRACE_FILE", tmp_path / "trace.jsonl")
    return umbrella.build_server(parts=PYTHON_PARTS)


async def test_parts_are_mounted_under_their_prefixes(server):
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {
        "ticket_get_ticket", "ticket_get_openapi_spec",
        "api_run_api_test",
        "report_post_jira_comment", "report_post_slack_message",
    }


async def test_server_carries_the_procedure(server):
    async with Client(server) as client:
        prompts = [p.name for p in await client.list_prompts()]
        result = await client.get_prompt("test_ticket", {"ticket_id": "NASH-101"})
    assert prompts == ["test_ticket"]
    text = result.messages[0].content.text
    assert 'ticket_get_ticket("NASH-101")' in text
    assert "browser_snapshot" in text
    assert "report_post_slack_message" in text
    assert "never claim a pass" in text
    assert "browser_snapshot" in umbrella.INSTRUCTIONS


async def test_every_call_is_traced(server, tmp_path):
    async with Client(server) as client:
        await client.call_tool("ticket_get_ticket", {"ticket_id": "NASH-101"})
        await client.call_tool("ticket_get_ticket", {"ticket_id": "NASH-999"})
    rows = [json.loads(l) for l in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert [r["tool"] for r in rows] == ["ticket_get_ticket", "ticket_get_ticket"]
    assert rows[0]["part"] == "ticket"
    assert rows[0]["server"] == "test-mcp"
    assert rows[0]["ok"] is True
    assert "title=Add Task creation flow should work end-to-end" in rows[0]["summary"]
    assert "error=ticket NASH-999 not found" in rows[1]["summary"]
    assert all(set(r) >= {"ts", "tool", "args", "ok", "ms", "summary"} for r in rows)


def test_a_broken_part_does_not_take_the_others_down(capsys):
    server = umbrella.build_server(parts=[("servers.does_not_exist", "nope"), *PYTHON_PARTS])
    assert "servers.does_not_exist" in capsys.readouterr().err

    async def names():
        async with Client(server) as client:
            return {t.name for t in await client.list_tools()}

    import asyncio
    assert "ticket_get_ticket" in asyncio.run(names())
