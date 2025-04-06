import os
import cv2
import cv2
from time import sleep
from pathlib import Path
import pickle
import jwt
from app.core import authHandler
from fastapi import HTTPException, status, Header

BASE_IMAGE_SAVE_PATH = '/data3/amalj/template_api/store/user_files'
DATA_DICT_PATH = '/data3/amalj/template_api/store/user_files/data_dict.pkl'
TOKEN_DB_PATH = '/data3/amalj/template_api/store/user_files/token_db.pkl'

async def save_image(uuid, base_path, image):
    image_save_path = Path(base_path) / f"{uuid}.jpg"
    cv2.imwrite(image_save_path, image)
    return image_save_path




async def authorize_token(uuid, token):
    # AUTH_PREFIX = 'Bearer '
    # auth_exception = HTTPException(
    #     status_code = status.HTTP_401_UNAUTHORIZED, 
    #     detail="Invalid Authentication Credentials"
    # )
    # authorization = Header()
    # # payload = authHandler.decode_jwt(token=authorization[len(AUTH_PREFIX):])
    # if not authorization:
    #     raise auth_exception
    # if not authorization.startswith(AUTH_PREFIX):
    #     raise auth_exception
    
    
    token_db = load_pickle(TOKEN_DB_PATH)
    if token in token_db:
        privilages = {
            'model': ['linetr']
        }
        return True, privilages
    else:
        return False, {}






def create_folders():
    Path(BASE_IMAGE_SAVE_PATH).mkdir(parents=True, exist_ok=True)



def save_pickle(data, path):
    with open(path, 'wb') as f:
        pickle.dump(data, f)
def load_pickle(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    return data
     
async def process_image(uuid):
    uuid = str(uuid)
    if os.path.exists(DATA_DICT_PATH):
        print('exist')
        data_dict = load_pickle(DATA_DICT_PATH)
    else:
        data_dict = {}
        print('not exist')
    data_dict[uuid] = 'Processing'
    save_pickle(data_dict, DATA_DICT_PATH)
    sleep(2)
    data_dict[uuid] = 'Success'
    save_pickle(data_dict, DATA_DICT_PATH)
    
def check_processing_status(uuid):
    data_dict = load_pickle(DATA_DICT_PATH)
    status = data_dict[uuid]
    if status == 'Processing':
        return {'status': 'Processing.  Wait for some time.'}
    elif status == 'Success':
        return {
                'polygons': ['']
            }