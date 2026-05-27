#!/bin/bash
set -e

# ==============================
# CONFIG (EDIT IF NEEDED)
# ==============================

BASE_DIR="/home/sreevatsa.s/HiSAM-API/web-app/backend"
CONDA_SH="/home/sreevatsa.s/miniconda/etc/profile.d/conda.sh"
CONDA_ENV="sreevatsa_test"

NETWORK_NAME="bhashini_api_network_vatsa"
MYSQL_CONTAINER="bhashini_api_mysql_vatsa"
REDIS_CONTAINER="bhashini_api_redis_vatsa"

CELERY_SESSION="celery"
WEBAPP_SESSION="webapp"

LOGFILE="/tmp/auto-deploy-debug.log"

# ==============================
# LOGGING
# ==============================

exec > >(tee -a "$LOGFILE") 2>&1
echo "=== Starting auto-deploy at $(date) ==="

# ==============================
# LOAD CONDA
# ==============================

source "$CONDA_SH"
conda activate "$CONDA_ENV"
echo "Activated conda environment"

# ==============================
# GO TO PROJECT DIR
# ==============================

cd "$BASE_DIR"
echo "Changed directory to $BASE_DIR"

# ==============================
# DOCKER NETWORK
# ==============================

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    echo "Creating Docker network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
else
    echo "Docker network $NETWORK_NAME already exists."
fi

# ==============================
# MYSQL CONTAINER
# ==============================

if ! docker ps -a --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER}$"; then
    echo "Creating MySQL container..."
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
    echo "Restarting MySQL container..."
    docker restart "$MYSQL_CONTAINER"
fi

# ==============================
# REDIS CONTAINER (FIXED PORT)
# ==============================

if ! docker ps -a --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
    echo "Creating Redis container..."
    docker run -d \
        --name "$REDIS_CONTAINER" \
        --network "$NETWORK_NAME" \
        -v bhashini_api_redis_volume:/data \
        -p 6376:6379 \
        redis:8.0.2
else
    echo "Restarting Redis container..."
    docker restart "$REDIS_CONTAINER"
fi

echo "Checked/started all Docker containers."

# ==============================
# TMUX PATH
# ==============================

TMUX_BIN=$(command -v tmux)
export CUDA_VISIBLE_DEVICES=0
echo "Using tmux at $TMUX_BIN"

# ==============================
# START CELERY (SAFE WAY)
# ==============================

if "$TMUX_BIN" has-session -t "$CELERY_SESSION" 2>/dev/null; then
    echo "Celery session already exists — killing and restarting..."
    "$TMUX_BIN" kill-session -t "$CELERY_SESSION"
fi

echo "Starting Celery tmux session..."

"$TMUX_BIN" new-session -d -s "$CELERY_SESSION" \
"source $CONDA_SH && \
 conda activate $CONDA_ENV && \
 cd $BASE_DIR && \
 celery -A src.worker.celery_app worker \
 --loglevel=INFO \
 -Q image_processing_queue \
 -c 1 \
 --pool=gevent \
 -f /home/sreevatsa.s/HiSAM-API/store/log_files/celery_log.log \
 --max-tasks-per-child=10"

# ==============================
# START FASTAPI (SAFE WAY)
# ==============================

if "$TMUX_BIN" has-session -t "$WEBAPP_SESSION" 2>/dev/null; then
    echo "WebApp session already exists — killing and restarting..."
    "$TMUX_BIN" kill-session -t "$WEBAPP_SESSION"
fi

echo "Starting WebApp tmux session..."

"$TMUX_BIN" new-session -d -s "$WEBAPP_SESSION" \
"source $CONDA_SH && \
 conda activate $CONDA_ENV && \
 cd $BASE_DIR && \
 uvicorn main:app --host 0.0.0.0 --port 5001"

echo "=== Deployment completed at $(date) ==="
