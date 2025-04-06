import logging
import typer
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound

# Setup paths for script execution
import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# from src.core.config import settings
# from src.logging_config import LOGGING_CONFIG
from decouple import config
from src.database.session import get_standalone_session
from src.database import crud, schemas, models
from src.core import security # For token generation/hashing

# Configure logging
# import logging.config
# logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(config('LOGGER_NAME') + ".scripts")

app = typer.Typer(help="Manage User API Tokens.")

def get_user_or_exit(db: Session, email: str) -> models.User:
    """Helper to get user by email or exit if not found."""
    user = crud.get_user_by_email(db, email=email)
    if not user:
        logger.error(f"User with email '{email}' not found.")
        print(f"Error: User with email '{email}' not found.")
        raise typer.Exit(code=1)
    return user

@app.command("create")
def create_token(
    email: str = typer.Option(..., prompt="User Email", help="Email of the user to create token for."),
    # expires_days: Optional[int] = typer.Option(None, help="Number of days until the token expires (optional).")
):
    """
    Create a new API token for a user. The raw token is printed ONCE.
    """
    logger.info(f"Attempting to create token for user: {email}")
    session: Session = get_standalone_session()
    try:
        user = get_user_or_exit(session, email)

    
        raw_token, token_hash = security.generate_and_hash_api_token()
        token_in = schemas.ApiTokenCreate(
            user_id=user.user_id,
            is_active=True,
            token_hash=token_hash
            # Add expiry logic here if needed based on expires_days
        )

        db_token = crud.create_token(session, token=token_in)

        logger.info(f"Token created successfully for user {email} (Token ID: {db_token.token_id}).")
        print("-" * 30)
        print(f"API Token created for user: {user.email}")
        print(f"Token ID: {db_token.token_id}")
        print("IMPORTANT: This is the only time the raw token will be shown.")
        print("Store it securely!")
        print(f"Token: {raw_token}")
        print("-" * 30)

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating token for {email}: {e}", exc_info=True)
        print(f"Error: Could not create token. {e}")
        raise typer.Exit(code=1)
    finally:
        session.close()

'''

FIX THE BELOW LATER
'''

# @app.command("list")
# def list_tokens(
#     email: str = typer.Option(..., prompt="User Email", help="Email of the user whose tokens to list."),
# ):
#     """
#     List active API tokens for a user (never shows raw token or hash).
#     """
#     logger.info(f"Listing tokens for user: {email}")
#     session: Session = get_standalone_session()
#     try:
#         user = get_user_or_exit(session, email)
#         tokens = crud.token.get_multi_by_user(session, user_id=user.user_id, limit=1000) # Get all tokens

#         if not tokens:
#             print(f"No API tokens found for user: {email}")
#             raise typer.Exit()

#         print(f"API Tokens for user: {user.email} (User ID: {user.user_id})")
#         print("-" * 60)
#         print(f"{'ID':<5} {'Active':<8} {'Created At':<22} {'Expires At':<22} {'Last Used':<22}")
#         print("-" * 60)
#         active_count = 0
#         for token in tokens:
#             status = "Yes" if token.is_active else "No"
#             if token.is_active: active_count += 1
#             created = token.created_at.strftime('%Y-%m-%d %H:%M:%S %Z') if token.created_at else "N/A"
#             expires = token.expires_at.strftime('%Y-%m-%d %H:%M:%S %Z') if token.expires_at else "Never"
#             last_used = token.last_used_at.strftime('%Y-%m-%d %H:%M:%S %Z') if token.last_used_at else "Never"
#             print(f"{token.token_id:<5} {status:<8} {created:<22} {expires:<22} {last_used:<22}")

#         print("-" * 60)
#         print(f"Total tokens: {len(tokens)}, Active: {active_count}")

#     except Exception as e:
#         session.rollback() # Just in case, though reads shouldn't modify
#         logger.error(f"Error listing tokens for {email}: {e}", exc_info=True)
#         print(f"Error: Could not list tokens. {e}")
#         raise typer.Exit(code=1)
#     finally:
#         session.close()


# @app.command("deactivate")
# def deactivate_token(
#     email: str = typer.Option(..., prompt="User Email", help="Email of the user whose token(s) to deactivate."),
#     token_id: Optional[int] = typer.Option(None, help="Specific Token ID to deactivate (optional, default: deactivate all)."),
# ):
#     """
#     Deactivate a specific API token or all tokens for a user.
#     """
#     action = f"token ID {token_id}" if token_id else "all tokens"
#     logger.info(f"Attempting to deactivate {action} for user: {email}")
#     session: Session = get_standalone_session()
#     try:
#         user = get_user_or_exit(session, email)

#         if token_id:
#             # Deactivate specific token
#             token_to_deactivate = session.get(models.ApiToken, token_id) # Use session.get for PK lookup
#             if not token_to_deactivate or token_to_deactivate.user_id != user.user_id:
#                 logger.error(f"Token ID {token_id} not found or does not belong to user {email}.")
#                 print(f"Error: Token ID {token_id} not found or does not belong to user {email}.")
#                 raise typer.Exit(code=1)

#             if not token_to_deactivate.is_active:
#                 print(f"Token ID {token_id} is already inactive.")
#                 raise typer.Exit()

#             crud.token.deactivate(session, db_obj=token_to_deactivate)
#             logger.info(f"Token ID {token_id} for user {email} deactivated successfully.")
#             print(f"Token ID {token_id} deactivated successfully.")
#         else:
#             # Deactivate all user tokens
#             count = crud.token.deactivate_all_user_tokens(session, user_id=user.user_id)
#             logger.info(f"Deactivated {count} token(s) for user {email}.")
#             print(f"Deactivated {count} token(s) for user {email}.")

#     except Exception as e:
#         session.rollback()
#         logger.error(f"Error deactivating {action} for {email}: {e}", exc_info=True)
#         print(f"Error: Could not deactivate token(s). {e}")
#         raise typer.Exit(code=1)
#     finally:
#         session.close()


# @app.command("regenerate")
# def regenerate_token(
#     email: str = typer.Option(..., prompt="User Email", help="Email of the user whose token to regenerate."),
#     token_id: int = typer.Option(..., prompt="Token ID", help="The ID of the specific token to regenerate."),
#     deactivate_old: bool = typer.Option(True, help="Deactivate the old token after regenerating."),
# ):
#     """
#     Generates a NEW token and optionally deactivates the specified OLD token.
#     """
#     logger.info(f"Attempting to regenerate token ID {token_id} for user: {email}")
#     session: Session = get_standalone_session()
#     try:
#         user = get_user_or_exit(session, email)

#         # Verify the old token exists and belongs to the user
#         old_token = session.get(models.ApiToken, token_id)
#         if not old_token or old_token.user_id != user.user_id:
#              logger.error(f"Token ID {token_id} not found or does not belong to user {email}.")
#              print(f"Error: Token ID {token_id} not found or does not belong to user {email}.")
#              raise typer.Exit(code=1)

#         # Generate the NEW raw token
#         new_raw_token = security.generate_api_token()
#         token_in = schemas.ApiTokenCreate(user_id=user.user_id, token_str=new_raw_token)

#         # Create the NEW token record
#         new_db_token = crud.token.create(session, obj_in=token_in)
#         logger.info(f"New token (ID: {new_db_token.token_id}) created for user {email}.")

#         # Deactivate the old token if requested
#         if deactivate_old:
#             crud.token.deactivate(session, db_obj=old_token)
#             logger.info(f"Old token ID {token_id} deactivated.")
#             print(f"Old token (ID: {token_id}) has been deactivated.")
#         else:
#              print(f"Old token (ID: {token_id}) remains active.")

#         # Print the NEW token details
#         print("-" * 30)
#         print(f"NEW API Token generated for user: {user.email}")
#         print(f"New Token ID: {new_db_token.token_id}")
#         print("IMPORTANT: This is the only time the new raw token will be shown.")
#         print("Store it securely!")
#         print(f"New Token: {new_raw_token}") # *** Print the raw token ***
#         print("-" * 30)

#     except Exception as e:
#         session.rollback()
#         logger.error(f"Error regenerating token {token_id} for {email}: {e}", exc_info=True)
#         print(f"Error: Could not regenerate token. {e}")
#         raise typer.Exit(code=1)
#     finally:
#         session.close()


if __name__ == "__main__":
    app()
