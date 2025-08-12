#!/usr/bin/env python3
"""
Generate Visualizations from Existing Backtest Results
Creates interactive charts from Freqtrade backtest JSON files
"""

import sys
import logging
from pathlib import Path

# Add the tick_data directory to the path so we can import enhanced_visualizer
sys.path.append(str(Path(__file__).parent))

from enhanced_visualizer import BacktestVisualizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Generate visualizations from existing backtest results"""
    
    # Initialize visualizer
    visualizer = BacktestVisualizer()
    
    # Path to backtest results directory
    results_dir = Path("user_data/backtest_results")
    
    # Find the most recent backtest result files (exclude .meta.json files)
    json_files = [f for f in results_dir.glob("backtest-result-*.json") if not f.name.endswith('.meta.json')]
    
    if not json_files:
        logger.error("No backtest result files found in user_data/backtest_results/")
        logger.info("Available files:")
        for f in results_dir.glob("*.json"):
            logger.info(f"  - {f.name}")
        return
    
    # Sort by filename (which contains timestamp) and get the most recent
    latest_file = sorted(json_files)[-1]
    logger.info(f"Using backtest results from: {latest_file}")
    
    try:
        # Load and convert the results
        logger.info("Loading and converting Freqtrade backtest results...")
        results = visualizer.load_freqtrade_backtest_results(latest_file)
        
        # Extract basic info
        trades_count = len(results['trades_data'])
        win_rate = results['backtest_summary']['win_rate_pct']
        total_return = results['backtest_summary']['total_return_pct']
        max_drawdown = results['backtest_summary']['max_drawdown_pct']
        
        logger.info(f"Loaded {trades_count} trades:")
        logger.info(f"  - Win Rate: {win_rate:.1f}%")
        logger.info(f"  - Total Return: {total_return:.2f}%")
        logger.info(f"  - Max Drawdown: {max_drawdown:.2f}%")
        
        # Extract date range from trades
        if results['trades_data']:
            first_trade = results['trades_data'][0]
            last_trade = results['trades_data'][-1]
            start_date = first_trade['entry_time'].strftime('%Y-%m-%d')
            end_date = last_trade['exit_time'].strftime('%Y-%m-%d')
            symbol = first_trade['pair'].replace('/USDT:USDT', '').replace('/', '')
        else:
            start_date = "2025-08-04"
            end_date = "2025-08-06"
            symbol = "ETH"
        
        logger.info(f"Creating visualizations for {symbol} from {start_date} to {end_date}")
        
        # Generate and save visualizations
        viz_paths = visualizer.save_visualizations(results, symbol, start_date, end_date)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 VISUALIZATIONS CREATED SUCCESSFULLY!")
        logger.info(f"{'='*60}")
        logger.info(f"Comprehensive Analysis: file://{viz_paths['comprehensive'].absolute()}")
        logger.info(f"Trade Timeline:        file://{viz_paths['timeline'].absolute()}")
        logger.info(f"{'='*60}")
        logger.info(f"Open these files in your browser to view interactive charts")
        
        # Show key metrics
        logger.info(f"\n📈 KEY RESULTS:")
        logger.info(f"   Total Trades: {trades_count}")
        logger.info(f"   Win Rate: {win_rate:.1f}%")
        logger.info(f"   Total Return: {total_return:.2f}%")
        logger.info(f"   Max Drawdown: {max_drawdown:.2f}%")
        logger.info(f"   Profit Factor: {results['trade_analysis']['profit_factor']:.2f}")
        logger.info(f"   Best Trade: ${results['trade_analysis']['max_win']:.2f}")
        logger.info(f"   Worst Trade: ${results['trade_analysis']['max_loss']:.2f}")
        
    except Exception as e:
        logger.error(f"Error creating visualizations: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()