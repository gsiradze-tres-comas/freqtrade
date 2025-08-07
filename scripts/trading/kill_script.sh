#!/bin/bash

# Check what's running first
RUNNING_PIDS=$(ps aux | grep "freqtrade trade" | grep -v grep | awk '{print $2}')

if [ -z "$RUNNING_PIDS" ]; then
    echo "ℹ️  No freqtrade trading bots currently running."
    exit 0
fi

echo "🛑 Found running freqtrade processes:"
ps aux | grep "freqtrade trade" | grep -v grep | awk '{print "📍 PID: " $2 " - " $11 " " $12 " " $13}'
echo ""

# Kill any running freqtrade processes
echo "🛑 Killing freqtrade processes..."
pkill -f freqtrade
pkill -f python.*freqtrade
pkill -f download_data
pkill -f backtest

sleep 2

# Verify they're gone
REMAINING=$(ps aux | grep "freqtrade trade" | grep -v grep | wc -l)
if [ "$REMAINING" -eq 0 ]; then
    echo "✅ All freqtrade processes terminated successfully"
    echo "🆕 You can now start a new bot with: ./start_paper_trading.sh"
else
    echo "⚠️  Some processes may still be running. Check with: ps aux | grep freqtrade"
fi

echo "🔚 Terminal is now free."