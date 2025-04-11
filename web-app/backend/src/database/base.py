# Import Base from the models file where it's defined
from .models import Base
# Import all models to ensure they are registered with Base's metadata
from .models import User, ApiToken, JobRecord, DocumentRecord