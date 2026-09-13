from __future__ import annotations
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from app.config import get_settings

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); email: Mapped[str]=mapped_column(String(255),unique=True); display_name: Mapped[str]=mapped_column(String(255)); provider: Mapped[str]=mapped_column(String(40),default="development"); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class ActiveAccessSession(Base):
    __tablename__="active_access_sessions"; id: Mapped[str]=mapped_column(String(64),primary_key=True); last_seen_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class OAuthLoginState(Base):
    __tablename__="oauth_login_states"; state: Mapped[str]=mapped_column(String(64),primary_key=True); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class OAuthSession(Base):
    __tablename__="oauth_sessions"; session_id: Mapped[str]=mapped_column(String(64),primary_key=True); user_id: Mapped[str]=mapped_column(ForeignKey("users.id")); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class OAuthCallbackTicket(Base):
    __tablename__="oauth_callback_tickets"; ticket: Mapped[str]=mapped_column(String(64),primary_key=True); session_id: Mapped[str]=mapped_column(String(64)); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class LoginAudit(Base):
    __tablename__="login_audit"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); user_id: Mapped[str]=mapped_column(ForeignKey("users.id")); email: Mapped[str]=mapped_column(String(255)); event: Mapped[str]=mapped_column(String(30)); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Presentation(Base):
    __tablename__="presentations"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); user_id: Mapped[str]=mapped_column(ForeignKey("users.id")); title: Mapped[str]=mapped_column(String(500)); topic: Mapped[str]=mapped_column(String(2000)); status: Mapped[str]=mapped_column(String(40),default="QUEUED"); current_version_id: Mapped[str|None]=mapped_column(String(36),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class PresentationVersion(Base):
    __tablename__="presentation_versions"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); presentation_id: Mapped[str]=mapped_column(ForeignKey("presentations.id")); version_number: Mapped[int]=mapped_column(Integer); spec_json: Mapped[dict]=mapped_column(JSON); generated_by: Mapped[str]=mapped_column(String(80)); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class GenerationJob(Base):
    __tablename__="generation_jobs"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); presentation_id: Mapped[str]=mapped_column(ForeignKey("presentations.id")); job_type: Mapped[str]=mapped_column(String(30),default="generate"); status: Mapped[str]=mapped_column(String(40),default="QUEUED"); progress: Mapped[int]=mapped_column(Integer,default=0); current_stage: Mapped[str]=mapped_column(String(50),default="QUEUED"); stage_started_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True); estimated_total_seconds: Mapped[int|None]=mapped_column(Integer,nullable=True); error_message: Mapped[str|None]=mapped_column(String(2000),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class FeedbackReport(Base):
    __tablename__="feedback_reports"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); session_id: Mapped[str]=mapped_column(String(64)); category: Mapped[str]=mapped_column(String(20)); message: Mapped[str]=mapped_column(String(6000)); prompt: Mapped[str|None]=mapped_column(String(16000),nullable=True); error_details: Mapped[str|None]=mapped_column(String(6000),nullable=True); reply_to: Mapped[str|None]=mapped_column(String(254),nullable=True); screenshot_path: Mapped[str|None]=mapped_column(String(1000),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

settings = get_settings()

# A fresh local deployment has no ignored ``storage/`` directory yet.  Create
# the SQLite parent and generated-file root before SQLAlchemy opens its first
# connection so startup works on a clean server as well as in development.
if settings.database_url.startswith("sqlite:///"):
    database_path = settings.database_url.removeprefix("sqlite:///")
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
settings.local_storage_path.mkdir(parents=True, exist_ok=True)
settings.feedback_storage_path.mkdir(parents=True, exist_ok=True)

engine=create_engine(settings.database_url, connect_args={"check_same_thread":False} if settings.database_url.startswith("sqlite") else {})
SessionLocal=sessionmaker(bind=engine, expire_on_commit=False)
def init_db():
    """Create tables and apply the small additive SQLite migrations we need."""
    Base.metadata.create_all(engine)
    columns={column["name"] for column in inspect(engine).get_columns("generation_jobs")}
    # Existing local and VM databases predate timing fields. Adding nullable
    # columns preserves every queued/completed job in place.
    with engine.begin() as connection:
        if "stage_started_at" not in columns:
            connection.execute(text("ALTER TABLE generation_jobs ADD COLUMN stage_started_at DATETIME"))
        if "estimated_total_seconds" not in columns:
            connection.execute(text("ALTER TABLE generation_jobs ADD COLUMN estimated_total_seconds INTEGER"))
