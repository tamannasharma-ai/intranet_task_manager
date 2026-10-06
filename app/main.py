import csv
import io
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from fastapi import FastAPI, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text, or_
from typing import List

from app.database import Base, engine, get_db, SessionLocal
from app.models import User, Task, TaskCategory, ActivityLog, TaskComment, TaskMember, Notification, TaskDependency
from app.schemas import CommentCreate, CommentOut, CollaborationUpdate, DependencyCreate
from app import workflow
from app.schemas import ActivityLogOut, CategoryCreate, CategoryOut, UserOut, TaskOut, TaskCreate, TaskUpdate, Token, PasswordChangeRequest, ManagerUpdate
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user, get_user_from_token
import app.crud as crud
from app.logging_config import logger
from app.ai_console import AIQuestion

VALID_TASK_FILTERS = {"all", "personal", "assigned-by-ro", "shared", "team-hierarchy", "delegated-by-me", "my-day", "archive", "trash"}
ALLOWED_EMAIL_DOMAIN = "thdc.co.in"
APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production" or os.getenv("VERCEL") == "1"
SECURE_COOKIES = IS_PRODUCTION or os.getenv("SECURE_COOKIES", "").lower() == "true"
if IS_PRODUCTION and not os.getenv("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY is required when APP_ENV=production")

# Create database tables automatically
Base.metadata.create_all(bind=engine)

def migrate_sqlite_schema() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    if "tasks" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "category_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN category_id INTEGER"))

migrate_sqlite_schema()

app = FastAPI(title="TaskOrbit")
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/vendor", StaticFiles(directory=str(STATIC_DIR / "vendor")), name="vendor")

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"application": "continuum", "status": "ok"}

login_attempts: dict[str, list[float]] = {}
login_attempts_lock = threading.Lock()
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5

@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request exception", extra={"request_id": request_id, "method": request.method, "path": request.url.path})
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "HTTP request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else None,
        },
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def record_activity(
    db: Session,
    event_type: str,
    action: str,
    request: Request | None = None,
    actor: User | None = None,
    target_type: str | None = None,
    target_id: int | str | None = None,
    metadata: dict | None = None,
    success: bool = True,
) -> None:
    event_metadata = dict(metadata or {})
    if request:
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            event_metadata["request_id"] = request_id
    db.add(
        ActivityLog(
            event_type=event_type,
            actor_user_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            action=action,
            metadata_json=json.dumps(event_metadata, separators=(",", ":")) if event_metadata else None,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent")[:500] if request and request.headers.get("user-agent") else None,
            success=1 if success else 0,
        )
    )
    logger.info("Activity event", extra={"event": event_type})

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize per process, including runtimes without ASGI lifespan events.
from app.demo_data import seed_demo
with SessionLocal() as demo_db:
    seed_demo(demo_db)

def get_direct_reportee_ids(db: Session, user: User) -> list[int]:
    return [id_ for (id_,) in db.query(User.id).filter(User.manager_id == user.id).all()]

def get_all_reportee_ids(db: Session, user: User) -> list[int]:
    """Return every descendant in the user's reporting hierarchy."""
    reportee_ids: list[int] = []
    pending_ids = get_direct_reportee_ids(db, user)
    visited_ids = {user.id}

    while pending_ids:
        reportee_id = pending_ids.pop(0)
        if reportee_id in visited_ids:
            continue

        visited_ids.add(reportee_id)
        reportee_ids.append(reportee_id)
        child_ids = [
            id_
            for (id_,) in db.query(User.id).filter(User.manager_id == reportee_id).all()
        ]
        pending_ids.extend(child_ids)

    return reportee_ids

def get_visible_task_assignee_ids(db: Session, user: User) -> list[int]:
    """Return the assignees whose tasks this user is allowed to list."""
    if user.role == "Admin":
        return [id_ for (id_,) in db.query(User.id).all()]

    reportee_ids = get_all_reportee_ids(db, user)
    return [user.id, *reportee_ids] if reportee_ids else [user.id]

def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user

def get_category_or_404(db: Session, category_id: int) -> TaskCategory:
    category = db.query(TaskCategory).filter(TaskCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
    return category

def can_assign_task(db: Session, current_user: User, assignee_id: int) -> bool:
    return assignee_id == current_user.id or assignee_id in get_direct_reportee_ids(db, current_user)

def can_access_task(db: Session, task: Task, current_user: User) -> bool:
    return bool(db.query(Task.id).filter(Task.id == task.id,
        workflow.visibility(current_user, get_all_reportee_ids(db, current_user))).first())

def can_update_task(db: Session, task: Task, current_user: User) -> bool:
    return task.assignee_id == current_user.id or workflow.collaborator(task, current_user)

def can_delete_task(db: Session, task: Task, current_user: User) -> bool:
    return task.assignee_id == current_user.id

def validate_task_users(db: Session, task_in: TaskCreate | TaskUpdate, current_user: User) -> None:
    if task_in.assignee_id is not None:
        get_user_or_404(db, task_in.assignee_id)
        if not can_assign_task(db, current_user, task_in.assignee_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only assign tasks to yourself or your direct reportees",
            )

    if task_in.shared_with_id is not None:
        get_user_or_404(db, task_in.shared_with_id)

    if task_in.category_id is not None:
        get_category_or_404(db, task_in.category_id)

def require_admin(current_user: User) -> User:
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can manage employees",
        )
    return current_user

# --- Auth Endpoints ---
@app.post("/api/auth/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    response: Response = None,
):
    email = form_data.username.strip().lower()
    attempt_key = f"{request.client.host if request.client else 'unknown'}:{email}"
    now = time.monotonic()
    with login_attempts_lock:
        recent_attempts = [
            timestamp
            for timestamp in login_attempts.get(attempt_key, [])
            if now - timestamp < LOGIN_WINDOW_SECONDS
        ]
        if len(recent_attempts) >= LOGIN_MAX_ATTEMPTS:
            record_activity(db, "LOGIN_THROTTLED", "Login throttled", request=request, metadata={"email": email}, success=False)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
                headers={"Retry-After": str(LOGIN_WINDOW_SECONDS)},
            )
        recent_attempts.append(now)
        login_attempts[attempt_key] = recent_attempts

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        record_activity(db, "LOGIN_FAILURE", "Invalid credentials", request=request, metadata={"email": email}, success=False)
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    with login_attempts_lock:
        login_attempts.pop(attempt_key, None)
    access_token = create_access_token(data={"sub": str(user.id)})
    record_activity(db, "LOGIN_SUCCESS", "User signed in", request=request, actor=user)
    db.commit()
    if response is not None:
        response.set_cookie(
            key="task_manager_token",
            value=access_token,
            httponly=True,
            samesite="lax",
            secure=SECURE_COOKIES,
            max_age=60 * 60 * 24,
        )
    return {"access_token": access_token, "token_type": "bearer", "user": user}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    # Always clear the cookie, including when the session has already expired.
    authorization = request.headers.get("authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else request.cookies.get("task_manager_token")
    if token:
        try:
            current_user = get_user_from_token(token, db)
        except HTTPException:
            current_user = None
        if current_user:
            record_activity(db, "LOGOUT", "User signed out", request=request, actor=current_user)
            db.commit()
    response.delete_cookie(
        key="task_manager_token",
        httponly=True,
        samesite="lax",
        secure=SECURE_COOKIES,
    )
    return {"message": "Logged out successfully"}

@app.post("/api/users/me/change-password")
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    record_activity(db, "PASSWORD_CHANGED", "User changed password", request=request, actor=current_user)
    db.commit()
    return {"message": "Password changed successfully"}

@app.get("/api/auth/users", response_model=List[UserOut])
def get_login_users(db: Session = Depends(get_db)):
    """Return safe account details used to select an account on the login page."""
    return db.query(User).order_by(User.name.asc()).all()

@app.get("/api/users", response_model=List[UserOut])
def get_all_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(User).all()

@app.post("/api/users/import")
async def import_users(
    request: Request,
    file: UploadFile = File(...),
    default_password: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.employee_import import parse_employees
    from sqlalchemy.exc import IntegrityError

    require_admin(current_user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV must be no larger than 2 MB")
    existing = {user.email.lower(): user for user in db.query(User).all()}
    rows, skipped = parse_employees(content, default_password, existing)
    imported = {}
    try:
        for row in rows:
            user = User(name=row["name"], email=row["email"], role=row["role"],
                        hashed_password=get_password_hash(row["password"]))
            db.add(user)
            imported[row["email"]] = user
        db.flush()
        all_users = {**existing, **imported}
        for row in rows:
            if row["manager_email"]:
                imported[row["email"]].manager_id = all_users[row["manager_email"]].id
        record_activity(db, "EMPLOYEES_IMPORTED", f"Imported {len(imported)} employee(s)",
                        request=request, actor=current_user, target_type="user_import",
                        metadata={"imported": len(imported), "skipped": len(skipped)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Accounts changed during import. No accounts imported; please retry.")
    return {"imported": len(imported), "skipped_existing": skipped, "errors": [],
            "uploaded_by": current_user.email}


@app.put("/api/users/{user_id}/manager", response_model=UserOut)
def update_reporting_manager(user_id: int, payload: ManagerUpdate, request: Request,
                             db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_admin(current_user)
    # Serialize hierarchy edits on PostgreSQL so concurrent changes cannot form a cycle.
    employees = {user.id: user for user in db.query(User).order_by(User.id).with_for_update().populate_existing().all()}
    employee = employees.get(user_id)
    if employee is None:
        raise HTTPException(404, "Employee not found")
    if payload.manager_id is not None and payload.manager_id not in employees:
        raise HTTPException(404, "Reporting manager not found")
    ancestor_id = payload.manager_id
    visited = {employee.id}
    while ancestor_id is not None:
        if ancestor_id in visited:
            raise HTTPException(400, "An employee cannot report to themselves or create a circular reporting relationship")
        visited.add(ancestor_id)
        ancestor = employees.get(ancestor_id)
        if ancestor is None:
            raise HTTPException(400, "The selected manager has an invalid reporting hierarchy")
        ancestor_id = ancestor.manager_id
    previous_manager = employee.manager_id
    if previous_manager != payload.manager_id:
        employee.manager_id = payload.manager_id
        record_activity(db, "REPORTING_MANAGER_UPDATED", "Updated employee reporting manager",
                        request=request, actor=current_user, target_type="user", target_id=employee.id,
                        metadata={"previous_manager_id": previous_manager, "manager_id": payload.manager_id})
    db.commit()
    db.refresh(employee)
    return employee

@app.get("/api/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(TaskCategory).order_by(TaskCategory.name.asc()).all()

@app.post("/api/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(category_in: CategoryCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    name = " ".join(category_in.name.split())
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")

    existing = db.query(TaskCategory).filter(TaskCategory.name.ilike(name)).first()
    if existing:
        return existing

    category = TaskCategory(name=name, creator_id=current_user.id)
    db.add(category)
    db.commit()
    db.refresh(category)
    record_activity(db, "CATEGORY_CREATED", f"Created category '{category.name}'", request=request, actor=current_user, target_type="category", target_id=category.id)
    db.commit()
    return category

# --- Task Endpoints ---
@app.get("/api/ai/config")
def ai_configuration(current_user: User = Depends(get_current_user)):
    from app.ai_console import configuration
    return configuration()


@app.post("/api/ai/chat")
def ai_chat(payload: AIQuestion, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.ai_console import answer_question
    return answer_question(db, current_user, get_all_reportee_ids(db, current_user), payload)


@app.get("/api/reports/tasks")
def get_task_summary(assignee_id: int | None = None, status: str = "all", priority: str = "all",
                     task_text: str = "", creator_text: str = "", due_from: str = "", due_to: str = "", overdue: str = "all",
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.task_reports import task_summary
    return task_summary(db, current_user, get_all_reportee_ids(db, current_user), assignee_id, status, priority,
                        task_text, creator_text, due_from, due_to, overdue)


@app.get("/api/reports/tasks.pdf")
def download_task_summary(assignee_id: int | None = None, status: str = "all", priority: str = "all",
                     task_text: str = "", creator_text: str = "", due_from: str = "", due_to: str = "", overdue: str = "all",
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.task_reports import summary_pdf
    summary = get_task_summary(assignee_id=assignee_id, status=status, priority=priority,
                               task_text=task_text, creator_text=creator_text, due_from=due_from,
                               due_to=due_to, overdue=overdue, db=db, current_user=current_user)
    employee = next((person for person in summary["employees"] if person["id"] == assignee_id), None)
    assignee_label = f"{employee['name']} ({employee['email']})" if employee else ("Selected employee" if assignee_id is not None else "All visible employees")
    pdf = summary_pdf(summary, current_user.name, f"Assigned to: {assignee_label} | Status: {status} | Priority: {priority} | Task: {task_text or 'All'} | Assigned by: {creator_text or 'All'} | Due: {due_from or 'Any'} to {due_to or 'Any'} | Overdue: {overdue}")
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="task-summary.pdf"', "Cache-Control": "no-store"})


@app.get("/api/tasks", response_model=List[TaskOut])
def list_tasks(filter_type: str = "all", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if filter_type not in VALID_TASK_FILTERS:
        raise HTTPException(status_code=400, detail="Invalid task filter")

    reportee_ids = get_all_reportee_ids(db, current_user)

    # Desk and personal views have the same user-specific scope for all roles.
    if filter_type in {"archive", "trash"}:
        query = db.query(Task).filter(workflow.visibility(current_user, reportee_ids))
    elif filter_type == "my-day":
        query = db.query(Task).filter(Task.assignee_id == current_user.id, Task.status != "done")
    elif filter_type == "shared":
        query = db.query(Task).filter(workflow.shared_clause(current_user.id))
    elif filter_type == "all":
        query = db.query(Task).filter(
            or_(Task.assignee_id == current_user.id, Task.creator_id == current_user.id),
        )
    elif filter_type == "personal":
        query = db.query(Task).filter(
            Task.assignee_id == current_user.id, Task.creator_id == current_user.id,
        )
    elif current_user.role == "Admin":
        query = db.query(Task)
    elif filter_type in {"team-hierarchy", "delegated-by-me"}:
        query = db.query(Task).filter(Task.assignee_id.in_(reportee_ids))
    else:
        query = db.query(Task).filter(Task.assignee_id == current_user.id)

    if filter_type in {"all", "personal", "my-day", "archive", "trash", "shared"}:
        pass
    elif filter_type == "assigned-by-ro":
        query = query.filter(Task.assignee_id == current_user.id, Task.creator_id == current_user.manager_id)
    elif filter_type == "shared":
        # Sharing never expands visibility beyond the user's own assignments.
        query = query.filter(Task.assignee_id == current_user.id, Task.shared_with_id == current_user.id)
    elif filter_type == "team-hierarchy":
        # Admins can use this view as the all-users workload view; other
        # users see the tasks assigned throughout their reporting hierarchy.
        pass
    elif filter_type == "delegated-by-me":
        query = query.filter(Task.creator_id == current_user.id, Task.assignee_id.in_(reportee_ids))
    
    if filter_type == "trash":
        query = query.filter(Task.deleted_at.is_not(None))
    else:
        query = query.filter(Task.deleted_at.is_(None))
        query = query.filter(Task.archived_at.is_not(None) if filter_type == "archive" else Task.archived_at.is_(None))
    return query.order_by(Task.created_at.desc()).all()

@app.post("/api/tasks", response_model=TaskOut)
def create_new_task(task_in: TaskCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    validate_task_users(db, task_in, current_user)
    workflow.validate_state(task_in)
    workflow.validate_members(db, task_in.members, task_in.assignee_id, current_user.id)
    task = crud.create_task(db=db, task_data=task_in, creator=current_user)
    record_activity(db, "TASK_CREATED", "Created task", request=request, actor=current_user, target_type="task", target_id=task.id, metadata={"assignee_id": task.assignee_id})
    db.commit()
    return task


def comment_task_or_404(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task or task.deleted_at or not can_access_task(db, task, user):
        raise HTTPException(404, "Task not found")
    return task


@app.get("/api/tasks/{task_id}/comments", response_model=list[CommentOut])
def list_comments(task_id: int, before_id: int | None = Query(None, gt=0),
                  limit: int = Query(50, ge=1, le=100),
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    comment_task_or_404(db, task_id, current_user)
    query = db.query(TaskComment).filter(TaskComment.task_id == task_id)
    if before_id is not None:
        query = query.filter(TaskComment.id < before_id)
    return query.order_by(TaskComment.id.desc()).limit(limit).all()


@app.post("/api/tasks/{task_id}/comments", response_model=CommentOut, status_code=201)
def post_comment(task_id: int, payload: CommentCreate, request: Request,
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = comment_task_or_404(db, task_id, current_user)
    if task.archived_at:
        raise HTTPException(409, "Restore the task before commenting")
    if not (current_user.id == task.creator_id or task.assignee_id in get_visible_task_assignee_ids(db, current_user)
            or workflow.collaborator(task, current_user)):
        raise HTTPException(403, "Viewers cannot post comments")
    previous = db.query(TaskComment).filter_by(request_id=str(payload.request_id)).first()
    if previous:
        if (previous.task_id, previous.author_id, previous.body) != (task_id, current_user.id, payload.body):
            raise HTTPException(409, "This submission ID has already been used")
        return previous
    comment = TaskComment(task_id=task_id, author_id=current_user.id,
                          author_name=current_user.name, body=payload.body,
                          request_id=str(payload.request_id))
    db.add(comment)
    record_activity(db, "TASK_COMMENTED", "Added a task comment", request=request,
                    actor=current_user, target_type="task", target_id=task_id)
    workflow.notify(db, task, workflow.participants(task), 'comment',
                    f'{current_user.name} commented on {task.title}', current_user.id)
    db.commit()
    db.refresh(comment)
    return comment

@app.put("/api/tasks/{task_id}", response_model=TaskOut)
def update_task_endpoint(task_id: int, task_in: TaskUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task or task.deleted_at:
        raise HTTPException(status_code=404, detail="Task not found")
    if not can_update_task(db, task, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to update this task")
    if task.archived_at:
        raise HTTPException(409, "Restore the task before editing")
    if task.assignee_id != current_user.id and task_in.model_fields_set - {'status', 'blocked_reason', 'checklist'}:
        raise HTTPException(403, "Collaborators can update status, block reason and checklist only")
    workflow.validate_state(task_in, task)
    validate_task_users(db, task_in, current_user)
    updated_task = crud.update_task(db=db, task=task, update_data=task_in, user=current_user)
    record_activity(db, "TASK_UPDATED", "Updated task", request=request, actor=current_user, target_type="task", target_id=task.id, metadata={"fields": sorted(task_in.model_fields_set)})
    db.commit()
    return updated_task

@app.delete("/api/tasks/{task_id}")
def delete_task_endpoint(task_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not can_delete_task(db, task, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to delete this task")
    record_activity(db, "TASK_DELETED", "Deleted task", request=request, actor=current_user, target_type="task", target_id=task.id, metadata={"title": task.title})
    task.deleted_at = datetime.utcnow()
    workflow.history(db, task, current_user, 'Moved task to Trash')
    db.commit()
    return {"message": "Task moved to Trash. You can restore it."}


@app.get("/api/admin/activity-logs", response_model=List[ActivityLogOut])
def list_activity_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit).all()


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def get_task_detail(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task or not can_access_task(db, task, current_user):
        raise HTTPException(404, "Task not found")
    return task


@app.get("/api/search/tasks", response_model=list[TaskOut])
def search_tasks_endpoint(q: str = Query(..., min_length=1, max_length=200), scope: str = 'active',
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if scope not in {'active', 'archive', 'trash'} or not q.strip():
        raise HTTPException(422, 'Enter a search term and choose active, archive or trash')
    query = db.query(Task).filter(workflow.visibility(current_user, get_all_reportee_ids(db, current_user)))
    if scope == 'trash':
        query = query.filter(Task.deleted_at.is_not(None))
    else:
        query = query.filter(Task.deleted_at.is_(None), Task.archived_at.is_not(None) if scope == 'archive' else Task.archived_at.is_(None))
    return workflow.search_tasks(query, q).order_by(Task.due_date, Task.id).all()


@app.get("/api/tasks/{task_id}/dependencies")
def list_dependencies(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = get_task_detail(task_id, db, current_user)
    result = []
    for link in task.dependency_links:
        prerequisite = link.prerequisite
        visible = can_access_task(db, prerequisite, current_user) and not prerequisite.deleted_at
        result.append(dict(link_id=link.id, task_id=prerequisite.id if visible else None,
                           title=prerequisite.title if visible else 'Restricted or deleted prerequisite',
                           status=prerequisite.status if visible else None, satisfied=link.satisfied,
                           archived=bool(prerequisite.archived_at) if visible else False))
    return result


def dependency_owner(db, task_id, current_user):
    task = comment_task_or_404(db, task_id, current_user)
    if current_user.id not in {task.assignee_id, task.creator_id}:
        raise HTTPException(403, 'Only the owner or creator can manage dependencies')
    if task.archived_at:
        raise HTTPException(409, 'Restore the task before changing dependencies')
    return task


@app.post("/api/tasks/{task_id}/dependencies")
def add_dependency(task_id: int, payload: DependencyCreate, request: Request,
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = dependency_owner(db, task_id, current_user)
    prerequisite = comment_task_or_404(db, payload.depends_on_id, current_user)
    if any(link.depends_on_id == prerequisite.id for link in task.dependency_links):
        return {'message': 'Prerequisite already linked'}
    workflow.check_dependency(db, task, prerequisite)
    db.add(TaskDependency(task_id=task.id, depends_on_id=prerequisite.id))
    workflow.history(db, task, current_user, 'Added a prerequisite task')
    record_activity(db, 'TASK_DEPENDENCY_ADDED', 'Added task dependency', request=request,
                    actor=current_user, target_type='task', target_id=task.id)
    db.commit()
    return {'message': 'Prerequisite added'}


@app.delete("/api/tasks/{task_id}/dependencies/{link_id}")
def remove_dependency(task_id: int, link_id: int, request: Request,
                      db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = dependency_owner(db, task_id, current_user)
    link = db.query(TaskDependency).filter_by(id=link_id, task_id=task.id).first()
    if not link:
        raise HTTPException(404, 'Dependency not found')
    db.delete(link)
    workflow.history(db, task, current_user, 'Removed a prerequisite task')
    record_activity(db, 'TASK_DEPENDENCY_REMOVED', 'Removed task dependency', request=request,
                    actor=current_user, target_type='task', target_id=task.id)
    db.commit()
    return {'message': 'Prerequisite removed'}


@app.put("/api/tasks/{task_id}/collaboration", response_model=TaskOut)
def update_collaboration(task_id: int, payload: CollaborationUpdate, request: Request,
                         db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = comment_task_or_404(db, task_id, current_user)
    if current_user.id not in {task.assignee_id, task.creator_id}:
        raise HTTPException(403, "Only the owner or creator can manage participants")
    if task.archived_at:
        raise HTTPException(409, "Restore the task before changing participants")
    workflow.validate_members(db, payload.members, task.assignee_id, task.creator_id)
    previous = workflow.participants(task)
    task.members.clear()
    db.flush()
    task.members = [TaskMember(user_id=m.user_id, role=m.role) for m in payload.members]
    task.shared_with_id = None  # Explicit roles replace legacy sharing.
    workflow.history(db, task, current_user, 'Updated collaborators and viewers')
    workflow.notify(db, task, workflow.participants(task) - previous, 'assignment',
                    f'You have been added to {task.title}', current_user.id)
    record_activity(db, 'TASK_PARTICIPANTS_UPDATED', 'Updated task participants', request=request,
                    actor=current_user, target_type='task', target_id=task.id)
    db.commit()
    return task


@app.post("/api/tasks/{task_id}/archive", response_model=TaskOut)
def archive_task(task_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = comment_task_or_404(db, task_id, current_user)
    if not can_delete_task(db, task, current_user):
        raise HTTPException(403, "Only the task owner can archive it")
    if not task.archived_at:
        task.archived_at = datetime.utcnow()
        workflow.history(db, task, current_user, 'Archived task')
        record_activity(db, 'TASK_ARCHIVED', 'Archived task', request=request, actor=current_user, target_type='task', target_id=task.id)
        db.commit()
    return task


@app.post("/api/tasks/{task_id}/restore", response_model=TaskOut)
def restore_task(task_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = get_task_detail(task_id, db, current_user)
    if not can_delete_task(db, task, current_user):
        raise HTTPException(403, "Only the task owner can restore it")
    if task.archived_at or task.deleted_at:
        task.archived_at = task.deleted_at = None
        workflow.history(db, task, current_user, 'Restored task to active work')
        record_activity(db, 'TASK_RESTORED', 'Restored task', request=request, actor=current_user, target_type='task', target_id=task.id)
        db.commit()
    return task


@app.get("/api/notifications")
def list_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_reminders = workflow.ensure_reminders(db, current_user)
    query = db.query(Notification).join(Task, Task.id == Notification.task_id).filter(
        Notification.recipient_id == current_user.id, Task.deleted_at.is_(None), Task.archived_at.is_(None),
        workflow.visibility(current_user, get_all_reportee_ids(db, current_user)),
        or_(Notification.kind != 'reminder', Notification.dedupe_key.in_(current_reminders)))
    unread = query.filter(Notification.read_at.is_(None)).count()
    rows = query.order_by(Notification.id.desc()).limit(100).all()
    return {'unread': unread, 'items': [dict(id=n.id, task_id=n.task_id, kind=n.kind, message=n.message,
            created_at=n.created_at, read=n.read_at is not None) for n in rows]}


@app.post("/api/notifications/read-all")
def read_all_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.recipient_id == current_user.id,
                                  Notification.read_at.is_(None)).update({'read_at': datetime.utcnow()})
    db.commit()
    return {'message': 'Notifications marked as read'}


@app.post("/api/notifications/{notification_id}/read")
def read_notification(notification_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Notification).filter_by(id=notification_id, recipient_id=current_user.id).first()
    if not item:
        raise HTTPException(404, 'Notification not found')
    item.read_at = datetime.utcnow()
    db.commit()
    return {'message': 'Notification marked as read'}

@app.get("/")
def redirect_to_login(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("task_manager_token")
    if token:
        try:
            get_user_from_token(token, db)
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        except HTTPException:
            pass
    return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login")
@app.get("/login.html")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")

@app.get("/dashboard")
@app.get("/dashboard.html")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("task_manager_token")
    if token:
        try:
            get_user_from_token(token, db)
            return FileResponse(STATIC_DIR / "index.html")
        except HTTPException:
            pass
    return RedirectResponse(url="/login.html", status_code=status.HTTP_303_SEE_OTHER)
