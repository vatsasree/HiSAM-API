from typing import Annotated
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from decouple import config

import logging
logger = logging.getLogger(__name__)

from sqlalchemy.orm import configure_mappers
configure_mappers()

# DB ENV VARIABLES
MYSQL_USER = config("MYSQL_USER")
MYSQL_PASSWORD = config("MYSQL_PASSWORD")
MYSQL_SERVER = config('MYSQL_SERVER')
MYSQL_PORT = config('MYSQL_PORT')
MYSQL_DATABASE = config("MYSQL_DATABASE")
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_SERVER}:{MYSQL_PORT}/{MYSQL_DATABASE}"

# CREATE DATABASE ENGINE & SESSION
try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_recycle=3600)
    logger.info("Database Engine created successfully.")
except Exception as e:
    logger.error(f"Error creating database engine: {e}", exc_info=True)
    raise # Re-raise the exception to prevent app startup if DB is unavailable
    
SessionLocal = sessionmaker(
    autocommit = False,
    autoflush=False,
    bind=engine

)
logger.info("Database session factory created.")

# --- FastAPI Dependency ---
def get_db():
    """
    Dependency that provides a SQLAlchemy database session per request.
    Ensures the session is closed afterwards.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error during database session: {e}", exc_info=True)
        db.rollback()
        raise # Re-raise the exception to be handled by FastAPI error handlers
    finally:
        db.close()
        

# --- Function for Standalone Sessions (Celery, Scripts) ---
def get_standalone_session() -> sessionmaker:
    """
    Creates and returns a new standalone SQLAlchemy Session.
    The caller is responsible for closing the session.
    """
    return SessionLocal()