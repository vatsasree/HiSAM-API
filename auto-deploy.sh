#!/bin/bash
set -e

# === Setup logging for debugging ===
LOGFILE="/tmp/auto-deploy-debug.log"
exec > >(tee -a "$LOGFILE") 2>&1
echo "=== Starting auto-deploy at $(date) ==="

# === Load conda ===
source /home/user/anaconda3/etc/profile.d/conda.sh
conda activate sreevatsa_test
echo "Activated conda environment"

# === Go to project directory ===
cd /data3/shanmukha.sreevatsa/demo_textline_app/web-app/backend
echo "Changed directory to backend"

# === Ensure Docker network exists ===
NETWORK_NAME="bhashini_api_network_vatsa"
if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    echo "Creating Docker network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
else
    echo "Docker network $NETWORK_NAME already exists."
fi

# === Check and run MySQL container ===
MYSQL_CONTAINER="bhashini_api_mysql_vatsa"
if ! docker ps -a --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER}$"; then
    echo "MySQL container not found. Creating and starting $MYSQL_CONTAINER..."
    docker run -d \
        --name "$MYSQL_CONTAINER" \
        --network "$NETWORK_NAME" \
        --restart unless-stopped \
        -v bhashini_api_mysql_vatsa_volume:/var/lib/mysql \
        -e MYSQL_ROOT_PASSWORD=root \
        -e MYSQL_DATABASE=bhashini_api_db_vatsa \
        -e MYSQL_USER=bhashini_user_vatsa \
        -e MYSQL_PASSWORD=bhashini_user_vatsa \
        -p 3309:3306 \
        mysql:9.3
else
    echo "MySQL container $MYSQL_CONTAINER already exists. Restarting..."
    docker restart "$MYSQL_CONTAINER"
fi

# === Check and run Redis container ===
REDIS_CONTAINER="bhashini_api_redis_vatsa"
if ! docker ps -a --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
    echo "Redis container not found. Creating and starting $REDIS_CONTAINER..."
    docker run -d \
        --name "$REDIS_CONTAINER" \
        --network "$NETWORK_NAME" \
        -v bhashini_api_redis_volume:/data \
        -p 6376:6379 \
        redis:8.0.2
else
    echo "Redis container $REDIS_CONTAINER already exists. Restarting..."
    docker restart "$REDIS_CONTAINER"
fi

echo "Checked/started all Docker containers."

# === Get full path to tmux ===
TMUX_BIN=$(command -v tmux)
echo "Using tmux at $TMUX_BIN"
export CUDA_VISIBLE_DEVICES=0

# === Start Celery in tmux if not running ===
SESSION_NAME_1="celery"
if ! "$TMUX_BIN" has-session -t $SESSION_NAME_1 2>/dev/null; then
    echo "Starting Celery session..."
    "$TMUX_BIN" new-session -d -s $SESSION_NAME_1 \
        "source /home/user/anaconda3/etc/profile.d/conda.sh && \
         conda activate sreevatsa_test && \
         cd /data3/shanmukha.sreevatsa/demo_textline_app/web-app/backend/ && \
         celery -A src.worker.celery_app worker --loglevel=INFO -Q image_processing_queue -c 1 --pool=gevent \
         -f /data3/shanmukha.sreevatsa/demo_textline_app/store/log_files/celery_log.log \
         --max-tasks-per-child=10"
else
    echo "Celery session already running."
fi

# === Start FastAPI in tmux if not running ===
SESSION_NAME_2="webapp"
if ! "$TMUX_BIN" has-session -t $SESSION_NAME_2 2>/dev/null; then
    echo "Starting WebApp session..."
    "$TMUX_BIN" new-session -d -s $SESSION_NAME_2 \
        "source /home/user/anaconda3/etc/profile.d/conda.sh && \
         conda activate sreevatsa_test && \
         cd /data3/shanmukha.sreevatsa/demo_textline_app/web-app/backend/ && \
         uvicorn main:app --host 0.0.0.0 --port 5016 --reload"
else
    echo "WebApp session already running."
fi

echo "=== Deployment script completed successfully at $(date) ==="