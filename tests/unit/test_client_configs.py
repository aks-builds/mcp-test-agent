"""The four MCP client configs must describe the same four servers.

Claude Code reads .mcp.json, Gemini CLI reads .gemini/settings.json,
Codex CLI reads .codex/config.toml and OpenCode reads opencode.json.
If one drifts, the live demo works in one tool and breaks in another.
"""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {"ticket-spec", "api-test", "reporting", "playwright"}


def _claude():
    data = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    return {k: [v["command"], *v["args"]] for k, v in data["mcpServers"].items()}


def _gemini():
    data = json.loads((ROOT / ".gemini" / "settings.json").read_text(encoding="utf-8"))
    return {k: [v["command"], *v["args"]] for k, v in data["mcpServers"].items()}


def _codex():
    data = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    return {k: [v["command"], *v["args"]] for k, v in data["mcp_servers"].items()}


def _opencode():
    data = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    for v in data["mcp"].values():
        assert v["type"] == "local"
        assert v["enabled"] is True
    return {k: v["command"] for k, v in data["mcp"].items()}


def test_all_clients_list_the_same_four_servers():
    configs = {
        "claude": _claude(),
        "gemini": _gemini(),
        "codex": _codex(),
        "opencode": _opencode(),
    }
    for name, servers in configs.items():
        assert set(servers) == EXPECTED, f"{name} has {sorted(servers)}"


def test_all_clients_launch_each_server_the_same_way():
    reference = _claude()
    for name, servers in {"gemini": _gemini(), "codex": _codex(), "opencode": _opencode()}.items():
        for server, command in reference.items():
            assert servers[server] == command, f"{name}/{server}: {servers[server]} != {command}"


def test_agent_context_files_point_at_the_runbook():
    assert "AGENT_RUNBOOK.md" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in (ROOT / "GEMINI.md").read_text(encoding="utf-8")
    assert (ROOT / "AGENT_RUNBOOK.md").exists()
