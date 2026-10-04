"""Run with: python -B -m unittest discover -s tests -v.

Uses only an in-memory database; never connects to the configured app database.
"""
import os
import unittest
from datetime import date, datetime

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["LOG_FILE"] = ""
os.environ["APP_ENV"] = "development"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db
from app.models import User, Task
from app.auth import create_access_token


class TaskRegressions(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            manager = User(name="Manager", email="manager@thdc.co.in", hashed_password="unused")
            db.add(manager)
            db.flush()
            worker = User(name="Worker", email="worker@thdc.co.in", hashed_password="unused", manager_id=manager.id)
            outsider = User(name="Other", email="other@thdc.co.in", hashed_password="unused")
            db.add_all([worker, outsider])
            db.commit()
            self.manager, self.worker, self.outsider = manager.id, worker.id, outsider.id

        def override_db():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def headers(self, user):
        return {"Authorization": "Bearer " + create_access_token({"sub": str(user)})}

    def create(self):
        response = self.client.post("/api/tasks", headers=self.headers(self.manager), json={
            "title": "Report", "due_date": date.today().isoformat(), "assignee_id": self.worker,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_delegation_visibility_and_permissions(self):
        task_id = self.create()
        result = self.client.get("/api/tasks?filter_type=delegated-by-me", headers=self.headers(self.manager))
        self.assertEqual([t["id"] for t in result.json()], [task_id])
        for user in [self.worker, self.outsider]:
            result = self.client.get("/api/tasks?filter_type=delegated-by-me", headers=self.headers(user))
            self.assertEqual(result.json(), [])
        result = self.client.get("/api/tasks", headers=self.headers(self.manager))
        self.assertEqual([t["id"] for t in result.json()], [task_id])
        for user in [self.manager, self.outsider]:
            self.assertEqual(self.client.put(f"/api/tasks/{task_id}", headers=self.headers(user), json={"status": "done"}).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/tasks/{task_id}", headers=self.headers(user)).status_code, 403)

    def test_cannot_assign_to_unrelated_user(self):
        result = self.client.post("/api/tasks", headers=self.headers(self.manager), json={
            "title": "Report", "due_date": date.today().isoformat(), "assignee_id": self.outsider,
        })
        self.assertEqual(result.status_code, 403)

    def test_desk_all_statuses_and_personal_scope_for_all_roles(self):
        with self.sessions() as db:
            samples = [
                ("personal pending", self.manager, self.manager, "todo"),
                ("personal finished", self.manager, self.manager, "done"),
                ("assigned pending", self.outsider, self.manager, "inprogress"),
                ("assigned finished", self.outsider, self.manager, "done"),
                ("delegated pending", self.manager, self.worker, "todo"),
                ("delegated started", self.manager, self.worker, "inprogress"),
                ("delegated finished", self.manager, self.worker, "done"),
                ("team unrelated", self.worker, self.worker, "todo"),
                ("outsider private", self.outsider, self.outsider, "todo"),
            ]
            for title, creator, assignee, status in samples:
                db.add(Task(title=title, creator_id=creator, assignee_id=assignee,
                            status=status, due_date="2026-10-03"))
            db.commit()
        for role in ["Reporting Officer", "Admin"]:
            with self.sessions() as db:
                db.get(User, self.manager).role = role
                db.commit()
            desk = self.client.get("/api/tasks?filter_type=all", headers=self.headers(self.manager))
            self.assertEqual(desk.status_code, 200)
            self.assertEqual({t["title"] for t in desk.json()}, {
                "personal pending", "personal finished", "assigned pending", "assigned finished",
                "delegated pending", "delegated started", "delegated finished"})
            personal = self.client.get("/api/tasks?filter_type=personal", headers=self.headers(self.manager))
            self.assertEqual(personal.status_code, 200)
            self.assertEqual({t["title"] for t in personal.json()}, {"personal pending", "personal finished"})
        worker = self.client.get("/api/tasks?filter_type=personal", headers=self.headers(self.worker))
        self.assertEqual({t["title"] for t in worker.json()}, {"team unrelated"})

    def test_reopening_and_recompletion(self):
        task_id = self.create()
        for reopen_status in ["inprogress", "todo"]:
            self.client.put(f"/api/tasks/{task_id}", headers=self.headers(self.worker), json={"status": "done"})
            with self.sessions() as db:
                db.get(Task, task_id).completed_at = datetime(2000, 1, 1)
                db.commit()
            result = self.client.put(f"/api/tasks/{task_id}", headers=self.headers(self.worker), json={"status": reopen_status})
            self.assertEqual(result.status_code, 200)
            self.assertIsNone(result.json()["completed_at"])
            result = self.client.put(f"/api/tasks/{task_id}", headers=self.headers(self.worker), json={"status": "done"})
            self.assertGreater(datetime.fromisoformat(result.json()["completed_at"]), datetime(2000, 1, 1))

    def test_logout_clears_valid_cookie(self):
        self.client.cookies.set("task_manager_token", create_access_token({"sub": str(self.worker)}))
        result = self.client.post("/api/auth/logout")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Max-Age=0", result.headers["set-cookie"])

    def test_logout_clears_expired_cookie(self):
        self.client.cookies.set("task_manager_token", "expired.invalid.token")
        result = self.client.post("/api/auth/logout")
        self.assertEqual(result.status_code, 200)
        self.assertIn("Max-Age=0", result.headers["set-cookie"])

    def test_logout_is_idempotent(self):
        for _ in range(2):
            self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)

    def test_health_checks_database(self):
        result = self.client.get("/api/health")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"application": "continuum", "status": "ok"})

    def test_ai_setup_and_authentication(self):
        from unittest.mock import patch
        self.assertEqual(self.client.post('/api/ai/chat', json={'question':'Status?'}).status_code, 401)
        with patch.dict(os.environ, {'GROQ_API_KEY':'', 'GROQ_FREE_TIER_CONFIRMED':'false'}):
            result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'question':'Status?'})
            self.assertEqual(result.status_code, 503)
        with patch.dict(os.environ, {'GROQ_API_KEY':'test-secret', 'GROQ_FREE_TIER_CONFIRMED':'false'}):
            config = self.client.get('/api/ai/config', headers=self.headers(self.manager))
            self.assertNotIn('test-secret', config.text)
            self.assertEqual(self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'question':'Status?'}).status_code, 503)

    def test_ai_only_sends_authorized_task_context(self):
        from unittest.mock import patch, MagicMock
        from app.ai_console import _requests
        _requests.clear()
        self.create()
        with self.sessions() as db:
            db.add(Task(title='SECRET OUTSIDER', creator_id=self.outsider, assignee_id=self.outsider,
                        due_date='2026-10-03', status='todo'))
            db.commit()
        reply = MagicMock(status_code=200, is_success=True)
        reply.json.return_value = {'choices':[{'message':{'content':'Report is pending [Task #1].'}}]}
        with patch.dict(os.environ, {'GROQ_API_KEY':'test-secret', 'GROQ_FREE_TIER_CONFIRMED':'true'}), patch('app.ai_console.httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = reply
            result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'question':'What is pending?'})
            self.assertEqual(result.status_code, 200, result.text)
            body = post.call_args.kwargs['json']
            self.assertEqual(body['model'], 'qwen/qwen3.8-27b')
            self.assertNotIn('SECRET OUTSIDER', str(body))
            self.assertNotIn('hashed_password', str(body))
            self.assertNotIn('manager@thdc.co.in', str(body))
            self.assertEqual(result.json()['included_tasks'], 1)
            self.assertEqual(result.json()['answer'], 'Report is pending [Task #1].')
            post.reset_mock()
            result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'question':'Hidden?', 'assignee_id':self.outsider})
            self.assertEqual(result.json()['total_tasks'], 0)
            post.assert_not_called()

    def test_ai_context_is_bounded_and_labels_partial_data(self):
        from unittest.mock import patch, MagicMock
        from app.ai_console import _requests
        _requests.clear()
        with self.sessions() as db:
            for i in range(110):
                db.add(Task(title=f'Task {i}', summary='Description ' * 200, creator_id=self.manager,
                            assignee_id=self.worker, due_date='2026-10-03', status='todo'))
            db.commit()
        reply = MagicMock(status_code=200, is_success=True)
        reply.json.return_value = {'choices':[{'message':{'content':'Partial summary.'}}]}
        with patch.dict(os.environ, {'GROQ_API_KEY':'test-secret', 'GROQ_FREE_TIER_CONFIRMED':'true'}), patch('app.ai_console.httpx.Client') as client:
            post = client.return_value.__enter__.return_value.post
            post.return_value = reply
            result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'mode':'summary'})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()['partial'])
            self.assertEqual(result.json()['total_tasks'], 110)
            self.assertLessEqual(result.json()['included_tasks'], 30)
            self.assertLess(len(post.call_args.kwargs['json']['messages'][1]['content'].encode('utf-8')), 14000)
        _requests.clear()

    def test_ai_limits_and_safe_provider_errors(self):
        from unittest.mock import patch, MagicMock
        from app.ai_console import _requests
        _requests.clear()
        self.create()
        reply = MagicMock(status_code=429, is_success=False)
        with patch.dict(os.environ, {'GROQ_API_KEY':'test-secret', 'GROQ_FREE_TIER_CONFIRMED':'true'}), patch('app.ai_console.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value = reply
            for _ in range(5):
                result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'mode':'summary'})
                self.assertEqual(result.status_code, 429)
                self.assertNotIn('test-secret', result.text)
            client.return_value.__enter__.return_value.post.reset_mock()
            result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'mode':'summary'})
            self.assertEqual(result.status_code, 429)
            client.return_value.__enter__.return_value.post.assert_not_called()
        _requests.clear()

    def test_ai_oversized_request_has_actionable_safe_error(self):
        from unittest.mock import patch, MagicMock
        from app.ai_console import _requests
        _requests.clear()
        self.create()
        reply = MagicMock(status_code=413, is_success=False)
        reply.text = 'private organization details test-secret'
        with patch.dict(os.environ, {'GROQ_API_KEY':'test-secret', 'GROQ_FREE_TIER_CONFIRMED':'true'}), patch('app.ai_console.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value = reply
            result = self.client.post('/api/ai/chat', headers=self.headers(self.manager), json={'mode':'summary'})
            self.assertEqual(result.status_code, 413)
            self.assertIn('Filter by employee or status', result.json()['detail'])
            self.assertNotIn('test-secret', result.text)
            self.assertNotIn('private organization', result.text)
            client.return_value.__enter__.return_value.post.assert_called_once()
        _requests.clear()

    def test_summary_column_filters_and_pdf_match(self):
        from io import BytesIO
        from pypdf import PdfReader
        task_id = self.create()
        with self.sessions() as db:
            task = db.get(Task, task_id)
            task.due_date = "2000-01-15"
            task.priority = "High"
            db.add(Task(title="Hidden report", creator_id=self.outsider, assignee_id=self.outsider,
                        due_date="2000-01-15", priority="High"))
            db.commit()
        params = dict(task_text=f"#{task_id} report", creator_text="MANAGER", assignee_id=self.worker,
                      status="pending", priority="High", due_from="2000-01-01", due_to="2000-01-31", overdue="yes")
        result = self.client.get('/api/reports/tasks', params=params, headers=self.headers(self.manager))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([row['id'] for row in result.json()['tasks']], [task_id])
        self.assertEqual(result.json()['totals']['overdue'], 1)
        pdf = self.client.get('/api/reports/tasks.pdf', params=params, headers=self.headers(self.manager))
        self.assertEqual(pdf.status_code, 200)
        text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Report', text)
        self.assertNotIn('Hidden report', text)
        for extra in ({'overdue':'no'}, {'task_text':'%'}, {'creator_text':'Other'}, {'due_from':'2000-01-16'}):
            result = self.client.get('/api/reports/tasks', params={**params, **extra}, headers=self.headers(self.manager))
            self.assertEqual(result.json()['totals']['total'], 0)
            self.assertEqual(result.json()['tasks'], [])
        for extra in ({'due_from':'invalid'}, {'due_from':'2000-02-01'}, {'overdue':'invalid'}, {'task_text':'x'*201}):
            for endpoint in ('/api/reports/tasks', '/api/reports/tasks.pdf'):
                result = self.client.get(endpoint, params={**params, **extra}, headers=self.headers(self.manager))
                self.assertEqual(result.status_code, 400, result.text)

    def test_summary_and_pdf_permissions_filters(self):
        from io import BytesIO
        from pypdf import PdfReader
        task_id = self.create()
        with self.sessions() as db:
            task = db.get(Task, task_id)
            task.priority = 'High'
            task.due_date = '2000-01-01'
            db.add(Task(title='CONFIDENTIAL OUTSIDER', creator_id=self.outsider, assignee_id=self.outsider,
                        status='done', priority='Low', due_date='2000-01-01'))
            db.commit()
        query = f'assignee_id={self.worker}&status=pending&priority=High'
        summary = self.client.get('/api/reports/tasks?' + query, headers=self.headers(self.manager))
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['totals'], {'total':1, 'pending':1, 'done':0, 'overdue':1})
        pdf = self.client.get('/api/reports/tasks.pdf?' + query, headers=self.headers(self.manager))
        self.assertEqual(pdf.status_code, 200)
        self.assertIn('application/pdf', pdf.headers['content-type'])
        self.assertIn('attachment', pdf.headers['content-disposition'])
        text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Report', text)
        self.assertIn('Worker', text)
        self.assertNotIn('CONFIDENTIAL', text)
        hidden = self.client.get(f'/api/reports/tasks?assignee_id={self.outsider}', headers=self.headers(self.manager))
        self.assertEqual(hidden.json()['tasks'], [])
        completed = self.client.get('/api/reports/tasks?status=done', headers=self.headers(self.manager))
        self.assertEqual(completed.json()['tasks'], [])
        self.assertEqual(self.client.get('/api/reports/tasks.pdf').status_code, 401)
        self.assertEqual(self.client.get('/api/reports/tasks?status=invalid', headers=self.headers(self.manager)).status_code, 400)
        self.make_admin()
        admin = self.client.get('/api/reports/tasks', headers=self.headers(self.outsider))
        self.assertEqual(admin.json()['totals']['total'], 2)

    def test_pdf_empty_and_multiple_pages(self):
        from io import BytesIO
        from pypdf import PdfReader
        from app.task_reports import summary_pdf
        data = {'tasks': [], 'totals': {'total': 0, 'pending': 0, 'done': 0, 'overdue': 0}, 'generated_at': '2026-10-03T12:00:00+05:30'}
        empty = PdfReader(BytesIO(summary_pdf(data, 'Test User', 'All tasks')))
        self.assertIn('No tasks match', empty.pages[0].extract_text())
        data['tasks'] = [dict(id=i, title='Long task title with <markup> & details ' * 4,
            creator='Reporting Officer', assignee='Employee With Long Name', status='inprogress', priority='High', due_date='2026-10-03', overdue=False) for i in range(70)]
        data['totals'] = {'total':70, 'pending':70, 'done':0, 'overdue':0}
        report = PdfReader(BytesIO(summary_pdf(data, 'Test User', 'All tasks')))
        self.assertGreater(len(report.pages), 1)
        for page in report.pages:
            self.assertIn('Assigned by', page.extract_text())
        self.assertIn('#69', report.pages[-1].extract_text())

    def test_manager_update_requires_admin(self):
        response = self.client.put(f"/api/users/{self.worker}/manager", headers=self.headers(self.manager), json={"manager_id": self.outsider})
        self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            self.assertEqual(db.get(User, self.worker).manager_id, self.manager)

    def make_admin(self):
        with self.sessions() as db:
            db.get(User, self.outsider).role = "Admin"
            db.commit()

    def test_update_and_remove_manager_changes_visibility_and_audits(self):
        from app.models import ActivityLog
        task_id = self.create()
        self.make_admin()
        response = self.client.put(f"/api/users/{self.worker}/manager", headers=self.headers(self.outsider), json={"manager_id": self.outsider})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["manager_id"], self.outsider)
        response = self.client.get('/api/tasks?filter_type=team-hierarchy', headers=self.headers(self.manager))
        self.assertEqual(response.json(), [])
        response = self.client.put(f"/api/users/{self.worker}/manager", headers=self.headers(self.outsider), json={"manager_id": None})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["manager_id"])
        with self.sessions() as db:
            self.assertEqual(db.get(Task, task_id).assignee_id, self.worker)
            self.assertEqual(db.query(ActivityLog).filter_by(event_type='REPORTING_MANAGER_UPDATED').count(), 2)

    def test_reporting_cycles_and_missing_manager_rejected(self):
        self.make_admin()
        for employee, manager, status in [(self.worker, self.worker, 400), (self.manager, self.worker, 400), (self.worker, 99999, 404), (99999, None, 404)]:
            response = self.client.put(f"/api/users/{employee}/manager", headers=self.headers(self.outsider), json={"manager_id": manager})
            self.assertEqual(response.status_code, status, response.text)
        response = self.client.put(f"/api/users/{self.worker}/manager", headers=self.headers(self.outsider), json={})
        self.assertEqual(response.status_code, 422)
        with self.sessions() as db:
            self.assertEqual(db.get(User, self.worker).manager_id, self.manager)
            self.assertIsNone(db.get(User, self.manager).manager_id)

    def test_indirect_reporting_cycle_rejected(self):
        self.make_admin()
        with self.sessions() as db:
            db.get(User, self.outsider).manager_id = self.worker
            db.commit()
        response = self.client.put(f"/api/users/{self.manager}/manager", headers=self.headers(self.outsider), json={"manager_id": self.outsider})
        self.assertEqual(response.status_code, 400)

    def import_csv(self, content, admin=True, fallback=""):
        if admin:
            with self.sessions() as db:
                db.get(User, self.manager).role = "Admin"
                db.commit()
        return self.client.post("/api/users/import", headers=self.headers(self.manager),
                                files={"file": ("employees.csv", content, "text/csv")},
                                data={"default_password": fallback})

    def test_individual_password_upload_and_login(self):
        from app.auth import verify_password
        result = self.import_csv("username,password\nnew@thdc.co.in,Individual-123\nsecond@thdc.co.in,Different-456\n")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["imported"], 2)
        self.assertNotIn("Individual-123", result.text)
        with self.sessions() as db:
            user = db.query(User).filter_by(email="new@thdc.co.in").one()
            self.assertNotEqual(user.hashed_password, "Individual-123")
            self.assertTrue(verify_password("Individual-123", user.hashed_password))
        for email, password in [("new@thdc.co.in", "Individual-123"), ("second@thdc.co.in", "Different-456")]:
            login = self.client.post("/api/auth/login", data={"username": email, "password": password})
            self.assertEqual(login.status_code, 200)

    def test_import_requires_admin(self):
        result = self.import_csv("username,password\nnew@thdc.co.in,Individual-123\n", admin=False)
        self.assertEqual(result.status_code, 403)

    def test_import_rejects_invalid_rows_atomically(self):
        cases = [
            "username,password\ngood@thdc.co.in,Individual-123\nbad@thdc.co.in,short\n",
            "username,password\ngood@thdc.co.in,Individual-123\ngood@thdc.co.in,Different-123\n",
            "username,password,manager_email\na@thdc.co.in,Individual-123,b@thdc.co.in\nb@thdc.co.in,Different-123,a@thdc.co.in\n",
            "username,password,manager_email\na@thdc.co.in,Individual-123,missing@thdc.co.in\n",
            "username,password\na@thdc.co.in,Individual-123,extra\n",
            "username,password\n",
        ]
        for csv in cases:
            with self.subTest(csv=csv):
                result = self.import_csv(csv)
                self.assertEqual(result.status_code, 400, result.text)
                self.assertNotIn("Individual-123", result.text)
                with self.sessions() as db:
                    self.assertEqual(db.query(User).count(), 3)

    def test_import_existing_accounts_are_unchanged(self):
        result = self.import_csv("username,password\nworker@thdc.co.in,Replacement-123\n")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["skipped_existing"], ["worker@thdc.co.in"])
        with self.sessions() as db:
            self.assertEqual(db.get(User, self.worker).hashed_password, "unused")

    def test_legacy_import_and_forward_manager_reference(self):
        result = self.import_csv("name,email,role,manager_email\nNew,new@thdc.co.in,Engineer,boss@thdc.co.in\nBoss,boss@thdc.co.in,Reporting Officer,\n", fallback="Fallback-123")
        self.assertEqual(result.status_code, 200, result.text)
        with self.sessions() as db:
            user = db.query(User).filter_by(email="new@thdc.co.in").one()
            boss = db.query(User).filter_by(email="boss@thdc.co.in").one()
            self.assertEqual(user.manager_id, boss.id)

    def test_health_reports_database_failure_without_details(self):
        from unittest.mock import Mock
        broken_db = Mock()
        broken_db.execute.side_effect = RuntimeError("private database connection details")
        app.dependency_overrides[get_db] = lambda: broken_db
        result = self.client.get("/api/health")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json(), {"detail": "Database unavailable"})


if __name__ == "__main__":
    unittest.main()
