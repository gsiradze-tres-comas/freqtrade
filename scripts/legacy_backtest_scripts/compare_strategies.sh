#!/bin/bash
#
# Strategy Comparison Backtesting
# Runs both strategies with identical parameters for direct comparison.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${PURPLE}=================================================================================${NC}"
echo -e "${PURPLE}⚔️  STRATEGY COMPARISON BACKTESTING${NC}"
echo -e "${PURPLE}=================================================================================${NC}"
echo -e "${GREEN}🛡️  SafeBullRiderStrategy vs 🚀 Try1BullRiderStrategy${NC}"
echo -e "${GREEN}✅ Uses Freqtrade's native engine for both${NC}"
echo -e "${GREEN}✅ Identical parameters for fair comparison${NC}"
echo -e "${PURPLE}=================================================================================${NC}"

# Default parameters
TIMERANGE="20240811-20250810"  # Full year
TIMEFRAME="5m"
FEE="0.001"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --timerange)
            TIMERANGE="$2"
            shift 2
            ;;
        --short)
            TIMERANGE="20250701-20250731"
            echo -e "${YELLOW}📅 Using short timerange: $TIMERANGE${NC}"
            shift
            ;;
        --recent)
            TIMERANGE="20250801-20250810"
            echo -e "${YELLOW}📅 Using recent timerange: $TIMERANGE${NC}"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --timerange RANGE    Date range (default: full year)"
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

echo -e "${BLUE}📊 Comparison Configuration:${NC}"
echo -e "  • Timerange: $TIMERANGE"
echo -e "  • Timeframe: $TIMEFRAME"
echo -e "  • Trading Fee: ${FEE}%"
echo -e ""

# Create timestamp for this comparison
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo -e "${YELLOW}🔄 Running Strategy Comparison...${NC}"
echo -e ""

# Run SafeBullRiderStrategy
echo -e "${BLUE}=================================================================================${NC}"
echo -e "${BLUE}🛡️  STEP 1: Running SafeBullRiderStrategy${NC}"
echo -e "${BLUE}=================================================================================${NC}"

freqtrade backtesting \
    --config user_data/configs/config_safe_bull.json \
    --strategy SafeBullRiderStrategy \
    --timerange $TIMERANGE \
    --timeframe $TIMEFRAME \
    --fee $FEE \
    --enable-protections \
    --breakdown day week month \
    --export trades \
    --export-filename user_data/backtest_results/safe_strategy_comparison_$TIMESTAMP

echo -e ""

# Run Try1BullRiderStrategy  
echo -e "${BLUE}=================================================================================${NC}"
echo -e "${BLUE}🚀 STEP 2: Running Try1BullRiderStrategy${NC}"
echo -e "${BLUE}=================================================================================${NC}"

freqtrade backtesting \
    --config user_data/configs/config_billionaire.json \
    --strategy Try1BullRiderStrategy \
    --timerange $TIMERANGE \
    --timeframe $TIMEFRAME \
    --fee $FEE \
    --enable-protections \
    --breakdown day week month \
    --export trades \
    --export-filename user_data/backtest_results/original_strategy_comparison_$TIMESTAMP

echo -e ""
echo -e "${PURPLE}=================================================================================${NC}"
echo -e "${GREEN}✅ STRATEGY COMPARISON COMPLETE!${NC}"
echo -e "${PURPLE}=================================================================================${NC}"

echo -e ""
echo -e "${BLUE}📊 Comparison Summary:${NC}"
echo -e ""
echo -e "${GREEN}🛡️  SafeBullRiderStrategy Features:${NC}"
echo -e "  • Daily loss limits (3% max)"
echo -e "  • Time restrictions (2-4 AM blocked)"
echo -e "  • Weekend filter enabled"
echo -e "  • Market risk checks"
echo -e "  • Volatility filters"
echo -e "  • Dynamic stop losses"
echo -e "  • Emergency exits"
echo -e "  • Max 7 positions (5 in drawdown)"
echo -e ""
echo -e "${RED}🚀 Try1BullRiderStrategy Features:${NC}"
echo -e "  • No safety limits"
echo -e "  • No time restrictions"
echo -e "  • No market condition filters"
echo -e "  • Fixed 4% stop loss"
echo -e "  • Max 15 positions"
echo -e "  • Higher profit potential"
echo -e "  • Higher risk exposure"
echo -e ""
echo -e "${YELLOW}📊 Results Location:${NC}"
echo -e "  Safe Strategy: user_data/backtest_results/safe_strategy_comparison_$TIMESTAMP*"
echo -e "  Original Strategy: user_data/backtest_results/original_strategy_comparison_$TIMESTAMP*"
echo -e ""
echo -e "${YELLOW}🔍 Key Metrics to Compare:${NC}"
echo -e "  • Total Return (%)"
echo -e "  • Maximum Drawdown (%)"
echo -e "  • Win Rate (%)"
echo -e "  • Profit Factor"
echo -e "  • Sharpe Ratio"
echo -e "  • Number of Trades"
echo -e "  • Average Trade Duration"
echo -e ""
echo -e "${BLUE}💡 Analysis Tips:${NC}"
echo -e "  • SafeBullRiderStrategy should have LOWER drawdown"
echo -e "  • SafeBullRiderStrategy should have FEWER trades"
echo -e "  • SafeBullRiderStrategy should have BETTER risk-adjusted returns"
echo -e "  • Original strategy may have HIGHER absolute returns"
echo -e "  • Compare performance during market downturns"