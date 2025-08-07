#!/bin/bash

# 📊 Monitor Try1BullRiderStrategy Live Performance
# Shows real-time stats from PostgreSQL database

echo "📊 Try1BullRiderStrategy Live Performance Monitor"
echo "================================================"
echo ""

# Calculate bot runtime
echo "⏱️  BOT RUNTIME:"
python3 -c "
import psycopg2
from datetime import datetime
try:
    conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db')
    cur = conn.cursor()
    cur.execute('SELECT MIN(open_date), MAX(COALESCE(close_date, open_date)) FROM trades')
    result = cur.fetchone()
    if result[0]:
        start_time = result[0]
        last_time = result[1]
        duration = last_time - start_time
        hours = duration.total_seconds() / 3600
        print(f'   Running for: {hours:.1f} hours')
        print(f'   Started at: {start_time.strftime(\"%Y-%m-%d %H:%M\")}')
    else:
        print('   No trades yet')
    conn.close()
except Exception as e:
    print(f'   Error: {e}')
"
echo ""

echo "📈 CURRENT PERFORMANCE:"

# Total trades
echo "🔢 Total Trades:"
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM trades')
    print(f'   {cur.fetchone()[0]} trades executed')
    conn.close()
except: print('   Database connection failed')
"

# Win rate and profit
echo ""
echo "💰 Profit & Win Rate:"
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db')
    cur = conn.cursor()
    
    # Win rate
    cur.execute(\"SELECT COUNT(*) FROM trades WHERE close_profit > 0 AND is_open = false\")
    wins = cur.fetchone()[0]
    cur.execute(\"SELECT COUNT(*) FROM trades WHERE is_open = false\")
    total_closed = cur.fetchone()[0]
    
    if total_closed > 0:
        win_rate = (wins / total_closed) * 100
        print(f'   Win Rate: {win_rate:.1f}% ({wins}/{total_closed})')
    else:
        print('   Win Rate: No closed trades yet')
    
    # Total profit in USDT (using close_profit_abs for actual USDT amount)
    cur.execute(\"SELECT SUM(close_profit_abs) FROM trades WHERE is_open = false\")
    result = cur.fetchone()[0]
    total_profit = result if result else 0
    print(f'   Total Profit: {total_profit:.2f} USDT')
    
    # Average profit percentage  
    cur.execute(\"SELECT AVG(close_profit * 100) FROM trades WHERE is_open = false\")
    result = cur.fetchone()[0]
    avg_profit_pct = result if result else 0
    print(f'   Avg Profit/Trade: {avg_profit_pct:.2f}%')
    
    conn.close()
except Exception as e: 
    print(f'   Database error: {e}')
"

# Recent trades
echo ""
echo "📋 Recent Trades (Last 10):"
python3 -c "
import psycopg2
try:
    conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db')
    cur = conn.cursor()
    cur.execute(\"\"\"
        SELECT pair, open_date, close_date, close_profit_abs, close_profit * 100, is_open 
        FROM trades 
        ORDER BY id DESC 
        LIMIT 10
    \"\"\")
    
    trades = cur.fetchall()
    if trades:
        for trade in trades:
            pair, open_date, close_date, profit_abs, profit_pct, is_open = trade
            status = 'OPEN' if is_open else 'CLOSED'
            if is_open:
                print(f'   {pair:<15} {status:<7} (in progress)')
            else:
                profit_str = f'{profit_abs:.2f}' if profit_abs else '0.00'
                pct_str = f'{profit_pct:.2f}' if profit_pct else '0.00'
                print(f'   {pair:<15} {status:<7} +${profit_str:>7} ({pct_str:>5}%)')
    else:
        print('   No trades yet')
    
    conn.close()
except Exception as e: 
    print(f'   Database error: {e}')
"

echo ""

# Performance Summary
echo "📊 PERFORMANCE SUMMARY:"
python3 -c "
import psycopg2
from datetime import datetime
try:
    conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db')
    cur = conn.cursor()
    
    # Get total profit and trade count
    cur.execute('SELECT SUM(close_profit_abs), COUNT(*) FROM trades WHERE is_open = false')
    total_profit, closed_trades = cur.fetchone()
    total_profit = total_profit or 0
    
    # Get runtime in hours
    cur.execute('SELECT MIN(open_date), MAX(COALESCE(close_date, open_date)) FROM trades')
    result = cur.fetchone()
    if result[0]:
        duration_hours = (result[1] - result[0]).total_seconds() / 3600
        
        # Calculate hourly profit rate
        if duration_hours > 0:
            hourly_rate = total_profit / duration_hours
            daily_projection = hourly_rate * 24
            
            print(f'   💵 Hourly Profit Rate: \${hourly_rate:.2f}/hour')
            print(f'   📈 Daily Projection: \${daily_projection:.2f}/day')
            print(f'   🎯 Monthly Projection: \${daily_projection * 30:.2f}/month')
            
            # Compare to target
            if closed_trades > 5:  # Only show comparison after enough trades
                trades_per_day = (closed_trades / duration_hours) * 24
                print(f'   📊 Trade Frequency: {trades_per_day:.1f} trades/day')
    
    conn.close()
except Exception as e:
    print(f'   Error: {e}')
"

echo ""
echo "🌐 Web UI: http://127.0.0.1:8080 (freqtrade/freqtrade)"
echo "📝 Live logs: tail -f user_data/logs/freqtrade_hft.log"
echo "⏹️  Stop bot: ./kill_script.sh"
echo ""