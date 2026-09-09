from __future__ import annotations
from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from app.config import get_settings

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); email: Mapped[str]=mapped_column(String(255),unique=True); display_name: Mapped[str]=mapped_column(String(255)); provider: Mapped[str]=mapped_column(String(40),default="development"); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class ActiveAccessSession(Base):
    __tablename__="active_access_sessions"; id: Mapped[str]=mapped_column(String(64),primary_key=True); last_seen_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Presentation(Base):
    __tablename__="presentations"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); user_id: Mapped[str]=mapped_column(ForeignKey("users.id")); title: Mapped[str]=mapped_column(String(500)); topic: Mapped[str]=mapped_column(String(2000)); status: Mapped[str]=mapped_column(String(40),default="QUEUED"); current_version_id: Mapped[str|None]=mapped_column(String(36),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class PresentationVersion(Base):
    __tablename__="presentation_versions"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); presentation_id: Mapped[str]=mapped_column(ForeignKey("presentations.id")); version_number: Mapped[int]=mapped_column(Integer); spec_json: Mapped[dict]=mapped_column(JSON); generated_by: Mapped[str]=mapped_column(String(80)); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class GenerationJob(Base):
    __tablename__="generation_jobs"; id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4())); presentation_id: Mapped[str]=mapped_column(ForeignKey("presentations.id")); job_type: Mapped[str]=mapped_column(String(30),default="generate"); status: Mapped[str]=mapped_column(String(40),default="QUEUED"); progress: Mapped[int]=mapped_column(Integer,default=0); current_stage: Mapped[str]=mapped_column(String(50),default="QUEUED"); error_message: Mapped[str|None]=mapped_column(String(2000),nullable=True); created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)

engine=create_engine(get_settings().database_url, connect_args={"check_same_thread":False} if get_settings().database_url.startswith("sqlite") else {})
SessionLocal=sessionmaker(bind=engine, expire_on_commit=False)
def init_db(): Base.metadata.create_all(engine)
