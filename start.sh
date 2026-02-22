#!/bin/bash
# Chemo Rota Converter — Launcher
# Double-click "Chemo Rota Converter.desktop" to run this.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=5000
PIDFILE="$DIR/.flask.pid"
LOGFILE="$DIR/.flask.log"

notify() {
    notify-send "Chemo Rota Converter" "$1" --icon=document-send 2>/dev/null || true
}

# ── Check if already running ──────────────────────────────────────────────────
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Server already running (PID $OLD_PID). Opening browser..."
        notify "Already running — opening browser."
        xdg-open "http://localhost:$PORT"
        exit 0
    else
        # Stale PID file — clean up
        rm -f "$PIDFILE"
    fi
fi

# ── Start Flask ───────────────────────────────────────────────────────────────
echo "Starting Chemo Rota Converter on port $PORT..."
echo "Log: $LOGFILE"
echo ""

cd "$DIR"
"$DIR/.venv/bin/python3" app.py > "$LOGFILE" 2>&1 &
FLASK_PID=$!
echo $FLASK_PID > "$PIDFILE"

# ── Wait for Flask to be ready (up to 15 seconds) ────────────────────────────
echo -n "Waiting for server"
for i in $(seq 1 30); do
    sleep 0.5
    if curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
        echo " ready!"
        break
    fi
    echo -n "."
    # Check it hasn't crashed
    if ! kill -0 "$FLASK_PID" 2>/dev/null; then
        echo ""
        echo "ERROR: Server failed to start. Check log:"
        echo "  $LOGFILE"
        cat "$LOGFILE"
        rm -f "$PIDFILE"
        notify "Failed to start — check ~/.flask.log"
        read -p "Press Enter to close..."
        exit 1
    fi
done

# ── Open browser ──────────────────────────────────────────────────────────────
xdg-open "http://localhost:$PORT"
notify "Converter is running. Use stop.sh (or the desktop icon) to stop it when done."

echo ""
echo "============================================"
echo "  Chemo Rota Converter is running!"
echo "  URL: http://localhost:$PORT"
echo "  PID: $FLASK_PID  (saved to .flask.pid)"
echo ""
echo "  To STOP the server, run stop.sh"
echo "  or double-click 'Stop Converter.desktop'"
echo "============================================"
echo ""
echo "This window can be closed — the server keeps running in the background."
