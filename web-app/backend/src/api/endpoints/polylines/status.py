import os
import logging
import base64
import mimetypes
from uuid import UUID
import xml.etree.ElementTree as ET
from xml.dom import minidom
from ast import literal_eval
from typing import List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi import status as http_status
from sqlalchemy.orm import Session

from src.api import deps
from src.database import crud, schemas, models # Import models for type hinting
from src.worker.tasks import check_and_update_job_status

from fastapi.responses import JSONResponse
import json

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{job_id}",
    response_model=schemas.JobStatusResponse,
    summary="Get job status",
    description="Retrieve the current status and processing results (if completed) for a given job ID.",
)
async def get_job_status(
    job_id: UUID,  # Path parameter converted to UUID
    db: Session = Depends(deps.get_db),
    current_token: models.ApiToken = Depends(deps.get_current_valid_api_token),
):
    """
    Fetches the job details from the database based on the provided job_id.
    """
    logger.info(f"Status requested for job ID: {job_id} by token ID: {current_token.token_id}")
    # check if job is completed really and update it if completed_with_errors
    # sometimes, if job is completed with some failures, the status was not updated as COMPLETED_WITH_ERRORS
    job_status = check_and_update_job_status(db, job_id_bytes=job_id.bytes)
    if job_status:
        logger.info(f"For Job {job_id}, status updated.")
    # Fetch job details
    db_job = crud.get_job_by_job_id(db=db, job_id_bytes=job_id.bytes)
    
    if not db_job:
        logger.warning(f"Job ID not found: {job_id}")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    
    # Check if the requesting token owns the job
    if db_job.api_token_id != current_token.token_id:
        logger.warning(f"Token ID {current_token.token_id} attempted to access job {job_id} owned by token ID {db_job.api_token_id}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view the status of this job.",
        )
    
    # Fetch the documents related to the job
    db_docs = crud.get_job_document_statuses(db=db, job_id_bytes=job_id.bytes)
    
    # Create response data
    documents_data = [
        schemas.DocumentStatusResponse(doc_path=doc.doc_path, status=doc.status)
        for doc in db_docs
    ]
    
    # Format the response to match the desired structure
    response_data = {
        "job_id": str(job_id),  # Convert UUID to string if needed
        "status": db_job.status,  # The status from the db_job
        "documents": documents_data
    }
    
    return response_data

@router.get(
    "/hisam_result/{job_id}",
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
    # check if job is completed really and update it if completed_with_errors
    # sometimes, if job is completed with some failures, the status was not updated as COMPLETED_WITH_ERRORS
    status = check_and_update_job_status(db, job_id_bytes=job_id.bytes)
    if status:
        logger.info(f"For Job {job_id}, status updated.")
    db_job = crud.get_job_by_job_id(db=db, job_id_bytes=job_id.bytes)
    if not db_job:
        logger.warning(f"Job ID not found: {job_id}")
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    # Check if the requesting token owns the job (or has permission)
    if db_job.api_token_id != current_token.token_id:
        # maybe later update this so that admin can also view status - if admin dashboadrd is built.
        logger.warning(f"Token ID {current_token.token_id} attempted to access job {job_id} owned by token ID {db_job.api_token_id}")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view the status of this job.",
        )

    try:
        
        # json_result = convert_to_hisam_format(
        #     db=db,
        #     job_id_bytes=job_id.bytes
        # )
        # print('json_result', json_result)
        # logging.info(f'json_result {json_result}')
        # # return Response(content=xml_data, media_type="application/xml")
        # return {"job_id": str(job_id), "results": json_result}
        json_result = convert_to_hisam_format(db=db, job_id_bytes=job_id.bytes)
        return JSONResponse(
            content={"job_id": str(job_id), "results": json_result}
        )
    except FileNotFoundError as fnf_err:
        logger.error(f"File not found during TEI conversion for job {job_id}: {fnf_err}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: referenced file not found. {fnf_err}",
        )
    except Exception as err:
        logger.error(f"Error Fetching Job ID: {job_id} with error : {err} ")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching job data or converting to TEI for job ID: {job_id}.",
        )


def scale_annotations_with_rescaling_factor(annotation, rescale_factor):
    scaled_annotation = []
    for poly in annotation:
        scaled_poly = []
        for point in poly:
            scaled_point = (int(point[0] / rescale_factor), int(point[1] / rescale_factor))
            scaled_poly.append(scaled_point)
        scaled_annotation.append(scaled_poly)
    return scaled_annotation

# def convert_to_tei_p5_format(db: Session, job_id_bytes: bytes, allowed_output_types: List[str]):
def convert_to_hisam_format(db: Session, job_id_bytes: bytes):
    # db_docs = crud.get_job_document_statuses(db=db, job_id_bytes=job_id_bytes)
    # processed_pages_data = []

    # print("\n\n")
    # for i, doc_record in enumerate(db_docs):
    #     # page_data: Dict[str, Any] = {
    #     #     'image_name': doc_record.doc_path.split('/')[-1],
    #     #     'width': doc_record.width,
    #     #     'height': doc_record.height,
    #     #     'rescale_factor': doc_record.rescale_factor,
    #     #     'polygons': [],
    #     #     'paths': [],
    #     #     'binary_image_path': None
    #     # }
        
    #     # Safely parse the output field
    #     output_dict = {}
    #     if doc_record.output:
    #         try:
    #             output_dict = literal_eval(doc_record.output)
    #             if not isinstance(output_dict, dict): # Ensure it's a dict
    #                 logger.warning(f"Parsed output for doc {doc_record.doc_path} is not a dict: {output_dict}")
    #                 output_dict = {}
    #         except (ValueError, SyntaxError) as e:
    #             logger.error(f"Could not parse 'output' field for doc {doc_record.doc_path}: {e}. Content: {doc_record.output}")
    #             # Continue with empty output_dict or raise error, depending on desired behavior

    #     processed_pages_data.append(page_data)
    # print(f"{len(processed_pages_data)} no of results found.")
    # print(processed_pages_data[-1]['polygons'])
    # print("\n\n")
    # xml_data = convert_to_tei(processed_pages_data, allowed_output_types)
    # return xml_data
    db_docs = crud.get_job_document_statuses(db=db, job_id_bytes=job_id_bytes)
    processed_pages_data = []

    for i, doc_record in enumerate(db_docs):
        output_dict = {}
        if doc_record.output:
            try:
                output_dict = json.loads(doc_record.output)   # ✅ safer and correct for JSON
                logger.info(f"doc_record.output: {doc_record.output}")
                if not isinstance(output_dict, dict):
                    logger.warning(
                        f"Parsed output for doc {doc_record.doc_path} is not a dict: {output_dict}"
                    )
                    output_dict = {}
            except (ValueError, SyntaxError) as e:
                logger.error(
                    f"Could not parse 'output' field for doc {doc_record.doc_path}: {e}. "
                    f"Content: {doc_record.output}"
                )

        page_data = {
            "doc_path": doc_record.doc_path,
            "status": doc_record.status,
            "width": doc_record.width,
            "height": doc_record.height,
            "rescale_factor": doc_record.rescale_factor,
            "output": output_dict,  # keep your inference result dict here
        }

        processed_pages_data.append(page_data)

    logger.info(f"{len(processed_pages_data)} documents found for job {job_id_bytes}")
    return processed_pages_data

