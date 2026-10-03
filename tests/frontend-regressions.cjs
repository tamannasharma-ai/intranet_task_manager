const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('app/static/index.html', 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
scripts.forEach(script => new vm.Script(script));
const code = scripts.join('\n');
const context = {document: {createElement: () => ({})}, currentUser: {id: 1, manager_id: 2}};
vm.createContext(context);
for (const name of ['escapeHtml', 'createCard', 'localDateToday', 'formatTime', 'logout']) {
  const prefix = name === 'logout' ? '    async function ' : '    function ';
  const start = code.indexOf(prefix + name + '(');
  assert.ok(start >= 0);
  const end = code.indexOf('\n    }', start) + 6;
  vm.runInContext(code.slice(start, end), context);
}
const hostile = '<img src=x onerror=alert(1)>';
context.task = {id: 1, title: hostile, summary: hostile, priority: 'High', creator_id: 2, assignee_id: 1,
  creator: {id:2,name:hostile}, assignee: {name:hostile}, category: {name:hostile}, due_date:'2026-10-03',history:[]};
const card = vm.runInContext('createCard(task)', context);
assert.ok(!card.innerHTML.includes('<img'));
assert.ok(card.innerHTML.includes('&lt;img'));

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
