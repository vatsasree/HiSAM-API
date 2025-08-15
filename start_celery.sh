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