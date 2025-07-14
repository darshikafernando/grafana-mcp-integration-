"""Enhanced error handling and resilience patterns."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from functools import wraps

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker implementation for service resilience."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitBreakerState.CLOSED
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply circuit breaker."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                else:
                    raise Exception(f"Circuit breaker OPEN for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise e
        
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return False
        return datetime.utcnow() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
    
    def _on_success(self) -> None:
        """Handle successful operation."""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
    
    def _on_failure(self) -> None:
        """Handle failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")


class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, max_requests: int = 100, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    async def acquire(self) -> bool:
        """Acquire permission to make a request."""
        now = datetime.utcnow()
        
        # Remove old requests outside the time window
        cutoff = now - timedelta(seconds=self.time_window)
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]
        
        # Check if we can make a new request
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        
        return False
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator to apply rate limiting."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not await self.acquire():
                raise Exception(f"Rate limit exceeded for {func.__name__}")
            return await func(*args, **kwargs)
        
        return wrapper


class ErrorContext:
    """Context manager for error tracking and metrics."""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.start_time: Optional[datetime] = None
        self.errors: List[Exception] = []
    
    async def __aenter__(self):
        self.start_time = datetime.utcnow()
        logger.debug(f"Starting operation: {self.operation_name}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = datetime.utcnow() - self.start_time if self.start_time else timedelta(0)
        
        if exc_type:
            self.errors.append(exc_val)
            logger.error(f"Operation {self.operation_name} failed after {duration.total_seconds()}s: {exc_val}")
        else:
            logger.debug(f"Operation {self.operation_name} completed in {duration.total_seconds()}s")
        
        return False  # Don't suppress exceptions


def with_timeout(timeout_seconds: float):
    """Decorator to add timeout to async functions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(f"Function {func.__name__} timed out after {timeout_seconds}s")
                raise
        
        return wrapper
    return decorator


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
    multiplier: float = 2.0
):
    """Retry decorator with exponential backoff."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )


class ServiceHealthCheck:
    """Health check for external services."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.last_check: Optional[datetime] = None
        self.is_healthy = True
        self.consecutive_failures = 0
        self.health_threshold = 3
    
    async def check_health(self, health_func: Callable) -> bool:
        """Perform health check using provided function."""
        try:
            result = await health_func()
            if result:
                self.is_healthy = True
                self.consecutive_failures = 0
                logger.debug(f"Health check passed for {self.service_name}")
            else:
                self._record_failure()
            
            self.last_check = datetime.utcnow()
            return self.is_healthy
            
        except Exception as e:
            logger.error(f"Health check failed for {self.service_name}: {e}")
            self._record_failure()
            return False
    
    def _record_failure(self) -> None:
        """Record a health check failure."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.health_threshold:
            self.is_healthy = False
            logger.warning(f"{self.service_name} marked as unhealthy after {self.consecutive_failures} failures")


class ErrorAggregator:
    """Aggregate and analyze errors across operations."""
    
    def __init__(self):
        self.errors: Dict[str, List[Dict[str, Any]]] = {}
    
    def record_error(self, operation: str, error: Exception, context: Dict[str, Any] = None):
        """Record an error for analysis."""
        if operation not in self.errors:
            self.errors[operation] = []
        
        error_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        }
        
        self.errors[operation].append(error_record)
        
        # Keep only recent errors (last 1000 per operation)
        if len(self.errors[operation]) > 1000:
            self.errors[operation] = self.errors[operation][-1000:]
    
    def get_error_summary(self, operation: str = None) -> Dict[str, Any]:
        """Get summary of errors."""
        if operation:
            operation_errors = self.errors.get(operation, [])
            return self._analyze_errors(operation_errors)
        
        # Overall summary
        total_errors = sum(len(errors) for errors in self.errors.values())
        return {
            "total_errors": total_errors,
            "operations_with_errors": len(self.errors),
            "operations": {op: self._analyze_errors(errors) for op, errors in self.errors.items()}
        }
    
    def _analyze_errors(self, error_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze a list of errors."""
        if not error_list:
            return {"count": 0}
        
        # Count by error type
        error_types = {}
        recent_errors = []
        now = datetime.utcnow()
        
        for error in error_list:
            error_type = error["error_type"]
            error_types[error_type] = error_types.get(error_type, 0) + 1
            
            # Check if error is recent (last hour)
            error_time = datetime.fromisoformat(error["timestamp"])
            if now - error_time < timedelta(hours=1):
                recent_errors.append(error)
        
        return {
            "count": len(error_list),
            "recent_count": len(recent_errors),
            "error_types": error_types,
            "most_common": max(error_types.items(), key=lambda x: x[1]) if error_types else None
        }


# Global instances
error_aggregator = ErrorAggregator()
service_health_checks = {
    "grafana": ServiceHealthCheck("grafana"),
    "kubernetes": ServiceHealthCheck("kubernetes"),
    "cloudwatch": ServiceHealthCheck("cloudwatch")
}


def handle_service_error(service_name: str, operation: str):
    """Decorator to handle service-specific errors."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_aggregator.record_error(
                    f"{service_name}::{operation}",
                    e,
                    {"service": service_name, "operation": operation}
                )
                
                # Mark service as potentially unhealthy
                if service_name in service_health_checks:
                    service_health_checks[service_name]._record_failure()
                
                raise e
        
        return wrapper
    return decorator