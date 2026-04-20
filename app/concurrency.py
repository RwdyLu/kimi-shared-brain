"""
Concurrency Control for Trading Factory System
Supports optimistic locking, pessimistic locking, conflict detection, and retry logic.
"""
import os
import time
import fcntl
import threading
from enum import Enum
from typing import Optional, Callable, Any, Dict
from contextlib import contextmanager
from dataclasses import dataclass


class LockType(Enum):
    """Types of concurrency locks."""
    OPTIMISTIC = "optimistic"    # Version-based
    PESSIMISTIC = "pessimistic"  # File/Mutex lock
    ADAPTIVE = "adaptive"        # Auto-select based on contention


@dataclass
class LockResult:
    """Result of a lock acquisition attempt."""
    success: bool
    lock_type: LockType
    version: Optional[int] = None
    error: Optional[str] = None


class OptimisticLock:
    """
    Optimistic locking using version numbers.
    Best for low-contention scenarios.
    """
    
    def __init__(self, resource_id: str):
        self.resource_id = resource_id
        self._versions: Dict[str, int] = {}
        self._lock = threading.Lock()
    
    def acquire(self, expected_version: int) -> LockResult:
        """
        Attempt to acquire optimistic lock.
        Returns success only if version matches.
        """
        with self._lock:
            current_version = self._versions.get(self.resource_id, 0)
            
            if current_version != expected_version:
                return LockResult(
                    success=False,
                    lock_type=LockType.OPTIMISTIC,
                    version=current_version,
                    error=f"Version mismatch: expected {expected_version}, got {current_version}"
                )
            
            # Increment version
            self._versions[self.resource_id] = current_version + 1
            
            return LockResult(
                success=True,
                lock_type=LockType.OPTIMISTIC,
                version=current_version + 1
            )
    
    def release(self, new_version: int) -> None:
        """Release lock and update version."""
        with self._lock:
            self._versions[self.resource_id] = new_version
    
    def get_version(self) -> int:
        """Get current version."""
        with self._lock:
            return self._versions.get(self.resource_id, 0)


class PessimisticLock:
    """
    Pessimistic locking using file locks or mutex.
    Best for high-contention scenarios.
    """
    
    def __init__(self, resource_id: str, lock_dir: str = "/tmp/kimi-shared-brain/locks"):
        self.resource_id = resource_id
        self.lock_dir = lock_dir
        self._mutex = threading.Lock()
        self._file_lock: Optional[Any] = None
        
        # Ensure lock directory exists
        os.makedirs(lock_dir, exist_ok=True)
        self.lock_file = os.path.join(lock_dir, f"{resource_id}.lock")
    
    @contextmanager
    def acquire(self, timeout: float = 30.0, blocking: bool = True):
        """
        Acquire pessimistic lock with timeout.
        
        Usage:
            with lock.acquire():
                # Critical section
                pass
        """
        lock_file = open(self.lock_file, 'w')
        
        try:
            if blocking:
                # Try to acquire with timeout
                start_time = time.time()
                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except (IOError, OSError):
                        if time.time() - start_time >= timeout:
                            raise TimeoutError(f"Could not acquire lock for {self.resource_id} within {timeout}s")
                        time.sleep(0.1)
            else:
                # Non-blocking
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (IOError, OSError):
                    raise RuntimeError(f"Lock for {self.resource_id} is already held")
            
            self._file_lock = lock_file
            yield LockResult(success=True, lock_type=LockType.PESSIMISTIC)
            
        finally:
            if self._file_lock:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
                self._file_lock = None


class AdaptiveLock:
    """
    Adaptive locking that switches between optimistic and pessimistic based on contention.
    """
    
    def __init__(self, resource_id: str):
        self.resource_id = resource_id
        self.optimistic = OptimisticLock(resource_id)
        self.pessimistic = PessimisticLock(resource_id)
        
        # Contention tracking
        self._conflict_count = 0
        self._success_count = 0
        self._threshold = 3  # Switch to pessimistic after this many conflicts
        self._lock = threading.Lock()
    
    def acquire(self, expected_version: Optional[int] = None, 
                timeout: float = 30.0) -> LockResult:
        """
        Acquire lock using adaptive strategy.
        
        Starts with optimistic, switches to pessimistic if conflicts exceed threshold.
        """
        with self._lock:
            use_pessimistic = self._conflict_count >= self._threshold
        
        if use_pessimistic:
            # Use pessimistic lock
            try:
                with self.pessimistic.acquire(timeout=timeout):
                    with self._lock:
                        self._success_count += 1
                    return LockResult(success=True, lock_type=LockType.ADAPTIVE)
            except TimeoutError as e:
                return LockResult(success=False, lock_type=LockType.ADAPTIVE, error=str(e))
        else:
            # Try optimistic lock
            result = self.optimistic.acquire(expected_version or 0)
            
            with self._lock:
                if result.success:
                    self._success_count += 1
                    self._conflict_count = max(0, self._conflict_count - 1)
                else:
                    self._conflict_count += 1
            
            return result
    
    def get_stats(self) -> Dict[str, int]:
        """Get contention statistics."""
        with self._lock:
            return {
                "conflicts": self._conflict_count,
                "successes": self._success_count,
                "threshold": self._threshold,
                "current_strategy": "pessimistic" if self._conflict_count >= self._threshold else "optimistic"
            }


class RetryWithBackoff:
    """
    Retry logic with exponential backoff for handling transient failures.
    """
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 max_delay: float = 30.0, exponential: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential = exponential
    
    def execute(self, operation: Callable, *args, **kwargs) -> Any:
        """
        Execute operation with retry logic.
        
        Args:
            operation: Callable to execute
            *args, **kwargs: Arguments to pass to operation
            
        Returns:
            Result of operation
            
        Raises:
            Exception: If all retries exhausted
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    # Calculate delay
                    if self.exponential:
                        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    else:
                        delay = self.base_delay
                    
                    time.sleep(delay)
        
        # All retries exhausted
        raise last_exception


# Convenience functions for task management
def with_optimistic_lock(task_id: str, expected_version: int, 
                         operation: Callable) -> Any:
    """
    Execute operation with optimistic locking.
    
    Usage:
        result = with_optimistic_lock("T-001", 1, lambda: update_task(data))
    """
    lock = OptimisticLock(task_id)
    result = lock.acquire(expected_version)
    
    if not result.success:
        raise RuntimeError(f"Optimistic lock failed: {result.error}")
    
    try:
        return operation()
    finally:
        lock.release(result.version)


def with_pessimistic_lock(task_id: str, operation: Callable, 
                          timeout: float = 30.0) -> Any:
    """
    Execute operation with pessimistic locking.
    
    Usage:
        result = with_pessimistic_lock("T-001", lambda: update_task(data))
    """
    lock = PessimisticLock(task_id)
    
    with lock.acquire(timeout=timeout):
        return operation()


def with_retry(operation: Callable, max_retries: int = 3, 
               *args, **kwargs) -> Any:
    """
    Execute operation with retry logic.
    
    Usage:
        result = with_retry(update_task, 3, task_data)
    """
    retry = RetryWithBackoff(max_retries=max_retries)
    return retry.execute(operation, *args, **kwargs)
