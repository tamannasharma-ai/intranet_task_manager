"""Fictional accounts and task scenarios with stable IDs across demo instances."""
from datetime import datetime, timedelta, timezone

DEMO_PASSWORD = "DemoPass123!"
# id, name, email, role, manager_id
EMPLOYEES = (
    (1, "Avery Morgan", "avery@example.com", "Admin", None),
    (2, "Jordan Ellis", "jordan@example.com", "Reporting Officer", 1),
    (3, "Riley Bennett", "riley@example.com", "Reporting Officer", 1),
    (4, "Casey Parker", "casey@example.com", "Reporting Officer", 1),
    (5, "Taylor Reed", "taylor@example.com", "Junior Engineer", 2),
    (6, "Morgan Hayes", "morgan@example.com", "Junior Engineer", 2),
    (7, "Quinn Foster", "quinn@example.com", "Project Analyst", 2),
    (8, "Jamie Brooks", "jamie@example.com", "Junior Staff", 2),
    (9, "Alex Rowan", "alex@example.com", "Operations Officer", 3),
    (10, "Cameron Blake", "cameron@example.com", "Junior Ops Officer", 3),
    (11, "Drew Collins", "drew@example.com", "Project Analyst", 3),
    (12, "Skyler Lane", "skyler@example.com", "Junior Staff", 3),
    (13, "Reese Harper", "reese@example.com", "Finance Officer", 4),
    (14, "Peyton Wells", "peyton@example.com", "HR Coordinator", 4),
    (15, "Emerson Gray", "emerson@example.com", "Junior Staff", 4),
)

def seed_demo(db):
    from app.auth import get_password_hash
    from app.models import TaskCategory, User
    fresh = not db.query(User).first()
    if fresh:
        password_hash = get_password_hash(DEMO_PASSWORD)
        for user_id, name, email, role, manager_id in EMPLOYEES:
            db.add(User(id=user_id, name=name, email=email, role=role,
                        manager_id=manager_id, hashed_password=password_hash))
        db.flush()
    existing = {name for (name,) in db.query(TaskCategory.name).all()}
    for name in ("Send email", "Take approval", "Prepare report", "Review document"):
        if name not in existing:
            db.add(TaskCategory(name=name))
    db.flush()
    if fresh:
        seed_tasks(db)
    db.commit()


def seed_tasks(db):
    """Populate each employee's views; called only for a fresh demo roster."""
    import json
    from app.models import ActivityLog, Task, TaskCategory, TaskHistory

    # Store UTC timestamps like the existing ORM; due dates follow the demo's
    # India timezone so today's examples stay current on every deployment.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today = (now + timedelta(hours=5, minutes=30)).date()
    categories = {c.name: c.id for c in db.query(TaskCategory).all()}
    names = {row[0]: row[1] for row in EMPLOYEES}
    emails = {row[0]: row[2] for row in EMPLOYEES}
    subjects = (
        "quarterly delivery plan", "engineering review pack", "operations handover",
        "resource allocation plan", "pump inspection checklist", "sensor calibration report",
        "project milestone tracker", "drawing register", "shift readiness checklist",
        "maintenance schedule", "service performance report", "spare parts register",
        "sample budget reconciliation", "new starter checklist", "training attendance report",
    )

    def add(title, summary, creator, assignee, status, priority, days, category, shared=None):
        created = now - timedelta(days=7)
        started = created + timedelta(days=1) if status != "todo" else None
        completed = now - timedelta(days=1) if status == "done" else None
        task = Task(title=title, summary=summary, creator_id=creator,
                    assignee_id=assignee, shared_with_id=shared, status=status,
                    priority=priority, due_date=(today + timedelta(days=days)).isoformat(),
                    category_id=categories[category], created_at=created,
                    started_at=started, completed_at=completed)
        db.add(task)
        db.flush()

        def event(actor, timestamp, event_type, action):
            db.add(TaskHistory(task_id=task.id, author_name=names[actor],
                               action=action, timestamp=timestamp))
            db.add(ActivityLog(event_type=event_type, actor_user_id=actor,
                               actor_email=emails[actor], target_type="task",
                               target_id=str(task.id), action=action, created_at=timestamp,
                               metadata_json=json.dumps({"demo": True, "assignee_id": assignee}),
                               success=1))

        action = f"Fictional demo task created by {names[creator]}"
        if creator != assignee:
            action += f" and delegated to {names[assignee]}"
        if shared:
            action += f"; shared with {names[shared]}"
        event(creator, created, "TASK_CREATED", action)
        if started:
            event(assignee, started, "TASK_UPDATED", "Status changed from 'todo' to 'inprogress'; execution clock started")
        if completed:
            event(assignee, completed, "TASK_UPDATED", "Status changed from 'inprogress' to 'done'; review completed")

    for user_id, name, email, role, manager_id in EMPLOYEES:
        subject = subjects[user_id - 1]
        add(f"Review {subject}",
            "Fictional personal work due today. Check the draft, record findings, and start execution.",
            user_id, user_id, "todo", "High", 0, "Review document")
        add(f"Prepare {subject}",
            "Fictional overdue work in progress. Draft is ready; verify figures and resolve two open comments.",
            user_id, user_id, "inprogress", "Medium", -2, "Prepare report")
        add(f"Send update on {subject}",
            "Fictional completed work. The team update was reviewed and sent; inspect the lifecycle history.",
            user_id, user_id, "done", "Low", -1, "Send email")
        if manager_id:
            status = ("todo", "inprogress", "done")[(user_id - 2) % 3]
            add(f"Obtain approval for {subject}",
                f"Fictional assignment from {names[manager_id]}. Review the proposal and document the approval decision.",
                manager_id, user_id, status, "High", 3, "Take approval")
            # The app's Shared view includes tasks assigned AND shared to the
            # current employee, so these examples respect that visibility rule.
            add(f"Coordinate feedback on {subject}",
                f"Fictional shared assignment from {names[manager_id]}. Consolidate feedback before tomorrow's review.",
                manager_id, user_id, "todo", "Medium", 1, "Review document", shared=user_id)
