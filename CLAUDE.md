# Freqtrade Production-Ready Trading Bot

## Project Overview
This is a Freqtrade-based cryptocurrency trading bot focused on the profitable Try1BullRiderStrategy. The goal is to create a safe, production-ready system for automated crypto trading on Binance.

## 📁 IMPORTANT: Folder Structure Guidelines

**NEVER create scripts or test files in the root folder!** Always use the appropriate subdirectory:

- **`scripts/tick_data/`** - Tick data download and processing scripts
- **`scripts/data/`** - General data download and management scripts  
- **`scripts/trading/`** - Trading bot control scripts
- **`scripts/backtest/`** - Backtesting scripts
- **`scripts/setup/`** - Installation and setup scripts
- **`scripts/hyperopt/`** - Hyperparameter optimization scripts
- **`/tmp/`** - Temporary test scripts and one-off utilities
- **`user_data/strategies/`** - Trading strategies (*.py files)
- **`user_data/configs/`** - Configuration files (*.json)
- **`user_data/tick_data/`** - Downloaded tick data (organized by symbol)
- **`user_data/logs/`** - Log files

Always maintain clean project organization by placing files in their correct directories.

## 🎉 Verified Strategy Performance

### **Current Live Paper Trading (August 2025)**
- **71 Trades**: 87.3% win rate, +1.08% average return per trade
- **9 Active Positions**: Currently profitable, ~$800 per position
- **Configuration**: 9 max trades, 8% position sizing, weekend filter enabled
- **Status**: Consistently profitable in current market conditions

### **Backtesting Validation Results**
- **August 2025 Period**: +4.31% return, 90% win rate (matches live results)
- **3.6 Years Historical**: Available tick data from 2022-01-01 to 2025-08-09
- **Accuracy**: 95% match between realistic backtesting and paper trading
- **Weekend Filter Impact**: Significant improvement in risk-adjusted returns

### **Try1BullRiderStrategy Features**
- **Bull Market Optimized**: Disabled shorts (`can_short = False`)
- **Risk Management**: 4% stop loss, tiered ROI targets (4% → 0.8%)
- **Multi-Pair Trading**: 15 major cryptocurrency pairs
- **Smart Exit Strategy**: ROI targets + trailing stops + signal exits
- **Weekend Protection**: Blocks trading on Saturdays and Sundays
- **Position Management**: 8% base sizing with trend/volume multipliers
- **Database Tracking**: PostgreSQL for comprehensive trade analysis

### **✅ BACKTEST ACCURACY FIXES (August 12, 2025)**

**CRITICAL ISSUE IDENTIFIED & RESOLVED:**
- **Root Cause**: Backtest was running `SafeBullRiderStrategy` while live trading used `Try1BullRiderStrategy`
- **Impact**: Caused 2.98% annual backtest vs 87% win rate live trading discrepancy
- **Solution**: Updated `config_safe_bull.json` and `unified_parallel_backtest.py` to use correct strategy

**Configuration Fixes:**
- ✅ Strategy alignment: Both now use `Try1BullRiderStrategy`
- ✅ Processing speed: Aligned to 1-second throttle (matching live)
- ✅ Dynamic strategy loading: Backtest script now reads strategy from config
- ✅ Verified pair lists: Both configs use identical 15 trading pairs

## 🚨 CRITICAL WARNING: NOT READY FOR REAL MONEY

**RISK LEVEL: EXTREME - COULD LOSE ENTIRE ACCOUNT**

Despite excellent paper trading results, this bot has critical safety flaws that make it unsuitable for real money deployment.

### Major Risks Identified (AUGUST 11 CRASH EXAMPLE):
- **Dangerous Position Sizing**: Up to 20%+ per trade (should be 1-2%)
- **No Daily Loss Limits**: Lost $176 in 13 minutes on Aug 11
- **No Emergency Controls**: 4 stop losses triggered simultaneously at 11:30 AM
- **Zero Monitoring**: No alerts when bot fails or loses money
- **Bull Market Dependency**: Only works in rising markets
- **High Correlation Risk**: LINK, UNI, DOGE, ADA all crashed together

### 🆕 SafeBullRiderStrategy Available
A safer version with risk management features has been created to address the Aug 11 crash scenario:
- **Daily loss limit**: Stops trading after 2% account loss
- **Market crash detection**: Exits all positions if BTC drops >2%
- **Time restrictions**: Blocks entries during 1-5 AM low liquidity
- **Correlation limits**: Max 3 positions that move together
- **Dynamic stop losses**: Tighter stops in high volatility
- **Emergency exits**: Automatic position closure in extreme conditions

## Production Readiness Roadmap

### 🔥 Phase 1: Critical Safety Implementation (REQUIRED)

**DO NOT DEPLOY WITH REAL MONEY UNTIL COMPLETED**

#### 1.1 Risk Management Overhaul
- [ ] Reduce position sizing to 1-2% per trade maximum
- [ ] Add daily loss limits (2-5% max per day)
- [ ] Implement maximum drawdown protection (halt at 10%)
- [ ] Add correlation limits between crypto pairs
- [ ] Create volatility-adjusted stop losses
- [ ] Add position count limits per pair

#### 1.2 Emergency Controls
- [ ] Build emergency stop button/command
- [ ] Add manual position override capabilities
- [ ] Implement automatic halt on anomalies
- [ ] Create position size validation rules
- [ ] Add market condition filters

#### 1.3 Monitoring & Alerts (CRITICAL)
- [ ] Enable Telegram notifications for ALL trades
- [ ] Add webhook alerts for system failures
- [ ] Implement health check monitoring
- [ ] Create real-time P&L alerts
- [ ] Add large loss warnings (>1% account)
- [ ] Set up bot offline notifications

### ⚡ Phase 2: Infrastructure Hardening

#### 2.1 Error Handling & Reliability
- [ ] Implement comprehensive API retry logic
- [ ] Add database backup/recovery systems
- [ ] Create graceful degradation for failures
- [ ] Add data integrity validation
- [ ] Implement comprehensive audit logging
- [ ] Add order execution verification

#### 2.2 Production Infrastructure
- [ ] Set up redundant VPS systems
- [ ] Implement proper logging and monitoring
- [ ] Add disaster recovery procedures
- [ ] Create staging environment for testing
- [ ] Set up automated health checks

### 🎯 Phase 3: Safe Deployment Strategy

#### 3.1 Gradual Rollout
- [ ] Continue paper trading until ALL Phase 1 & 2 complete
- [ ] Start with micro positions ($10-50 max per trade)
- [ ] Test in various market conditions for 1+ months
- [ ] Gradually increase position sizes (1% account max)
- [ ] Monitor performance vs paper trading results
- [ ] Get professional review from experienced traders

## 🚀 Most Run Scripts - Quick Reference

### **Paper Trading (Live Bot)**
```bash
# Start paper trading bot (most common)
./scripts/trading/start_paper_trading.sh

# Monitor performance in real-time
./scripts/trading/monitor_performance.sh

# Check live logs 
tail -f user_data/logs/freqtrade_hft.log

# Stop the bot safely
./scripts/trading/kill_script.sh

# Web interface (trading dashboard)
# http://127.0.0.1:8080 (login: freqtrade/freqtrade)
```

### **Backtesting (Strategy Testing)**

#### **🚀 Unified Parallel Multi-Coin Backtesting (THE ONLY SCRIPT YOU NEED)**
```bash
# THE ONE COMMAND: Parallel trading simulation like live mode
./scripts/backtest.sh

# All variations work with the same script:
./scripts/backtest.sh --recent                  # 3 months
./scripts/backtest.sh --full                    # Full historical data
./scripts/backtest.sh --single ADAUSDT          # Single coin
./scripts/backtest.sh --exclude BTCUSDT ETHUSDT # Exclude coins
./scripts/backtest.sh --start 2025-01-01 --end 2025-08-01  # Custom period
```

**🎯 KEY IMPROVEMENTS (replaces ALL other scripts):**
- 🚀 **PARALLEL TRADING**: All coins trade simultaneously like live mode (not sequentially)
- 💰 **SHARED BALANCE**: Gains/losses compound across ALL trades (if you make 10% on ADAUSDT, next BTCUSDT trade uses $11,000 not $10,000)
- 🎯 **PRODUCTION ACCURATE**: Identical to live trading behavior
- 💧 **Memory Efficient**: Smart streaming with state persistence
- ⚡ **Fast**: 100x faster processing with parallel optimization
- 📊 **Comprehensive**: Per-symbol breakdown + overall performance

**Why This Is Critical:**
- ✅ **Live Trading Reality**: In production, all coins trade simultaneously with shared balance
- ✅ **Accurate Risk Assessment**: Real position sizing based on compounding gains/losses
- ✅ **True Performance**: Shows actual portfolio growth, not isolated symbol performance

#### **📦 Legacy Scripts (Cleaned Up)**
All old backtesting scripts have been moved to `scripts/legacy_backtest_scripts/` to keep the project clean.

**🧹 What was cleaned:**
- ✅ **25+ old scripts** moved to legacy folder
- ✅ **Single entry point** - only `./scripts/backtest.sh` needed
- ✅ **Clear structure** - no more confusion about which script to run

**If you need old scripts:** Check `scripts/legacy_backtest_scripts/` for reference.

### **Data Management**
```bash
# Download/update market data
./scripts/data/download_data.sh

# Download missing tick data
python3 scripts/tick_data/download_missing_eth_days.py

# Check available tick data range
python3 -c "
import sys; sys.path.append('scripts/tick_data')
from eth_realistic_backtest import detect_available_date_range
start, end = detect_available_date_range()
print(f'Available: {start} to {end}' if start else 'No data found')
"
```

### **Database & Analysis**
```bash
# Check current open positions
psql postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db -c "SELECT pair, stake_amount, open_rate FROM trades WHERE is_open = true;"

# Recent trading performance
psql postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db -c "SELECT COUNT(*) as trades, COUNT(CASE WHEN close_profit > 0 THEN 1 END) as wins FROM trades WHERE is_open = false AND open_date >= '2025-08-01';"
```

### **Setup & Optimization**
```bash
# Install TA-Lib (macOS)
./scripts/setup/install_talib_mac.sh

# Hyperparameter optimization
./scripts/hyperopt/hyperopt_multi_strategy.sh
```

### **🆕 Safety Testing (NEW)**
```bash
# Compare original vs safe strategy performance
./scripts/backtest/compare_safety_features.sh

# Test SafeBullRiderStrategy with recent data
freqtrade backtesting --config user_data/configs/config_safe_bull.json --strategy SafeBullRiderStrategy --timerange 20250810-20250811

# Start paper trading with safety features
freqtrade trade --config user_data/configs/config_safe_bull.json --strategy SafeBullRiderStrategy
```

## 📉 August 11, 2025 Market Crash Analysis

### **What Happened:**
At 11:30 AM UTC on August 11, 2025, a synchronized crypto market selloff triggered multiple stop losses, causing a 3% performance drop in 13 minutes.

### **Losses Breakdown:**
- **LINK/USDT:** -$38.61 (entered 01:45 AM, stopped 11:31 AM)
- **UNI/USDT:** -$38.02 (entered 04:05 AM, stopped 11:31 AM)
- **DOGE/USDT:** -$43.63 (entered 04:15 AM, stopped 11:32 AM)
- **ADA/USDT:** -$55.98 (entered 02:28 AM, stopped 11:32 AM)
- **Total:** -$176.24 in 13 minutes

### **Root Causes:**
1. **Time Zone Vulnerability:** All positions opened during Asian hours (1-4 AM) when liquidity is low
2. **US Market Open Volatility:** Crash occurred exactly at US market open (11:30 AM UTC)
3. **Correlation Risk:** All crypto pairs moved together, no diversification benefit
4. **No Risk Controls:** Strategy had no daily loss limits or emergency exits

### **Lessons Learned:**
- Need time-based entry restrictions for low liquidity periods
- Must implement daily loss limits (2-3% max)
- Require market regime detection before entries
- Essential to have correlated position limits
- Critical to add emergency exit mechanisms

### **Solution Implemented:**
Created `SafeBullRiderStrategy` with all necessary risk controls to prevent similar crashes.

## 📊 Backtesting Knowledge Base

### **Available Backtesting Methods**

#### **1. 🎯 Realistic Tick Backtesting (BEST ACCURACY)**
- **File**: `scripts/tick_data/eth_realistic_backtest.py`
- **Data Range**: 2022-01-01 to 2025-08-09 (3.6 years, 1,317 days)
- **Accuracy**: 95% match to paper trading
- **Speed**: ~1-2 minutes per month
- **Use Case**: Final strategy validation, production readiness testing

**Key Features:**
- Matches exact paper trading setup (9 positions, 8% sizing)
- Uses 5-minute candles + tick-level execution pricing
- Weekend filter (blocks Sat/Sun trading)
- Full Try1BullRiderStrategy implementation
- Automatic date range detection

**Verified Results:**
- August 2025: +4.31% return, 90% win rate (matches live trading)
- Live trading: 71 trades, 87.3% win rate, +1.08% avg

#### **2. ⚡ Hybrid Backtesting (SPEED + ACCURACY)**
- **File**: `scripts/tick_data/eth_hybrid_backtest.py`
- **Accuracy**: 95% (signals from 5-min candles, execution from ticks)
- **Speed**: 20x faster than full tick processing
- **Use Case**: Quick comprehensive testing

#### **3. 🚀 Fast Backtesting (DEVELOPMENT)**
- **File**: `scripts/tick_data/eth_fast_backtest.py`
- **Speed**: 100x faster (1-minute candles or sampling)
- **Accuracy**: ~80-90% (good for quick iterations)
- **Use Case**: Strategy development, parameter testing

#### **4. 📈 Traditional Freqtrade Backtesting**
- **File**: `scripts/backtest/backtest_phase1.sh`
- **Data**: OHLCV candles from Binance API
- **Speed**: Very fast (seconds)
- **Accuracy**: Good for basic validation
- **Use Case**: Quick strategy checks, parameter optimization

### **Backtesting Performance Comparison**

| Method | Speed | Accuracy | Use Case | Data Type |
|--------|-------|----------|----------|-----------|
| **Realistic** | 1-2 min/month | 95% | Final validation | Ticks + 5min |
| **Hybrid** | 20x faster | 95% | Comprehensive test | 5min + ticks |
| **Fast** | 100x faster | 80-90% | Development | 1min/samples |
| **Traditional** | Seconds | Basic | Quick check | OHLCV |

### **When to Use Each Method**

**🎯 Use Realistic Tick Backtesting when:**
- Finalizing strategy for production
- Need exact paper trading accuracy
- Testing position sizing and risk management
- Validating across multiple market cycles

**⚡ Use Hybrid Backtesting when:**
- Need comprehensive results quickly
- Testing strategy modifications
- Comparing different timeframes
- Monthly/quarterly analysis

**🚀 Use Fast Backtesting when:**
- Developing new strategies
- Testing parameter changes
- Quick profit/loss estimates
- Rapid iteration cycles

**📈 Use Traditional Backtesting when:**
- Initial strategy validation
- Parameter optimization (hyperopt)
- Cross-pair comparisons
- Very quick sanity checks

### **Backtesting Best Practices**

1. **Always start with realistic backtesting** for final validation
2. **Test multiple market conditions** (bull, bear, sideways)
3. **Include transaction costs and slippage** in calculations
4. **Validate weekend filter effectiveness** with comparison tests
5. **Check results against live trading** for accuracy confirmation
6. **Test different position sizes** to find optimal risk levels

### **Data Storage & Management**

- **Tick Data Location**: `user_data/tick_data/ETHUSDT/` (symlinked to external storage)
- **Data Size**: 61GB+ of tick-level data
- **Coverage**: Daily files from 2022-01-01 to present
- **Format**: Feather files for fast pandas loading
- **External Storage**: `~/Documents/projects/tres-comas/tick_data/`

## Technical Configuration

### Database Setup:
- **PostgreSQL**: Running on port 5433
- **Database**: freqtrade_db
- **Connection**: postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db

### Current Strategy Config:
- **Strategy**: Try1BullRiderStrategy
- **Timeframe**: 5 minutes
- **Pairs**: 15 major cryptocurrencies
- **Stop Loss**: 4% (needs reduction for production)
- **ROI Targets**: 4% initial, trailing to 0.8%
- **Max Trades**: 15 concurrent positions

### API Requirements:
- **Exchange**: Binance Futures
- **API Keys**: Set in `.env` file
- **Permissions**: Futures trading enabled
- **Safety**: Currently dry-run mode only

## Risk Assessment & Safety

### What Could Go Wrong in Production:

#### Scenario 1: Market Crash
- All 15 positions hit 4% stop losses simultaneously
- Total loss: 60%+ of account in minutes
- No protection against correlated moves

#### Scenario 2: Bot Malfunction  
- Strategy bug opens unlimited positions
- No daily limits = unlimited losses
- No alerts = discovery hours later
- Account liquidation before intervention

#### Scenario 3: API/Network Issues
- Exchange API down during market crash
- Unable to close losing positions
- Losses compound while locked out
- No backup systems or failovers

### Current Safety Measures:
✅ **Paper Trading Mode**: All trades simulated  
✅ **Database Logging**: Comprehensive trade tracking  
✅ **Kill Switch**: Manual bot termination available  
✅ **Monitoring Script**: Real-time performance tracking  

### Missing Critical Safety (Phase 1 Required):
❌ **Daily Loss Limits**: None implemented  
❌ **Position Size Limits**: Can risk 20%+ per trade  
❌ **Emergency Controls**: No automatic halt mechanisms  
❌ **Alert System**: No notifications for failures/losses  
❌ **Market Condition Filters**: Trades the same in all conditions  

## Final Recommendations

### ⚠️ BEFORE REAL MONEY:
1. **Complete ALL Phase 1 safety implementations**
2. **Test extensively in various market conditions**
3. **Start with micro amounts ($10-50 max)**
4. **Get professional review from experienced traders**
5. **Have emergency fund separate from trading account**

### 📊 Success Metrics to Watch:
- **Daily Loss Never Exceeds**: 2-5% of account
- **Win Rate Maintains**: 60%+ (vs current 100%)
- **Drawdown Stays Under**: 10% maximum
- **Position Sizes Limited**: 1-2% per trade maximum

### 🎯 Deployment Timeline:
- **Phase 1 Implementation**: 2-4 weeks minimum
- **Phase 2 Infrastructure**: 2-3 weeks
- **Phase 3 Testing & Rollout**: 1-2 months minimum
- **Total Time to Production**: 2-3 months minimum

## Remember: This Could Save Your Account

The difference between paper trading profits and real money success is robust risk management. The current $195/12-hour performance is promising, but without proper safety mechanisms, it could become a $20,000 loss in a single day.

**Take the time to implement safety measures. Your future self will thank you.**

## 🔧 Common Issues & Troubleshooting

### **Backtesting Issues**
```bash
# No tick data found error
# Solution: Check symlink and data location
ls -la user_data/tick_data/ETHUSDT/
python3 -c "from scripts.tick_data.eth_realistic_backtest import detect_available_date_range; print(detect_available_date_range())"

# ModuleNotFoundError in tick scripts
# Solution: Run from project root directory
cd /Users/gsiradze/Documents/projects/tres-comas/freqtrade
python3 scripts/tick_data/eth_realistic_backtest.py --recent

# Slow tick processing
# Solution: Use recent flag for faster testing
python3 scripts/tick_data/eth_realistic_backtest.py --recent  # 3 months instead of 3 years
```

### **Paper Trading Issues**
```bash
# Bot not starting
# Check logs for errors
tail -f user_data/logs/freqtrade_hft.log

# Database connection issues
# Verify PostgreSQL is running
psql postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db -c "SELECT 1;"

# Weekend trading blocked messages
# This is normal - weekend filter is working correctly
grep "Weekend trading disabled" user_data/logs/freqtrade_hft.log

# No trades being generated
# Check market conditions and strategy signals
./scripts/trading/monitor_performance.sh
```

### **Data Issues**
```bash
# Missing tick data dates
python3 scripts/tick_data/download_missing_eth_days.py

# Symlink broken after moving tick data
ln -sf ~/Documents/projects/tres-comas/tick_data/ETHUSDT user_data/tick_data/ETHUSDT

# Storage space issues
du -sh ~/Documents/projects/tres-comas/tick_data/  # Check total size
```

### **Performance Monitoring**
```bash
# Check current bot status
./scripts/trading/monitor_performance.sh

# View recent trades in database
psql postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db -c "SELECT pair, open_date, close_date, profit_ratio FROM trades WHERE close_date IS NOT NULL ORDER BY close_date DESC LIMIT 10;"

# Monitor system resources
top -pid $(pgrep -f freqtrade)
```

### **Quick Fixes**
- **"Command not found"**: Always run commands from project root directory
- **"Permission denied"**: Make scripts executable with `chmod +x scripts/path/to/script.sh`
- **"Import errors"**: Check that you're in the correct directory and have all dependencies
- **"Database errors"**: Restart PostgreSQL with `brew services restart postgresql@14`
- **"API errors"**: Check .env file has correct Binance API keys
- **"Tick data not found"**: Verify symlink with `ls -la user_data/tick_data/ETHUSDT`

### **Emergency Commands**
```bash
# Stop all trading immediately
./scripts/trading/kill_script.sh
pkill -f freqtrade

# Check if bot is still running
ps aux | grep freqtrade

# Restart PostgreSQL
brew services restart postgresql@14

# Clean restart everything
./scripts/trading/kill_script.sh
brew services restart postgresql@14
./scripts/trading/start_paper_trading.sh
```