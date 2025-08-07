"""
Performance monitoring module for tracking trading latency and execution metrics
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

import numpy as np

from freqtrade.mixins import LoggingMixin


logger = logging.getLogger(__name__)


@dataclass
class LatencyMetrics:
    """Container for latency measurement data"""
    
    timestamp: float
    operation: str
    duration_ms: float
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class LatencyMonitor(LoggingMixin):
    """
    High-performance latency monitoring for trading operations
    
    Tracks:
    - Order execution times
    - API response times
    - WebSocket message latency
    - Strategy calculation times
    """
    
    def __init__(self, window_size: int = 1000):
        """
        Initialize latency monitor
        
        :param window_size: Number of recent measurements to keep for analysis
        """
        self.window_size = window_size
        self._metrics: Dict[str, deque] = {}
        self._lock = Lock()
        self._start_times: Dict[str, float] = {}
        
        # Pre-defined operation categories
        self.operations = {
            'order_create': 'Order Creation',
            'order_cancel': 'Order Cancellation',
            'order_update': 'Order Update',
            'ws_message': 'WebSocket Message',
            'api_call': 'API Call',
            'strategy_calc': 'Strategy Calculation',
            'data_fetch': 'Data Fetch',
            'db_operation': 'Database Operation'
        }
        
        # Initialize deques for each operation type
        for op in self.operations:
            self._metrics[op] = deque(maxlen=window_size)
    
    def start_timer(self, operation_id: str) -> None:
        """Start timing an operation"""
        self._start_times[operation_id] = time.perf_counter()
    
    def end_timer(self, operation_id: str, operation_type: str, 
                  success: bool = True, metadata: Optional[Dict[str, Any]] = None) -> float:
        """
        End timing an operation and record the metrics
        
        :param operation_id: Unique identifier for the operation
        :param operation_type: Type of operation (from self.operations)
        :param success: Whether the operation was successful
        :param metadata: Additional metadata about the operation
        :return: Duration in milliseconds
        """
        if operation_id not in self._start_times:
            logger.warning(f"No start time found for operation {operation_id}")
            return 0.0
        
        end_time = time.perf_counter()
        duration_ms = (end_time - self._start_times[operation_id]) * 1000
        
        # Clean up start time
        del self._start_times[operation_id]
        
        # Record metric
        metric = LatencyMetrics(
            timestamp=time.time(),
            operation=operation_type,
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {}
        )
        
        with self._lock:
            if operation_type in self._metrics:
                self._metrics[operation_type].append(metric)
            else:
                logger.warning(f"Unknown operation type: {operation_type}")
        
        # Log if latency exceeds threshold
        if operation_type == 'order_create' and duration_ms > 50:
            logger.warning(f"High order creation latency: {duration_ms:.2f}ms")
        elif operation_type == 'ws_message' and duration_ms > 10:
            logger.warning(f"High WebSocket latency: {duration_ms:.2f}ms")
        
        return duration_ms
    
    def get_statistics(self, operation_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistical summary of latency metrics
        
        :param operation_type: Specific operation type or None for all
        :return: Dictionary with statistical data
        """
        with self._lock:
            if operation_type:
                if operation_type not in self._metrics:
                    return {}
                
                metrics = list(self._metrics[operation_type])
                if not metrics:
                    return {}
                
                durations = [m.duration_ms for m in metrics]
                success_rate = sum(1 for m in metrics if m.success) / len(metrics) * 100
                
                return {
                    'operation': operation_type,
                    'count': len(metrics),
                    'success_rate': success_rate,
                    'mean_ms': np.mean(durations),
                    'median_ms': np.median(durations),
                    'std_ms': np.std(durations),
                    'min_ms': np.min(durations),
                    'max_ms': np.max(durations),
                    'p95_ms': np.percentile(durations, 95),
                    'p99_ms': np.percentile(durations, 99)
                }
            else:
                # Return statistics for all operations
                stats = {}
                for op_type in self.operations:
                    op_stats = self.get_statistics(op_type)
                    if op_stats:
                        stats[op_type] = op_stats
                return stats
    
    def get_recent_metrics(self, operation_type: str, count: int = 100) -> List[LatencyMetrics]:
        """Get recent metrics for a specific operation type"""
        with self._lock:
            if operation_type not in self._metrics:
                return []
            
            metrics = list(self._metrics[operation_type])
            return metrics[-count:] if len(metrics) > count else metrics
    
    def log_summary(self) -> None:
        """Log a summary of all metrics"""
        stats = self.get_statistics()
        
        if not stats:
            logger.info("No latency metrics collected yet")
            return
        
        logger.info("=== Latency Summary ===")
        for op_type, op_stats in stats.items():
            logger.info(
                f"{self.operations.get(op_type, op_type)}: "
                f"mean={op_stats['mean_ms']:.2f}ms, "
                f"p95={op_stats['p95_ms']:.2f}ms, "
                f"p99={op_stats['p99_ms']:.2f}ms, "
                f"success={op_stats['success_rate']:.1f}%"
            )
    
    def check_performance_targets(self) -> Dict[str, bool]:
        """
        Check if performance targets are being met
        
        Returns dict of operation_type -> is_meeting_target
        """
        targets = {
            'order_create': 50,      # < 50ms
            'ws_message': 10,        # < 10ms
            'api_call': 100,         # < 100ms
            'strategy_calc': 100,    # < 100ms
            'data_fetch': 200,       # < 200ms
        }
        
        results = {}
        stats = self.get_statistics()
        
        for op_type, target_ms in targets.items():
            if op_type in stats:
                results[op_type] = stats[op_type]['p95_ms'] <= target_ms
            else:
                results[op_type] = None
        
        return results
    
    def export_metrics(self, filepath: str) -> None:
        """Export metrics to file for analysis"""
        import json
        
        with self._lock:
            export_data = {
                'timestamp': datetime.now().isoformat(),
                'statistics': self.get_statistics(),
                'performance_targets': self.check_performance_targets(),
                'recent_metrics': {}
            }
            
            # Include last 50 metrics for each operation type
            for op_type in self.operations:
                recent = self.get_recent_metrics(op_type, 50)
                if recent:
                    export_data['recent_metrics'][op_type] = [
                        {
                            'timestamp': m.timestamp,
                            'duration_ms': m.duration_ms,
                            'success': m.success,
                            'metadata': m.metadata
                        }
                        for m in recent
                    ]
        
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Exported performance metrics to {filepath}")


# Global instance for easy access
_monitor_instance: Optional[LatencyMonitor] = None


def get_monitor() -> LatencyMonitor:
    """Get or create the global latency monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = LatencyMonitor()
    return _monitor_instance


# Convenience decorators
def monitor_latency(operation_type: str):
    """Decorator to monitor function execution latency"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = get_monitor()
            operation_id = f"{func.__name__}_{time.time()}"
            monitor.start_timer(operation_id)
            
            try:
                result = func(*args, **kwargs)
                monitor.end_timer(operation_id, operation_type, success=True)
                return result
            except Exception as e:
                monitor.end_timer(operation_id, operation_type, success=False,
                                metadata={'error': str(e)})
                raise
        
        return wrapper
    return decorator