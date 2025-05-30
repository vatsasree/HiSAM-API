import logging
import typer
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Setup paths for script execution
import os
import sys
# Add project root to sys.path to allow imports like 'from src.core...'
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print(project_root)
sys.path.insert(0, '/data3/amal.joseph/template_api/web-app/backend/')

# from src.core.config import settings # Load settings first
from decouple import config
# from src.logging_config import LOGGING_CONFIG # Use dict config
from src.database.session import get_standalone_session
from src.database import crud, schemas, models
from src.core.security import get_password_hash # We need this if CRUD doesn't handle hashing

# import logging.config
# logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(config('LOGGER_NAME') + ".scripts") # Specific logger

app = typer.Typer()

@app.command()
def main(
    email: str = typer.Option(..., prompt=True, help="User's email address"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=False, help="User's password (min 8 chars)"),
    full_name: str = typer.Option(None, prompt=True, help="User's full name (optional)"),
):
    """
    Creates a new user in the database.
    """
    logger.info(f"Attempting to create user: {email}")

    # Validate password length client-side for better UX
    if len(password) < 5:
        logger.error("Password must be at least 5 characters long.")
        raise typer.Exit(code=1)

    # Use Pydantic schema for validation before hitting DB
    try:
        user_in = schemas.UserCreate(email=email, password=password, full_name=full_name)
    except Exception as e: # Catch Pydantic validation errors
        logger.error(f"Invalid input data: {e}")
        print(f"Error: Invalid input - {e}")
        raise typer.Exit(code=1)

    session: Session = get_standalone_session()
    
    try:
        existing_user = crud.get_user_by_email(session, email=user_in.email)
        if existing_user is not None:
            
            logger.warning(f"User with email '{user_in.email}' already exists.")
            print(f"Error: User with email '{user_in.email}' already exists.")
            raise typer.Exit(code=1)

        logger.info("Creating user...")
        created_user = crud.create_user(session, user=user_in)
        logger.info(f"User '{created_user.email}' (ID: {created_user.user_id}) created successfully.")
        print(f"User '{created_user.email}' created successfully with ID: {created_user.user_id}")

    except IntegrityError as e: # Catch potential race conditions or other DB integrity issues
        session.rollback()
        logger.error(f"Database integrity error creating user {user_in.email}: {e}", exc_info=True)
        print(f"Error: A database error occurred. It's possible the email was registered concurrently.")
        raise typer.Exit(code=1)
    except Exception as e:
        session.rollback()
        logger.error(f"An unexpected error occurred creating user {user_in.email}: {e}", exc_info=True)
        print(f"Error: An unexpected error occurred: {e}")
        raise typer.Exit(code=1)
    finally:
        session.close()
        logger.debug("Database session closed for create_user script.")

if __name__ == "__main__":
    app()