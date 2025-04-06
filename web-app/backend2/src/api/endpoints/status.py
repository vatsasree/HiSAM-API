import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api import deps
from src.database import crud, schemas, models # Import models for type hinting

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get(
    "/{job_id}",
    response_model=schemas.JobStatusResponse,
    summary="Get job status and results",
    description="Retrieve the current status and processing results (if completed) for a given job ID.",
)
async def get_job_status(
    job_id: UUID, # Path parameter converted to UUID
    db: Session = Depends(deps.get_db),
    # Optional: Require authentication to view status
    current_token: models.ApiToken = Depends(deps.get_current_valid_api_token),
):
    """
    Fetches the job details from the database based on the provided job_id.
    """
    logger.info(f"Status requested for job ID: {job_id} by token ID: {current_token.token_id}")

    # Fetch the job using the specific CRUD method that loads documents
    # job_id_bytes = UUID(bytes=job_id)
    db_job = crud.get_job_by_job_id(db=db, job_id_bytes=job_id.bytes)

    if not db_job:
        logger.warning(f"Job ID not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    # Optional: Check if the requesting token owns the job (or has permission)
    # if db_job.api_token_id != current_token.token_id:
    #     # Depending on requirements, you might allow any authenticated user
    #     # or restrict to the owner or specific admin roles.
    #     logger.warning(f"Token ID {current_token.token_id} attempted to access job {job_id} owned by token ID {db_job.api_token_id}")
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="You do not have permission to view the status of this job.",
    #     )

    # Pydantic schema will handle the conversion and serialization including nested documents
    return schemas.JobStatusResponse(job=db_job)
