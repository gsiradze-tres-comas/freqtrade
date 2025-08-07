"""
Ultra-fast order execution manager for high-frequency trading
"""

import asyncio
import hashlib
import hmac
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import aiohttp
from ccxt import Exchange

from freqtrade.constants import BuySell
from freqtrade.enums import TradingMode
from freqtrade.exceptions import ExchangeError, InvalidOrderException, TemporaryError
from freqtrade.mixins import LoggingMixin
from freqtrade.performance import get_monitor


logger = logging.getLogger(__name__)


class OrderPriority(Enum):
    """Order priority levels for queue management"""
    CRITICAL = 1  # Stop loss, emergency exits
    HIGH = 2      # Take profit, normal exits
    NORMAL = 3    # Regular entries
    LOW = 4       # DCA entries, position adjustments


@dataclass
class FastOrder:
    """Enhanced order structure for fast execution"""
    
    pair: str
    order_type: str
    side: BuySell
    amount: float
    price: Optional[float] = None
    params: Dict[str, Any] = field(default_factory=dict)
    priority: OrderPriority = OrderPriority.NORMAL
    pre_signed: bool = False
    signature: Optional[str] = None
    timestamp: Optional[int] = None
    callback: Optional[Callable] = None
    retry_count: int = 0
    max_retries: int = 3


class ConnectionPool:
    """HTTP connection pool for optimized API requests"""
    
    def __init__(self, size: int = 10, timeout: int = 5):
        self.size = size
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._sessions: List[aiohttp.ClientSession] = []
        self._available: deque = deque()
        self._lock = Lock()
        
    async def initialize(self):
        """Initialize the connection pool"""
        connector = aiohttp.TCPConnector(
            limit=self.size,
            limit_per_host=self.size,
            ttl_dns_cache=300,
            enable_cleanup_closed=True
        )
        
        for _ in range(self.size):
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout
            )
            self._sessions.append(session)
            self._available.append(session)
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get an available session from the pool"""
        while True:
            with self._lock:
                if self._available:
                    return self._available.popleft()
            await asyncio.sleep(0.001)  # Very short wait
    
    def return_session(self, session: aiohttp.ClientSession):
        """Return a session to the pool"""
        with self._lock:
            self._available.append(session)
    
    async def close(self):
        """Close all sessions"""
        for session in self._sessions:
            await session.close()


class FastOrderManager(LoggingMixin):
    """
    High-performance order execution manager
    
    Features:
    - WebSocket order streaming
    - Order pre-signing
    - Connection pooling
    - Priority queue management
    - Circuit breaker protection
    """
    
    def __init__(self, exchange: Exchange, config: Dict[str, Any]):
        self.exchange = exchange
        self.config = config
        self.trading_mode = config.get('trading_mode', TradingMode.SPOT)
        
        # Performance monitoring
        self.monitor = get_monitor()
        
        # Order queue with priority
        self._order_queues: Dict[OrderPriority, deque] = {
            priority: deque() for priority in OrderPriority
        }
        self._queue_lock = Lock()
        
        # Connection pool
        self.pool_size = config.get('order_pool_size', 10)
        self.connection_pool = ConnectionPool(self.pool_size)
        
        # Circuit breaker
        self.circuit_breaker_enabled = config.get('circuit_breaker_enabled', True)
        self.max_failures = config.get('circuit_breaker_max_failures', 5)
        self.failure_window = config.get('circuit_breaker_window', 60)  # seconds
        self._failures: deque = deque()
        self._circuit_open = False
        
        # Pre-signing cache
        self._signature_cache: Dict[str, Tuple[str, int]] = {}
        self._cache_ttl = 30  # seconds
        
        # WebSocket order updates
        self._ws_connected = False
        self._order_callbacks: Dict[str, Callable] = {}
        
        # Async tasks
        self._tasks: List[asyncio.Task] = []
        self._running = False
    
    async def initialize(self):
        """Initialize the fast order manager"""
        logger.info("Initializing FastOrderManager...")
        
        # Initialize connection pool
        await self.connection_pool.initialize()
        
        # Start order processor
        self._running = True
        processor_task = asyncio.create_task(self._process_order_queue())
        self._tasks.append(processor_task)
        
        # Start WebSocket listener if enabled
        if self.config.get('use_order_ws', True):
            ws_task = asyncio.create_task(self._websocket_listener())
            self._tasks.append(ws_task)
        
        logger.info("FastOrderManager initialized successfully")
    
    async def shutdown(self):
        """Shutdown the order manager"""
        logger.info("Shutting down FastOrderManager...")
        
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Close connection pool
        await self.connection_pool.close()
        
        logger.info("FastOrderManager shutdown complete")
    
    def pre_sign_order(self, order: FastOrder) -> FastOrder:
        """
        Pre-sign an order for faster execution
        
        :param order: Order to pre-sign
        :return: Order with signature
        """
        if not self.config.get('enable_order_presigning', False):
            return order
        
        # Check cache first
        cache_key = self._get_order_cache_key(order)
        if cache_key in self._signature_cache:
            signature, timestamp = self._signature_cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                order.signature = signature
                order.timestamp = int(timestamp * 1000)
                order.pre_signed = True
                return order
        
        # Generate new signature
        timestamp = int(time.time() * 1000)
        order.timestamp = timestamp
        
        # Build query string
        params = {
            'symbol': order.pair,
            'side': order.side.upper(),
            'type': order.order_type.upper(),
            'quantity': str(order.amount),
            'timestamp': timestamp
        }
        
        if order.price:
            params['price'] = str(order.price)
        
        params.update(order.params)
        
        query_string = urlencode(sorted(params.items()))
        
        # Sign with API secret
        signature = hmac.new(
            self.exchange._config['exchange']['secret'].encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        order.signature = signature
        order.pre_signed = True
        
        # Cache the signature
        self._signature_cache[cache_key] = (signature, time.time())
        
        return order
    
    def _get_order_cache_key(self, order: FastOrder) -> str:
        """Generate cache key for order signature"""
        return f"{order.pair}:{order.side}:{order.order_type}:{order.amount}:{order.price}"
    
    async def place_order(self, order: FastOrder) -> Dict[str, Any]:
        """
        Place an order with optimized execution
        
        :param order: Order to place
        :return: Order response
        """
        operation_id = f"fast_order_{time.time()}"
        self.monitor.start_timer(operation_id)
        
        try:
            # Check circuit breaker
            if self._is_circuit_open():
                raise TemporaryError("Circuit breaker is open - too many failures")
            
            # Pre-sign if not already done
            if not order.pre_signed:
                order = self.pre_sign_order(order)
            
            # Add to priority queue
            with self._queue_lock:
                self._order_queues[order.priority].append(order)
            
            # Wait for order completion (with timeout)
            result = await self._wait_for_order_completion(order, timeout=5)
            
            self.monitor.end_timer(operation_id, 'order_create', success=True,
                                 metadata={'priority': order.priority.name})
            
            return result
            
        except Exception as e:
            self.monitor.end_timer(operation_id, 'order_create', success=False,
                                 metadata={'error': str(e)})
            self._record_failure()
            raise
    
    async def _process_order_queue(self):
        """Process orders from the priority queue"""
        while self._running:
            try:
                # Process orders by priority
                for priority in OrderPriority:
                    with self._queue_lock:
                        if self._order_queues[priority]:
                            order = self._order_queues[priority].popleft()
                            asyncio.create_task(self._execute_order(order))
                
                await asyncio.sleep(0.001)  # Very short sleep
                
            except Exception as e:
                logger.error(f"Error in order processor: {e}")
                await asyncio.sleep(0.1)
    
    async def _execute_order(self, order: FastOrder):
        """Execute a single order"""
        session = None
        try:
            session = await self.connection_pool.get_session()
            
            # Build request
            url = self._get_order_endpoint(order)
            headers = self._get_headers(order)
            data = self._build_order_data(order)
            
            # Execute request
            async with session.post(url, json=data, headers=headers) as response:
                result = await response.json()
                
                if response.status == 200:
                    # Success - trigger callback if provided
                    if order.callback:
                        await order.callback(result)
                    
                    # Store for completion waiting
                    if hasattr(order, '_future'):
                        order._future.set_result(result)
                else:
                    # Handle error
                    error_msg = result.get('msg', 'Unknown error')
                    
                    if order.retry_count < order.max_retries:
                        order.retry_count += 1
                        logger.warning(f"Order failed, retrying ({order.retry_count}/{order.max_retries}): {error_msg}")
                        
                        # Re-queue with same priority
                        with self._queue_lock:
                            self._order_queues[order.priority].append(order)
                    else:
                        raise ExchangeError(f"Order failed after {order.max_retries} retries: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error executing order: {e}")
            if hasattr(order, '_future'):
                order._future.set_exception(e)
        
        finally:
            if session:
                self.connection_pool.return_session(session)
    
    def _get_order_endpoint(self, order: FastOrder) -> str:
        """Get the appropriate order endpoint"""
        base_url = self.exchange._ccxt_config['urls']['api']['fapiPrivate']
        
        if self.trading_mode == TradingMode.FUTURES:
            return f"{base_url}/fapi/v1/order"
        else:
            return f"{base_url}/api/v3/order"
    
    def _get_headers(self, order: FastOrder) -> Dict[str, str]:
        """Get request headers"""
        return {
            'X-MBX-APIKEY': self.exchange._config['exchange']['key'],
            'Content-Type': 'application/json'
        }
    
    def _build_order_data(self, order: FastOrder) -> Dict[str, Any]:
        """Build order request data"""
        data = {
            'symbol': order.pair.replace('/', ''),
            'side': order.side.upper(),
            'type': order.order_type.upper(),
            'quantity': str(order.amount),
            'timestamp': order.timestamp or int(time.time() * 1000),
            'signature': order.signature
        }
        
        if order.price:
            data['price'] = str(order.price)
        
        data.update(order.params)
        
        return data
    
    async def _wait_for_order_completion(self, order: FastOrder, timeout: float) -> Dict[str, Any]:
        """Wait for order completion with timeout"""
        future = asyncio.Future()
        order._future = future
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise TemporaryError(f"Order placement timed out after {timeout}s")
    
    async def _websocket_listener(self):
        """Listen for order updates via WebSocket"""
        # This would connect to exchange WebSocket for order updates
        # Implementation depends on specific exchange WebSocket API
        logger.info("WebSocket order listener started (placeholder)")
        
        while self._running:
            await asyncio.sleep(1)
            # TODO: Implement actual WebSocket connection
    
    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open"""
        if not self.circuit_breaker_enabled:
            return False
        
        # Clean old failures
        current_time = time.time()
        while self._failures and current_time - self._failures[0] > self.failure_window:
            self._failures.popleft()
        
        # Check if we've exceeded max failures
        if len(self._failures) >= self.max_failures:
            if not self._circuit_open:
                logger.error(f"Circuit breaker opened - {len(self._failures)} failures in {self.failure_window}s")
                self._circuit_open = True
            return True
        
        if self._circuit_open:
            logger.info("Circuit breaker closed")
            self._circuit_open = False
        
        return False
    
    def _record_failure(self):
        """Record a failure for circuit breaker"""
        self._failures.append(time.time())
    
    async def batch_place_orders(self, orders: List[FastOrder]) -> List[Dict[str, Any]]:
        """
        Place multiple orders in batch
        
        :param orders: List of orders to place
        :return: List of order responses
        """
        # Pre-sign all orders
        signed_orders = [self.pre_sign_order(order) for order in orders]
        
        # Place orders concurrently
        tasks = [self.place_order(order) for order in signed_orders]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        successful = []
        failed = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed.append((orders[i], result))
                logger.error(f"Batch order failed: {result}")
            else:
                successful.append(result)
        
        if failed:
            logger.warning(f"Batch placement: {len(successful)} succeeded, {len(failed)} failed")
        
        return successful