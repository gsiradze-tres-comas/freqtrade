#!/bin/bash
#
# Bot Failure Diagnostic Script
# Captures comprehensive information when bot crashes
#

LOG_DIR="user_data/logs"
DIAGNOSTIC_FILE="$LOG_DIR/bot_diagnostics_$(date +%Y%m%d_%H%M%S).log"

echo "=== BOT FAILURE DIAGNOSTIC REPORT ===" > "$DIAGNOSTIC_FILE"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')" >> "$DIAGNOSTIC_FILE"
echo "" >> "$DIAGNOSTIC_FILE"

# 1. Check if bot is running
echo "=== PROCESS STATUS ===" >> "$DIAGNOSTIC_FILE"
if pgrep -f "freqtrade trade" > /dev/null; then
    echo "Bot Status: RUNNING" >> "$DIAGNOSTIC_FILE"
    ps aux | grep -E "freqtrade trade" | grep -v grep >> "$DIAGNOSTIC_FILE"
else
    echo "Bot Status: NOT RUNNING" >> "$DIAGNOSTIC_FILE"
fi
echo "" >> "$DIAGNOSTIC_FILE"

# 2. Last 100 lines of error logs
echo "=== LAST 100 LOG LINES ===" >> "$DIAGNOSTIC_FILE"
tail -100 "$LOG_DIR/freqtrade_hft.log" >> "$DIAGNOSTIC_FILE" 2>&1
echo "" >> "$DIAGNOSTIC_FILE"

# 3. Check for specific error patterns
echo "=== ERROR ANALYSIS ===" >> "$DIAGNOSTIC_FILE"
echo "Connection Errors:" >> "$DIAGNOSTIC_FILE"
grep -c "ConnectionError\|TimeoutError\|RequestTimeout" "$LOG_DIR/freqtrade_hft.log" | tail -1 >> "$DIAGNOSTIC_FILE"

echo "Database Errors:" >> "$DIAGNOSTIC_FILE"
grep -c "PendingRollbackError\|OperationalError\|IntegrityError" "$LOG_DIR/freqtrade_hft.log" | tail -1 >> "$DIAGNOSTIC_FILE"

echo "SSL/TLS Errors:" >> "$DIAGNOSTIC_FILE"
grep -c "SSLError\|_abort\|ssl" "$LOG_DIR/freqtrade_hft.log" | tail -1 >> "$DIAGNOSTIC_FILE"

echo "Strategy Errors:" >> "$DIAGNOSTIC_FILE"
grep -c "AttributeError\|KeyError\|ValueError\|TypeError" "$LOG_DIR/freqtrade_hft.log" | tail -1 >> "$DIAGNOSTIC_FILE"
echo "" >> "$DIAGNOSTIC_FILE"

# 4. Last errors and tracebacks
echo "=== LAST ERRORS & TRACEBACKS ===" >> "$DIAGNOSTIC_FILE"
grep -A 20 -B 5 "ERROR\|CRITICAL\|Traceback\|Exception" "$LOG_DIR/freqtrade_hft.log" | tail -200 >> "$DIAGNOSTIC_FILE"
echo "" >> "$DIAGNOSTIC_FILE"

# 5. System resources
echo "=== SYSTEM RESOURCES ===" >> "$DIAGNOSTIC_FILE"
echo "Memory Usage:" >> "$DIAGNOSTIC_FILE"
top -l 1 | head -10 >> "$DIAGNOSTIC_FILE" 2>&1
echo "" >> "$DIAGNOSTIC_FILE"

echo "Disk Usage:" >> "$DIAGNOSTIC_FILE"
df -h . >> "$DIAGNOSTIC_FILE"
echo "" >> "$DIAGNOSTIC_FILE"

# 6. Network connectivity
echo "=== NETWORK STATUS ===" >> "$DIAGNOSTIC_FILE"
echo "Binance API Check:" >> "$DIAGNOSTIC_FILE"
curl -s -o /dev/null -w "HTTP Code: %{http_code}, Time: %{time_total}s\n" https://api.binance.com/api/v3/ping >> "$DIAGNOSTIC_FILE" 2>&1
echo "" >> "$DIAGNOSTIC_FILE"

# 7. Database status
echo "=== DATABASE STATUS ===" >> "$DIAGNOSTIC_FILE"
psql postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_safe_db -c "SELECT COUNT(*) as open_trades FROM trades WHERE is_open = true;" >> "$DIAGNOSTIC_FILE" 2>&1
echo "" >> "$DIAGNOSTIC_FILE"

# 8. Recent restart history
echo "=== RESTART HISTORY ===" >> "$DIAGNOSTIC_FILE"
if [ -f "$LOG_DIR/auto_restart.log" ]; then
    tail -20 "$LOG_DIR/auto_restart.log" >> "$DIAGNOSTIC_FILE"
else
    echo "No restart log found" >> "$DIAGNOSTIC_FILE"
fi
echo "" >> "$DIAGNOSTIC_FILE"

# 9. Strategy file integrity
echo "=== STRATEGY CHECK ===" >> "$DIAGNOSTIC_FILE"
if [ -f "user_data/strategies/SafeBullRiderStrategy.py" ]; then
    echo "Strategy file exists" >> "$DIAGNOSTIC_FILE"
    python3 -m py_compile user_data/strategies/SafeBullRiderStrategy.py 2>&1 | head -5 >> "$DIAGNOSTIC_FILE"
else
    echo "Strategy file NOT FOUND!" >> "$DIAGNOSTIC_FILE"
fi
echo "" >> "$DIAGNOSTIC_FILE"

echo "=== END OF DIAGNOSTIC REPORT ===" >> "$DIAGNOSTIC_FILE"

# Print summary to console
echo "📊 Diagnostic report saved to: $DIAGNOSTIC_FILE"
echo ""
echo "Quick Summary:"
echo "-------------"
grep "Bot Status:" "$DIAGNOSTIC_FILE"
echo "Errors found:"
grep -E "Connection Errors:|Database Errors:|SSL/TLS Errors:|Strategy Errors:" "$DIAGNOSTIC_FILE" | head -4
echo ""
echo "Last critical error:"
grep -A 3 "CRITICAL\|ERROR" "$LOG_DIR/freqtrade_hft.log" | tail -4

# Also save a summary for quick reference
SUMMARY_FILE="$LOG_DIR/last_failure_summary.txt"
{
    echo "Last Failure: $(date '+%Y-%m-%d %H:%M:%S')"
    grep "Bot Status:" "$DIAGNOSTIC_FILE"
    echo "---"
    grep -A 3 "ERROR\|CRITICAL" "$LOG_DIR/freqtrade_hft.log" | tail -10
} > "$SUMMARY_FILE"