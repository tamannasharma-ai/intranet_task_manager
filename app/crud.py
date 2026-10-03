from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Task, TaskCategory, TaskHistory, User
from app.schemas import TaskCreate, TaskUpdate

def create_task(db: Session, task_data: TaskCreate, creator: User) -> Task:
    now = datetime.utcnow()
    started_at = now if task_data.status == "inprogress" else None
    completed_at = now if task_data.status == "done" else None
    due_date = task_data.due_date.isoformat()

    db_task = Task(
        title=task_data.title,
        summary=task_data.summary,
        status=task_data.status,
        priority=task_data.priority,
        due_date=due_date,
        creator_id=creator.id,
        assignee_id=task_data.assignee_id,
        shared_with_id=task_data.shared_with_id,
        category_id=task_data.category_id,
        created_at=now,
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(db_task)
    db.flush()

    assignee = db.query(User).filter(User.id == task_data.assignee_id).first()
    action_text = f"Task created by {creator.name}"
    if creator.id != task_data.assignee_id:
        action_text += f" and delegated to {assignee.name if assignee else 'assignee'}"
    if task_data.category_id:
        category = db.query(TaskCategory).filter(TaskCategory.id == task_data.category_id).first()
        if category:
            action_text += f" under '{category.name}'"

    log = TaskHistory(task_id=db_task.id, author_name=creator.name, action=action_text, timestamp=now)
    db.add(log)
    db.commit()
    db.refresh(db_task)
    return db_task

def update_task(db: Session, task: Task, update_data: TaskUpdate, user: User) -> Task:
    now = datetime.utcnow()
    changes = []

    # Detect Lifecycle Transitions
    if update_data.status and update_data.status != task.status:
        changes.append(f"Status changed from '{task.status}' to '{update_data.status}'")
        task.status = update_data.status
        if update_data.status != "done":
            task.completed_at = None
        if update_data.status == "inprogress" and not task.started_at:
            task.started_at = now
            changes.append("Execution clock started")
        elif update_data.status == "done":
            task.completed_at = now
            changes.append("Task clocked as completed")
        elif update_data.status == "todo":
            task.completed_at = None

    if update_data.assignee_id and update_data.assignee_id != task.assignee_id:
        new_user = db.query(User).filter(User.id == update_data.assignee_id).first()
        changes.append(f"Reassigned to {new_user.name if new_user else 'user'}")
        task.assignee_id = update_data.assignee_id

    if update_data.priority and update_data.priority != task.priority:
        changes.append(f"Priority changed to {update_data.priority}")
        task.priority = update_data.priority

    if "category_id" in update_data.model_fields_set and update_data.category_id != task.category_id:
        category = None
        if update_data.category_id is not None:
            category = db.query(TaskCategory).filter(TaskCategory.id == update_data.category_id).first()
        changes.append(f"Category changed to {category.name if category else 'None'}")
        task.category_id = update_data.category_id

    if update_data.due_date:
        due_date = update_data.due_date.isoformat()
        if due_date != task.due_date:
            changes.append(f"Due date changed to {due_date}")
            task.due_date = due_date

    if update_data.title:
        if update_data.title != task.title:
            changes.append("Title changed")
        task.title = update_data.title
    if update_data.summary is not None:
        if update_data.summary != task.summary:
            changes.append("Summary changed")
        task.summary = update_data.summary
    if "shared_with_id" in update_data.model_fields_set:
        if update_data.shared_with_id != task.shared_with_id:
            changes.append("Sharing changed")
        task.shared_with_id = update_data.shared_with_id

    if changes:
        log = TaskHistory(task_id=task.id, author_name=user.name, action="; ".join(changes), timestamp=now)
        db.add(log)

    db.commit()
    db.refresh(task)
    return task
