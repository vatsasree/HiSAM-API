.
├── .env                  # Environment variables (secrets!)
├── .gitignore
├── Dockerfile            # Builds the FastAPI/Celery image
├── docker-compose.yml    # Defines services (app, worker, db, redis)
├── alembic.ini           # Alembic config
├── migrations/           # Alembic migration scripts
│   ├── versions/
│   └── env.py
├── requirements.txt      # Python dependencies
├── app/                  # Main application package
│   ├── __init__.py
│   ├── main.py           # FastAPI app instance, routers, middleware
│   ├── core/             # Core logic, settings, security
│   │   ├── __init__.py
│   │   ├── config.py     # Pydantic settings (reads .env)
│   │   └── security.py   # API token handling logic
│   ├── db/               # Database related code
│   │   ├── __init__.py
│   │   ├── base.py       # Base model, common elements
│   │   ├── crud.py       # CRUD operations (e.g., create_job, get_job)
│   │   ├── models.py     # SQLAlchemy models (e.g., Job, ApiToken)
│   │   ├── schemas.py    # Pydantic schemas (for API validation/response)
│   │   └── session.py    # Database session management
│   ├── api/              # API endpoints/routers
│   │   ├── __init__.py
│   │   ├── deps.py       # API dependencies (e.g., get_db, get_current_user)
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       ├── process.py  # /process endpoint router
│   │       └── status.py   # /status endpoint router
│   ├── worker/           # Celery related code
│   │   ├── __init__.py
│   │   ├── celery_app.py # Celery app instance creation and config
│   │   └── tasks.py      # Celery task definitions (e.g., process_image_task)
│   └── logging_config.py # Logging setup
└── tests/                # Pytest tests
    ├── __init__.py
    ├── conftest.py       # Fixtures (test client, db session)
    ├── api/              # API tests
    │   └── test_process.py
    │   └── test_status.py
    ├── worker/           # Worker tests
    │   └── test_tasks.py
    └── db/               # DB/CRUD tests (optional)
        └── test_crud.py