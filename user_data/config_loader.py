"""
Configuration loader for environment variables
"""
import os
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

def get_env(key: str, default: Any = None, cast_type: type = str) -> Any:
    """Get environment variable with type casting"""
    value = os.getenv(key, default)
    if value is None:
        return None
    
    if cast_type == bool:
        return value.lower() in ('true', '1', 'yes', 'on')
    elif cast_type == int:
        return int(value)
    elif cast_type == float:
        return float(value)
    return value

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables"""
    return {
        "$schema": "https://schema.freqtrade.io/schema.json",
        "max_open_trades": get_env('MAX_OPEN_TRADES', 5, int),
        "stake_currency": "USDT",
        "stake_amount": get_env('STAKE_AMOUNT', 100, float),
        "tradable_balance_ratio": 0.99,
        "fiat_display_currency": "USD",
        "timeframe": "1m",
        "dry_run": get_env('DRY_RUN', True, bool),
        "dry_run_wallet": 10000,
        "cancel_open_orders_on_exit": False,
        "unfilledtimeout": {
            "entry": 5,
            "exit": 5,
            "exit_timeout_count": 0,
            "unit": "minutes"
        },
        "entry_pricing": {
            "price_side": "same",
            "use_order_book": True,
            "order_book_top": 1,
            "price_last_balance": 0.0,
            "check_depth_of_market": {
                "enabled": False,
                "bids_to_ask_delta": 1
            }
        },
        "exit_pricing": {
            "price_side": "same", 
            "use_order_book": True,
            "order_book_top": 1
        },
        "exchange": {
            "name": "binance",
            "key": get_env('BINANCE_API_KEY', ''),
            "secret": get_env('BINANCE_API_SECRET', ''),
            "ccxt_config": {
                "enableRateLimit": True,
                "rateLimit": 50
            },
            "ccxt_async_config": {
                "enableRateLimit": True,
                "rateLimit": 50
            },
            "pair_whitelist": [
                "BTC/USDT",
                "ETH/USDT",
                "BNB/USDT",
                "SOL/USDT",
                "ADA/USDT",
                "XRP/USDT",
                "DOT/USDT",
                "AVAX/USDT",
                "MATIC/USDT",
                "LINK/USDT"
            ],
            "pair_blacklist": [
                "BNB/BTC",
                ".*DOWN/USDT",
                ".*UP/USDT"
            ]
        },
        "pairlists": [
            {
                "method": "VolumePairList",
                "number_assets": 20,
                "sort_key": "quoteVolume",
                "min_value": 20000000,
                "refresh_period": 1800
            },
            {
                "method": "PriceFilter",
                "low_price_ratio": 0.01,
                "min_price": 0.00000010,
                "max_price": 10000000,
                "max_value": 50000
            },
            {
                "method": "SpreadFilter",
                "max_spread_ratio": 0.005
            },
            {
                "method": "VolatilityFilter",
                "lookback_days": 10,
                "min_volatility": 0.01,
                "max_volatility": 0.75,
                "refresh_period": 1800
            },
            {
                "method": "ShuffleFilter",
                "seed": 42
            }
        ],
        "telegram": {
            "enabled": bool(get_env('TELEGRAM_TOKEN')),
            "token": get_env('TELEGRAM_TOKEN', ''),
            "chat_id": get_env('TELEGRAM_CHAT_ID', ''),
            "notification_settings": {
                "status": "on",
                "warning": "on",
                "startup": "on",
                "entry": "on",
                "entry_cancel": "on",
                "entry_fill": "on",
                "exit": {
                    "roi": "on",
                    "emergency_exit": "on",
                    "force_exit": "on",
                    "exit_signal": "on",
                    "trailing_stop_loss": "on",
                    "stop_loss": "on",
                    "stoploss_on_exchange": "on",
                    "custom_exit": "on"
                },
                "exit_cancel": "on",
                "exit_fill": "on",
                "protection_trigger": "on",
                "protection_trigger_global": "on"
            },
            "reload": True,
            "balance_dust_level": 0.01
        },
        "api_server": {
            "enabled": True,
            "listen_ip_address": "127.0.0.1",
            "listen_port": 8080,
            "verbosity": "error",
            "enable_openapi": False,
            "jwt_secret_key": get_env('API_SERVER_JWT_SECRET', 'somethingrandom_change_this_please'),
            "ws_token": get_env('API_SERVER_WS_TOKEN', 'your_websocket_token_here'),
            "CORS_origins": ["http://localhost:3000"],
            "username": get_env('API_SERVER_USERNAME', 'freqtrader'),
            "password": get_env('API_SERVER_PASSWORD', 'SuperSecurePassword')
        },
        "bot_name": "HighFreqBot",
        "initial_state": "running",
        "force_entry_enable": False,
        "internals": {
            "process_throttle_secs": get_env('PROCESS_THROTTLE_SECS', 2, int),
            "heartbeat_interval": get_env('HEARTBEAT_INTERVAL', 30, int)
        },
        "db_url": get_env('DATABASE_URL', 'sqlite:///user_data/tradesv3.sqlite'),
        "user_data_dir": "user_data",
        "datadir": "user_data/data/binance",
        "strategy": "MACrossoverFreqStrategy",
        "strategy_path": "user_data/strategies/",
        "recursive_strategy_search": False,
        "add_config_files": [],
        "logfile": "user_data/logs/freqtrade.log"
    }