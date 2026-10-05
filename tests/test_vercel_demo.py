"""Exercise a fresh serverless process, without ASGI lifespan startup."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class VercelDemoTests(unittest.TestCase):
    def test_fresh_vercel_instance(self):
        script = r'''
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine
from app.demo_data import seed_demo
from app.models import User, Task, TaskHistory, ActivityLog

assert engine.url.database is None
with SessionLocal() as db:
    counts = tuple(db.query(model).count() for model in (Task, TaskHistory, ActivityLog))
    seed_demo(db)
    assert db.query(User).count() == 15
    assert db.query(Task).count() == 73
    assert counts == tuple(db.query(model).count() for model in (Task, TaskHistory, ActivityLog))
client = TestClient(app, base_url="https://demo.example.com")
assert client.get("/api/health").status_code == 200
users = client.get("/api/auth/users").json()
assert len(users) == 15
assert all(u["email"].endswith("@example.com") for u in users)
assert all("hashed_password" not in u for u in users)
for path in ("/login", "/login.html", "/vendor/continuum-theme.css", "/vendor/tailwindcdn.js"):
    assert client.get(path).status_code == 200, path
assert client.get("/dashboard", follow_redirects=False).status_code == 303
for user in users:
    response = client.post("/api/auth/login", data={"username": user["email"], "password": "DemoPass123!"})
    assert response.status_code == 200, response.text
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    demo_headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    personal = client.get("/api/tasks?filter_type=personal", headers=demo_headers).json()
    assert {task["status"] for task in personal} == {"todo", "inprogress", "done"}
    assert all(task["history"] for task in personal)
    if user["manager_id"]:
        for view in ("assigned-by-ro", "shared"):
            assert client.get("/api/tasks?filter_type=" + view, headers=demo_headers).json(), (user, view)
    if user["id"] in (1, 2, 3, 4):
        for view in ("team-hierarchy", "delegated-by-me"):
            assert client.get("/api/tasks?filter_type=" + view, headers=demo_headers).json(), (user, view)
response = client.post("/api/auth/login", data={"username": "arjun@example.com", "password": "DemoPass123!"})
headers = {"Authorization": "Bearer " + response.json()["access_token"]}
assert client.get("/dashboard").status_code == 200
assert client.get("/", follow_redirects=False).headers["location"] == "/dashboard"
response = client.post("/api/tasks", headers=headers, json={"title": "Demo review", "due_date": "2026-12-01", "assignee_id": 5})
assert response.status_code == 200, response.text
tasks = client.get("/api/tasks?filter_type=delegated-by-me", headers=headers).json()
assert any(task["id"] == response.json()["id"] and task["title"] == "Demo review" for task in tasks)
assert client.get("/api/reports/tasks.pdf", headers=headers).content.startswith(b"%PDF")
assert client.post("/api/auth/logout", headers=headers).status_code == 200
assert client.get("/dashboard", follow_redirects=False).status_code == 303
client.close()
engine.dispose()
'''
        env = dict(os.environ, VERCEL="1", APP_ENV="production",
                   SECRET_KEY="test-only-key-for-serverless-demo-smoke-test",
                   DATABASE_URL="postgresql://unused:unused@invalid/unused", LOG_LEVEL="ERROR")
        env.pop("LOG_FILE", None)
        result = subprocess.run([sys.executable, "-B", "-c", script], env=env,
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
