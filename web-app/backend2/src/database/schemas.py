from uuid import uuid4, UUID
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
            return None # Handle case where bytes are not a valid UUID
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
    # hashed_password: str
    password: str
################# password: Optional[str] = None # Password optional on creation if using tokens only

class UserUpdate(UserBase):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None

class UserRead(UserBase):
    user_id: int
    is_active: bool
    create_at: datetime

# --- API Token Schemas --- 
class ApiTokenBase(OrmBaseModel):
    user_id: int
    is_active: bool = True
    expires_at: Optional[datetime] = None

class ApiTokenCreate(ApiTokenBase):
    # The raw token is only used momentarily during creation, never stored raw. Only hash is stored.
    token_hash: str = Field(..., exclude=True) # Exclude from default serialization

class ApiTokenUpdate(OrmBaseModel): # Schema for updates (e.g., admin actions)
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None

class ApiTokenRead(OrmBaseModel):
    token_id: int
    user_id: int
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    # token_str: Optional[str] = Field(None, exclude=True) # Excluded from normal responses


# --- Document Record Schemas --- 
class DocumentRecordBase(OrmBaseModel):
    doc_path: str

class DocumentRecordCreate(DocumentRecordBase):
    # job_id is set implicitly when creating documents for a job
    pass

class DocumentRecordUpdate(OrmBaseModel): # Used by Celery Task
    status: Optional[JobStatus] = None
    output: Optional[str] = None
    error_message: Optional[str] = None
    
class DocumentRecordRead(DocumentRecordBase):
    doc_id: int
    job_id: BinaryUUID # Use the custom type for conversion
    status: JobStatus
    output: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

# --- Job Record Schema --- 
class JobRecordBase(OrmBaseModel):
    pass

class JobRecordCreate(JobRecordBase):
    # job_id is auto-generated (bytes in DB)
    api_token_id: int

class JobRecordUpdate(OrmBaseModel): # Used by Celery Task / System
    status: Optional[JobStatus] = None

class JobRecordRead(JobRecordBase):
    job_id: BinaryUUID
    api_token_id: int
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentRecordRead] = [] # Include related documents


# --- API Endpint Schemas ---

# Response body for the /process endpoint
class ProcessResponse(BaseModel):
    job_id: UUID # Return the standard UUID
    message: str = "Job accepted for processing."
    document_count: int

# Response body for the /status/{job_id} endpoint
class JobStatusResponse(BaseModel):
    job: JobRecordRead # Return the full job details including documents


# --- Admin Script Schemas ---
class TokenGenerationRequest(BaseModel):
    user_email: EmailStr

class TokenInfo(BaseModel): # For listing tokens (never show hash/raw)
    token_id: int
    created_at: datetime
    is_active: bool
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

class UserTokenList(BaseModel):
    user: UserRead
    tokens: List[TokenInfo] = []