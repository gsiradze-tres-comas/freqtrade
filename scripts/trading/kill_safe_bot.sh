#!/bin/bash

# Stop the SafeBullRiderStrategy bot

echo "🛑 Stopping SafeBullRiderStrategy..."

# Try to kill using saved PID first
if [ -f "user_data/.safe_bot.pid" ]; then
    PID=$(cat user_data/.safe_bot.pid)
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        echo "✅ Stopped bot with PID: $PID"
        rm user_data/.safe_bot.pid
    else
        echo "⚠️ Saved PID $PID not running, searching for process..."
    fi
fi

# Also kill any SafeBullRiderStrategy processes
if pgrep -f "SafeBullRiderStrategy" > /dev/null; then
    pkill -f "SafeBullRiderStrategy"
    echo "✅ Killed all SafeBullRiderStrategy processes"
else
    echo "ℹ️ No SafeBullRiderStrategy processes found"
fi

echo "🔍 Current freqtrade processes:"
ps aux | grep freqtrade | grep -v grep || echo "   None running"