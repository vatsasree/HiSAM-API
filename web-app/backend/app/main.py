from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, UploadFile, BackgroundTasks
from uuid import uuid4
from app.utils import utils
from enum import Enum
import uvicorn

BASE_IMAGE_SAVE_PATH = '/data3/amalj/template_api/store/user_files'
class PredictionType(Enum):
    polygons = "polygons"
    scribbles = "scribbles"

from app.utils.logger import setup_logger
logger = setup_logger(name='line_parser_logger', log_file='store/log_files/parsing_records.log')


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB on startup
    # create_tables()
    utils.create_folders()
    yield
    # Things to do after starting the app
    logger.info(f'APP Started')
app = FastAPI()


@app.get('/health')
def health_check():
    return {'status': 'running'}

@app.post('/predict')
async def predict(
    prediction_type: PredictionType, 
    image: UploadFile, 
    token: str, 
    background_tasks: BackgroundTasks
):
    uuid = uuid4()
    
    # AUTHENTICATION
    authorized, privilages = await utils.authorize_token(uuid, token)
    if not authorized:
        print('not authorized')
        logger.info(f'Unauthorized request from token={token} , uuid={uuid}')
        return {
            'result': 'Unauthorized Request, this incident is reported.'
        }
    else:
        print('authorized')
        # If user is authenticated
        try:
            # image_save_path = await utils.save_image(uuid, BASE_IMAGE_SAVE_PATH, image)
            pass
        except Exception as error:
            logger.error("")

        background_tasks.add_task(utils.process_image, uuid)
        return {'result': f'{uuid} - Results will be available shortly.'}


@app.post('/check_status')
async def predict(
    token: str, 
    uuid: str
):
    # AUTHENTICATION
    authorized, privilages = await utils.authorize_token(uuid, token)
    if not authorized:
        print('not authorized')
        logger.info(f'Unauthorized request from token={token} , uuid={uuid}')
        return {
            'result': 'Unauthorized Request, this incident is reported.'
        }
    else:
        print('authorized')   
        result = utils.check_processing_status(uuid)
        return {
            'result': result
        }
        
        
        
if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)