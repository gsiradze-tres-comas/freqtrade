#!/bin/bash

# Download All Try1 Data Script
# Downloads 30 days of 1m data for all 15 crypto pairs used in successful try1 bot
# With progress tracking and error handling

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DAYS=30
TIMEFRAME="1m"
EXCHANGE="binance"
CONFIG_FILE="user_data/configs/config_hft_optimized.json"

# All 15 crypto pairs from successful try1 bot
PAIRS=(
    "BTC/USDT:USDT"
    "ETH/USDT:USDT" 
    "BNB/USDT:USDT"
    "SOL/USDT:USDT"
    "ADA/USDT:USDT"
    "DOT/USDT:USDT"
    "MATIC/USDT:USDT"
    "LINK/USDT:USDT"
    "AVAX/USDT:USDT"
    "UNI/USDT:USDT"
    "LTC/USDT:USDT"
    "ATOM/USDT:USDT"
    "XRP/USDT:USDT"
    "ALGO/USDT:USDT"
    "FTM/USDT:USDT"
)

echo -e "${BLUE}🚀 Try1 Data Download Script${NC}"
echo -e "${BLUE}=============================${NC}"
echo -e "📊 Downloading ${DAYS} days of ${TIMEFRAME} data for ${#PAIRS[@]} pairs"
echo -e "🏪 Exchange: ${EXCHANGE}"
echo -e "⏰ Started at: $(date)"
echo ""

# Check if freqtrade command exists
if ! command -v freqtrade &> /dev/null; then
    echo -e "${RED}❌ Error: freqtrade command not found${NC}"
    echo "Please make sure freqtrade is installed and in your PATH"
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Error: Config file not found: $CONFIG_FILE${NC}"
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p user_data/logs

# Progress tracking variables
TOTAL_PAIRS=${#PAIRS[@]}
SUCCESSFUL_DOWNLOADS=0
FAILED_DOWNLOADS=0
START_TIME=$(date +%s)

# Function to show progress
show_progress() {
    local current=$1
    local total=$2
    local percentage=$((current * 100 / total))
    local bar_length=30
    local filled_length=$((percentage * bar_length / 100))
    
    printf "\r${BLUE}Progress: ["
    printf "%*s" $filled_length | tr ' ' '='
    printf "%*s" $((bar_length - filled_length)) | tr ' ' '-'
    printf "] %d%% (%d/%d)${NC}" $percentage $current $total
}

# Function to download data for a single pair
download_pair() {
    local pair=$1
    local pair_clean=$(echo "$pair" | tr '/' '_' | tr ':' '_')
    local log_file="user_data/logs/download_${pair_clean}.log"
    
    echo -e "\n${YELLOW}📈 Downloading: $pair${NC}"
    
    if freqtrade download-data \
        --exchange "$EXCHANGE" \
        --pairs "$pair" \
        --timeframe "$TIMEFRAME" \
        --days "$DAYS" \
        --config "$CONFIG_FILE" \
        > "$log_file" 2>&1; then
        
        echo -e "${GREEN}✅ Success: $pair${NC}"
        return 0
    else
        echo -e "${RED}❌ Failed: $pair${NC}"
        echo -e "${RED}   See log: $log_file${NC}"
        return 1
    fi
}

# Download data for each pair
echo -e "${BLUE}Starting downloads...${NC}\n"

for i in "${!PAIRS[@]}"; do
    pair="${PAIRS[$i]}"
    current_num=$((i + 1))
    
    show_progress $current_num $TOTAL_PAIRS
    
    if download_pair "$pair"; then
        ((SUCCESSFUL_DOWNLOADS++))
    else
        ((FAILED_DOWNLOADS++))
    fi
    
    # Small delay to avoid rate limiting
    sleep 1
done

# Final progress
echo -e "\n"
show_progress $TOTAL_PAIRS $TOTAL_PAIRS

# Calculate total time
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
MINUTES=$((TOTAL_TIME / 60))
SECONDS=$((TOTAL_TIME % 60))

# Final summary
echo -e "\n\n${BLUE}📊 Download Summary${NC}"
echo -e "${BLUE}===================${NC}"
echo -e "✅ Successful: ${GREEN}$SUCCESSFUL_DOWNLOADS${NC}/$TOTAL_PAIRS pairs"
echo -e "❌ Failed: ${RED}$FAILED_DOWNLOADS${NC}/$TOTAL_PAIRS pairs"
echo -e "⏰ Total time: ${MINUTES}m ${SECONDS}s"
echo -e "🏁 Completed at: $(date)"

# Show data directory info
if [ -d "user_data/data/$EXCHANGE" ]; then
    echo -e "\n${BLUE}📁 Data Directory Info:${NC}"
    echo -e "Location: user_data/data/$EXCHANGE"
    echo -e "Files created: $(find user_data/data/$EXCHANGE -name "*.feather" | wc -l)"
    echo -e "Total size: $(du -sh user_data/data/$EXCHANGE | cut -f1)"
fi

# Check for failed downloads
if [ $FAILED_DOWNLOADS -gt 0 ]; then
    echo -e "\n${YELLOW}⚠️  Some downloads failed. Check log files in user_data/logs/${NC}"
    echo -e "${YELLOW}You can re-run this script to retry failed downloads.${NC}"
    exit 1
else
    echo -e "\n${GREEN}🎉 All downloads completed successfully!${NC}"
    echo -e "${GREEN}You can now run backtests with the complete dataset.${NC}"
fi