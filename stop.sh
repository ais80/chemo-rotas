#!/bin/bash
# Chemo Rota Converter — Stop Server
# Run this (or double-click the desktop icon) when you're finished.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$DIR/.flask.pid"

notify() {
    notify-send "Chemo Rota Converter" "$1" --icon=document-send 2>/dev/null || true
}

if [ ! -f "$PIDFILE" ]; then
    echo "Server doesn't appear to be running (no PID file found)."
    notify "Server was not running."
    exit 0
fi

PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping Chemo Rota Converter (PID $PID)..."
    kill "$PID"
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        kill -9 "$PID"
    fi
    rm -f "$PIDFILE"
    echo "Server stopped."
    notify "Converter stopped."
else
    echo "Server was not running (stale PID file). Cleaning up."
    rm -f "$PIDFILE"
    notify "Server was not running."
fi
