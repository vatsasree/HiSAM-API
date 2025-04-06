from typing import Generator, Any
from sqlalchemy.orm import Session

# Re-export get_db for cleaner imports in endpoint files
from src.database.session import get_db

# Re-export token dependency
from src.core.security import get_current_valid_api_token
from src.database.models import ApiToken # Import the model type

# You can define other common dependencies here if needed
# Example: Dependency to get the current user based on JWT (if implementing user login)
# from fastapi.security import OAuth2PasswordBearer
# from jose import jwt
# from pydantic import ValidationError
# from fastapi import Depends, HTTPException, status
# from src.core import security, config
# from src.database import crud, schemas, models

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{config.settings.API_V1_STR}/login/access-token")

# async def get_current_user(
#     db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
# ) -> models.User:
#     credentials_exception = HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Could not validate credentials",
#         headers={"WWW-Authenticate": "Bearer"},
#     )
#     try:
#         payload = jwt.decode(
#             token, config.settings.SECRET_KEY, algorithms=[security.ALGORITHM]
#         )
#         username: str = payload.get("sub")
#         if username is None:
#             raise credentials_exception
#         token_data = schemas.TokenData(username=username)
#     except (jwt.JWTError, ValidationError):
#         raise credentials_exception
#     user = crud.user.get_by_email(db, email=token_data.username)
#     if user is None:
#         raise credentials_exception
#     return user

# async def get_current_active_user(
#     current_user: models.User = Depends(get_current_user),
# ) -> models.User:
#     if not crud.user.is_active(current_user):
#         raise HTTPException(status_code=400, detail="Inactive user")
#     return current_user
