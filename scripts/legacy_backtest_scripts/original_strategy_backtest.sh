#!/bin/bash
#
# Try1BullRiderStrategy Native Backtesting
# Uses Freqtrade's built-in engine for the original aggressive strategy.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================================================================${NC}"
echo -e "${BLUE}🚀 TRY1BULLRIDERSTRATEGY NATIVE BACKTESTING${NC}"
echo -e "${BLUE}=================================================================================${NC}"
echo -e "${GREEN}✅ Uses Freqtrade's built-in engine${NC}"
echo -e "${GREEN}✅ Original aggressive strategy${NC}"
echo -e "${RED}⚠️  No safety features (for comparison)${NC}"
echo -e "${BLUE}=================================================================================${NC}"

# Default parameters
TIMERANGE="20240811-20250810"  # Full year
TIMEFRAME="5m"
FEE="0.001"  # 0.1% Binance fee

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --timerange)
            TIMERANGE="$2"
            shift 2
            ;;
        --timeframe)
            TIMEFRAME="$2"
            shift 2
            ;;
        --short)
            TIMERANGE="20250701-20250731"  # Just last month
            echo -e "${YELLOW}📅 Using short timerange: $TIMERANGE${NC}"
            shift
            ;;
        --recent)
            TIMERANGE="20250801-20250810"  # Just last 10 days
            echo -e "${YELLOW}📅 Using recent timerange: $TIMERANGE${NC}"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --timerange RANGE    Date range (default: full year 20240811-20250810)"
            echo "  --timeframe TF       Timeframe (default: 5m)"
            echo "  --short             Use last month only"
            echo "  --recent            Use last 10 days only"
            echo "  -h, --help          Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}📊 Configuration:${NC}"
echo -e "  • Strategy: Try1BullRiderStrategy (original)"
echo -e "  • Config: user_data/configs/config_billionaire.json"
echo -e "  • Timerange: $TIMERANGE"
echo -e "  • Timeframe: $TIMEFRAME"
echo -e "  • Trading Fee: ${FEE}%"
echo -e ""

# Check if config exists
if [ ! -f "user_data/configs/config_billionaire.json" ]; then
    echo -e "${RED}❌ Configuration file not found: user_data/configs/config_billionaire.json${NC}"
    exit 1
fi

# Check if strategy exists
if [ ! -f "user_data/strategies/Try1BullRiderStrategy.py" ]; then
    echo -e "${RED}❌ Strategy file not found: user_data/strategies/Try1BullRiderStrategy.py${NC}"
    exit 1
fi

echo -e "${YELLOW}🔄 Running Try1BullRiderStrategy backtest...${NC}"
echo -e "${BLUE}=================================================================================${NC}"

# Run the backtest using Freqtrade's native engine
freqtrade backtesting \
    --config user_data/configs/config_billionaire.json \
    --strategy Try1BullRiderStrategy \
    --timerange $TIMERANGE \
    --timeframe $TIMEFRAME \
    --fee $FEE \
    --enable-protections \
    --breakdown day week month \
    --export trades \
    --export-filename user_data/backtest_results/original_strategy_$(date +%Y%m%d_%H%M%S)

echo -e "${BLUE}=================================================================================${NC}"
echo -e "${GREEN}✅ Backtest complete!${NC}"
echo -e ""
echo -e "${RED}⚠️ Original Strategy Characteristics:${NC}"
echo -e "  • High profit potential"
echo -e "  • No daily loss limits"
echo -e "  • No time restrictions"
echo -e "  • No safety filters"
echo -e "  • Higher risk profile"
echo -e ""
echo -e "${YELLOW}📊 Results saved to: user_data/backtest_results/${NC}"