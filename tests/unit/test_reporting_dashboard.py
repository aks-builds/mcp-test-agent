import json

import pytest
from fastapi.testclient import TestClient

from servers.reporting import dashboard


@pytest.fixture
def client(tmp_path, monkeypatch):
    jira_file = tmp_path / "jira_comments.json"
    slack_file = tmp_path / "slack_messages.json"
    jira_file.write_text(json.dumps({"NASH-101": [{"comment": "hi"}]}), encoding="utf-8")
    slack_file.write_text(json.dumps({"#qa-alerts": [{"text": "hello"}]}), encoding="utf-8")
    monkeypatch.setattr(dashboard, "JIRA_FILE", jira_file)
    monkeypatch.setattr(dashboard, "SLACK_FILE", slack_file)
    return TestClient(dashboard.app)


def test_jira_feed_returns_stored_comments(client):
    resp = client.get("/api/jira")
    assert resp.status_code == 200
    assert resp.json()["NASH-101"][0]["comment"] == "hi"


def test_slack_feed_returns_stored_messages(client):
    resp = client.get("/api/slack")
    assert resp.status_code == 200
    assert resp.json()["#qa-alerts"][0]["text"] == "hello"


def test_jira_feed_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "JIRA_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(dashboard, "SLACK_FILE", tmp_path / "missing2.json")
    client = TestClient(dashboard.app)
    assert client.get("/api/jira").json() == {}
