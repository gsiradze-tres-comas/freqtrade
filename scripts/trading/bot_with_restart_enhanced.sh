#!/bin/bash
#
# Enhanced FreqTrade Auto-Restart Script with Network Recovery
# Handles internet disconnections and automatically retries
#

# Configuration
CONFIG_FILE="user_data/configs/config_safe_bull.json"
STRATEGY="SafeBullRiderStrategy"
LOG_FILE="user_data/logs/freqtrade_hft.log"
RESTART_LOG="user_data/logs/auto_restart.log"
PID_FILE="user_data/pids/bot.pid"

# Restart limits
MAX_RESTARTS_PER_HOUR=10
RESTART_COUNT=0
HOUR_START=$(date +%s)

# Cooldown periods
RESTART_COOLDOWN=30      # Normal restart cooldown
NETWORK_RETRY_DELAY=60    # Delay between network reconnection attempts
MAX_NETWORK_RETRIES=60    # Max retries for network (60 = 1 hour of retrying)

# Ensure directories exist
mkdir -p user_data/logs user_data/pids

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$RESTART_LOG"
}

check_network_connectivity() {
    # Check multiple endpoints to verify internet connectivity
    local binance_check=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://api.binance.com/api/v3/ping 2>/dev/null)
    local google_check=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://www.google.com 2>/dev/null)
    
    if [ "$binance_check" = "200" ] || [ "$google_check" = "200" ] || [ "$google_check" = "302" ]; then
        return 0  # Network is available
    else
        return 1  # Network is down
    fi
}

wait_for_network() {
    local retry_count=0
    
    log_message "🌐 Checking network connectivity..."
    
    while [ $retry_count -lt $MAX_NETWORK_RETRIES ]; do
        if check_network_connectivity; then
            log_message "✅ Network connection restored!"
            return 0
        fi
        
        retry_count=$((retry_count + 1))
        log_message "⚠️ Network unavailable (attempt $retry_count/$MAX_NETWORK_RETRIES). Retrying in ${NETWORK_RETRY_DELAY}s..."
        sleep $NETWORK_RETRY_DELAY
    done
    
    log_message "❌ Network unavailable after $MAX_NETWORK_RETRIES attempts. Exiting."
    return 1
}

cleanup() {
    log_message "🛑 Shutting down auto-restart monitor..."
    
    # Kill bot if running
    if [ -f "$PID_FILE" ]; then
        local bot_pid=$(cat "$PID_FILE")
        if ps -p "$bot_pid" > /dev/null 2>&1; then
            log_message "Stopping bot (PID: $bot_pid)..."
            kill -TERM "$bot_pid" 2>/dev/null
            sleep 2
            kill -9 "$bot_pid" 2>/dev/null
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

detect_failure_reason() {
    local log_tail=$(tail -100 "$LOG_FILE" 2>/dev/null)
    
    # Network/Market loading errors
    if echo "$log_tail" | grep -qi "Could not load markets\|Market.*not.*load\|ccxt.*NetworkError"; then
        echo "NETWORK_ERROR"
        return 0
    fi
    
    # Database connection errors
    if echo "$log_tail" | grep -qi "PendingRollbackError\|rollback\|database.*disconnect\|connection.*lost\|psycopg2.*OperationalError"; then
        echo "DATABASE_ERROR"
        return 0
    fi
    
    # API connection errors
    if echo "$log_tail" | grep -qi "RequestTimeout\|TimeoutError\|ConnectionError\|HTTPError.*5\|Read timed out"; then
        echo "API_ERROR"
        return 0
    fi
    
    # SSL/connection cleanup errors
    if echo "$log_tail" | grep -qi "AttributeError.*_abort\|SSLError\|ssl.*handshake"; then
        echo "SSL_ERROR"
        return 0
    fi
    
    # Rate limit errors
    if echo "$log_tail" | grep -qi "RateLimitExceeded\|429.*Too Many Requests"; then
        echo "RATE_LIMIT"
        return 0
    fi
    
    echo "UNKNOWN"
}

start_bot() {
    # First ensure network is available
    if ! check_network_connectivity; then
        log_message "⚠️ Network unavailable. Waiting for connection..."
        if ! wait_for_network; then
            return 1
        fi
    fi
    
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
        
        # Check why it failed
        local failure_reason=$(detect_failure_reason)
        log_message "📝 Failure reason: $failure_reason"
        
        # If network issue, wait for network
        if [ "$failure_reason" = "NETWORK_ERROR" ]; then
            log_message "🌐 Network-related failure detected. Waiting for connectivity..."
            wait_for_network
        fi
        
        return 1
    fi
    
    # Check if bot successfully connected to exchange
    sleep 5
    local recent_log=$(tail -20 "$LOG_FILE" 2>/dev/null)
    if echo "$recent_log" | grep -qi "Could not load markets"; then
        log_message "⚠️ Bot started but couldn't connect to exchange"
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
    
    # Check for recent errors that need restart
    local failure_reason=$(detect_failure_reason)
    if [ "$failure_reason" != "UNKNOWN" ]; then
        log_message "🔍 Error detected: $failure_reason"
        return 1  # Needs restart
    fi
    
    return 0  # Bot is healthy
}

# Main monitoring loop
log_message "🏥 Enhanced FreqTrade Auto-Restart Monitor Starting"
log_message "Config: $CONFIG_FILE | Strategy: $STRATEGY"
log_message "Max restarts/hour: $MAX_RESTARTS_PER_HOUR | Network retry: ${NETWORK_RETRY_DELAY}s"

# Initial bot start
start_attempt=0
max_initial_attempts=5

while [ $start_attempt -lt $max_initial_attempts ]; do
    if start_bot; then
        break
    fi
    
    start_attempt=$((start_attempt + 1))
    log_message "⚠️ Initial start attempt $start_attempt/$max_initial_attempts failed"
    
    if [ $start_attempt -lt $max_initial_attempts ]; then
        log_message "⏳ Waiting ${RESTART_COOLDOWN}s before retry..."
        sleep $RESTART_COOLDOWN
    else
        log_message "❌ Failed to start bot after $max_initial_attempts attempts"
        exit 1
    fi
done

# Monitoring loop
while true; do
    sleep 30  # Check every 30 seconds
    
    if ! monitor_bot; then
        # Bot needs restart
        local bot_pid=$(cat "$PID_FILE" 2>/dev/null)
        local failure_reason=$(detect_failure_reason)
        
        log_message "⚠️ Bot not healthy (PID: $bot_pid, Reason: $failure_reason)"
        
        # Kill existing bot if still running
        if [ -n "$bot_pid" ] && ps -p "$bot_pid" > /dev/null 2>&1; then
            log_message "🔄 Stopping unhealthy bot..."
            kill -TERM "$bot_pid" 2>/dev/null
            sleep 2
            kill -9 "$bot_pid" 2>/dev/null
        fi
        
        # Check restart limits
        check_restart_limits
        
        # Handle different failure types
        case "$failure_reason" in
            NETWORK_ERROR|API_ERROR)
                log_message "🌐 Network/API issue detected. Checking connectivity..."
                if ! wait_for_network; then
                    log_message "❌ Cannot restore network connection. Exiting."
                    exit 1
                fi
                ;;
            RATE_LIMIT)
                log_message "⏳ Rate limit detected. Waiting 60 seconds..."
                sleep 60
                ;;
            DATABASE_ERROR)
                log_message "🗄️ Database error. Waiting 10 seconds..."
                sleep 10
                ;;
            *)
                log_message "⏳ Waiting ${RESTART_COOLDOWN}s before restart..."
                sleep $RESTART_COOLDOWN
                ;;
        esac
        
        # Attempt restart
        RESTART_COUNT=$((RESTART_COUNT + 1))
        log_message "🔄 Restart attempt $RESTART_COUNT/$MAX_RESTARTS_PER_HOUR this hour"
        
        if ! start_bot; then
            log_message "❌ Failed to restart bot"
            log_message "⏳ Will retry in ${RESTART_COOLDOWN}s..."
            sleep $RESTART_COOLDOWN
        else
            log_message "✅ Bot successfully restarted"
        fi
    fi
done