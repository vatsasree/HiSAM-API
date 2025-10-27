# === Get full path to tmux ===
TMUX_BIN=$(command -v tmux)
echo "Using tmux at $TMUX_BIN"
export CUDA_VISIBLE_DEVICES=1

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