from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Task Tracker", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_tasks: list[dict] = []
_next_id = 1


class TaskCreate(BaseModel):
    title: str


class Task(BaseModel):
    id: int
    title: str
    completed: bool


def reset_tasks() -> None:
    global _tasks, _next_id
    _tasks = []
    _next_id = 1


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/tasks", response_model=list[Task])
def list_tasks():
    return _tasks


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(payload: TaskCreate):
    global _next_id
    task = {"id": _next_id, "title": payload.title, "completed": False}
    _tasks.append(task)
    _next_id += 1
    return task
