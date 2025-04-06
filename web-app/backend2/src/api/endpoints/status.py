import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

# Import necessary components
from src.api import deps
from src.database import models, schemas # Need schemas for response, models for deps
# from src.core.config import settings
from decouple import config

# Still need security dependency if authentication is required
from src.core.security import get_current_valid_api_token

logger = logging.getLogger(config('LOGGER_NAME'))
router = APIRouter()

@router.get(
    "/{job_id}",
    response_model=schemas.JobStatusResponse,
    summary="Get job status and results (SIMPLIFIED)",
    description="SIMPLIFIED: Logs request, waits 2s, returns dummy status data for the given job ID.",
)
async def get_job_status_simplified(
    job_id: uuid.UUID, # Keep path parameter
    # Keep authentication dependency
    current_token: models.ApiToken = Depends(deps.get_current_valid_api_token),
    # No database dependency needed: db: Session = Depends(deps.get_db),
):
    """
    SIMPLIFIED Endpoint:
    - Logs the status request for the job ID with the associated token ID.
    - Simulates work with a 2-second delay.
    - Returns a dummy status response without interacting with DB or Celery results.
    """
    logger.info(f"Simplified /status endpoint hit for job ID: {job_id} by token ID: {current_token.token_id}.")

    # Simulate work/delay
    time.sleep(2)

    logger.info(f"Returning dummy status for job ID: {job_id}")

    # Construct dummy response data matching the schema
    # Use the provided job_id in the response for consistency
    dummy_output_example = '{"detail": "Simulated processing result data"}'
    dummy_doc_1 = schemas.DocumentRecordRead(
        doc_id=101,
        job_id=job_id, # Link to the requested job_id
        status=models.JobStatus.COMPLETED, # Hardcode status
        doc_path=f"{job_id}/dummy_image1.jpg",
        output=dummy_output_example,
        error_message=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dummy_doc_2 = schemas.DocumentRecordRead(
        doc_id=102,
        job_id=job_id, # Link to the requested job_id
        status=models.JobStatus.COMPLETED, # Hardcode status
        doc_path=f"{job_id}/dummy_image2.png",
        output=dummy_output_example,
        error_message=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dummy_job = schemas.JobRecordRead(
        job_id=job_id, # Use the requested job_id
        api_token_id=current_token.token_id, # Can use the current token's ID
        status=models.JobStatus.COMPLETED, # Hardcode overall status
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        documents=[dummy_doc_1, dummy_doc_2] # Include dummy documents
    )

    return schemas.JobStatusResponse(job=dummy_job)



# ---------------------------------------------------------------------------------------------------------
# import logging
# from uuid import UUID

# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session

# from src.api import deps
# from src.database import crud, schemas, models # Import models for type hinting

# logger = logging.getLogger(__name__)
# router = APIRouter()

# @router.get(
#     "/{job_id}",
#     response_model=schemas.JobStatusResponse,
#     summary="Get job status and results",
#     description="Retrieve the current status and processing results (if completed) for a given job ID.",
# )
# async def get_job_status(
#     job_id: UUID, # Path parameter converted to UUID
#     db: Session = Depends(deps.get_db),
#     # Optional: Require authentication to view status
#     current_token: models.ApiToken = Depends(deps.get_current_valid_api_token),
# ):
#     """
#     Fetches the job details from the database based on the provided job_id.
#     """
#     logger.info(f"Status requested for job ID: {job_id} by token ID: {current_token.token_id}")

#     # Fetch the job using the specific CRUD method that loads documents
#     db_job = crud.job.get_by_job_id(db=db, job_id=job_id)

#     if not db_job:
#         logger.warning(f"Job ID not found: {job_id}")
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Job with ID '{job_id}' not found.",
#         )

#     # Optional: Check if the requesting token owns the job (or has permission)
#     # if db_job.api_token_id != current_token.token_id:
#     #     # Depending on requirements, you might allow any authenticated user
#     #     # or restrict to the owner or specific admin roles.
#     #     logger.warning(f"Token ID {current_token.token_id} attempted to access job {job_id} owned by token ID {db_job.api_token_id}")
#     #     raise HTTPException(
#     #         status_code=status.HTTP_403_FORBIDDEN,
#     #         detail="You do not have permission to view the status of this job.",
#     #     )

#     # Pydantic schema will handle the conversion and serialization including nested documents
#     return schemas.JobStatusResponse(job=db_job)
