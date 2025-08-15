import os
import logging
import base64
import mimetypes
from uuid import UUID
import xml.etree.ElementTree as ET
from xml.dom import minidom
from ast import literal_eval
from typing import List, Dict, Any, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from src.api import deps
from src.database import crud, schemas, models # Import models for type hinting

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
    
    # Fetch job details
    db_job = crud.get_job_by_job_id(db=db, job_id_bytes=job_id.bytes)
    
    if not db_job:
        logger.warning(f"Job ID not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    
    # Check if the requesting token owns the job
    if db_job.api_token_id != current_token.token_id:
        logger.warning(f"Token ID {current_token.token_id} attempted to access job {job_id} owned by token ID {db_job.api_token_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
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
    "/tei/{job_id}",
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
    db_job = crud.get_job_by_job_id(db=db, job_id_bytes=job_id.bytes)

    if not db_job:
        logger.warning(f"Job ID not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )
    # Check if the requesting token owns the job (or has permission)
    if db_job.api_token_id != current_token.token_id:
        # maybe later update this so that admin can also view status - if admin dashboadrd is built.
        logger.warning(f"Token ID {current_token.token_id} attempted to access job {job_id} owned by token ID {db_job.api_token_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view the status of this job.",
        )

    # allowed_output_types =  "response_polygon,response_scribble"
    allowed_output_types = get_allowed_output_types(db=db, 
                                                    token_id=current_token.token_id)
    try:
        xml_data = convert_to_tei_p5_format(
            db=db, 
            job_id_bytes=job_id.bytes, 
            allowed_output_types=allowed_output_types
        )
        return Response(content=xml_data, media_type="application/xml")
    except FileNotFoundError as fnf_err:
        logger.error(f"File not found during TEI conversion for job {job_id}: {fnf_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: referenced file not found. {fnf_err}",
        )
    except Exception as err:
        logger.error(f"Error Fetching Job ID: {job_id} with error : {err} ")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching job data or converting to TEI for job ID: {job_id}.",
        )



# --- Helper Functions ---
def get_allowed_output_types(db: Session, token_id: int) -> List[str]:
    priv_objs = crud.get_token_privileges(db=db, token_id=token_id)
    print(f"\n\n PRIV OBJS = {priv_objs} \n\n")
    return [p.name for p in priv_objs]



def convert_to_tei_p5_format(db: Session, job_id_bytes: bytes, allowed_output_types: List[str]):
    db_docs = crud.get_job_document_statuses(db=db, job_id_bytes=job_id_bytes)
    processed_pages_data = []

    print("\n\n")
    for i, doc_record in enumerate(db_docs):
        print(f"{doc_record.doc_path.split('/')[-1]}")
        page_data: Dict[str, Any] = {
            'image_name': doc_record.doc_path.split('/')[-1],
            'width': doc_record.width,
            'height': doc_record.height,
            'polygons': [],
            'paths': [],
            'binary_image_path': None
        }
        
        # Safely parse the output field
        output_dict = {}
        if doc_record.output:
            try:
                output_dict = literal_eval(doc_record.output)
                if not isinstance(output_dict, dict): # Ensure it's a dict
                    logger.warning(f"Parsed output for doc {doc_record.doc_path} is not a dict: {output_dict}")
                    output_dict = {}
            except (ValueError, SyntaxError) as e:
                logger.error(f"Could not parse 'output' field for doc {doc_record.doc_path}: {e}. Content: {doc_record.output}")
                # Continue with empty output_dict or raise error, depending on desired behavior

        # Process polygons for <zone>
        if "response_polygon" in allowed_output_types:
            raw_polygons = output_dict.get('polygons', [])
            if raw_polygons:
                for poly_idx, line_points in enumerate(raw_polygons):
                    try:
                        page_data['polygons'].append({
                            "id": f"line{poly_idx+1}",
                            "points": [tuple(points) for points in line_points]
                        })
                    except TypeError: # If line_points or points are not iterable/structured as expected
                         logger.warning(f"Malformed polygon data in doc {doc_record.doc_path}, polygon {poly_idx+1}: {line_points}")


        # Process scribbles for <path>
        if "response_scribble" in allowed_output_types:
            raw_scribbles = output_dict.get('scribbles', [])
            if raw_scribbles:
                for scribble_idx, path_points in enumerate(raw_scribbles):
                    try:
                        page_data['paths'].append({
                            "id": f"path{scribble_idx+1}",
                            "points": [tuple(points) for points in path_points]
                        })
                    except TypeError:
                        logger.warning(f"Malformed scribble data in doc {doc_record.doc_path}, scribble {scribble_idx+1}: {path_points}")

        # Get path for <binaryObject>
        if "response_binary_map" in allowed_output_types:
            page_data['binary_image_path'] = output_dict.get('binary_map_path')
        print(f'POLYGONS = {page_data.get("polygons")}')
        processed_pages_data.append(page_data)
    print(f"{len(processed_pages_data)} no of results found.")
    print(processed_pages_data[-1]['polygons'])
    print("\n\n")
    xml_data = convert_to_tei(processed_pages_data, allowed_output_types)
    return xml_data


def convert_to_tei(processed_pages_data, allowed_output_types):
    """
    Convert processed pages data to TEI-P5 XML format.

    Args:
        processed_pages_data (list of dict): Each dict contains:
            - image_name (str): filename of the page image
            - width (int or float): width of the image
            - height (int or float): height of the image
            - polygons (list of dict): each with 'id' and 'points' (list of tuples)
            - paths (list of dict): each with 'id' and 'points' (list of tuples)
            - binary_image_path (str or None): filesystem path to binary image to embed
        allowed_output_types (list of str): e.g., ['polygon', 'scribble', 'binary_object']

    Returns:
        str: Pretty-printed TEI-P5 XML string
    """
    # TEI namespace
    TEI_NS = "http://www.tei-c.org/ns/1.0"
    NSMAP = {None: TEI_NS}

    # Create root TEI element
    tei = ET.Element('TEI', xmlns=TEI_NS)
    facs = ET.SubElement(tei, 'facsimile')

    for page in processed_pages_data:
        print(page.get('image_name'))
        # derive xml:id from image_name (without extension)
        page_id = os.path.splitext(page['image_name'])[0]
        surface_attrib = {'xml:id': page_id}
        surface = ET.SubElement(facs, 'surface', surface_attrib)

        # Graphic element
        graphic_attrib = {
            'url': page['image_name'],
            'width': str(page['width']),
            'height': str(page['height'])
        }
        ET.SubElement(surface, 'graphic', graphic_attrib)

        # Polygons as <zone>
        if 'response_polygon' in allowed_output_types and page.get('polygons'):
            for poly in page['polygons']:
                # join points as "x1,y1 x2,y2 ..."
                pts = ' '.join(f"{x},{y}" for x, y in poly['points'])
                zone_attrib = {
                    'xml:id': f"{page_id}_{poly['id']}",
                    'points': pts,
                    'type': 'line'
                }
                ET.SubElement(surface, 'zone', zone_attrib)

        # Scribbles as <path>
        if 'response_scribble' in allowed_output_types and page.get('paths'):
            for path in page['paths']:
                pts = ' '.join(f"{x},{y}" for x, y in path['points'])
                path_attrib = {'points': pts}
                ET.SubElement(surface, 'path', path_attrib)

        # Binary object embedding
        if 'response_binary_map' in allowed_output_types and page.get('binary_image_path'):
            bpath = page['binary_image_path']
            if bpath and os.path.isfile(bpath):
                mime_type, _ = mimetypes.guess_type(bpath)
                mime_type = mime_type or 'application/octet-stream'
                with open(bpath, 'rb') as bf:
                    data = bf.read()
                b64 = base64.b64encode(data).decode('ascii')
                bin_attrib = {'mimeType': mime_type}
                bin_obj = ET.SubElement(surface, 'binaryObject', bin_attrib)
                bin_obj.text = b64

    # Generate pretty XML string
    rough_str = ET.tostring(tei, encoding='utf-8')
    reparsed = minidom.parseString(rough_str)
    return reparsed.toprettyxml(indent="  ")