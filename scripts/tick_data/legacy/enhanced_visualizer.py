#!/usr/bin/env python3
"""
Enhanced Backtest Visualizer
Creates interactive Plotly charts for comprehensive backtest analysis
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import logging
import json
import pytz

logger = logging.getLogger(__name__)

class BacktestVisualizer:
    """Advanced visualization for backtest results"""
    
    def __init__(self, output_dir="user_data/visualization_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def normalize_datetime(self, dt):
        """Normalize datetime to timezone-naive UTC"""
        if pd.isna(dt):
            return dt
        
        # Convert to pandas datetime if string
        if isinstance(dt, str):
            dt = pd.to_datetime(dt)
        
        # If timezone-aware, convert to UTC then make naive
        if hasattr(dt, 'tz') and dt.tz is not None:
            dt = dt.tz_convert('UTC').tz_localize(None)
        elif isinstance(dt, pd.Timestamp) and dt.tz is not None:
            dt = dt.tz_convert('UTC').tz_localize(None)
        
        return dt
    
    def load_freqtrade_backtest_results(self, results_file):
        """Load and convert Freqtrade backtest results to visualizer format"""
        with open(results_file, 'r') as f:
            data = json.load(f)
        
        strategy_data = list(data['strategy'].values())[0]  # Get first strategy
        trades = strategy_data['trades']
        
        # Convert trades to expected format
        converted_trades = []
        balance_history = []
        running_balance = strategy_data.get('starting_balance', 10000)
        
        for trade in trades:
            # Normalize datetime strings
            entry_time = self.normalize_datetime(trade['open_date'])
            exit_time = self.normalize_datetime(trade['close_date'])
            
            converted_trade = {
                'entry_time': entry_time,
                'exit_time': exit_time,
                'entry_price': trade['open_rate'],
                'exit_price': trade['close_rate'],
                'pnl': trade['profit_abs'],
                'pnl_pct': trade['profit_ratio'],
                'duration_minutes': trade.get('trade_duration', 0),
                'exit_reason': trade['exit_reason'],
                'pair': trade['pair']
            }
            converted_trades.append(converted_trade)
            
            # Create balance history entry
            running_balance += trade['profit_abs']
            balance_history.append({
                'timestamp': exit_time,
                'balance': running_balance,
                'trade_pnl': trade['profit_abs']
            })
        
        # Create backtest summary
        summary = {
            'total_return_pct': strategy_data.get('profit_total', 0) * 100,
            'total_trades': strategy_data.get('total_trades', 0),
            'win_rate_pct': (strategy_data.get('wins', 0) / max(strategy_data.get('total_trades', 1), 1)) * 100,
            'max_drawdown_pct': strategy_data.get('max_drawdown', 0) * 100,
            'final_balance': strategy_data.get('final_balance', running_balance),
            'starting_balance': strategy_data.get('starting_balance', 10000)
        }
        
        # Create trade analysis
        trade_analysis = {
            'profit_factor': strategy_data.get('expectancy_ratio', 0),
            'max_win': max([t['profit_abs'] for t in trades]) if trades else 0,
            'max_loss': min([t['profit_abs'] for t in trades]) if trades else 0,
            'winning_trades': strategy_data.get('wins', 0),
            'losing_trades': strategy_data.get('losses', 0)
        }
        
        return {
            'trades_data': converted_trades,
            'balance_history': balance_history,
            'backtest_summary': summary,
            'trade_analysis': trade_analysis
        }
    
    def create_comprehensive_chart(self, results, symbol, start_date, end_date):
        """Create comprehensive interactive chart with price action and trades"""
        
        trades = results.get('trades_data', [])
        balance_history = results.get('balance_history', [])
        
        # Create subplot figure
        fig = make_subplots(
            rows=4, cols=1,
            subplot_titles=(
                f'{symbol} Price Action with Trade Markers',
                'Balance & Drawdown',
                'Trade P&L Distribution',
                'Performance Metrics'
            ),
            vertical_spacing=0.08,
            row_heights=[0.5, 0.25, 0.15, 0.1],
            specs=[[{"secondary_y": True}],
                   [{"secondary_y": True}],
                   [{"type": "histogram"}],
                   [{"type": "table"}]]
        )
        
        # We'll need actual price data for the main chart
        # For now, create a simulated price series based on trades
        if trades:
            price_data = self._generate_price_series_from_trades(trades, start_date, end_date)
            
            # Main price chart
            fig.add_trace(
                go.Scatter(
                    x=price_data['datetime'],
                    y=price_data['price'],
                    mode='lines',
                    name=f'{symbol} Price',
                    line=dict(color='gray', width=1)
                ),
                row=1, col=1
            )
            
            # Add trade entry markers
            entry_times = [self.normalize_datetime(t['entry_time']) for t in trades]
            entry_prices = [t['entry_price'] for t in trades]
            entry_pnl = [t['pnl'] for t in trades]
            
            fig.add_trace(
                go.Scatter(
                    x=entry_times,
                    y=entry_prices,
                    mode='markers',
                    name='Trade Entries',
                    marker=dict(
                        symbol='triangle-up',
                        size=10,
                        color='blue',
                        line=dict(color='darkblue', width=1)
                    ),
                    hovertemplate='<b>Entry</b><br>Time: %{x}<br>Price: $%{y:.2f}<extra></extra>'
                ),
                row=1, col=1
            )
            
            # Add trade exit markers
            exit_times = [self.normalize_datetime(t['exit_time']) for t in trades]
            exit_prices = [t['exit_price'] for t in trades]
            
            colors = ['green' if pnl > 0 else 'red' for pnl in entry_pnl]
            
            fig.add_trace(
                go.Scatter(
                    x=exit_times,
                    y=exit_prices,
                    mode='markers',
                    name='Trade Exits',
                    marker=dict(
                        symbol='triangle-down',
                        size=10,
                        color=colors,
                        line=dict(color='black', width=1)
                    ),
                    hovertemplate='<b>Exit</b><br>Time: %{x}<br>Price: $%{y:.2f}<br>P&L: %{customdata:.2f}<extra></extra>',
                    customdata=entry_pnl
                ),
                row=1, col=1
            )
        
        # Balance curve
        if balance_history:
            balance_times = [self.normalize_datetime(entry['timestamp']) for entry in balance_history]
            balances = [entry['balance'] for entry in balance_history]
            
            fig.add_trace(
                go.Scatter(
                    x=balance_times,
                    y=balances,
                    mode='lines',
                    name='Account Balance',
                    line=dict(color='blue', width=2),
                    hovertemplate='<b>Balance</b><br>Time: %{x}<br>Balance: $%{y:.2f}<extra></extra>'
                ),
                row=2, col=1
            )
            
            # Calculate and show drawdown
            peak = np.maximum.accumulate(balances)
            drawdown = (np.array(balances) - peak) / peak * 100
            
            fig.add_trace(
                go.Scatter(
                    x=balance_times,
                    y=drawdown,
                    mode='lines',
                    name='Drawdown %',
                    line=dict(color='red', width=1),
                    fill='tozeroy',
                    fillcolor='rgba(255, 0, 0, 0.2)',
                    yaxis='y2',
                    hovertemplate='<b>Drawdown</b><br>Time: %{x}<br>Drawdown: %{y:.2f}%<extra></extra>'
                ),
                row=2, col=1, secondary_y=True
            )
        
        # P&L Distribution histogram
        if trades:
            pnl_values = [t['pnl'] for t in trades]
            
            fig.add_trace(
                go.Histogram(
                    x=pnl_values,
                    nbinsx=20,
                    name='Trade P&L Distribution',
                    marker=dict(
                        color=['green' if x > 0 else 'red' for x in pnl_values],
                        opacity=0.7
                    )
                ),
                row=3, col=1
            )
        
        # Performance metrics table
        summary = results.get('backtest_summary', {})
        trade_analysis = results.get('trade_analysis', {})
        
        metrics_data = [
            ['Metric', 'Value'],
            ['Total Return', f"{summary.get('total_return_pct', 0):.2f}%"],
            ['Total Trades', str(summary.get('total_trades', 0))],
            ['Win Rate', f"{summary.get('win_rate_pct', 0):.1f}%"],
            ['Max Drawdown', f"{summary.get('max_drawdown_pct', 0):.2f}%"],
            ['Profit Factor', f"{trade_analysis.get('profit_factor', 0):.2f}"],
            ['Best Trade', f"${trade_analysis.get('max_win', 0):.2f}"],
            ['Worst Trade', f"${trade_analysis.get('max_loss', 0):.2f}"],
        ]
        
        fig.add_trace(
            go.Table(
                header=dict(
                    values=['<b>Metric</b>', '<b>Value</b>'],
                    fill_color='lightgray',
                    align='left'
                ),
                cells=dict(
                    values=list(zip(*metrics_data[1:])),
                    fill_color='white',
                    align='left'
                )
            ),
            row=4, col=1
        )
        
        # Update layout
        fig.update_layout(
            height=1200,
            title=f'Comprehensive Backtest Analysis - {symbol} ({start_date} to {end_date})',
            showlegend=True,
            template='plotly_white'
        )
        
        # Update y-axes
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="Balance ($)", row=2, col=1)
        fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1, secondary_y=True)
        fig.update_yaxes(title_text="Frequency", row=3, col=1)
        
        fig.update_xaxes(title_text="Time", row=1, col=1)
        fig.update_xaxes(title_text="Time", row=2, col=1)
        fig.update_xaxes(title_text="P&L ($)", row=3, col=1)
        
        return fig
    
    def _generate_price_series_from_trades(self, trades, start_date, end_date):
        """Generate a realistic price series from trade data points"""
        # Extract all price points from trades
        price_points = []
        
        for trade in trades:
            price_points.append({
                'datetime': self.normalize_datetime(trade['entry_time']),
                'price': trade['entry_price']
            })
            price_points.append({
                'datetime': self.normalize_datetime(trade['exit_time']),
                'price': trade['exit_price']
            })
        
        # Sort by time
        price_points = sorted(price_points, key=lambda x: x['datetime'])
        
        if not price_points:
            return pd.DataFrame(columns=['datetime', 'price'])
        
        # Create interpolated price series
        df = pd.DataFrame(price_points)
        df = df.drop_duplicates(subset=['datetime']).reset_index(drop=True)
        
        # Create 5-minute intervals
        start_dt = self.normalize_datetime(start_date)
        end_dt = self.normalize_datetime(end_date) + timedelta(days=1)
        time_range = pd.date_range(start_dt, end_dt, freq='5min')
        
        # Interpolate prices
        full_df = pd.DataFrame({'datetime': time_range})
        full_df = full_df.merge(df, on='datetime', how='left')
        full_df['price'] = full_df['price'].interpolate(method='linear')
        
        # Add some realistic price movement
        if len(full_df) > 1:
            full_df['price'] = full_df['price'].ffill().bfill()
        
        return full_df
    
    def create_trade_timeline(self, results):
        """Create detailed trade timeline visualization"""
        trades = results.get('trades_data', [])
        
        if not trades:
            return go.Figure()
        
        fig = go.Figure()
        
        # Create timeline bars showing trade duration and P&L
        for i, trade in enumerate(trades):
            start_time = self.normalize_datetime(trade['entry_time'])
            end_time = self.normalize_datetime(trade['exit_time'])
            pnl = trade['pnl']
            
            color = 'green' if pnl > 0 else 'red'
            
            duration_hours = (end_time - start_time).total_seconds() / 3600
            
            fig.add_trace(
                go.Bar(
                    x=[duration_hours],
                    y=[f"Trade {i+1}"],
                    orientation='h',
                    marker=dict(color=color, opacity=0.7),
                    name=f"Trade {i+1}",
                    text=f"${pnl:.2f}",
                    textposition="inside",
                    hovertemplate=(
                        f"<b>Trade {i+1}</b><br>"
                        f"Entry: {trade['entry_time']}<br>"
                        f"Exit: {trade['exit_time']}<br>"
                        f"Duration: {trade['duration_minutes']} min<br>"
                        f"P&L: ${pnl:.2f}<br>"
                        f"Return: {trade['pnl_pct']*100:.2f}%"
                        "<extra></extra>"
                    )
                )
            )
        
        fig.update_layout(
            title="Trade Timeline - Duration and P&L",
            xaxis_title="Duration (Hours)",
            yaxis_title="Trades",
            height=max(400, len(trades) * 25),
            showlegend=False,
            template='plotly_white'
        )
        
        return fig
    
    def save_visualizations(self, results, symbol, start_date, end_date):
        """Save all visualizations to HTML files"""
        
        # Main comprehensive chart
        comprehensive_fig = self.create_comprehensive_chart(results, symbol, start_date, end_date)
        comprehensive_path = self.output_dir / f"backtest_analysis_{symbol}_{start_date}_{end_date}.html"
        comprehensive_fig.write_html(str(comprehensive_path))
        
        # Trade timeline
        timeline_fig = self.create_trade_timeline(results)
        timeline_path = self.output_dir / f"trade_timeline_{symbol}_{start_date}_{end_date}.html"
        timeline_fig.write_html(str(timeline_path))
        
        logger.info(f"📊 Visualizations saved:")
        logger.info(f"  - Comprehensive: {comprehensive_path}")
        logger.info(f"  - Timeline: {timeline_path}")
        
        return {
            'comprehensive': comprehensive_path,
            'timeline': timeline_path
        }

def create_enhanced_visualizations(results, symbol, start_date, end_date):
    """Standalone function to create visualizations"""
    visualizer = BacktestVisualizer()
    return visualizer.save_visualizations(results, symbol, start_date, end_date)