const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('app/static/index.html', 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
scripts.forEach(script => new vm.Script(script));
const code = scripts.join('\n');
const context = {document: {createElement: () => ({})}, currentUser: {id: 1, manager_id: 2}};
vm.createContext(context);
for (const name of ['escapeHtml', 'taskDueLabel', 'createCard', 'localDateToday', 'formatTime', 'logout']) {
  const prefix = name === 'logout' ? '    async function ' : '    function ';
  const start = code.indexOf(prefix + name + '(');
  assert.ok(start >= 0);
  const end = code.indexOf('\n    }', start) + 6;
  vm.runInContext(code.slice(start, end), context);
}
const today = new Date(2026, 9, 3, 12);
assert.equal(context.taskDueLabel({due_date:'2026-10-03',status:'todo'}, today).label, 'Due today');
assert.equal(context.taskDueLabel({due_date:'2026-10-04',status:'todo'}, today).label, 'Due tomorrow');
assert.equal(context.taskDueLabel({due_date:'2026-09-30',status:'inprogress'}, today).label, '3 days overdue');
assert.equal(context.taskDueLabel({due_date:'2026-09-30',status:'done'}, today).label, 'Finished');
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
assert.equal(new Set(ids).size, ids.length, 'Duplicate UI control IDs');
const hostile = '<img src=x onerror=alert(1)>';
context.task = {id: 1, title: hostile, summary: hostile, priority: 'High', creator_id: 2, assignee_id: 1,
  creator: {id:2,name:hostile}, assignee: {name:hostile}, category: {name:hostile}, due_date:'2026-10-03',history:[]};
const card = vm.runInContext('createCard(task)', context);
assert.ok(!card.innerHTML.includes('<img'));
assert.ok(card.innerHTML.includes('&lt;img'));

// Exercise the actual board rendering and controls with more than one page
// in every column, including page clamping after completion/deletion.
const elements = new Map();
const board = {
  currentUser: {id: 1}, pageSize: 2,
  columnPages: {todo: 1, inprogress: 1, done: 1},
  currentTasks: [],
  createCard: task => ({taskId: task.id}),
  document: {
    createElement: () => ({}),
    getElementById: id => {
      if (!elements.has(id)) elements.set(id, {
        children: [], replaceChildren() { this.children = []; },
        appendChild(child) { this.children.push(child); }
      });
      return elements.get(id);
    }
  }
};
vm.createContext(board);
for (const name of ['compareTaskOrder', 'getColumnTasks', 'updatePagination', 'changePage', 'changePageSize', 'renderBoard']) {
  const start = code.indexOf('    function ' + name + '(');
  const end = code.indexOf('\n    }', start) + 6;
  vm.runInContext(code.slice(start, end), board);
}
board.currentTasks = [
  {id:1,status:'todo',due_date:'2026-10-01',priority:'Low'},
  {id:2,status:'todo',due_date:'2026-10-05',priority:'High'},
  {id:3,status:'todo',due_date:'2026-10-01',priority:'High'},
  {id:4,status:'inprogress',due_date:'2026-10-01',priority:'High'},
  {id:5,status:'inprogress',due_date:'2026-10-02',priority:'High'},
  {id:6,status:'inprogress',due_date:'2026-10-03',priority:'High'},
  {id:7,status:'done',completed_at:'2026-10-01T12:00:00',priority:'High'},
  {id:8,status:'done',completed_at:'2026-10-03T12:00:00',priority:'Low'},
  {id:9,status:'done',completed_at:null,priority:'High'}
];
board.renderBoard();
assert.deepEqual(elements.get('col-todo').children.map(c=>c.taskId), [3,1]);
assert.deepEqual(elements.get('col-done').children.map(c=>c.taskId), [8,7]);
assert.equal(elements.get('badge-done').textContent, 3);
assert.equal(elements.get('badge-todo').textContent, 3);
board.changePage('todo', 1);
assert.deepEqual(elements.get('col-todo').children.map(c=>c.taskId), [2]);
assert.deepEqual(elements.get('col-done').children.map(c=>c.taskId), [8,7]);
assert.equal(elements.get('badge-todo').textContent, 3);
assert.equal(elements.get('next-page-todo').disabled, true);
board.currentTasks = board.currentTasks.filter(task=>task.id!==2);
board.renderBoard();
assert.equal(board.columnPages.todo, 1);
board.changePage('done', 1);
assert.deepEqual(elements.get('col-done').children.map(c=>c.taskId), [9]);
board.changePageSize('6');
assert.equal(board.columnPages.done, 1);
board.currentTasks = [];
board.renderBoard();
assert.equal(elements.get('badge-done').textContent, 0);
assert.equal(elements.get('previous-page-done').disabled, true);
assert.equal(elements.get('next-page-done').disabled, true);
assert.equal(elements.get('col-done').children[0].textContent, 'No tasks in this column.');
console.log('PASS: independent column pages, due-date/completion sorting, totals, page clamping, empty states');

(async () => {
  const events = [];
  context.authToken = 'test-token';
  context.fetch = async (url, options) => {
    assert.equal(url, '/api/auth/logout');
    assert.equal(options.headers.Authorization, 'Bearer test-token');
    events.push('request');
    return {ok:true};
  };
  context.localStorage = {removeItem: key => events.push(key)};
  context.window = {location: {replace: () => events.push('redirect')}};
  context.alert = message => events.push(message);
  await vm.runInContext('logout()', context);
  assert.deepEqual(events, ['request', 'taskManagerToken', 'taskManagerUser', 'redirect']);
  events.length = 0;
  context.fetch = async () => ({ok:false});
  await vm.runInContext('logout()', context);
  assert.deepEqual(events, ['Sign out failed. Please try again.']);
  console.log('PASS: dashboard syntax, hostile-name rendering, logout success and failure');
})().catch(error => { console.error(error); process.exitCode = 1; });
