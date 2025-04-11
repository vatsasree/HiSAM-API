import logging
import os
import shutil
import imagesize
from uuid import uuid4, UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from src.api import deps
from src.database import crud, models, schemas
# from src.core.config import settings
from decouple import config
from src.worker.tasks import process_image_task # Import the Celery task

logger = logging.getLogger(config('LOGGER_NAME'))
router = APIRouter()

MAX_FILES = 100
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

@router.post(
    "/",
    response_model=schemas.ProcessResponse,
    status_code=status.HTTP_202_ACCEPTED, # 202 Accepted: request accepted, processing started
    summary="Submit images for processing",
    description="Upload one or more image files. A job ID is returned, and processing starts in the background.",
)
async def submit_processing_job(
    *,
    files: List[UploadFile] = File(..., description=f"Image files to process (max {MAX_FILES} files, max {MAX_FILE_SIZE_MB}MB each)"),
    db: Session = Depends(deps.get_db),
    current_token: models.ApiToken = Depends(deps.get_current_valid_api_token), # Enforce valid token
):
    """
    Handles image uploads, creates job/document records, and dispatches tasks.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files were uploaded.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"Too many files. Maximum allowed is {MAX_FILES}.")

    job_uuid = uuid4() # Generate UUID for the job
    saved_file_paths = []
    doc_create_schemas = []

    # --- 1. Create Job Directory ---
    job_upload_dir = Path(config('UPLOAD_DIR')) / str(job_uuid)
    try:
        job_upload_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create upload directory {job_upload_dir}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create storage directory for the job.")

    # --- 2. Save Uploaded Files & Prepare Document Records ---
    for file in files:
        if file.size > MAX_FILE_SIZE_BYTES:
             # Clean up already saved files for this job if one file is too large
            shutil.rmtree(job_upload_dir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{file.filename}' exceeds the maximum size limit of {MAX_FILE_SIZE_MB}MB."
            )

        # Basic content type check (can be spoofed, add more robust checks if needed)
        if not file.content_type or not file.content_type.startswith("image/"):
            shutil.rmtree(job_upload_dir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File '{file.filename}' has an unsupported content type: {file.content_type}. Only images are allowed."
            )

        # Sanitize filename (important for security)
        safe_filename = secure_filename(file.filename) # Use a utility for this
        if not safe_filename:
             safe_filename = f"upload_{uuid4().hex}" # Generate safe name if original is bad

        relative_path = Path(str(job_uuid)) / safe_filename
        destination_path = Path(config('UPLOAD_DIR')) / relative_path

        try:
            logger.debug(f"Saving file '{file.filename}' to '{destination_path}'")
            with open(destination_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_file_paths.append(str(destination_path)) # Store full path temporarily if needed
            # Prepare schema for DB creation, store relative path
            width, height = imagesize.get(destination_path)
            doc_create_schemas.append(schemas.DocumentRecordBase(
                doc_path=str(relative_path), 
                width=width, 
                height=height
            ))
        except Exception as e:
            logger.error(f"Failed to save uploaded file '{file.filename}': {e}", exc_info=True)
            # Clean up potentially partially saved files and directory
            shutil.rmtree(job_upload_dir, ignore_errors=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not save file: {safe_filename}")
        finally:
            await file.close() # Ensure file pointer is closed

    if not doc_create_schemas:
         # Should not happen if validation passed, but good safety check
         shutil.rmtree(job_upload_dir, ignore_errors=True)
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid files processed.")


    # --- 3. Create Job and Document Records in DB within a transaction ---
    try:
        # Create the main job record
        job_create = schemas.JobRecordCreate(api_token_id=current_token.token_id)
        # We need to manually create the JobRecord object with the generated UUID bytes
        db_job = models.JobRecord(
            job_id=job_uuid.bytes,
            api_token_id=job_create.api_token_id,
            status=models.JobStatus.QUEUED # Initial status
        )
        db.add(db_job)
        # Flush to get the job_id assigned if needed, but commit handles it
        # db.flush() # Not strictly needed here before commit

        # Create document records linked to the job
        db_documents = []
        for doc_schema in doc_create_schemas:
            db_doc = models.DocumentRecord(
                job_id=job_uuid.bytes, # Link using the generated job_id bytes
                doc_path=doc_schema.doc_path,
                width=doc_schema.width, 
                height=doc_schema.height,
                status=models.JobStatus.QUEUED
            )
            db_documents.append(db_doc)

        db.add_all(db_documents)
        db.commit() # Commit JobRecord and DocumentRecords together

        # Refresh to get auto-generated IDs (like doc_id)
        for doc in db_documents:
            db.refresh(doc)
        db.refresh(db_job) # Refresh job as well

        logger.info(f"Job {job_uuid} created with {len(db_documents)} documents for token ID {current_token.token_id}.")

    except Exception as e:
        db.rollback() # Rollback transaction on any DB error
        logger.error(f"Database error creating job {job_uuid}: {e}", exc_info=True)
        # Clean up saved files if DB operation failed
        shutil.rmtree(job_upload_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create job record in database.")

    # --- 4. Dispatch Celery Tasks ---
    task_ids = []
    for db_doc in db_documents:
        try:
            print(f'\n\n{db_doc = } - {db_doc.doc_id =} process_image_task.apply_async\n\n')
            # Send task with the DocumentRecord primary key (doc_id)
            task = process_image_task.apply_async(
                args=[db_doc.doc_id],
                queue='image_processing_queue' # Ensure task goes to the correct queue
            )
            print('\n\n task send to process_image_task completed \n\n')
            task_ids.append(task.id)
            logger.info(f"Dispatched task {task.id} for document ID {db_doc.doc_id} (Job {job_uuid})")
        except Exception as e:
            # This is problematic: DB records exist but task dispatch failed.
            # Implement retry logic or mark the document/job as failed immediately.
            logger.error(f"Failed to dispatch Celery task for document ID {db_doc.doc_id} (Job {job_uuid}): {e}", exc_info=True)
            # Attempt to mark the specific document as FAILED in DB
            try:
                crud.update_document_status_and_result(
                    db, doc_id=db_doc.doc_id, status=models.JobStatus.FAILED, error_message="Failed to queue task"
                )
                # Optionally, check if this failure should mark the whole job as FAILED
            except Exception as db_err:
                logger.error(f"Failed to update document {db_doc.doc_id} status to FAILED after task dispatch error: {db_err}")
            # Consider how to report this back to the user - maybe a partial success?
            # For simplicity now, we'll still return 202 but log the error.

    # Return the Job ID to the client
    return schemas.ProcessResponse(
        job_id=job_uuid,
        message="Job accepted for processing.",
        document_count=len(db_documents)
    )

# --- Helper Functions ---
from pathlib import Path
import re

def secure_filename(filename: str) -> str:
    """
    Sanitizes a filename to prevent directory traversal and invalid characters.
    Basic implementation, consider a more robust library if needed.
    """
    # Remove directory traversal attempts
    filename = filename.replace("../", "").replace("..\\", "")
    # Keep only alphanumeric, underscore, hyphen, dot
    filename = re.sub(r'[^\w\.\-]', '_', filename)
    # Collapse multiple underscores/hyphens
    filename = re.sub(r'[-_]+', '_', filename).strip('_')
    # Limit length (optional)
    max_len = 100
    if len(filename) > max_len:
         name, ext = os.path.splitext(filename)
         filename = name[:max_len - len(ext) -1] + ext

    # Handle edge cases like empty filename or just "."
    if not filename or filename == '.':
        return "" # Or generate a random name

    return filename