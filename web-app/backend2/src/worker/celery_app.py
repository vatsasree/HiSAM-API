import logging
from celery import Celery
from decouple import config
# from src.core.config import settings

# Initialize logging early
logger = logging.getLogger(config('LOGGER_NAME'))
logger.info("Initializing Celery app...")

# Create Celery instance
# The first argument is the name of the current module (__name__)
# The 'broker' and 'backend' arguments specify the URLs for Redis.
# The 'include' argument lists modules where Celery should look for tasks.
celery_app = Celery(
    "image_worker",
    broker=config('CELERY_BROKER_URL'),
    backend=config('CELERY_RESULT_BACKEND'),
    include=["src.worker.tasks"] # List of modules containing tasks
)

# Optional Celery configuration settings
# See Celery documentation for more options:
# https://docs.celeryq.dev/en/stable/userguide/configuration.html
celery_app.conf.update(
    task_serializer="json",        # Use JSON for task serialization
    result_serializer="json",      # Use JSON for result serialization
    accept_content=["json"],       # Accept only JSON content
    timezone="UTC",                # Use UTC timezone
    enable_utc=True,
    # task_track_started=True,       # Track when tasks start execution (useful for monitoring)
    # worker_prefetch_multiplier=1,  # Process one task at a time (good for long-running tasks like I/O bound or ML)
    # task_acks_late=True,           # Acknowledge task only after it completes (or fails)
    # broker_connection_retry_on_startup=True, # Retry connection on startup
)

logger.info(f"Celery app initialized. Broker: {config('CELERY_BROKER_URL')}, Backend: {config('CELERY_RESULT_BACKEND')}")
logger.info(f"Tasks will be discovered in: {celery_app.conf.include}")

# You can define periodic tasks here using celery_app.conf.beat_schedule
# celery_app.conf.beat_schedule = {
#     'cleanup-old-jobs': {
#         'task': 'src.worker.tasks.cleanup_task',
#         'schedule': 3600.0,  # Run every hour
#     },
# }
