#!/bin/bash

# Bot Auto-Restart Script
# Monitors freqtrade bot and restarts on DB/API connection errors
# Usage: ./bot_with_restart.sh [config_file] [strategy]

CONFIG_FILE=${1:-"user_data/configs/config_safe_bull.json"}
STRATEGY=${2:-"SafeBullRiderStrategy"}
LOG_FILE="user_data/logs/freqtrade_hft.log"
RESTART_LOG="user_data/logs/bot_restarts.log"
PID_FILE="user_data/.bot.pid"

# Restart limits
MAX_RESTARTS_PER_HOUR=10
RESTART_COOLDOWN=30  # seconds
RESTART_COUNT=0
HOUR_START=$(date +%s)

# Ensure log directories exist
mkdir -p user_data/logs

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$RESTART_LOG"
}

cleanup() {
    log_message "🛑 Shutdown requested, stopping bot..."
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null; then
            log_message "Stopping bot with PID $PID"
            kill -TERM "$PID" 2>/dev/null
            sleep 5
            if ps -p "$PID" > /dev/null; then
                log_message "Force killing bot with PID $PID"
                kill -9 "$PID" 2>/dev/null
            fi
        fi
        rm -f "$PID_FILE"
    fi
    exit 0
}

# Handle shutdown signals
trap cleanup SIGINT SIGTERM

check_restart_limits() {
    local current_time=$(date +%s)
    local hour_elapsed=$((current_time - HOUR_START))
    
    # Reset counter every hour
    if [ $hour_elapsed -ge 3600 ]; then
        RESTART_COUNT=0
        HOUR_START=$current_time
        log_message "📊 Restart counter reset (new hour)"
    fi
    
    # Check if we've exceeded hourly limit
    if [ $RESTART_COUNT -ge $MAX_RESTARTS_PER_HOUR ]; then
        log_message "❌ CRITICAL: Max restarts per hour reached ($MAX_RESTARTS_PER_HOUR)"
        log_message "⏸️  Bot suspended for safety. Manual intervention required."
        exit 1
    fi
}

is_connection_error() {
    local log_tail=$(tail -50 "$LOG_FILE" 2>/dev/null)
    
    # Check for database connection errors
    if echo "$log_tail" | grep -qi "PendingRollbackError\|rollback\|database.*disconnect\|connection.*lost"; then
        return 0
    fi
    
    # Check for API connection errors
    if echo "$log_tail" | grep -qi "RequestTimeout\|TimeoutError\|ConnectionError\|HTTPError.*5\|HTTPError.*timeout"; then
        return 0
    fi
    
    # Check for SSL/connection cleanup errors
    if echo "$log_tail" | grep -qi "AttributeError.*_abort\|connection.*abort"; then
        return 0
    fi
    
    return 1
}

start_bot() {
    log_message "🚀 Starting FreqTrade bot..."
    log_message "Config: $CONFIG_FILE"
    log_message "Strategy: $STRATEGY"
    
    # Start bot in background
    nohup freqtrade trade \
        --config "$CONFIG_FILE" \
        --strategy "$STRATEGY" \
        --logfile "$LOG_FILE" \
        > user_data/logs/bot_stdout.log 2>&1 &
    
    local bot_pid=$!
    echo $bot_pid > "$PID_FILE"
    
    log_message "✅ Bot started with PID: $bot_pid"
    
    # Wait for bot to initialize
    sleep 10
    
    # Verify bot is still running
    if ! ps -p "$bot_pid" > /dev/null; then
        log_message "❌ Bot failed to start properly"
        return 1
    fi
    
    return 0
}

monitor_bot() {
    local bot_pid=$(cat "$PID_FILE" 2>/dev/null)
    
    # Check if PID file exists and process is running
    if [ -z "$bot_pid" ] || ! ps -p "$bot_pid" > /dev/null 2>&1; then
        return 1  # Bot is not running
    fi
    
    # Check for connection errors in recent logs
    if is_connection_error; then
        log_message "🔍 Connection error detected in logs"
        return 1  # Needs restart
    fi
    
    return 0  # Bot is healthy
}

# Main monitoring loop
log_message "🏥 FreqTrade Auto-Restart Monitor Starting"
log_message "Config: $CONFIG_FILE | Strategy: $STRATEGY"
log_message "Max restarts/hour: $MAX_RESTARTS_PER_HOUR | Cooldown: ${RESTART_COOLDOWN}s"

# Initial bot start
if ! start_bot; then
    log_message "❌ Failed to start bot initially, exiting"
    exit 1
fi

# Monitoring loop
while true; do
    sleep 30  # Check every 30 seconds
    
    if ! monitor_bot; then
        # Bot needs restart
        check_restart_limits
        
        RESTART_COUNT=$((RESTART_COUNT + 1))
        log_message "⚠️  Bot restart needed ($RESTART_COUNT/$MAX_RESTARTS_PER_HOUR this hour)"
        
        # Kill existing bot if still running
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if ps -p "$PID" > /dev/null; then
                log_message "🛑 Stopping unhealthy bot (PID: $PID)"
                kill -TERM "$PID" 2>/dev/null
                sleep 10
                if ps -p "$PID" > /dev/null; then
                    kill -9 "$PID" 2>/dev/null
                fi
            fi
            rm -f "$PID_FILE"
        fi
        
        # Cooldown before restart
        log_message "⏳ Waiting ${RESTART_COOLDOWN}s before restart..."
        sleep $RESTART_COOLDOWN
        
        # Restart bot
        if start_bot; then
            log_message "✅ Bot restarted successfully"
        else
            log_message "❌ Failed to restart bot"
            exit 1
        fi
    fi
done