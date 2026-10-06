from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_name: str
    action: str
    timestamp: datetime


class CommentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=5000)
    request_id: UUID


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    author_id: int
    author_name: str
    body: str
    created_at: datetime


class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    actor_user_id: Optional[int] = None
    actor_email: Optional[EmailStr] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    action: str
    metadata_json: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: int
    created_at: datetime

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: str
    manager_id: Optional[int] = None

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    creator_id: Optional[int] = None
    created_at: datetime

class ChecklistItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=300)
    done: bool = False


class TaskMemberIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int = Field(gt=0)
    role: Literal["collaborator", "viewer"]


class CollaborationUpdate(BaseModel):
    members: list[TaskMemberIn] = Field(max_length=30)


class DependencyCreate(BaseModel):
    depends_on_id: int = Field(gt=0)


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: Optional[str] = None
    due_date: date
    priority: Literal["Low", "Medium", "High"] = "Medium"
    status: Literal["todo", "inprogress", "blocked", "done"] = "todo"
    assignee_id: int
    shared_with_id: Optional[int] = None
    category_id: Optional[int] = None
    blocked_reason: Optional[str] = Field(default=None, max_length=1000)
    recurrence: Literal["none", "daily", "weekly", "monthly"] = "none"
    checklist: list[ChecklistItem] = Field(default_factory=list, max_length=50)
    members: list[TaskMemberIn] = Field(default_factory=list, max_length=30)

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    summary: Optional[str] = None
    due_date: Optional[date] = None
    priority: Optional[Literal["Low", "Medium", "High"]] = None
    status: Optional[Literal["todo", "inprogress", "blocked", "done"]] = None
    assignee_id: Optional[int] = None
    shared_with_id: Optional[int] = None
    category_id: Optional[int] = None
    blocked_reason: Optional[str] = Field(default=None, max_length=1000)
    recurrence: Optional[Literal["none", "daily", "weekly", "monthly"]] = None
    checklist: Optional[list[ChecklistItem]] = Field(default=None, max_length=50)

class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    creator: UserOut
    assignee: UserOut
    shared_with: Optional[UserOut] = None
    category: Optional[CategoryOut] = None
    history: list[HistoryOut] = Field(default_factory=list)
    archived_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    recurrence_parent_id: Optional[int] = None
    dependency_count: int = 0
    waiting_count: int = 0

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

class ManagerUpdate(BaseModel):
    manager_id: Optional[int] = Field(..., gt=0)
