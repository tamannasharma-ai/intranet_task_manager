"""Fictional accounts with stable IDs across demo instances."""
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
    if not db.query(User).first():
        password_hash = get_password_hash(DEMO_PASSWORD)
        for user_id, name, email, role, manager_id in EMPLOYEES:
            db.add(User(id=user_id, name=name, email=email, role=role,
                        manager_id=manager_id, hashed_password=password_hash))
        db.flush()
    existing = {name for (name,) in db.query(TaskCategory.name).all()}
    for name in ("Send email", "Take approval", "Prepare report", "Review document"):
        if name not in existing:
            db.add(TaskCategory(name=name))
    db.commit()
