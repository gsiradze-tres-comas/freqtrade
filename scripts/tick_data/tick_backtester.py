#!/usr/bin/env python3
"""
Tick-Level Backtesting Engine
Ultra-accurate backtesting using tick data for precise entry/exit simulation
"""

import pandas as pd
import numpy as np
from pathlib import Path
import logging
from datetime import datetime, timedelta
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Trade:
    """Trade record with tick-level precision"""
    symbol: str
    entry_time: datetime
    entry_price: float
    entry_signal: str
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0
    slippage_entry: float = 0.0
    slippage_exit: float = 0.0
    max_drawdown: float = 0.0
    max_profit: float = 0.0
    duration_minutes: int = 0
    is_winner: bool = False

@dataclass
class Portfolio:
    """Portfolio state tracker"""
    initial_balance: float = 10000.0
    current_balance: float = 10000.0
    available_balance: float = 10000.0
    open_positions: List[Trade] = None
    closed_trades: List[Trade] = None
    max_open_trades: int = 15
    position_size_pct: float = 0.067  # 6.67% per position (unlimited/15)
    
    def __post_init__(self):
        if self.open_positions is None:
            self.open_positions = []
        if self.closed_trades is None:
            self.closed_trades = []

class TickBacktester:
    def __init__(self, tick_data_dir="user_data/tick_data", results_dir="user_data/tick_backtest_results"):
        self.tick_data_dir = Path(tick_data_dir)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Strategy parameters (from Try1BullRiderStrategy)
        self.rsi_oversold = 40
        self.rsi_overbought = 65
        self.volume_multiplier = 1.2
        self.trend_strength = 0.005
        
        # Risk management
        self.stop_loss_pct = 0.04  # 4%
        self.take_profit_pct = 0.04  # 4%
        self.trailing_stop_pct = 0.015  # 1.5%
        self.trailing_stop_offset = 0.02  # 2%
        
        # Trading costs
        self.taker_fee = 0.0004  # 0.04% (Binance futures)
        self.maker_fee = 0.0002  # 0.02% (Binance futures)
        self.slippage_assumption = 0.0001  # 0.01% additional slippage
        
        self.portfolio = Portfolio()
        
        # Balance history for drawdown calculation
        self.balance_history = []
    
    def load_tick_data(self, symbol, date):
        """Load tick data for specific symbol and date"""
        tick_file = self.tick_data_dir / symbol / f"{symbol}-trades-{date.strftime('%Y-%m-%d')}.feather"
        
        if not tick_file.exists():
            return None
        
        try:
            df = pd.read_feather(tick_file)
            return df.sort_values('datetime')  # Ensure chronological order
        except Exception as e:
            logger.error(f"Error loading tick data: {e}")
            return None
    
    def calculate_position_size(self, price):
        """Calculate position size based on available balance"""
        position_value = self.portfolio.available_balance * self.portfolio.position_size_pct
        quantity = position_value / price
        return quantity, position_value
    
    def check_entry_signal(self, price, tick_data, current_time):
        """Check if current conditions trigger an entry signal"""
        # This is a simplified version - in real implementation,
        # you'd need to maintain OHLC bars and indicators in real-time
        
        # For now, return random signals for demonstration
        # In practice, you'd implement the full Try1BullRiderStrategy logic
        
        # Basic trend following signal (placeholder)
        if len(tick_data) > 100:
            recent_prices = tick_data.tail(20)['price']
            if recent_prices.iloc[-1] > recent_prices.mean() * 1.001:  # 0.1% above recent average
                return 'trend_follow'
        
        return None
    
    def check_exit_conditions(self, trade, current_price, current_time):
        """Check if current conditions trigger an exit"""
        entry_price = trade.entry_price
        current_pnl_pct = (current_price - entry_price) / entry_price
        
        # Stop loss
        if current_pnl_pct <= -self.stop_loss_pct:
            return 'stop_loss', current_price
        
        # Take profit
        if current_pnl_pct >= self.take_profit_pct:
            return 'take_profit', current_price
        
        # Trailing stop (simplified)
        if trade.max_profit > 0 and current_pnl_pct < (trade.max_profit - self.trailing_stop_pct):
            return 'trailing_stop', current_price
        
        # Time-based exit (24 hours max)
        duration = (current_time - trade.entry_time).total_seconds() / 3600
        if duration >= 24:
            return 'time_exit', current_price
        
        return None, None
    
    def execute_trade(self, action, symbol, price, quantity, tick_time, signal_type="", reason=""):
        """Execute a trade with realistic slippage and fees"""
        
        # Calculate slippage based on action
        if action == 'buy':
            slippage_impact = price * (self.slippage_assumption + np.random.uniform(0, 0.0002))
            execution_price = price + slippage_impact
            fee_rate = self.taker_fee  # Assume market orders
        else:  # sell
            slippage_impact = price * (self.slippage_assumption + np.random.uniform(0, 0.0002))
            execution_price = price - slippage_impact
            fee_rate = self.taker_fee
        
        trade_value = execution_price * quantity
        fees = trade_value * fee_rate
        
        return {
            'execution_price': execution_price,
            'slippage': slippage_impact,
            'fees': fees,
            'trade_value': trade_value
        }
    
    def open_position(self, symbol, signal_type, tick_data_row):
        """Open a new position"""
        if len(self.portfolio.open_positions) >= self.portfolio.max_open_trades:
            return False  # Maximum positions reached
        
        price = tick_data_row['price']
        tick_time = tick_data_row['datetime']
        
        # Calculate position size
        quantity, position_value = self.calculate_position_size(price)
        
        if position_value > self.portfolio.available_balance:
            return False  # Insufficient balance
        
        # Execute entry
        execution = self.execute_trade('buy', symbol, price, quantity, tick_time, signal_type)
        
        # Create trade record
        trade = Trade(
            symbol=symbol,
            entry_time=tick_time,
            entry_price=execution['execution_price'],
            entry_signal=signal_type,
            quantity=quantity,
            slippage_entry=execution['slippage'],
            fees=execution['fees']
        )
        
        # Update portfolio
        self.portfolio.open_positions.append(trade)
        self.portfolio.available_balance -= (execution['trade_value'] + execution['fees'])
        
        logger.info(f"Opened {signal_type} position: {symbol} @ {execution['execution_price']:.4f}, qty: {quantity:.6f}")
        return True
    
    def close_position(self, trade_index, exit_reason, tick_data_row):
        """Close an existing position"""
        trade = self.portfolio.open_positions[trade_index]
        price = tick_data_row['price']
        tick_time = tick_data_row['datetime']
        
        # Execute exit
        execution = self.execute_trade('sell', trade.symbol, price, trade.quantity, tick_time, reason=exit_reason)
        
        # Calculate P&L
        trade_value = execution['trade_value']
        total_fees = trade.fees + execution['fees']
        initial_value = trade.entry_price * trade.quantity
        gross_pnl = trade_value - initial_value
        net_pnl = gross_pnl - total_fees
        pnl_pct = net_pnl / initial_value
        
        # Update trade record
        trade.exit_time = tick_time
        trade.exit_price = execution['execution_price']
        trade.exit_reason = exit_reason
        trade.slippage_exit = execution['slippage']
        trade.fees += execution['fees']
        trade.pnl = net_pnl
        trade.pnl_pct = pnl_pct
        trade.duration_minutes = int((tick_time - trade.entry_time).total_seconds() / 60)
        trade.is_winner = net_pnl > 0
        
        # Update portfolio
        self.portfolio.available_balance += trade_value - execution['fees']
        self.portfolio.current_balance = self.portfolio.available_balance + sum(
            pos.entry_price * pos.quantity for pos in self.portfolio.open_positions if pos != trade
        )
        
        # Track balance history for drawdown calculation
        self.balance_history.append({
            'timestamp': tick_time,
            'balance': self.portfolio.current_balance,
            'trade_pnl': net_pnl
        })
        
        # Move to closed trades
        self.portfolio.closed_trades.append(trade)
        self.portfolio.open_positions.remove(trade)
        
        logger.info(f"Closed position: {trade.symbol} @ {execution['execution_price']:.4f}, P&L: {net_pnl:.2f} ({pnl_pct*100:.2f}%)")
        return trade
    
    def update_open_positions(self, tick_data_row):
        """Update open positions with current market data"""
        current_price = tick_data_row['price']
        current_time = tick_data_row['datetime']
        
        positions_to_close = []
        
        for i, trade in enumerate(self.portfolio.open_positions):
            if trade.symbol in tick_data_row.get('symbol', trade.symbol):  # Match symbol
                # Update unrealized P&L tracking
                current_pnl_pct = (current_price - trade.entry_price) / trade.entry_price
                trade.max_profit = max(trade.max_profit, current_pnl_pct)
                trade.max_drawdown = min(trade.max_drawdown, current_pnl_pct)
                
                # Check exit conditions
                exit_reason, exit_price = self.check_exit_conditions(trade, current_price, current_time)
                if exit_reason:
                    positions_to_close.append(i)
        
        # Close positions that hit exit conditions
        for i in reversed(positions_to_close):  # Reverse to maintain indices
            self.close_position(i, exit_reason, tick_data_row)
    
    def run_backtest(self, symbol, start_date, end_date):
        """Run tick-level backtest for a symbol across date range"""
        logger.info(f"Starting tick backtest for {symbol} from {start_date} to {end_date}")
        
        # Reset portfolio
        self.portfolio = Portfolio()
        
        current_date = start_date
        total_ticks_processed = 0
        
        while current_date <= end_date:
            # Load tick data for the day
            tick_df = self.load_tick_data(symbol, current_date)
            
            if tick_df is not None and len(tick_df) > 0:
                logger.info(f"Processing {len(tick_df):,} ticks for {current_date}")
                
                # Process each tick
                for idx, tick_row in tick_df.iterrows():
                    tick_data_row = dict(tick_row)
                    tick_data_row['symbol'] = symbol
                    
                    # Update existing positions first
                    self.update_open_positions(tick_data_row)
                    
                    # Check for new entry signals
                    signal = self.check_entry_signal(tick_row['price'], tick_df.iloc[:idx+1], tick_row['datetime'])
                    if signal and len(self.portfolio.open_positions) < self.portfolio.max_open_trades:
                        self.open_position(symbol, signal, tick_data_row)
                    
                    total_ticks_processed += 1
                    
                    # Progress logging
                    if total_ticks_processed % 100000 == 0:
                        logger.info(f"Processed {total_ticks_processed:,} ticks, Open positions: {len(self.portfolio.open_positions)}")
            
            current_date += timedelta(days=1)
        
        # Close any remaining open positions
        if self.portfolio.open_positions:
            logger.info(f"Closing {len(self.portfolio.open_positions)} remaining positions at market close")
            # For simplicity, close at last known price
            last_price = tick_df.iloc[-1]['price'] if tick_df is not None else 50000
            last_time = tick_df.iloc[-1]['datetime'] if tick_df is not None else datetime.now()
            
            for i in range(len(self.portfolio.open_positions) - 1, -1, -1):
                self.close_position(i, 'market_close', {
                    'price': last_price, 
                    'datetime': last_time
                })
        
        logger.info(f"Backtest complete! Processed {total_ticks_processed:,} ticks")
        return self.generate_results()
    
    def calculate_drawdown_stats(self):
        """Calculate detailed drawdown statistics"""
        if len(self.balance_history) == 0:
            return {
                'max_drawdown_pct': 0,
                'max_drawdown_usd': 0,
                'drawdown_duration_trades': 0,
                'recovery_time_trades': 0,
                'current_drawdown_pct': 0
            }
        
        balances = [entry['balance'] for entry in self.balance_history]
        initial_balance = self.portfolio.initial_balance
        
        # Calculate running maximum (peak) and drawdown
        peak = initial_balance
        max_drawdown_usd = 0
        max_drawdown_pct = 0
        drawdown_start = None
        max_drawdown_duration = 0
        recovery_time = 0
        
        for i, balance in enumerate(balances):
            # Update peak
            if balance > peak:
                if drawdown_start is not None:
                    # We've recovered - calculate recovery time
                    recovery_time = max(recovery_time, i - drawdown_start)
                    drawdown_start = None
                peak = balance
            
            # Calculate current drawdown
            drawdown_usd = peak - balance
            drawdown_pct = (drawdown_usd / peak) * 100 if peak > 0 else 0
            
            # Track maximum drawdown
            if drawdown_usd > max_drawdown_usd:
                max_drawdown_usd = drawdown_usd
                max_drawdown_pct = drawdown_pct
            
            # Track drawdown duration
            if balance < peak and drawdown_start is None:
                drawdown_start = i
            elif balance < peak and drawdown_start is not None:
                current_duration = i - drawdown_start
                max_drawdown_duration = max(max_drawdown_duration, current_duration)
        
        # Current drawdown
        current_balance = balances[-1] if balances else initial_balance
        current_peak = max(balances) if balances else initial_balance
        current_drawdown_pct = ((current_peak - current_balance) / current_peak) * 100 if current_peak > 0 else 0
        
        return {
            'max_drawdown_pct': max_drawdown_pct,
            'max_drawdown_usd': max_drawdown_usd,
            'drawdown_duration_trades': max_drawdown_duration,
            'recovery_time_trades': recovery_time,
            'current_drawdown_pct': current_drawdown_pct,
            'total_balance_points': len(balances)
        }
    
    def generate_results(self):
        """Generate comprehensive backtest results"""
        if not self.portfolio.closed_trades:
            return {"error": "No completed trades found"}
        
        trades_df = pd.DataFrame([asdict(trade) for trade in self.portfolio.closed_trades])
        
        # Calculate performance metrics
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['is_winner'] == True])
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_pnl = trades_df['pnl'].sum()
        total_fees = trades_df['fees'].sum()
        avg_trade_pnl = trades_df['pnl'].mean()
        
        max_win = trades_df['pnl'].max()
        max_loss = trades_df['pnl'].min()
        avg_win = trades_df[trades_df['is_winner']]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[~trades_df['is_winner']]['pnl'].mean() if losing_trades > 0 else 0
        
        # FIXED: Proper profit factor calculation (Total Gross Profit / Total Gross Loss)
        total_wins = trades_df[trades_df['is_winner']]['pnl'].sum() if winning_trades > 0 else 0
        total_losses = abs(trades_df[~trades_df['is_winner']]['pnl'].sum()) if losing_trades > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Portfolio performance
        initial_balance = self.portfolio.initial_balance
        final_balance = self.portfolio.current_balance
        total_return = (final_balance - initial_balance) / initial_balance
        
        # Timing analysis
        avg_duration = trades_df['duration_minutes'].mean()
        avg_slippage_entry = trades_df['slippage_entry'].mean()
        avg_slippage_exit = trades_df['slippage_exit'].mean()
        total_slippage_cost = (trades_df['slippage_entry'] + trades_df['slippage_exit']).sum()
        
        # Drawdown analysis
        drawdown_stats = self.calculate_drawdown_stats()
        
        results = {
            'backtest_summary': {
                'initial_balance': initial_balance,
                'final_balance': final_balance,
                'total_return': total_return,
                'total_return_pct': total_return * 100,
                'total_pnl': total_pnl,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'win_rate_pct': win_rate * 100,
                'max_drawdown_pct': drawdown_stats['max_drawdown_pct'],
                'max_drawdown_usd': drawdown_stats['max_drawdown_usd']
            },
            'trade_analysis': {
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'avg_trade_pnl': avg_trade_pnl,
                'max_win': max_win,
                'max_loss': max_loss,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor
            },
            'execution_analysis': {
                'total_fees': total_fees,
                'avg_duration_minutes': avg_duration,
                'avg_slippage_entry': avg_slippage_entry,
                'avg_slippage_exit': avg_slippage_exit,
                'total_slippage_cost': total_slippage_cost
            },
            'drawdown_analysis': drawdown_stats,
            'trades_data': trades_df.to_dict('records')
        }
        
        return results
    
    def save_results(self, results, symbol, start_date, end_date):
        """Save backtest results to file"""
        filename = f"tick_backtest_{symbol}_{start_date}_{end_date}.json"
        filepath = self.results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Results saved to {filepath}")
        return filepath

def main():
    """Example usage"""
    backtester = TickBacktester()
    
    # Test with recent data
    symbol = "BTCUSDT"
    end_date = datetime.now().date() - timedelta(days=1)
    start_date = end_date - timedelta(days=2)  # 3-day test
    
    print("Running tick-level backtest...")
    results = backtester.run_backtest(symbol, start_date, end_date)
    
    # Save results
    backtester.save_results(results, symbol, start_date, end_date)
    
    # Print summary
    if 'backtest_summary' in results:
        summary = results['backtest_summary']
        print(f"\n{'='*50}")
        print(f"TICK BACKTEST RESULTS")
        print(f"{'='*50}")
        print(f"Total Return: {summary['total_return_pct']:.2f}%")
        print(f"Total Trades: {summary['total_trades']}")
        print(f"Win Rate: {summary['win_rate_pct']:.1f}%")
        print(f"Final Balance: ${summary['final_balance']:,.2f}")

if __name__ == "__main__":
    main()