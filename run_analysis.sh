#!/bin/bash

# FreqTrade Analysis Script
# Run this and paste ALL output back to Claude

echo "🚀 Starting Comprehensive FreqTrade Analysis"
echo "============================================="
echo ""

# 1. Plot dataframe with indicators and trades
echo "📊 Creating visual plots..."
freqtrade plot-dataframe \
    --config user_data/configs/config_safe_bull.json \
    --strategy BeastModeStrategy \
    --timerange 20240601-20250630 \
    --plot-limit 100

echo ""
echo "📈 Creating profit plots..."
freqtrade plot-profit \
    --config user_data/configs/config_safe_bull.json \
    --timerange 20240601-20250630

echo ""
echo "📋 Running detailed backtesting analysis..."
freqtrade backtesting-analysis \
    --config user_data/configs/config_safe_bull.json \
    --analysis-groups 0 1 2 3 4

echo ""
echo "📊 Show trade analysis..."
freqtrade show-trades \
    --config user_data/configs/config_safe_bull.json \
    --timerange 20240601-20250630 \
    --print-json

echo ""
echo "✅ Analysis Complete!"
echo "📁 Check user_data/plot/ directory for visual charts"
echo "🔍 Paste ALL output above back to Claude for analysis"