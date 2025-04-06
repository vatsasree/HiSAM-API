# app/core/security.py
import secrets
import hashlib
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from typing import Optional
from decouple import config

from src.database import crud, models, schemas # Import crud for token lookup
from src.database.session import get_db
# from src.api.deps import get_db # Import get_db dependency


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Hashes a password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

# --- API Token Specific Functions ---
# Expects the token to be passed in the 'X-API-Token' header
API_KEY_HEADER_NAME = "X-API-Token"
# Expects the token to be passed in the header defined in settings
api_key_header_scheme = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False) # auto_error=False to allow custom exception

def generate_api_token(prefix: str = "usk", length: int = 40) -> str:
    """Generates a secure random API token with a prefix."""
    # Generates a URL-safe text string, containing Base64 characters
    random_part = secrets.token_urlsafe(length)
    return f"{prefix}_{random_part}" # Example: usk_RjZmVDI1ZDAtZTM1YS0...

def hash_api_token(token: str) -> str:
    """Creates a SHA-256 hash of the API token for storage."""
    # We don't use bcrypt here because we need to look up by the hash
    # and bcrypt generates a different hash each time (includes salt).
    # SHA-256 is deterministic and suitable for this lookup purpose.
    # Ensure the token is encoded to bytes before hashing.
    return hashlib.sha256(token.encode('utf-8')).hexdigest()

def generate_and_hash_api_token():
    # used in manage_token.py
    raw_token =generate_api_token()
    token_hash =hash_api_token(raw_token)
    return raw_token, token_hash


async def get_current_valid_api_token(
    api_key: str = Depends(api_key_header_scheme), # Gets token from header
    db: Session = Depends(get_db) # Gets DB session
) -> models.ApiToken:
    """
    Dependency to verify the API token provided in the header.

    1. Checks if the token was provided.
    2. Hashes the provided token using SHA-256.
    3. Looks up the hash in the database.
    4. Checks if the token is active and not expired (if expiry is implemented).
    5. Returns the corresponding ApiToken model or raises HTTPException.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, # Use 401 for missing credentials
            detail="Not authenticated: API Token is required.",
            headers={"WWW-Authenticate": "Header"}, # Indicate header auth is expected
        )

    token_hash = hash_api_token(api_key)
    db_token = crud.token.get_by_hash(db, token_hash=token_hash)

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Token provided.",
        )

    if not db_token.is_active:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="API Token is inactive."
        )

    # Optional: Check for token expiry
    # if db_token.expires_at and db_token.expires_at < datetime.now(timezone.utc):
    #     # You might want to deactivate the token here as well
    #     # crud.token.deactivate(db, db_token=db_token)
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="API Token has expired."
    #     )

    # Optional: Update last used timestamp (consider performance implications)
    # crud.token.update_last_used(db, db_token=db_token)

    return db_token

# --- User related security (if needed later, e.g. for web dashboard) ---
# Example: Creating and verifying JWT tokens for user sessions
# from jose import JWTError, jwt
# from datetime import timedelta

# ALGORITHM = "HS256"
# ACCESS_TOKEN_EXPIRE_MINUTES = 30

# def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
#     to_encode = data.copy()
#     if expires_delta:
#         expire = datetime.now(timezone.utc) + expires_delta
#     else:
#         expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
#     return encoded_jwt

# def verify_access_token(token: str, credentials_exception):
#     try:
#         payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
#         username: str = payload.get("sub")
#         if username is None:
#             raise credentials_exception
#         token_data = schemas.TokenData(username=username) # Assuming you have a TokenData schema
#     except JWTError:
#         raise credentials_exception
#     return token_data