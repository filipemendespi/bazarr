# coding=utf-8

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass, field
import json
import traceback

from sqlalchemy import select, update, insert, delete, text
from sqlalchemy.exc import SQLAlchemyError

from app.database import database
from app.config import settings

logger = logging.getLogger(__name__)


class RetryOperationType(Enum):
    """Types of operations that can be retried."""
    SYNC_LIBRARY = "sync_library"
    SYNC_MOVIE = "sync_movie" 
    SYNC_SHOW = "sync_show"
    SYNC_EPISODE = "sync_episode"
    PLEX_CONNECTION = "plex_connection"
    WEBHOOK_PROCESSING = "webhook_processing"


class RetryStatus(Enum):
    """Retry status states."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RetryOperation:
    """Represents a retry operation."""
    operation_type: RetryOperationType
    operation_data: Dict[str, Any]
    max_attempts: int = 3
    current_attempt: int = 0
    next_retry_at: Optional[datetime] = None
    status: RetryStatus = RetryStatus.PENDING
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    operation_id: Optional[str] = None


class PlexRetryService:
    """
    Service for handling retry policies and error recovery for Plex operations.
    """
    
    def __init__(self):
        self.retry_enabled = getattr(settings.plex, 'retry_failed_sync', True)
        self.max_attempts = getattr(settings.plex, 'max_retry_attempts', 3)
        self.retry_delay_minutes = getattr(settings.plex, 'retry_delay_minutes', 15)
        self._ensure_retry_table()
    
    def _ensure_retry_table(self):
        """Ensure the retry operations table exists."""
        try:
            # Create table if it doesn't exist
            database.execute(text("""
                CREATE TABLE IF NOT EXISTS plex_retry_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT UNIQUE NOT NULL,
                    operation_type TEXT NOT NULL,
                    operation_data TEXT NOT NULL,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    current_attempt INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    next_retry_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            database.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_plex_retry_status_next_retry 
                ON plex_retry_operations(status, next_retry_at)
            """))
            database.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_plex_retry_operation_type 
                ON plex_retry_operations(operation_type)
            """))
        except SQLAlchemyError as e:
            logger.error(f"Error creating retry operations table: {e}")
    
    def add_retry_operation(self, operation: RetryOperation) -> bool:
        """
        Add a new retry operation to the queue.
        
        Args:
            operation: The retry operation to add
            
        Returns:
            True if successfully added, False otherwise
        """
        if not self.retry_enabled:
            return False
            
        try:
            operation_id = operation.operation_id or self._generate_operation_id(operation)
            
            # Calculate next retry time
            next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=self.retry_delay_minutes)
            
            # Insert into database
            database.execute(text("""
                INSERT OR REPLACE INTO plex_retry_operations 
                (operation_id, operation_type, operation_data, max_attempts, 
                 current_attempt, status, next_retry_at, created_at, updated_at)
                VALUES (:operation_id, :operation_type, :operation_data, :max_attempts,
                        :current_attempt, :status, :next_retry_at, :created_at, :updated_at)
            """), {
                'operation_id': operation_id,
                'operation_type': operation.operation_type.value,
                'operation_data': json.dumps(operation.operation_data),
                'max_attempts': operation.max_attempts or self.max_attempts,
                'current_attempt': operation.current_attempt,
                'status': operation.status.value,
                'next_retry_at': next_retry_at,
                'created_at': operation.created_at,
                'updated_at': datetime.now(timezone.utc)
            })
            
            logger.info(f"Added retry operation {operation_id} for {operation.operation_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding retry operation: {e}")
            return False
    
    def get_pending_operations(self, limit: int = 50) -> List[RetryOperation]:
        """
        Get pending retry operations that are ready to be executed.
        
        Args:
            limit: Maximum number of operations to return
            
        Returns:
            List of retry operations ready for execution
        """
        if not self.retry_enabled:
            return []
            
        try:
            now = datetime.now(timezone.utc)
            
            results = database.execute(text("""
                SELECT operation_id, operation_type, operation_data, max_attempts,
                       current_attempt, status, error_message, next_retry_at,
                       created_at, updated_at
                FROM plex_retry_operations
                WHERE status = 'pending' 
                  AND (next_retry_at IS NULL OR next_retry_at <= :now)
                ORDER BY created_at ASC
                LIMIT :limit
            """), {'now': now, 'limit': limit}).fetchall()
            
            operations = []
            for row in results:
                op = RetryOperation(
                    operation_type=RetryOperationType(row.operation_type),
                    operation_data=json.loads(row.operation_data),
                    max_attempts=row.max_attempts,
                    current_attempt=row.current_attempt,
                    status=RetryStatus(row.status),
                    error_message=row.error_message,
                    next_retry_at=row.next_retry_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    operation_id=row.operation_id
                )
                operations.append(op)
            
            return operations
            
        except Exception as e:
            logger.error(f"Error getting pending operations: {e}")
            return []
    
    def mark_operation_in_progress(self, operation_id: str) -> bool:
        """Mark an operation as in progress."""
        return self._update_operation_status(operation_id, RetryStatus.IN_PROGRESS)
    
    def mark_operation_completed(self, operation_id: str) -> bool:
        """Mark an operation as completed successfully."""
        return self._update_operation_status(operation_id, RetryStatus.COMPLETED)
    
    def mark_operation_failed(self, operation_id: str, error_message: str, 
                            increment_attempt: bool = True) -> bool:
        """
        Mark an operation as failed and potentially schedule retry.
        
        Args:
            operation_id: The operation ID
            error_message: Error description
            increment_attempt: Whether to increment the attempt counter
            
        Returns:
            True if successfully updated
        """
        try:
            # Get current operation
            result = database.execute(text("""
                SELECT current_attempt, max_attempts FROM plex_retry_operations
                WHERE operation_id = :operation_id
            """), {'operation_id': operation_id}).fetchone()
            
            if not result:
                return False
            
            current_attempt = result.current_attempt
            max_attempts = result.max_attempts
            
            if increment_attempt:
                current_attempt += 1
            
            # Determine next status and retry time
            if current_attempt >= max_attempts:
                # Max attempts reached, mark as failed
                status = RetryStatus.FAILED
                next_retry_at = None
            else:
                # Schedule next retry
                status = RetryStatus.PENDING
                next_retry_at = datetime.now(timezone.utc) + timedelta(
                    minutes=self.retry_delay_minutes * (2 ** (current_attempt - 1))  # Exponential backoff
                )
            
            # Update operation
            database.execute(text("""
                UPDATE plex_retry_operations
                SET current_attempt = :current_attempt,
                    status = :status,
                    error_message = :error_message,
                    next_retry_at = :next_retry_at,
                    updated_at = :updated_at
                WHERE operation_id = :operation_id
            """), {
                'operation_id': operation_id,
                'current_attempt': current_attempt,
                'status': status.value,
                'error_message': error_message,
                'next_retry_at': next_retry_at,
                'updated_at': datetime.now(timezone.utc)
            })
            
            if status == RetryStatus.FAILED:
                logger.warning(f"Operation {operation_id} failed permanently after {current_attempt} attempts")
            else:
                logger.info(f"Operation {operation_id} scheduled for retry at {next_retry_at}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error marking operation failed: {e}")
            return False
    
    def cancel_operation(self, operation_id: str) -> bool:
        """Cancel a pending retry operation."""
        return self._update_operation_status(operation_id, RetryStatus.CANCELLED)
    
    def cleanup_old_operations(self, days: int = 7) -> int:
        """
        Clean up old completed, failed, or cancelled operations.
        
        Args:
            days: Number of days to keep operations
            
        Returns:
            Number of operations cleaned up
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            
            result = database.execute(text("""
                DELETE FROM plex_retry_operations
                WHERE status IN ('completed', 'failed', 'cancelled')
                  AND updated_at < :cutoff_date
            """), {'cutoff_date': cutoff_date})
            
            count = result.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} old retry operations")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up old operations: {e}")
            return 0
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """Get retry operation statistics."""
        try:
            # Overall statistics
            overall_stats = database.execute(text("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM plex_retry_operations
                GROUP BY status
            """)).fetchall()
            
            # Statistics by operation type
            type_stats = database.execute(text("""
                SELECT 
                    operation_type,
                    status,
                    COUNT(*) as count
                FROM plex_retry_operations
                GROUP BY operation_type, status
            """)).fetchall()
            
            # Recent activity (last 24 hours)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            recent_stats = database.execute(text("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM plex_retry_operations
                WHERE updated_at >= :cutoff
                GROUP BY status
            """), {'cutoff': recent_cutoff}).fetchall()
            
            # Format results
            overall = {row.status: row.count for row in overall_stats}
            by_type = {}
            for row in type_stats:
                if row.operation_type not in by_type:
                    by_type[row.operation_type] = {}
                by_type[row.operation_type][row.status] = row.count
            
            recent = {row.status: row.count for row in recent_stats}
            
            return {
                'overall_statistics': overall,
                'by_operation_type': by_type,
                'recent_activity_24h': recent,
                'retry_enabled': self.retry_enabled,
                'max_attempts': self.max_attempts,
                'retry_delay_minutes': self.retry_delay_minutes
            }
            
        except Exception as e:
            logger.error(f"Error getting retry statistics: {e}")
            return {'error': str(e)}
    
    def _update_operation_status(self, operation_id: str, status: RetryStatus) -> bool:
        """Update the status of a retry operation."""
        try:
            database.execute(text("""
                UPDATE plex_retry_operations
                SET status = :status, updated_at = :updated_at
                WHERE operation_id = :operation_id
            """), {
                'operation_id': operation_id,
                'status': status.value,
                'updated_at': datetime.now(timezone.utc)
            })
            return True
            
        except Exception as e:
            logger.error(f"Error updating operation status: {e}")
            return False
    
    def _generate_operation_id(self, operation: RetryOperation) -> str:
        """Generate a unique operation ID."""
        import hashlib
        
        # Create ID from operation type and key data
        key_data = f"{operation.operation_type.value}_{operation.created_at.isoformat()}"
        
        # Add specific identifiers based on operation type
        if operation.operation_type == RetryOperationType.SYNC_LIBRARY:
            key_data += f"_{operation.operation_data.get('library_key', '')}"
        elif operation.operation_type in [RetryOperationType.SYNC_MOVIE, 
                                        RetryOperationType.SYNC_SHOW,
                                        RetryOperationType.SYNC_EPISODE]:
            key_data += f"_{operation.operation_data.get('plex_id', '')}"
        
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def execute_retry_operation(self, operation: RetryOperation, 
                              executor: Callable[[RetryOperation], bool]) -> bool:
        """
        Execute a retry operation with error handling.
        
        Args:
            operation: The retry operation to execute
            executor: Function that executes the actual operation
            
        Returns:
            True if successful, False if failed
        """
        if not operation.operation_id:
            return False
        
        try:
            # Mark as in progress
            self.mark_operation_in_progress(operation.operation_id)
            
            # Execute the operation
            success = executor(operation)
            
            if success:
                self.mark_operation_completed(operation.operation_id)
                logger.info(f"Retry operation {operation.operation_id} completed successfully")
                return True
            else:
                self.mark_operation_failed(operation.operation_id, "Operation returned False")
                return False
                
        except Exception as e:
            error_msg = f"Exception during retry execution: {str(e)}\n{traceback.format_exc()}"
            self.mark_operation_failed(operation.operation_id, error_msg)
            logger.error(f"Retry operation {operation.operation_id} failed: {e}")
            return False


# Singleton instance
retry_service = PlexRetryService()


def with_retry(operation_type: RetryOperationType, operation_data: Dict[str, Any], 
               max_attempts: Optional[int] = None):
    """
    Decorator for adding retry capability to functions.
    
    Args:
        operation_type: Type of operation for retry tracking
        operation_data: Data needed to retry the operation
        max_attempts: Maximum retry attempts (uses config default if None)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Add to retry queue if retry is enabled
                if retry_service.retry_enabled:
                    retry_op = RetryOperation(
                        operation_type=operation_type,
                        operation_data=operation_data,
                        max_attempts=max_attempts or retry_service.max_attempts,
                        error_message=str(e)
                    )
                    retry_service.add_retry_operation(retry_op)
                    logger.warning(f"Operation failed, added to retry queue: {e}")
                
                # Re-raise the exception
                raise
        return wrapper
    return decorator