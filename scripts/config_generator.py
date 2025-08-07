#!/usr/bin/env python3
"""
High-Performance Configuration Generator for Freqtrade
Generates optimized configurations for different trading scenarios
"""
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class HighPerformanceConfigGenerator:
    """Generate optimized Freqtrade configurations for high-performance trading"""
    
    def __init__(self, output_dir: str = "user_data/configs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
    def generate_base_config(self, mode: str = "spot") -> Dict[str, Any]:
        """Generate base configuration with performance optimizations"""
        return {
            "$schema": "https://schema.freqtrade.io/schema.json",
            "trading_mode": mode,
            "margin_mode": "isolated" if mode == "futures" else "",
            "max_open_trades": int(os.getenv("MAX_OPEN_TRADES", 3)),
            "stake_currency": "USDT",
            "stake_amount": float(os.getenv("STAKE_AMOUNT", 100)),
            "tradable_balance_ratio": 0.99,
            "fiat_display_currency": "USD",
            "dry_run": os.getenv("DRY_RUN", "true").lower() == "true",
            "dry_run_wallet": float(os.getenv("INITIAL_CAPITAL", 1000)),
            "cancel_open_orders_on_exit": True,
            "force_entry_enable": False,
            
            # Database - Using PostgreSQL for performance
            "db_url": os.getenv("DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5433/freqtrade_db"),
            
            # Performance settings
            "process_only_new_candles": True,
            "heartbeat_interval": int(os.getenv("HEARTBEAT_INTERVAL", 30)),
            "internals": {
                "process_throttle_secs": float(os.getenv("PROCESS_THROTTLE_SECS", 1)),
                "sd_notify": True,
            },
            
            # Order execution settings
            "order_types": {
                "entry": "limit",
                "exit": "limit",
                "stoploss": "market",
                "stoploss_on_exchange": True,
                "stoploss_on_exchange_interval": 60,
            },
            
            "order_time_in_force": {
                "entry": os.getenv("ORDER_TIME_IN_FORCE", "GTC"),
                "exit": "GTC"
            },
            
            # Pricing strategies for precision
            "entry_pricing": {
                "price_side": "bid",
                "use_order_book": True,
                "order_book_top": 1,
                "price_last_balance": 0.0,
                "check_depth_of_market": {
                    "enabled": True,
                    "bids_to_ask_delta": 1
                }
            },
            
            "exit_pricing": {
                "price_side": "ask",
                "use_order_book": True,
                "order_book_top": 1
            },
            
            # Exchange configuration
            "exchange": self._get_exchange_config(mode),
            
            # Pairlist for high-volume trading
            "pairlists": self._get_pairlist_config(),
            
            # Telegram configuration
            "telegram": self._get_telegram_config(),
            
            # API server for monitoring
            "api_server": self._get_api_server_config(),
            
            # Logging
            "logfile": "user_data/logs/freqtrade.log",
            "user_data_dir": "user_data",
            "datadir": "user_data/data/binance",
            "strategy_path": "user_data/strategies/",
        }
    
    def _get_exchange_config(self, mode: str) -> Dict[str, Any]:
        """Get optimized exchange configuration"""
        config = {
            "name": "binance",
            "key": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_API_SECRET", ""),
            "ccxt_config": {
                "enableRateLimit": True,
                "rateLimit": 50,  # Aggressive rate limit for speed
                "options": {
                    "defaultType": "future" if mode == "futures" else "spot",
                    "adjustForTimeDifference": True,
                }
            },
            "ccxt_async_config": {
                "enableRateLimit": True,
                "rateLimit": 50,
                "aiohttp_proxy": None,
                "aiohttp_trust_env": True
            },
            "pair_whitelist": [],  # Will be populated by pairlist
            "pair_blacklist": [
                "BNB/.*",
                ".*/BNB",
                ".*BULL/.*",
                ".*BEAR/.*",
                ".*DOWN/.*",
                ".*UP/.*",
                ".*BUSD.*"
            ]
        }
        
        # Use testnet if configured
        if os.getenv("BINANCE_TESTNET", "false").lower() == "true":
            config["ccxt_config"]["urls"] = {
                "api": {
                    "spot": "https://testnet.binance.vision",
                    "future": "https://testnet.binancefuture.com"
                }
            }
            
        return config
    
    def _get_pairlist_config(self) -> list:
        """Get pairlist configuration optimized for high-volume trading"""
        return [
            {
                "method": "VolumePairList",
                "number_assets": 30,
                "sort_key": "quoteVolume",
                "min_value": 20000000,  # $20M daily volume minimum
                "refresh_period": 1800,
                "lookback_days": 1
            },
            {
                "method": "SpreadFilter",
                "max_spread_ratio": 0.002  # 0.2% max spread for tight markets
            },
            {
                "method": "PriceFilter",
                "low_price_ratio": 0.001,
                "min_price": 0.00000010,
                "max_price": 1000000,
            },
            {
                "method": "VolatilityFilter",
                "lookback_days": 3,
                "min_volatility": 0.01,
                "max_volatility": 0.30,
                "refresh_period": 1800
            },
            {
                "method": "PerformanceFilter",
                "minutes": 60  # Filter by 1-hour performance
            },
            {
                "method": "PrecisionFilter"
            },
        ]
    
    def _get_telegram_config(self) -> Optional[Dict[str, Any]]:
        """Get Telegram configuration if credentials are available"""
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            return {"enabled": False}
            
        return {
            "enabled": True,
            "token": token,
            "chat_id": chat_id,
            "notification_settings": {
                "status": "on",
                "warning": "on",
                "startup": "on",
                "entry": "on",
                "entry_fill": "on",
                "exit": "on",
                "exit_fill": "on",
                "protection_trigger": "on",
                "protection_trigger_global": "on"
            },
            "reload": True,
            "balance_dust_level": 0.01
        }
    
    def _get_api_server_config(self) -> Dict[str, Any]:
        """Get API server configuration"""
        return {
            "enabled": True,
            "listen_ip_address": os.getenv("API_SERVER_HOST", "127.0.0.1"),
            "listen_port": int(os.getenv("API_SERVER_PORT", 8080)),
            "verbosity": os.getenv("LOG_LEVEL", "INFO"),
            "enable_openapi": False,
            "jwt_secret_key": os.getenv("API_SERVER_JWT_SECRET", "your_random_jwt_secret"),
            "ws_token": os.getenv("API_SERVER_WS_TOKEN", "your_websocket_token"),
            "CORS_origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "username": os.getenv("API_SERVER_USERNAME", "freqtrader"),
            "password": os.getenv("API_SERVER_PASSWORD", "SuperSecurePassword")
        }
    
    def generate_high_frequency_config(self) -> Dict[str, Any]:
        """Generate configuration optimized for high-frequency trading"""
        config = self.generate_base_config("spot")
        
        # High-frequency specific settings
        config.update({
            "strategy": os.getenv("STRATEGY", "HighFrequencyStrategy"),
            "timeframe": "1m",
            "bot_name": "HighFreqBot",
            
            # Ultra-fast processing
            "internals": {
                "process_throttle_secs": 0.5,  # 500ms processing interval
                "sd_notify": True,
            },
            
            # Fast order execution
            "order_types": {
                "entry": "market" if os.getenv("USE_MARKET_ORDERS", "false").lower() == "true" else "limit",
                "exit": "market" if os.getenv("USE_MARKET_ORDERS", "false").lower() == "true" else "limit",
                "stoploss": "market",
                "stoploss_on_exchange": True,
                "stoploss_on_exchange_interval": 30,
            },
            
            # Tight timeouts
            "unfilledtimeout": {
                "entry": 10,
                "exit": 10,
                "exit_timeout_count": 0,
                "unit": "seconds"
            },
            
            # Risk management
            "stoploss": float(os.getenv("STOP_LOSS_PERCENTAGE", -2)) / 100,
            "trailing_stop": os.getenv("USE_TRAILING_STOP", "true").lower() == "true",
            "trailing_stop_positive": float(os.getenv("TRAILING_STOP_POSITIVE", 0.01)),
            "trailing_stop_positive_offset": float(os.getenv("TRAILING_STOP_POSITIVE_OFFSET", 0.012)),
            "trailing_only_offset_is_reached": True,
        })
        
        # Adjust pairlist for HFT
        config["pairlists"][0]["number_assets"] = 10  # Focus on top 10 pairs
        config["pairlists"][1]["max_spread_ratio"] = 0.001  # Tighter spread requirement
        
        return config
    
    def generate_futures_config(self) -> Dict[str, Any]:
        """Generate configuration for futures trading"""
        config = self.generate_base_config("futures")
        
        config.update({
            "strategy": os.getenv("STRATEGY", "MomentumFreqStrategy"),
            "timeframe": "5m",
            "bot_name": "FuturesBot",
            "leverage": 3.0,  # Conservative leverage
            "liquidation_buffer": 0.05,  # 5% buffer from liquidation
            
            # Futures-specific risk management
            "stoploss": -0.02,  # 2% stop loss
            "trailing_stop": True,
            "trailing_stop_positive": 0.01,
            "trailing_stop_positive_offset": 0.015,
            
            # Position sizing for futures
            "position_adjustment_enable": True,
            "max_entry_position_adjustment": 3,
        })
        
        return config
    
    def generate_scalping_config(self) -> Dict[str, Any]:
        """Generate configuration for scalping strategy"""
        config = self.generate_base_config("spot")
        
        config.update({
            "strategy": "RSIBounceFreqStrategy",
            "timeframe": "1m",
            "bot_name": "ScalpingBot",
            
            # Scalping specific settings
            "minimal_roi": {
                "0": 0.01,   # 1% ROI
                "10": 0.005,  # 0.5% after 10 minutes
                "30": 0.003,  # 0.3% after 30 minutes
                "60": 0      # Exit after 60 minutes
            },
            
            "stoploss": -0.005,  # 0.5% tight stop loss
            
            # No trailing stop for scalping
            "trailing_stop": False,
            
            # Very tight timeouts
            "unfilledtimeout": {
                "entry": 30,
                "exit": 10,
                "exit_timeout_count": 0,
                "unit": "seconds"
            },
            
            # Focus on most liquid pairs
            "max_open_trades": 1,  # One trade at a time for focus
        })
        
        # Ultra-tight spread requirement
        config["pairlists"][1]["max_spread_ratio"] = 0.0005  # 0.05% max spread
        
        return config
    
    def save_config(self, config: Dict[str, Any], name: str):
        """Save configuration to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"config_{name}_{timestamp}.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)
            
        # Create/update symlink to latest
        latest_link = self.output_dir / f"config_{name}_latest.json"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(filename)
        
        print(f"✓ Configuration saved to: {filepath}")
        print(f"✓ Latest symlink updated: {latest_link}")
        
        return filepath
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration has required fields"""
        required_fields = ["exchange", "stake_currency", "dry_run", "db_url"]
        
        for field in required_fields:
            if field not in config:
                print(f"❌ Missing required field: {field}")
                return False
                
        # Check API credentials
        if not config["exchange"].get("key") or not config["exchange"].get("secret"):
            print("❌ Missing API credentials. Check your .env file")
            return False
            
        return True
    
    def generate_all_configs(self):
        """Generate all configuration variants"""
        configs = {
            "base": self.generate_base_config(),
            "high_frequency": self.generate_high_frequency_config(),
            "futures": self.generate_futures_config(),
            "scalping": self.generate_scalping_config(),
        }
        
        saved_configs = []
        for name, config in configs.items():
            if self.validate_config(config):
                filepath = self.save_config(config, name)
                saved_configs.append((name, filepath))
            else:
                print(f"❌ Skipping {name} config due to validation errors")
                
        return saved_configs


def main():
    parser = argparse.ArgumentParser(description="Generate high-performance Freqtrade configurations")
    parser.add_argument("--type", choices=["all", "base", "high_frequency", "futures", "scalping"], 
                       default="all", help="Type of configuration to generate")
    parser.add_argument("--output", help="Output directory", default="user_data/configs")
    
    args = parser.parse_args()
    
    generator = HighPerformanceConfigGenerator(args.output)
    
    if args.type == "all":
        print("🚀 Generating all configuration variants...")
        configs = generator.generate_all_configs()
        print(f"\n✅ Generated {len(configs)} configurations successfully!")
        
        # Also generate the default config_dynamic.json for backward compatibility
        default_config = generator.generate_base_config()
        with open("user_data/config_dynamic.json", "w") as f:
            json.dump(default_config, f, indent=4)
        print("✓ Default config written to user_data/config_dynamic.json")
    else:
        config_map = {
            "base": generator.generate_base_config,
            "high_frequency": generator.generate_high_frequency_config,
            "futures": generator.generate_futures_config,
            "scalping": generator.generate_scalping_config,
        }
        
        print(f"🚀 Generating {args.type} configuration...")
        config = config_map[args.type]()
        
        if generator.validate_config(config):
            generator.save_config(config, args.type)
            print("✅ Configuration generated successfully!")
        else:
            print("❌ Configuration validation failed!")
            exit(1)


if __name__ == "__main__":
    main()