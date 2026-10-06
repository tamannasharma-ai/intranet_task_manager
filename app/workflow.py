"""Demo task workflows; all state lives in the existing temporary database."""
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from app.models import Notification, Task, TaskHistory, TaskMember, TaskDependency, TaskComment, TaskCategory, User


def today_ist():
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


def shared_clause(user_id):
    return or_(Task.shared_with_id == user_id, Task.members.any(TaskMember.user_id == user_id))


def visibility(user, reportee_ids):
    if user.role == 'Admin':
        return True
    return or_(Task.assignee_id.in_([user.id, *reportee_ids]), Task.creator_id == user.id, shared_clause(user.id))


def collaborator(task, user):
    return any(m.user_id == user.id and m.role == 'collaborator' for m in task.members)


def validate_members(db, members, owner_id, creator_id):
    ids = [m.user_id for m in members]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, 'Select each participant only once')
    if owner_id in ids or creator_id in ids:
        raise HTTPException(422, 'The owner and creator already have access; choose other participants')
    if ids and db.query(User).filter(User.id.in_(ids)).count() != len(ids):
        raise HTTPException(422, 'One or more participants no longer exist')


def validate_state(payload, task=None):
    state = payload.status if payload.status is not None else task.status
    if task and state in {'inprogress', 'done'} and state != task.status and task.waiting_count:
        raise HTTPException(409, 'Finish the prerequisite tasks before starting or completing this task')
    supplied = payload.model_fields_set
    reason = payload.blocked_reason if 'blocked_reason' in supplied else getattr(task, 'blocked_reason', None)
    if state == 'blocked' and not (reason or '').strip():
        raise HTTPException(422, 'Explain why the task is blocked')
    if 'recurrence' in supplied and payload.recurrence is None:
        raise HTTPException(422, 'Choose a repeat frequency')
    if 'checklist' in supplied and payload.checklist is None:
        raise HTTPException(422, 'Checklist must be a list')


def notify(db, task, recipients, kind, message, actor_id=None):
    for recipient in set(recipients) - {None, actor_id}:
        db.add(Notification(recipient_id=recipient, task_id=task.id, kind=kind, message=message[:500]))


def participants(task):
    return {task.assignee_id, task.creator_id, task.shared_with_id, *(m.user_id for m in task.members)}


def notify_assignment(db, task, actor_id):
    notify(db, task, participants(task), 'assignment', f'New task: {task.title}', actor_id)


def history(db, task, user, action):
    db.add(TaskHistory(task_id=task.id, author_name=user.name, action=action))


def apply_fields(db, task, payload):
    if 'recurrence' in payload.model_fields_set:
        task.recurrence = payload.recurrence
    if not task.recurrence_day:
        task.recurrence_day = date.fromisoformat(task.due_date).day
    if 'checklist' in payload.model_fields_set:
        task.checklist = [item.model_dump() for item in payload.checklist]
    if task.status == 'blocked':
        if 'blocked_reason' in payload.model_fields_set:
            task.blocked_reason = payload.blocked_reason.strip()
    else:
        task.blocked_reason = None


def repeat_after_completion(db, task, actor):
    if task.recurrence == 'none' or task.status != 'done':
        return
    if db.query(Task.id).filter(Task.recurrence_parent_id == task.id).first():
        return
    due = date.fromisoformat(task.due_date)
    if due.year == 9999 and (task.recurrence == 'monthly' and due.month == 12 or
                            task.recurrence in {'daily', 'weekly'} and due > date(9999, 12, 24)):
        raise HTTPException(422, 'Choose an earlier due date for repeating tasks')
    if task.recurrence == 'monthly':
        month = due.month % 12 + 1
        year = due.year + (due.month == 12)
        due = date(year, month, min(task.recurrence_day or due.day, monthrange(year, month)[1]))
    else:
        due += timedelta(days=1 if task.recurrence == 'daily' else 7)
    following = Task(title=task.title, summary=task.summary, status='todo', priority=task.priority,
                     due_date=due.isoformat(), creator_id=task.creator_id, assignee_id=task.assignee_id,
                     shared_with_id=task.shared_with_id, category_id=task.category_id,
                     recurrence=task.recurrence, recurrence_day=task.recurrence_day,
                     recurrence_parent_id=task.id,
                     checklist=[dict(text=item['text'], done=False) for item in task.checklist],
                     members=[TaskMember(user_id=m.user_id, role=m.role) for m in task.members])
    db.add(following)
    db.flush()
    history(db, following, actor, f'Recurring task created from task #{task.id}')
    history(db, task, actor, f'Next occurrence created as task #{following.id}, due {due.isoformat()}')
    notify_assignment(db, following, None)


def ensure_reminders(db, user):
    today = today_ist()
    tomorrow = today + timedelta(days=1)
    tasks = db.query(Task).filter(Task.assignee_id == user.id, Task.status != 'done',
                                  Task.archived_at.is_(None), Task.deleted_at.is_(None),
                                  Task.due_date <= tomorrow.isoformat()).all()
    current_keys = []
    for task in tasks:
        when = 'overdue' if task.due_date < today.isoformat() else 'due today' if task.due_date == today.isoformat() else 'due tomorrow'
        key = f'due:{user.id}:{task.id}:{today}:{task.due_date}'
        current_keys.append(key)
        if not db.query(Notification.id).filter_by(dedupe_key=key).first():
            db.add(Notification(recipient_id=user.id, task_id=task.id, kind='reminder',
                                message=f'{task.title}: {when}'[:500], dedupe_key=key))
    db.commit()
    return current_keys


def search_tasks(query, text):
    """Literal substring search, scoped by the caller before matching."""
    text = text.strip()
    pattern = '%' + text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    matches = [Task.title.ilike(pattern, escape='\\'), Task.summary.ilike(pattern, escape='\\'),
               Task.comments.any(TaskComment.body.ilike(pattern, escape='\\')),
               Task.creator.has(User.name.ilike(pattern, escape='\\')),
               Task.assignee.has(User.name.ilike(pattern, escape='\\')),
               Task.category.has(TaskCategory.name.ilike(pattern, escape='\\'))]
    identifier = text.lstrip('#')
    if identifier.isascii() and identifier.isdigit() and len(identifier) <= 10:
        matches.append(Task.id == int(identifier))
    return query.filter(or_(*matches))


def check_dependency(db, task, prerequisite):
    if task.id == prerequisite.id:
        raise HTTPException(422, 'A task cannot depend on itself')
    if len(task.dependency_links) >= 20:
        raise HTTPException(422, 'A task can have at most 20 prerequisites')
    if task.status in {'inprogress', 'done'} and prerequisite.status != 'done':
        raise HTTPException(409, 'Move this task to To Do or Blocked before adding an unfinished prerequisite')
    # Follow dependency edges from the prerequisite; reaching this task closes a cycle.
    pending = [prerequisite.id]
    visited = set()
    while pending:
        current = pending.pop()
        if current == task.id:
            raise HTTPException(422, 'This dependency would create a circular chain')
        if current not in visited:
            visited.add(current)
            pending.extend(row[0] for row in db.query(TaskDependency.depends_on_id).filter_by(task_id=current))
