/* Voice input only fills drafts. The user must explicitly save or post. */
let activeDictation = null;
function dictationActive() { return activeDictation !== null; }

function stopDictation() {
  if (!activeDictation) return;
  const session = activeDictation;
  activeDictation = null;
  session.recognition.abort();
  session.restore();
  session.status.textContent = 'Stopped. Review your text before saving.';
}

function addVoiceControl(fieldId) {
  const field = document.getElementById(fieldId);
  const row = document.createElement('div');
  row.className = 'flex flex-wrap items-center gap-2 mt-2 text-xs';
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = '🎙 Dictate';
  button.className = 'rounded-lg border border-indigo-200 px-3 py-2 text-indigo-700';
  button.setAttribute('aria-label', `Dictate ${fieldId === 'task-title' ? 'task title' : fieldId === 'task-summary' ? 'task description' : 'comment'}`);
  button.setAttribute('aria-pressed', 'false');
  const language = document.createElement('select');
  language.setAttribute('aria-label', 'Dictation language');
  language.className = 'rounded-lg border p-2';
  for (const [value, label] of [['en-IN', 'English (India)'], ['hi-IN', 'Hindi']]) {
    language.add(new Option(label, value));
  }
  const status = document.createElement('p');
  status.className = 'text-xs text-slate-600 mt-1';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const hint = document.createElement('p');
  hint.className = 'text-xs text-slate-500 mt-1';
  hint.textContent = 'Voice may send audio to your browser’s speech service. Review text before saving. You can also type or use Windows + H.';
  row.append(button, language);
  field.after(row, status, hint);
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition || !window.isSecureContext) {
    button.disabled = true;
    language.disabled = true;
    status.textContent = !window.isSecureContext
      ? 'Voice needs HTTPS or localhost. You can still type.'
      : 'Browser dictation is unavailable. You can still type or use Windows + H.';
    return;
  }
  button.addEventListener('click', () => {
    if (activeDictation?.field === field) {
      button.disabled = true;
      status.textContent = 'Finishing dictation…';
      activeDictation.recognition.stop();
      return;
    }
    if (field.readOnly || field.disabled) return;
    stopDictation();
    const recognition = new Recognition();
    recognition.lang = language.value;
    recognition.continuous = true;
    recognition.interimResults = false;
    const submit = field.form?.querySelector('[type="submit"]');
    const session = {recognition, field, status, seen: new Set(),
      restore() {
        field.readOnly = false;
        language.disabled = false;
        button.disabled = false;
        button.textContent = '🎙 Dictate';
        button.setAttribute('aria-pressed', 'false');
        if (submit) submit.disabled = false;
      }};
    activeDictation = session;
    field.readOnly = true;
    language.disabled = true;
    if (submit) submit.disabled = true;
    button.textContent = '■ Stop dictation';
    button.setAttribute('aria-pressed', 'true');
    status.textContent = 'Allow microphone access when prompted. Listening…';
    recognition.onresult = event => {
      if (activeDictation !== session) return;
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (!event.results[i].isFinal || session.seen.has(i)) continue;
        session.seen.add(i);
        const transcript = event.results[i][0].transcript.trim();
        const next = field.value + (field.value && !/\s$/.test(field.value) ? ' ' : '') + transcript;
        if (field.maxLength > 0 && next.length > field.maxLength) {
          stopDictation();
          status.textContent = 'This phrase exceeds the field limit. Shorten your text, then try again.';
          return;
        }
        field.value = next;
        field.dispatchEvent(new Event('input', {bubbles: true}));
      }
    };
    recognition.onerror = event => {
      if (activeDictation !== session) return;
      const messages = {
        'not-allowed': 'Microphone permission denied. Allow it in browser settings or type instead.',
        'service-not-allowed': 'Speech service is unavailable. Type or use Windows + H.',
        'audio-capture': 'No microphone is available. Check your microphone or type instead.',
        'network': 'Speech service connection failed. Check your connection or type instead.',
        'no-speech': 'No speech detected. Try again or type instead.',
        'language-not-supported': 'This speech service does not support the selected language.'
      };
      stopDictation();
      status.textContent = messages[event.error] || 'Dictation stopped. Your existing text is preserved.';
    };
    recognition.onend = () => {
      if (activeDictation !== session) return;
      activeDictation = null;
      session.restore();
      status.textContent = 'Dictation finished. Review and edit the text before saving.';
      field.focus();
    };
    try { recognition.start(); }
    catch (_) {
      stopDictation();
      status.textContent = 'Unable to start dictation. Type or use Windows + H.';
    }
  });
}

const commentsDialog = document.createElement('dialog');
commentsDialog.id = 'comments-dialog';
commentsDialog.setAttribute('aria-labelledby', 'comments-heading');
commentsDialog.style.cssText = 'width:min(95vw,640px);max-height:90vh;border:1px solid #cbd5e1;border-radius:16px;padding:24px;';
commentsDialog.innerHTML = `
  <div class="flex items-center justify-between gap-3 mb-3">
    <h2 id="comments-heading" class="font-bold text-lg">Task comments</h2>
    <button type="button" id="comments-close" class="rounded-lg border px-3 py-2 text-sm">Close</button>
  </div>
  <p id="comments-task-title" class="text-sm font-semibold text-slate-700 mb-3"></p>
  <p class="text-xs text-slate-500 mb-3">Newest comments first. Visible to people who can access this task.</p>
  <div id="comments-list" class="space-y-3 mb-3" style="max-height:32vh;overflow:auto"></div>
  <button type="button" id="comments-more" class="rounded-lg border px-3 py-2 text-xs mb-3" hidden>Load older comments</button>
  <p id="comments-status" role="status" aria-live="polite" class="text-sm text-slate-600 mb-3"></p>
  <form id="comment-form" class="space-y-3">
    <label for="comment-body" class="block text-sm font-semibold">Add a comment</label>
    <textarea id="comment-body" required maxlength="5000" rows="3" class="w-full rounded-lg border border-slate-300 p-3 text-sm" placeholder="Write an update or dictate a comment…"></textarea>
    <button type="submit" id="comment-submit" class="rounded-lg bg-indigo-600 text-white px-4 py-2 text-sm">Post comment</button>
  </form>`;
document.body.append(commentsDialog);
const commentBody = document.getElementById('comment-body');
const commentsStatus = document.getElementById('comments-status');
const commentsMore = document.getElementById('comments-more');
let commentTaskId = null;
let commentCursor = null;
let commentVersion = 0;
let commentPosting = false;
const commentDrafts = new Map();
const commentRequests = new Map();

function closeComments() {
  if (commentPosting) return;
  stopDictation();
  commentsDialog.close();
}
document.getElementById('comments-close').onclick = closeComments;
commentsDialog.addEventListener('cancel', event => { event.preventDefault(); closeComments(); });
commentsDialog.addEventListener('close', () => {
  stopDictation();
  commentVersion++;
  commentTaskId = null;
});
commentBody.addEventListener('input', () => {
  if (commentTaskId !== null) commentDrafts.set(commentTaskId, commentBody.value);
});

async function openComments(taskId) {
  stopDictation();
  const task = currentTasks.find(task => task.id === taskId);
  if (!task) return;
  commentTaskId = taskId;
  commentVersion++;
  commentCursor = null;
  document.getElementById('comments-task-title').textContent = task.title;
  document.getElementById('comments-list').replaceChildren();
  commentBody.value = commentDrafts.get(taskId) || '';
  const writable = !task.archived_at && !task.deleted_at && canComment(task);
  document.getElementById('comment-form').hidden = !writable;
  const voiceStatus = commentBody.nextElementSibling?.nextElementSibling;
  if (voiceStatus && (window.SpeechRecognition || window.webkitSpeechRecognition) && window.isSecureContext) {
    voiceStatus.textContent = '';
  }
  commentsMore.hidden = true;
  commentsDialog.showModal();
  await loadComments();
}

async function loadComments() {
  const version = commentVersion;
  const taskId = commentTaskId;
  commentsMore.disabled = true;
  commentsStatus.textContent = 'Loading comments…';
  try {
    const suffix = commentCursor === null ? '' : `?before_id=${commentCursor}`;
    const response = await fetch(`/api/tasks/${taskId}/comments${suffix}`, {
      headers: {Authorization: 'Bearer ' + authToken}
    });
    await requireSuccess(response);
    const comments = await response.json();
    if (version !== commentVersion) return;
    const list = document.getElementById('comments-list');
    for (const comment of comments) {
      const article = document.createElement('article');
      article.className = 'rounded-lg border border-slate-200 bg-slate-50 p-3';
      const author = document.createElement('p');
      author.className = 'text-xs font-semibold text-slate-600 mb-1';
      author.textContent = `${comment.author_name} · ${formatTime(comment.created_at)}`;
      const body = document.createElement('p');
      body.className = 'text-sm text-slate-800';
      body.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere';
      body.textContent = comment.body;
      article.append(author, body);
      list.append(article);
    }
    if (comments.length) commentCursor = comments[comments.length - 1].id;
    commentsMore.hidden = comments.length < 50;
    commentsMore.textContent = 'Load older comments';
    commentsStatus.textContent = list.childElementCount ? '' : 'No comments yet. Add the first update below.';
  } catch (error) {
    if (version !== commentVersion) return;
    commentsStatus.textContent = error.message || 'Unable to load comments.';
    commentsMore.hidden = false;
    commentsMore.textContent = 'Retry loading comments';
  } finally {
    if (version === commentVersion) commentsMore.disabled = false;
  }
}
commentsMore.onclick = loadComments;

document.getElementById('comment-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (commentPosting || dictationActive()) return;
  const body = commentBody.value.trim();
  if (!body) { commentsStatus.textContent = 'Enter a comment before posting.'; return; }
  const taskId = commentTaskId;
  const previous = commentRequests.get(taskId);
  // Reuse the ID after a lost response so retrying cannot post the same draft twice.
  const submission = previous?.body === body ? previous : {
    body, request_id: typeof crypto.randomUUID === 'function' ? crypto.randomUUID() :
      '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c =>
        (Number(c) ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> Number(c) / 4).toString(16))
  };
  commentRequests.set(taskId, submission);
  commentPosting = true;
  const submit = document.getElementById('comment-submit');
  submit.disabled = true;
  commentBody.readOnly = true;
  document.getElementById('comments-close').disabled = true;
  commentsStatus.textContent = 'Posting comment…';
  try {
    const response = await fetch(`/api/tasks/${taskId}/comments`, {
      method: 'POST', headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + authToken},
      body: JSON.stringify(submission)
    });
    await requireSuccess(response);
    commentBody.value = '';
    commentDrafts.delete(taskId);
    commentRequests.delete(taskId);
    refreshNotifications();
    commentVersion++;
    commentCursor = null;
    document.getElementById('comments-list').replaceChildren();
    await loadComments();
  } catch (error) {
    commentsStatus.textContent = (error.message || 'Unable to post comment.') + ' Your draft has been kept; you can retry.';
  } finally {
    commentPosting = false;
    submit.disabled = false;
    commentBody.readOnly = false;
    document.getElementById('comments-close').disabled = false;
  }
});

for (const id of ['task-title', 'task-summary', 'comment-body']) addVoiceControl(id);
document.addEventListener('visibilitychange', () => { if (document.hidden) stopDictation(); });
window.addEventListener('pagehide', stopDictation);
