from uuid import UUID
from datetime import datetime
from typing import List, Optional, Any, Annotated
from pydantic import BaseModel, Field, field_validator, ConfigDict, BeforeValidator, EmailStr

from src.database.models import JobStatus

# --- Base Schemas ---
class OrmBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# --- Validator Functions ---
def convert_binary_to_uuid(v: Any) -> Optional[UUID]:
    if isinstance(v, bytes):
        try:
            return UUID(bytes=v)
        except ValueError:
            return None
    if isinstance(v, UUID):
        return v
    return None

# Type Alias for clarity
BinaryUUID = Annotated[UUID, BeforeValidator(convert_binary_to_uuid)]


# --- User Schemas ---
class UserBase(OrmBaseModel):
    email: str
    full_name: str

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None

class UserRead(UserBase):
    user_id: int
    is_active: bool
    created_at: datetime


# --- Privilege Schemas ---
class PrivilegeCreate(BaseModel):
    name: str
    description: Optional[str] = None

class PrivilegeRead(OrmBaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None


# --- API Token Schemas ---
class ApiTokenBase(OrmBaseModel):
    user_id: int
    is_active: bool = True
    expires_at: Optional[datetime] = None

class ApiTokenCreate(ApiTokenBase):
    token_hash: str = Field(..., exclude=True)

class ApiTokenUpdate(OrmBaseModel):
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None

class ApiTokenRead(OrmBaseModel):
    token_id: int
    user_id: int
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    privileges: List[PrivilegeRead] = []


# --- Document Record Schemas ---
class DocumentRecordBase(OrmBaseModel):
    doc_path: str
    width: Optional[int]
    height: Optional[int]
    rescale_factor: Optional[float]

class DocumentRecordCreate(DocumentRecordBase):
    pass

class DocumentRecordUpdate(OrmBaseModel):
    status: Optional[JobStatus] = None
    output: Optional[str] = None
    error_message: Optional[str] = None

class DocumentRecordRead(DocumentRecordBase):
    doc_id: int
    job_id: BinaryUUID
    status: JobStatus
    output: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class DocumentRecordStatus(OrmBaseModel):
    doc_path: str
    status: JobStatus


# --- Job Record Schemas ---
class JobRecordBase(OrmBaseModel):
    pass

class JobRecordCreate(JobRecordBase):
    api_token_id: int

class JobRecordUpdate(OrmBaseModel):
    status: Optional[JobStatus] = None

class JobRecordRead(JobRecordBase):
    job_id: BinaryUUID
    api_token_id: int
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentRecordRead] = []


# --- API Endpoint Schemas ---
class ProcessResponse(BaseModel):
    job_id: UUID
    message: str = "Job accepted for processing."
    document_count: int

# class JobStatusResponse(BaseModel):
#     job: JobRecordRead




class JobStatusCheck(BaseModel):
    job_id: BinaryUUID
    status: JobStatus
    documents: List[DocumentRecordStatus] = []


# --- Admin Script Schemas ---
class TokenGenerationRequest(BaseModel):
    user_email: EmailStr

class TokenInfo(BaseModel):
    token_id: int
    created_at: datetime
    is_active: bool
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    privileges: List[PrivilegeRead] = []

class UserTokenList(BaseModel):
    user: UserRead
    tokens: List[TokenInfo] = []


# --- Document Status Schema ---
class DocumentStatusResponse(BaseModel):
    doc_path: str
    status: str

# Job status response schema
class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    documents: List[DocumentStatusResponse] = []
