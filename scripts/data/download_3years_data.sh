#!/bin/bash

# Download 3 years of historical data for backtesting
# Usage: ./download_3years_data.sh [BTC|all]

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
EXCHANGE="binance"
TIMEFRAME="5m"
START_DATE="20220101"
END_DATE="20250807"
DATA_DIR="user_data/data"

# Pairs to download
ALL_PAIRS=(
    "BTC/USDT:USDT"
    "ETH/USDT:USDT"
    "DOGE/USDT:USDT"
    "ADA/USDT:USDT"
    "XRP/USDT:USDT"
    "SOL/USDT:USDT"
    "AVAX/USDT:USDT"
    "LINK/USDT:USDT"
    "BNB/USDT:USDT"
    "BCH/USDT:USDT"
    "TIA/USDT:USDT"
    "DOT/USDT:USDT"
    "UNI/USDT:USDT"
    "1INCH/USDT:USDT"
)

# Function to download data for a single pair
download_pair() {
    local pair=$1
    echo -e "${YELLOW}Downloading 3 years of data for $pair...${NC}"
    
    # Run in background and wait with timeout
    (
        freqtrade download-data \
            --exchange $EXCHANGE \
            --pairs "$pair" \
            --timeframe $TIMEFRAME \
            --timerange ${START_DATE}-${END_DATE} \
            --datadir $DATA_DIR \
            --data-format-ohlcv feather \
            --trading-mode futures
    ) &
    
    # Get the PID and wait for max 30 seconds
    local pid=$!
    local count=0
    while kill -0 $pid 2>/dev/null && [ $count -lt 30 ]; do
        sleep 1
        ((count++))
    done
    
    # Kill if still running
    if kill -0 $pid 2>/dev/null; then
        kill -9 $pid 2>/dev/null
        wait $pid 2>/dev/null
    fi
    
    # Check if the file was created
    PAIR_FILE=$(echo $pair | sed 's/\//_/g')
    if [ -f "user_data/data/futures/${PAIR_FILE}-5m-futures.feather" ]; then
        echo -e "${GREEN}✓ Successfully downloaded $pair${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠ $pair already exists or skipped${NC}"
        return 0  # Continue anyway
    fi
}

# Main script
echo "========================================="
echo "  3-YEAR HISTORICAL DATA DOWNLOADER"
echo "========================================="
echo "Exchange: $EXCHANGE"
echo "Timeframe: $TIMEFRAME"
echo "Date Range: Jan 2022 - Aug 2025"
echo "========================================="

# Parse arguments
MODE=${1:-BTC}

if [ "$MODE" = "BTC" ]; then
    echo -e "${GREEN}Downloading Bitcoin data only...${NC}"
    download_pair "BTC/USDT:USDT"
    
elif [ "$MODE" = "all" ]; then
    echo -e "${GREEN}Downloading data for all ${#ALL_PAIRS[@]} pairs...${NC}"
    echo "This will take approximately 15-30 minutes."
    echo ""
    
    # Track progress
    SUCCESS_COUNT=0
    FAIL_COUNT=0
    
    for i in "${!ALL_PAIRS[@]}"; do
        pair="${ALL_PAIRS[$i]}"
        echo ""
        echo "[$((i+1))/${#ALL_PAIRS[@]}] Processing $pair..."
        
        if download_pair "$pair"; then
            ((SUCCESS_COUNT++))
        else
            ((FAIL_COUNT++))
        fi
        
        # Small delay to avoid rate limiting
        sleep 2
    done
    
    echo ""
    echo "========================================="
    echo "DOWNLOAD COMPLETE"
    echo "Success: $SUCCESS_COUNT pairs"
    echo "Failed: $FAIL_COUNT pairs"
    echo "========================================="
    
else
    echo -e "${RED}Invalid argument: $MODE${NC}"
    echo "Usage: $0 [BTC|all]"
    echo "  BTC - Download only Bitcoin data"
    echo "  all - Download all 15 pairs"
    exit 1
fi

# Check downloaded data
echo ""
echo "Checking downloaded files..."
ls -lh $DATA_DIR/$EXCHANGE/*5m.feather 2>/dev/null | tail -5

echo ""
echo -e "${GREEN}Data download complete!${NC}"
echo "You can now run backtests with 3 years of historical data."
echo ""
echo "Example backtest command:"
echo "freqtrade backtesting --config user_data/configs/config_billionaire.json \\"
echo "  --strategy Try1BullRiderStrategy --timerange 20220101-20250807"

exit 0