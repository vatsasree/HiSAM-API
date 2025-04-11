FROM python:3.12.5

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory inside the container
WORKDIR /app



COPY ./web-app/backend/requirements.txt /app/
# RUN pip install --no-cache-dir -r /app/requirements.txt # USE THIS WHILE FINAL PROD DEPLOYMENT
RUN pip install -r /app/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        # Clean up apt cache to reduce image size
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*

# Add wait-for-it script - currently not using as healthcheck is being used in docker-compose.yaml
# COPY wait-for-it.sh /usr/local/bin/wait-for-it
# RUN chmod +x /usr/local/bin/wait-for-it

# Copy the FastAPI app code to the container
COPY ./web-app/backend /app/


# Expose the FastAPI port
EXPOSE 2305


# Command to run the FastAPI app - overridden by docker-compose.yaml
# CMD ["uvicorn", "web-app.server.main:app", "--host", "0.0.0.0", "--port", "2305", "--reload"]
