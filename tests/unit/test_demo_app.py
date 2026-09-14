from fastapi.testclient import TestClient

from demo_app.main import app, reset_tasks

client = TestClient(app)


def setup_function():
    reset_tasks()


def test_create_and_list_task():
    resp = client.post("/tasks", json={"title": "Buy milk"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Buy milk"
    assert body["completed"] is False

    resp = client.get("/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Buy milk"
