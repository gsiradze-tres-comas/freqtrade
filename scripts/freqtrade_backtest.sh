#!/bin/bash

# FreqTrade Internal Backtest Script
# Fast, built-in backtesting using FreqTrade's optimized engine

set -e

# Default parameters
STRATEGY="BeastModeStrategy"
CONFIG="user_data/configs/config_safe_bull.json"
TIMEFRAME="5m"
BALANCE=2500
START_DATE=""
END_DATE=""
RECENT=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --strategy)
      STRATEGY="$2"
      shift 2
      ;;
    --config)
      CONFIG="$2"
      shift 2
      ;;
    --balance)
      BALANCE="$2"
      shift 2
      ;;
    --start)
      START_DATE="$2"
      shift 2
      ;;
    --end)
      END_DATE="$2"
      shift 2
      ;;
    --recent)
      RECENT="yes"
      shift
      ;;
    --help)
      echo "FreqTrade Internal Backtest"
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --strategy STRATEGY    Strategy name (default: BeastModeStrategy)"
      echo "  --config CONFIG        Config file (default: user_data/configs/config_safe_bull.json)"
      echo "  --balance BALANCE      Starting balance (default: 2500)"
      echo "  --start YYYY-MM-DD     Start date"
      echo "  --end YYYY-MM-DD       End date"
      echo "  --recent               Use recent 3 months"
      echo "  --help                 Show this help"
      echo ""
      echo "Examples:"
      echo "  $0 --recent                                    # Last 3 months"
      echo "  $0 --start 2024-01-01 --end 2024-12-31        # Full year 2024"
      echo "  $0 --strategy BeastModeStrategy --balance 5000 # Custom balance"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Determine date range
if [ "$RECENT" = "yes" ]; then
    # Last 3 months
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        START_DATE=$(date -j -v-3m +%Y%m%d)
        END_DATE=$(date -j +%Y%m%d)
    else
        # Linux
        START_DATE=$(date -d '3 months ago' +%Y%m%d)
        END_DATE=$(date +%Y%m%d)
    fi
    TIMERANGE="${START_DATE}-${END_DATE}"
elif [ -n "$START_DATE" ] && [ -n "$END_DATE" ]; then
    # Custom date range
    TIMERANGE="${START_DATE//-/}-${END_DATE//-/}"
else
    echo "Error: Must specify either --recent or both --start and --end dates"
    exit 1
fi

echo "🚀 FreqTrade Internal Backtest"
echo "================================"
echo "Strategy: $STRATEGY"
echo "Config: $CONFIG"
echo "Balance: \$$BALANCE"
echo "Timeframe: $TIMEFRAME"
echo "Date Range: $TIMERANGE"
echo "================================"
echo ""

# Check if config exists
if [ ! -f "$CONFIG" ]; then
    echo "❌ Error: Config file not found: $CONFIG"
    exit 1
fi

# Update config with balance (create temp config)
TEMP_CONFIG="/tmp/backtest_config.json"
python3 -c "
import json
with open('$CONFIG', 'r') as f:
    config = json.load(f)
config['dry_run_wallet'] = $BALANCE
with open('$TEMP_CONFIG', 'w') as f:
    json.dump(config, f, indent=2)
"

echo "⏰ Starting backtest at $(date)"
START_TIME=$(date +%s)

# Run FreqTrade backtest
freqtrade backtesting \
    --config "$TEMP_CONFIG" \
    --strategy "$STRATEGY" \
    --timeframe "$TIMEFRAME" \
    --timerange "$TIMERANGE" \
    --breakdown day \
    --cache none \
    --export trades \
    --export-filename "user_data/backtest_results/$(date +%Y%m%d_%H%M%S)_${STRATEGY}_${TIMERANGE}.json"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "✅ Backtest completed in ${DURATION} seconds"
echo "📊 Results exported to user_data/backtest_results/"

# Clean up temp config
rm -f "$TEMP_CONFIG"

# Show summary
echo ""
echo "🎯 Quick Commands:"
echo "# View detailed results:"
echo "freqtrade backtesting-analysis --config $CONFIG"
echo ""
echo "# Plot results:"
echo "freqtrade plot-dataframe --config $CONFIG --strategy $STRATEGY --timerange $TIMERANGE"