"""Every agent client must point at the same single server, test-mcp.

Claude Code reads .mcp.json, Gemini CLI reads .gemini/settings.json,
Codex CLI reads .codex/config.toml and OpenCode reads opencode.json.
If one drifts, the agent works in one tool and breaks in another.
"""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {"test-mcp": ["python", "-m", "servers.test_mcp.server"]}


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


def test_all_clients_point_at_test_mcp_only():
    for name, servers in {"claude": _claude(), "gemini": _gemini(),
                          "codex": _codex(), "opencode": _opencode()}.items():
        assert servers == EXPECTED, f"{name}: {servers}"


def test_opencode_can_only_act_through_mcp():
    """A live run once wandered off into shell commands, read the whole
    repo and killed the app's server. The agent gets MCP tools only."""
    data = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    for tool in ("bash", "edit", "read", "glob", "grep", "list", "skill", "task"):
        assert data["permission"][tool] == "deny", tool


def test_codex_disables_external_plugins():
    """Codex has global plugins (Postman, etc.) that hijack the session.
    The project config must disable them so only test-mcp tools load."""
    data = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    postman = data.get("plugins", {}).get("postman@postman", {})
    assert postman.get("enabled") is False, "postman plugin must be disabled"


def test_no_instruction_files_in_the_repo():
    """The procedure lives in the server (instructions + prompt), not in
    AGENTS.md style files. MCP alone does the job."""
    for name in ("AGENTS.md", "GEMINI.md", "CLAUDE.md", "AGENT_RUNBOOK.md"):
        assert not (ROOT / name).exists(), f"{name} should not exist"
