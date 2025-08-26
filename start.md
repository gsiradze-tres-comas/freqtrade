# BeastModeStrategy - Quick Start Commands

## 1. Paper Trading (Live Bot)
```bash
# Start paper trading bot
freqtrade trade --config user_data/configs/config_safe_bull.json --strategy BeastModeStrategy

# Background mode with auto-restart
nohup freqtrade trade --config user_data/configs/config_safe_bull.json --strategy BeastModeStrategy > user_data/logs/paper_trading.log 2>&1 &

# Monitor live trades
tail -f user_data/logs/freqtrade_safe.log

# Web UI: http://127.0.0.1:8080 (login: freqtrade/freqtrade)
```

**Parameters:**
- `--config`: Config file path (default: user_data/configs/config_safe_bull.json)
- `--strategy`: Strategy name (default: BeastModeStrategy)
- `--dry-run`: Force paper mode (already set in config)
- `--db-url`: Database override (default: PostgreSQL on port 5433)

## 2. Backtesting
```bash
# Run backtest for specific year
python3 scripts/backtest.py --balance 3000 --year 2022

# Run recent 3 months
python3 scripts/backtest.py --balance 3000 --recent

# Background mode with output logging
nohup python3 scripts/backtest.py --balance 3000 --year 2022 > backtest_results.log 2>&1 &

# Custom date range
python3 scripts/backtest.py --balance 3000 --start 2025-01-01 --end 2025-08-01
```

**Parameters:**
- `--balance`: Starting balance in USDT (required)
- `--year`: Backtest specific year (2022, 2023, 2024, 2025)
- `--recent`: Last 3 months only (faster)
- `--start` / `--end`: Custom date range (YYYY-MM-DD format)
- `--pairs`: Override pair list (optional)