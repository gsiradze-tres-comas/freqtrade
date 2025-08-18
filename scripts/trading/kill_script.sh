#!/bin/bash

# Check what's running first
RUNNING_PIDS=$(ps aux | grep "freqtrade trade" | grep -v grep | awk '{print $2}')
RESTART_PIDS=$(ps aux | grep "bot_with_restart.sh" | grep -v grep | awk '{print $2}')

if [ -z "$RUNNING_PIDS" ] && [ -z "$RESTART_PIDS" ]; then
    echo "ℹ️  No freqtrade trading bots or auto-restart scripts currently running."
    exit 0
fi

echo "🛑 Found running processes:"
if [ -n "$RUNNING_PIDS" ]; then
    ps aux | grep "freqtrade trade" | grep -v grep | awk '{print "📍 FreqTrade PID: " $2 " - " $11 " " $12 " " $13}'
fi
if [ -n "$RESTART_PIDS" ]; then
    ps aux | grep "bot_with_restart.sh" | grep -v grep | awk '{print "🔄 Auto-restart PID: " $2 " - " $11 " " $12 " " $13}'
fi
echo ""

# Kill auto-restart scripts first (to prevent them from restarting the bot)
echo "🛑 Stopping auto-restart scripts..."
pkill -f bot_with_restart.sh

# Kill any running freqtrade processes
echo "🛑 Killing freqtrade processes..."
pkill -f freqtrade
pkill -f python.*freqtrade
pkill -f download_data
pkill -f backtest

sleep 2

# Verify they're gone
REMAINING_FREQTRADE=$(ps aux | grep "freqtrade trade" | grep -v grep | wc -l)
REMAINING_RESTART=$(ps aux | grep "bot_with_restart.sh" | grep -v grep | wc -l)

if [ "$REMAINING_FREQTRADE" -eq 0 ] && [ "$REMAINING_RESTART" -eq 0 ]; then
    echo "✅ All processes terminated successfully"
    echo "🆕 You can now start a new bot with:"
    echo "   Foreground: ./scripts/trading/bot_with_restart.sh"
    echo "   Background: nohup ./scripts/trading/bot_with_restart.sh > user_data/logs/auto_restart_output.log 2>&1 &"
else
    echo "⚠️  Some processes may still be running:"
    if [ "$REMAINING_FREQTRADE" -gt 0 ]; then
        echo "   FreqTrade processes: $REMAINING_FREQTRADE"
    fi
    if [ "$REMAINING_RESTART" -gt 0 ]; then
        echo "   Auto-restart processes: $REMAINING_RESTART"
    fi
    echo "   Check with: ps aux | grep -E 'freqtrade|bot_with_restart'"
fi

echo "🔚 Terminal is now free."