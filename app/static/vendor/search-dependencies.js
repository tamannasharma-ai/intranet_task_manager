/* Permission-scoped search and prerequisite controls. */
const searchMobileStyle = document.createElement('style');
searchMobileStyle.textContent = `
 .task-search-bar {display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
 .task-search-bar input {flex:1;min-width:180px;}
 .task-search-bar input,.task-search-bar select,.mobile-view-switch select {border:1px solid #cbd5e1;background:white;border-radius:8px;padding:10px;color:#334155;}
 .mobile-view-switch {display:none;}
 .dependency-row {display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #e2e8f0;}
 .dependency-row span {min-width:0;overflow-wrap:anywhere;}
 .dependency-search-row {display:flex;gap:8px;}
 .dependency-search-row input {min-width:0;flex:1;}
 .dependency-search-row button,.dependency-row button {flex-shrink:0;}
 button:focus-visible,select:focus-visible,input:focus-visible {outline:2px solid #4f46e5;outline-offset:3px;}
 @media(max-width:700px) {
  .dashboard-workspace .workspace-shell {display:flex;flex-direction:column;}
  .dashboard-workspace .workspace-main {order:0;min-width:0;padding:16px;}
  .dashboard-workspace .workspace-sidebar {order:1;width:100%;padding:16px;}
  .workspace-sidebar > .sidebar-eyebrow,.workspace-nav,.sidebar-note {display:none !important;}
  .sidebar-account {margin-top:0 !important;display:flex;flex-wrap:wrap;gap:8px;}
  .sidebar-account .sidebar-eyebrow {width:100%;}
  .mobile-view-switch {display:flex;align-items:center;gap:12px;font-weight:600;}
  .mobile-view-switch select {flex:1;min-width:0;}
  .task-search-bar input {flex-basis:100%;width:100%;}
  .task-search-bar select {flex:1;min-width:0;}
  .dashboard-workspace input:not([type=checkbox]),.dashboard-workspace select,.dashboard-workspace textarea {font-size:16px;}
  .dashboard-workspace button,.dashboard-workspace select {min-height:44px;}
  .task-card .task-actions button {min-width:44px;}
  .app-topbar {height:auto !important;min-height:64px;flex-wrap:wrap;gap:8px;padding:10px 16px !important;}
  .app-topbar > div {min-width:0;}
  #user-avatar {display:none;}
  #workspace-kpis {grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}
  #workspace-kpis > div {padding:12px;min-width:0;}
  .workspace-heading {align-items:stretch !important;}
  .create-task-button {width:100%;justify-content:center;}
  .workflow-dialog {max-height:90dvh;width:calc(100vw - 24px);padding:16px;}
  #details-member-list label {flex-wrap:wrap;}
  #details-member-list select {width:100%;}
 }
`;
document.head.append(searchMobileStyle);
const searchForm = document.createElement('form');
searchForm.id = 'task-search-form';
searchForm.className = 'task-search-bar';
searchForm.innerHTML = `<label for="task-search-query" class="sr-only">Search tasks and comments</label>
 <input id="task-search-query" type="search" maxlength="200" placeholder="Search tasks, comments, people or #ID…">
 <label for="task-search-scope" class="sr-only">Search scope</label>
 <select id="task-search-scope"><option value="active">Active tasks</option><option value="archive">Archive</option><option value="trash">Trash</option></select>
 <button type="submit" class="workflow-btn">Search</button><button type="button" id="task-search-clear" class="workflow-btn">Clear</button>`;
document.querySelector('.workspace-heading').after(searchForm);
searchForm.onsubmit = event => {event.preventDefault();setFilter('search');};
document.getElementById('task-search-clear').onclick = () => {searchForm.reset();setFilter('my-day');};
document.getElementById('task-search-query').addEventListener('search', () => {
  if (!document.getElementById('task-search-query').value) setFilter('my-day');
});

const mobileView = document.createElement('label');
mobileView.className = 'mobile-view-switch'; mobileView.textContent = 'View';
const mobileSelect = document.createElement('select'); mobileSelect.id='mobile-view-select'; mobileSelect.setAttribute('aria-label','Choose task view');
mobileView.append(mobileSelect); document.querySelector('.workspace-main').prepend(mobileView);
function syncMobileView(filter = activeFilter) {
  mobileSelect.replaceChildren();
  for (const button of document.querySelectorAll('.workspace-nav button')) {
    if (button.style.display === 'none') continue;
    const value = button.id.replace('tab-', '') === 'team' ? 'team-hierarchy' : button.id.replace('tab-', '');
    mobileSelect.add(new Option(button.textContent.trim(),value));
  }
  mobileSelect.add(new Option('Search results','search')); mobileSelect.value=filter;
}
mobileSelect.onchange=()=>setFilter(mobileSelect.value);
window.addEventListener('DOMContentLoaded', () => {
  syncMobileView();
  new MutationObserver(() => syncMobileView()).observe(document.querySelector('.workspace-nav'), {subtree:true,attributes:true,attributeFilter:['style']});
});

const dependenciesSection = document.createElement('section'); dependenciesSection.className='workflow-section';
dependenciesSection.innerHTML=`<h3>Prerequisite tasks</h3>
 <p class="text-xs text-slate-500 my-2">Finish these tasks before starting or completing this one. Linking a task does not grant access to it.</p>
 <div id="dependency-list"></div><p id="dependency-message" role="status" class="text-sm my-2"></p>
 <form id="dependency-find"><label for="dependency-query">Find a prerequisite by title or #ID</label>
 <div class="dependency-search-row"><input id="dependency-query" type="search" maxlength="200" required><button type="submit" class="workflow-btn">Find tasks</button></div></form>
 <form id="dependency-add" hidden><label for="dependency-candidate">Choose prerequisite</label><select id="dependency-candidate" required></select>
 <button type="submit" class="workflow-btn mt-2">Add prerequisite</button></form>`;
document.getElementById('details-members').before(dependenciesSection);
let dependencyBusy = false;
async function loadTaskDependencies(task, manage, version) {
  const list=document.getElementById('dependency-list'); list.replaceChildren();
  document.getElementById('dependency-find').hidden=!manage;
  document.getElementById('dependency-add').hidden=true;
  document.getElementById('dependency-query').value='';
  const message=document.getElementById('dependency-message');message.textContent='Loading prerequisites…';
  try {
    const links=await workflowRequest(`/api/tasks/${task.id}/dependencies`);
    if(version!==detailsVersion) return;
    message.textContent=links.length ? '' : 'No prerequisites. This task can progress independently.';
    const labels={todo:'To Do',inprogress:'In Progress',blocked:'Blocked',done:'Done'};
    links.forEach(link=>{
      const row=document.createElement('div');row.className='dependency-row';
      const text=document.createElement('span');
      text.textContent=`${link.satisfied?'✓':'Waiting'} · ${link.task_id ? '#'+link.task_id+' · ':''}${link.title}${link.status?' · '+labels[link.status]:''}${link.archived?' (archived)':''}`;
      row.append(text);
      if(manage) row.append(workflowButton('Remove', event=>changeDependency('DELETE',task.id,link.link_id,undefined,event.currentTarget)));
      list.append(row);
    });
  } catch(error) {if(version===detailsVersion) message.textContent=error.message;}
}
document.getElementById('dependency-find').onsubmit=async event=>{
  event.preventDefault(); if(dependencyBusy || detailsBusy) return;
  const version=detailsVersion, taskId=detailTask.id;
  const query=document.getElementById('dependency-query').value.trim();if(!query)return;
  const button=event.target.querySelector('button');button.disabled=true;
  const message=document.getElementById('dependency-message');message.textContent='Searching…';
  document.getElementById('dependency-add').hidden=true;
  try {
    const tasks=await workflowRequest(`/api/search/tasks?q=${encodeURIComponent(query)}&scope=active`);
    if(version!==detailsVersion)return;
    const select=document.getElementById('dependency-candidate');select.replaceChildren();
    tasks.filter(t=>t.id!==taskId).forEach(task=>select.add(new Option(`#${task.id} · ${task.title} · ${task.status}`,task.id)));
    document.getElementById('dependency-add').hidden=!select.options.length;
    message.textContent=select.options.length ? 'Choose a task below.' : 'No matching tasks you can access. Try another title or #ID.';
  } catch(error){if(version===detailsVersion)message.textContent=error.message;}
  finally{button.disabled=false;}
};
document.getElementById('dependency-add').onsubmit=event=>{
  event.preventDefault();const id=Number(document.getElementById('dependency-candidate').value);
  if(id)changeDependency('POST',detailTask.id,null,{depends_on_id:id},event.target.querySelector('button'));
};
async function changeDependency(method,taskId,linkId,payload,button) {
  if(dependencyBusy || detailsBusy)return;
  dependencyBusy=detailsBusy=true;button.disabled=true;document.getElementById('details-close').disabled=true;
  try {
    await workflowRequest(`/api/tasks/${taskId}/dependencies${linkId ? '/'+linkId:''}`,method,payload);
    await fetchTasks();await openTaskDetails(taskId);
    document.getElementById('dependency-message').textContent=method==='POST'?'Prerequisite added.':'Prerequisite removed.';
  } catch(error){document.getElementById('dependency-message').textContent=error.message;}
  finally{dependencyBusy=detailsBusy=false;button.disabled=false;document.getElementById('details-close').disabled=false;}
}
