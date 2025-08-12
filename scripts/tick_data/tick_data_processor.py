#!/usr/bin/env python3
"""
Tick Data Processor
Converts raw Binance tick data into formats suitable for backtesting
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
from datetime import datetime, timedelta
import talib as ta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TickDataProcessor:
    def __init__(self, tick_data_dir="user_data/tick_data", processed_dir="user_data/processed_tick_data"):
        self.tick_data_dir = Path(tick_data_dir)
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def load_tick_data(self, symbol, date):
        """Load raw tick data for a specific symbol and date"""
        tick_file = self.tick_data_dir / symbol / f"{symbol}-trades-{date.strftime('%Y-%m-%d')}.feather"
        
        if not tick_file.exists():
            logger.warning(f"Tick data file not found: {tick_file}")
            return None
        
        try:
            df = pd.read_feather(tick_file)
            logger.info(f"Loaded {len(df):,} ticks for {symbol} on {date}")
            return df
        except Exception as e:
            logger.error(f"Error loading tick data: {e}")
            return None
    
    def aggregate_ticks_to_ohlc(self, tick_df, timeframe='5min'):
        """Convert tick data to OHLC bars for comparison"""
        if tick_df is None or len(tick_df) == 0:
            return None
        
        try:
            # Set datetime as index
            tick_df = tick_df.set_index('datetime')
            
            # Aggregate to OHLC
            ohlc_df = tick_df['price'].resample(timeframe).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last'
            })
            
            # Add volume (sum of quantities)
            ohlc_df['volume'] = tick_df['qty'].resample(timeframe).sum()
            
            # Add trade count
            ohlc_df['trade_count'] = tick_df['trade_id'].resample(timeframe).count()
            
            # Remove rows with NaN values
            ohlc_df = ohlc_df.dropna()
            
            # Reset index to have datetime as column
            ohlc_df = ohlc_df.reset_index()
            
            logger.info(f"Aggregated {len(tick_df):,} ticks to {len(ohlc_df)} {timeframe} bars")
            return ohlc_df
            
        except Exception as e:
            logger.error(f"Error aggregating ticks to OHLC: {e}")
            return None
    
    def add_technical_indicators(self, ohlc_df):
        """Add technical indicators needed by Try1BullRiderStrategy"""
        try:
            # EMAs for trend detection
            ohlc_df['ema_8'] = ta.EMA(ohlc_df['close'].values, timeperiod=8)
            ohlc_df['ema_21'] = ta.EMA(ohlc_df['close'].values, timeperiod=21)
            ohlc_df['ema_50'] = ta.EMA(ohlc_df['close'].values, timeperiod=50)
            
            # RSI
            ohlc_df['rsi'] = ta.RSI(ohlc_df['close'].values, timeperiod=14)
            
            # Volume indicators
            ohlc_df['volume_mean'] = ohlc_df['volume'].rolling(window=20).mean()
            ohlc_df['volume_ratio'] = ohlc_df['volume'] / ohlc_df['volume_mean']
            
            # Price momentum
            ohlc_df['momentum_5'] = ohlc_df['close'].pct_change(periods=5)
            ohlc_df['momentum_20'] = ohlc_df['close'].pct_change(periods=20)
            
            # ATR
            ohlc_df['atr'] = ta.ATR(ohlc_df['high'].values, ohlc_df['low'].values, ohlc_df['close'].values, timeperiod=14)
            
            # Trend detection (simplified from strategy)
            ohlc_df['uptrend'] = (
                (ohlc_df['ema_8'] > ohlc_df['ema_21']) & 
                (ohlc_df['ema_21'] > ohlc_df['ema_50']) & 
                (ohlc_df['close'] > ohlc_df['ema_8'])
            )
            
            # Candle patterns
            ohlc_df['green_candle'] = (ohlc_df['close'] > ohlc_df['open']).astype(int)
            ohlc_df['body_size'] = abs(ohlc_df['close'] - ohlc_df['open'])
            
            return ohlc_df.dropna()  # Remove NaN rows created by indicators
            
        except Exception as e:
            logger.error(f"Error adding technical indicators: {e}")
            return ohlc_df
    
    def identify_signals_from_ticks(self, tick_df, ohlc_df):
        """Identify exact buy/sell signals from tick data"""
        signals = []
        
        if ohlc_df is None or len(ohlc_df) == 0:
            return signals
        
        try:
            # Strategy parameters (from Try1BullRiderStrategy)
            rsi_oversold = 40
            rsi_overbought = 65
            volume_multiplier = 1.2
            trend_strength = 0.005
            
            for i, row in ohlc_df.iterrows():
                if i < 50:  # Skip early rows due to indicators warmup
                    continue
                
                # Long signal conditions (simplified)
                long_dip_buy = (
                    row['uptrend'] and
                    row['rsi'] < rsi_oversold and
                    row['volume_ratio'] > volume_multiplier
                )
                
                long_breakout = (
                    row['momentum_5'] > trend_strength and
                    row['green_candle'] == 1 and
                    row['volume_ratio'] > 1.5 and
                    row['close'] > row['ema_8']
                )
                
                long_trend_follow = (
                    row['uptrend'] and
                    row['close'] > ohlc_df.iloc[i-1]['close'] and
                    row['rsi'] > 45 and row['rsi'] < 70 and
                    row['volume_ratio'] > 1.0
                )
                
                # Record signals
                if long_dip_buy or long_breakout or long_trend_follow:
                    signal_type = 'dip_buy' if long_dip_buy else ('breakout' if long_breakout else 'trend_follow')
                    signals.append({
                        'datetime': row['datetime'],
                        'signal': 'long',
                        'type': signal_type,
                        'price': row['close'],
                        'rsi': row['rsi'],
                        'volume_ratio': row['volume_ratio'],
                        'atr': row['atr']
                    })
            
            logger.info(f"Identified {len(signals)} signals from tick analysis")
            return signals
            
        except Exception as e:
            logger.error(f"Error identifying signals: {e}")
            return []
    
    def simulate_tick_execution(self, tick_df, signal_time, signal_price, direction='long'):
        """Simulate order execution using actual tick data"""
        if tick_df is None:
            return None
        
        try:
            # Find ticks around signal time (within 5 minutes)
            signal_time = pd.to_datetime(signal_time)
            mask = (
                (tick_df['datetime'] >= signal_time) & 
                (tick_df['datetime'] <= signal_time + timedelta(minutes=5))
            )
            relevant_ticks = tick_df[mask]
            
            if len(relevant_ticks) == 0:
                return None
            
            # Find actual execution price (first tick after signal)
            execution_tick = relevant_ticks.iloc[0]
            
            # Calculate slippage (difference between signal price and execution price)
            slippage = (execution_tick['price'] - signal_price) / signal_price
            
            return {
                'signal_time': signal_time,
                'signal_price': signal_price,
                'execution_time': execution_tick['datetime'],
                'execution_price': execution_tick['price'],
                'slippage': slippage,
                'slippage_bps': slippage * 10000,  # basis points
                'is_buyer_maker': execution_tick['is_buyer_maker']
            }
            
        except Exception as e:
            logger.error(f"Error simulating execution: {e}")
            return None
    
    def process_symbol_date_range(self, symbol, start_date, end_date, timeframe='5min'):
        """Process tick data for a symbol across date range"""
        logger.info(f"Processing {symbol} from {start_date} to {end_date}")
        
        current_date = start_date
        all_signals = []
        all_executions = []
        
        while current_date <= end_date:
            # Load tick data
            tick_df = self.load_tick_data(symbol, current_date)
            
            if tick_df is not None and len(tick_df) > 0:
                # Convert to OHLC
                ohlc_df = self.aggregate_ticks_to_ohlc(tick_df, timeframe)
                
                if ohlc_df is not None:
                    # Add indicators
                    ohlc_df = self.add_technical_indicators(ohlc_df)
                    
                    # Find signals
                    signals = self.identify_signals_from_ticks(tick_df, ohlc_df)
                    
                    # Simulate executions for each signal
                    for signal in signals:
                        execution = self.simulate_tick_execution(
                            tick_df, signal['datetime'], signal['price'], signal['signal']
                        )
                        if execution:
                            execution.update(signal)  # Combine signal and execution data
                            all_executions.append(execution)
                    
                    all_signals.extend(signals)
            
            current_date += timedelta(days=1)
        
        # Save processed results
        if all_signals:
            signals_df = pd.DataFrame(all_signals)
            signals_file = self.processed_dir / f"{symbol}_signals_{start_date}_{end_date}.feather"
            signals_df.to_feather(signals_file)
            logger.info(f"Saved {len(signals_df)} signals to {signals_file.name}")
        
        if all_executions:
            executions_df = pd.DataFrame(all_executions)
            executions_file = self.processed_dir / f"{symbol}_executions_{start_date}_{end_date}.feather"
            executions_df.to_feather(executions_file)
            logger.info(f"Saved {len(executions_df)} executions to {executions_file.name}")
            
            # Calculate summary statistics
            avg_slippage = executions_df['slippage_bps'].mean()
            max_slippage = executions_df['slippage_bps'].max()
            min_slippage = executions_df['slippage_bps'].min()
            
            logger.info(f"Execution Summary - Avg slippage: {avg_slippage:.2f} bps, Range: {min_slippage:.2f} to {max_slippage:.2f} bps")
        
        return len(all_signals), len(all_executions)

def main():
    """Example usage"""
    processor = TickDataProcessor()
    
    # Process recent data for a symbol
    symbol = "BTCUSDT"
    end_date = datetime.now().date() - timedelta(days=1)
    start_date = end_date - timedelta(days=2)  # Process 3 days
    
    print(f"Processing tick data for {symbol}...")
    signals, executions = processor.process_symbol_date_range(symbol, start_date, end_date)
    print(f"Found {signals} signals and {executions} executions")

if __name__ == "__main__":
    main()