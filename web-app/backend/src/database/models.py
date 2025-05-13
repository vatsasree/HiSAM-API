from sqlalchemy import Integer, String, Column, ForeignKey, Boolean, Text, DateTime, Enum as SQLEnum, Table
from sqlalchemy.dialects.mysql import BINARY, LONGTEXT, SMALLINT
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from uuid import uuid4
from enum import Enum

# Define the Base using declarative_base()
Base = declarative_base()

# Association table for ApiToken privileges
token_privileges = Table(
    'token_privileges', Base.metadata,
    Column('token_id', Integer, ForeignKey('api_tokens.token_id', ondelete='CASCADE'), primary_key=True),
    Column('privilege_id', Integer, ForeignKey('privileges.id', ondelete='CASCADE'), primary_key=True)
)

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
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tokens = relationship('ApiToken', back_populates='user', cascade="all, delete-orphan")

class Privilege(Base):
    __tablename__ = 'privileges'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(32), nullable=False, unique=True)
    description = Column(String(512), nullable=True)

    tokens = relationship(
        'ApiToken', secondary=token_privileges,
        back_populates='privileges'
    )

class ApiToken(Base):
    __tablename__ = 'api_tokens'
    
    token_id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship('User', back_populates='tokens')
    jobs = relationship('JobRecord', back_populates='api_token', cascade="all, delete-orphan")
    privileges = relationship(
        'Privilege', secondary=token_privileges,
        back_populates='tokens'
    )

class JobRecord(Base):
    __tablename__ = 'jobs'
    
    job_id = Column(BINARY(16), primary_key=True, default=lambda: uuid4().bytes)
    api_token_id = Column(Integer, ForeignKey('api_tokens.token_id', ondelete='CASCADE'), nullable=False)
    n_documents = Column(SMALLINT, nullable=True)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    api_token = relationship('ApiToken', back_populates='jobs')
    documents = relationship('DocumentRecord', back_populates='job', cascade='all, delete-orphan')

class DocumentRecord(Base):
    __tablename__ = 'documents'
    
    doc_id = Column(Integer, primary_key=True, index=True)
    job_id = Column(BINARY(16), ForeignKey('jobs.job_id', ondelete='CASCADE'), nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True)
    doc_path = Column(String(512), nullable=False)
    width = Column(SMALLINT, nullable=True)
    height = Column(SMALLINT, nullable=True)
    output = Column(LONGTEXT, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    job = relationship('JobRecord', back_populates='documents')
