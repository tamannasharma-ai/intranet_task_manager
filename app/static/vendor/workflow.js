/* Daily planning, collaboration and recoverable task workflows. */
const workflowView = document.createElement('section');
workflowView.id = 'workflow-view';
workflowView.className = 'hidden workflow-view';
document.getElementById('kanban-board').before(workflowView);
const workflowStyle = document.createElement('style');
workflowStyle.textContent = `
  .workflow-view {flex:1;min-height:0;overflow:auto;padding:2px 4px 12px;}
  .day-groups {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;}
  .day-group {min-width:0;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:14px;padding:12px;}
  .day-group h3 {font-weight:700;margin-bottom:12px;}
  .day-group .task-card {margin-bottom:10px;}
  .task-card > div:first-child {flex-wrap:wrap;gap:8px;}
  .task-card .task-actions {width:100%;flex-wrap:wrap;justify-content:flex-start;gap:6px;margin-left:0;opacity:1;color:#475569;}
  .task-card .task-actions > * {margin-left:0 !important;}
  .workflow-actions {display:flex;flex-wrap:wrap;gap:6px;padding-top:8px;}
  .workflow-actions button,.workflow-btn {border:1px solid #cbd5e1;border-radius:8px;padding:6px 10px;font-size:12px;background:white;color:#334155;}
  .workflow-actions button:disabled,.workflow-btn:disabled {opacity:.5;cursor:wait;}
  .workflow-dialog {width:min(94vw,720px);max-height:90vh;overflow:auto;padding:24px;border:1px solid #cbd5e1;border-radius:16px;}
  .workflow-dialog::backdrop {background:#0f172a66;}
  .workflow-section {padding:16px 0;border-top:1px solid #e2e8f0;margin-top:14px;}
  .workflow-section label {display:block;font-size:13px;margin:8px 0;}
  .workflow-section input:not([type=checkbox]),.workflow-section select,.workflow-section textarea {border:1px solid #cbd5e1;border-radius:8px;padding:8px;width:100%;}
  .workflow-section h3 {font-weight:700;}
  #details-member-list {max-height:240px;overflow:auto;padding-right:6px;margin-bottom:12px;}
  #details-member-list label {display:flex;align-items:center;justify-content:space-between;gap:12px;}
  #details-member-list select {width:160px;flex-shrink:0;}
  .workflow-error {font-size:13px;color:#9f1239;margin-top:10px;}
  .notification-item {display:block;width:100%;text-align:left;border:1px solid #e2e8f0;border-radius:10px;padding:12px;margin:8px 0;}
  .notification-item.unread {background:#eef2ff;border-color:#a5b4fc;}
  .dashboard-workspace #kanban-board {grid-template-columns:repeat(4,minmax(0,1fr));}
  @media(max-width:1200px) {.day-groups {grid-template-columns:1fr;} .dashboard-workspace #kanban-board {grid-template-columns:repeat(2,minmax(0,1fr));overflow:auto;}}
  @media(max-width:700px) {.dashboard-workspace #kanban-board {grid-template-columns:1fr;} .workflow-view {flex:0 0 auto;overflow:visible;} .workflow-dialog {padding:16px;}}
`;
document.head.append(workflowStyle);
const blockedColumn = document.getElementById('col-todo').parentElement.cloneNode(true);
blockedColumn.innerHTML = blockedColumn.innerHTML.replaceAll('todo', 'blocked').replaceAll('To Do', 'Blocked');
document.getElementById('col-done').parentElement.before(blockedColumn);
for (const [filter, label] of [['my-day', 'My Day'], ['archive', 'Archive'], ['trash', 'Trash']]) {
  const button = document.createElement('button');
  button.id = `tab-${filter}`;
  button.className = 'workflow-btn';
  button.textContent = label;
  button.onclick = () => setFilter(filter);
  const nav = document.querySelector('.workspace-nav');
  if (filter === 'my-day') nav.prepend(button); else nav.append(button);
}

function workflowButton(label, action) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'workflow-btn'; button.textContent = label;
  button.onclick = action;
  return button;
}
function canProgress(task) {
  return task.assignee_id === currentUser.id || task.members.some(m => m.user_id === currentUser.id && m.role === 'collaborator');
}
function canComment(task) {
  const reportee = allUsers.find(u => u.id === task.assignee_id);
  let person = reportee; const visited = new Set();
  while (person && !visited.has(person.id)) {
    if (person.manager_id === currentUser.id) return true;
    visited.add(person.id); person = allUsers.find(u => u.id === person.manager_id);
  }
  return currentUser.role === 'Admin' || task.creator_id === currentUser.id || canProgress(task);
}
function indiaToday() {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts(new Date());
  const part = key => parts.find(p => p.type === key).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}
function renderWorkflowView() {
  if (!['my-day', 'archive', 'trash'].includes(activeFilter)) return false;
  for (const id of ['kanban-board', 'priority-legend', 'pagination-controls']) document.getElementById(id).classList.add('hidden');
  workflowView.classList.remove('hidden'); workflowView.replaceChildren();
  const today = indiaToday();
  const groups = activeFilter === 'my-day' ? [
    ['Overdue', currentTasks.filter(t => t.due_date < today)],
    ['Due Today', currentTasks.filter(t => t.due_date === today)],
    ['Upcoming', currentTasks.filter(t => t.due_date > today)]
  ] : [[activeFilter === 'archive' ? 'Archived tasks' : 'Deleted tasks', currentTasks]];
  const grid = document.createElement('div');
  grid.className = groups.length === 3 ? 'day-groups' : '';
  for (const [label, tasks] of groups) {
    const section = document.createElement('section'); section.className = 'day-group';
    const heading = document.createElement('h3'); heading.textContent = `${label} · ${tasks.length}`;
    section.append(heading);
    tasks.sort(compareTaskOrder).forEach(task => section.append(createCard(task)));
    if (!tasks.length) {const empty = document.createElement('p'); empty.textContent = 'No tasks here.'; empty.className = 'text-sm text-slate-500'; section.append(empty);}
    grid.append(section);
  }
  workflowView.append(grid);
  document.getElementById('kpi-total').textContent = currentTasks.length;
  document.getElementById('kpi-progress').textContent = currentTasks.filter(t => t.status === 'inprogress').length;
  document.getElementById('kpi-done').textContent = currentTasks.filter(t => t.status === 'done').length;
  document.getElementById('kpi-delegated').textContent = currentTasks.filter(t => t.creator_id === currentUser.id && t.assignee_id !== currentUser.id).length;
  return true;
}
function decorateWorkflowCard(card, task) {
  const meta = document.createElement('p'); meta.className = 'text-xs text-slate-600';
  const labels = {todo:'To Do', inprogress:'In Progress', blocked:'Blocked', done:'Done'};
  const parts = [labels[task.status]];
  if (task.recurrence !== 'none') parts.push(`Repeats ${task.recurrence}`);
  if (task.checklist.length) parts.push(`${task.checklist.filter(i => i.done).length}/${task.checklist.length} steps`);
  meta.textContent = parts.join(' · '); card.append(meta);
  if (task.blocked_reason) {const reason = document.createElement('p'); reason.className = 'text-sm text-rose-700'; reason.textContent = `Blocked: ${task.blocked_reason}`; card.append(reason);}
  if (task.deleted_at) card.querySelector('[aria-label="Task comments"]')?.remove();
  const actions = document.createElement('div'); actions.className = 'workflow-actions';
  const owner = task.assignee_id === currentUser.id;
  if (task.archived_at || task.deleted_at) {
    if (owner) actions.append(workflowButton('Restore', event => taskMutation(task.id, 'restore', null, event.currentTarget)));
  } else {
    if (canProgress(task) && task.status !== 'done') {
      if (task.status !== 'inprogress') actions.append(workflowButton('Start', event => taskMutation(task.id, '', {status:'inprogress'}, event.currentTarget)));
      actions.append(workflowButton('Complete', event => taskMutation(task.id, '', {status:'done'}, event.currentTarget)));
    }
    if (owner) {
      actions.append(workflowButton('Reschedule', () => openTaskDetails(task.id)));
      actions.append(workflowButton('Archive', event => taskMutation(task.id, 'archive', null, event.currentTarget)));
    }
  }
  card.append(actions);
}
async function workflowRequest(path, method='GET', payload) {
  const response = await fetch(path, {method, headers:{Authorization:'Bearer '+authToken, 'Content-Type':'application/json'},
    ...(payload === undefined ? {} : {body:JSON.stringify(payload)})});
  await requireSuccess(response); return response.json();
}
async function taskMutation(id, action, payload, button) {
  if (button?.disabled) return;
  if (button) button.disabled = true;
  try {
    await workflowRequest(`/api/tasks/${id}${action ? '/'+action : ''}`, action ? 'POST':'PUT', payload || undefined);
    await fetchTasks(); await refreshNotifications();
  } catch(error) {alert(error.message);} finally {if(button) button.disabled=false;}
}

const extras = document.createElement('div'); extras.className = 'workflow-section';
extras.innerHTML = `
  <label for="task-blocked-reason">Blocked reason (required when blocked)</label>
  <textarea id="task-blocked-reason" maxlength="1000" rows="2" placeholder="What is preventing progress?"></textarea>
  <label for="task-recurrence">Repeat</label>
  <select id="task-recurrence"><option value="none">Does not repeat</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select>
  <p class="text-xs text-slate-500 mt-1">Completing this task creates the next occurrence from its due date.</p>
  <label for="task-checklist">Checklist — one step per line (up to 50)</label>
  <textarea id="task-checklist" rows="3" maxlength="15049" placeholder="Inspect equipment&#10;Record findings&#10;Send report"></textarea>`;
document.getElementById('task-form').querySelector('[type=submit]').parentElement.before(extras);
document.getElementById('task-status').addEventListener('change', () => {
  document.getElementById('task-blocked-reason').required = document.getElementById('task-status').value === 'blocked';
});
function configureTaskExtras(task) {
  document.getElementById('task-recurrence').value = task?.recurrence || 'none';
  document.getElementById('task-blocked-reason').value = task?.blocked_reason || '';
  document.getElementById('task-blocked-reason').required = task?.status === 'blocked';
  document.getElementById('task-checklist').value = (task?.checklist || []).map(i => i.text).join('\n');
}
function collectTaskExtras(id) {
  const previous = currentTasks.find(t => t.id === Number(id))?.checklist || [];
  const remaining = [...previous];
  const checklist = document.getElementById('task-checklist').value.split('\n').map(s => s.trim()).filter(Boolean).map(text => {
    const index = remaining.findIndex(i => i.text === text);
    return {text, done: index < 0 ? false : remaining.splice(index,1)[0].done};
  });
  return {recurrence:document.getElementById('task-recurrence').value, blocked_reason:document.getElementById('task-blocked-reason').value, checklist};
}

const detailsDialog = document.createElement('dialog'); detailsDialog.className = 'workflow-dialog'; detailsDialog.setAttribute('aria-labelledby', 'details-title');
detailsDialog.innerHTML = `
 <div class="flex justify-between gap-3"><h2 id="details-title" class="text-lg font-bold">Task details</h2><button type="button" id="details-close" class="workflow-btn">Close</button></div>
 <p id="details-people" class="text-sm text-slate-600 mt-3"></p><p id="details-access" class="text-xs text-slate-500 mt-2"></p>
 <p id="details-notes" class="text-sm mt-3" style="white-space:pre-wrap;overflow-wrap:anywhere"></p>
 <form id="details-progress" class="workflow-section">
  <h3>Progress and checklist</h3>
  <label for="details-status">Status</label><select id="details-status"><option value="todo">To Do</option><option value="inprogress">In Progress</option><option value="blocked">Blocked</option><option value="done">Done</option></select>
  <label for="details-reason">Blocked reason</label><textarea id="details-reason" rows="2" maxlength="1000"></textarea>
  <div id="details-owner-fields"><label for="details-due">Due date</label><input id="details-due" type="date" required>
  <label for="details-repeat">Repeat</label><select id="details-repeat"><option value="none">Does not repeat</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></div>
  <div id="details-checklist" class="my-3"></div>
  <button type="submit" class="workflow-btn">Save progress</button>
 </form>
 <form id="details-members" class="workflow-section"><h3>Participants</h3>
  <p class="text-xs text-slate-500 my-2">Owner: full task control. Collaborators: progress, checklist and comments. Viewers: read only. The creator manages participants and comments; reporting managers retain oversight.</p>
  <div id="details-member-list"></div><button type="submit" class="workflow-btn">Save participants</button>
 </form>
 <p id="details-error" role="status" class="workflow-error"></p>`;
document.body.append(detailsDialog);
let detailTask = null, detailsBusy = false, detailsVersion = 0;
document.getElementById('details-close').onclick = () => {if(!detailsBusy) detailsDialog.close();};
detailsDialog.addEventListener('cancel', event => {if(detailsBusy) event.preventDefault();});
detailsDialog.addEventListener('close', () => {detailsVersion++;});
document.getElementById('details-status').onchange = () => {document.getElementById('details-reason').required = document.getElementById('details-status').value === 'blocked';};
async function openTaskDetails(id) {
  const version = ++detailsVersion;
  try {
    const task = await workflowRequest(`/api/tasks/${id}`);
    if (version !== detailsVersion) return;
    detailTask = task;
    const active = !task.archived_at && !task.deleted_at;
    const owner = task.assignee_id === currentUser.id;
    const edit = active && canProgress(task);
    const manage = active && (owner || task.creator_id === currentUser.id);
    document.getElementById('details-title').textContent = `#${task.id} · ${task.title}`;
    document.getElementById('details-people').textContent = `Owner: ${task.assignee.name} · Created by: ${task.creator.name}`;
    document.getElementById('details-access').textContent = task.deleted_at ? 'In Trash — restore to continue work.' : task.archived_at ? 'Archived — restore to continue work.' : owner ? 'You own this task.' : canProgress(task) ? 'You are a collaborator.' : 'Read-only task details.';
    document.getElementById('details-notes').textContent = task.summary || 'No description.';
    document.getElementById('details-error').textContent = '';
    document.getElementById('details-status').value = task.status;
    document.getElementById('details-reason').value = task.blocked_reason || '';
    document.getElementById('details-reason').required = task.status === 'blocked';
    document.getElementById('details-due').value = task.due_date;
    document.getElementById('details-repeat').value = task.recurrence;
    const checks = document.getElementById('details-checklist'); checks.replaceChildren();
    task.checklist.forEach((item, index) => {
      const label = document.createElement('label'); const checkbox = document.createElement('input');
      checkbox.type='checkbox'; checkbox.checked=item.done; checkbox.dataset.index=index; checkbox.disabled=!edit;
      label.append(checkbox, document.createTextNode(' '+item.text)); checks.append(label);
    });
    if (!task.checklist.length) checks.textContent = 'No checklist steps. The owner can add steps through Edit task.';
    document.getElementById('details-progress').querySelectorAll('input,select,textarea,button').forEach(el => el.disabled = !edit);
    document.getElementById('details-owner-fields').querySelectorAll('input,select').forEach(el => el.disabled = !owner || !active);
    const memberList = document.getElementById('details-member-list'); memberList.replaceChildren();
    const members = [...task.members];
    if (task.shared_with_id && !members.some(m => m.user_id === task.shared_with_id)) members.push({user_id:task.shared_with_id,role:'viewer'});
    for (const user of allUsers.filter(u => ![task.creator_id,task.assignee_id].includes(u.id))) {
      const role = members.find(m => m.user_id === user.id)?.role || '';
      if (!manage && !role) continue;
      const label = document.createElement('label'); label.textContent = user.name;
      const select = document.createElement('select'); select.dataset.userId=user.id; select.setAttribute('aria-label', `${user.name} access`);
      for (const [value,text] of [['','No direct role'],['collaborator','Collaborator'],['viewer','Viewer']]) select.add(new Option(text,value));
      select.value=role; select.disabled=!manage; label.append(select); memberList.append(label);
    }
    document.getElementById('details-members').querySelector('[type=submit]').disabled = !manage;
    if (!detailsDialog.open) detailsDialog.showModal();
  } catch(error) {alert(error.message);}
}
async function saveDetails(event, membership) {
  event.preventDefault(); if(detailsBusy || !detailTask) return;
  detailsBusy=true; const submit=event.target.querySelector('[type=submit]'); submit.disabled=true;
  document.getElementById('details-close').disabled=true;
  try {
    let payload;
    if (membership) payload={members:[...document.getElementById('details-member-list').querySelectorAll('select')].filter(s=>s.value).map(s=>({user_id:Number(s.dataset.userId),role:s.value}))};
    else {
      payload={status:document.getElementById('details-status').value,blocked_reason:document.getElementById('details-reason').value,
        checklist:detailTask.checklist.map((item,i)=>({...item,done:document.querySelector(`#details-checklist input[data-index="${i}"]`).checked}))};
      if (detailTask.assignee_id===currentUser.id) Object.assign(payload,{due_date:document.getElementById('details-due').value,recurrence:document.getElementById('details-repeat').value});
    }
    await workflowRequest(`/api/tasks/${detailTask.id}${membership ? '/collaboration':''}`, 'PUT', payload);
    await fetchTasks(); await refreshNotifications();
    await openTaskDetails(detailTask.id);
    document.getElementById('details-error').textContent='Saved.';
  } catch(error) {document.getElementById('details-error').textContent=error.message;}
  finally {detailsBusy=false;submit.disabled=false;document.getElementById('details-close').disabled=false;}
}
document.getElementById('details-progress').onsubmit = event => saveDetails(event,false);
document.getElementById('details-members').onsubmit = event => saveDetails(event,true);

const notificationButton = workflowButton('Notifications', () => {notificationDialog.showModal(); refreshNotifications();});
notificationButton.id='notification-bell'; notificationButton.setAttribute('aria-label','Open notifications');
document.getElementById('user-avatar').before(notificationButton);
const notificationDialog = document.createElement('dialog'); notificationDialog.className='workflow-dialog'; notificationDialog.setAttribute('aria-labelledby','notifications-heading');
notificationDialog.innerHTML=`<div class="flex justify-between gap-3"><h2 id="notifications-heading" class="font-bold text-lg">Notifications</h2><button type="button" id="notifications-close" class="workflow-btn">Close</button></div><p class="text-xs text-slate-500 my-3">Latest 100 updates. Due reminders refresh while the app is open.</p><button type="button" id="notifications-read" class="workflow-btn">Mark all as read</button><p id="notifications-error" role="status" class="workflow-error"></p><div id="notifications-list"></div>`;
document.body.append(notificationDialog);
document.getElementById('notifications-close').onclick=()=>notificationDialog.close();
document.getElementById('notifications-read').onclick=async()=>{
  try {await workflowRequest('/api/notifications/read-all','POST');await refreshNotifications();}
  catch(error){document.getElementById('notifications-error').textContent=error.message;}
};
let notificationsLoading=false;
async function refreshNotifications() {
  if(!authToken || notificationsLoading || document.hidden) return;
  notificationsLoading=true;
  try {
    const data=await workflowRequest('/api/notifications');
    notificationButton.textContent=`Notifications${data.unread ? ' ('+data.unread+')':''}`;
    notificationButton.setAttribute('aria-label',`Open notifications, ${data.unread} unread`);
    document.getElementById('notifications-error').textContent='';
    const list=document.getElementById('notifications-list');list.replaceChildren();
    data.items.forEach(item=>{
      const button=workflowButton('',async()=>{
        try {await workflowRequest(`/api/notifications/${item.id}/read`,'POST');notificationDialog.close();await openTaskDetails(item.task_id);await refreshNotifications();}
        catch(error){document.getElementById('notifications-error').textContent=error.message;}
      });
      button.className='notification-item'+(item.read?'':' unread');
      button.textContent=`${item.read?'':'● '}${item.message} · ${formatTime(item.created_at)}`;list.append(button);
    });
    if(!data.items.length) list.textContent='You are all caught up.';
  } catch(error) {notificationButton.textContent='Notifications (!)';document.getElementById('notifications-error').textContent=error.message;}
  finally {notificationsLoading=false;}
}
window.addEventListener('DOMContentLoaded',refreshNotifications);
setInterval(refreshNotifications,60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshNotifications();});
