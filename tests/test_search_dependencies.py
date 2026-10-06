import unittest
from uuid import uuid4
import test_regressions as fixtures

class SearchDependencyTests(unittest.TestCase):
    setUp = fixtures.TaskRegressions.setUp
    tearDown = fixtures.TaskRegressions.tearDown
    headers = fixtures.TaskRegressions.headers
    create = fixtures.TaskRegressions.create

    def search(self, text, user=None, scope='active'):
        return self.client.get('/api/search/tasks', params={'q':text,'scope':scope}, headers=self.headers(user or self.worker))

    def link(self, task, prerequisite, user=None):
        return self.client.post(f'/api/tasks/{task}/dependencies', json={'depends_on_id':prerequisite}, headers=self.headers(user or self.worker))

    def update(self, task, **payload):
        return self.client.put(f'/api/tasks/{task}', json=payload, headers=self.headers(self.worker))

    def test_search_fields_literals_and_permissions(self):
        task=self.create()
        self.update(task, title='Budget 50%_ready', summary='monsoon planning')
        self.client.post(f'/api/tasks/{task}/comments', headers=self.headers(self.worker), json={'body':'Procurement discussion','request_id':str(uuid4())})
        for text in ['50%_', 'MONSOON', 'procurement', 'Worker', 'Manager', f'#{task}']:
            self.assertEqual([t['id'] for t in self.search(text).json()], [task], text)
        self.assertEqual(self.search('Report').json(), [])
        self.assertEqual(self.search('monsoon',self.outsider).json(), [])
        self.assertEqual(self.search(' ').status_code,422)
        self.assertEqual(self.search('budget',scope='unknown').status_code,422)

    def test_search_archive_trash_scopes(self):
        task=self.create()
        self.client.post(f'/api/tasks/{task}/archive',headers=self.headers(self.worker))
        self.assertEqual(self.search('Report').json(),[])
        self.assertEqual(len(self.search('Report',scope='archive').json()),1)
        self.client.delete(f'/api/tasks/{task}',headers=self.headers(self.worker))
        self.assertEqual(self.search('Report',scope='archive').json(),[])
        self.assertEqual(len(self.search('Report',scope='trash').json()),1)

    def test_dependencies_gate_progress_and_reject_cycles(self):
        a,b,c=self.create(),self.create(),self.create()
        self.assertEqual(self.link(a,a).status_code,422)
        self.assertEqual(self.link(a,b).status_code,200)
        self.assertEqual(self.link(a,b).status_code,200)
        self.assertEqual(self.link(b,c).status_code,200)
        self.assertEqual(self.link(c,a).status_code,422)
        for status in ['inprogress','done']:
            self.assertEqual(self.update(a,status=status).status_code,409)
        self.assertEqual(self.update(c,status='done').status_code,200)
        self.assertEqual(self.update(b,status='done').status_code,200)
        self.assertEqual(self.update(a,status='inprogress').status_code,200)
        self.assertEqual(self.update(a,status='done').status_code,200)
        task=self.client.get(f'/api/tasks/{a}',headers=self.headers(self.worker)).json()
        self.assertEqual((task['dependency_count'],task['waiting_count']),(1,0))

    def test_permissions_redaction_and_remove(self):
        a,b=self.create(),self.create()
        self.assertEqual(self.link(a,b,self.manager).status_code,200)
        self.client.put(f'/api/tasks/{a}/collaboration',headers=self.headers(self.manager),json={'members':[{'user_id':self.outsider,'role':'collaborator'}]})
        self.assertEqual(self.link(a,b,self.outsider).status_code,403)
        links=self.client.get(f'/api/tasks/{a}/dependencies',headers=self.headers(self.outsider)).json()
        self.assertIsNone(links[0]['task_id'])
        self.assertNotIn('Report',links[0]['title'])
        path=f"/api/tasks/{a}/dependencies/{links[0]['link_id']}"
        self.assertEqual(self.client.delete(path,headers=self.headers(self.outsider)).status_code,403)
        self.assertEqual(self.client.delete(path,headers=self.headers(self.worker)).status_code,200)
        self.assertEqual(self.update(a,status='done').status_code,200)

    def test_deleted_prerequisite_blocks_until_restored(self):
        a,b=self.create(),self.create()
        self.link(a,b)
        self.update(b,status='done')
        self.client.delete(f'/api/tasks/{b}',headers=self.headers(self.worker))
        self.assertEqual(self.update(a,status='done').status_code,409)
        self.client.post(f'/api/tasks/{b}/restore',headers=self.headers(self.worker))
        self.assertEqual(self.update(a,status='done').status_code,200)
