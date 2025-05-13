#!/bin/bash
set -e

# === Setup logging for debugging ===
LOGFILE="/tmp/auto-deploy-debug.log"
exec > >(tee -a "$LOGFILE") 2>&1
echo "=== Starting auto-deploy at $(date) ==="

# === Load conda ===
source /home/user/anaconda3/etc/profile.d/conda.sh
conda activate linetr_webapp
echo "Activated conda environment"

# === Go to project directory ===
cd /data3/amal.joseph/template_api/web-app/backend
echo "Changed directory to backend"

# === Restart Docker containers ===
docker restart fdae77a35e209f49584e37125f56f25d9f2d2ad8ae66ec066c60f40927a7d63c
docker restart eca7b1fd13f28b291142788f58f23bf5ce2a141c868ba28048034c98d1f0ae9a
echo "Restarted Docker containers"

# === Get full path to tmux ===
TMUX_BIN=$(command -v tmux)
echo "Using tmux at $TMUX_BIN"

# === Start Celery in tmux if not running ===
SESSION_NAME_1="celery"
if ! "$TMUX_BIN" has-session -t $SESSION_NAME_1 2>/dev/null; then
    echo "Starting Celery session..."
    "$TMUX_BIN" new-session -d -s $SESSION_NAME_1 "source /home/user/anaconda3/etc/profile.d/conda.sh && conda activate linetr_webapp && celery -A src.worker.celery_app worker --loglevel=INFO -Q image_processing_queue -c 2 --pool=gevent -f /data3/amal.joseph/template_api/store/log_files/celery_log.log --max-tasks-per-child=10"
fi

# === Start FastAPI in tmux if not running ===
SESSION_NAME_2="webapp"
if ! "$TMUX_BIN" has-session -t $SESSION_NAME_2 2>/dev/null; then
    echo "Starting WebApp session..."
    "$TMUX_BIN" new-session -d -s $SESSION_NAME_2 "source /home/user/anaconda3/etc/profile.d/conda.sh && conda activate linetr_webapp && uvicorn main:app --host 0.0.0.0 --port 8000"
fi

echo "Deployment script completed."
