"""Comments use isolated demo storage and existing task visibility rules."""
from uuid import uuid4
import unittest

import test_regressions as fixtures
from app.models import ActivityLog, TaskComment, User


class CommentTests(unittest.TestCase):
    setUp = fixtures.TaskRegressions.setUp
    tearDown = fixtures.TaskRegressions.tearDown
    headers = fixtures.TaskRegressions.headers
    create = fixtures.TaskRegressions.create

    def post(self, task_id, user, body='Progress update', request_id=None):
        return self.client.post(f'/api/tasks/{task_id}/comments', headers=self.headers(user),
                                json={'body': body, 'request_id': request_id or str(uuid4())})

    def test_comment_author_permissions_and_plain_text(self):
        task_id = self.create()
        body = '<img src=x onerror=alert(1)>\nकाम पूरा हुआ'
        for user in [self.manager, self.worker]:
            result = self.post(task_id, user, body)
            self.assertEqual(result.status_code, 201, result.text)
            self.assertEqual(result.json()['author_id'], user)
            self.assertEqual(result.json()['body'], body)
            self.assertNotIn('request_id', result.json())
        self.assertEqual(self.post(task_id, self.outsider).status_code, 404)
        for user in [self.manager, self.worker]:
            result = self.client.get(f'/api/tasks/{task_id}/comments', headers=self.headers(user))
            self.assertEqual(len(result.json()), 2)
        self.assertEqual(self.client.get(f'/api/tasks/{task_id}/comments', headers=self.headers(self.outsider)).status_code, 404)
        self.assertEqual(self.client.get(f'/api/tasks/{task_id}/comments').status_code, 401)
        self.assertEqual(self.post(999999, self.worker).status_code, 404)

    def test_comment_validation_retry_and_audit(self):
        task_id = self.create()
        for body in ['', '   ', 'x' * 5001]:
            self.assertEqual(self.post(task_id, self.worker, body).status_code, 422)
        request_id = str(uuid4())
        first = self.post(task_id, self.worker, '  Ready  ', request_id)
        second = self.post(task_id, self.worker, 'Ready', request_id)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(first.json()['body'], 'Ready')
        self.assertEqual(self.post(task_id, self.manager, 'Ready', request_id).status_code, 409)
        self.assertEqual(self.post(task_id, self.worker, 'Different', request_id).status_code, 409)
        with self.sessions() as db:
            self.assertEqual(db.query(TaskComment).count(), 1)
            self.assertEqual(db.query(ActivityLog).filter_by(event_type='TASK_COMMENTED').count(), 1)

    def test_comment_pagination_and_task_deletion(self):
        task_id = self.create()
        ids = [self.post(task_id, self.worker, str(i)).json()['id'] for i in range(3)]
        endpoint = f'/api/tasks/{task_id}/comments'
        newest = self.client.get(endpoint + '?limit=2', headers=self.headers(self.worker)).json()
        self.assertEqual([c['id'] for c in newest], list(reversed(ids[1:])))
        older = self.client.get(endpoint + f'?before_id={newest[-1]["id"]}', headers=self.headers(self.worker)).json()
        self.assertEqual([c['id'] for c in older], ids[:1])
        self.assertEqual(self.client.get(endpoint + '?limit=101', headers=self.headers(self.worker)).status_code, 422)
        self.assertEqual(self.client.delete(f'/api/tasks/{task_id}', headers=self.headers(self.worker)).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(TaskComment).count(), 3)
        self.assertEqual(self.client.get(endpoint, headers=self.headers(self.worker)).status_code, 404)
        self.assertEqual(self.client.post(f'/api/tasks/{task_id}/restore', headers=self.headers(self.worker)).status_code, 200)
        self.assertEqual(len(self.client.get(endpoint, headers=self.headers(self.worker)).json()), 3)

    def test_admin_access_and_shared_viewer_cannot_comment(self):
        task_id = self.create()
        from app.models import Task
        with self.sessions() as db:
            db.get(Task, task_id).shared_with_id = self.outsider
            db.commit()
        self.assertEqual(self.post(task_id, self.outsider).status_code, 403)
        self.assertEqual(self.client.get(f'/api/tasks/{task_id}/comments', headers=self.headers(self.outsider)).status_code, 200)
        with self.sessions() as db:
            db.get(User, self.outsider).role = 'Admin'
            db.commit()
        self.assertEqual(self.post(task_id, self.outsider).status_code, 201)
        self.assertIn('microphone=(self)', self.client.get('/login').headers['Permissions-Policy'])
