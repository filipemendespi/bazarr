# coding=utf-8

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .retry_service import retry_service, RetryOperation, RetryOperationType
from .sync import sync_plex_libraries
from .operations import get_plex_server
from app.config import settings

logger = logging.getLogger(__name__)


class PlexRetryWorker:
    """
    Background worker that processes retry operations.
    """
    
    def __init__(self):
        self.is_running = False
    
    def process_pending_operations(self) -> Dict[str, Any]:
        """
        Process all pending retry operations.
        
        Returns:
            Dictionary with processing results
        """
        if self.is_running:
            logger.warning("Retry worker is already running, skipping execution")
            return {'skipped': True, 'reason': 'Already running'}
        
        self.is_running = True
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        try:
            # Get pending operations
            operations = retry_service.get_pending_operations()
            
            if not operations:
                logger.debug("No pending retry operations found")
                return results
            
            logger.info(f"Processing {len(operations)} pending retry operations")
            
            for operation in operations:
                results['processed'] += 1
                
                try:
                    success = self._execute_operation(operation)
                    if success:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        
                except Exception as e:
                    results['failed'] += 1
                    error_msg = f"Error processing operation {operation.operation_id}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
            
            # Cleanup old operations
            cleanup_count = retry_service.cleanup_old_operations()
            if cleanup_count > 0:
                results['cleaned_up'] = cleanup_count
            
            logger.info(f"Retry worker completed: {results['successful']} successful, "
                       f"{results['failed']} failed, {results['processed']} total")
            
        except Exception as e:
            logger.error(f"Error in retry worker: {e}")
            results['errors'].append(f"Worker error: {str(e)}")
        
        finally:
            self.is_running = False
        
        return results
    
    def _execute_operation(self, operation: RetryOperation) -> bool:
        """
        Execute a specific retry operation.
        
        Args:
            operation: The retry operation to execute
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if operation.operation_type == RetryOperationType.SYNC_LIBRARY:
                return self._retry_sync_library(operation)
            elif operation.operation_type == RetryOperationType.SYNC_MOVIE:
                return self._retry_sync_movie(operation)
            elif operation.operation_type == RetryOperationType.SYNC_SHOW:
                return self._retry_sync_show(operation)
            elif operation.operation_type == RetryOperationType.SYNC_EPISODE:
                return self._retry_sync_episode(operation)
            elif operation.operation_type == RetryOperationType.PLEX_CONNECTION:
                return self._retry_plex_connection(operation)
            elif operation.operation_type == RetryOperationType.WEBHOOK_PROCESSING:
                return self._retry_webhook_processing(operation)
            else:
                logger.warning(f"Unknown operation type: {operation.operation_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing retry operation {operation.operation_id}: {e}")
            return False
    
    def _retry_sync_library(self, operation: RetryOperation) -> bool:
        """Retry library synchronization."""
        try:
            library_key = operation.operation_data.get('library_key')
            if not library_key:
                logger.error("Missing library_key in sync_library operation")
                return False
            
            # Use sync_plex_libraries with specific library filter
            result = sync_plex_libraries(
                full_sync=operation.operation_data.get('full_sync', False),
                cleanup_removed=operation.operation_data.get('cleanup_removed', False),
                conflict_strategy=operation.operation_data.get('conflict_strategy', 'plex_wins'),
                library_keys=[library_key]  # Sync only this library
            )
            
            return result.get('success', False)
            
        except Exception as e:
            logger.error(f"Error retrying library sync: {e}")
            return False
    
    def _retry_sync_movie(self, operation: RetryOperation) -> bool:
        """Retry movie synchronization."""
        try:
            plex_id = operation.operation_data.get('plex_id')
            library_key = operation.operation_data.get('library_key')
            
            if not plex_id or not library_key:
                logger.error("Missing plex_id or library_key in sync_movie operation")
                return False
            
            # Get Plex server and movie
            plex_server = get_plex_server()
            if not plex_server:
                return False
            
            # Get the movie from Plex
            movie = plex_server.fetchItem(plex_id)
            if not movie:
                logger.error(f"Movie with ID {plex_id} not found in Plex")
                return False
            
            # Import sync functions
            from .sync import PlexSyncService
            sync_service = PlexSyncService()
            
            # Sync the specific movie
            success = sync_service._sync_movie(movie, library_key)
            
            return success
            
        except Exception as e:
            logger.error(f"Error retrying movie sync: {e}")
            return False
    
    def _retry_sync_show(self, operation: RetryOperation) -> bool:
        """Retry show synchronization."""
        try:
            plex_id = operation.operation_data.get('plex_id')
            library_key = operation.operation_data.get('library_key')
            
            if not plex_id or not library_key:
                logger.error("Missing plex_id or library_key in sync_show operation")
                return False
            
            # Get Plex server and show
            plex_server = get_plex_server()
            if not plex_server:
                return False
            
            # Get the show from Plex
            show = plex_server.fetchItem(plex_id)
            if not show:
                logger.error(f"Show with ID {plex_id} not found in Plex")
                return False
            
            # Import sync functions
            from .sync import PlexSyncService
            sync_service = PlexSyncService()
            
            # Sync the specific show
            success = sync_service._sync_show(show, library_key)
            
            return success
            
        except Exception as e:
            logger.error(f"Error retrying show sync: {e}")
            return False
    
    def _retry_sync_episode(self, operation: RetryOperation) -> bool:
        """Retry episode synchronization."""
        try:
            plex_id = operation.operation_data.get('plex_id')
            show_plex_id = operation.operation_data.get('show_plex_id')
            
            if not plex_id or not show_plex_id:
                logger.error("Missing plex_id or show_plex_id in sync_episode operation")
                return False
            
            # Get Plex server and episode
            plex_server = get_plex_server()
            if not plex_server:
                return False
            
            # Get the episode from Plex
            episode = plex_server.fetchItem(plex_id)
            if not episode:
                logger.error(f"Episode with ID {plex_id} not found in Plex")
                return False
            
            # Import sync functions
            from .sync import PlexSyncService
            sync_service = PlexSyncService()
            
            # Sync the specific episode
            success = sync_service._sync_episode(episode, show_plex_id)
            
            return success
            
        except Exception as e:
            logger.error(f"Error retrying episode sync: {e}")
            return False
    
    def _retry_plex_connection(self, operation: RetryOperation) -> bool:
        """Retry Plex server connection."""
        try:
            # Test Plex connection
            plex_server = get_plex_server()
            if not plex_server:
                return False
            
            # Try to get server info to verify connection
            server_info = plex_server.machineIdentifier
            if server_info:
                logger.info("Plex connection retry successful")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error retrying Plex connection: {e}")
            return False
    
    def _retry_webhook_processing(self, operation: RetryOperation) -> bool:
        """Retry webhook processing."""
        try:
            webhook_data = operation.operation_data.get('webhook_data')
            if not webhook_data:
                logger.error("Missing webhook_data in webhook_processing operation")
                return False
            
            # Import webhook handler
            from api.webhooks.plex import _handle_plex_webhook
            
            # Process the webhook
            result = _handle_plex_webhook(webhook_data)
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Error retrying webhook processing: {e}")
            return False


# Singleton instance
retry_worker = PlexRetryWorker()


def process_plex_retries():
    """
    Function to be called by the scheduler to process retry operations.
    This is the function that will be scheduled to run periodically.
    """
    if not getattr(settings.plex, 'retry_failed_sync', True):
        logger.debug("Plex retry processing is disabled")
        return
    
    logger.debug("Starting Plex retry processing")
    results = retry_worker.process_pending_operations()
    
    if results.get('processed', 0) > 0:
        logger.info(f"Plex retry processing completed: {results}")
    
    return results