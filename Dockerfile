FROM python:3.12.5
# FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app



COPY ./web-app/server/requirements.txt /app/web-app/server/
# RUN pip install --no-cache-dir -r /app/web-app/server/requirements.txt # USE THIS WHILE FINAL PROD DEPLOYMENT
RUN pip install -r /app/web-app/server/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0

# Add wait-for-it script
COPY wait-for-it.sh /usr/local/bin/wait-for-it
RUN chmod +x /usr/local/bin/wait-for-it

# Copy the FastAPI app code to the container
COPY ./web-app/ /app/web-app/


# Expose the FastAPI port
EXPOSE 2305
ENV PYTHONPATH=/app/web-app/server


# Command to run the FastAPI app
# CMD ["uvicorn", "web-app.server.main:app", "--host", "0.0.0.0", "--port", "2305", "--reload"]
