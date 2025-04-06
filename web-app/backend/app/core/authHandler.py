import jwt
from decouple import config
import time

JWT_SECRET = config("JWT_SECRET")
JWT_ALGORITHM = config("JWT_ALGORITHM")

# TODO - change to datetime and timedelta
class AuthHandler(object):
    
    @staticmethod
    def sign_jwt(user_id: int) -> str:
        payload = {
            "user_id": user_id, 
            "expires": time.time() + 3600 #expires in 60mins
        }
        
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token
    
    @staticmethod
    def decode_jwt(token: str) -> dict:
        try:
            decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return  decoded_token if decoded_token["expires"] > time.time() else None
        except:
            print("Unable to decode the token.")
            return None