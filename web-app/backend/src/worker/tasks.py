import time
import logging
import json
from pathlib import Path
from uuid import UUID as PyUUID
from celery import shared_task
from celery.signals import worker_init
from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session
from typing import Optional
from src.database.session import get_standalone_session # Use standalone session for tasks
from src.database import crud, models, schemas
from decouple import config as env_config
import torch
import cv2
import traceback

logger = logging.getLogger(env_config('LOGGER_NAME') + ".tasks") # Specific logger for tasks
celery_logger = get_task_logger(__name__)
model_config = {
    "model_type": "vit_l",
    "checkpoint": "/home/sreevatsa.s/HiSAM-API/store/model_files/pretrained_checkpoint/hi_sam_l.pth",
    "device": "cuda:0",
    "devices": [4, 5, 6, 7],
    "total_points": 1500,
    "batch_points": 100,
    "layout_thresh": 0.5,
    "convert_to_image": False,
    "convert_to_deskew_image": False,
    "seed": 42,
    "use_fgmask": False,
    "eval": True,
    "eval_out_file": "output.jsonl",
    "existing_fgmask_input": "./datasets/HierText/val_fgmask/",
    "output": "./demo_output",
    "attn_layers": 1,
    "batch_inference_size": 1,
    "hier_det": True,
    "input": None,
    "input_pdf": None,
    "input_size": [1024, 1024],
    "number_of_gpus": 8,
    "prompt_len": 12,
    "vis": False,
    "num_workers": 1,
    "max_cores": 128,
    "batch_size": 1
}

## --- Import your inference code ---
try:
    # from src.ml_models.LineTR.infer_new import Infer
    from src.ml_models.hisam_CS.detectors.models.hisam_cs_infer import HiSAMDetector as Infer
    MODEL_LOADED = True
    # --- Initialize the Model ONCE per worker process ---
    inference_model = Infer(model_config)
    logger.info("Inference model loaded successfully in worker process.")
except ImportError as e:
    logger.error(f"Failed to import inference code: {e}", exc_info=True)
    MODEL_LOADED = False
    inference_model = None # Ensure it's defined even on failure
except Exception as e:
    # Catch potential errors during model initialization (e.g., file not found, GPU issue)
    logger.error(f"Failed to initialize inference model: {e}", exc_info=True)
    MODEL_LOADED = False
    inference_model = None

@worker_init.connect
def on_worker_init(sender, **kwargs):
    logger.info(f"Worker {sender} initialized with CUDA: {torch.cuda.is_available()}")

@shared_task(bind=True, max_retries=3, default_retry_delay=60) # Example retry config
def process_image_task(self, doc_id: int):
    """
    Celery task to simulate image processing for a single document.
    """
    logger.info(f"[Task ID: {self.request.id}] Processing document ID: {doc_id}")
   
    # --- Check if model loaded correctly during worker startup ---
    task_id_str = f"[Task ID: {self.request.id} Doc ID: {doc_id}]" # For logging
    logger.info(f"{task_id_str} Task received.")
    # if not MODEL_LOADED or inference_model is None:
    #     logger.error(f"{task_id_str} Inference model not available. Aborting.")
    #     # Optionally update DB to FAILED here, but raising prevents retries
    #     # We don't want to retry if the fundamental model isn't loaded.
    #     raise RuntimeError("Inference model could not be loaded in worker.")
    session: Session = get_standalone_session()
    db_doc: Optional[models.DocumentRecord] = None

    try:
        # --- 1. Get Document Record ---
        db_doc = crud.get_document_by_id(session, doc_id=doc_id)
        try:
            mark_job_processing_started(session, job_id_bytes=db_doc.job_id)
        except:
            logger.error(f"[Task ID: {self.request.id}] Marking JobId: {db_doc.job_id} as Processing failed. Document ID: {doc_id}")
        if not db_doc:
            logger.error(f"[Task ID: {self.request.id}] Document ID {doc_id} not found in database. Aborting task.")
            # No retry needed if the document doesn't exist
            return {"status": "FAILED", "error": "Document not found"}

        job_id_uuid = db_doc.job_id
        logger.info(f"[Task ID: {self.request.id}] Found Document ID {doc_id} for Job ID {job_id_uuid}")

        # --- Check if already processed or failed ---
        if db_doc.status in [models.JobStatus.COMPLETED, models.JobStatus.FAILED]:
            logger.warning(f"[Task ID: {self.request.id}] Document ID {doc_id} already in terminal state: {db_doc.status}. Skipping.")
            return {"status": db_doc.status.value, "message": "Already processed"}

        # --- 2. Update Document Status to PROCESSING ---
        crud.update_document_status_and_result(
            session, doc_id=doc_id, status=models.JobStatus.PROCESSING
        )
        logger.info(f"[Task ID: {self.request.id}] Document ID {doc_id} status set to PROCESSING.")
        # --- 2.1 Update Job Status to PROCESSING ---


        # --- 3. Perform Inference ---
        # Construct the full path to the image file saved by the API endpoint
        image_path = Path(env_config('UPLOAD_DIR')) / db_doc.doc_path
        logger.info(f"{task_id_str} Starting inference for file: {image_path}")

        if not image_path.exists():
            logger.error(f"{task_id_str} Image file not found at path: {image_path}. Marking as FAILED.")
            crud.update_document_status_and_result(
                session, doc_id=doc_id, status=models.JobStatus.FAILED, error_message="Image file not found"
            )
            status = check_and_update_job_status(session, db_doc.job_id) # Update parent job status
            raise FileNotFoundError(f"Image file not found: {image_path}") # Raise error to go to except block

        # === Call your inference code ===
        
        output_data = inference_model.detect(image_path)
        print('output_data',output_data)
        logger.info(f"output_data {output_data}")
        output_json = json.dumps(output_data)
        
        # --- 4. Update Status to COMPLETED with results ---
        crud.update_document_status_and_result(
            session, doc_id=doc_id, status=models.JobStatus.COMPLETED, output=output_json
        )
        logger.info(f"[Task ID: {self.request.id}] Document ID {doc_id} processing COMPLETED.")

        # --- 5. Check and Update Parent Job Status ---
        status = check_and_update_job_status(session, db_doc.job_id)
        if not status:
            time.sleep(60)
            status = check_and_update_job_status(session, db_doc.job_id)
            

        return {"status": "COMPLETED", "doc_id": doc_id, "output_preview": output_data}

    except Exception as e:
        torch.cuda.empty_cache()  # Clear GPU memory on failure
        logger.error(f"[Task ID: {self.request.id}] Error processing document ID {doc_id}: {e}", exc_info=True)
        print(traceback.format_exc())
        logger.error(traceback.format_exc())
        session.rollback() # Rollback any partial changes from this attempt

        if db_doc: # If we managed to fetch the document
             try:
                 # Update status to FAILED in DB
                 crud.update_document_status_and_result(
                     session, doc_id=doc_id, status=models.JobStatus.FAILED, error_message=repr(e) # str(e)
                 )
                 logger.info(f"[Task ID: {self.request.id}] Document ID {doc_id} status set to FAILED.")
                 # Update parent job status after marking doc as failed
                 status = check_and_update_job_status(session, db_doc.job_id)
             except Exception as update_err:
                 logger.error(f"[Task ID: {self.request.id}] CRITICAL: Failed to update document {doc_id} status to FAILED after error: {update_err}", exc_info=True)
                 session.rollback() # Rollback the status update attempt

        # Use Celery's retry mechanism for transient errors
        try:
            # self.retry(exc=e) # Pass exception to retry
            logger.warning(f"[Task ID: {self.request.id}] Task for doc ID {doc_id} retrying after error.")
            raise self.retry(exc=e, countdown=5)
        except self.MaxRetriesExceededError:
            logger.error(f"[Task ID: {self.request.id}] Max retries exceeded for doc ID {doc_id}")
            crud.update_document_status_and_result(
                session, doc_id=doc_id, status=models.JobStatus.FAILED, error_message='Max retries exceeded.' # str(e)
            )
            return {"status": "FAILED", "error": f"Failed after retries: {str(e)}"}
        except Exception as retry_exc:
            logger.error(f"[Task ID: {self.request.id}] Task for doc ID {doc_id} failed after retries: {retry_exc}")
            crud.update_document_status_and_result(
                session, doc_id=doc_id, status=models.JobStatus.FAILED, error_message='Failed after retries.' # str(e)
            )
            return {"status": "FAILED", "error": f"Failed after retries: {str(e)}"}

    finally:
        session.close() # Ensure session is always closed
        logger.debug(f"[Task ID: {self.request.id}] DB Session closed for doc ID {doc_id}")


def mark_job_processing_started(session: Session, job_id_bytes: bytes):
    try:
        job_uuid = PyUUID(bytes=job_id_bytes) # For logging
        logger.info(f"Processing started by worker for  Job ID: {job_uuid}")
        crud.update_job_status(session, job_id_bytes=job_id_bytes, status=models.JobStatus.PROCESSING)
    except Exception as e:
        logger.error(f"Error updating job status to processing for job_id_bytes {job_id_bytes.hex()}: {e}", exc_info=True)
        session.rollback() # Rollback potential failed job status update

def check_and_update_job_status(session: Session, job_id_bytes: bytes):
    """
    Checks the status of all documents within a job and updates the parent
    JobRecord's status if all documents are completed or if any have failed.
    """
    try:
        job_uuid = PyUUID(bytes=job_id_bytes) # For logging
        logger.debug(f"Checking overall status for Job ID: {job_uuid}")
        document_statuses = crud.get_job_document_statuses(session, job_id_bytes=job_id_bytes)

        if not document_statuses:
            logger.warning(f"No documents found for Job ID: {job_uuid} during status check. Cannot update job status.")
            return
                # Check if all documents have reached a final state (COMPLETED or FAILED)
        all_docs_finished = all(status.status in [models.JobStatus.COMPLETED, models.JobStatus.FAILED] 
                               for status in document_statuses)
        if all_docs_finished:
            final_job_status = None
            if all(status.status == models.JobStatus.COMPLETED for status in document_statuses):
                final_job_status = models.JobStatus.COMPLETED
            elif all(status.status == models.JobStatus.FAILED for status in document_statuses):
                final_job_status = models.JobStatus.FAILED
            elif any(status.status == models.JobStatus.FAILED for status in document_statuses):
                # If some documents failed but others succeeded, mark as COMPLETED_WITH_ERRORS
                final_job_status = models.JobStatus.COMPLETED_WITH_ERRORS

            if final_job_status:
                db_job = crud.get_job_by_job_id(session, job_id_bytes=job_id_bytes)
                if db_job and db_job.status != final_job_status:
                    logger.info(f"Updating Job ID {job_uuid} status to {final_job_status}")
                    crud.update_job_status(session, job_id_bytes=job_id_bytes, status=final_job_status)
                elif not db_job:
                    logger.error(f"Job ID {job_uuid} (bytes: {job_id_bytes.hex()}) not found during final status update check.")
            return True
        else:
            return False
    except Exception as e:
        # Log error but don't let it crash the original task flow
        logger.error(f"Error checking/updating overall job status for job_id_bytes {job_id_bytes.hex()}: {e}", exc_info=True)
        session.rollback() # Rollback potential failed job status update
        return False


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



""""
celery -A src.worker.celery_app worker --loglevel=INFO -Q image_processing_queue -c 4 —pool=gevent

Have to use the spawing method as gevent.
Reason - https://stackoverflow.com/questions/45459205/keras-predict-not-returning-inside-celery-task

Prefork would leads to the tensor operations gettings stuck.
Threads would works for single task, but when there are many tasks, 
    eventhough it would run without getting stuck, it would fail as the cuda context is shared by threads.



"""