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
# 1. create token for user with email
# 2. list token for an email
# 3. deactivate token - email + token_id
# 4. regeneate token - email + token_id + decative_old_token_bool (to deactivate old token or not)
'''
def create_token()
def get_token_by_email()
def deactivate_token()
def regenerate_token()

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
'''

def create_token(db: Session, token: schemas.ApiTokenCreate) -> Optional[models.ApiToken]:
    db_token = models.ApiToken(user_id=token.user_id, token_hash=token.token_hash)
    db.add(db_token)
    db.commit()
    db.refresh(instance=db_token)
    return db_token