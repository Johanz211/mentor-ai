#!/usr/bin/env bash
# Mentor AI — Health check & auto-restart
# Keeps the web server running. Add to cron:
#   */5 * * * * /home/johannes/mentor-ai/healthcheck.sh >> /home/johannes/mentor-ai/logs/health.log 2>&1

set -euo pipefail

APP_DIR="/home/johannes/mentor-ai"
PORT=8888
LOG_DIR="$APP_DIR/logs"
PID_FILE="$APP_DIR/mentor.pid"

mkdir -p "$LOG_DIR"

timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

# Check if server is responding
is_healthy() {
    curl -sf --max-time 5 "http://localhost:$PORT/api/mentors" > /dev/null 2>&1
}

# Check if Ollama is reachable
is_ollama_up() {
    curl -sf --max-time 5 "http://localhost:11434/api/tags" > /dev/null 2>&1
}

# Find running mentor server PID
find_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return
        fi
    fi
    # Fallback: find by port
    ss -tlnp 2>/dev/null | grep ":$PORT" | grep -oP 'pid=\K[0-9]+' | head -1 || true
}

# Start the server
start_server() {
    echo "[$(timestamp)] Starting Mentor AI on port $PORT..."
    cd "$APP_DIR"
    source venv/bin/activate
    nohup python3 mentor.py web --port "$PORT" >> "$LOG_DIR/server.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    sleep 3

    if is_healthy; then
        echo "[$(timestamp)] ✅ Server started (PID: $pid)"
    else
        echo "[$(timestamp)] ❌ Server started but not responding — check $LOG_DIR/server.log"
    fi
}

# Stop the server
stop_server() {
    local pid
    pid=$(find_pid)
    if [ -n "$pid" ]; then
        echo "[$(timestamp)] Stopping server (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 2
        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo "[$(timestamp)] Server stopped"
    fi
}

# Main health check
main() {
    case "${1:-check}" in
        start)
            stop_server
            start_server
            ;;
        stop)
            stop_server
            ;;
        restart)
            stop_server
            start_server
            ;;
        status)
            if is_healthy; then
                local pid
                pid=$(find_pid)
                echo "[$(timestamp)] ✅ Server is healthy (PID: ${pid:-unknown})"
            else
                echo "[$(timestamp)] ❌ Server is down"
            fi
            if is_ollama_up; then
                echo "[$(timestamp)] ✅ Ollama is reachable"
            else
                echo "[$(timestamp)] ⚠️  Ollama is not reachable"
            fi
            ;;
        check|"")
            # Auto-restart if down
            if is_healthy; then
                # Healthy — silent (don't spam logs on cron)
                :
            else
                echo "[$(timestamp)] ⚠️  Server is down — restarting..."
                stop_server
                start_server
            fi
            ;;
        *)
            echo "Usage: $0 {start|stop|restart|status|check}"
            exit 1
            ;;
    esac
}

main "$@"
