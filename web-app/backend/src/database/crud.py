from uuid import uuid4
from typing import List, Optional
from sqlalchemy.orm import Session

from src.core import security
from . import models, schemas


# --- User CRUD ---
def get_user(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    hashed_password = security.get_password_hash(user.password)
    db_user = models.User(full_name=user.full_name, email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(instance=db_user)
    return db_user

# --- Token CRUD ---
# 1. create token for user with email - [DONE]
# 2. list token for an email - [DONE]
# 3. deactivate token - email + token_id - [TODO]
# 4. regeneate token - email + token_id + decative_old_token_bool (to deactivate old token or not) - [TODO]

def create_token(db: Session, token: schemas.ApiTokenCreate) -> Optional[models.ApiToken]:
    db_token = models.ApiToken(user_id=token.user_id, token_hash=token.token_hash)
    db.add(db_token)
    db.commit()
    db.refresh(instance=db_token)
    return db_token

def get_token_by_hash(db: Session, *, token_hash: str) -> Optional[models.ApiToken]:
    """Get a token by its SHA-256 hash."""
    return db.query(models.ApiToken).filter(models.ApiToken.token_hash == token_hash).first()

def get_token_privileges(db: Session, token_id: int) -> List[schemas.PrivilegeRead]:
    # 1. Query the Privilege table joined to the token_privileges association
    privileges = (
        db.query(models.Privilege)
          .join(
              models.token_privileges,
              models.Privilege.id == models.token_privileges.c.privilege_id
          )
          .filter(models.token_privileges.c.token_id == token_id)
          .all()
    )

    # 2. Convert each ORM Privilege into the Pydantic schema
    return [
        schemas.PrivilegeRead.model_validate(priv)  # use model_validate per Pydantic V2 :contentReference[oaicite:0]{index=0}
        for priv in privileges
    ]

# --- Document CRUD ---
def get_document_by_id(db: Session, doc_id: int) -> Optional[models.DocumentRecord]:
    return db.query(models.DocumentRecord).filter(models.DocumentRecord.doc_id == doc_id).first()

def update_document_status_and_result(
    db: Session, 
    doc_id:int, 
    status: models.JobStatus, 
    output: Optional[str] = None, 
    error_message: Optional[str] = None
    ) -> Optional[models.DocumentRecord]:
    data_obj = db.query(models.DocumentRecord).filter(models.DocumentRecord.doc_id == doc_id).first()
        
    if not data_obj:
        return None 
    
    if status is not None:
        data_obj.status = status
    if output is not None:
        data_obj.output = output
    if error_message is not None:
        data_obj.error_message = error_message

    # Commit the changes to the database  
    db.commit()
    db.refresh(instance=data_obj)

    return data_obj

def get_job_document_statuses(db: Session, job_id_bytes: bytes) -> List[models.JobStatus]:
    return db.query(models.DocumentRecord).filter(models.DocumentRecord.job_id == job_id_bytes).all()


# --- Job CRUD ---
def update_job_status(db: Session, job_id_bytes: bytes, status: models.JobStatus) -> Optional[models.JobRecord]:
    job_data = get_job_by_job_id(db, job_id_bytes=job_id_bytes)
    
    if not job_data:
        return None
    
    if status is not None:
        job_data.status = status

    # Commit the changes to the database  
    db.commit()
    db.refresh(instance=job_data)
    return job_data

def get_job_by_job_id(db: Session, job_id_bytes: bytes) -> models.JobRecord:
    return db.query(models.JobRecord).filter(models.JobRecord.job_id == job_id_bytes).first()

# --- User Privilage CRUD --- #
# def get_user_privileges(db:Session, )