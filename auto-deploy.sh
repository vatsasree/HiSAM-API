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
docker restart 1e7fe1f3c8ebf98b560fd4884f0a55cb4df49e1c617291079cc65150a7be69c1
docker restart 8b70362cdf5b57113437400c46ef28ff73cc14435550cefef16013a9eab646cd
echo "Restarted Docker containers"

# === Get full path to tmux ===
TMUX_BIN=$(command -v tmux)
echo "Using tmux at $TMUX_BIN"
export CUDA_VISIBLE_DEVICES=1
# === Start Celery in tmux if not running ===
SESSION_NAME_1="celery"
if ! "$TMUX_BIN" has-session -t $SESSION_NAME_1 2>/dev/null; then
    echo "Starting Celery session..."
    "$TMUX_BIN" new-session -d -s $SESSION_NAME_1 "source /home/user/anaconda3/etc/profile.d/conda.sh && conda activate linetr_webapp && cd /data3/amal.joseph/template_api/web-app/backend/ && celery -A src.worker.celery_app worker --loglevel=INFO -Q image_processing_queue -c 1 --pool=gevent -f /data3/amal.joseph/template_api/store/log_files/celery_log.log --max-tasks-per-child=10"
fi

# === Start FastAPI in tmux if not running ===
SESSION_NAME_2="webapp"
if ! "$TMUX_BIN" has-session -t $SESSION_NAME_2 2>/dev/null; then
    echo "Starting WebApp session..."
    "$TMUX_BIN" new-session -d -s $SESSION_NAME_2 "source /home/user/anaconda3/etc/profile.d/conda.sh && conda activate linetr_webapp && cd /data3/amal.joseph/template_api/web-app/backend/  && uvicorn main:app --host 0.0.0.0 --port 5010 --reload"
fi

echo "Deployment script completed."
