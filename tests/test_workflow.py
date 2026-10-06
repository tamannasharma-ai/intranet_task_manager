import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
import test_regressions as fixtures
from app.models import Task, Notification
from app.workflow import today_ist


class WorkflowTests(unittest.TestCase):
    setUp = fixtures.TaskRegressions.setUp
    tearDown = fixtures.TaskRegressions.tearDown
    headers = fixtures.TaskRegressions.headers
    create = fixtures.TaskRegressions.create

    def update(self, task, user=None, **payload):
        return self.client.put(f'/api/tasks/{task}', headers=self.headers(user or self.worker), json=payload)

    def members(self, task, role=None, user=None):
        return self.client.put(f'/api/tasks/{task}/collaboration', headers=self.headers(user or self.manager),
            json={'members': [] if role is None else [{'user_id': self.outsider, 'role': role}]})

    def tasks(self, user, view='all'):
        response = self.client.get('/api/tasks?filter_type='+view, headers=self.headers(user))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def notifications(self, user):
        return self.client.get('/api/notifications', headers=self.headers(user)).json()

    def test_my_day_is_owner_only_and_excludes_completed_archived_and_deleted(self):
        task = self.create()
        self.assertEqual([t['id'] for t in self.tasks(self.worker, 'my-day')], [task])
        self.assertEqual(self.tasks(self.manager, 'my-day'), [])
        self.update(task, status='done')
        self.assertEqual(self.tasks(self.worker, 'my-day'), [])
        self.update(task, status='todo')
        for action in ['archive', 'restore']:
            result = self.client.post(f'/api/tasks/{task}/{action}', headers=self.headers(self.worker))
            self.assertEqual(result.status_code, 200)
            self.assertEqual(bool(self.tasks(self.worker, 'my-day')), action == 'restore')
        self.client.delete(f'/api/tasks/{task}', headers=self.headers(self.worker))
        self.assertEqual(self.tasks(self.worker, 'my-day'), [])

    def test_collaborators_and_viewers_have_different_permissions(self):
        task = self.create()
        self.assertEqual(self.members(task, 'viewer').status_code, 200)
        self.assertEqual([t['id'] for t in self.tasks(self.outsider, 'shared')], [task])
        self.assertEqual(self.update(task, self.outsider, status='done').status_code, 403)
        self.assertEqual(self.members(task, 'collaborator').status_code, 200)
        self.assertEqual(self.update(task, self.outsider, status='inprogress').status_code, 200)
        self.assertEqual(self.update(task, self.outsider, title='Hijacked').status_code, 403)
        self.assertEqual(self.update(task, self.outsider, assignee_id=self.outsider).status_code, 403)
        self.assertEqual(self.members(task, user=self.outsider).status_code, 403)
        self.assertEqual(self.client.post(f'/api/tasks/{task}/archive', headers=self.headers(self.outsider)).status_code, 403)
        self.assertEqual(self.client.post(f'/api/tasks/{task}/comments', headers=self.headers(self.outsider),
            json={'body':'Update', 'request_id':str(uuid4())}).status_code, 201)
        self.assertTrue(self.notifications(self.outsider)['items'])
        self.assertEqual(self.members(task).status_code, 200)
        self.assertEqual(self.tasks(self.outsider, 'shared'), [])
        self.assertEqual(self.client.get(f'/api/tasks/{task}', headers=self.headers(self.outsider)).status_code, 404)
        self.assertEqual(self.notifications(self.outsider)['items'], [])

    def test_blocked_requires_reason_and_is_in_pending_reports(self):
        task = self.create()
        self.assertEqual(self.update(task, status='blocked').status_code, 422)
        self.assertEqual(self.update(task, status='blocked', blocked_reason='   ').status_code, 422)
        self.assertEqual(self.update(task, status='blocked', blocked_reason='Awaiting drawing').status_code, 200)
        response = self.client.get('/api/reports/tasks?status=pending', headers=self.headers(self.manager))
        self.assertEqual(response.json()['tasks'][0]['status'], 'blocked')
        self.assertEqual(self.client.get('/api/reports/tasks.pdf?status=blocked', headers=self.headers(self.manager)).status_code, 200)
        self.assertIsNone(self.update(task, status='inprogress').json()['blocked_reason'])

    def test_repeat_month_end_and_recompletion_do_not_duplicate(self):
        task = self.create()
        self.update(task, due_date='2028-01-31', recurrence='monthly', checklist=[{'text':'Inspect', 'done':True}])
        self.update(task, status='done')
        self.update(task, status='todo')
        self.update(task, status='done')
        with self.sessions() as db:
            children = db.query(Task).filter_by(recurrence_parent_id=task).all()
            self.assertEqual(len(children), 1)
            child = children[0]
            child_id = child.id
            self.assertEqual(child.due_date, '2028-02-29')
            self.assertEqual(child.checklist, [{'text':'Inspect', 'done':False}])
            self.assertEqual(child.status, 'todo')
        self.update(child_id, due_date='2028-02-29', status='done')
        with self.sessions() as db:
            self.assertEqual(db.query(Task).filter_by(recurrence_parent_id=child_id).one().due_date, '2028-03-31')

    def test_daily_and_weekly_repeat_and_none(self):
        for frequency, expected in [('daily','2026-11-01'), ('weekly','2026-11-07'), ('none',None)]:
            task=self.create()
            self.update(task, due_date='2026-10-31', recurrence=frequency)
            self.update(task, status='done')
            with self.sessions() as db:
                child=db.query(Task).filter_by(recurrence_parent_id=task).first()
                self.assertEqual(child.due_date if child else None, expected)

    def test_archive_and_trash_restore_with_permissions(self):
        task=self.create()
        self.assertEqual(self.client.post(f'/api/tasks/{task}/archive', headers=self.headers(self.manager)).status_code, 403)
        self.client.post(f'/api/tasks/{task}/archive', headers=self.headers(self.worker))
        self.assertEqual(self.tasks(self.worker), [])
        self.assertEqual(self.update(task, title='Changed').status_code, 409)
        self.assertEqual([t['id'] for t in self.tasks(self.worker,'archive')], [task])
        self.assertEqual(self.client.get('/api/reports/tasks', headers=self.headers(self.worker)).json()['tasks'], [])
        self.client.delete(f'/api/tasks/{task}', headers=self.headers(self.worker))
        self.assertEqual(self.tasks(self.worker,'archive'), [])
        self.assertEqual([t['id'] for t in self.tasks(self.worker,'trash')], [task])
        self.assertEqual(self.client.post(f'/api/tasks/{task}/restore', headers=self.headers(self.outsider)).status_code, 404)
        self.assertEqual(self.client.post(f'/api/tasks/{task}/restore', headers=self.headers(self.worker)).status_code, 200)
        self.assertEqual(len(self.tasks(self.worker)), 1)

    def test_reminders_are_deduplicated_and_read_state_is_private(self):
        task=self.create()
        self.update(task, due_date=(today_ist()+timedelta(days=1)).isoformat())
        first=self.notifications(self.worker)
        second=self.notifications(self.worker)
        self.assertEqual(first,second)
        self.assertEqual(len([n for n in first['items'] if n['kind']=='reminder']),1)
        item=first['items'][0]
        self.assertEqual(self.client.post(f'/api/notifications/{item["id"]}/read', headers=self.headers(self.outsider)).status_code,404)
        self.client.post('/api/notifications/read-all', headers=self.headers(self.worker))
        self.assertEqual(self.notifications(self.worker)['unread'],0)
        self.update(task, due_date=(today_ist()+timedelta(days=10)).isoformat())
        self.assertFalse(any(n['kind']=='reminder' for n in self.notifications(self.worker)['items']))
        self.update(task, due_date=today_ist().isoformat())
        self.assertEqual(len([n for n in self.notifications(self.worker)['items'] if n['kind']=='reminder']),1)
        self.update(task,status='done')
        self.assertFalse(any(n['kind']=='reminder' for n in self.notifications(self.worker)['items']))

    def test_invalid_checklists_members_and_atomic_update(self):
        task=self.create()
        for checklist in [[{'text':''}], [{'text':'x'*301}], [{'text':str(i)} for i in range(51)], None]:
            self.assertEqual(self.update(task,checklist=checklist).status_code,422)
        for members in [[{'user_id':self.worker,'role':'viewer'}],
                        [{'user_id':self.outsider,'role':'viewer'}]*2,
                        [{'user_id':99999,'role':'viewer'}]]:
            response=self.client.put(f'/api/tasks/{task}/collaboration',headers=self.headers(self.manager),json={'members':members})
            self.assertEqual(response.status_code,422)
        # Audit failures must not commit a partially edited task.
        with patch('app.main.record_activity',side_effect=RuntimeError('test audit failure')):
            with self.assertRaises(RuntimeError):
                self.update(task,title='Must roll back')
        with self.sessions() as db:
            self.assertEqual(db.get(Task,task).title,'Report')
