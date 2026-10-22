from fastapi.testclient import TestClient

from task_tracker.main import app, reset_tasks

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


def test_complete_task():
    created = client.post("/tasks", json={"title": "Buy milk"}).json()
    resp = client.post(f"/tasks/{created['id']}/complete")
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


def test_complete_missing_task_404():
    resp = client.post("/tasks/999/complete")
    assert resp.status_code == 404
