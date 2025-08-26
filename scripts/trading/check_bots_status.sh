#!/bin/bash

# Check Production Bots Status

echo "🔍 PRODUCTION BOTS STATUS CHECK"
echo "================================"

# Check running processes
RUNNING_BOTS=$(ps aux | grep "freqtrade trade" | grep -v grep | wc -l | tr -d ' ')

if [ $RUNNING_BOTS -eq 0 ]; then
    echo "❌ NO BOTS RUNNING"
    echo ""
    echo "💡 Start bots with:"
    echo "   ./scripts/trading/start_production_bots.sh"
    exit 0
fi

echo "🔢 Found $RUNNING_BOTS running bot(s)"
echo ""

# Check SafeBullRider
SAFEBULL_COUNT=$(ps aux | grep "SafeBullRiderStrategy" | grep -v grep | wc -l | tr -d ' ')
if [ $SAFEBULL_COUNT -gt 0 ]; then
    echo "✅ SafeBullRider: $SAFEBULL_COUNT instance(s) running"
    echo "   📊 Web UI: http://127.0.0.1:8081"
    SAFEBULL_PID=$(ps aux | grep "SafeBullRiderStrategy" | grep -v grep | head -1 | awk '{print $2}')
    echo "   🆔 PID: $SAFEBULL_PID"
else
    echo "❌ SafeBullRider: NOT RUNNING"
fi

# Check BeastModeV3
BEAST_COUNT=$(ps aux | grep "BeastModeStrategyV3" | grep -v grep | wc -l | tr -d ' ')
if [ $BEAST_COUNT -gt 0 ]; then
    echo "✅ BeastModeV3: $BEAST_COUNT instance(s) running" 
    echo "   📈 Web UI: http://127.0.0.1:8080"
    BEAST_PID=$(ps aux | grep "BeastModeStrategyV3" | grep -v grep | head -1 | awk '{print $2}')
    echo "   🆔 PID: $BEAST_PID"
else
    echo "❌ BeastModeV3: NOT RUNNING"
fi

echo ""

# Check for duplicates
if [ $RUNNING_BOTS -gt 2 ]; then
    echo "⚠️  WARNING: $RUNNING_BOTS bots running (expected: 2)"
    echo "   You may have duplicate processes"
    echo "   Kill all with: ./scripts/trading/kill_script.sh"
    echo ""
fi

# Check recent log activity
echo "📊 RECENT ACTIVITY:"
if [ -f "user_data/logs/safebull_$(date +%Y%m%d).log" ]; then
    LAST_SAFEBULL=$(tail -1 "user_data/logs/safebull_$(date +%Y%m%d).log" 2>/dev/null)
    echo "   SafeBull: ${LAST_SAFEBULL:0:80}..."
fi

if [ -f "user_data/logs/beastmode_$(date +%Y%m%d).log" ]; then
    LAST_BEAST=$(tail -1 "user_data/logs/beastmode_$(date +%Y%m%d).log" 2>/dev/null)
    echo "   BeastMode: ${LAST_BEAST:0:80}..."
fi

echo ""
echo "💡 Quick Commands:"
echo "   Monitor performance: ./scripts/trading/monitor_performance.sh"
echo "   Kill all bots:      ./scripts/trading/kill_script.sh"
echo "   Restart bots:       ./scripts/trading/start_production_bots.sh"
echo ""