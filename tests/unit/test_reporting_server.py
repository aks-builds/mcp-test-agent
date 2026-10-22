import json

import pytest

from servers.reporting import server as reporting_server


@pytest.fixture(autouse=True)
def use_tmp_data_files(tmp_path, monkeypatch):
    jira_file = tmp_path / "jira_comments.json"
    slack_file = tmp_path / "slack_messages.json"
    monkeypatch.setattr(reporting_server, "JIRA_FILE", jira_file)
    monkeypatch.setattr(reporting_server, "SLACK_FILE", slack_file)
    return jira_file, slack_file


def test_post_jira_comment_appends_to_store(use_tmp_data_files):
    jira_file, _ = use_tmp_data_files
    result = reporting_server.post_jira_comment("NASH-101", "All tests passed.")
    assert result["posted"] is True
    assert result["ticket_id"] == "NASH-101"
    assert "url" in result
    store = json.loads(jira_file.read_text(encoding="utf-8"))
    assert store["NASH-101"][0]["comment"] == "All tests passed."


def test_post_slack_message_appends_to_store(use_tmp_data_files):
    _, slack_file = use_tmp_data_files
    result = reporting_server.post_slack_message("#qa-alerts", "Build green.")
    assert result["posted"] is True
    assert result["channel"] == "#qa-alerts"
    assert "url" in result
    store = json.loads(slack_file.read_text(encoding="utf-8"))
    assert store["#qa-alerts"][0]["text"] == "Build green."


def test_post_jira_comment_appends_multiple_entries(use_tmp_data_files):
    jira_file, _ = use_tmp_data_files
    reporting_server.post_jira_comment("NASH-101", "First.")
    reporting_server.post_jira_comment("NASH-101", "Second.")
    store = json.loads(jira_file.read_text(encoding="utf-8"))
    assert [e["comment"] for e in store["NASH-101"]] == ["First.", "Second."]
