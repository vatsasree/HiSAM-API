import time
import logging
import json
from pathlib import Path
from uuid import UUID as PyUUID
from celery import shared_task
from sqlalchemy.orm import Session
from typing import Optional
from src.database.session import get_standalone_session # Use standalone session for tasks
from src.database import crud, models, schemas
from decouple import config
# from src.core.config import settings

logger = logging.getLogger(config('LOGGER_NAME') + ".tasks") # Specific logger for tasks

@shared_task(bind=True, max_retries=3, default_retry_delay=60) # Example retry config
def process_image_task(self, document_id: int):
    """
    Celery task to simulate image processing for a single document.
    """
    logger.info(f"[Task ID: {self.request.id}] Processing document ID: {document_id}")

    session: Session = get_standalone_session()
    db_doc: Optional[models.DocumentRecord] = None

    try:
        # --- 1. Get Document Record ---
        db_doc = crud.document.get(session, id=document_id)
        if not db_doc:
            logger.error(f"[Task ID: {self.request.id}] Document ID {document_id} not found in database. Aborting task.")
            # No retry needed if the document doesn't exist
            return {"status": "FAILED", "error": "Document not found"}

        job_id_uuid = db_doc.job_uuid # Get UUID for logging
        logger.info(f"[Task ID: {self.request.id}] Found Document ID {document_id} for Job ID {job_id_uuid}")

        # --- Check if already processed or failed ---
        if db_doc.status in [models.JobStatus.COMPLETED, models.JobStatus.FAILED]:
            logger.warning(f"[Task ID: {self.request.id}] Document ID {document_id} already in terminal state: {db_doc.status}. Skipping.")
            return {"status": db_doc.status.value, "message": "Already processed"}

        # --- 2. Update Status to PROCESSING ---
        crud.document.update_status_and_result(
            session, doc_id=document_id, status=models.JobStatus.PROCESSING
        )
        logger.info(f"[Task ID: {self.request.id}] Document ID {document_id} status set to PROCESSING.")

        # --- 3. Simulate Image Processing ---
        # Construct the full path to the image file
        image_path = Path(config('UPLOAD_DIR')) / db_doc.doc_path
        logger.info(f"[Task ID: {self.request.id}] Simulating processing for file: {image_path}")

        if not image_path.exists():
             logger.error(f"[Task ID: {self.request.id}] Image file not found at path: {image_path}. Marking as FAILED.")
             crud.document.update_status_and_result(
                 session, doc_id=document_id, status=models.JobStatus.FAILED, error_message="Image file not found"
             )
             check_and_update_job_status(session, db_doc.job_id) # Update parent job status
             return {"status": "FAILED", "error": "Image file not found"}

        # *** Replace this sleep with actual image processing code ***
        time.sleep(2)
        # *** ---------------------------------------------------- ***

        # Simulate successful processing output (JSON string)
        output_data = {
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file_path": str(db_doc.doc_path),
            "result": "Simulated processing successful",
            "dimensions": {"width": 640, "height": 480} # Example data
        }
        output_json = json.dumps(output_data)

        # --- 4. Update Status to COMPLETED with results ---
        crud.document.update_status_and_result(
            session, doc_id=document_id, status=models.JobStatus.COMPLETED, output=output_json
        )
        logger.info(f"[Task ID: {self.request.id}] Document ID {document_id} processing COMPLETED.")

        # --- 5. Check and Update Parent Job Status ---
        check_and_update_job_status(session, db_doc.job_id)

        return {"status": "COMPLETED", "doc_id": document_id, "output_preview": output_data.get("result")}

    except Exception as e:
        logger.error(f"[Task ID: {self.request.id}] Error processing document ID {document_id}: {e}", exc_info=True)
        session.rollback() # Rollback any partial changes from this attempt

        if db_doc: # If we managed to fetch the document
             try:
                 # Update status to FAILED in DB
                 crud.document.update_status_and_result(
                     session, doc_id=document_id, status=models.JobStatus.FAILED, error_message=str(e)
                 )
                 logger.info(f"[Task ID: {self.request.id}] Document ID {document_id} status set to FAILED.")
                 # Update parent job status after marking doc as failed
                 check_and_update_job_status(session, db_doc.job_id)
             except Exception as update_err:
                 logger.error(f"[Task ID: {self.request.id}] CRITICAL: Failed to update document {document_id} status to FAILED after error: {update_err}", exc_info=True)
                 session.rollback() # Rollback the status update attempt

        # Use Celery's retry mechanism for transient errors
        try:
            # self.retry(exc=e) # Pass exception to retry
            # For this example, let's just mark as failed without retry
             logger.warning(f"[Task ID: {self.request.id}] Task for doc ID {document_id} failed permanently after error.")
             return {"status": "FAILED", "error": str(e)}
        except Exception as retry_exc: # Catch potential MaxRetriesExceededError if retry is used
            logger.error(f"[Task ID: {self.request.id}] Task for doc ID {document_id} failed after retries: {retry_exc}")
            return {"status": "FAILED", "error": f"Failed after retries: {str(e)}"}

    finally:
        session.close() # Ensure session is always closed
        logger.debug(f"[Task ID: {self.request.id}] DB Session closed for doc ID {document_id}")


def check_and_update_job_status(session: Session, job_id_bytes: bytes):
    """
    Checks the status of all documents within a job and updates the parent
    JobRecord's status if all documents are completed or if any have failed.
    """
    try:
        job_uuid = PyUUID(bytes=job_id_bytes) # For logging
        logger.debug(f"Checking overall status for Job ID: {job_uuid}")
        document_statuses = crud.document.get_job_document_statuses(session, job_id_bytes=job_id_bytes)

        if not document_statuses:
            logger.warning(f"No documents found for Job ID: {job_uuid} during status check. Cannot update job status.")
            return

        final_job_status = None
        if all(status == models.JobStatus.COMPLETED for status in document_statuses):
            final_job_status = models.JobStatus.COMPLETED
        elif any(status == models.JobStatus.FAILED for status in document_statuses):
             # If any document failed, the whole job is marked as FAILED
             final_job_status = models.JobStatus.FAILED
        # Optional: Could add logic for PARTIALLY_COMPLETED if needed
        # elif all(status in [models.JobStatus.COMPLETED, models.JobStatus.FAILED] for status in document_statuses):
        #     final_job_status = models.JobStatus.FAILED # Or a custom partial status

        if final_job_status:
            db_job = session.get(models.JobRecord, job_id_bytes) # Efficient lookup by PK
            if db_job and db_job.status != final_job_status:
                logger.info(f"Updating Job ID {job_uuid} status to {final_job_status}")
                crud.job.update_status(session, db_obj=db_job, status=final_job_status)
            elif not db_job:
                logger.error(f"Job ID {job_uuid} (bytes: {job_id_bytes.hex()}) not found during final status update check.")

    except Exception as e:
        # Log error but don't let it crash the original task flow
        logger.error(f"Error checking/updating overall job status for job_id_bytes {job_id_bytes.hex()}: {e}", exc_info=True)
        session.rollback() # Rollback potential failed job status update


# Example of a scheduled cleanup task (add to celery_app includes and beat_schedule if used)
# from datetime import datetime, timedelta, timezone
# @shared_task
# def cleanup_task():
#     logger.info("Running scheduled cleanup task...")
#     session = get_standalone_session()
#     try:
#         # Example: Delete jobs older than 30 days that are completed or failed
#         cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
#         stmt = delete(models.JobRecord).where(
#             models.JobRecord.status.in_([models.JobStatus.COMPLETED, models.JobStatus.FAILED]),
#             models.JobRecord.updated_at < cutoff_date
#         )
#         result = session.execute(stmt)
#         session.commit()
#         logger.info(f"Cleanup task deleted {result.rowcount} old jobs.")
#     except Exception as e:
#         logger.error(f"Error during cleanup task: {e}", exc_info=True)
#         session.rollback()
#     finally:
#         session.close()
