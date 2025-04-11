from fastapi import FastAPI
from src.logging import setup_logger
from decouple import config
from contextlib import asynccontextmanager
from src.api.api import api_router

'''
https://www.youtube.com/watch?v=H9Blu0kWdZE&ab_channel=EricRoby
https://github.com/techwithgio/twg_fastapi

'''


logger = setup_logger(name=config('LOGGER_NAME'), log_file=config('LOG_FILE_PATH'))

# Application Event Handlers
@asynccontextmanager
async def lifespan(app: FastAPI):
    #events to perform on app startup
    # funtion to create folders, if not exists
    logger.info('--- Application Startup ---')
    logger.info(f"Project Name: {config('PROJECT_NAME')}")
    logger.info(f"API V1 Prefix: {config('API_V1_STR')}")
    yield
    #events to perform on app shutdown
    logger.info('--- Application Shutdown ---')
    


app = FastAPI(
    title=config('PROJECT_NAME'), 
    version=config('PROJECT_VERSION'), 
    openapi_url=f"{config('API_V1_STR')}/openapi.json", 
    description=config('PROJECT_DESCRIPTION'), 
    lifespan=lifespan
)

# --- API Routers ---
app.include_router(api_router, prefix=config('API_V1_STR'))

# --- Root Endpoint ---
@app.get("/", tags=["Root"])
async def read_root():
    # check if API is running
    logger.debug("Root endpoint '/' accessed")
    return {
        "message": f"{config('PROJECT_NAME')}",
        "version": config('PROJECT_VERSION'),
    }