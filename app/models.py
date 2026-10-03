from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="Junior Staff") # e.g., "Reporting Officer", "Junior Staff"
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    manager = relationship("User", remote_side=[id], backref="reportees")
    tasks_assigned = relationship("Task", foreign_keys="Task.assignee_id", back_populates="assignee")
    tasks_created = relationship("Task", foreign_keys="Task.creator_id", back_populates="creator")
    categories_created = relationship("TaskCategory", back_populates="creator")

class TaskCategory(Base):
    __tablename__ = "task_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, index=True, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    creator = relationship("User", back_populates="categories_created")
    tasks = relationship("Task", back_populates="category")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(50), default="todo") # "todo", "inprogress", "done"
    priority = Column(String(20), default="Medium") # "Low", "Medium", "High"
    due_date = Column(String(50), nullable=False)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("task_categories.id"), nullable=True)

    # Lifecycle Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[creator_id], back_populates="tasks_created")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="tasks_assigned")
    shared_with = relationship("User", foreign_keys=[shared_with_id])
    category = relationship("TaskCategory", back_populates="tasks")
    history = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan", order_by="desc(TaskHistory.timestamp)")

class TaskHistory(Base):
    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    author_name = Column(String(100), nullable=False)
    action = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="history")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_email = Column(String(120), nullable=True, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(80), nullable=True)
    action = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    success = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
