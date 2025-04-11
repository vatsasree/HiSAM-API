from sqlalchemy import Integer, String, Column, ForeignKey, Boolean, Text, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.mysql import BINARY, LONGTEXT, SMALLINT
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
# from ..database.se import Base
from uuid import uuid4, UUID
from enum import Enum


# Define the Base using declarative_base()
Base = declarative_base()


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    


class User(Base):
    __tablename__ = 'users'
    
    user_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    tokens = relationship('ApiToken', back_populates='user')


class ApiToken(Base):
    __tablename__ = 'api_tokens'
    
    token_id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    # token_prefix = Column(String(8), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    user = relationship('User', back_populates="tokens")
    jobs = relationship("JobRecord", back_populates="tokens")
    
class JobRecord(Base):
    __tablename__ = "jobs"
    
    job_id = Column(BINARY(16), primary_key=True, default=lambda: uuid4().bytes)
    api_token_id = Column(Integer, ForeignKey("api_tokens.token_id"), nullable=False)
    n_documents = Column(SMALLINT, nullable=True)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    tokens = relationship("ApiToken", back_populates="jobs")
    documents = relationship("DocumentRecord", back_populates="jobs", cascade="all, delete-orphan")
    # cascade ensure changes (eg: delete / update) in parsing records is passed to child table

    # # Helper property to get UUID as string
    # @property
    # def job_id_str(self):
    #     return str(uuid.UUID(bytes=self.id)) if self.id else None

class DocumentRecord(Base):
    __tablename__ = "documents"
    
    doc_id = Column(Integer, primary_key=True, index=True)
    job_id = Column(BINARY(16), ForeignKey("jobs.job_id"), nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True)
    doc_path = Column(String(512), nullable=False)
    width = Column(SMALLINT, nullable=True)
    height = Column(SMALLINT, nullable=True)
    output = Column(LONGTEXT, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    jobs = relationship("JobRecord", back_populates="documents")
    