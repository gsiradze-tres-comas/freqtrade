#!/bin/bash

# Quick script to open the latest backtest visualizations in browser

echo "🎯 Opening Backtest Visualization Charts..."

# Find the most recent visualization files
RESULTS_DIR="user_data/visualization_results"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "❌ Visualization results directory not found: $RESULTS_DIR"
    exit 1
fi

# Find latest comprehensive analysis file
COMPREHENSIVE=$(ls -t "$RESULTS_DIR"/backtest_analysis_*.html 2>/dev/null | head -1)
# Find latest timeline file  
TIMELINE=$(ls -t "$RESULTS_DIR"/trade_timeline_*.html 2>/dev/null | head -1)

if [ -z "$COMPREHENSIVE" ] && [ -z "$TIMELINE" ]; then
    echo "❌ No visualization files found in $RESULTS_DIR"
    echo "💡 Run: python scripts/tick_data/create_backtest_visualizations.py"
    exit 1
fi

echo "📊 Found visualization files:"
if [ -n "$COMPREHENSIVE" ]; then
    echo "   - Comprehensive Analysis: $(basename "$COMPREHENSIVE")"
fi
if [ -n "$TIMELINE" ]; then
    echo "   - Trade Timeline: $(basename "$TIMELINE")"
fi

echo ""
echo "🚀 Opening in your default browser..."

# Open files in browser (works on macOS, Linux, Windows)
if [ -n "$COMPREHENSIVE" ]; then
    if command -v open >/dev/null 2>&1; then
        # macOS
        open "$COMPREHENSIVE"
    elif command -v xdg-open >/dev/null 2>&1; then
        # Linux
        xdg-open "$COMPREHENSIVE"
    elif command -v start >/dev/null 2>&1; then
        # Windows
        start "$COMPREHENSIVE"
    else
        echo "📄 Comprehensive Analysis: file://$(realpath "$COMPREHENSIVE")"
    fi
fi

if [ -n "$TIMELINE" ]; then
    if command -v open >/dev/null 2>&1; then
        # macOS
        open "$TIMELINE"
    elif command -v xdg-open >/dev/null 2>&1; then
        # Linux  
        xdg-open "$TIMELINE"
    elif command -v start >/dev/null 2>&1; then
        # Windows
        start "$TIMELINE"
    else
        echo "📄 Trade Timeline: file://$(realpath "$TIMELINE")"
    fi
fi

echo ""
echo "✅ Charts opened! You should see interactive Plotly visualizations showing:"
echo "   📈 Price action with entry/exit markers"
echo "   💰 Balance curve and drawdown analysis" 
echo "   📊 Trade P&L distribution"
echo "   ⏱️ Trade timeline with duration"
echo "   📋 Performance metrics summary"