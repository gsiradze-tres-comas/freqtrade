#!/bin/bash

# Download 3 years of historical data for backtesting
# Batch version with better error handling

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

# All pairs in one command for efficiency
ALL_PAIRS="BTC/USDT:USDT,ETH/USDT:USDT,DOGE/USDT:USDT,ADA/USDT:USDT,XRP/USDT:USDT,SOL/USDT:USDT,AVAX/USDT:USDT,LINK/USDT:USDT,BNB/USDT:USDT,BCH/USDT:USDT,TIA/USDT:USDT,DOT/USDT:USDT,UNI/USDT:USDT,1INCH/USDT:USDT"

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
    PAIRS="BTC/USDT:USDT"
elif [ "$MODE" = "all" ]; then
    echo -e "${GREEN}Downloading data for all 15 pairs...${NC}"
    echo "This will download all pairs in a single batch."
    PAIRS=$ALL_PAIRS
else
    echo -e "${RED}Invalid argument: $MODE${NC}"
    echo "Usage: $0 [BTC|all]"
    exit 1
fi

# Check if we need to erase existing data
echo ""
echo "Checking existing data..."
if [ -d "user_data/data/futures" ] && [ "$(ls -A user_data/data/futures/*.feather 2>/dev/null | wc -l)" -gt 0 ]; then
    echo -e "${YELLOW}Found existing data files. Using --erase to redownload fresh data.${NC}"
    ERASE_FLAG="--erase"
else
    ERASE_FLAG=""
fi

# Download all pairs in one command
echo ""
echo "Starting download..."
freqtrade download-data \
    --exchange $EXCHANGE \
    --pairs $PAIRS \
    --timeframe $TIMEFRAME \
    --timerange ${START_DATE}-${END_DATE} \
    --datadir $DATA_DIR \
    --data-format-ohlcv feather \
    --trading-mode futures \
    $ERASE_FLAG

# Check results
echo ""
echo "========================================="
echo "Checking downloaded files..."
echo "========================================="

if [ -d "user_data/data/futures" ]; then
    echo "Futures data:"
    ls -lh user_data/data/futures/*5m*.feather 2>/dev/null | head -15
    
    # Count files
    FILE_COUNT=$(ls user_data/data/futures/*5m*.feather 2>/dev/null | wc -l)
    echo ""
    echo -e "${GREEN}Downloaded $FILE_COUNT pairs successfully!${NC}"
else
    echo -e "${RED}No data found in futures directory${NC}"
fi

echo ""
echo "========================================="
echo -e "${GREEN}Data download complete!${NC}"
echo "========================================="
echo ""
echo "You can now run comprehensive backtests:"
echo ""
echo "Example - Test full 3 years:"
echo "freqtrade backtesting --config user_data/configs/config_billionaire.json \\"
echo "  --strategy Try1BullRiderStrategy --timerange 20220101-20250807"
echo ""
echo "Example - Test 2022 bear market:"
echo "freqtrade backtesting --config user_data/configs/config_billionaire.json \\"
echo "  --strategy Try1BullRiderStrategy --timerange 20220101-20221231"
echo ""
echo "Example - Test 2024-2025 bull market:"
echo "freqtrade backtesting --config user_data/configs/config_billionaire.json \\"
echo "  --strategy Try1BullRiderStrategy --timerange 20240101-20250807"

exit 0