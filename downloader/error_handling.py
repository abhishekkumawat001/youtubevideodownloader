"""
Enhanced error handling system for YouTube Downloader
Provides categorized errors, retry logic with exponential backoff, and detailed error reporting
"""

import time
import random
import logging
import traceback
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from functools import wraps


class ErrorCategory(Enum):
    """Categories of errors that can occur during download"""
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    CONTENT_UNAVAILABLE = "content_unavailable"
    QUOTA_EXCEEDED = "quota_exceeded"
    FORMAT_ERROR = "format_error"
    FILESYSTEM = "filesystem"
    EXTRACTOR = "extractor"
    UNKNOWN = "unknown"


@dataclass
class DownloadError:
    """Structured error information"""
    category: ErrorCategory
    message: str
    original_exception: Optional[Exception] = None
    url: Optional[str] = None
    retry_count: int = 0
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ErrorClassifier:
    """Classifies exceptions into appropriate error categories"""
    
    # Error patterns for classification
    ERROR_PATTERNS = {
        ErrorCategory.NETWORK: [
            "network", "connection", "timeout", "unreachable", "dns",
            "socket", "http", "ssl", "certificate", "proxy"
        ],
        ErrorCategory.AUTHENTICATION: [
            "authentication", "login", "password", "credentials", "unauthorized",
            "forbidden", "access denied", "private", "members only"
        ],
        ErrorCategory.CONTENT_UNAVAILABLE: [
            "not available", "removed", "deleted", "blocked", "restricted",
            "copyright", "unavailable", "private video", "video does not exist"
        ],
        ErrorCategory.QUOTA_EXCEEDED: [
            "quota", "rate limit", "too many requests", "daily limit",
            "exceeded", "throttled"
        ],
        ErrorCategory.FORMAT_ERROR: [
            "format", "codec", "encoding", "unsupported", "invalid format",
            "no suitable formats", "format not available"
        ],
        ErrorCategory.FILESYSTEM: [
            "permission", "disk", "space", "directory", "file", "path",
            "access denied", "read-only", "filesystem"
        ],
        ErrorCategory.EXTRACTOR: [
            "extractor", "parser", "regex", "extraction", "youtube",
            "unable to extract", "no video found"
        ]
    }
    
    @classmethod
    def classify_error(cls, exception: Exception, url: Optional[str] = None) -> ErrorCategory:
        """Classify an exception into an error category"""
        error_text = str(exception).lower()
        
        # Check each category for matching patterns
        for category, patterns in cls.ERROR_PATTERNS.items():
            if any(pattern in error_text for pattern in patterns):
                return category
        
        # Check exception type
        if isinstance(exception, (ConnectionError, TimeoutError)):
            return ErrorCategory.NETWORK
        elif isinstance(exception, PermissionError):
            return ErrorCategory.FILESYSTEM
        elif isinstance(exception, FileNotFoundError):
            return ErrorCategory.FILESYSTEM
        
        return ErrorCategory.UNKNOWN


class RetryStrategy:
    """Implements retry logic with exponential backoff and jitter"""
    
    def __init__(self, 
                 max_retries: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_backoff: bool = True,
                 jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.jitter = jitter
    
    def should_retry(self, error: DownloadError) -> bool:
        """Determine if an error should be retried"""
        if error.retry_count >= self.max_retries:
            return False
        
        # Some errors should not be retried
        non_retryable = {
            ErrorCategory.CONTENT_UNAVAILABLE,
            ErrorCategory.AUTHENTICATION,
        }
        
        if error.category in non_retryable:
            return False
        
        return True
    
    def get_delay(self, retry_count: int) -> float:
        """Calculate delay before next retry"""
        if self.exponential_backoff:
            delay = self.base_delay * (2 ** retry_count)
        else:
            delay = self.base_delay
        
        # Apply maximum delay limit
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)
        
        return delay


class ErrorHandler:
    """Main error handling class with logging and retry coordination"""
    
    def __init__(self, retry_strategy: Optional[RetryStrategy] = None):
        self.retry_strategy = retry_strategy or RetryStrategy()
        self.error_history: List[DownloadError] = []
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def handle_error(self, exception: Exception, url: Optional[str] = None) -> DownloadError:
        """Process and classify an error"""
        category = ErrorClassifier.classify_error(exception, url)
        
        error = DownloadError(
            category=category,
            message=str(exception),
            original_exception=exception,
            url=url
        )
        
        self.error_history.append(error)
        self._log_error(error)
        
        return error
    
    def _log_error(self, error: DownloadError):
        """Log error information"""
        log_message = f"Error ({error.category.value}): {error.message}"
        if error.url:
            log_message += f" [URL: {error.url}]"
        
        if error.category in [ErrorCategory.NETWORK, ErrorCategory.QUOTA_EXCEEDED]:
            self.logger.warning(log_message)
        elif error.category == ErrorCategory.UNKNOWN:
            self.logger.error(log_message)
            if error.original_exception:
                self.logger.debug(traceback.format_exc())
        else:
            self.logger.info(log_message)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors encountered"""
        if not self.error_history:
            return {"total_errors": 0}
        
        category_counts = {}
        for error in self.error_history:
            category = error.category.value
            category_counts[category] = category_counts.get(category, 0) + 1
        
        return {
            "total_errors": len(self.error_history),
            "by_category": category_counts,
            "most_recent": self.error_history[-1].message if self.error_history else None
        }


def with_retry(retry_strategy: Optional[RetryStrategy] = None, 
               error_handler: Optional[ErrorHandler] = None):
    """Decorator to add retry logic to functions"""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            _retry_strategy = retry_strategy or RetryStrategy()
            _error_handler = error_handler or ErrorHandler()
            
            last_error = None
            
            for attempt in range(_retry_strategy.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error = _error_handler.handle_error(e)
                    error.retry_count = attempt
                    last_error = error
                    
                    if attempt < _retry_strategy.max_retries and _retry_strategy.should_retry(error):
                        delay = _retry_strategy.get_delay(attempt)
                        _error_handler.logger.info(
                            f"Retrying in {delay:.1f} seconds... (attempt {attempt + 1}/{_retry_strategy.max_retries + 1})"
                        )
                        time.sleep(delay)
                    else:
                        break
            
            # All retries exhausted
            if last_error and last_error.original_exception:
                raise last_error.original_exception
            elif last_error:
                raise Exception(last_error.message)
            
        return wrapper
    return decorator


class FallbackExtractor:
    """Manages fallback extraction methods when primary extractor fails"""
    
    def __init__(self):
        self.extractors = ["yt-dlp", "pytube"]  # Could add more extractors
        self.current_extractor = 0
    
    def get_next_extractor(self) -> Optional[str]:
        """Get the next available extractor"""
        if self.current_extractor < len(self.extractors):
            extractor = self.extractors[self.current_extractor]
            self.current_extractor += 1
            return extractor
        return None
    
    def reset(self):
        """Reset to first extractor"""
        self.current_extractor = 0


# Example usage and testing functions
def test_error_classification():
    """Test error classification functionality"""
    classifier = ErrorClassifier()
    
    test_cases = [
        (ConnectionError("Network unreachable"), ErrorCategory.NETWORK),
        (Exception("Video not available"), ErrorCategory.CONTENT_UNAVAILABLE),
        (Exception("Rate limit exceeded"), ErrorCategory.QUOTA_EXCEEDED),
        (PermissionError("Access denied"), ErrorCategory.FILESYSTEM),
        (Exception("Unknown error"), ErrorCategory.UNKNOWN),
    ]
    
    for exception, expected_category in test_cases:
        actual_category = classifier.classify_error(exception)
        print(f"Exception: {exception} -> {actual_category.value} (expected: {expected_category.value})")


if __name__ == "__main__":
    # Test the error handling system
    test_error_classification()
    
    # Test retry decorator
    @with_retry(RetryStrategy(max_retries=2, base_delay=0.1))
    def failing_function():
        raise ConnectionError("Network timeout")
    
    try:
        failing_function()
    except Exception as e:
        print(f"Final exception: {e}")
